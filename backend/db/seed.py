"""Database creation and default data."""

from pathlib import Path

from .connection import DB_PATH, USER_ID, connect, transaction, utc_now

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def init_db(path: Path = DB_PATH) -> None:
    """Create any missing tables and seed defaults.

    Safe on every startup. The watchlist is seeded only when its table is new, so
    a user who removed every ticker does not get the defaults back on restart.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        with transaction(conn):
            seed_watchlist = not _table_exists(conn, "watchlist")
            conn.executescript(SCHEMA_PATH.read_text())
            now = utc_now()
            conn.execute(
                "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                (USER_ID, DEFAULT_CASH, now),
            )
            if seed_watchlist:
                conn.executemany(
                    "INSERT INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
                    [(USER_ID, ticker, now) for ticker in DEFAULT_TICKERS],
                )
    finally:
        conn.close()


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None
