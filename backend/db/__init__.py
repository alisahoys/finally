"""SQLite persistence for FinAlly.

Call `init_db()` once at startup, then open a connection with `connect()` per
request or task and pass it to the functions below.
"""

from .chat import add_chat_message, get_recent_chat_messages
from .connection import DB_PATH, connect, transaction
from .portfolio import (
    TradeError,
    execute_trade,
    get_cash,
    get_position,
    get_positions,
    get_snapshots,
    record_snapshot,
)
from .seed import DEFAULT_CASH, DEFAULT_TICKERS, init_db
from .watchlist import (
    add_to_watchlist,
    get_tracked_tickers,
    get_watchlist,
    remove_from_watchlist,
)

__all__ = [
    "DB_PATH",
    "DEFAULT_CASH",
    "DEFAULT_TICKERS",
    "TradeError",
    "add_chat_message",
    "add_to_watchlist",
    "connect",
    "execute_trade",
    "get_cash",
    "get_position",
    "get_positions",
    "get_recent_chat_messages",
    "get_snapshots",
    "get_tracked_tickers",
    "get_watchlist",
    "init_db",
    "record_snapshot",
    "remove_from_watchlist",
    "transaction",
]
