"""FastAPI application: startup, shutdown and route wiring."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, closing, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import portfolio, watchlist
from app.market import (
    MarketDataSource,
    PriceCache,
    create_market_data_source,
    create_stream_router,
)
from app.services import ActionError, NotOnWatchlistError, get_portfolio
from db import DB_PATH, TradeError, connect, get_tracked_tickers, init_db, record_snapshot

SNAPSHOT_INTERVAL = 30.0


async def snapshot_loop(db_path: Path, cache: PriceCache, interval: float) -> None:
    """Record the portfolio value now and then every `interval` seconds."""
    while True:
        with closing(connect(db_path)) as conn:
            record_snapshot(conn, get_portfolio(conn, cache)["total_value"])
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the database, then run market data and snapshots until shutdown."""
    db_path, cache, source = app.state.db_path, app.state.cache, app.state.source
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        await source.start(get_tracked_tickers(conn))
    snapshots = asyncio.create_task(snapshot_loop(db_path, cache, SNAPSHOT_INTERVAL))
    yield
    snapshots.cancel()
    with suppress(asyncio.CancelledError):
        await snapshots
    await source.stop()


def _bad_request(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _not_found(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def create_app(
    db_path: Path = DB_PATH,
    source_factory: Callable[[PriceCache], MarketDataSource] = create_market_data_source,
) -> FastAPI:
    """Build the application; nothing is started until the lifespan runs."""
    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.db_path = db_path
    app.state.cache = PriceCache()
    app.state.source = source_factory(app.state.cache)

    app.add_exception_handler(TradeError, _bad_request)
    app.add_exception_handler(ActionError, _bad_request)
    app.add_exception_handler(NotOnWatchlistError, _not_found)

    app.include_router(create_stream_router(app.state.cache))
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        """Report that the server is up."""
        return {"status": "ok"}

    return app


app = create_app()
