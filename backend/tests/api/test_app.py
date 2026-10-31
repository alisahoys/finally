"""Tests for application startup, shutdown and background tasks."""

import asyncio

from fastapi.testclient import TestClient

from app.main import create_app, snapshot_loop
from app.market import PriceCache
from db import DEFAULT_TICKERS, connect, get_snapshots, init_db

from .conftest import FakeSource


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_serves_static_frontend_without_shadowing_the_api(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>FinAlly</h1>")
    app = create_app(db_path=tmp_path / "test.db", source_factory=FakeSource, static_dir=static)
    with TestClient(app) as client:
        assert "FinAlly" in client.get("/").text
        assert client.get("/api/health").json() == {"status": "ok"}


def test_stream_route_is_mounted(app):
    assert "/api/stream/prices" in {route.path for route in app.routes}


def test_startup_tracks_watchlist_and_records_first_snapshot(client, source):
    assert sorted(source.started_with) == sorted(DEFAULT_TICKERS)
    assert client.get("/api/portfolio/history").json()[0]["total_value"] == 10000.0


def test_shutdown_stops_the_source(app, source):
    with TestClient(app):
        assert not source.stopped
    assert source.stopped


def test_restart_keeps_state_and_tracks_held_tickers(tmp_path):
    path = tmp_path / "test.db"
    with TestClient(create_app(path, FakeSource)) as client:
        client.post(
            "/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"}
        )

    restarted = create_app(path, FakeSource)
    with TestClient(restarted) as client:
        assert "PYPL" in restarted.state.source.started_with
        assert client.get("/api/portfolio").json()["cash_balance"] == 9940.0


async def test_snapshot_loop_records_on_each_interval(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    task = asyncio.create_task(snapshot_loop(path, PriceCache(), interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()

    conn = connect(path)
    assert len(get_snapshots(conn)) >= 2
    conn.close()


def test_trading_with_the_real_simulator(tmp_path, monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(create_app(tmp_path / "test.db")) as client:
        watchlist = client.get("/api/watchlist").json()
        assert all(entry["price"] > 0 for entry in watchlist)

        response = client.post(
            "/api/portfolio/trade", json={"ticker": "ZZZZ", "quantity": 0.001, "side": "buy"}
        )

        assert response.status_code == 200
        assert response.json()["portfolio"]["positions"][0]["ticker"] == "ZZZZ"

