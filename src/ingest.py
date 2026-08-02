"""Pull data from Quicken Simplifi and store it in the local SQLite database.

Orchestrates authentication (cached token), data retrieval (accounts,
transactions, categories, tags), normalization, and upsert into the
database. Also saves a raw snapshot for auditability.

Usage::

    from src.config import Settings
    from src.ingest import ingest

    settings = Settings.from_yaml("config.yaml").resolve_env_vars()
    result = ingest(settings)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from simplifiapi.client import Client

from src.database import (
    create_tables,
    get_engine,
    insert_snapshot,
    upsert_accounts,
    upsert_categories,
    upsert_tags,
    upsert_transactions,
)
from src.token_store import load_token

logger = structlog.get_logger()


def _normalize_account(account: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize fields from a Simplifi account resource."""
    return {
        "id": account.get("id", ""),
        "name": account.get("name", ""),
        "type": account.get("type"),
        "subtype": account.get("subtype"),
        "balance": account.get("balance"),
        "currency": account.get("currency"),
        "financial_institution": account.get("financialInstitution"),
        "is_closed": 1 if account.get("isClosed") else 0,
        "raw_json": json.dumps(account),
    }


def _normalize_transaction(txn: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize fields from a Simplifi transaction resource."""
    cat = txn.get("category", {}) if isinstance(txn.get("category"), dict) else {}
    tag_list = txn.get("tags", [])
    tag_name = tag_list[0].get("name") if tag_list else None
    return {
        "id": txn.get("id", ""),
        "account_id": txn.get("accountId", ""),
        "date": txn.get("date"),
        "description": txn.get("description"),
        "amount": txn.get("amount"),
        "category": cat.get("name"),  # Simplifi native category
        "category_id": cat.get("id"),
        "tag": tag_name,
        "is_pending": 1 if txn.get("isPending") else 0,
        "merchant_name": txn.get("merchantName"),
        "cleaned_merchant": None,
        "is_subscription": 0,
        "subscription_label": None,
        "llm_category": None,
        "raw_json": json.dumps(txn),
    }


def _normalize_category(cat: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Simplifi category resource."""
    return {
        "id": cat.get("id", ""),
        "name": cat.get("name", ""),
        "parent_id": cat.get("parentCategoryId"),
        "is_income": 1 if cat.get("isIncome") else 0,
    }


def _normalize_tag(tag: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Simplifi tag resource."""
    return {
        "id": tag.get("id", ""),
        "name": tag.get("name", ""),
    }


def ingest(settings) -> dict[str, Any]:
    """Run the full ingest pipeline.

    Args:
        settings: A resolved Settings instance.

    Returns:
        Dict with counts and status.
    """

    logger.info("ingest_started")

    token = load_token(str(settings.simplifi.resolved_token_path))
    if not token:
        logger.error("ingest_skipped_no_token")
        return {"status": "skipped", "reason": "no_valid_token"}

    client = Client()
    if not client.verify_token(token):
        logger.error("ingest_skipped_auth_failure")
        return {"status": "skipped", "reason": "auth_failure"}

    datasets = client.get_datasets()
    if not datasets:
        logger.error("ingest_skipped_no_datasets")
        return {"status": "skipped", "reason": "no_datasets"}

    dataset_id = datasets[0]["id"]
    logger.info("dataset_selected", dataset_id=dataset_id)

    accounts_raw = client.get_accounts(dataset_id)
    transactions_raw = client.get_transactions(dataset_id)
    categories_raw = client.get_categories(dataset_id)
    tags_raw = client.get_tags(dataset_id)

    accounts_norm = [_normalize_account(a) for a in accounts_raw]
    transactions_norm = [_normalize_transaction(t) for t in transactions_raw]
    categories_norm = [_normalize_category(c) for c in categories_raw]
    tags_norm = [_normalize_tag(t) for t in tags_raw]

    engine = get_engine(settings.database.resolved_path)
    create_tables(engine)

    acct_count = upsert_accounts(engine, accounts_norm)
    txn_count = upsert_transactions(engine, transactions_norm)
    cat_count = upsert_categories(engine, categories_norm)
    tag_count = upsert_tags(engine, tags_norm)

    now = datetime.now(UTC).isoformat()
    insert_snapshot(
        engine,
        {
            "fetched_at": now,
            "dataset_id": dataset_id,
            "account_count": len(accounts_raw),
            "transaction_count": len(transactions_raw),
            "raw_json": json.dumps(
                {
                    "dataset_id": dataset_id,
                    "accounts": len(accounts_raw),
                    "transactions": len(transactions_raw),
                    "categories": len(categories_raw),
                    "tags": len(tags_raw),
                }
            ),
        },
    )

    result = {
        "status": "ok",
        "dataset_id": dataset_id,
        "accounts": acct_count,
        "transactions": txn_count,
        "categories": cat_count,
        "tags": tag_count,
        "fetched_at": now,
    }
    logger.info(
        "ingest_complete",
        accounts=acct_count,
        transactions=txn_count,
        categories=cat_count,
        tags=tag_count,
    )
    return result
