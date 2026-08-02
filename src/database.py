"""Database engine, table creation, and upsert helpers.

Uses SQLAlchemy Core (not ORM). Tables are created via ``metadata.create_all()``
and writes use ``insert()`` with SQLite ``ON CONFLICT`` for idempotent upserts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
import structlog

from src.models import metadata

logger = structlog.get_logger()


def get_engine(db_path: str | Path) -> Engine:
    """Create a SQLAlchemy engine for a SQLite database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A SQLAlchemy Engine instance.
    """
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    return create_engine(url, echo=False)


def create_tables(engine: Engine) -> None:
    """Create all tables defined in the metadata if they do not exist.

    Args:
        engine: A SQLAlchemy Engine instance.
    """
    metadata.create_all(engine, checkfirst=True)
    logger.info("tables_created")


def upsert_accounts(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Insert or update account records.

    Args:
        engine: A SQLAlchemy Engine instance.
        rows: List of account dicts from Simplifi.

    Returns:
        Number of rows affected.
    """
    if not rows:
        return 0

    from src.models import accounts

    with engine.begin() as conn:
        stmt = sqlite_insert(accounts).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "type": stmt.excluded.type,
                "subtype": stmt.excluded.subtype,
                "balance": stmt.excluded.balance,
                "currency": stmt.excluded.currency,
                "financial_institution": stmt.excluded.financial_institution,
                "is_closed": stmt.excluded.is_closed,
                "raw_json": stmt.excluded.raw_json,
            },
        )
        result = conn.execute(stmt)
    logger.info("accounts_upserted", count=result.rowcount)
    return result.rowcount


def upsert_transactions(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Insert new or update existing transaction records.

    Matches on the Simplifi transaction ID. Existing rows are updated
    with fresh data (e.g. categories change, pending status resolves).

    Args:
        engine: A SQLAlchemy Engine instance.
        rows: List of normalized transaction dicts.

    Returns:
        Number of rows affected.
    """
    if not rows:
        return 0

    from src.models import transactions

    with engine.begin() as conn:
        stmt = sqlite_insert(transactions).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "account_id": stmt.excluded.account_id,
                "date": stmt.excluded.date,
                "description": stmt.excluded.description,
                "amount": stmt.excluded.amount,
                "category": stmt.excluded.category,
                "category_id": stmt.excluded.category_id,
                "tag": stmt.excluded.tag,
                "is_pending": stmt.excluded.is_pending,
                "merchant_name": stmt.excluded.merchant_name,
                "cleaned_merchant": stmt.excluded.cleaned_merchant,
                "is_subscription": stmt.excluded.is_subscription,
                "subscription_label": stmt.excluded.subscription_label,
                "llm_category": stmt.excluded.llm_category,
                "raw_json": stmt.excluded.raw_json,
            },
        )
        result = conn.execute(stmt)
    logger.info("transactions_upserted", count=result.rowcount)
    return result.rowcount


def upsert_categories(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Insert or update category records.

    Args:
        engine: A SQLAlchemy Engine instance.
        rows: List of category dicts from Simplifi.

    Returns:
        Number of rows affected.
    """
    if not rows:
        return 0

    from src.models import categories

    with engine.begin() as conn:
        stmt = sqlite_insert(categories).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "parent_id": stmt.excluded.parent_id,
                "is_income": stmt.excluded.is_income,
            },
        )
        result = conn.execute(stmt)
    logger.info("categories_upserted", count=result.rowcount)
    return result.rowcount


def upsert_tags(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Insert or update tag records.

    Args:
        engine: A SQLAlchemy Engine instance.
        rows: List of tag dicts from Simplifi.

    Returns:
        Number of rows affected.
    """
    if not rows:
        return 0

    from src.models import tags

    with engine.begin() as conn:
        stmt = sqlite_insert(tags).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"name": stmt.excluded.name},
        )
        result = conn.execute(stmt)
    logger.info("tags_upserted", count=result.rowcount)
    return result.rowcount


def insert_snapshot(engine: Engine, row: dict[str, Any]) -> int:
    """Insert a data snapshot record.

    Args:
        engine: A SQLAlchemy Engine instance.
        row: Snapshot dict with fetched_at, counts, raw_json.

    Returns:
        Row count (1).
    """
    from src.models import snapshots

    with engine.begin() as conn:
        result = conn.execute(snapshots.insert().values(**row))
    logger.info("snapshot_inserted", id=result.inserted_primary_key[0])
    return 1


def update_enrichment(
    engine: Engine, transaction_id: str, updates: dict[str, Any]
) -> None:
    """Update enrichment fields on a transaction.

    Preserves existing enrichment fields unless explicitly overwritten.

    Args:
        engine: A SQLAlchemy Engine instance.
        transaction_id: The Simplifi transaction ID.
        updates: Dict of column_name -> new_value to merge.
    """
    from src.models import transactions

    with engine.begin() as conn:
        stmt = (
            transactions.update()
            .where(transactions.c.id == transaction_id)
            .values(**updates)
        )
        result = conn.execute(stmt)
    if result.rowcount == 0:
        logger.warning("enrichment_no_match", transaction_id=transaction_id)
