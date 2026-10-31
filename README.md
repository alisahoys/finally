# FinAlly — AI Trading Workstation

An AI-powered trading terminal: live streaming prices, a simulated $10k portfolio, and an LLM chat assistant that analyzes positions and executes trades. Built by coding agents as the capstone of an agentic AI coding course.

## Status

The backend (market data, portfolio, watchlist, chat), frontend, Docker image, start/stop scripts and E2E tests are complete. See `planning/PLAN.md` for the full spec.

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

## Run

Needs Docker and a `.env` file. On Windows, Docker runs inside WSL and the scripts call into it.

| Platform | Start | Stop |
|---|---|---|
| macOS, Linux, WSL | `scripts/start_mac.sh` | `scripts/stop_mac.sh` |
| Windows | `scripts\start_windows.cmd` | `scripts\stop_windows.cmd` |

Then open http://localhost:8000. Start flags: `--build` rebuilds the image, `--open` opens the browser, and `--simulator` uses the simulator even if `.env` has a `MASSIVE_API_KEY`. With an empty key the simulator is used anyway. The start script prints which market data source is active.

Stopping keeps your data in the `finally-data` Docker volume. To reset to $10k, stop the app and run `docker volume rm finally-data`.

## Backend Development

```bash
cd backend
uv sync --dev
uv run pytest
uv run market_data_demo.py   # terminal demo of the price simulator
```

## Frontend Development

Run the backend first, then in a second terminal:

```bash
cd frontend
npm install
npm test
npm run dev   # http://localhost:3000, proxies /api to the backend on port 8000
```

## E2E Tests

Playwright runs in Docker against the app, using the simulator, the mock LLM and a fresh database:

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
```

## Layout

```
backend/    FastAPI app and tests
frontend/   Next.js app
planning/   Spec and agent docs
test/       Playwright E2E tests
scripts/    Docker start/stop scripts
```

## License

See [LICENSE](LICENSE).
