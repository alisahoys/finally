# Market Data Interface

The unified Python API for stock prices in FinAlly. It uses Massive when `MASSIVE_API_KEY` is set and the simulator otherwise, and downstream code cannot tell which is running.

The interface below is already built in `backend/app/market/`, except for the changes in [Required Changes](#required-changes). **The Massive path does not work today**: it writes no prices on any plan. API details are in `MASSIVE_API.md`; simulator details are in `MARKET_SIMULATOR.md`.

## Design

Sources push prices into a cache on their own schedule. Consumers only ever read the cache, so nothing downstream waits on a network call.

```
create_market_data_source(cache)
        |
        |-- MASSIVE_API_KEY set --> MassiveDataSource --+-- snapshots (paid plans)
        |                                               +-- daily closes (free plan)
        |
        +-- otherwise ------------> SimulatorDataSource (GBM, 500ms)
                                            |
                                            v  writes
                                       PriceCache
                                            |  reads
                 +--------------------------+------------------------+
                 v                          v                        v
          SSE /api/stream/prices    Portfolio valuation       Trade execution
```

## Public API

Import everything from `app.market`:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### PriceUpdate

An immutable price for one ticker at one moment. It is the only data type that leaves this layer. `open_price` is a required change.

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    open_price: float  # First price seen since the ticker was added to tracking
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    change: float                  # price - previous_price
    change_percent: float          # Tick-to-tick, in percent units
    session_change_percent: float  # Against open_price, in percent units
    direction: str                 # "up", "down", or "flat"

    def to_dict(self) -> dict: ...  # The SSE payload for one ticker
```

The last four are computed properties, shown as attributes for brevity.

### PriceCache

Thread-safe, so callers need no locking of their own.

```python
class PriceCache:
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate: ...
    def get(self, ticker: str) -> PriceUpdate | None: ...
    def get_price(self, ticker: str) -> float | None: ...
    def get_all(self) -> dict[str, PriceUpdate]: ...
    def remove(self, ticker: str) -> None: ...

    @property
    def version(self) -> int: ...  # Bumped on every change; drives SSE
```

Prices are rounded to 2 decimals. The first `update()` for a ticker sets `open_price`, and `remove()` discards it, so a ticker that is removed and re-added gets a fresh open price as `PLAN.md` section 6 requires.

### MarketDataSource

```python
class MarketDataSource(ABC):
    async def start(self, tickers: list[str]) -> None: ...  # Call once
    async def stop(self) -> None: ...                       # Safe to repeat
    async def add_ticker(self, ticker: str) -> None: ...    # No-op if present
    async def remove_ticker(self, ticker: str) -> None: ... # Also clears the cache entry
    def get_tickers(self) -> list[str]: ...
```

There is deliberately no `get_price()`. Reads go through the cache.

### create_market_data_source

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Massive if MASSIVE_API_KEY is non-empty, otherwise the simulator. Returns unstarted."""
```

The choice is made once at startup. A key that turns out to be invalid does not fall back to the simulator, because silently showing fake prices to someone who configured real data would be worse than showing an error in the logs.

## Source Behaviour

| | Simulator | Massive (paid) | Massive (Basic) |
|---|---|---|---|
| Price source | GBM | Latest snapshot | Last session's close |
| Update interval | 0.5s | 15s | 1 hour |
| Prices move intraday | Yes | Yes, delayed 15 min below Advanced | **No** |
| Available right after `add_ticker` | Yes | Next poll | Yes, if it traded |
| Unknown symbol | Random seed price | Never priced | Never priced |
| `session_change_percent` | Against seed price | Against first poll | **Always 0** |

Callers must handle `cache.get()` returning `None`. `PLAN.md` section 8 already defines this as a `400` on trades and `null` fields in responses.

## Free Plan Decision

A Basic key cannot call the snapshot endpoint, so `MassiveDataSource` detects the `403 NOT_AUTHORIZED` on its first poll and switches to daily closes for the life of the process. The alternatives were worse:

- **Log the error and do nothing:** the app runs with no prices at all, which is what a Basic key gets today.
- **Fall back to the simulator:** this contradicts "use Massive if the key is set", and shows invented prices as if they were real.

The cost is a quiet UI on Basic: prices are real but stay still, so there are no flashes, and sparklines stay flat. Anyone who wants a live-looking demo should leave `MASSIVE_API_KEY` empty.

## Massive Implementation

This replaces the polling internals of `massive_client.py`. It was exercised against the live API with a Basic key using `massive` 2.9.1: all 10 default tickers priced from one snapshot attempt and one daily summary call, `PYPL` priced immediately on add, and `ZZZZZ` left unpriced. The snapshot branch was tested by replaying documented payloads through the real `TickerSnapshot.from_dict`, because no paid key was available.

```python
from datetime import UTC, datetime, timedelta

from massive import RESTClient
from massive.exceptions import BadResponse
from massive.rest.models import GroupedDailyAgg, TickerSnapshot

END_OF_DAY_INTERVAL = 3600.0
MAX_LOOKBACK_DAYS = 7
NOT_AUTHORIZED = "NOT_AUTHORIZED"


def snapshot_price(snap: TickerSnapshot) -> float | None:
    """Best available price: last trade, minute bar, day bar, then previous close."""
    candidates = (
        snap.last_trade and snap.last_trade.price,
        snap.min and snap.min.close,
        snap.day and snap.day.close,
        snap.prev_day and snap.prev_day.close,
    )
    return next((p for p in candidates if p), None)


def latest_closes(client: RESTClient) -> dict[str, GroupedDailyAgg]:
    """Whole-market daily bars for the most recent completed session."""
    today = datetime.now(UTC).date()
    for days_back in range(1, MAX_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=days_back)
        try:
            bars = client.get_grouped_daily_aggs(date=day.isoformat(), adjusted=True)
        except BadResponse as e:
            if NOT_AUTHORIZED not in str(e):
                raise
            continue
        if bars:
            return {bar.ticker: bar for bar in bars}
    return {}
```

Inside `MassiveDataSource`, add `self._end_of_day = False` and `self._closes: dict[str, GroupedDailyAgg] = {}` to `__init__`, then:

```python
    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            self._write_close(ticker)

    async def _poll_once(self) -> None:
        """Run one poll cycle. Failures are logged and retried on the next interval."""
        if not self._tickers or not self._client:
            return
        try:
            if not self._end_of_day:
                await self._poll_snapshots()
            if self._end_of_day:
                await self._poll_closes()
        except Exception as e:
            logger.error("Massive poll failed: %s", e)

    async def _poll_snapshots(self) -> None:
        """Write the latest prices, or switch to end-of-day if the plan has no snapshots."""
        try:
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
        except BadResponse as e:
            if NOT_AUTHORIZED not in str(e):
                raise
            logger.warning("Massive plan has no snapshots; using end-of-day closes")
            self._end_of_day = True
            self._interval = END_OF_DAY_INTERVAL
            return
        for snap in snapshots:
            price = snapshot_price(snap)
            if price:
                timestamp = snap.updated / 1e9 if snap.updated else None
                self._cache.update(snap.ticker, price, timestamp)

    async def _poll_closes(self) -> None:
        """Refresh the whole-market closes and write the tracked tickers."""
        self._closes = await asyncio.to_thread(latest_closes, self._client)
        for ticker in self._tickers:
            self._write_close(ticker)

    def _write_close(self, ticker: str) -> None:
        bar = self._closes.get(ticker)
        if bar:
            self._cache.update(ticker, bar.close, bar.timestamp / 1e3)

    def _fetch_snapshots(self) -> list[TickerSnapshot]:
        """Synchronous Massive call. Runs in a thread."""
        return self._client.get_snapshot_all(market_type="stocks", tickers=self._tickers)
```

Notes:

- The whole-market result is kept in `_closes`, so adding a ticker on Basic needs no API call.
- The lookback starts at yesterday. The worst case, the first poll on the Tuesday after a Monday holiday, is 1 snapshot call plus 4 daily calls, which fits the 5 requests/min limit.
- The `NOT_AUTHORIZED` check matches the response text because `BadResponse` carries no status code.
- A plan upgrade needs a restart to leave end-of-day mode.

## Using It

### Startup and Shutdown

The database must be ready before the source starts, because the initial tickers come from it (`PLAN.md` section 7).

```python
price_cache = PriceCache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    source = create_market_data_source(price_cache)
    await source.start(load_tracked_tickers())
    app.state.market_source = source
    yield
    await source.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(create_stream_router(price_cache))
```

`create_stream_router` needs the cache when the app is built, which is why the cache is created outside `lifespan`.

For local development outside Docker, call `load_dotenv()` before `create_market_data_source`. `python-dotenv` is not yet a dependency.

### Tracked Tickers

Sources know nothing about the database. The route and trade code decides what to track, using the union of watchlist and positions from `PLAN.md` section 6:

| Event | Call |
|---|---|
| Ticker added to the watchlist | `await source.add_ticker(ticker)` |
| Buy | `await source.add_ticker(ticker)` (no-op if tracked) |
| Removed from the watchlist | `await source.remove_ticker(ticker)` only if no position is held |
| Sold to zero | `await source.remove_ticker(ticker)` only if not on the watchlist |

### Reading Prices

```python
update = price_cache.get("AAPL")
if update is None:
    raise HTTPException(400, "No price available for AAPL yet")

fill_price = update.price
```

SSE needs no code here: `GET /api/stream/prices` sends all of `get_all()` whenever `version` changes.

## Required Changes

| # | File | Change | Why |
|---|---|---|---|
| 1 | `massive_client.py` | Pass `market_type="stocks"` | The enum builds a bad URL; every poll gets a `404` |
| 2 | `massive_client.py` | Use `snapshot_price()` and `snap.updated / 1e9` | `last_trade.timestamp` does not exist, and `last_trade` is `None` on Starter. Every snapshot would be skipped |
| 3 | `massive_client.py` | Add the end-of-day fallback | Basic keys get no prices. **The key in `.env` is Basic** |
| 4 | `models.py`, `cache.py` | Add `open_price` and `session_change_percent` | Approved in `PLAN.md` section 6 |
| 5 | `cache.py` | Bump `version` when `remove()` deletes an entry | On Massive, removed tickers stay in SSE clients until the next poll |
| 6 | `pyproject.toml` | Require `massive>=2.9.1` and refresh `uv.lock` | Locked at 2.2.0 |
| 7 | `test_massive.py` | Build fixtures with `TickerSnapshot.from_dict` | See below |

Change 1 and change 2 hide each other: fixing either alone still produces no prices.

Changes 2 to 5 were checked on a scratch copy of the backend, with the code above merged in as written, and 72 of 74 tests passed. The total is the 73 existing tests, with `open_price` added to their `PriceUpdate` calls, plus one new cache test. The two failures are expected, and both need rewriting under change 7:

- `test_timestamp_conversion` asserts the old `last_trade.timestamp` conversion through a `MagicMock`.
- `test_malformed_snapshot_skipped` relies on `last_trade = None` being an error, which is now a supported case.

### Testing Massive

All 73 tests pass today while the Massive path is broken, because `MagicMock` accepts any attribute and the tests replace `_fetch_snapshots`, so the URL is never built. Fixtures should go through the real models:

```python
BAR = {"o": 190.0, "h": 192.0, "l": 189.0, "c": 191.5, "v": 1000000, "vw": 190.8}
FULL = {
    "ticker": "AAPL",
    "day": BAR,
    "prevDay": {**BAR, "c": 188.0},
    "min": {**BAR, "c": 191.4, "t": 1761600000000},
    "updated": 1761600000000000000,
    "lastTrade": {"p": 191.55, "s": 100, "t": 1761600000123456789},
}
STARTER = {k: v for k, v in FULL.items() if k != "lastTrade"}


def test_snapshot_price_falls_back_by_plan():
    assert snapshot_price(TickerSnapshot.from_dict(FULL)) == 191.55
    assert snapshot_price(TickerSnapshot.from_dict(STARTER)) == 191.4
```

Also assert the call uses `market_type="stocks"`, and cover the fallback by making the mocked snapshot call raise `BadResponse('{"status":"NOT_AUTHORIZED"}')`.

## PLAN.md Corrections

These statements in `PLAN.md` section 6 conflict with what Massive does today:

| Current text | Correction |
|---|---|
| "REST API polling... works on all tiers" | Snapshots need Starter or above; Basic gets daily closes |
| "Free tier (5 calls/min): poll every 15 seconds" | Basic has no intraday prices to poll; it refreshes closes hourly |
| "Paid tiers: poll every 2-15 seconds" | Paid limits are unlimited, but only Advanced and above are real-time |

## Left Out on Purpose

- **Historical prices:** charts build from SSE since page load, per `PLAN.md`.
- **A data-quality flag:** the UI spec has nowhere to show "delayed" or "end of day".
- **Market-hours awareness:** outside trading hours the last price simply stops changing.
- **Runtime switching between sources:** restart with a different environment.
