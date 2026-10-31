"""SQLite connections and transactions.

Connections run in autocommit mode: each statement commits on its own, and
multi-statement work wraps itself in `transaction`.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "finally.db"
USER_ID = "default"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a connection whose rows support access by column name.

    `check_same_thread` is off so a connection can be opened in one worker thread
    and used in another. Use one connection per request; do not share them.
    """
    conn = sqlite3.connect(path, autocommit=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run the block atomically, taking the write lock up front.

    Taking the lock before any read keeps read-then-write sequences, such as
    checking cash and then spending it, safe across connections.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
