from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any


class ReplayWorkbenchChatError(RuntimeError):
    """Raised when replay workbench chat operations fail due to invalid state or scope mismatch."""


class ReplayWorkbenchChatUnavailableError(ReplayWorkbenchChatError):
    """Raised when a chat turn requires an AI backend that is not currently configured."""


class ReplayWorkbenchNotFoundError(RuntimeError):
    """Raised when a requested replay or chat resource does not exist."""


def parse_utc(value: str) -> datetime:
    """Parse an ISO datetime string and normalize it to UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def payload_to_model(payload: Any, model_type):
    if payload is None:
        return None
    return model_type.model_validate(payload)


def slugify_chat_title(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value or "").strip()
    return normalized or "AI会话"


def chunk_stream_text(value: str, preferred_size: int = 32) -> list[str]:
    text = value or ""
    if not text:
        return []
    pieces = [piece for piece in re.split(r"(\s+)", text) if piece]
    if not pieces:
        return [text]
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > preferred_size:
            chunks.append(current)
            current = piece
            continue
        current += piece
    if current:
        chunks.append(current)
    return chunks


class PreparedReplyTurn:
    def __init__(
        self,
        *,
        session: StoredChatSession,
        replay_ingestion_id: str | None,
        user_record: StoredChatMessage,
        assistant_pending: StoredChatMessage,
        history,
        request: ChatReplyRequest,
        prompt_trace_id: str | None = None,
        parent_message_id: str | None = None,
    ) -> None:
        self.session = session
        self.replay_ingestion_id = replay_ingestion_id
        self.user_record = user_record
        self.assistant_pending = assistant_pending
        self.history = history
        self.request = request
        self.prompt_trace_id = prompt_trace_id
        self.parent_message_id = parent_message_id

    @property
    def has_replay_context(self) -> bool:
        return bool(self.replay_ingestion_id)


class FinalizedReplyTurn:
    def __init__(
        self,
        *,
        session_id: str,
        user_record: StoredChatMessage,
        assistant_record: StoredChatMessage,
        plan_cards: list[StoredChatPlanCard],
        annotations: list[StoredChatAnnotation],
        memory: SessionMemory | None,
        replay_response,
        prompt_trace_id: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_record = user_record
        self.assistant_record = assistant_record
        self.plan_cards = plan_cards
        self.annotations = annotations
        self.memory = memory
        self.replay_response = replay_response
        self.prompt_trace_id = prompt_trace_id
