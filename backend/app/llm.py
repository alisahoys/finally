"""LLM access: the structured reply schema, the OpenRouter call and mock mode."""

import logging
import os
import re
from typing import Literal

from litellm import acompletion
from pydantic import BaseModel, Field

DEFAULT_MODEL = "openrouter/nvidia/nemotron-3.5-super-vl:free"
TIMEOUT_SECONDS = 60
FALLBACK_MESSAGE = "Sorry, I couldn't reach the AI model just now. Please try again."

MOCK_TRADE = re.compile(r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+([a-z]+)\b", re.IGNORECASE)
MOCK_WATCH = re.compile(r"\bwatch\s+([a-z]+)\b", re.IGNORECASE)

logger = logging.getLogger(__name__)


class TradeIntent(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LLMReply(BaseModel):
    """The structured response requested from the model."""

    message: str
    trades: list[TradeIntent] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)


async def get_reply(messages: list[dict]) -> LLMReply:
    """Return the assistant's reply to `messages`, whose last entry is the user's message.

    Any failure is logged and becomes an apology with no actions, so a bad model
    response can never execute anything.
    """
    if os.environ.get("LLM_MOCK", "").lower() == "true":
        return mock_reply(messages[-1]["content"])
    try:
        return await _call_model(messages)
    except Exception:
        logger.exception("LLM call failed")
        return LLMReply(message=FALLBACK_MESSAGE)


async def _call_model(messages: list[dict]) -> LLMReply:
    response = await acompletion(
        model=os.environ.get("LLM_MODEL") or DEFAULT_MODEL,
        messages=messages,
        response_format=LLMReply,
        timeout=TIMEOUT_SECONDS,
    )
    return LLMReply.model_validate_json(response.choices[0].message.content)


def mock_reply(message: str) -> LLMReply:
    """Return the deterministic reply used for tests and development without a key."""
    if match := MOCK_TRADE.search(message):
        verb, quantity, ticker = match[1].lower(), match[2], match[3].upper()
        return LLMReply(
            message=f"Mock: {verb}ing {quantity} {ticker}.",
            trades=[TradeIntent(ticker=ticker, side=verb, quantity=float(quantity))],
        )
    if match := MOCK_WATCH.search(message):
        ticker = match[1].upper()
        return LLMReply(
            message=f"Mock: adding {ticker} to your watchlist.",
            watchlist_changes=[WatchlistChange(ticker=ticker, action="add")],
        )
    return LLMReply(message="Mock: I received your message.")
