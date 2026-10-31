"""Tests for the POST /api/chat flow against a real app and database."""

import json
from types import SimpleNamespace

import pytest

from app import llm
from app.llm import FALLBACK_MESSAGE
from db import add_chat_message, connect, get_recent_chat_messages


def send(client, message):
    response = client.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def scripted_llm(monkeypatch, replies):
    """Make the model answer with each of `replies` in turn; return the prompts it receives."""
    prompts = []
    remaining = iter(replies)

    async def _acompletion(**kwargs):
        prompts.append(kwargs["messages"])
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=json.dumps(reply))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setattr(llm, "acompletion", _acompletion)
    return prompts


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def stored(app):
    """Read back the stored chat messages."""

    def _stored():
        conn = connect(app.state.db_path)
        messages = get_recent_chat_messages(conn)
        conn.close()
        return messages

    return _stored


class TestMockedFlow:
    def test_plain_message(self, client):
        assert send(client, "hello") == {"message": "Mock: I received your message.", "actions": []}

    def test_buy_executes_and_reports_the_fill(self, client):
        body = send(client, "buy 5 NVDA")

        assert body["message"] == "Mock: buying 5 NVDA."
        assert body["actions"] == [
            {
                "type": "trade",
                "ticker": "NVDA",
                "side": "buy",
                "quantity": 5,
                "status": "ok",
                "price": 800.0,
            }
        ]
        portfolio = client.get("/api/portfolio").json()
        assert portfolio["cash_balance"] == 6000.0
        assert portfolio["positions"][0]["ticker"] == "NVDA"

    def test_sell_executes(self, client, buy):
        buy("AAPL", 10)
        body = send(client, "sell 4 aapl")
        assert body["actions"][0]["status"] == "ok"
        assert client.get("/api/portfolio").json()["positions"][0]["quantity"] == 6

    def test_trade_records_a_snapshot(self, client):
        before = len(client.get("/api/portfolio/history").json())
        send(client, "buy 1 AAPL")
        assert len(client.get("/api/portfolio/history").json()) == before + 1

    def test_buying_an_untracked_ticker_starts_tracking_it(self, client, source):
        send(client, "buy 1 PYPL")
        assert "PYPL" in source.get_tickers()

    def test_watch_adds_to_the_watchlist(self, client, source):
        body = send(client, "watch pypl")

        assert body["actions"] == [
            {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "ok"}
        ]
        assert client.get("/api/watchlist").json()[-1]["ticker"] == "PYPL"
        assert "PYPL" in source.get_tickers()

    @pytest.mark.parametrize(
        ("message", "error"),
        [
            ("sell 100 TSLA", "Insufficient shares"),
            ("buy 1000 NVDA", "Insufficient cash"),
            ("buy 0 AAPL", "Quantity must be greater than 0"),
            ("buy 1 TOOLONG", "Invalid ticker: TOOLONG"),
            ("watch AAPL", "AAPL is already on the watchlist"),
        ],
    )
    def test_rejected_action_is_reported_not_raised(self, client, message, error):
        action = send(client, message)["actions"][0]
        assert action["status"] == "error"
        assert action["error"] == error
        assert "price" not in action

    def test_rejected_trade_changes_nothing(self, client):
        send(client, "buy 1000 NVDA")
        portfolio = client.get("/api/portfolio").json()
        assert portfolio["cash_balance"] == 10000.0
        assert portfolio["positions"] == []

    def test_no_price_yet(self, client, source):
        del source.prices["PYPL"]
        action = send(client, "buy 1 PYPL")["actions"][0]
        assert action["error"] == "No price available for PYPL yet"

    def test_exchange_is_stored_with_actions(self, client, stored):
        body = send(client, "buy 1 AAPL")

        user, assistant = stored()
        assert (user["role"], user["content"], user["actions"]) == ("user", "buy 1 AAPL", None)
        assert assistant["role"] == "assistant"
        assert assistant["content"] == body["message"]
        assert assistant["actions"] == body["actions"]

    def test_body_requires_a_message(self, client):
        assert client.post("/api/chat", json={}).status_code == 422


class TestModelFlow:
    def test_prompt_carries_live_context_and_the_new_message(self, client, buy, monkeypatch):
        buy("AAPL", 2)
        prompts = scripted_llm(monkeypatch, [{"message": "ok"}])

        send(client, "how am I doing?")

        system, user = prompts[0]
        assert system["role"] == "system"
        assert "FinAlly, an AI trading assistant" in system["content"]
        assert '"cash_balance": 9620.0' in system["content"]
        assert '"ticker": "AAPL", "quantity": 2.0' in system["content"]
        assert '"ticker": "NFLX", "price": 600.0' in system["content"]
        assert user == {"role": "user", "content": "how am I doing?"}

    def test_history_is_oldest_first(self, client, monkeypatch):
        prompts = scripted_llm(monkeypatch, [{"message": "one"}, {"message": "two"}])

        send(client, "first")
        send(client, "second")

        assert prompts[1][1:] == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "one"},
            {"role": "user", "content": "second"},
        ]

    def test_history_is_limited_to_twenty_messages(self, app, client, monkeypatch):
        conn = connect(app.state.db_path)
        for number in range(25):
            add_chat_message(conn, "user", f"old {number}")
        conn.close()
        prompts = scripted_llm(monkeypatch, [{"message": "ok"}])

        send(client, "new")

        history = prompts[0][1:-1]
        assert len(history) == 20
        assert history[0]["content"] == "old 5"

    def test_failed_action_outcome_reaches_the_next_prompt(self, client, monkeypatch):
        trade = {"ticker": "TSLA", "side": "sell", "quantity": 100}
        prompts = scripted_llm(
            monkeypatch, [{"message": "Selling", "trades": [trade]}, {"message": "ok"}]
        )

        send(client, "sell my TSLA")
        send(client, "did it work?")

        assistant = prompts[1][2]
        assert assistant["content"].startswith("Selling\n[Action results: ")
        assert '"status": "error"' in assistant["content"]
        assert '"error": "Insufficient shares"' in assistant["content"]

    def test_trades_and_watchlist_changes_run_together(self, client, monkeypatch):
        reply = {
            "message": "Doing it",
            "trades": [
                {"ticker": "nvda", "side": "buy", "quantity": 1},
                {"ticker": "AAPL", "side": "sell", "quantity": 1},
            ],
            "watchlist_changes": [
                {"ticker": "PYPL", "action": "add"},
                {"ticker": "NFLX", "action": "remove"},
            ],
        }
        scripted_llm(monkeypatch, [reply])

        actions = send(client, "go")["actions"]

        assert [action["status"] for action in actions] == ["ok", "error", "ok", "ok"]
        assert actions[0]["ticker"] == "NVDA"
        tickers = [entry["ticker"] for entry in client.get("/api/watchlist").json()]
        assert "PYPL" in tickers
        assert "NFLX" not in tickers

    def test_removing_an_absent_ticker_is_reported(self, client, monkeypatch):
        reply = {"message": "x", "watchlist_changes": [{"ticker": "PYPL", "action": "remove"}]}
        scripted_llm(monkeypatch, [reply])

        action = send(client, "go")["actions"][0]

        assert action["status"] == "error"
        assert action["error"] == "PYPL is not on the watchlist"

    def test_removing_a_held_ticker_keeps_tracking_it(self, client, buy, source, monkeypatch):
        buy("AAPL", 1)
        reply = {"message": "x", "watchlist_changes": [{"ticker": "AAPL", "action": "remove"}]}
        scripted_llm(monkeypatch, [reply])

        send(client, "go")

        assert "AAPL" in source.get_tickers()

    def test_llm_failure_returns_an_apology_and_stores_it(self, client, stored, monkeypatch):
        scripted_llm(monkeypatch, [RuntimeError("rate limited")])

        body = send(client, "buy 1 AAPL")

        assert body == {"message": FALLBACK_MESSAGE, "actions": []}
        assert client.get("/api/portfolio").json()["positions"] == []
        assert [message["content"] for message in stored()] == ["buy 1 AAPL", FALLBACK_MESSAGE]

    def test_malformed_reply_executes_nothing(self, client, monkeypatch):
        trade = {"ticker": "AAPL", "side": "hold", "quantity": 1}
        scripted_llm(monkeypatch, [{"message": "x", "trades": [trade]}])

        body = send(client, "go")

        assert body == {"message": FALLBACK_MESSAGE, "actions": []}
