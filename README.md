# tokenwatch

A self-hosted LLM cost dashboard. tokenwatch is a **transparent proxy** that sits
between your app and the Anthropic / OpenAI APIs: it forwards every request
untouched, reads the `usage` block from the response, prices it against an
editable rate card, and shows you the running spend on a live dashboard.

No SDK changes beyond one line — just point your client's `base_url` at tokenwatch.

![dashboard](docs/dashboard.png)

## Features

- **Drop-in proxy** for `/v1/messages` (Anthropic) and `/v1/chat/completions` (OpenAI)
- **Live pricing** from `backend/app/pricing.yaml` (USD per 1M tokens, reloaded per request)
- **SQLite storage** — zero external services
- **Dashboard** at `/`: total spend, per-model table, per-day chart, recent requests (auto-refresh 10s)
- **JSON API** at `/api/usage`
- **One-command Docker** deploy

## Quick start

### With uv

```bash
uv run tokenwatch          # serves on http://localhost:8000
```

### With Docker

```bash
docker compose up          # serves on http://localhost:8000
```

Open http://localhost:8000 for the dashboard.

## Point your SDK at tokenwatch

Set the client `base_url` to your tokenwatch host. Auth headers are passed
through to the real upstream unchanged.

**Anthropic (Python)**

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://localhost:8000", api_key="sk-ant-...")
client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=256,
    messages=[{"role": "user", "content": "hello"}],
)
```

**OpenAI (Python)**

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="sk-...")
client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
```

Every call now shows up on the dashboard with its computed cost.

## Configuration

All via environment variables:

| Variable                       | Default                     | Purpose                                  |
| ------------------------------ | --------------------------- | ---------------------------------------- |
| `TOKENWATCH_UPSTREAM_ANTHROPIC`| `https://api.anthropic.com` | Anthropic upstream base URL              |
| `TOKENWATCH_UPSTREAM_OPENAI`   | `https://api.openai.com`    | OpenAI upstream base URL                 |
| `TOKENWATCH_DB`                | `tokenwatch.db`             | SQLite database path                     |
| `TOKENWATCH_HOST`              | `0.0.0.0`                   | Bind host                                |
| `TOKENWATCH_PORT`              | `8000`                      | Bind port                                |

### Pricing

Edit `backend/app/pricing.yaml` — prices are USD per 1,000,000 tokens and the
file is re-read on every request, so changes take effect immediately. Unknown
models fall back to the `_default` entry and are flagged in the data.

## Development

```bash
uv run --extra dev pytest -q
```

## Screenshots

Place a dashboard screenshot at `docs/dashboard.png` (referenced above).

## License

MIT © 2026 Dhanush Shankar
