"""Tests for database creation, seeding and connection behaviour."""

import sqlite3
from pathlib import Path

import pytest

from db import (
    DB_PATH,
    DEFAULT_CASH,
    DEFAULT_TICKERS,
    connect,
    get_cash,
    get_watchlist,
    init_db,
    remove_from_watchlist,
    transaction,
)

TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_db_path_is_in_top_level_db_directory():
    assert DB_PATH == Path(__file__).resolve().parents[3] / "db" / "finally.db"


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "test.db"
    init_db(path)
    assert path.exists()


def test_creates_all_tables(conn):
    assert table_names(conn) == TABLES


def test_seeds_default_user_and_watchlist(conn):
    assert get_cash(conn) == DEFAULT_CASH == 10000.0
    assert [entry["ticker"] for entry in get_watchlist(conn)] == DEFAULT_TICKERS
    assert len(DEFAULT_TICKERS) == 10


def test_reinit_preserves_data(db_path, conn):
    remove_from_watchlist(conn, "AAPL")
    conn.execute("UPDATE users_profile SET cash_balance = 5.0")
    init_db(db_path)
    assert get_cash(conn) == 5.0
    assert "AAPL" not in [entry["ticker"] for entry in get_watchlist(conn)]


def test_reinit_does_not_restore_an_emptied_watchlist(db_path, conn):
    for ticker in DEFAULT_TICKERS:
        remove_from_watchlist(conn, ticker)
    init_db(db_path)
    assert get_watchlist(conn) == []


def test_recreates_missing_table_and_seeds_it(db_path, conn):
    conn.execute("DROP TABLE watchlist")
    conn.execute("DROP TABLE trades")
    init_db(db_path)
    assert table_names(conn) == TABLES
    assert len(get_watchlist(conn)) == 10


def test_restores_missing_user_profile(db_path, conn):
    conn.execute("DELETE FROM users_profile")
    init_db(db_path)
    assert get_cash(conn) == DEFAULT_CASH


def test_rows_default_to_default_user(conn):
    conn.execute(
        "INSERT INTO positions (ticker, quantity, avg_cost, updated_at) VALUES ('X', 1, 1, 'now')"
    )
    assert conn.execute("SELECT user_id FROM positions").fetchone()["user_id"] == "default"


def test_position_quantity_must_be_positive(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO positions (ticker, quantity, avg_cost, updated_at) "
            "VALUES ('X', 0, 1, 'now')"
        )


def test_transaction_commits_on_success(db_path, conn):
    with transaction(conn):
        conn.execute("UPDATE users_profile SET cash_balance = 1.0")
    other = connect(db_path)
    assert get_cash(other) == 1.0
    other.close()


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("UPDATE users_profile SET cash_balance = 1.0")
            raise RuntimeError
    assert get_cash(conn) == DEFAULT_CASH
