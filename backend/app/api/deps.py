"""FastAPI dependencies for the shared application state."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app.market import MarketDataSource, PriceCache
from db import connect


def _get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _get_cache(request: Request) -> PriceCache:
    return request.app.state.cache


def _get_source(request: Request) -> MarketDataSource:
    return request.app.state.source


Conn = Annotated[sqlite3.Connection, Depends(_get_conn)]
Cache = Annotated[PriceCache, Depends(_get_cache)]
Source = Annotated[MarketDataSource, Depends(_get_source)]
