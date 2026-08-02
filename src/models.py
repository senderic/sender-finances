"""SQLAlchemy table definitions for the finance database.

Uses SQLAlchemy Core (not ORM) for schema declaration. Tables are
defined with MetaData and created via create_all(). All writes use
Core insert() with ON CONFLICT for upsert semantics.
"""

from __future__ import annotations

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, UniqueConstraint

metadata = MetaData()

accounts = Table(
    "accounts",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("type", String),
    Column("subtype", String),
    Column("balance", Float),
    Column("currency", String),
    Column("financial_institution", String),
    Column("is_closed", Integer, default=0),
    Column("raw_json", Text),
)

transactions = Table(
    "transactions",
    metadata,
    Column("id", String, primary_key=True),
    Column("account_id", String, nullable=False),
    Column("date", String, nullable=False),
    Column("description", String),
    Column("amount", Float),
    Column("category", String),
    Column("category_id", String),
    Column("tag", String),
    Column("is_pending", Integer, default=0),
    Column("merchant_name", String),
    Column("cleaned_merchant", String),
    Column("is_subscription", Integer, default=0),
    Column("subscription_label", String),
    Column("llm_category", String),
    Column("raw_json", Text),
)

categories = Table(
    "categories",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("parent_id", String),
    Column("is_income", Integer, default=0),
)

tags = Table(
    "tags",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
)

snapshots = Table(
    "snapshots",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("fetched_at", String, nullable=False),
    Column("dataset_id", String),
    Column("account_count", Integer),
    Column("transaction_count", Integer),
    Column("raw_json", Text),
)

net_worth_snapshots = Table(
    "net_worth_snapshots",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("date", String, nullable=False),
    Column("total_assets", Float),
    Column("total_liabilities", Float),
    Column("net_worth", Float),
    UniqueConstraint("date"),
)
