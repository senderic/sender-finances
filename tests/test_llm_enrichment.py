"""Tests for LLM enrichment module."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.llm.enrichment import _parse_categorization_response, recategorize_batch


def test_parse_categorization_json():
    """Should parse a valid JSON categorization response."""
    response = '{"txn-1": "Restaurants", "txn-2": "Groceries"}'
    result = _parse_categorization_response(response)
    assert result == {"txn-1": "Restaurants", "txn-2": "Groceries"}


def test_parse_categorization_markdown_fence():
    """Should handle JSON inside markdown code fences."""
    response = '```json\n{"txn-1": "Restaurants"}\n```'
    result = _parse_categorization_response(response)
    assert result == {"txn-1": "Restaurants"}


def test_parse_categorization_no_json():
    """Should return empty dict when no JSON is found."""
    result = _parse_categorization_response("Just some text, no JSON here.")
    assert result == {}


def test_parse_categorization_invalid_json():
    """Should return empty dict for malformed JSON."""
    result = _parse_categorization_response("{invalid: json}")
    assert result == {}


def test_recategorize_batch_unavailable_client():
    """Should return empty dict when client is not available."""
    client = MagicMock()
    client.available = False

    transactions = [{"id": "txn-1", "description": "Coffee", "amount": -4.50}]
    result = recategorize_batch(client, transactions, ["Restaurants", "Groceries"])
    assert result == {}


def test_recategorize_batch_empty():
    """Should return empty dict for no transactions."""
    client = MagicMock()
    client.available = True
    result = recategorize_batch(client, [], ["Restaurants"])
    assert result == {}


def test_recategorize_batch_success():
    """Should call invoke and parse results."""
    client = MagicMock()
    client.available = True
    client.invoke.return_value = '{"txn-1": "Restaurants", "txn-2": "Groceries"}'

    transactions = [
        {"id": "txn-1", "description": "Pizza place", "amount": -25.00},
        {"id": "txn-2", "description": "Whole Foods", "amount": -85.00},
    ]
    categories = ["Restaurants", "Groceries", "Shopping"]

    result = recategorize_batch(client, transactions, categories)
    assert result == {"txn-1": "Restaurants", "txn-2": "Groceries"}
    client.invoke.assert_called_once()


def test_recategorize_batch_llm_failure():
    """Should return empty dict if LLM fails."""
    client = MagicMock()
    client.available = True
    client.invoke.return_value = None

    transactions = [{"id": "txn-1", "description": "Pizza place", "amount": -25.00}]
    result = recategorize_batch(client, transactions, ["Restaurants"])
    assert result == {}
