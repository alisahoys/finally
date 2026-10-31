"""Tests for trades, positions and snapshots."""

import re
import sqlite3
import threading
from uuid import UUID

import pytest

from db import (
    TradeError,
    connect,
    execute_trade,
    get_cash,
    get_position,
    get_positions,
    get_snapshots,
    record_snapshot,
)

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def trade_count(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]


class TestBuy:
    def test_opens_position_and_spends_cash(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        position = get_position(conn, "AAPL")
        assert position["quantity"] == 10
        assert position["avg_cost"] == 100.0
        assert get_cash(conn) == 9000.0

    def test_averages_cost_by_quantity(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        execute_trade(conn, "AAPL", "buy", 30, 200.0)
        position = get_position(conn, "AAPL")
        assert position["quantity"] == 40
        assert position["avg_cost"] == 175.0

    def test_can_spend_all_cash(self, conn):
        execute_trade(conn, "AAPL", "buy", 100, 100.0)
        assert get_cash(conn) == 0.0

    def test_supports_fractional_shares(self, conn):
        execute_trade(conn, "AAPL", "buy", 0.5, 100.0)
        assert get_position(conn, "AAPL")["quantity"] == 0.5
        assert get_cash(conn) == 9950.0

    def test_rejects_insufficient_cash(self, conn):
        with pytest.raises(TradeError, match="Insufficient cash"):
            execute_trade(conn, "AAPL", "buy", 101, 100.0)
        assert get_position(conn, "AAPL") is None
        assert get_cash(conn) == 10000.0
        assert trade_count(conn) == 0


class TestSell:
    def test_partial_sell_keeps_avg_cost(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        execute_trade(conn, "AAPL", "sell", 4, 150.0)
        position = get_position(conn, "AAPL")
        assert position["quantity"] == 6
        assert position["avg_cost"] == 100.0
        assert get_cash(conn) == 9600.0

    def test_selling_everything_deletes_the_position(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        execute_trade(conn, "AAPL", "sell", 10, 100.0)
        assert get_position(conn, "AAPL") is None
        assert get_cash(conn) == 10000.0

    def test_selling_at_a_loss_returns_less_cash(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        execute_trade(conn, "AAPL", "sell", 10, 80.0)
        assert get_cash(conn) == 9800.0

    def test_float_dust_does_not_leave_a_position_open(self, conn):
        for _ in range(3):
            execute_trade(conn, "AAPL", "buy", 0.1, 100.0)
        assert get_position(conn, "AAPL")["quantity"] != 0.3
        execute_trade(conn, "AAPL", "sell", 0.3, 100.0)
        assert get_position(conn, "AAPL") is None

    def test_rejects_selling_more_than_held(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        with pytest.raises(TradeError, match="Insufficient shares"):
            execute_trade(conn, "AAPL", "sell", 11, 100.0)
        assert get_position(conn, "AAPL")["quantity"] == 10
        assert get_cash(conn) == 9000.0
        assert trade_count(conn) == 1

    def test_rejects_selling_unheld_ticker(self, conn):
        with pytest.raises(TradeError, match="Insufficient shares"):
            execute_trade(conn, "AAPL", "sell", 1, 100.0)
        assert trade_count(conn) == 0


class TestTradeLog:
    def test_returns_the_stored_trade(self, conn):
        trade = execute_trade(conn, "AAPL", "buy", 2, 100.0)
        UUID(trade["id"])
        assert ISO_UTC.match(trade["executed_at"])
        stored = conn.execute(
            "SELECT id, ticker, side, quantity, price, executed_at FROM trades"
        ).fetchone()
        assert dict(stored) == trade

    def test_is_append_only_across_buys_and_sells(self, conn):
        execute_trade(conn, "AAPL", "buy", 2, 100.0)
        execute_trade(conn, "AAPL", "sell", 2, 110.0)
        sides = conn.execute("SELECT side FROM trades ORDER BY rowid").fetchall()
        assert [row["side"] for row in sides] == ["buy", "sell"]

    def test_failed_log_rolls_back_cash_and_position(self, conn):
        execute_trade(conn, "AAPL", "buy", 10, 100.0)
        with pytest.raises(sqlite3.IntegrityError):
            execute_trade(conn, "AAPL", "short", 5, 100.0)
        assert get_position(conn, "AAPL")["quantity"] == 10
        assert get_cash(conn) == 9000.0


def test_concurrent_buys_cannot_overspend(db_path):
    """Each trade alone is affordable; together only some of them are."""
    errors = []

    def buy():
        conn = connect(db_path)
        try:
            execute_trade(conn, "AAPL", "buy", 60, 100.0)
        except TradeError as error:
            errors.append(error)
        conn.close()

    threads = [threading.Thread(target=buy) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    conn = connect(db_path)
    assert len(errors) == 3
    assert get_cash(conn) == 4000.0
    conn.close()


def test_get_positions_is_sorted_by_ticker(conn):
    execute_trade(conn, "MSFT", "buy", 1, 100.0)
    execute_trade(conn, "AAPL", "buy", 1, 100.0)
    assert [position["ticker"] for position in get_positions(conn)] == ["AAPL", "MSFT"]


def test_snapshots_are_returned_oldest_first(conn):
    for value in (10000.0, 9000.0, 11000.0):
        record_snapshot(conn, value)
    snapshots = get_snapshots(conn)
    assert [snapshot["total_value"] for snapshot in snapshots] == [10000.0, 9000.0, 11000.0]
    assert set(snapshots[0]) == {"total_value", "recorded_at"}
    assert ISO_UTC.match(snapshots[0]["recorded_at"])
