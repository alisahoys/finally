"""Chat route."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Cache, Conn, Source
from app.chat import handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("")
async def chat(body: ChatRequest, conn: Conn, cache: Cache, source: Source) -> dict:
    """Answer a message, execute any actions it implies and return both."""
    return await handle_chat(conn, cache, source, body.message)
