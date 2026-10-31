"""The chat flow: build the prompt, get a reply, execute its actions, store the exchange."""

import json
import sqlite3

from app.llm import LLMReply, TradeIntent, WatchlistChange, get_reply
from app.market import MarketDataSource, PriceCache
from app.services import (
    ActionError,
    add_watchlist_ticker,
    get_portfolio,
    get_priced_watchlist,
    place_trade,
    remove_watchlist_ticker,
)
from db import TradeError, add_chat_message, get_recent_chat_messages

HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant for a simulated portfolio.

- Analyze portfolio composition, risk concentration and P&L.
- Suggest trades with reasoning.
- Execute trades when the user asks or agrees, by listing them in `trades`. This includes \
broad requests like "rebalance my portfolio", where you may buy or sell any position, not \
only those named.
- Manage the watchlist proactively through `watchlist_changes`.
- Be concise and data-driven.
- Phrase trades and watchlist changes as intents ("Buying 5 NVDA"), never as completed \
results ("Purchase successful"). The backend executes them after you reply.
- Earlier assistant messages may end with "[Action results: ...]". Those are the real \
outcomes of your actions, added by the backend. Do not write them yourself.
- Always respond with valid JSON matching the requested schema."""


def build_messages(conn: sqlite3.Connection, cache: PriceCache, user_message: str) -> list[dict]:
    """Return the system prompt with live context, recent history and the new message."""
    return [
        {"role": "system", "content": _system_content(conn, cache)},
        *map(_history_message, get_recent_chat_messages(conn, HISTORY_LIMIT)),
        {"role": "user", "content": user_message},
    ]


def _system_content(conn: sqlite3.Connection, cache: PriceCache) -> str:
    portfolio = json.dumps(get_portfolio(conn, cache))
    watchlist = json.dumps(get_priced_watchlist(conn, cache))
    return f"{SYSTEM_PROMPT}\n\nCurrent portfolio:\n{portfolio}\n\nWatchlist:\n{watchlist}"


def _history_message(message: dict) -> dict:
    content = message["content"]
    if message["actions"]:
        content += f"\n[Action results: {json.dumps(message['actions'])}]"
    return {"role": message["role"], "content": content}


async def _run_trade(
    conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, intent: TradeIntent
) -> dict:
    action = {
        "type": "trade",
        "ticker": intent.ticker.upper(),
        "side": intent.side,
        "quantity": intent.quantity,
    }
    try:
        trade = await place_trade(conn, cache, source, intent.ticker, intent.side, intent.quantity)
    except (ActionError, TradeError) as error:
        return {**action, "status": "error", "error": str(error)}
    return {**action, "status": "ok", "price": trade["price"]}


async def _run_watchlist_change(
    conn: sqlite3.Connection, source: MarketDataSource, change: WatchlistChange
) -> dict:
    action = {"type": "watchlist", "ticker": change.ticker.upper(), "action": change.action}
    apply = add_watchlist_ticker if change.action == "add" else remove_watchlist_ticker
    try:
        await apply(conn, source, change.ticker)
    except ActionError as error:
        return {**action, "status": "error", "error": str(error)}
    return {**action, "status": "ok"}


async def execute_actions(
    conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, reply: LLMReply
) -> list[dict]:
    """Run each action through normal validation; a failure is reported, not raised."""
    trades = [await _run_trade(conn, cache, source, trade) for trade in reply.trades]
    changes = [
        await _run_watchlist_change(conn, source, change) for change in reply.watchlist_changes
    ]
    return trades + changes


async def handle_chat(
    conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, user_message: str
) -> dict:
    """Answer a message and return it in the POST /api/chat shape."""
    reply = await get_reply(build_messages(conn, cache, user_message))
    actions = await execute_actions(conn, cache, source, reply)
    add_chat_message(conn, "user", user_message)
    add_chat_message(conn, "assistant", reply.message, actions)
    return {"message": reply.message, "actions": actions}
