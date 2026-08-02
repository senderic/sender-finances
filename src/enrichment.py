"""Deterministic enrichment: subscription detection and merchant normalization.

These run without LLM and are fast/cheap. The LLM-based recategorization
is a separate step in ``src/llm/enrichment.py``.

Usage::

    from src.enrichment import detect_subscriptions, normalize_merchants
    from src.database import get_engine, update_enrichment

    engine = get_engine("data/finances.db")
    detect_subscriptions(engine)
    normalize_merchants(engine)
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import text

import structlog

logger = structlog.get_logger()

MERCHANT_PATTERNS: list[tuple[str, str]] = [
    (r"amazon\s*(?:prime|video|music|web|marketplace|\.com|payments?|digital|kindle)", "Amazon"),
    (r"^amzn", "Amazon"),
    (r"netflix", "Netflix"),
    (r"spotify", "Spotify"),
    (r"hulu", "Hulu"),
    (r"disney\+|disney plus", "Disney+"),
    (r"youtube\s*(?:premium|tv|music)", "YouTube"),
    (r"apple\.com/bill|apple\s*(?:music|tv|arcade|news\+|fitness\+|icloud)", "Apple"),
    (r"google\s*(?:one|play|youtube|fi|storage)", "Google"),
    (r"microsoft\s*(?:365|office|onedrive|xbox|xbox live|game pass)", "Microsoft"),
    (r"adobe\s*(?:creative cloud|photoshop|acrobat)", "Adobe"),
    (r"dropbox", "Dropbox"),
    (r"github", "GitHub"),
    (r"patreon", "Patreon"),
    (r"substack", "Substack"),
    (r"wireless|verizon|at&t|t-mobile|sprint", "Phone Bill"),
    (r"comcast|xfinity|spectrum|cox|optimum", "Internet/Cable"),
    (r"geico|progressive|state farm|allstate|usaa|liberty mutual|farmers", "Insurance"),
    (r"planet fitness|equinox|24 hour|crunch|ymca|orangetheory|barry's", "Gym"),
    (r"uber\s*(?:one|pass|eats pass)", "Uber"),
    (r"doordash\s*(?:dashpass)?", "DoorDash"),
    (r"chatgpt|openai", "OpenAI"),
]


def normalize_merchants(engine) -> int:
    """Apply regex-based merchant name normalization.

    Strips common suffixes (order numbers, dates, store IDs) and maps
    to canonical merchant names.

    Args:
        engine: SQLAlchemy Engine.

    Returns:
        Number of transactions updated.
    """
    count = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, description, merchant_name FROM transactions WHERE cleaned_merchant IS NULL")
        ).fetchall()

    for row in rows:
        raw = (row.merchant_name or row.description or "").strip()
        cleaned = _clean_merchant(raw)

        if cleaned and cleaned != raw:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE transactions SET cleaned_merchant = :merchant WHERE id = :tid"),
                    {"merchant": cleaned, "tid": row.id},
                )
            count += 1

    logger.info("merchants_normalized", count=count)
    return count


def _clean_merchant(raw: str) -> str | None:
    """Normalize a merchant name string.

    Args:
        raw: Raw merchant name or description.

    Returns:
        Canonical merchant name or None if no pattern matched.
    """
    for pattern, canonical in MERCHANT_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            return canonical

    return None


def detect_subscriptions(engine) -> int:
    """Detect recurring subscription transactions.

    Groups transactions by exact description and amount. Flags any
    group with >= 3 occurrences and consistent monthly intervals as
    a probable subscription.

    Args:
        engine: SQLAlchemy Engine.

    Returns:
        Number of transactions flagged as subscriptions.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """SELECT id, description, amount, date
                   FROM transactions
                   WHERE amount < 0 AND is_subscription = 0
                   ORDER BY description, date"""
            )
        ).fetchall()

    groups: dict[tuple[str, float], list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        desc = (row.description or "").strip()
        amt = round(row.amount, 2) if row.amount else 0
        groups[(desc, amt)].append((row.id, row.date or ""))

    count = 0
    for (desc, amt), occurrences in groups.items():
        if len(occurrences) < 3:
            continue

        dates = []
        for _, d in occurrences:
            try:
                dates.append(datetime.fromisoformat(d))
            except (ValueError, TypeError):
                dates.append(None)

        label = _guess_subscription_label(desc)
        valid_dates = [d for d in dates if d is not None]
        is_sub = len(occurrences) >= 3 and (
            len(valid_dates) < 2 or _has_monthly_pattern(valid_dates)
        )

        if is_sub:
            for txn_id, _ in occurrences:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """UPDATE transactions
                               SET is_subscription = 1, subscription_label = :label
                               WHERE id = :tid"""
                        ),
                        {"label": label, "tid": txn_id},
                    )
            count += len(occurrences)

    logger.info("subscriptions_detected", flagged_count=count, groups_analyzed=len(groups))
    return count


def _guess_subscription_label(description: str) -> str:
    """Guess a human-readable subscription label from the description.

    Args:
        description: Transaction description.

    Returns:
        A short label like 'Netflix', 'AWS', 'Unknown Subscription'.
    """
    for pattern, canonical in MERCHANT_PATTERNS:
        if re.search(pattern, description, re.IGNORECASE):
            return canonical
    return "Unknown Subscription"


def _has_monthly_pattern(dates: list[datetime]) -> bool:
    """Check if dates occur roughly monthly (28-33 days apart).

    Args:
        dates: Sorted list of datetimes.

    Returns:
        True if the sequence looks monthly.
    """
    if len(dates) < 2:
        return False
    sorted_dates = sorted(dates)
    intervals = []
    for i in range(1, len(sorted_dates)):
        delta = (sorted_dates[i] - sorted_dates[i - 1]).days
        if delta > 0:
            intervals.append(delta)
    if not intervals:
        return False
    avg = sum(intervals) / len(intervals)
    return 25 <= avg <= 35
