"""Tests for the portfolio endpoints."""

import pytest


def trade(client, ticker, quantity, side):
    return client.post(
        "/api/portfolio/trade", json={"ticker": ticker, "quantity": quantity, "side": side}
    )


def test_fresh_portfolio(client):
    assert client.get("/api/portfolio").json() == {
        "cash_balance": 10000.0,
        "total_value": 10000.0,
        "unrealized_pnl": 0.0,
        "positions": [],
    }


def test_buy_returns_trade_and_portfolio(buy):
    body = buy("AAPL", 10)
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"
    assert body["trade"]["quantity"] == 10
    assert body["trade"]["price"] == 190.0
    assert body["trade"]["executed_at"].endswith("Z")
    assert body["trade"]["id"]
    assert body["portfolio"]["cash_balance"] == 8100.0
    assert body["portfolio"]["total_value"] == 10000.0


def test_position_valued_at_latest_price(client, buy, cache):
    buy("AAPL", 10)
    cache.update("AAPL", 191.9)

    body = client.get("/api/portfolio").json()

    assert body["positions"] == [
        {
            "ticker": "AAPL",
            "quantity": 10,
            "avg_cost": 190.0,
            "current_price": 191.9,
            "market_value": 1919.0,
            "unrealized_pnl": 19.0,
            "pnl_percent": 1.0,
        }
    ]
    assert body["unrealized_pnl"] == 19.0
    assert body["total_value"] == 10019.0


def test_second_buy_averages_cost(client, buy, cache):
    buy("AAPL", 10)
    cache.update("AAPL", 200.0)
    buy("AAPL", 10)
    assert client.get("/api/portfolio").json()["positions"][0]["avg_cost"] == 195.0


def test_fractional_shares(client, buy):
    buy("AAPL", 0.5)
    assert client.get("/api/portfolio").json()["positions"][0]["quantity"] == 0.5


def test_partial_sell_at_a_loss_keeps_avg_cost(client, buy, cache):
    buy("AAPL", 10)
    cache.update("AAPL", 171.0)

    response = trade(client, "AAPL", 4, "sell")

    assert response.status_code == 200
    portfolio = response.json()["portfolio"]
    assert portfolio["cash_balance"] == 8784.0
    assert portfolio["positions"][0]["quantity"] == 6
    assert portfolio["positions"][0]["avg_cost"] == 190.0
    assert portfolio["positions"][0]["unrealized_pnl"] == -114.0
    assert portfolio["positions"][0]["pnl_percent"] == -10.0


def test_selling_everything_closes_the_position(client, buy):
    buy("AAPL", 10)
    assert trade(client, "AAPL", 10, "sell").json()["portfolio"]["positions"] == []


def test_lowercase_ticker_is_normalized(client):
    assert trade(client, "aapl", 1, "buy").json()["trade"]["ticker"] == "AAPL"


def test_position_without_cached_price_is_valued_at_cost(client, buy, cache):
    buy("AAPL", 10)
    cache.remove("AAPL")

    body = client.get("/api/portfolio").json()

    position = body["positions"][0]
    assert position["current_price"] is None
    assert position["market_value"] == 1900.0
    assert position["unrealized_pnl"] == 0.0
    assert body["total_value"] == 10000.0


def test_insufficient_cash_is_rejected(client):
    response = trade(client, "AAPL", 1000, "buy")
    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient cash"}
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_selling_more_than_owned_is_rejected(client, buy):
    buy("AAPL", 1)
    response = trade(client, "AAPL", 2, "sell")
    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient shares"}
    assert client.get("/api/portfolio").json()["positions"][0]["quantity"] == 1


@pytest.mark.parametrize("ticker", ["", "TOOLONG", "AB1", "A.B", "AAPL\n"])
def test_invalid_ticker_is_rejected(client, ticker):
    response = trade(client, ticker, 1, "buy")
    assert response.status_code == 400
    assert "Invalid ticker" in response.json()["detail"]


@pytest.mark.parametrize("quantity", [0, -1])
def test_non_positive_quantity_is_rejected(client, quantity):
    response = trade(client, "AAPL", quantity, "buy")
    assert response.status_code == 400
    assert response.json() == {"detail": "Quantity must be greater than 0"}


def test_nan_quantity_is_rejected(client):
    response = client.post(
        "/api/portfolio/trade",
        content='{"ticker": "AAPL", "quantity": NaN, "side": "buy"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert client.get("/api/portfolio").json()["positions"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"ticker": "AAPL", "quantity": 1, "side": "short"},
        {"ticker": "AAPL", "side": "buy"},
        {"quantity": 1, "side": "buy"},
    ],
)
def test_schema_errors_are_422(client, body):
    assert client.post("/api/portfolio/trade", json=body).status_code == 422


def test_buy_without_a_price_is_rejected(client, source):
    del source.prices["PYPL"]
    response = trade(client, "PYPL", 1, "buy")
    assert response.status_code == 400
    assert response.json() == {"detail": "No price available for PYPL yet"}


def test_buy_retry_fills_once_the_price_arrives(client, source, cache):
    del source.prices["PYPL"]
    trade(client, "PYPL", 1, "buy")

    assert "PYPL" in source.get_tickers()
    cache.update("PYPL", 60.0)

    assert trade(client, "PYPL", 1, "buy").status_code == 200


def test_buying_an_untracked_ticker_starts_tracking(client, buy, source):
    assert "PYPL" not in source.get_tickers()
    assert buy("PYPL", 1)["trade"]["price"] == 60.0
    assert "PYPL" in source.get_tickers()


def test_rejected_buy_does_not_leave_ticker_tracked(client, source, cache):
    assert trade(client, "PYPL", 1000, "buy").status_code == 400
    assert "PYPL" not in source.get_tickers()
    assert "PYPL" not in cache


def test_buying_a_tracked_ticker_does_not_touch_its_price_feed(client, cache):
    cache.update("AAPL", 195.0)
    version = cache.version
    trade(client, "AAPL", 1, "buy")
    assert cache.version == version


def test_selling_to_zero_stops_tracking_unwatched_ticker(client, buy, source, cache):
    buy("PYPL", 1)
    trade(client, "PYPL", 1, "sell")
    assert "PYPL" not in source.get_tickers()
    assert "PYPL" not in cache


def test_selling_to_zero_keeps_tracking_watched_ticker(client, buy, source):
    buy("AAPL", 1)
    trade(client, "AAPL", 1, "sell")
    assert "AAPL" in source.get_tickers()


def test_each_trade_records_a_snapshot(client, buy, cache):
    before = len(client.get("/api/portfolio/history").json())
    buy("AAPL", 10)
    cache.update("AAPL", 200.0)
    trade(client, "AAPL", 5, "sell")

    history = client.get("/api/portfolio/history").json()

    assert len(history) == before + 2
    assert history[-1]["total_value"] == 10100.0
    assert set(history[-1]) == {"total_value", "recorded_at"}


def test_rejected_trade_records_no_snapshot(client):
    before = len(client.get("/api/portfolio/history").json())
    trade(client, "AAPL", 1000, "buy")
    assert len(client.get("/api/portfolio/history").json()) == before
