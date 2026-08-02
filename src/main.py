"""CLI entry point for sender-finances.

Usage::

    uv run python -m src.main login      # Interactive MFA login
    uv run python -m src.main ingest     # Pull data from Simplifi
    uv run python -m src.main enrich     # Run enrichment (subs + merchants + LLM recategorization)
    uv run python -m src.main report     # Print wallet brief to stdout
    uv run python -m src.main dashboard  # Launch Streamlit dashboard
"""

from __future__ import annotations

import argparse
import logging
import sys
from getpass import getpass

from simplifiapi.client import Client
import structlog

from src.config import Settings
from src.token_store import load_token, save_token


def setup_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def cmd_login(settings: Settings) -> None:
    """Interactive login to Quicken Simplifi, saving token to disk."""
    print("Logging into Quicken Simplifi...")
    email = input("Email: ").strip()
    password = getpass("Password: ").strip()

    client = Client()
    token = client.get_token(email, password)
    if not token:
        print("Login failed.")
        sys.exit(1)

    if not client.verify_token(token):
        print("Token verification failed.")
        sys.exit(1)

    save_token(token, str(settings.simplifi.resolved_token_path))
    print("Token saved successfully.")


def cmd_ingest(settings: Settings) -> None:
    """Pull data from Simplifi and upsert into SQLite."""
    from src.ingest import ingest

    result = ingest(settings)
    print(f"Status: {result.get('status')}")
    if result.get("status") == "ok":
        print(f"Accounts: {result.get('accounts')}")
        print(f"Transactions: {result.get('transactions')}")
        print(f"Categories: {result.get('categories')}")
        print(f"Tags: {result.get('tags')}")


def cmd_enrich(settings: Settings) -> None:
    """Run all enrichment steps."""
    from src.database import create_tables, get_engine, update_enrichment
    from src.enrichment import detect_subscriptions, normalize_merchants
    from src.llm.client import OpencodeLLMClient
    from src.llm.enrichment import recategorize_batch
    from sqlalchemy import text

    engine = get_engine(settings.database.resolved_path)
    create_tables(engine)

    if settings.enrichment.merchant_normalization:
        print("Normalizing merchants...")
        n = normalize_merchants(engine)
        print(f"  Updated {n} transactions.")

    if settings.enrichment.subscription_detection:
        print("Detecting subscriptions...")
        n = detect_subscriptions(engine)
        print(f"  Flagged {n} transactions.")

    if settings.enrichment.recategorization and settings.llm.enabled:
        client = OpencodeLLMClient(settings.llm)
        if client.available:
            with engine.begin() as conn:
                uncat = conn.execute(
                    text(
                        """SELECT id, description, amount, merchant_name
                           FROM transactions
                           WHERE (category IS NULL OR category = 'Uncategorized')
                             AND llm_category IS NULL
                           LIMIT 200"""
                    )
                ).fetchall()

            if uncat:
                with engine.begin() as conn:
                    cats = conn.execute(text("SELECT name FROM categories WHERE is_income = 0")).fetchall()
                category_names = [c.name for c in cats]

                print(f"Recategorizing {len(uncat)} uncategorized transactions...")
                results = recategorize_batch(
                    client,
                    [{"id": r.id, "description": r.description, "amount": r.amount, "merchant_name": r.merchant_name} for r in uncat],
                    category_names,
                )
                for txn_id, category in results.items():
                    update_enrichment(engine, txn_id, {"llm_category": category})
                print(f"  Categorized {len(results)} transactions.")
                print(f"  LLM usage: {client.get_usage_summary()}")
            else:
                print("No uncategorized transactions to process.")
        else:
            print("LLM (opencode) not available — skipping recategorization.")


def cmd_report(settings: Settings) -> None:
    """Print a wallet brief to stdout."""
    import json

    from src.insights import wallet_brief

    db_path = str(settings.database.resolved_path)
    brief = wallet_brief(db_path)
    print(json.dumps(brief, indent=2, default=str))


def cmd_dashboard(settings: Settings) -> None:
    """Launch the Streamlit dashboard."""
    import subprocess
    import os

    print("Launching Streamlit dashboard...")
    os.execvp("streamlit", ["streamlit", "run", "src/dashboard.py", "--server.port", "8501", "--server.headless", "true"])


def main() -> None:
    parser = argparse.ArgumentParser(description="sender-finances — personal finance dashboard")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Interactive MFA login to Quicken Simplifi")
    sub.add_parser("ingest", help="Pull data from Simplifi into local SQLite")
    sub.add_parser("enrich", help="Run enrichment (subscriptions, merchants, LLM categories)")
    sub.add_parser("report", help="Print wallet brief as JSON")
    sub.add_parser("dashboard", help="Launch Streamlit dashboard")

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    args = parser.parse_args()

    settings = Settings.from_yaml(args.config).resolve_env_vars()
    setup_logging(settings.logging.level)

    commands = {
        "login": cmd_login,
        "ingest": cmd_ingest,
        "enrich": cmd_enrich,
        "report": cmd_report,
        "dashboard": cmd_dashboard,
    }

    commands[args.command](settings)


if __name__ == "__main__":
    main()
