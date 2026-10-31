"""Tests for the watchlist and tracked tickers."""

from db import (
    DEFAULT_TICKERS,
    add_to_watchlist,
    execute_trade,
    get_tracked_tickers,
    get_watchlist,
    remove_from_watchlist,
)


def tickers(conn):
    return [entry["ticker"] for entry in get_watchlist(conn)]


def test_add_appends_to_the_end(conn):
    assert add_to_watchlist(conn, "PYPL") is True
    assert tickers(conn)[-1] == "PYPL"


def test_add_duplicate_returns_false(conn):
    assert add_to_watchlist(conn, "AAPL") is False
    assert tickers(conn) == DEFAULT_TICKERS


def test_remove(conn):
    assert remove_from_watchlist(conn, "AAPL") is True
    assert "AAPL" not in tickers(conn)


def test_remove_missing_returns_false(conn):
    assert remove_from_watchlist(conn, "PYPL") is False


def test_entries_have_added_at(conn):
    assert set(get_watchlist(conn)[0]) == {"ticker", "added_at"}


def test_tracked_is_the_sorted_watchlist_with_no_positions(conn):
    assert get_tracked_tickers(conn) == sorted(DEFAULT_TICKERS)


def test_tracked_includes_held_ticker_not_on_watchlist(conn):
    execute_trade(conn, "PYPL", "buy", 1, 100.0)
    assert "PYPL" in get_tracked_tickers(conn)


def test_tracked_keeps_held_ticker_removed_from_watchlist(conn):
    execute_trade(conn, "AAPL", "buy", 1, 100.0)
    remove_from_watchlist(conn, "AAPL")
    assert "AAPL" in get_tracked_tickers(conn)


def test_tracked_drops_ticker_with_no_watch_and_no_position(conn):
    execute_trade(conn, "AAPL", "buy", 1, 100.0)
    remove_from_watchlist(conn, "AAPL")
    execute_trade(conn, "AAPL", "sell", 1, 100.0)
    assert "AAPL" not in get_tracked_tickers(conn)


def test_tracked_has_no_duplicates(conn):
    execute_trade(conn, "AAPL", "buy", 1, 100.0)
    assert get_tracked_tickers(conn).count("AAPL") == 1
