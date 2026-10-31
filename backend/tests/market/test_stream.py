"""Tests for the SSE streaming endpoint."""

import json

from app.market import PriceCache, create_stream_router
from app.market.stream import _generate_events


class FakeRequest:
    """Request that reports a disconnect after `checks` is_disconnected calls."""

    client = None

    def __init__(self, checks: int):
        self._checks = checks

    async def is_disconnected(self) -> bool:
        self._checks -= 1
        return self._checks < 0


def _bound_cache(router) -> PriceCache:
    """Return the cache captured by the router's first /prices route."""
    return router.routes[0].endpoint.__closure__[0].cell_contents


def test_each_router_streams_its_own_cache():
    first, second = PriceCache(), PriceCache()
    create_stream_router(first)
    router = create_stream_router(second)
    assert len(router.routes) == 1
    assert _bound_cache(router) is second


async def test_stream_starts_with_retry_then_sends_all_tickers():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("GOOGL", 175.0)

    events = [e async for e in _generate_events(cache, FakeRequest(checks=1), interval=0)]

    assert events[0] == "retry: 1000\n\n"
    payload = json.loads(events[1].removeprefix("data: "))
    assert set(payload) == {"AAPL", "GOOGL"}
    assert payload["AAPL"]["open_price"] == 190.0
    assert payload["AAPL"]["session_change_percent"] == 0.0


async def test_stream_skips_event_when_version_unchanged():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    events = [e async for e in _generate_events(cache, FakeRequest(checks=3), interval=0)]

    assert len(events) == 2
