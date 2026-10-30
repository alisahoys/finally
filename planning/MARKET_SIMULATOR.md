# Market Simulator

The approach and code structure for simulated stock prices, used whenever `MASSIVE_API_KEY` is empty. It is built and tested in `backend/app/market/`. It implements the interface in `MARKET_INTERFACE.md`, so the rest of the app does not know prices are simulated.

Measurements here were taken on 2026-10-30 from the current code, with 20,000 ticks for the per-tick figures and 60,000 for event timing.

## Goals

- Look alive: prices change about twice a second.
- Look plausible: no negative prices, realistic tick sizes, stocks that move together.
- Stay self-contained: no network and no API key.
- Supply the occasional sudden move, so a demo has something to react to.

## Approach

Each tick has three steps:

1. Draw correlated random numbers, one per ticker.
2. Move each price with geometric Brownian motion (GBM).
3. Occasionally apply a sudden shock to a ticker.

### Geometric Brownian Motion

GBM multiplies a price by a random factor, so a price can never reach zero or go negative.

```
S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)
```

| Symbol | Meaning |
|---|---|
| `S(t)` | Current price |
| `mu` | Annual drift (expected return) |
| `sigma` | Annual volatility |
| `dt` | Tick length as a fraction of a trading year |
| `Z` | Correlated standard normal draw |

A tick is 500ms, and a trading year is 252 days of 6.5 hours:

```
dt = 0.5 / (252 * 6.5 * 3600) = 8.48e-8
```

So one simulated second is one second of trading time. Each tick's typical move is `sigma * sqrt(dt)`, or about 0.64 basis points for AAPL.

### Correlated Moves

Real stocks move together, so independent draws would look wrong. The simulator builds a correlation matrix `C`, takes its Cholesky factor `L`, and multiplies independent draws by it:

```
L = cholesky(C)
Z_correlated = L @ Z_independent
```

| Pair | Target | Measured |
|---|---|---|
| Tech with tech (AAPL, MSFT) | 0.6 | 0.56 |
| Finance with finance (JPM, V) | 0.5 | 0.44 |
| Cross-sector (AAPL, JPM) | 0.3 | 0.27 |
| TSLA with anything (TSLA, NVDA) | 0.3 | 0.30 |
| Unknown tickers | 0.3 | Not measured |

Measured values fall slightly short of the targets because prices are rounded to cents, which adds noise to very small moves. The underlying draws are correlated at the target values.

TSLA sits in the tech group but is special-cased to 0.3, since it trades on its own story. The Cholesky factor also succeeded with 50 mixed tickers.

### Shock Events

On each tick, each ticker has a 0.1% chance of jumping 2-5% in a random direction. That is about one event per ticker every 500 seconds, or one somewhere on the default 10-ticker watchlist about every 50 seconds. The measured gap was 47.6 seconds.

```python
if random.random() < self._event_prob:
    shock_magnitude = random.uniform(0.02, 0.05)
    shock_sign = random.choice([-1, 1])
    self._prices[ticker] *= 1 + shock_magnitude * shock_sign
```

## Parameters

All constants live in `seed_prices.py`.

| Ticker | Seed | Sigma | Mu | Avg move per tick | Flat ticks |
|---|---|---|---|---|---|
| AAPL | 190 | 0.22 | 0.05 | $0.010 | 30% |
| GOOGL | 175 | 0.25 | 0.05 | $0.010 | 30% |
| MSFT | 420 | 0.20 | 0.05 | $0.020 | 15% |
| AMZN | 185 | 0.28 | 0.05 | $0.012 | 25% |
| TSLA | 250 | 0.50 | 0.03 | $0.030 | 11% |
| NVDA | 800 | 0.40 | 0.08 | $0.075 | 4% |
| META | 500 | 0.30 | 0.05 | $0.035 | 9% |
| JPM | 195 | 0.18 | 0.04 | $0.008 | 36% |
| V | 280 | 0.17 | 0.04 | $0.011 | 27% |
| NFLX | 600 | 0.35 | 0.05 | $0.050 | 6% |

Moves are from the no-event run. A "flat" tick rounds to the same cent as the one before it, so it shows no flash.

Tickers not listed here use `sigma=0.25`, `mu=0.05`, and a random seed price between $50 and $300.

### Seed Prices Are Out of Date

The seeds no longer match the market:

| Ticker | Seed | Close 2026-10-29 | | Ticker | Seed | Close 2026-10-29 |
|---|---|---|---|---|---|---|
| AAPL | 190 | 348.91 | | NVDA | 800 | 213.66 |
| GOOGL | 175 | 283.82 | | META | 500 | 624.52 |
| MSFT | 420 | 530.14 | | JPM | 195 | 343.58 |
| AMZN | 185 | 243.79 | | V | 280 | 410.54 |
| TSLA | 250 | 403.30 | | NFLX | 600 | 62.05 |

**Decision: update `SEED_PRICES` to these closes.** It is a one-dictionary edit, and the tests read the constant rather than literal values. `PLAN.md` section 6 quotes AAPL ~$190 and GOOGL ~$175 only as examples, so update those at the same time.

## Code Structure

```
backend/app/market/
  seed_prices.py   Constants: prices, parameters, correlation groups
  simulator.py     GBMSimulator (pure math) and SimulatorDataSource (async wrapper)
  cache.py         PriceCache, written by the wrapper
  interface.py     MarketDataSource, the contract the wrapper implements
```

Splitting the two classes keeps the math testable without an event loop: `GBMSimulator` knows nothing about asyncio or the cache.

### GBMSimulator

Synchronous, with no I/O.

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT, event_probability: float = 0.001) -> None: ...
    def step(self) -> dict[str, float]: ...             # Advance one tick
    def add_ticker(self, ticker: str) -> None: ...      # Rebuilds the Cholesky factor
    def remove_ticker(self, ticker: str) -> None: ...   # Rebuilds the Cholesky factor
    def get_price(self, ticker: str) -> float | None: ...
    def get_tickers(self) -> list[str]: ...
```

`step()` is the core of the simulator:

```python
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
```

This is condensed from `simulator.py`, which also logs events. The simulator keeps unrounded prices internally, so rounding for display never compounds into the path.

The correlation matrix is rebuilt only when tickers change:

```python
def _rebuild_cholesky(self) -> None:
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
```

### SimulatorDataSource

Adapts `GBMSimulator` to `MarketDataSource`.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5, event_probability: float = 0.001) -> None: ...

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

The broad `except` is deliberate: one bad step should not end the price stream for the whole app.

## Lifecycle

| Event | What happens |
|---|---|
| `start(tickers)` | Creates the simulator, writes seed prices to the cache, starts the loop |
| `add_ticker` | Adds to the simulator and writes the seed price at once, so the ticker can be traded immediately |
| `remove_ticker` | Removes from the simulator and the cache |
| `stop()` | Cancels the loop and waits for it to finish |

Writing the seed price first gives the behaviour `PLAN.md` section 6 expects: the seed price is the first price the cache receives, so it becomes the session open price with no simulator-specific code.

Removing a ticker discards its simulated price. Adding it back restarts it from its seed, or from a new random price if it is unknown, so its price jumps.

## Known Limits

These are acceptable for a demo, and none needs fixing now:

- **Events dominate long sessions.** Over a 6.5-hour run, each ticker sees about 47 shocks, which swing it far more than the GBM term does: roughly 25% against about 1.4% for AAPL. Shocks also add a slight downward pull, about 3% per 6.5 hours, because a +3% and a -3% move do not cancel exactly. Lower `event_probability` if long sessions start to look wild.
- **`dt` does not follow `update_interval`.** Changing the interval without passing a matching `dt` changes the volatility per second of real time. `SimulatorDataSource` does not currently pass `dt` at all.
- **No market hours.** Prices run around the clock, with no overnight gaps.
- **Random is unseeded.** Exact price paths are not reproducible, so tests assert properties rather than values.
- **Tick timing drifts slightly.** The loop sleeps a fixed 500ms after each step, on top of the time the step takes.

## Testing

`tests/market/test_simulator.py` and `test_simulator_source.py` pass and check properties rather than exact values:

- Prices stay positive and rounded to 2 decimals.
- Seed prices apply, and unknown tickers get a random seed.
- Adding and removing tickers works, including duplicates and unknown symbols.
- The Cholesky factor rebuilds on add and is `None` with one ticker.
- Pairwise correlations match each group's constant.
- The source populates the cache, updates over time, survives a failing step, and stops cleanly.

**Gap:** nothing checks the size of a shock. `test_custom_event_probability` runs with `event_probability=1.0` but only confirms the source starts and stops. Add a `GBMSimulator` test with `event_probability=1.0` that asserts each tick moves about 2-5%.

Run the demo to see it live:

```bash
cd backend
uv run market_data_demo.py
```
