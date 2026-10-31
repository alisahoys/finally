"""Portfolio and watchlist operations shared by the API routes.

The async functions change what the market data source tracks, so they must run
on the event loop alongside it.
"""

import re
import sqlite3

from app.market import MarketDataSource, PriceCache
from db import (
    add_to_watchlist,
    execute_trade,
    get_cash,
    get_positions,
    get_tracked_tickers,
    get_watchlist,
    record_snapshot,
    remove_from_watchlist,
)

TICKER_PATTERN = re.compile(r"[A-Z]{1,5}")


class ActionError(ValueError):
    """A request failed validation; the message is safe to show to the user."""


class NotOnWatchlistError(ActionError):
    """The ticker to remove is not on the watchlist."""


def normalize_ticker(ticker: str) -> str:
    """Return the ticker in uppercase, or raise ActionError if it is malformed."""
    normalized = ticker.upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise ActionError(f"Invalid ticker: {ticker}")
    return normalized


async def sync_tracking(conn: sqlite3.Connection, source: MarketDataSource, ticker: str) -> None:
    """Make the source track `ticker` only if it is on the watchlist or held."""
    if ticker in get_tracked_tickers(conn):
        await _ensure_tracked(source, ticker)
    else:
        await source.remove_ticker(ticker)


async def _ensure_tracked(source: MarketDataSource, ticker: str) -> None:
    # Checked here because re-adding makes the simulator rewrite the cached price.
    if ticker not in source.get_tickers():
        await source.add_ticker(ticker)


def get_portfolio(conn: sqlite3.Connection, cache: PriceCache) -> dict:
    """Return cash, valued positions and totals in the GET /api/portfolio shape."""
    positions = [_value_position(position, cache) for position in get_positions(conn)]
    cash = get_cash(conn)
    return {
        "cash_balance": round(cash, 2),
        "total_value": round(cash + sum(p["market_value"] for p in positions), 2),
        "unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
        "positions": positions,
    }


def _value_position(position: dict, cache: PriceCache) -> dict:
    ticker, quantity, avg_cost = position["ticker"], position["quantity"], position["avg_cost"]
    current_price = cache.get_price(ticker)
    price = avg_cost if current_price is None else current_price
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "current_price": current_price,
        "market_value": round(quantity * price, 2),
        "unrealized_pnl": round(quantity * (price - avg_cost), 2),
        "pnl_percent": round((price - avg_cost) / avg_cost * 100, 2),
    }


async def place_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    source: MarketDataSource,
    ticker: str,
    side: str,
    quantity: float,
) -> dict:
    """Fill a market order at the cached price and snapshot the portfolio.

    A buy starts tracking its ticker first, since an untracked ticker has no price.
    With Massive the price arrives on a later poll, so the ticker stays tracked
    after the "no price" rejection and a retry can fill. Any other rejection
    leaves tracking as it was.

    Raises ActionError or TradeError if the trade is rejected.
    """
    ticker = normalize_ticker(ticker)
    if not quantity > 0:
        raise ActionError("Quantity must be greater than 0")
    if side == "buy":
        await _ensure_tracked(source, ticker)
    price = cache.get_price(ticker)
    if price is None:
        raise ActionError(f"No price available for {ticker} yet")
    try:
        trade = execute_trade(conn, ticker, side, quantity, price)
    finally:
        await sync_tracking(conn, source, ticker)
    record_snapshot(conn, get_portfolio(conn, cache)["total_value"])
    return trade


def get_priced_watchlist(conn: sqlite3.Connection, cache: PriceCache) -> list[dict]:
    """Return watchlist entries with latest prices, null until a price is cached."""
    return [_price_entry(entry, cache) for entry in get_watchlist(conn)]


def _price_entry(entry: dict, cache: PriceCache) -> dict:
    update = cache.get(entry["ticker"])
    return {
        "ticker": entry["ticker"],
        "price": update.price if update else None,
        "open_price": update.open_price if update else None,
        "session_change_percent": round(update.session_change_percent, 2) if update else None,
        "added_at": entry["added_at"],
    }


async def add_watchlist_ticker(
    conn: sqlite3.Connection, source: MarketDataSource, ticker: str
) -> None:
    """Add a ticker and start tracking it. Raises ActionError if invalid or duplicate."""
    ticker = normalize_ticker(ticker)
    if not add_to_watchlist(conn, ticker):
        raise ActionError(f"{ticker} is already on the watchlist")
    await sync_tracking(conn, source, ticker)


async def remove_watchlist_ticker(
    conn: sqlite3.Connection, source: MarketDataSource, ticker: str
) -> None:
    """Remove a ticker, tracking it still if held. Raises NotOnWatchlistError if absent."""
    ticker = ticker.upper()
    if not remove_from_watchlist(conn, ticker):
        raise NotOnWatchlistError(f"{ticker} is not on the watchlist")
    await sync_tracking(conn, source, ticker)
