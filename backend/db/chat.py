"""Conversation history with the LLM."""

import json
import sqlite3
from uuid import uuid4

from .connection import USER_ID, utc_now


def add_chat_message(
    conn: sqlite3.Connection, role: str, content: str, actions: list[dict] | None = None
) -> None:
    """Append a message; `actions` is the executed actions list, None for user messages."""
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(uuid4()),
            USER_ID,
            role,
            content,
            None if actions is None else json.dumps(actions),
            utc_now(),
        ),
    )


def get_recent_chat_messages(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Return the latest `limit` messages, oldest first, with `actions` decoded.

    Ordered by rowid because a user message and its reply often share a timestamp.
    """
    rows = conn.execute(
        "SELECT role, content, actions, created_at FROM chat_messages "
        "WHERE user_id = ? ORDER BY rowid DESC LIMIT ?",
        (USER_ID, limit),
    ).fetchall()
    return [_decode(row) for row in reversed(rows)]


def _decode(row: sqlite3.Row) -> dict:
    message = dict(row)
    if message["actions"] is not None:
        message["actions"] = json.loads(message["actions"])
    return message
