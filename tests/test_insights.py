"""Tests for insights module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.database import create_tables, upsert_transactions
from src.insights import category_breakdown, detect_spending_anomalies, savings_rate, wallet_brief


@pytest.fixture
def populated_db():
    """Create a temp SQLite database with test transaction data."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    engine = create_engine(f"sqlite:///{db_path}")
    create_tables(engine)

    base = {
        "subscription_label": None,
        "is_subscription": 0,
        "llm_category": None,
        "cleaned_merchant": None,
    }
    rows = [
        {
            "id": "t1",
            "account_id": "a1",
            "date": "2026-08-01",
            "description": "Netflix",
            "amount": -14.99,
            "category": "Entertainment",
            "is_subscription": 1,
            "subscription_label": "Netflix",
            "llm_category": None,
            "cleaned_merchant": None,
        },
        {
            "id": "t2",
            "account_id": "a1",
            "date": "2026-08-01",
            "description": "Salary",
            "amount": 5000.00,
            "category": "Income",
            **base,
        },
        {
            "id": "t3",
            "account_id": "a1",
            "date": "2026-08-01",
            "description": "Groceries",
            "amount": -120.50,
            "category": "Groceries",
            **base,
        },
        {
            "id": "t4",
            "account_id": "a1",
            "date": "2026-07-01",
            "description": "Netflix",
            "amount": -14.99,
            "category": "Entertainment",
            "is_subscription": 1,
            "subscription_label": "Netflix",
            "llm_category": None,
            "cleaned_merchant": None,
        },
        {
            "id": "t5",
            "account_id": "a1",
            "date": "2026-07-01",
            "description": "Salary",
            "amount": 5000.00,
            "category": "Income",
            **base,
        },
        {
            "id": "t6",
            "account_id": "a1",
            "date": "2026-07-01",
            "description": "Groceries",
            "amount": -95.00,
            "category": "Groceries",
            **base,
        },
        {
            "id": "t7",
            "account_id": "a1",
            "date": "2026-06-01",
            "description": "Netflix",
            "amount": -14.99,
            "category": "Entertainment",
            "is_subscription": 1,
            "subscription_label": "Netflix",
            "llm_category": None,
            "cleaned_merchant": None,
        },
        {
            "id": "t8",
            "account_id": "a1",
            "date": "2026-06-01",
            "description": "Salary",
            "amount": 5000.00,
            "category": "Income",
            **base,
        },
        {
            "id": "t9",
            "account_id": "a1",
            "date": "2026-06-01",
            "description": "Groceries",
            "amount": -110.00,
            "category": "Groceries",
            **base,
        },
    ]
    upsert_transactions(engine, rows)

    yield str(db_path)

    engine.dispose()
    db_path.unlink(missing_ok=True)


def test_category_breakdown(populated_db):
    """category_breakdown should return monthly category aggregates."""
    df = category_breakdown(populated_db, months=3)
    assert not df.is_empty()
    categories = df["category"].unique().to_list()
    assert "Entertainment" in categories
    assert "Groceries" in categories
    assert df["month"].n_unique() >= 2


def test_detect_spending_anomalies(populated_db):
    """detect_spending_anomalies should flag outlier days."""
    df = detect_spending_anomalies(populated_db, z_threshold=0.1)
    assert "flagged" in df.columns
    assert "z_score" in df.columns


def test_savings_rate(populated_db):
    """savings_rate should compute income/expenses/rate."""
    result = savings_rate(populated_db, months=3)
    assert "monthly_income" in result
    assert "monthly_expenses" in result
    assert "savings_rate" in result
    assert result["monthly_income"] == 5000.0
    assert result["monthly_expenses"] > 0


def test_wallet_brief(populated_db):
    """wallet_brief should return a complete overview dict."""
    brief = wallet_brief(populated_db)
    assert "savings_rate" in brief
    assert "top_categories" in brief
    assert "subscriptions" in brief
    assert "anomalies" in brief
    saverate = brief["savings_rate"]
    assert saverate["monthly_income"] == 5000.0


def test_empty_database():
    """Insights on empty database should not crash."""
    import tempfile

    db_path = Path(tempfile.mktemp(suffix=".db"))
    engine = create_engine(f"sqlite:///{db_path}")
    create_tables(engine)

    try:
        df = category_breakdown(str(db_path), months=3)
        assert df.is_empty()

        result = savings_rate(str(db_path))
        assert result["monthly_income"] == 0.0
        assert result["savings_rate"] == 0.0
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)
