# Massive API Reference

How FinAlly gets real and end-of-day stock prices from Massive (formerly Polygon.io). This replaces `planning/archive/MASSIVE_API.md`, which has wrong field names and plan limits.

**Verified 2026-10-30** against the Massive docs, the `massive` 2.9.1 client source, and live calls using a Stocks Basic key.

| Evidence | Applies to |
|---|---|
| Run live on Basic | Daily Market Summary, Previous Day Bar, Custom Bars, Market Status, and the `403` errors in this document |
| Client source plus documented payloads, **not** run live (needs a paid plan) | Full Market Snapshot success path |
| Docs only | Unified Snapshot, Last Trade, Daily Ticker Summary |

## Which Endpoint to Use

| Need | Endpoint | Calls | Plan |
|---|---|---|---|
| Latest prices for many tickers | Full Market Snapshot | 1 | Starter or above |
| End-of-day prices for many tickers | Daily Market Summary | 1 | All, including free Basic |

FinAlly uses the snapshot when the plan allows it and falls back to the daily summary when it does not. Both return many tickers in one request, so the free limit of 5 requests per minute is not a problem.

## Plans

Only Advanced and above are real-time. The free plan has **no snapshots**, so it cannot return intraday prices.

| Plan | $/month | Requests | Recency | Snapshots | `lastTrade` in snapshot |
|---|---|---|---|---|---|
| Basic | 0 | 5/min | End of day | No | n/a |
| Starter | 29 | Unlimited | 15 min delayed | Yes | **No** |
| Developer | 79 | Unlimited | 15 min delayed | Yes | Yes |
| Advanced | 199 | Unlimited | Real-time | Yes | Yes |
| Business | 2,499 | Unlimited | Real-time FMV + end-of-day SIP | Yes | Check with Massive; Last Trade needs the Expansion add-on |

- Limits apply per asset class. A paid Options plan leaves stocks on 5 requests/min.
- Extra API keys do not raise limits.
- Prices and plan contents change, so check [massive.com/stocks](https://massive.com/stocks) before relying on them.

## Setup

```bash
uv add "massive>=2.9.1"
```

```python
from massive import RESTClient

client = RESTClient(api_key=api_key)
```

- **Package:** `massive` on PyPI, replacing `polygon-api-client`. Latest is 2.9.1 (requires Python 3.10+). `backend/uv.lock` currently pins 2.2.0.
- **Base URL:** `https://api.massive.com`. `https://api.polygon.io` still works.
- **Auth:** the client sends `Authorization: Bearer <key>`. Raw requests can use that header or `?apiKey=<key>`.
- **Always pass `api_key` explicitly.** The default argument reads `os.getenv` when the module is imported, so a key loaded later from `.env` is missed.
- **The client is synchronous.** Call it with `asyncio.to_thread` from async code.
- **`HTTPS_PROXY` is ignored.** Behind a proxy, pass `RESTClient(proxy=...)`.

## Latest Prices: Full Market Snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT
```

| Query parameter | Notes |
|---|---|
| `tickers` | Comma-separated and case-sensitive. Omit it and you get 10,000+ tickers |
| `include_otc` | Default `false` |

```python
snapshots = client.get_snapshot_all(market_type="stocks", tickers=["AAPL", "MSFT"])

for snap in snapshots:
    print(snap.ticker, snapshot_price(snap), snap.todays_change_percent)
```

**Pass `market_type="stocks"`, not `SnapshotMarketType.STOCKS`.** The client compares against the enum's `.value` and formats the raw enum into the path, so the enum requests `/v2/snapshot/locale/global/markets/SnapshotMarketType.STOCKS/tickers`. That returned `404 page not found` live on 2.9.1, and `snapshot.py` builds the path the same way in 2.2.0.

### Response

```json
{
  "status": "OK",
  "count": 1,
  "tickers": [{
    "ticker": "AAPL",
    "todaysChange": -0.124,
    "todaysChangePerc": -0.601,
    "updated": 1605192894630916600,
    "day": {"o": 20.64, "h": 20.64, "l": 20.506, "c": 20.506, "v": 37216, "vw": 20.616},
    "prevDay": {"o": 20.79, "h": 21, "l": 20.5, "c": 20.63, "v": 292738, "vw": 20.6939},
    "min": {"t": 1684428600000, "o": 20.506, "h": 20.506, "l": 20.506, "c": 20.506, "v": 5000, "vw": 20.5105, "av": 37216, "n": 1},
    "lastTrade": {"p": 20.506, "s": 2416, "t": 1605192894630916600, "x": 4, "c": [14, 41], "i": "71675577320245"},
    "lastQuote": {"p": 20.5, "s": 13, "P": 20.6, "S": 22, "t": 1605192959994246100}
  }]
}
```

| JSON | Python (`TickerSnapshot`) | Notes |
|---|---|---|
| `ticker` | `ticker` | |
| `lastTrade.p` | `last_trade.price` | `last_trade` is `None` unless the plan includes trades |
| `lastTrade.t` | `last_trade.sip_timestamp` | Nanoseconds. There is **no** `.timestamp` attribute |
| `lastQuote` | `last_quote` | `None` unless the plan includes quotes |
| `min.c` / `min.t` | `min.close` / `min.timestamp` | `t` is milliseconds |
| `day.c` | `day.close` | `Agg` has no `change_percent` or `previous_close` |
| `prevDay.c` | `prev_day.close` | |
| `todaysChangePerc` | `todays_change_percent` | Change from the previous close, in percent units |
| `updated` | `updated` | Nanoseconds in the documented sample |

### Choosing a Price

Field availability depends on the plan and the time of day, so take the first non-empty value:

```python
def snapshot_price(snap: TickerSnapshot) -> float | None:
    """Best available price: last trade, minute bar, day bar, then previous close."""
    candidates = (
        snap.last_trade and snap.last_trade.price,
        snap.min and snap.min.close,
        snap.day and snap.day.close,
        snap.prev_day and snap.prev_day.close,
    )
    return next((p for p in candidates if p), None)
```

Snapshots are cleared overnight and repopulate from about 4:00 AM ET. The docs say the clear is at 3:30 AM EST, while the client's docstring says 12 AM. During that window zeros are possible, which is why this skips falsy values.

## End-of-Day Prices: Daily Market Summary

```
GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true
```

One request returns every US stock for a date: 12,597 rows for 2026-10-29. There is no ticker filter, so filter on the client.

```python
bars = client.get_grouped_daily_aggs(date="2026-10-29", adjusted=True)
closes = {bar.ticker: bar.close for bar in bars}
print(closes["AAPL"])  # 348.91
```

Live response row:

```json
{"T": "AAPL", "o": 348, "h": 351.43, "l": 347.3, "c": 348.91, "v": 42582126.245661, "vw": 349.3528, "n": 736010, "t": 1793304000000}
```

| JSON | Python (`GroupedDailyAgg`) | Notes |
|---|---|---|
| `T` | `ticker` | |
| `o` `h` `l` `c` | `open` `high` `low` `close` | |
| `v` / `vw` | `volume` / `vwap` | |
| `n` | `transactions` | |
| `t` | `timestamp` | Milliseconds. Observed as 20:00 UTC, the 4 PM ET close |

Observed behaviour on Basic:

| Date requested | Result |
|---|---|
| A completed session | `200` with rows |
| Today, before end of day | `403 NOT_AUTHORIZED`: `Attempted to request today's data before end of day...` |
| Saturday (2026-10-24) | `200` with no rows; the client returns `[]` |

So finding the latest session means walking back from yesterday until rows appear. Massive does not publish the time end-of-day data becomes available. History on Basic is 2 years.

## Other Useful Endpoints

### Previous Day Bar (one ticker)

`GET /v2/aggs/ticker/{ticker}/prev`, on all plans. Costs one request per ticker, so use the daily summary for several tickers.

```python
bar = client.get_previous_close_agg("AAPL")[0]
print(bar.close)  # 348.91
```

### Custom Bars (history)

`GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`, on all plans. `limit` defaults to 5,000 and caps at 50,000. `list_aggs` follows `next_url` pagination, which uses extra requests.

```python
bars = list(client.list_aggs("AAPL", 1, "day", "2026-10-26", "2026-10-29", adjusted=True, sort="asc"))
```

Daily bars here are stamped at the start of the window. Live values were 04:00 UTC (midnight ET), unlike the 20:00 UTC stamp on the daily summary, so compare dates rather than raw timestamps.

### Market Status

`GET /v1/marketstatus/now`, on all plans.

```python
status = client.get_market_status()
print(status.market, status.early_hours, status.after_hours)  # extended-hours True False
```

### Not Used by FinAlly

| Endpoint | Path | Why not |
|---|---|---|
| Daily Ticker Summary | `/v1/open-close/{ticker}/{date}` | One ticker per request. Adds pre-market and after-hours prices |
| Unified Snapshot | `/v3/snapshot?ticker.any_of=...` | Up to 250 tickers, paginated, not on Basic. Adds nothing over the full snapshot |
| Last Trade | `/v2/last/trade/{ticker}` | One ticker per request, Developer and above |
| Single Ticker Snapshot | `/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}` | The full snapshot already covers this |
| WebSockets | `wss://socket.massive.com` | Paid only, and `PLAN.md` chose REST polling |

## Errors

The client raises `massive.exceptions.BadResponse` for every non-200 response, with the response body as the message. `AuthError` is only raised when no key is given at all.

| Status | Body | Meaning | Action |
|---|---|---|---|
| `401` | `{"status":"ERROR","error":"API Key was not provided"}` | Missing or invalid key | Log it; fix the key |
| `403` | `{"status":"NOT_AUTHORIZED","message":"You are not entitled to this data..."}` | Plan excludes the endpoint | Fall back to the daily summary |
| `403` | `{"status":"NOT_AUTHORIZED","message":"Attempted to request today's data before end of day..."}` | Date too recent for the plan | Try an earlier date |
| `404` | `404 page not found` | Bad path, such as the enum issue above | Fix the call |
| `429` | `You've exceeded the maximum requests per minute...` | Over 5/min on Basic | Wait for the next poll |

A `200` response can also carry `"status": "DELAYED"` on 15-minute plans. That is normal, not an error.

The client retries `413`, `429`, `499`, and `5xx` up to 3 times with a sub-second backoff. It does not retry `401` or `403`, and on Basic its `429` retries are too fast to outlast the one-minute window.

## Sources

- [Full Market Snapshot](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot.md)
- [Daily Market Summary](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary.md)
- [Previous Day Bar](https://massive.com/docs/rest/stocks/aggregates/previous-day-bar.md)
- [Daily Ticker Summary](https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary.md)
- [Custom Bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars.md)
- [Unified Snapshot](https://massive.com/docs/rest/stocks/snapshots/unified-snapshot.md)
- [Last Trade](https://massive.com/docs/rest/stocks/trades-quotes/last-trade.md)
- [Market Status](https://massive.com/docs/rest/stocks/market-operations/market-status.md)
- [REST Quickstart](https://massive.com/docs/rest/quickstart.md)
- [Stocks plans](https://massive.com/stocks)
- [Request limits](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis)
- [Real-time access and errors](https://massive.com/knowledge-base/article/how-quickly-can-i-access-massives-market-date)
- [`massive` on PyPI](https://pypi.org/project/massive/) and [client source](https://github.com/massive-com/client-python)
