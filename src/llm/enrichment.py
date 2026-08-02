"""LLM-powered transaction enrichment.

Sends batches of uncategorized transactions to the LLM and parses
structured JSON responses to assign categories.

Usage::

    from src.llm.client import OpencodeLLMClient
    from src.llm.enrichment import recategorize_batch

    client = OpencodeLLMClient(settings.llm)
    results = recategorize_batch(client, uncategorized_transactions, categories)
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from src.llm.client import OpencodeLLMClient

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a personal finance assistant. Your task is to categorize financial transactions.

Rules:
1. Assign each transaction ONE category from the provided category list.
2. If no category fits, use "Uncategorized".
3. Be specific: prefer "Restaurants" over "Food & Dining" when the description mentions a restaurant.
4. For Amazon/Walmart/Target transactions, use "Shopping" unless the description indicates groceries.
5. Return ONLY a JSON object with transaction IDs mapped to category names. No explanation.

Example output:
{"txn_123": "Restaurants", "txn_456": "Gas & Fuel", "txn_789": "Uncategorized"}
"""


def recategorize_batch(
    client: OpencodeLLMClient,
    transactions: list[dict[str, Any]],
    category_names: list[str],
    batch_size: int = 50,
) -> dict[str, str]:
    """Recategorize uncategorized transactions using the LLM.

    Sends transactions in batches to avoid prompt length limits.

    Args:
        client: An initialized OpencodeLLMClient.
        transactions: List of dicts with ``id``, ``description``, ``amount``,
                      and optionally ``merchant_name``.
        category_names: Available Simplifi category names.
        batch_size: Max transactions per LLM call.

    Returns:
        Dict mapping transaction_id -> suggested category name.
    """
    if not client.available:
        logger.warning("recategorize_skipped_llm_unavailable")
        return {}

    if not transactions:
        return {}

    categories_str = "\n".join(f"- {c}" for c in sorted(category_names))
    results: dict[str, str] = {}

    for i in range(0, len(transactions), batch_size):
        batch = transactions[i : i + batch_size]
        txn_list = []
        for t in batch:
            desc = t.get("description", "")
            amt = t.get("amount", 0)
            merchant = t.get("merchant_name", "")
            display = f"${amt:.2f} - {desc}"
            if merchant:
                display += f" ({merchant})"
            txn_list.append(f"  {t['id']}: {display}")

        prompt = f"""Available categories:
{categories_str}

Transactions to categorize:
{chr(10).join(txn_list)}

Return a JSON object mapping each transaction ID to its best-fit category."""

        response = client.invoke(prompt, SYSTEM_PROMPT)
        if not response:
            logger.warning("recategorize_batch_failed", batch_start=i)
            continue

        batch_results = _parse_categorization_response(response)
        results.update(batch_results)
        logger.info("recategorize_batch_complete", processed=len(batch_results))

    return results


def _parse_categorization_response(response: str) -> dict[str, str]:
    """Extract a JSON mapping of transaction_id -> category from LLM output.

    Handles bare JSON and markdown code fences.

    Args:
        response: Raw LLM response text.

    Returns:
        Dict of transaction_id -> category_name.
    """
    match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
    if not match:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            logger.warning("recategorize_parse_no_json")
            return {}
    else:
        json_str = match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("recategorize_parse_invalid_json")
        return {}
