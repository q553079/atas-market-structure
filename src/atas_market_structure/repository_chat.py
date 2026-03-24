from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from atas_market_structure.repository_records import (
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredPromptBlock,
    StoredSessionMemory,
)


class ChatRepository(Protocol):
    """Replay chat/session/annotation persistence surface.

    Allowed to own:
    chat sessions, chat messages, prompt blocks, session memory, chart-mounted annotations, plan cards.

    Must not own:
    recognition outputs, tuning patch promotion, raw ingestion reliability paths.
    """

    def save_chat_session(self, **kwargs: Any) -> StoredChatSession:
        ...

    def get_chat_session(self, session_id: str) -> StoredChatSession | None:
        ...

    def list_chat_sessions(
        self,
        *,
        workspace_id: str | None = None,
        symbol: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> list[StoredChatSession]:
        ...

    def update_chat_session(self, session_id: str, **updates: Any) -> StoredChatSession | None:
        ...

    def save_chat_message(self, **kwargs: Any) -> StoredChatMessage:
        ...

    def get_chat_message(self, message_id: str) -> StoredChatMessage | None:
        ...

    def list_chat_messages(self, *, session_id: str, limit: int = 200, latest: bool = False) -> list[StoredChatMessage]:
        ...

    def update_chat_message(self, message_id: str, **updates: Any) -> StoredChatMessage | None:
        ...

    def save_prompt_block(self, **kwargs: Any) -> StoredPromptBlock:
        ...

    def get_prompt_block(self, block_id: str) -> StoredPromptBlock | None:
        ...

    def list_prompt_blocks(self, *, session_id: str, kind: str | None = None, limit: int = 200) -> list[StoredPromptBlock]:
        ...

    def save_or_update_session_memory(self, **kwargs: Any) -> StoredSessionMemory:
        ...

    def get_session_memory(self, session_id: str) -> StoredSessionMemory | None:
        ...

    def save_chat_annotation(self, **kwargs: Any) -> StoredChatAnnotation:
        ...

    def list_chat_annotations(
        self,
        *,
        session_id: str,
        message_id: str | None = None,
        status: str | None = None,
        visible_only: bool = False,
        limit: int = 500,
    ) -> list[StoredChatAnnotation]:
        ...

    def save_chat_plan_card(self, **kwargs: Any) -> StoredChatPlanCard:
        ...

    def list_chat_plan_cards(
        self,
        *,
        session_id: str,
        message_id: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[StoredChatPlanCard]:
        ...
