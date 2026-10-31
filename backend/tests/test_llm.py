"""Tests for the LLM reply schema, the model call and mock mode."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import llm
from app.llm import FALLBACK_MESSAGE, LLMReply, TradeIntent, WatchlistChange, get_reply, mock_reply

MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "hello"}]


def fake_completion(monkeypatch, content=None, error=None):
    """Replace the LiteLLM call and return the list of kwargs it receives."""
    calls = []

    async def _acompletion(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(llm, "acompletion", _acompletion)
    return calls


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.delenv("LLM_MODEL", raising=False)


class TestSchema:
    def test_full_reply(self):
        reply = LLMReply.model_validate_json(
            '{"message": "hi", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1.5}], '
            '"watchlist_changes": [{"ticker": "PYPL", "action": "remove"}]}'
        )
        assert reply.trades == [TradeIntent(ticker="AAPL", side="buy", quantity=1.5)]
        assert reply.watchlist_changes == [WatchlistChange(ticker="PYPL", action="remove")]

    def test_only_message_is_required(self):
        reply = LLMReply.model_validate_json('{"message": "hi"}')
        assert reply.trades == []
        assert reply.watchlist_changes == []

    @pytest.mark.parametrize(
        "payload",
        [
            "not json",
            "{}",
            '{"message": "hi", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}]}',
            '{"message": "hi", "trades": [{"ticker": "AAPL", "side": "buy"}]}',
            '{"message": "hi", "watchlist_changes": [{"ticker": "AAPL", "action": "pin"}]}',
        ],
    )
    def test_malformed_replies_are_rejected(self, payload):
        with pytest.raises(ValidationError):
            LLMReply.model_validate_json(payload)


class TestGetReply:
    async def test_parses_the_structured_response(self, monkeypatch):
        fake_completion(monkeypatch, '{"message": "hi"}')
        assert await get_reply(MESSAGES) == LLMReply(message="hi")

    async def test_requests_structured_output_from_the_default_model(self, monkeypatch):
        calls = fake_completion(monkeypatch, '{"message": "hi"}')
        await get_reply(MESSAGES)
        assert calls[0]["model"] == llm.DEFAULT_MODEL
        assert calls[0]["messages"] == MESSAGES
        assert calls[0]["response_format"] is LLMReply
        assert "extra_body" not in calls[0]

    async def test_default_model_is_free(self):
        assert llm.DEFAULT_MODEL.endswith(":free")

    async def test_model_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "openrouter/other/model:free")
        calls = fake_completion(monkeypatch, '{"message": "hi"}')
        await get_reply(MESSAGES)
        assert calls[0]["model"] == "openrouter/other/model:free"

    async def test_empty_model_setting_uses_the_default(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "")
        calls = fake_completion(monkeypatch, '{"message": "hi"}')
        await get_reply(MESSAGES)
        assert calls[0]["model"] == llm.DEFAULT_MODEL

    async def test_call_failure_becomes_an_apology(self, monkeypatch):
        fake_completion(monkeypatch, error=TimeoutError("slow"))
        assert await get_reply(MESSAGES) == LLMReply(message=FALLBACK_MESSAGE)

    @pytest.mark.parametrize("content", ["not json", '{"trades": []}', None])
    async def test_unparseable_response_becomes_an_apology(self, monkeypatch, content):
        fake_completion(monkeypatch, content)
        assert await get_reply(MESSAGES) == LLMReply(message=FALLBACK_MESSAGE)

    async def test_failure_is_logged(self, monkeypatch, caplog):
        fake_completion(monkeypatch, error=RuntimeError("provider down"))
        await get_reply(MESSAGES)
        assert "LLM call failed" in caplog.text

    async def test_mock_mode_never_calls_the_model(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "TRUE")
        calls = fake_completion(monkeypatch, '{"message": "real"}')
        reply = await get_reply(MESSAGES)
        assert reply.message == "Mock: I received your message."
        assert calls == []


class TestMockReply:
    def test_buy(self):
        reply = mock_reply("Buy 5 nvda")
        assert reply.message == "Mock: buying 5 NVDA."
        assert reply.trades == [TradeIntent(ticker="NVDA", side="buy", quantity=5)]
        assert reply.watchlist_changes == []

    def test_sell_with_fractional_quantity(self):
        reply = mock_reply("please SELL 0.5 AAPL now")
        assert reply.message == "Mock: selling 0.5 AAPL."
        assert reply.trades == [TradeIntent(ticker="AAPL", side="sell", quantity=0.5)]

    def test_watch(self):
        reply = mock_reply("watch pypl")
        assert reply.message == "Mock: adding PYPL to your watchlist."
        assert reply.watchlist_changes == [WatchlistChange(ticker="PYPL", action="add")]
        assert reply.trades == []

    def test_trade_rule_wins_over_watch(self):
        assert mock_reply("watch PYPL and buy 1 AAPL").trades[0].ticker == "AAPL"

    def test_anything_else(self):
        assert mock_reply("how am I doing?") == LLMReply(message="Mock: I received your message.")
