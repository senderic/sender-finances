"""Tests for database module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.database import (
    create_tables,
    get_engine,
    insert_snapshot,
    update_enrichment,
    upsert_accounts,
    upsert_categories,
    upsert_tags,
    upsert_transactions,
)


@pytest.fixture
def engine():
    """Create a temporary in-memory SQLite database."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    eng = create_engine(f"sqlite:///{db_path}")
    create_tables(eng)
    yield eng
    eng.dispose()
    db_path.unlink(missing_ok=True)


def test_create_tables(engine):
    """create_tables should create all expected tables."""
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        ).fetchall()
    table_names = {r[0] for r in tables}
    expected = {"accounts", "transactions", "categories", "tags", "snapshots", "net_worth_snapshots"}
    assert expected.issubset(table_names)


def test_upsert_accounts(engine):
    """upsert_accounts should insert new accounts."""
    rows = [
        {
            "id": "acc-1",
            "name": "Checking",
            "type": "CHECKING",
            "subtype": None,
            "balance": 5000.0,
            "currency": "USD",
            "financial_institution": "Chase",
            "is_closed": 0,
            "raw_json": "{}",
        }
    ]
    count = upsert_accounts(engine, rows)
    assert count == 1

    with engine.connect() as conn:
        result = conn.execute(text("SELECT name, balance FROM accounts WHERE id = 'acc-1'")).fetchone()
    assert result[0] == "Checking"
    assert result[1] == 5000.0


def test_upsert_accounts_update(engine):
    """upsert_accounts should update existing accounts on conflict."""
    rows = [{"id": "acc-1", "name": "Checking", "type": "CHECKING", "balance": 5000.0}]
    upsert_accounts(engine, rows)

    rows[0]["balance"] = 6000.0
    rows[0]["name"] = "Checking Updated"
    upsert_accounts(engine, rows)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT name, balance FROM accounts WHERE id = 'acc-1'")).fetchone()
    assert result[0] == "Checking Updated"
    assert result[1] == 6000.0


def test_upsert_transactions(engine):
    """upsert_transactions should insert new transactions."""
    rows = [
        {
            "id": "txn-1",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "description": "Coffee shop",
            "amount": -4.50,
            "category": "Restaurants",
            "category_id": "cat-1",
            "tag": None,
            "is_pending": 0,
            "merchant_name": "Starbucks",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
            "raw_json": "{}",
        }
    ]
    count = upsert_transactions(engine, rows)
    assert count == 1

    with engine.connect() as conn:
        result = conn.execute(text("SELECT description, amount FROM transactions WHERE id = 'txn-1'")).fetchone()
    assert result[0] == "Coffee shop"
    assert result[1] == -4.50


def test_upsert_transactions_dedup(engine):
    """upsert_transactions should not duplicate on repeated insert."""
    rows = [{"id": "txn-1", "account_id": "acc-1", "date": "2026-08-01", "amount": -4.50}]
    count1 = upsert_transactions(engine, rows)
    count2 = upsert_transactions(engine, rows)
    assert count1 >= 1
    assert count2 >= 1

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM transactions WHERE id = 'txn-1'")).scalar()
    assert total == 1


def test_upsert_categories(engine):
    """upsert_categories should insert categories."""
    rows = [{"id": "cat-1", "name": "Restaurants", "parent_id": None, "is_income": 0}]
    count = upsert_categories(engine, rows)
    assert count == 1


def test_upsert_tags(engine):
    """upsert_tags should insert tags."""
    rows = [{"id": "tag-1", "name": "Vacation"}]
    count = upsert_tags(engine, rows)
    assert count == 1


def test_insert_snapshot(engine):
    """insert_snapshot should store a snapshot record."""
    row = {"fetched_at": "2026-08-01T12:00:00", "dataset_id": "ds-1", "account_count": 5, "transaction_count": 100, "raw_json": "{}"}
    count = insert_snapshot(engine, row)
    assert count == 1

    with engine.connect() as conn:
        result = conn.execute(text("SELECT account_count FROM snapshots")).fetchone()
    assert result[0] == 5


def test_update_enrichment(engine):
    """update_enrichment should update enrichment fields on a transaction."""
    rows = [{"id": "txn-1", "account_id": "acc-1", "date": "2026-08-01", "amount": -4.50}]
    upsert_transactions(engine, rows)

    update_enrichment(engine, "txn-1", {"llm_category": "Restaurants", "is_subscription": 1})

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT llm_category, is_subscription FROM transactions WHERE id = 'txn-1'")
        ).fetchone()
    assert result[0] == "Restaurants"
    assert result[1] == 1
