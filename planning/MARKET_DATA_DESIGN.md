# Market Data Backend Design

The implementation design for FinAlly's market data layer: one Python API over two price sources, a GBM simulator and the Massive REST API. It is written so an agent can build from it without reading anything else.

**Status:** the simulator, cache, factory and SSE stream are built in `backend/app/market/`, and the simulator path works. **The Massive path writes no prices on any plan today.** Section 9 lists the changes, in order.

All code here was run on 2026-10-30 on a scratch copy of the backend with `massive` 2.9.1, and 97 tests passed. Section 12 says what that does and does not prove.

**Precedence:** where this document differs from `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md` or `MASSIVE_API.md`, this document wins. Those three stay useful as background: `MASSIVE_API.md` is the API reference, and the other two explain the reasoning. Ignore `planning/archive/`, which has wrong field names and plan limits.

## Contents

1. [Architecture](#1-architecture)
2. [Unified API](#2-unified-api)
3. [Simulator](#3-simulator)
4. [Massive](#4-massive)
5. [SSE Stream](#5-sse-stream)
6. [App Integration](#6-app-integration)
7. [Tracked Tickers](#7-tracked-tickers)
8. [Testing](#8-testing)
9. [Implementation Order](#9-implementation-order)
10. [Documentation Follow-Ups](#10-documentation-follow-ups)
11. [Known Limits](#11-known-limits)
12. [What Was Verified](#12-what-was-verified)

## 1. Architecture

Sources push prices into a cache on their own schedule, and consumers only read the cache. Nothing downstream waits on a network call or knows which source is running.

```
create_market_data_source(cache)
        |
        |-- MASSIVE_API_KEY set --> MassiveDataSource --+-- snapshots, every 15s (paid plans)
        |                                               +-- daily closes, hourly (free plan)
        |
        +-- otherwise ------------> SimulatorDataSource (GBM, every 500ms)
                                            |
                                            v  writes
                                       PriceCache
                                            |  reads
                 +--------------------------+------------------------+
                 v                          v                        v
          SSE /api/stream/prices    Portfolio valuation       Trade execution
```

| File | Responsibility | Change needed |
|---|---|---|
| `models.py` | `PriceUpdate`, the only type that leaves this layer | Add `open_price`, `session_change_percent` |
| `cache.py` | `PriceCache`, thread-safe latest prices | Set `open_price`; bump version on remove |
| `interface.py` | `MarketDataSource` abstract class | None |
| `seed_prices.py` | Simulator constants | Update seed prices |
| `simulator.py` | `GBMSimulator` and `SimulatorDataSource` | One comment |
| `massive_client.py` | `MassiveDataSource` | Replace polling internals |
| `factory.py` | `create_market_data_source()` | None |
| `stream.py` | SSE endpoint | Two small fixes |

The `.py` files under `backend/` use CRLF line endings. Keep them, so diffs stay small.

## 2. Unified API

Import everything from `app.market`:

```python
from app.market import (
    MarketDataSource,
    PriceCache,
    PriceUpdate,
    create_market_data_source,
    create_stream_router,
)
```

### PriceUpdate

**File: `backend/app/market/models.py`** (complete)

```python
"""Data models for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    open_price: float  # First price seen since the ticker was added to tracking
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        """Absolute price change from previous update."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def session_change_percent(self) -> float:
        """Percentage change from the session open price."""
        if self.open_price == 0:
            return 0.0
        return round((self.price - self.open_price) / self.open_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat'."""
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE transmission."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "open_price": self.open_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "session_change_percent": self.session_change_percent,
            "direction": self.direction,
        }
```

Derived values are properties, so they can never disagree with the stored prices. `open_price` has no default because only the cache can set it correctly.

### PriceCache

**File: `backend/app/market/cache.py`.** Only `update` and `remove` change; `get`, `get_price`, `get_all`, `version`, `__len__` and `__contains__` stay as they are.

```python
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price for a ticker. Returns the created PriceUpdate.

        Automatically computes direction and change from the previous price.
        If this is the first update for the ticker, previous_price == price (direction='flat')
        and the price becomes the session open_price.
        """
        with self._lock:
            ts = timestamp or time.time()
            price = round(price, 2)
            prev = self._prices.get(ticker)

            update = PriceUpdate(
                ticker=ticker,
                price=price,
                previous_price=prev.price if prev else price,
                open_price=prev.open_price if prev else price,
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def remove(self, ticker: str) -> None:
        """Remove a ticker and its open price. Bumps the version so SSE clients see it go."""
        with self._lock:
            if self._prices.pop(ticker, None):
                self._version += 1
```

Because `remove` discards the entry, a ticker that is removed and added back gets a fresh open price, as `PLAN.md` section 6 requires. The version bump matters on Massive, where a removed ticker would otherwise stay on clients until the next poll.

Example:

```python
cache = PriceCache()
cache.update("AAPL", 190.00)

update = cache.update("AAPL", 191.90)
update.previous_price          # 190.0
update.open_price              # 190.0
update.direction               # "up"
update.session_change_percent  # 1.0

cache.get("AAPL")              # PriceUpdate, or None if unknown
cache.get_price("AAPL")        # 191.9, or None if unknown
cache.get_all()                # {"AAPL": PriceUpdate(...)}, a copy
cache.version                  # 2
```

The lock is a `threading.Lock`, not an `asyncio.Lock`, because code that reaches the cache can run in a worker thread through `asyncio.to_thread`.

### MarketDataSource

**File: `backend/app/market/interface.py`** (no change; bodies are docstrings in the real file)

```python
class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    def get_tickers(self) -> list[str]: ...
```

| Method | Contract |
|---|---|
| `start` | Call once. Writes first prices where possible, then starts the background task |
| `stop` | Cancels the task. Safe to repeat |
| `add_ticker` | No-op if tracked. **On return, the ticker is priced if the source can price it now** |
| `remove_ticker` | No-op if untracked. Also removes the cache entry |
| `get_tickers` | The tracked tickers |

There is deliberately no `get_price()`. Reads go through the cache.

### Factory

**File: `backend/app/market/factory.py`** (no change)

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Massive if MASSIVE_API_KEY is non-empty, otherwise the simulator. Returns unstarted."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
```

The choice is made once at startup. An invalid key does not fall back to the simulator, because silently showing invented prices to someone who configured real data is worse than an error in the logs.

### Source Behaviour

| | Simulator | Massive (paid) | Massive (Basic) |
|---|---|---|---|
| Price source | GBM | Latest snapshot | Last session's close |
| Update interval | 0.5s | 15s | 1 hour |
| Prices move intraday | Yes | Yes, delayed 15 min below Advanced | **No** |
| Priced when `add_ticker` returns | Always | If it traded and the call succeeded | If it traded and closes have loaded |
| Unknown symbol | Random seed price | Never priced | Never priced |
| `session_change_percent` | Against seed price | Against first poll | 0 until a new session's close arrives |

Callers must handle `cache.get()` returning `None`. `PLAN.md` section 8 defines that as a `400` on trades and `null` fields in responses.

## 3. Simulator

The simulator needs no network or key. Each tick it draws correlated random numbers, moves each price with geometric Brownian motion, and occasionally applies a sudden shock.

GBM multiplies a price by a random factor, so a price can never reach zero:

```
S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

dt = 0.5 / (252 * 6.5 * 3600) = 8.48e-8     500ms as a fraction of a trading year
```

To make stocks move together, it multiplies independent draws by the Cholesky factor of a correlation matrix:

```
L = cholesky(C)
Z_correlated = L @ Z_independent
```

### Constants

**File: `backend/app/market/seed_prices.py`.** Replace `SEED_PRICES` with the closes from 2026-10-29, because the old seeds no longer resemble the market. Everything else stays.

```python
# Starting prices for the default watchlist (closes from 2026-10-29)
SEED_PRICES: dict[str, float] = {
    "AAPL": 348.91,
    "GOOGL": 283.82,
    "MSFT": 530.14,
    "AMZN": 243.79,
    "TSLA": 403.30,
    "NVDA": 213.66,
    "META": 624.52,
    "JPM": 343.58,
    "V": 410.54,
    "NFLX": 62.05,
}

TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL": {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05},
    "AMZN": {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03},  # High volatility
    "NVDA": {"sigma": 0.40, "mu": 0.08},  # High volatility, strong drift
    "META": {"sigma": 0.30, "mu": 0.05},
    "JPM": {"sigma": 0.18, "mu": 0.04},  # Low volatility (bank)
    "V": {"sigma": 0.17, "mu": 0.04},  # Low volatility (payments)
    "NFLX": {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR = 0.6  # Tech stocks move together
INTRA_FINANCE_CORR = 0.5  # Finance stocks move together
CROSS_GROUP_CORR = 0.3  # Between sectors / unknown tickers
TSLA_CORR = 0.3  # TSLA does its own thing
```

Tickers not listed use `DEFAULT_PARAMS` and a random seed between $50 and $300.

Measured with the new seeds over 20,000 ticks with shocks off. A "flat" tick rounds to the same cent as the one before, so it shows no flash.

| Ticker | Avg move per tick | Flat ticks | | Ticker | Avg move per tick | Flat ticks |
|---|---|---|---|---|---|---|
| AAPL | $0.018 | 18% | | NVDA | $0.020 | 16% |
| GOOGL | $0.017 | 19% | | META | $0.043 | 8% |
| MSFT | $0.025 | 13% | | JPM | $0.014 | 22% |
| AMZN | $0.016 | 20% | | V | $0.016 | 19% |
| TSLA | $0.047 | 7% | | NFLX | $0.005 | 53% |

**Decision: leave NFLX's volatility alone.** At $62.05 it is flat on about half its ticks, but it still flashes about once a second, which is alive enough. Inflating sigma for one ticker would make its percentage moves unrealistic.

Measured correlations were 0.59 for AAPL/MSFT (target 0.6), 0.48 for JPM/V (0.5), 0.29 for AAPL/JPM (0.3) and 0.29 for TSLA/NVDA (0.3). Rounding to cents pulls them slightly below target, and more so on cheap tickers.

### GBMSimulator

**File: `backend/app/market/simulator.py`** (built). Pure math, synchronous, with no asyncio or cache, so it can be tested without an event loop. The core, condensed from the file, which also logs shocks:

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT, event_probability: float = 0.001) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Returns {ticker: new_price}."""
        n = len(self._tickers)
        if n == 0:
            return {}

        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu = self._params[ticker]["mu"]
            sigma = self._params[ticker]["sigma"]

            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._event_prob:
                shock_magnitude = random.uniform(0.02, 0.05)
                shock_sign = random.choice([-1, 1])
                self._prices[ticker] *= 1 + shock_magnitude * shock_sign

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add a ticker without rebuilding Cholesky (for batch initialization)."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """Rebuild the Cholesky decomposition. Called whenever tickers change."""
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho

        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Correlation between two tickers, from their sector groups."""
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]

        # TSLA is in no group; named here so its correlation can be tuned on its own
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR

        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR

        return CROSS_GROUP_CORR
```

`add_ticker`, `remove_ticker`, `get_price` and `get_tickers` are thin wrappers over this state. The comment above replaces the one in `simulator.py` that wrongly says TSLA is in the tech set.

The simulator keeps unrounded prices internally, so rounding for display never compounds into the path. A shock is about one event per ticker every 500 seconds, or one somewhere on the default watchlist about every 50 seconds.

### SimulatorDataSource

Adapts `GBMSimulator` to `MarketDataSource`. Built, with no change needed.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5, event_probability: float = 0.001) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        # Seed the cache with initial prices so SSE has data immediately
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            # Seed cache immediately so the ticker has a price right away
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    async def _run_loop(self) -> None:
        """Core loop: step the simulation, write to cache, sleep."""
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

The seed price is the first price the cache receives, so it becomes the session open price with no simulator-specific code. The broad `except` is deliberate: one bad step should not end the price stream for the whole app.

## 4. Massive

### Endpoints

| Need | Endpoint | Client call | Plan |
|---|---|---|---|
| Latest prices | Full Market Snapshot | `get_snapshot_all(market_type="stocks", tickers=[...])` | Starter or above |
| End-of-day prices | Daily Market Summary | `get_grouped_daily_aggs(date=..., adjusted=True)` | All, including free Basic |

Each is one request however many tickers are tracked. The client is synchronous, so every call goes through `asyncio.to_thread`.

### Three Traps in the Current Code

Each of these was reproduced with the real client against a local server.

| Trap | Current code | Fix |
|---|---|---|
| The enum builds a bad URL | `SnapshotMarketType.STOCKS` requests `/locale/global/markets/SnapshotMarketType.STOCKS/tickers`, which returns `404` | Pass the string `"stocks"` |
| `last_trade` has no `.timestamp` | The attribute is `sip_timestamp`, and `last_trade` is `None` on Starter, so every snapshot is skipped | `snapshot_price()`, and `snap.updated / 1e9` |
| Snapshots need a paid plan | Basic gets `403 NOT_AUTHORIZED` on every poll, so no prices at all | Fall back to daily closes |

The first two hide each other, so fixing either alone still produces no prices.

### Poll States

```
                 403 NOT_AUTHORIZED on a snapshot
  [snapshots] -------------------------------------> [closes pending]  retry every 60s
   every 15s                                                 |
                                                             | closes loaded
                                                             v
                                                       [end of day]    refresh hourly
```

The switch lasts for the life of the process, so a plan upgrade needs a restart.

**Decision: stay on the 60-second retry until closes have actually loaded.** Going straight to hourly would leave a Basic key with no prices for an hour after one `429`, and each restart spends most of the 5 requests/min allowance. The interval is 60 seconds rather than 15 because Basic's limit is per minute.

**Decision: `add_ticker` prices the ticker before returning.** On paid plans that costs one extra snapshot call, and on Basic it reads the closes already in memory. The alternative leaves a just-added ticker unpriced for up to 15 seconds, which makes the first buy of a new ticker fail (see section 7).

**Decision: ignore snapshot rows for tickers no longer tracked.** A poll in flight when `remove_ticker` runs would otherwise write the ticker back into the cache, where nothing would ever remove it. It would stay on every client, frozen, until a restart.

### Client

**File: `backend/app/market/massive_client.py`** (complete replacement)

```python
"""Massive (Polygon.io) API client for real market data."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from massive import RESTClient
from massive.exceptions import BadResponse
from massive.rest.models import GroupedDailyAgg, TickerSnapshot

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

END_OF_DAY_INTERVAL = 3600.0  # Refresh hourly once closes have loaded
END_OF_DAY_RETRY_INTERVAL = 60.0  # Until then, outlast the per-minute limit on Basic
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


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Polls the full market snapshot for all tracked tickers in a single call. The
    free Basic plan has no snapshots, so on the first 403 this switches to daily
    closes for the life of the process.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None
        self._end_of_day = False
        self._closes: dict[str, GroupedDailyAgg] = {}

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)

        # Do an immediate first poll so the cache has data right away
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        """Track a ticker and price it now, so a caller can trade it straight away."""
        ticker = ticker.upper().strip()
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        if self._end_of_day:
            self._write_close(ticker)
        else:
            await self._poll_once()

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Internal ---

    async def _poll_loop(self) -> None:
        """Poll on interval. First poll already happened in start()."""
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

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
            self._interval = END_OF_DAY_RETRY_INTERVAL
            return
        for snap in snapshots:
            price = snapshot_price(snap)
            if price and snap.ticker in self._tickers:  # May have been removed mid-poll
                timestamp = snap.updated / 1e9 if snap.updated else None
                self._cache.update(snap.ticker, price, timestamp)

    async def _poll_closes(self) -> None:
        """Refresh the whole-market closes and write the tracked tickers."""
        closes = await asyncio.to_thread(latest_closes, self._client)
        if not closes:
            return
        self._closes = closes
        for ticker in self._tickers:
            self._write_close(ticker)
        self._interval = END_OF_DAY_INTERVAL

    def _write_close(self, ticker: str) -> None:
        bar = self._closes.get(ticker)
        if bar:
            self._cache.update(ticker, bar.close, bar.timestamp / 1e3)

    def _fetch_snapshots(self) -> list[TickerSnapshot]:
        """Synchronous Massive call. Runs in a thread."""
        return self._client.get_snapshot_all(market_type="stocks", tickers=self._tickers)
```

Notes on the code:

- `api_key` is always passed explicitly. The client's default argument reads the environment when the module is imported, which is before `.env` is loaded.
- `snapshot_price` skips zeros because snapshots are cleared overnight. `last_trade` is `None` on Starter.
- `NOT_AUTHORIZED` is matched in the message text because `BadResponse` carries no status code.
- `latest_closes` starts at yesterday in UTC and treats a `403` as "too recent" and an empty result as a non-trading day.
- The whole-market result is kept in `_closes`, so adding a ticker on Basic needs no API call.
- A symbol with no snapshot row or close stays unpriced, and the rest of the app treats it like any other cache miss.

### Failure Behaviour

| Failure | Raised as | What happens |
|---|---|---|
| Bad or missing key (`401`) | `BadResponse` | Logged every poll. No prices. Fix the key and restart |
| Plan excludes snapshots (`403`) | `BadResponse` | Switch to daily closes |
| Date too recent (`403`) | `BadResponse` | Try an earlier date |
| Rate limit (`429`) | **`urllib3` `MaxRetryError`** | Logged, retried on the next interval |
| Server error (`5xx`) | **`urllib3` `MaxRetryError`** (not reproduced; same client path as `429`) | Logged, retried on the next interval |
| Network failure | `urllib3` exception | Logged, retried on the next interval |

`MASSIVE_API.md` says `BadResponse` covers every non-200 response. That does not hold for the statuses the client retries (`413`, `429`, `499`, `5xx`): once retries run out, urllib3 raises `MaxRetryError` first. `_poll_once` catches `Exception`, so the behaviour above is unaffected, but do not write code that expects a `429` to arrive as `BadResponse`. An exhausted `429` also costs 4 requests, since the client tries 4 times in under a second.

On any failure the cache keeps its last prices, and SSE carries on with them.

### Request Budget on Basic

The limit is 5 requests/min. A normal first poll costs 1 snapshot call plus 1 to 3 daily calls, depending on the day of the week. The worst case is 1 + 5: the morning (UTC) after a Monday holiday, before Tuesday's data is ready. The sixth call gets a `429`, and 60 seconds later the retry runs without the snapshot call, so it fits in 5.

## 5. SSE Stream

**File: `backend/app/market/stream.py`** (complete)

```python
"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Create the SSE streaming router with a reference to the price cache.

    This factory pattern lets us inject the PriceCache without globals.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices every ~500ms. The client connects
        with EventSource and receives events in the format:

            data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}

        Includes a retry directive so the browser auto-reconnects on
        disconnection (EventSource built-in behavior).
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted price events.

    Sends all prices every `interval` seconds. Stops when the client
    disconnects (detected via request.is_disconnected()).
    """
    # Tell the client to retry after 1 second if the connection drops
    yield "retry: 1000\n\n"

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            # Check for client disconnect
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()
                data = {ticker: update.to_dict() for ticker, update in prices.items()}
                yield f"data: {json.dumps(data)}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
```

Two things changed from the current file:

- **Empty events are sent.** The old `if prices:` guard meant that removing the last ticker sent nothing, so clients kept showing it.
- **The router is created inside the factory.** A module-level router gains a duplicate route each time the factory is called, which happens when tests build several apps.

Every event is complete, so a client replaces its state rather than merging. A ticker that is missing from an event is no longer tracked, and `{}` means nothing is tracked.

Wire format, as captured from a running server:

```
retry: 1000

data: {"AAPL": {"ticker": "AAPL", "price": 348.92, "previous_price": 348.92, "open_price": 348.91, "timestamp": 1793360493.1498737, "change": 0.0, "change_percent": 0.0, "session_change_percent": 0.0029, "direction": "flat"}, "NFLX": {...}}
```

Client:

```typescript
const source = new EventSource("/api/stream/prices");

source.onmessage = (event) => {
  const prices: Record<string, PriceUpdate> = JSON.parse(event.data);
  setPrices(prices);
};
```

`EventSource` reconnects by itself, and a new connection receives a full event straight away because `last_version` starts at `-1`.

Do not assume `timestamp` strictly increases. On Massive it is the source's time, so it can repeat or lag; build chart points from receipt time. On Basic, events arrive only hourly, so a long gap is normal and not a sign of a dead connection.

## 6. App Integration

**File: `backend/app/main.py`** (new)

```python
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.market import PriceCache, create_market_data_source, create_stream_router

load_dotenv(Path(__file__).parents[2] / ".env")  # No file in Docker, so this does nothing there

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

- The database must be ready first, because the initial tickers come from it (`PLAN.md` section 7).
- The cache is created outside `lifespan` because `create_stream_router` needs it when the app is built.
- `load_dotenv` leaves existing environment variables alone by default, as `PLAN.md` section 5 requires.
- `init_db` and `load_tracked_tickers` belong to the database work, not this layer.

```python
def load_tracked_tickers(conn: sqlite3.Connection) -> list[str]:
    """The union of watchlist and position tickers (PLAN.md section 6)."""
    query = """
        SELECT ticker FROM watchlist WHERE user_id = 'default'
        UNION
        SELECT ticker FROM positions WHERE user_id = 'default'
    """
    return [row[0] for row in conn.execute(query)]
```

### Shutdown

**Decision: run uvicorn with `--timeout-graceful-shutdown 2`.** An open SSE connection never finishes by itself, and uvicorn waits for connections before it runs the lifespan shutdown. Measured with one client attached: on SIGTERM the default settings were still running after 20 seconds, so `docker stop` would wait out its timeout and kill the process, and `source.stop()` would never run. With the flag it exited in 2.3 seconds and `source.stop()` ran. It logs one traceback for the cancelled stream, which is harmless.

```dockerfile
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "2"]
```

### Reading Prices

```python
update = price_cache.get(ticker)
if update is None:
    raise HTTPException(400, f"No price available for {ticker} yet")

fill_price = update.price
```

SSE needs no code here. `GET /api/watchlist` builds its row from the same fields:

```python
def watchlist_row(ticker: str, added_at: str, update: PriceUpdate | None) -> dict:
    """One GET /api/watchlist row. Price fields are null until a price is cached."""
    return {
        "ticker": ticker,
        "price": update.price if update else None,
        "open_price": update.open_price if update else None,
        "session_change_percent": update.session_change_percent if update else None,
        "added_at": added_at,
    }
```

## 7. Tracked Tickers

Sources know nothing about the database. Route and trade code decide what to track, using one rule: **a ticker is tracked while it is on the watchlist or held.**

`PLAN.md` says buying starts tracking a ticker, and also rejects a trade with no cached price, but not in which order. Checking the price first means an untracked ticker can never be bought. So the order is:

1. Call `add_ticker`, which is a no-op if the ticker is tracked and prices it if it is new.
2. Read the price and run the trade.
3. Afterwards, whether the trade succeeded or not, stop tracking the ticker if it is neither watched nor held.

Step 3 sits in a `finally`, so one rule covers a rejected buy, a sale to zero, and a normal trade, where it does nothing.

```python
def is_watched_or_held(conn: sqlite3.Connection, ticker: str) -> bool:
    query = """
        SELECT 1 FROM watchlist WHERE user_id = 'default' AND ticker = ?
        UNION
        SELECT 1 FROM positions WHERE user_id = 'default' AND ticker = ?
    """
    return conn.execute(query, (ticker, ticker)).fetchone() is not None


async def release_ticker(source: MarketDataSource, conn: sqlite3.Connection, ticker: str) -> None:
    """Stop tracking a ticker that is neither on the watchlist nor held."""
    if not is_watched_or_held(conn, ticker):
        await source.remove_ticker(ticker)


async def execute_trade(
    source: MarketDataSource,
    cache: PriceCache,
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
) -> dict:
    """Run a trade for the API or the AI chat. Raises TradeError on any rejection."""
    await source.add_ticker(ticker)
    try:
        return apply_trade(conn, ticker, side, quantity, cache.get(ticker))
    finally:
        await release_ticker(source, conn, ticker)
```

`apply_trade` is the portfolio logic: it raises `TradeError` if the update is `None` or the trade fails validation. The route turns that into a `400`, and the chat code turns it into an action with `status: "error"`.

| Event | Calls |
|---|---|
| Added to the watchlist | Insert the row, then `await source.add_ticker(ticker)` |
| Removed from the watchlist | Delete the row, then `await release_ticker(source, conn, ticker)` |
| Any trade | `execute_trade` above |

Routes normalize tickers to uppercase first (`PLAN.md` section 8). The Massive source normalizes too, but the simulator does not.

## 8. Testing

```bash
cd backend
uv run --extra dev pytest -q
uv run --extra dev ruff check app/ tests/
```

### Massive Fixtures Must Use the Real Models

All 73 existing tests pass while the Massive path is broken, because `MagicMock` accepts any attribute and the tests replace `_fetch_snapshots`, so no URL is ever built. Build fixtures with `from_dict` instead, and assert the arguments of the client call:

```python
BAR = {"o": 190.0, "h": 192.0, "l": 189.0, "c": 191.5, "v": 1000000, "vw": 190.8}
NOT_ENTITLED = BadResponse('{"status":"NOT_AUTHORIZED","message":"You are not entitled"}')


def snapshot(ticker: str = "AAPL", **fields) -> TickerSnapshot:
    """Build a snapshot from a documented payload, as the Developer plan returns it."""
    payload = {
        "ticker": ticker,
        "day": BAR,
        "prevDay": {**BAR, "c": 188.0},
        "min": {**BAR, "c": 191.4, "t": 1761600000000},
        "updated": 1761600000000000000,
        "lastTrade": {"p": 191.55, "s": 100, "t": 1761600000123456789},
    }
    return TickerSnapshot.from_dict({**payload, **fields})


def close_bar(ticker: str, close: float) -> GroupedDailyAgg:
    return GroupedDailyAgg.from_dict({"T": ticker, **BAR, "c": close, "t": 1793304000000})


def make_source(cache: PriceCache, tickers: list[str]) -> MassiveDataSource:
    source = MassiveDataSource(api_key="test-key", price_cache=cache)
    source._tickers = tickers
    source._client = MagicMock()
    return source
```

Representative tests:

```python
async def test_requests_stocks_by_string():
    source = make_source(PriceCache(), ["AAPL"])
    source._client.get_snapshot_all.return_value = []
    await source._poll_once()
    source._client.get_snapshot_all.assert_called_once_with(market_type="stocks", tickers=["AAPL"])


async def test_failed_closes_retry_soon_rather_than_in_an_hour():
    cache = PriceCache()
    source = make_source(cache, ["AAPL"])
    source._client.get_snapshot_all.side_effect = NOT_ENTITLED
    source._client.get_grouped_daily_aggs.side_effect = [
        BadResponse("429"),
        [close_bar("AAPL", 348.91)],
    ]
    await source._poll_once()
    assert cache.get("AAPL") is None
    assert source._interval == END_OF_DAY_RETRY_INTERVAL

    await source._poll_once()
    assert cache.get_price("AAPL") == 348.91
    assert source._interval == END_OF_DAY_INTERVAL


async def test_ticker_removed_during_a_poll_stays_removed():
    cache = PriceCache()
    source = make_source(cache, ["AAPL"])

    def fetch_then_remove():
        source._tickers = []
        return [snapshot()]

    with patch.object(source, "_fetch_snapshots", side_effect=fetch_then_remove):
        await source._poll_once()
    assert cache.get("AAPL") is None
```

### SSE Tests

No ASGI client is needed, because the generator can be driven directly:

```python
class FakeRequest:
    """Reports a disconnect after `polls` calls to is_disconnected()."""

    client = None

    def __init__(self, polls: int) -> None:
        self._polls = polls

    async def is_disconnected(self) -> bool:
        self._polls -= 1
        return self._polls < 0


async def test_removing_the_last_ticker_sends_an_empty_event():
    cache = PriceCache()
    cache.update("AAPL", 190.00)
    events = _generate_events(cache, FakeRequest(polls=2), interval=0)
    assert await anext(events) == "retry: 1000\n\n"
    assert "AAPL" in json.loads((await anext(events)).removeprefix("data: "))
    cache.remove("AAPL")
    assert json.loads((await anext(events)).removeprefix("data: ")) == {}
```

### Coverage to Add

| File | Cover |
|---|---|
| `test_models.py` | Add `open_price=` to the 11 existing `PriceUpdate(...)` calls. `session_change_percent`, and both new fields in `to_dict()` |
| `test_cache.py` | First price is the open price; `remove` discards it; `remove` bumps the version once, and not for an unknown ticker |
| `test_simulator.py` | With `event_probability=1.0`, each tick moves 2-5% (nothing checks shock size today) |
| `test_massive.py` | Replace `_make_snapshot`. `snapshot_price` for each plan, zeros and empty snapshots; `latest_closes` past a `403` and empty days, and raising other errors; `market_type="stocks"`; timestamp in seconds; fallback on the first `403`; the two tests above; no rows keeps the last closes; `add_ticker` on paid and Basic, and no call on a duplicate |
| `test_stream.py` (new) | Retry first, then all tickers; nothing while the version is unchanged; the empty event; two routers from two factory calls |
| Portfolio tests (with that work) | On both sources: buy untracked then sell to zero; a rejected buy leaves no tracking; selling a watched ticker keeps it; an unknown symbol on Massive gets the `400` and is released |

`test_timestamp_conversion` and `test_malformed_snapshot_skipped` must be rewritten, because both assert the old `MagicMock` behaviour. Also remove the `_make_snapshot` use in `test_start_immediate_poll`.

## 9. Implementation Order

Each step should leave the suite passing.

1. **Dependencies.** In `pyproject.toml`, require `massive>=2.9.1` and add `python-dotenv`, then run `uv lock`. The lock file pins `massive` at 2.2.0. All 73 tests still passed on 2.9.1.
2. **`open_price`.** Change `models.py`, `cache.py` and `test_models.py`, and add the new tests. Also add the version bump in `remove`.
3. **Stream.** Change `stream.py` and add `test_stream.py`.
4. **Seeds.** Update `SEED_PRICES` and fix the TSLA comment. Tests read the constant, so none should change. Add the shock test.
5. **Massive.** Replace `massive_client.py` and rewrite `test_massive.py` in one step, since the old tests assert the old behaviour.
6. **Live check.** On a Basic key, confirm the 10 default tickers get prices and `ZZZZZ` does not, then restart twice quickly and confirm prices recover.
7. **Wire up the app.** Add `main.py` with the database work, the uvicorn flag in the Dockerfile, and `execute_trade` with the portfolio work.
8. **Update the docs** listed in section 10.

## 10. Documentation Follow-Ups

This design was added without editing other files, so these are still out of date.

| File | Change |
|---|---|
| `PLAN.md` section 6 | "works on all tiers": snapshots need Starter or above, and Basic gets daily closes |
| `PLAN.md` section 6 | "Free tier (5 calls/min): poll every 15 seconds": Basic has no intraday prices, and refreshes closes hourly |
| `PLAN.md` section 6 | "Paid tiers: poll every 2-15 seconds": only Advanced and above are real-time |
| `PLAN.md` section 6 | Seed examples AAPL ~$190 and GOOGL ~$175 become ~$349 and ~$284 |
| `PLAN.md` section 8 | Add the trade order from section 7: add, read the price, trade, release |
| `PLAN.md` section 11 | Add `--timeout-graceful-shutdown 2` to the CMD |
| `MASSIVE_API.md` | Retried statuses raise `MaxRetryError`, not `BadResponse` |
| `MARKET_SIMULATOR.md` | TSLA is not in the tech group. Replace the per-tick table and the measured correlations |
| `MARKET_INTERFACE.md` | Point its Massive implementation at this document |
| `MARKET_DATA_SUMMARY.md`, `README.md`, root `CLAUDE.md` | Say the Massive client is broken until step 5 is done |
| `backend/CLAUDE.md` | Add the new `PriceUpdate` fields |

## 11. Known Limits

None of these needs fixing now.

- **Basic looks quiet.** Prices are real but do not move, so there are no flashes and sparklines stay flat. `MARKET_INTERFACE.md` records that the key in `.env` is Basic, so **anyone running with that key gets this**. Leave `MASSIVE_API_KEY` empty for a live-looking demo, and in E2E tests.
- **Basic can be a day behind.** The lookback starts at yesterday in UTC, so a session's close is not picked up until the UTC date rolls over.
- **`session_change_percent` on a long-running Basic process** compares against the first close it saw, so it stops being 0 once a new session's close arrives.
- **`start()` on Massive waits for the first poll.** From reading the client, an unreachable network could hold startup for about 40 seconds (4 attempts at a 10-second connect timeout). This was not measured.
- **Each `add_ticker` on a paid plan re-polls every ticker.** This is one request, and paid limits are unlimited. It is a plain `await`, so a slow API slows that request.
- **Events dominate long simulator sessions.** Over 6.5 hours, shocks swing a ticker far more than the GBM term does.
- **`dt` does not follow `update_interval`.** Changing the interval without passing a matching `dt` changes volatility per real second.
- **Removing a simulated ticker discards its price.** Adding it back restarts it from its seed, or from a new random price if it is unknown. A rejected buy of an unknown ticker does this too.

Left out on purpose:

- **Historical prices:** charts build from SSE since page load, per `PLAN.md`.
- **A data-quality flag:** the UI spec has nowhere to show "delayed" or "end of day".
- **Market-hours awareness:** outside trading hours the last price simply stops changing.
- **Runtime switching between sources:** restart with a different environment.
- **WebSockets:** `PLAN.md` chose REST polling.

## 12. What Was Verified

Run on 2026-10-30 on a scratch copy of the backend with `massive` 2.9.1, FastAPI 0.128.7 and Python 3.12. **Nothing has been applied to the repo.**

| Check | Result |
|---|---|
| Existing 73 tests on `massive` 2.9.1, before any change | All pass |
| Full suite with this design | 97 pass, ruff clean, 98% coverage |
| Regression tests against the old behaviour | The hourly retry, the mid-poll removal and the empty-event tests each fail, as they should |
| Real `RESTClient` against a local fake server, Starter payload | Correct URL; price taken from the minute bar; unknown symbol unpriced; `add_ticker` priced in 1 call |
| Same, Basic payload | `403` switches to closes; a too-recent date and two empty days are walked; `add_ticker` makes 0 calls |
| Same, `429` during closes | `MaxRetryError`; no prices, 60-second interval; next poll recovers to hourly |
| Same, enum passed as `market_type` | `404` at the `global/markets/SnapshotMarketType.STOCKS` path |
| Real uvicorn with a `curl` SSE client | Events at about 2/s in the documented format; shutdown as described in section 6 |
| Sections 6 and 7 snippets, run as written, on the simulator and a mocked paid Massive source with real SQLite | 9 pass, including `load_tracked_tickers` and `watchlist_row` |
| Section 6 `main.py` as written, with stub `init_db` and `load_tracked_tickers` | Serves SSE; exits on SIGTERM; `.env` is loaded and existing variables win |
| Listings against tested code | `models.py`, `massive_client.py` and `stream.py` match exactly; the section 8 test blocks run as written |

**Not verified:**

- **No live Massive calls were made** for this design, and `.env` was not read. Plan behaviour comes from `MASSIVE_API.md`, whose Basic results were run live earlier. Step 6 in section 9 covers this.
- **The snapshot success path has never run against the real API,** because that needs a paid key. The fake server replays documented payloads through the real client.
- **The 60-second recovery was tested against a fake limiter,** not Massive's real rate-limit window.
- **`apply_trade`, `init_db` and the routes do not exist yet.** The trade flow was tested with a stand-in for `apply_trade`.
