# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, `open_price` (session open; defaults to `previous_price`), plus properties `change`, `change_percent`, `session_change_percent`, `direction` ("up"/"down"/"flat"), and `to_dict()` for JSON serialization.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None) -> PriceUpdate`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)`
  - `version` property — monotonic counter, increments on every update (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set, otherwise `SimulatorDataSource`.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Database

The SQLite layer lives in `db/` (`schema.sql` plus Python modules) and is imported as `db`. Stdlib `sqlite3`, autocommit mode.

```python
from db import connect, init_db, execute_trade, TradeError

init_db()                  # In the lifespan, before the market data source starts
conn = connect()           # One connection per request or task; never shared
trade = execute_trade(conn, "AAPL", "buy", 10, 190.5)  # Atomic; raises TradeError
```

- **Portfolio**: `get_cash`, `get_position`, `get_positions`, `execute_trade`, `record_snapshot`, `get_snapshots`. `TradeError` messages are user-facing. Callers record a snapshot after each trade.
- **Watchlist**: `get_watchlist`, `add_to_watchlist`, `remove_from_watchlist` (both return `False` on no change), `get_tracked_tickers` (watchlist union positions).
- **Chat**: `add_chat_message`, `get_recent_chat_messages`.
- **Transactions**: wrap multi-statement work in `with transaction(conn):`. It cannot be nested.
- **Location**: `DB_PATH` is `<parent of backend>/db/finally.db`. In Docker the code must live at `/app/backend` (not `/app`), installed editable, so this resolves to the `/app/db` volume and the volume does not shadow `backend/db/`.

## API

`app/main.py` builds the app (`create_app`, module-level `app` for uvicorn): `init_db`, market data source, 30s snapshot task, routers, and error handlers. Routes live in `app/api/` and stay thin; the logic is in `app/services.py`.

- **Implemented**: `/api/health`, `/api/stream/prices`, `/api/portfolio` (`GET`, `POST /trade`, `GET /history`), `/api/watchlist` (`GET`, `POST`, `DELETE /{ticker}`), `POST /api/chat`. The static frontend is served from `backend/static/` when that directory exists (Docker only).
- **Trading**: call `place_trade`, not `db.execute_trade`. It validates, prices from the cache, keeps tracking in sync and records the snapshot. Raises `ActionError`/`TradeError`, whose messages are user-facing.
- **Tracking**: after any watchlist or position change call `sync_tracking`, which applies the "watchlist union positions" rule.
- **Threads**: reads are `def` (worker thread); anything calling the market data source is `async` so it stays on the event loop.
- **Chat**: `app/llm.py` owns the schema, the LiteLLM call and mock mode; `get_reply` never raises (failures become an apology with no actions). `app/chat.py` builds the prompt, executes actions and stores the exchange. Results of past actions reach the model as an `[Action results: ...]` suffix on assistant history.
- **Environment**: `app/main.py` loads the project-root `.env` at import, without overriding real variables. Chat tests set `LLM_MOCK` themselves so they never reach the network.
- **Tests**: `tests/api/conftest.py` has `FakeSource`, a deterministic source injected through `create_app(source_factory=...)`.

## Running Tests

```bash
uv run --extra dev pytest -v              # All tests
uv run --extra dev pytest --cov=app --cov=db       # With coverage
uv run --extra dev ruff check app/ db/ tests/ # Lint
```

## Demo

```bash
uv run market_data_demo.py   # (--duration N, --no-screen) Live terminal dashboard with simulated prices
```
