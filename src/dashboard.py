"""Streamlit dashboard for personal finance insights."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import streamlit as st

from src.config import Settings
from src.insights import (
    category_breakdown,
    detect_spending_anomalies,
    savings_rate,
    wallet_brief,
)

st.set_page_config(
    page_title="Sender Finances",
    page_icon="💰",
    layout="wide",
)


@st.cache_data(ttl=3600)
def load_data(db_path: str):
    """Load and cache insight data."""
    brief = wallet_brief(db_path)
    breakdown = category_breakdown(db_path, months=1)
    anomalies = detect_spending_anomalies(db_path)
    srate = savings_rate(db_path)
    return brief, breakdown, anomalies, srate


def main() -> None:
    settings = Settings.from_yaml("config.yaml").resolve_env_vars()
    db_path = str(settings.database.resolved_path)

    if not Path(db_path).exists():
        st.error(
            f"Database not found at `{db_path}`. Run `uv run python -m src.main ingest` first."
        )
        return

    st.title("💰 Sender Finances")
    st.caption("Personal finance insights powered by Quicken Simplifi")

    brief, breakdown, anomalies, srate = load_data(db_path)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Monthly Income", f"${srate['monthly_income']:,.2f}")
    with col2:
        st.metric("Monthly Expenses", f"${srate['monthly_expenses']:,.2f}")
    with col3:
        st.metric("Savings Rate", f"{srate['savings_rate']:.1f}%")

    st.divider()
    st.subheader("Top Spending Categories")
    if not breakdown.is_empty():
        cat_df = (
            breakdown.group_by("category")
            .agg(pl.col("total").sum().abs(), pl.col("count").sum())
            .sort("total", descending=True)
            .head(10)
        )
        st.bar_chart(
            cat_df.to_pandas().set_index("category")["total"],
            horizontal=True,
        )
    else:
        st.info("No spending data yet.")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Subscriptions")
        if brief.get("subscriptions"):
            subs = pl.DataFrame(brief["subscriptions"])
            subs = subs.with_columns(pl.col("monthly_cost").abs())
            st.dataframe(
                subs.to_pandas(),
                use_container_width=True,
                hide_index=True,
            )
            total_sub = subs["monthly_cost"].sum()
            st.metric("Monthly Subscription Spend", f"${total_sub:,.2f}")
        else:
            st.info("No subscriptions detected.")

    with col_right:
        st.subheader("Spending Anomalies")
        if not anomalies.is_empty():
            display = anomalies.select(["date", "category", "amount", "z_score"])
            display = (
                display.with_columns(
                    pl.col("amount").abs().alias("amount"),
                    pl.col("z_score").round(2),
                )
                .sort("date", descending=True)
                .head(10)
            )
            st.dataframe(
                display.to_pandas(),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No anomalies detected.")


if __name__ == "__main__":
    main()
