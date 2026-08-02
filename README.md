# sender-finances

Personal finance dashboard powered by Quicken Simplifi. Pulls your accounts, transactions, categories, and tags from Simplifi into a local SQLite database, then runs enrichment (subscription detection, merchant normalization, LLM recategorization) and provides analytics via a Streamlit dashboard.

> **Privacy-first**: All data stays on your NUC. The only external API call is to Simplifi itself for data retrieval.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A Quicken Simplifi account
- `opencode` CLI (optional, for LLM-powered transaction categorization)
- Cloudflare DNS for the public dashboard (optional)

## Quick Start

```bash
# Clone and install
cd ~/sender-finances
uv sync

# Set up credentials
cp .env.example .env
# Edit .env with your Simplifi email/password

# Interactive login (handles MFA)
uv run python -m src.main login

# Pull data from Simplifi
uv run python -m src.main ingest

# Run enrichment (subscription detection, merchant normalization, LLM categories)
uv run python -m src.main enrich

# View a wallet brief
uv run python -m src.main report

# Launch the dashboard
uv run python -m src.main dashboard
```

## Architecture

```
Simplifi API (services.quicken.com)
       │
       │  simplifiapi Client (OAuth + MFA)
       ▼
  ~/sender-finances/
       │
  src/ingest.py  ──► SQLite (data/sender-finances.db)
       │                   │
       │                   ├── accounts
       │                   ├── transactions
       │                   ├── categories
       │                   ├── tags
       │                   └── snapshots
       │
  src/enrichment.py ◄──►  SQLite
       │                   │
       │  ┌────────────────┤
       │  │ Subscription   │
       │  │ Detection      │
       │  │ Merchant Norm  │
       │  └────────────────┤
       │                   │
  src/llm/enrichment.py ──┤  LLM Recategorization (opencode CLI)
                           │
  src/insights.py ◄──► connectorx + Polars
       │
       │  ┌────────────────┐
       │  │ Category       │
       │  │ Breakdown      │
       │  │ Anomalies      │
       │  │ Savings Rate   │
       │  │ Wallet Brief   │
       │  └────────────────┘
       │
  src/dashboard.py ──► Streamlit (port 8501)
       │
       │  Caddy reverse proxy
       ▼
  finances.ericsender.com
```

## Commands

| Command | Description |
|---------|-------------|
| `uv run python -m src.main login` | Interactive MFA login, saves token to `~/.simplifiapi_token` |
| `uv run python -m src.main ingest` | Pull all data from Simplifi into SQLite |
| `uv run python -m src.main enrich` | Run enrichment: subscriptions, merchants, LLM categories |
| `uv run python -m src.main report` | Print wallet brief as JSON |
| `uv run python -m src.main dashboard` | Launch Streamlit dashboard on port 8501 |

## Data Layer

| Path | Tool | Purpose |
|------|------|---------|
| Schema/DDL | SQLAlchemy Core `Table` + `MetaData` | Declarative schema, auto-migrations |
| Writes (upserts) | SQLAlchemy Core `insert()` with `ON CONFLICT` | Idempotent inserts, no ORM overhead |
| Reads (analytics) | `connectorx` → Polars `DataFrame` | 3-13x faster than pandas.read_sql, zero-copy Arrow |

## Enrichment Features

| Feature | Method | Requires |
|---------|--------|----------|
| Subscription detection | Groups identical amounts/descriptions, checks monthly pattern (>=3 occurrences) | None |
| Merchant normalization | Regex patterns (e.g., "AMAZON.COM*AB12CD3" → "Amazon") | None |
| LLM recategorization | Sends batches of uncategorized transactions to opencode with category list | `opencode` CLI |

## LLM Configuration

Uses the same opencode CLI pattern as sender-trades:

1. Free Zen models tried first (DeepSeek V4 Flash Free, MiMo V2.5 Free, etc.)
2. Paid Go models as fallback (GLM 5.2, Kimi K3, Qwen 3.7 Max)
3. Configurable via `config.yaml` → `llm` section
4. Budget capped at `max_calls_per_run: 10`

## Dashboard (Streamlit)

Accessible at `https://finances.ericsender.com` (proxied through Caddy with basic_auth).

Displays:
- Monthly income, expenses, savings rate
- Top spending categories (bar chart)
- Subscription breakdown with monthly costs
- Spending anomaly flags

### Caddy Configuration

Added to `~/media-stack/Caddyfile`:

```caddyfile
finances.ericsender.com {
    import cloudflare_tls
    import basic_auth
    reverse_proxy host.docker.internal:8501
}
```

### systemd Service (optional)

```bash
# ~/.config/systemd/user/sender-finances-dashboard.service
systemctl --user enable --now sender-finances-dashboard.service
```

## Cloudflare DNS

```
Type: CNAME
Name: finances
Target: ericsender.tplinkdns.com
Proxy: orange cloud ON
```

## Cron Schedule

```cron
# Pull Simplifi data daily at 7:00 AM PT
0 7 * * * ~/sender-finances/run_ingest.sh >> ~/sender-finances/logs/cron.log 2>&1
```

## Configuration

All settings in `config.yaml` with `${VAR}` and `${VAR:-default}` environment interpolation:

```yaml
simplifi:
  token_path: ${SIMPLIFI_TOKEN_PATH:-~/.simplifiapi_token}

database:
  sqlite_path: ${SQLITE_PATH:-data/sender-finances.db}

enrichment:
  subscription_detection: true
  merchant_normalization: true
  recategorization: true

llm:
  enabled: true
  zen_models: [...]
  paid_go_models: [...]
  timeout_sec: 60
  max_calls_per_run: 10

logging:
  level: ${LOG_LEVEL:-INFO}
```

## Development

```bash
# Run tests
uv run pytest tests/ -v --tb=short

# Run tests with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Future Phases

- **Phase 2 (Integrations)**: Atlas morning briefing personal finance section, sender-trades P&L correlation
- **Phase 3 (Delivery)**: Weekly email digest via Gmail SMTP, monthly Kindle "State of Finances" report
- **Phase 4 (Advanced)**: Cash flow forecasting, tax estimation, investment tracking from Simplifi brokerage accounts

## License

MIT
