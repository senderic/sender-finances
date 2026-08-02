"""Tests for ingest module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.ingest import _normalize_account, _normalize_category, _normalize_tag, _normalize_transaction


def test_normalize_account():
    """Should extract fields from Simplifi account dict."""
    raw = {
        "id": "acc-1",
        "name": "Checking",
        "type": "CHECKING",
        "subtype": "Personal",
        "balance": 3500.50,
        "currency": "USD",
        "financialInstitution": "Chase",
        "isClosed": False,
    }
    result = _normalize_account(raw)
    assert result["id"] == "acc-1"
    assert result["name"] == "Checking"
    assert result["balance"] == 3500.50
    assert result["is_closed"] == 0
    assert result["raw_json"]


def test_normalize_account_closed():
    """is_closed should be 1 when isClosed is True."""
    raw = {"id": "acc-2", "name": "Old Card", "isClosed": True}
    result = _normalize_account(raw)
    assert result["is_closed"] == 1


def test_normalize_transaction():
    """Should extract fields from Simplifi transaction dict."""
    raw = {
        "id": "txn-1",
        "accountId": "acc-1",
        "date": "2026-08-01",
        "description": "Grocery store",
        "amount": -85.42,
        "category": {"id": "cat-5", "name": "Groceries"},
        "tags": [{"id": "tag-1", "name": "Food"}],
        "isPending": False,
        "merchantName": "Whole Foods",
    }
    result = _normalize_transaction(raw)
    assert result["id"] == "txn-1"
    assert result["account_id"] == "acc-1"
    assert result["amount"] == -85.42
    assert result["category"] == "Groceries"
    assert result["category_id"] == "cat-5"
    assert result["tag"] == "Food"
    assert result["is_pending"] == 0
    assert result["merchant_name"] == "Whole Foods"
    assert result["cleaned_merchant"] is None
    assert result["is_subscription"] == 0


def test_normalize_transaction_no_tags():
    """Should handle transactions without tags."""
    raw = {"id": "txn-2", "accountId": "acc-1", "date": "2026-08-01", "amount": -10.00}
    result = _normalize_transaction(raw)
    assert result["tag"] is None
    assert result["category"] is None


def test_normalize_transaction_none_category():
    """Should handle transactions where category is None (not a dict)."""
    raw = {"id": "txn-3", "accountId": "acc-1", "category": None}
    result = _normalize_transaction(raw)
    assert result["category"] is None
    assert result["category_id"] is None


def test_normalize_category():
    """Should normalize category resources."""
    raw = {"id": "cat-1", "name": "Restaurants", "parentCategoryId": "parent-1", "isIncome": False}
    result = _normalize_category(raw)
    assert result["id"] == "cat-1"
    assert result["name"] == "Restaurants"
    assert result["parent_id"] == "parent-1"
    assert result["is_income"] == 0


def test_normalize_category_income():
    """Income categories should set is_income=1."""
    raw = {"id": "cat-10", "name": "Salary", "isIncome": True}
    result = _normalize_category(raw)
    assert result["is_income"] == 1


def test_normalize_tag():
    """Should normalize tag resources."""
    raw = {"id": "tag-1", "name": "Travel"}
    result = _normalize_tag(raw)
    assert result["id"] == "tag-1"
    assert result["name"] == "Travel"
