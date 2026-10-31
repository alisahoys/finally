"""Watchlist routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Cache, Conn, Source
from app.services import add_watchlist_ticker, get_priced_watchlist, remove_watchlist_ticker

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistRequest(BaseModel):
    ticker: str


@router.get("")
def read_watchlist(conn: Conn, cache: Cache) -> list[dict]:
    """Return watchlist tickers with latest prices."""
    return get_priced_watchlist(conn, cache)


@router.post("")
async def add_ticker(
    body: WatchlistRequest, conn: Conn, cache: Cache, source: Source
) -> list[dict]:
    """Add a ticker and return the updated watchlist."""
    await add_watchlist_ticker(conn, source, body.ticker)
    return get_priced_watchlist(conn, cache)


@router.delete("/{ticker}")
async def remove_ticker(ticker: str, conn: Conn, cache: Cache, source: Source) -> list[dict]:
    """Remove a ticker and return the updated watchlist."""
    await remove_watchlist_ticker(conn, source, ticker)
    return get_priced_watchlist(conn, cache)
