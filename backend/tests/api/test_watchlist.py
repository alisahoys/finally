"""Tests for the watchlist endpoints."""

from db import DEFAULT_TICKERS


def tickers(response):
    return [entry["ticker"] for entry in response.json()]


def test_default_watchlist(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    assert tickers(response) == DEFAULT_TICKERS


def test_entry_shape(client, cache):
    cache.update("AAPL", 192.0)

    entry = client.get("/api/watchlist").json()[0]

    assert entry["ticker"] == "AAPL"
    assert entry["price"] == 192.0
    assert entry["open_price"] == 190.0
    assert entry["session_change_percent"] == 1.05
    assert entry["added_at"]


def test_add_returns_updated_list_and_starts_tracking(client, source):
    response = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert response.status_code == 200
    assert tickers(response) == [*DEFAULT_TICKERS, "PYPL"]
    assert response.json()[-1]["price"] == 60.0
    assert "PYPL" in source.get_tickers()


def test_added_ticker_without_price_has_null_fields(client, source):
    del source.prices["PYPL"]
    entry = client.post("/api/watchlist", json={"ticker": "PYPL"}).json()[-1]
    assert entry["price"] is None
    assert entry["open_price"] is None
    assert entry["session_change_percent"] is None


def test_duplicate_add_is_rejected(client):
    response = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert response.status_code == 400
    assert response.json() == {"detail": "AAPL is already on the watchlist"}


def test_invalid_ticker_is_rejected(client):
    response = client.post("/api/watchlist", json={"ticker": "NOT VALID"})
    assert response.status_code == 400
    assert tickers(client.get("/api/watchlist")) == DEFAULT_TICKERS


def test_missing_ticker_field_is_422(client):
    assert client.post("/api/watchlist", json={}).status_code == 422


def test_remove_returns_updated_list_and_stops_tracking(client, source, cache):
    response = client.delete("/api/watchlist/AAPL")
    assert response.status_code == 200
    assert "AAPL" not in tickers(response)
    assert "AAPL" not in source.get_tickers()
    assert "AAPL" not in cache


def test_remove_normalizes_case(client):
    assert client.delete("/api/watchlist/aapl").status_code == 200


def test_remove_absent_ticker_is_404(client):
    response = client.delete("/api/watchlist/PYPL")
    assert response.status_code == 404
    assert response.json() == {"detail": "PYPL is not on the watchlist"}


def test_remove_held_ticker_hides_it_but_keeps_tracking(client, buy, source):
    buy("AAPL", 1)

    assert "AAPL" not in tickers(client.delete("/api/watchlist/AAPL"))

    assert "AAPL" in source.get_tickers()
    position = client.get("/api/portfolio").json()["positions"][0]
    assert position["current_price"] == 190.0


def test_readding_a_ticker_gets_a_fresh_open_price(client, source, cache):
    cache.update("AAPL", 250.0)
    client.delete("/api/watchlist/AAPL")
    source.prices["AAPL"] = 260.0

    entry = client.post("/api/watchlist", json={"ticker": "AAPL"}).json()[-1]

    assert entry["open_price"] == 260.0
    assert entry["session_change_percent"] == 0.0
