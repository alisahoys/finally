"""Watchlist storage and the set of tickers the market data source must track."""

import sqlite3

from .connection import USER_ID, utc_now


def get_watchlist(conn: sqlite3.Connection) -> list[dict]:
    """Return watchlist entries in the order they were added."""
    rows = conn.execute(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY rowid", (USER_ID,)
    )
    return [dict(row) for row in rows]


def add_to_watchlist(conn: sqlite3.Connection, ticker: str) -> bool:
    """Add a ticker. Returns False if it was already on the watchlist."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
        (USER_ID, ticker, utc_now()),
    )
    return cursor.rowcount == 1


def remove_from_watchlist(conn: sqlite3.Connection, ticker: str) -> bool:
    """Remove a ticker. Returns False if it was not on the watchlist."""
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, ticker)
    )
    return cursor.rowcount == 1


def get_tracked_tickers(conn: sqlite3.Connection) -> list[str]:
    """Return the union of watchlist and held position tickers, sorted."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = :user "
        "UNION SELECT ticker FROM positions WHERE user_id = :user "
        "ORDER BY ticker",
        {"user": USER_ID},
    )
    return [row["ticker"] for row in rows]
