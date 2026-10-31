"""Cash, positions, trades and portfolio snapshots."""

import sqlite3
from uuid import uuid4

from .connection import USER_ID, transaction, utc_now

# Absorbs float dust so that selling a whole position closes it exactly.
QUANTITY_EPSILON = 1e-9


class TradeError(ValueError):
    """A trade failed validation; the message is safe to show to the user."""


def get_cash(conn: sqlite3.Connection) -> float:
    """Return the user's cash balance."""
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))
    return row.fetchone()["cash_balance"]


def get_positions(conn: sqlite3.Connection) -> list[dict]:
    """Return all open positions, ordered by ticker."""
    rows = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? ORDER BY ticker",
        (USER_ID,),
    )
    return [dict(row) for row in rows]


def get_position(conn: sqlite3.Connection, ticker: str) -> dict | None:
    """Return the open position in `ticker`, or None."""
    row = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? AND ticker = ?",
        (USER_ID, ticker),
    ).fetchone()
    return dict(row) if row else None


def execute_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float
) -> dict:
    """Atomically apply a fill to cash and positions and log it.

    Raises TradeError for insufficient cash or shares, leaving the database unchanged.
    Returns the trade as stored.
    """
    with transaction(conn):
        if side == "buy":
            _apply_buy(conn, ticker, quantity, price)
        else:
            _apply_sell(conn, ticker, quantity, price)
        return _log_trade(conn, ticker, side, quantity, price)


def _apply_buy(conn: sqlite3.Connection, ticker: str, quantity: float, price: float) -> None:
    cost = quantity * price
    if cost > get_cash(conn):
        raise TradeError("Insufficient cash")
    position = get_position(conn, ticker)
    if position:
        held = position["quantity"]
        new_quantity = held + quantity
        avg_cost = (held * position["avg_cost"] + cost) / new_quantity
    else:
        new_quantity, avg_cost = quantity, price
    conn.execute(
        "INSERT INTO positions (user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, ticker) DO UPDATE SET "
        "quantity = excluded.quantity, avg_cost = excluded.avg_cost, "
        "updated_at = excluded.updated_at",
        (USER_ID, ticker, new_quantity, avg_cost, utc_now()),
    )
    _adjust_cash(conn, -cost)


def _apply_sell(conn: sqlite3.Connection, ticker: str, quantity: float, price: float) -> None:
    position = get_position(conn, ticker)
    if not position or quantity > position["quantity"] + QUANTITY_EPSILON:
        raise TradeError("Insufficient shares")
    remaining = position["quantity"] - quantity
    if remaining > QUANTITY_EPSILON:
        conn.execute(
            "UPDATE positions SET quantity = ?, updated_at = ? WHERE user_id = ? AND ticker = ?",
            (remaining, utc_now(), USER_ID, ticker),
        )
    else:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker)
        )
    _adjust_cash(conn, quantity * price)


def _adjust_cash(conn: sqlite3.Connection, delta: float) -> None:
    conn.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?", (delta, USER_ID)
    )


def _log_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float
) -> dict:
    trade = {
        "id": str(uuid4()),
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": utc_now(),
    }
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (:id, :user_id, :ticker, :side, :quantity, :price, :executed_at)",
        {**trade, "user_id": USER_ID},
    )
    return trade


def record_snapshot(conn: sqlite3.Connection, total_value: float) -> None:
    """Append a portfolio value snapshot."""
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid4()), USER_ID, total_value, utc_now()),
    )


def get_snapshots(conn: sqlite3.Connection) -> list[dict]:
    """Return all snapshots, oldest first.

    Ordered by rowid because timestamps have one-second resolution and the table
    is append-only.
    """
    rows = conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ? ORDER BY rowid",
        (USER_ID,),
    )
    return [dict(row) for row in rows]
