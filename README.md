# FinAlly — AI Trading Workstation

An AI-powered trading terminal: live streaming prices, a simulated $10k portfolio, and an LLM chat assistant that analyzes positions and executes trades. Built by coding agents as the capstone of an agentic AI coding course.

## Status

The market data subsystem (simulator, Massive client, price cache, SSE stream) is complete. The rest of the platform is in progress. See `planning/PLAN.md` for the full spec.

## Stack

- **Frontend**: Next.js (TypeScript, static export), Tailwind, Lightweight Charts
- **Backend**: FastAPI on `uv`, SSE streaming, SQLite
- **AI**: LiteLLM → OpenRouter (free models) with structured outputs
- **Market data**: GBM simulator by default, Massive (Polygon.io) API if a key is set

Everything runs in one Docker container on port 8000.

## Setup

```bash
cp .env.example .env   # add OPENROUTER_API_KEY
```

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Unless `LLM_MOCK=true` | OpenRouter key for AI chat |
| `MASSIVE_API_KEY` | No | Real market data; omit to use the simulator |
| `LLM_MODEL` | No | Free OpenRouter model ID (default in `.env.example`) |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses |

## Backend Development

```bash
cd backend
uv sync --dev
uv run pytest
uv run market_data_demo.py   # terminal demo of the price simulator
```

## Layout

```
backend/    FastAPI app and tests
frontend/   Next.js app (planned)
planning/   Spec and agent docs
test/       Playwright E2E tests (planned)
scripts/    Docker start/stop scripts (planned)
```

## License

See [LICENSE](LICENSE).
