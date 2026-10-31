"""Portfolio routes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Cache, Conn, Source
from app.services import get_portfolio, place_trade
from db import get_snapshots

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: Literal["buy", "sell"]


@router.get("")
def read_portfolio(conn: Conn, cache: Cache) -> dict:
    """Return positions, cash balance, total value and unrealized P&L."""
    return get_portfolio(conn, cache)


@router.post("/trade")
async def trade(body: TradeRequest, conn: Conn, cache: Cache, source: Source) -> dict:
    """Execute a market order and return it with the updated portfolio."""
    executed = await place_trade(conn, cache, source, body.ticker, body.side, body.quantity)
    return {"trade": executed, "portfolio": get_portfolio(conn, cache)}


@router.get("/history")
def read_history(conn: Conn) -> list[dict]:
    """Return all portfolio value snapshots, oldest first."""
    return get_snapshots(conn)
