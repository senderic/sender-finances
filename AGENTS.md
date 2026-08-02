# sender-finances — Agent Context

## What This Is

A personal finance dashboard that pulls data from Quicken Simplifi into a local SQLite database, runs deterministic enrichment (subscription detection, merchant normalization), optionally recategorizes transactions via LLM (opencode CLI), and provides a Streamlit dashboard at `finances.ericsender.com`.

## Schedule

Cron: `0 7 * * *` — 7:00 AM daily.
Runs `~/sender-finances/run_ingest.sh`, which sources `.env` and runs `uv run python -m src.main ingest`.

## Key Commands

```bash
# Interactive login (needs MFA on first run)
uv run python -m src.main login

# Pull data
uv run python -m src.main ingest

# Run enrichment
uv run python -m src.main enrich

# Print wallet brief
uv run python -m src.main report

# Launch dashboard
uv run python -m src.main dashboard

# All tests
uv run pytest tests/ -v --tb=short

# Lint + format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Dependencies

**Binary:**
- `uv` at `~/.local/bin/uv` — runs the pipeline
- `opencode` at `/home/linuxbrew/.linuxbrew/bin/opencode` — LLM recategorization

**Runtime Python deps:** pydantic, pydantic-settings, pyyaml, sqlalchemy, structlog, connectorx, polars, streamlit, simplifiapi (git dep)

**Dev deps:** pytest, pytest-cov, ruff

## Pipeline

1. **Load token** — `~/.simplifiapi_token` decoded, exp checked. Skip if expired.
2. **Authenticate** — `Client.verify_token()` against Simplifi
3. **Fetch** — accounts, transactions, categories, tags via `simplifiapi`
4. **Normalize** — Simplifi camelCase → snake_case, JSON serialization
5. **Upsert** — SQLite ON CONFLICT DO UPDATE (idempotent)
6. **Snapshot** — metadata row with counts, timestamps

## Enrichment Pipeline

1. **Merchant normalization** — regex patterns clean up transaction descriptions
2. **Subscription detection** — group by (description, amount), flag recurring >=3 at monthly intervals
3. **LLM recategorization** — uncategorized transactions batched to opencode with category list

## Database Schema

| Table | Key Fields |
|-------|-----------|
| `accounts` | id, name, type, subtype, balance, currency, financial_institution, is_closed |
| `transactions` | id (PK), account_id, date, description, amount, category, category_id, tag, is_pending, merchant_name, cleaned_merchant, is_subscription, subscription_label, llm_category |
| `categories` | id (PK), name, parent_id, is_income |
| `tags` | id (PK), name |
| `snapshots` | id (auto), fetched_at, dataset_id, account_count, transaction_count |
| `net_worth_snapshots` | id (auto), date (unique), total_assets, total_liabilities, net_worth |

## Data Layer Architecture

| Path | Tool | Why |
|------|------|-----|
| Schema/DDL | SQLAlchemy Core `Table` + `MetaData.create_all()` | Declarative, testable |
| Writes (upserts) | SQLAlchemy Core `insert()` with SQLite `ON CONFLICT` | No ORM overhead |
| Reads (analytics) | `connectorx.read_sql()` → Polars | 3-13x faster, zero-copy Arrow |

## Token Management

- Token stored at `~/.simplifiapi_token` (raw JWT)
- `token_store.py` decodes JWT payload, checks `exp` claim
- Expired token → ingest skipped silently (no MFA hang in cron)
- New token fetched interactively via `uv run python -m src.main login`

## LLM Pattern

Mirrors sender-trades: `OpencodeLLMClient` shells out to `opencode run --format json --auto --dir /tmp --pure`, parses NDJSON text events. Free Zen models tried first, paid Go models as fallback.

## Dashboard Deployment

```
Streamlit (:8501)
  → Caddy (host.docker.internal:8501)
    → finances.ericsender.com (Cloudflare TLS + basic_auth)
      → Cloudflare DNS → ericsender.tplinkdns.com
```

Caddy block in `~/media-stack/Caddyfile`:
```caddyfile
finances.ericsender.com {
    import cloudflare_tls
    import basic_auth
    reverse_proxy host.docker.internal:8501
}
```

## Known Issues

- Token expires ~1h after issuance. Cron runs need a valid token. Run `login` periodically to refresh.
- Streamlit must be running for dashboard access. Use systemd service for persistence.
- LLM recategorization requires `opencode` binary on PATH. Gracefully skips if unavailable.
