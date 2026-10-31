"""Tests for chat history."""

from db import add_chat_message, get_recent_chat_messages


def test_user_message_has_null_actions(conn):
    add_chat_message(conn, "user", "hello")
    message = get_recent_chat_messages(conn)[0]
    assert message["role"] == "user"
    assert message["content"] == "hello"
    assert message["actions"] is None


def test_actions_round_trip(conn):
    actions = [{"type": "trade", "ticker": "NVDA", "status": "ok", "price": 875.2}]
    add_chat_message(conn, "assistant", "Buying", actions)
    assert get_recent_chat_messages(conn)[0]["actions"] == actions


def test_empty_actions_stay_empty_not_null(conn):
    add_chat_message(conn, "assistant", "Sorry", [])
    assert get_recent_chat_messages(conn)[0]["actions"] == []


def test_messages_are_oldest_first(conn):
    add_chat_message(conn, "user", "question")
    add_chat_message(conn, "assistant", "answer", [])
    assert [message["content"] for message in get_recent_chat_messages(conn)] == [
        "question",
        "answer",
    ]


def test_returns_only_the_latest_messages(conn):
    for index in range(25):
        add_chat_message(conn, "user", str(index))
    messages = get_recent_chat_messages(conn)
    assert [message["content"] for message in messages] == [str(i) for i in range(5, 25)]
