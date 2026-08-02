"""Analytics and insights from the local finance database.

Uses ``connectorx`` for fast reads from SQLite into Polars DataFrames,
then runs aggregation, anomaly detection, and cash flow projection.

Usage::

    from src.insights import (
        category_breakdown,
        net_worth_timeline,
        detect_spending_anomalies,
        savings_rate,
        wallet_brief,
    )
"""

from __future__ import annotations

import connectorx as cx
import polars as pl

import structlog

logger = structlog.get_logger()


def _read_sql(db_path: str, query: str, params: list | None = None) -> pl.DataFrame:
    """Execute a SQL query and return results as a Polars DataFrame.

    Args:
        db_path: Path to the SQLite database.
        query: SQL query string.
        params: Optional query parameters.

    Returns:
        Polars DataFrame with results (empty DataFrame on error).
    """
    conn_str = f"sqlite://{db_path}"
    try:
        if params:
            return cx.read_sql(conn_str, query, params=params, return_type="polars")
        return cx.read_sql(conn_str, query, return_type="polars")
    except RuntimeError:
        return pl.DataFrame()


def category_breakdown(db_path: str, months: int = 3) -> pl.DataFrame:
    """Monthly spending breakdown by category.

    Args:
        db_path: Path to the SQLite database.
        months: Number of trailing months to include.

    Returns:
        Polars DataFrame with columns: category, month, total, count.
    """
    import sqlite3 as _sqlite3
    cutoff = _sqlite3.connect(db_path).execute(
        "SELECT date('now', ?)", [f"-{months} months"]
    ).fetchone()[0]

    query = f"""
        SELECT
            COALESCE(llm_category, category, 'Uncategorized') AS category,
            strftime('%Y-%m', date) AS month,
            SUM(amount) AS total,
            COUNT(*) AS count
        FROM transactions
        WHERE amount < 0
          AND date >= '{cutoff}'
        GROUP BY category, month
        ORDER BY month DESC, total ASC
    """
    return _read_sql(db_path, query)


def net_worth_timeline(db_path: str) -> pl.DataFrame:
    """Daily net worth from account balances.

    Uses the most recent snapshot per day. If multiple snapshots exist
    for a day, takes the latest.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Polars DataFrame with columns: date, total_assets, total_liabilities, net_worth.
    """
    query = """
        SELECT date, total_assets, total_liabilities, net_worth
        FROM net_worth_snapshots
        ORDER BY date DESC
    """
    return _read_sql(db_path, query)


def detect_spending_anomalies(db_path: str, z_threshold: float = 2.0) -> pl.DataFrame:
    """Detect daily spending anomalies using Z-score.

    Computes per-category Z-scores. Days where category spending exceeds
    the threshold are flagged.

    Args:
        db_path: Path to the SQLite database.
        z_threshold: Z-score threshold for flagging (default 2.0).

    Returns:
        Polars DataFrame with columns: date, category, amount, z_score, flagged.
    """
    query = """
        SELECT
            COALESCE(llm_category, category, 'Uncategorized') AS category,
            date,
            SUM(amount) AS amount
        FROM transactions
        WHERE amount < 0
        GROUP BY category, date
        ORDER BY date DESC
    """
    df = _read_sql(db_path, query)

    if df.is_empty():
        return df.with_columns(pl.lit(False, pl.Boolean).alias("flagged"))

    stats = df.group_by("category").agg([
        pl.col("amount").mean().alias("mean"),
        pl.col("amount").std(ddof=1).alias("std"),
    ])

    df = df.join(stats, on="category", how="left")
    df = df.with_columns(
        ((pl.col("amount") - pl.col("mean")) / pl.col("std").fill_null(0)).alias("z_score")
    )
    df = df.with_columns(
        (pl.col("z_score").abs() > z_threshold).alias("flagged")
    )
    return df.filter(pl.col("flagged")).sort("date", descending=True)


def savings_rate(db_path: str, months: int = 3) -> dict[str, float]:
    """Calculate monthly savings rate: (income - expenses) / income.

    Args:
        db_path: Path to the SQLite database.
        months: Number of trailing months.

    Returns:
        Dict with keys: 'monthly_income', 'monthly_expenses', 'savings_rate'.
    """
    import sqlite3 as _sqlite3
    cutoff = _sqlite3.connect(db_path).execute(
        "SELECT date('now', ?)", [f"-{months} months"]
    ).fetchone()[0]

    income_query = f"""
        SELECT AVG(monthly_total) AS avg_income
        FROM (
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS monthly_total
            FROM transactions
            WHERE amount > 0 AND date >= '{cutoff}'
            GROUP BY month
        )
    """
    expense_query = f"""
        SELECT AVG(monthly_total) AS avg_expenses
        FROM (
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS monthly_total
            FROM transactions
            WHERE amount < 0 AND date >= '{cutoff}'
            GROUP BY month
        )
    """
    income_df = _read_sql(db_path, income_query)
    expense_df = _read_sql(db_path, expense_query)

    avg_income = income_df[0, "avg_income"] if not income_df.is_empty() and income_df[0, "avg_income"] else 0.0
    avg_expenses = abs(expense_df[0, "avg_expenses"]) if not expense_df.is_empty() and expense_df[0, "avg_expenses"] else 0.0

    rate = ((avg_income - avg_expenses) / avg_income * 100) if avg_income > 0 else 0.0

    return {
        "monthly_income": round(avg_income, 2),
        "monthly_expenses": round(avg_expenses, 2),
        "savings_rate": round(rate, 1),
    }


def wallet_brief(db_path: str) -> dict:
    """Generate a concise financial overview (wallet brief).

    Combines multiple insights into a single dict suitable for display
    in a dashboard or embedding in an email digest.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Dict with keys: top_categories, subscriptions, anomalies, savings_rate.
    """
    import sqlite3 as _sqlite3
    cutoff = _sqlite3.connect(db_path).execute(
        "SELECT date('now', '-1 month')"
    ).fetchone()[0]

    top = category_breakdown(db_path, months=1)
    anomalies = detect_spending_anomalies(db_path)
    savings = savings_rate(db_path)

    sub_query = f"""
        SELECT subscription_label, COUNT(*) AS count, SUM(amount) AS monthly_cost
        FROM transactions
        WHERE is_subscription = 1 AND date >= '{cutoff}'
        GROUP BY subscription_label
        ORDER BY monthly_cost ASC
    """
    subs = _read_sql(db_path, sub_query)

    return {
        "savings_rate": savings,
        "top_categories": top.to_dicts()[:10] if not top.is_empty() else [],
        "subscriptions": subs.to_dicts() if not subs.is_empty() else [],
        "anomalies": anomalies.to_dicts() if not anomalies.is_empty() else [],
    }
