"""Tests for enrichment module."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from src.database import create_tables, upsert_transactions
from src.enrichment import (
    _clean_merchant,
    _guess_subscription_label,
    _has_monthly_pattern,
    detect_subscriptions,
    normalize_merchants,
)


def test_clean_merchant_amazon():
    """Should normalize Amazon variants."""
    assert _clean_merchant("AMAZON.COM*AB12CD3") == "Amazon"
    assert _clean_merchant("AMZN Mktp US") == "Amazon"
    assert _clean_merchant("Amazon Prime") == "Amazon"


def test_clean_merchant_netflix():
    assert _clean_merchant("NETFLIX.COM") == "Netflix"
    assert _clean_merchant("Netflix") == "Netflix"


def test_clean_merchant_spotify():
    assert _clean_merchant("Spotify USA") == "Spotify"


def test_clean_merchant_phone_bill():
    assert _clean_merchant("VERIZON WIRELESS") == "Phone Bill"
    assert _clean_merchant("T-MOBILE") == "Phone Bill"


def test_clean_merchant_unknown():
    """Unknown merchants should return None."""
    assert _clean_merchant("XYZ RANDOM STORE") is None


def test_guess_subscription_label():
    assert _guess_subscription_label("NETFLIX.COM") == "Netflix"
    assert _guess_subscription_label("Spotify USA") == "Spotify"
    assert _guess_subscription_label("RANDOM THING") == "Unknown Subscription"


def test_has_monthly_pattern():
    from datetime import datetime

    monthly = [
        datetime(2026, 1, 1),
        datetime(2026, 2, 1),
        datetime(2026, 3, 1),
        datetime(2026, 4, 1),
    ]
    assert _has_monthly_pattern(monthly) is True


def test_has_monthly_pattern_not_monthly():
    from datetime import datetime

    random = [
        datetime(2026, 1, 1),
        datetime(2026, 1, 5),
        datetime(2026, 3, 20),
    ]
    assert _has_monthly_pattern(random) is False


def test_has_monthly_pattern_single():
    from datetime import datetime

    assert _has_monthly_pattern([datetime(2026, 1, 1)]) is False
    assert _has_monthly_pattern([]) is False


def test_normalize_merchants_updates_db():
    """normalize_merchants should update cleaned_merchant on matching transactions."""
    import tempfile
    from pathlib import Path

    db_path = Path(tempfile.mktemp(suffix=".db"))
    engine = create_engine(f"sqlite:///{db_path}")
    create_tables(engine)

    rows = [
        {
            "id": "txn-1",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "amount": -15.99,
            "description": "NETFLIX.COM",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
        },
        {
            "id": "txn-2",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "amount": -99.00,
            "description": "RANDOM XYZ",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
        },
    ]
    upsert_transactions(engine, rows)

    count = normalize_merchants(engine)
    assert count >= 1

    with engine.connect() as conn:
        netflix = conn.execute(
            text("SELECT cleaned_merchant FROM transactions WHERE id = 'txn-1'")
        ).fetchone()
        random_txn = conn.execute(
            text("SELECT cleaned_merchant FROM transactions WHERE id = 'txn-2'")
        ).fetchone()

    assert netflix[0] == "Netflix"
    assert random_txn[0] is None

    engine.dispose()
    db_path.unlink(missing_ok=True)


def test_detect_subscriptions_flags_recurring():
    """detect_subscriptions should flag transactions with >=3 monthly occurrences."""
    import tempfile
    from pathlib import Path

    db_path = Path(tempfile.mktemp(suffix=".db"))
    engine = create_engine(f"sqlite:///{db_path}")
    create_tables(engine)

    rows = [
        {
            "id": "txn-1",
            "account_id": "acc-1",
            "date": "2026-06-01",
            "amount": -14.99,
            "description": "NETFLIX.COM",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
        },
        {
            "id": "txn-2",
            "account_id": "acc-1",
            "date": "2026-07-01",
            "amount": -14.99,
            "description": "NETFLIX.COM",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
        },
        {
            "id": "txn-3",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "amount": -14.99,
            "description": "NETFLIX.COM",
            "cleaned_merchant": None,
            "is_subscription": 0,
            "subscription_label": None,
            "llm_category": None,
        },
    ]
    upsert_transactions(engine, rows)

    count = detect_subscriptions(engine)
    assert count >= 3

    with engine.connect() as conn:
        subs = conn.execute(
            text("SELECT COUNT(*) FROM transactions WHERE is_subscription = 1")
        ).scalar()
    assert subs == 3

    engine.dispose()
    db_path.unlink(missing_ok=True)
