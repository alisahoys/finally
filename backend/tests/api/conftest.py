"""API test fixtures: a real app and database, with a deterministic price source."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import MarketDataSource, PriceCache

DEFAULT_PRICES = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 400.0,
    "AMZN": 180.0,
    "TSLA": 200.0,
    "NVDA": 800.0,
    "META": 500.0,
    "JPM": 190.0,
    "V": 280.0,
    "NFLX": 600.0,
    "PYPL": 60.0,
}


class FakeSource(MarketDataSource):
    """Publishes one fixed price per ticker. Tickers missing from `prices` stay unpriced,
    like a just-added ticker under Massive."""

    def __init__(self, cache: PriceCache):
        self.cache = cache
        self.prices = dict(DEFAULT_PRICES)
        self.tickers: list[str] = []
        self.started_with: list[str] | None = None
        self.stopped = False

    async def start(self, tickers: list[str]) -> None:
        self.started_with = list(tickers)
        for ticker in tickers:
            await self.add_ticker(ticker)

    async def stop(self) -> None:
        self.stopped = True

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self.tickers:
            self.tickers.append(ticker)
        if ticker in self.prices:
            self.cache.update(ticker, self.prices[ticker])

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            self.tickers.remove(ticker)
        self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=tmp_path / "test.db", source_factory=FakeSource)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cache(app) -> PriceCache:
    return app.state.cache


@pytest.fixture
def source(app) -> FakeSource:
    return app.state.source


@pytest.fixture
def buy(client):
    """Buy shares through the API and assert that it succeeded."""

    def _buy(ticker: str, quantity: float) -> dict:
        body = {"ticker": ticker, "quantity": quantity, "side": "buy"}
        response = client.post("/api/portfolio/trade", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    return _buy
