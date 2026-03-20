from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from threading import Lock
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterBackfillCommand,
    AdapterBackfillDispatchResponse,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintBar,
    AdapterHistoryFootprintPayload,
    AdapterInitiativeDriveState,
    AdapterPostHarvestResponseState,
    AdapterSamePriceReplenishmentState,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
    BuildPromptBlocksRequest,
    ChatAnnotation,
    ChatHandoffPacket,
    ChatHandoffRequest,
    ChatHandoffResponse,
    ChatMessage,
    ChatMessagesEnvelope,
    ChatObjectsEnvelope,
    ChatPlanCard,
    ChatReplyRequest,
    ChatReplyResponse,
    ChatSession,
    ChatSessionEnvelope,
    ChatSessionsEnvelope,
    ChatWindowRange,
    CreateChatMessageRequest,
    CreateChatSessionRequest,
    PromptBlock,
    PromptBlocksEnvelope,
    SessionMemory,
    SessionMemoryEnvelope,
    UpdateChatSessionRequest,
    UpdateMountedMessageRequest,
    ReplayAcquisitionMode,
    ReplayAiBriefing,
    ReplayCachePolicy,
    ReplayFootprintBarDetail,
    ReplayFootprintLevelDetail,
    ReplayOperatorEntryAcceptedResponse,
    ReplayOperatorEntryEnvelope,
    ReplayOperatorEntryRecord,
    ReplayOperatorEntryRequest,
    ReplayManualRegionAnnotationAcceptedResponse,
    ReplayManualRegionAnnotationEnvelope,
    ReplayManualRegionAnnotationRecord,
    ReplayManualRegionAnnotationRequest,
    ReplayVerificationState,
    ReplayVerificationStatus,
    ReplayWorkbenchAcceptedResponse,
    ReplayWorkbenchAcceptedSummary,
    ReplayWorkbenchAckRebuildResult,
    ReplayWorkbenchAckVerification,
    ReplayWorkbenchAtasBackfillAcceptedResponse,
    ReplayWorkbenchAtasBackfillRecord,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchAtasBackfillStatus,
    ReplayWorkbenchBuildAction,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchCacheRecord,
    ReplayWorkbenchGapSegment,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchIntegrity,
    ReplayWorkbenchLiveSourceStatus,
    ReplayWorkbenchLiveStatusResponse,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
    ReplayChartBar,
    ReplayEventAnnotation,
    ReplayFocusRegion,
    ReplayLiveStreamState,
    ReplayStrategyCandidate,
    StructureSide,
    Timeframe,
)
from atas_market_structure.repository import (
    AnalysisRepository,
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredIngestion,
    StoredPromptBlock,
    StoredSessionMemory,
)
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine


class ReplayWorkbenchChatError(RuntimeError):
    """Raised when replay workbench chat operations fail due to invalid state or scope mismatch."""


class ReplayWorkbenchNotFoundError(RuntimeError):
    """Raised when a requested replay cache record does not exist."""


def payload_to_model(payload: Any, model_type):
    if payload is None:
        return None
    return model_type.model_validate(payload)


def _slugify_title(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value or "").strip()
    return normalized or "AI会话"


class _PreparedReplyTurn:
    def __init__(self, *, session: StoredChatSession, replay_ingestion_id: str, user_record: StoredChatMessage, assistant_pending: StoredChatMessage, history, request: ChatReplyRequest) -> None:
        self.session = session
        self.replay_ingestion_id = replay_ingestion_id
        self.user_record = user_record
        self.assistant_pending = assistant_pending
        self.history = history
        self.request = request


class _FinalizedReplyTurn:
    def __init__(self, *, session_id: str, user_record: StoredChatMessage, assistant_record: StoredChatMessage, plan_cards: list[StoredChatPlanCard], annotations: list[StoredChatAnnotation], memory: SessionMemory | None, replay_response) -> None:
        self.session_id = session_id
        self.user_record = user_record
        self.assistant_record = assistant_record
        self.plan_cards = plan_cards
        self.annotations = annotations
        self.memory = memory
        self.replay_response = replay_response


class ReplayWorkbenchChatService:
    """Session-aware replay workbench chat orchestration built on top of the existing repository and AI chat service."""

    def __init__(self, repository: AnalysisRepository, replay_ai_chat_service) -> None:
        self._repository = repository
        self._replay_ai_chat_service = replay_ai_chat_service
        self._stream_registry_lock = Lock()
        self._stream_registry: dict[str, dict[str, Any]] = {}

    def create_session(self, request: CreateChatSessionRequest) -> ChatSessionEnvelope:
        now = datetime.now(tz=UTC)
        session_id = f"sess-{uuid4().hex}"
        title = _slugify_title(request.title)
        self._repository.save_chat_session(
            session_id=session_id,
            workspace_id=request.workspace_id,
            title=title,
            symbol=request.symbol,
            contract_id=request.contract_id,
            timeframe=str(request.timeframe),
            window_range=request.window_range.model_dump(mode="json"),
            active_model=request.active_model,
            status="active",
            draft_text="",
            draft_attachments=[],
            selected_prompt_block_ids=[],
            pinned_context_block_ids=[],
            mounted_reply_ids=[],
            active_plan_id=None,
            memory_summary_id=None,
            unread_count=0,
            scroll_offset=0,
            pinned=False,
            created_at=now,
            updated_at=now,
        )
        return ChatSessionEnvelope(session=self._require_session(session_id))

    def list_sessions(self, *, workspace_id: str | None = None, symbol: str | None = None, include_archived: bool = False) -> ChatSessionsEnvelope:
        sessions = self._repository.list_chat_sessions(
            workspace_id=workspace_id,
            symbol=symbol,
            include_archived=include_archived,
        )
        return ChatSessionsEnvelope(sessions=[self._session_model(item) for item in sessions])

    def get_session(self, session_id: str) -> ChatSessionEnvelope:
        return ChatSessionEnvelope(session=self._require_session(session_id))

    def update_session(self, session_id: str, request: UpdateChatSessionRequest) -> ChatSessionEnvelope:
        session = self._require_stored_session(session_id)
        updates = request.model_dump(exclude_none=True, mode="json")
        updates["updated_at"] = datetime.now(tz=UTC)
        self._repository.update_chat_session(session.session_id, **updates)
        return ChatSessionEnvelope(session=self._require_session(session_id))

    def archive_session(self, session_id: str) -> ChatSessionEnvelope:
        self._require_stored_session(session_id)
        self._repository.update_chat_session(session_id, status="archived", updated_at=datetime.now(tz=UTC))
        return ChatSessionEnvelope(session=self._require_session(session_id))

    def list_messages(self, session_id: str, limit: int = 200) -> ChatMessagesEnvelope:
        self._require_stored_session(session_id)
        messages = self._repository.list_chat_messages(session_id=session_id, limit=limit)
        return ChatMessagesEnvelope(messages=[self._message_model(item) for item in messages])

    def create_message(self, session_id: str, request: CreateChatMessageRequest) -> ChatMessagesEnvelope:
        self._require_stored_session(session_id)
        now = datetime.now(tz=UTC)
        self._repository.save_chat_message(
            message_id=f"msg-{uuid4().hex}",
            session_id=session_id,
            parent_message_id=None,
            role=request.role,
            content=request.content,
            status="sent" if request.role == "user" else "completed",
            reply_title=None,
            stream_buffer="",
            model=None,
            annotations=[],
            plan_cards=[],
            mounted_to_chart=False,
            mounted_object_ids=[],
            is_key_conclusion=False,
            request_payload={"attachments": [item.model_dump(mode="json") for item in request.attachments], "selected_block_ids": request.selected_block_ids},
            response_payload={},
            created_at=now,
            updated_at=now,
        )
        self._repository.update_chat_session(session_id, updated_at=now)
        return self.list_messages(session_id)

    def build_prompt_blocks(self, session_id: str, request: BuildPromptBlocksRequest) -> PromptBlocksEnvelope:
        session = self._require_stored_session(session_id)
        replay_ingestion = self._find_latest_replay_ingestion_for_symbol(session.symbol)
        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload) if replay_ingestion else None
        latest_message = self._get_latest_message(session_id, role="assistant")
        latest_memory = self._repository.get_session_memory(session_id)
        blocks: list[PromptBlock] = []
        now = datetime.now(tz=UTC)
        for kind in request.candidates:
            block = self._build_prompt_block(session, replay_payload, latest_message, latest_memory, kind, now)
            self._repository.save_prompt_block(
                block_id=block.block_id,
                session_id=block.session_id,
                symbol=block.symbol,
                contract_id=block.contract_id,
                timeframe=str(block.timeframe) if block.timeframe is not None else None,
                kind=block.kind,
                title=block.title,
                preview_text=block.preview_text,
                full_payload=block.full_payload,
                selected_by_default=block.selected_by_default,
                pinned=block.pinned,
                ephemeral=block.ephemeral,
                created_at=block.created_at,
                expires_at=block.expires_at,
            )
            blocks.append(block)
        return PromptBlocksEnvelope(blocks=blocks)

    def get_prompt_block(self, block_id: str) -> PromptBlocksEnvelope:
        block = self._repository.get_prompt_block(block_id)
        if block is None:
            raise ReplayWorkbenchNotFoundError(f"Prompt block '{block_id}' not found.")
        return PromptBlocksEnvelope(blocks=[self._prompt_block_model(block)])

    def reply(self, session_id: str, request: ChatReplyRequest) -> ChatReplyResponse:
        prepared = self._prepare_reply_turn(session_id, request)
        replay_response = self._run_reply_model(prepared)
        finalized = self._finalize_reply_turn(prepared, replay_response)
        return self._build_reply_response(finalized)

    def build_reply_event_preview(self, session_id: str, request: ChatReplyRequest) -> list[dict[str, Any]]:
        prepared = self._prepare_reply_turn(session_id, request)
        self._register_stream(prepared.assistant_pending.message_id, session_id)
        try:
            replay_response = self._run_reply_model(prepared)
            if self._is_stream_cancelled(prepared.assistant_pending.message_id):
                interrupted = self._interrupt_reply_turn(prepared)
                return self._build_interrupted_events(interrupted)
            finalized = self._finalize_reply_turn(prepared, replay_response)
            return self._build_reply_events(finalized)
        finally:
            self._unregister_stream(prepared.assistant_pending.message_id)

    def stop_message(self, session_id: str, message_id: str) -> ChatMessage:
        message = self._repository.get_chat_message(message_id)
        if message is None or message.session_id != session_id:
            raise ReplayWorkbenchNotFoundError(f"Chat message '{message_id}' not found in session '{session_id}'.")
        self._mark_stream_cancelled(message_id)
        updated = self._repository.update_chat_message(
            message_id,
            status="interrupted",
            updated_at=datetime.now(tz=UTC),
        )
        if updated is None:
            raise ReplayWorkbenchChatError(f"Chat message '{message_id}' disappeared during stop update.")
        return self._message_model(updated)

    def regenerate_message(self, session_id: str, message_id: str) -> ChatReplyResponse:
        message = self._repository.get_chat_message(message_id)
        if message is None or message.session_id != session_id:
            raise ReplayWorkbenchNotFoundError(f"Chat message '{message_id}' not found in session '{session_id}'.")
        user_message = self._find_regenerate_user_message(session_id, message)
        if user_message is None:
            raise ReplayWorkbenchChatError(f"No user message context found for regenerate target '{message_id}'.")
        request_payload = user_message.request_payload or {}
        request = ChatReplyRequest(
            user_input=user_message.content,
            selected_block_ids=request_payload.get("selected_block_ids", []),
            pinned_block_ids=request_payload.get("pinned_block_ids", []),
            include_memory_summary=bool(request_payload.get("include_memory_summary", False)),
            include_recent_messages=bool(request_payload.get("include_recent_messages", True)),
            model=message.model,
            preset=str(message.request_payload.get("preset") or request_payload.get("preset") or "general"),
            attachments=[],
            replay_ingestion_id=message.response_payload.get("replay_ingestion_id") or request_payload.get("replay_ingestion_id"),
        )
        return self.reply(session_id, request)

    def _find_regenerate_user_message(self, session_id: str, assistant_message: StoredChatMessage) -> StoredChatMessage | None:
        messages = self._repository.list_chat_messages(session_id=session_id, limit=500)
        assistant_index = next((index for index, item in enumerate(messages) if item.message_id == assistant_message.message_id), None)
        if assistant_index is None:
            return None
        for candidate in reversed(messages[:assistant_index]):
            if candidate.role == "user":
                return candidate
        return None

    def _prepare_reply_turn(self, session_id: str, request: ChatReplyRequest) -> _PreparedReplyTurn:
        session = self._require_stored_session(session_id)
        replay_ingestion_id = request.replay_ingestion_id or self._find_latest_replay_ingestion_id_for_symbol(session.symbol)
        if replay_ingestion_id is None:
            raise ReplayWorkbenchChatError(f"No replay ingestion found for symbol '{session.symbol}'.")
        self._validate_block_scope(session, request.selected_block_ids + request.pinned_block_ids)

        now = datetime.now(tz=UTC)
        user_record = self._repository.save_chat_message(
            message_id=f"msg-{uuid4().hex}",
            session_id=session_id,
            parent_message_id=None,
            role="user",
            content=request.user_input,
            status="sent",
            reply_title=None,
            stream_buffer="",
            model=None,
            annotations=[],
            plan_cards=[],
            mounted_to_chart=False,
            mounted_object_ids=[],
            is_key_conclusion=False,
            request_payload={
                "selected_block_ids": request.selected_block_ids,
                "pinned_block_ids": request.pinned_block_ids,
                "include_memory_summary": request.include_memory_summary,
                "include_recent_messages": request.include_recent_messages,
                "attachments": [item.model_dump(mode="json") for item in request.attachments],
            },
            response_payload={},
            created_at=now,
            updated_at=now,
        )
        assistant_pending = self._repository.save_chat_message(
            message_id=f"msg-{uuid4().hex}",
            session_id=session_id,
            parent_message_id=None,
            role="assistant",
            content="",
            status="pending",
            reply_title=None,
            stream_buffer="",
            model=request.model or session.active_model,
            annotations=[],
            plan_cards=[],
            mounted_to_chart=False,
            mounted_object_ids=[],
            is_key_conclusion=False,
            request_payload={},
            response_payload={},
            created_at=now,
            updated_at=now,
        )
        history = self._build_history_for_reply(session_id, request.include_recent_messages, request.include_memory_summary)
        return _PreparedReplyTurn(
            session=session,
            replay_ingestion_id=replay_ingestion_id,
            user_record=user_record,
            assistant_pending=assistant_pending,
            history=history,
            request=request,
        )

    def _run_reply_model(self, prepared: _PreparedReplyTurn):
        return self._replay_ai_chat_service.chat(
            __import__("atas_market_structure.models", fromlist=["ReplayAiChatRequest"]).ReplayAiChatRequest(
                replay_ingestion_id=prepared.replay_ingestion_id,
                preset=prepared.request.preset,
                user_message=prepared.request.user_input,
                history=prepared.history,
                model_override=prepared.request.model or prepared.session.active_model,
                include_live_context=True,
                attachments=prepared.request.attachments,
            )
        )

    def _finalize_reply_turn(self, prepared: _PreparedReplyTurn, replay_response) -> _FinalizedReplyTurn:
        plan_cards = self._extract_plan_cards(prepared.session, prepared.assistant_pending.message_id, replay_response.reply_text)
        annotations = self._build_annotations(prepared.session, prepared.assistant_pending.message_id, plan_cards)
        assistant_record = self._repository.update_chat_message(
            prepared.assistant_pending.message_id,
            content=replay_response.reply_text,
            status="completed",
            model=replay_response.model,
            plan_cards=[item.plan_id for item in plan_cards],
            annotations=[item.annotation_id for item in annotations],
            response_payload=replay_response.model_dump(mode="json"),
            updated_at=datetime.now(tz=UTC),
        )
        if assistant_record is None:
            raise ReplayWorkbenchChatError(f"Assistant message '{prepared.assistant_pending.message_id}' disappeared during update.")
        memory = self._refresh_session_memory(
            prepared.session.session_id,
            replay_response.model,
            prepared.request.user_input,
            replay_response.reply_text,
            annotations,
            plan_cards,
        )
        self._repository.update_chat_session(
            prepared.session.session_id,
            active_model=replay_response.model,
            memory_summary_id=memory.memory_summary_id if memory else None,
            updated_at=datetime.now(tz=UTC),
        )
        return _FinalizedReplyTurn(
            session_id=prepared.session.session_id,
            user_record=prepared.user_record,
            assistant_record=assistant_record,
            plan_cards=plan_cards,
            annotations=annotations,
            memory=memory,
            replay_response=replay_response,
        )

    def _build_reply_response(self, finalized: _FinalizedReplyTurn) -> ChatReplyResponse:
        replay_response = finalized.replay_response
        return ChatReplyResponse(
            session=self._require_session(finalized.session_id),
            user_message=self._message_model(finalized.user_record),
            assistant_message=self._message_model(finalized.assistant_record),
            annotations=[self._annotation_model(item) for item in finalized.annotations],
            plan_cards=[self._plan_card_model(item) for item in finalized.plan_cards],
            memory=finalized.memory,
            reply_text=replay_response.reply_text,
            provider=replay_response.provider,
            model=replay_response.model,
            preset=str(replay_response.preset),
            referenced_strategy_ids=replay_response.referenced_strategy_ids,
            live_context_summary=replay_response.live_context_summary,
            follow_up_suggestions=replay_response.follow_up_suggestions,
            attachment_summaries=replay_response.attachment_summaries,
        )

    def _build_reply_events(self, finalized: _FinalizedReplyTurn) -> list[dict[str, Any]]:
        replay_response = finalized.replay_response
        events: list[dict[str, Any]] = [
            {
                "event": "message_start",
                "data": {
                    "session_id": finalized.session_id,
                    "message_id": finalized.assistant_record.message_id,
                    "model": replay_response.model,
                    "provider": replay_response.provider,
                },
            },
            {
                "event": "message_status",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "status": "streaming",
                },
            },
            {
                "event": "token",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "delta": replay_response.reply_text,
                },
            },
        ]
        if finalized.annotations:
            events.append(
                {
                    "event": "annotation_patch",
                    "data": {
                        "message_id": finalized.assistant_record.message_id,
                        "annotations": [self._annotation_model(item).model_dump(mode="json") for item in finalized.annotations],
                    },
                }
            )
        if finalized.plan_cards:
            events.append(
                {
                    "event": "plan_card",
                    "data": {
                        "message_id": finalized.assistant_record.message_id,
                        "plan_cards": [self._plan_card_model(item).model_dump(mode="json") for item in finalized.plan_cards],
                    },
                }
            )
        if finalized.memory is not None:
            events.append(
                {
                    "event": "memory_updated",
                    "data": finalized.memory.model_dump(mode="json"),
                }
            )
        events.append(
            {
                "event": "message_end",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "status": finalized.assistant_record.status,
                    "content": replay_response.reply_text,
                    "reply_title": finalized.assistant_record.reply_title,
                    "provider": replay_response.provider,
                    "model": replay_response.model,
                    "plan_cards": [self._plan_card_model(item).model_dump(mode="json") for item in finalized.plan_cards],
                    "annotations": [self._annotation_model(item).model_dump(mode="json") for item in finalized.annotations],
                    "live_context_summary": replay_response.live_context_summary,
                    "follow_up_suggestions": replay_response.follow_up_suggestions,
                },
            }
        )
        return events

    def _build_reply_events(self, finalized: _FinalizedReplyTurn) -> list[dict[str, Any]]:
        replay_response = finalized.replay_response
        events: list[dict[str, Any]] = [
            {
                "event": "message_start",
                "data": {
                    "session_id": finalized.session_id,
                    "message_id": finalized.assistant_record.message_id,
                    "model": replay_response.model,
                    "provider": replay_response.provider,
                },
            },
            {
                "event": "message_status",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "status": "streaming",
                },
            },
            {
                "event": "token",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "delta": replay_response.reply_text,
                },
            },
        ]
        if finalized.annotations:
            events.append(
                {
                    "event": "annotation_patch",
                    "data": {
                        "message_id": finalized.assistant_record.message_id,
                        "annotations": [self._annotation_model(item).model_dump(mode="json") for item in finalized.annotations],
                    },
                }
            )
        if finalized.plan_cards:
            events.append(
                {
                    "event": "plan_card",
                    "data": {
                        "message_id": finalized.assistant_record.message_id,
                        "plan_cards": [self._plan_card_model(item).model_dump(mode="json") for item in finalized.plan_cards],
                    },
                }
            )
        if finalized.memory is not None:
            events.append(
                {
                    "event": "memory_updated",
                    "data": finalized.memory.model_dump(mode="json"),
                }
            )
        events.append(
            {
                "event": "message_end",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "status": finalized.assistant_record.status,
                    "content": replay_response.reply_text,
                    "reply_title": finalized.assistant_record.reply_title,
                    "provider": replay_response.provider,
                    "model": replay_response.model,
                    "plan_cards": [self._plan_card_model(item).model_dump(mode="json") for item in finalized.plan_cards],
                    "annotations": [self._annotation_model(item).model_dump(mode="json") for item in finalized.annotations],
                    "live_context_summary": replay_response.live_context_summary,
                    "follow_up_suggestions": replay_response.follow_up_suggestions,
                },
            }
        )
        return events

    def _interrupt_reply_turn(self, prepared: _PreparedReplyTurn) -> StoredChatMessage:
        interrupted = self._repository.update_chat_message(
            prepared.assistant_pending.message_id,
            status="interrupted",
            updated_at=datetime.now(tz=UTC),
        )
        if interrupted is None:
            raise ReplayWorkbenchChatError(f"Assistant message '{prepared.assistant_pending.message_id}' disappeared during interrupt update.")
        return interrupted

    def _build_interrupted_events(self, interrupted: StoredChatMessage) -> list[dict[str, Any]]:
        return [
            {
                "event": "message_start",
                "data": {
                    "session_id": interrupted.session_id,
                    "message_id": interrupted.message_id,
                    "model": interrupted.model,
                    "provider": "interrupted",
                },
            },
            {
                "event": "message_status",
                "data": {
                    "message_id": interrupted.message_id,
                    "status": "interrupted",
                },
            },
            {
                "event": "error",
                "data": {
                    "message_id": interrupted.message_id,
                    "code": "STREAM_INTERRUPTED",
                    "message": "stream interrupted by user",
                },
            },
        ]

    def _register_stream(self, message_id: str, session_id: str) -> None:
        with self._stream_registry_lock:
            self._stream_registry[message_id] = {"session_id": session_id, "cancelled": False}

    def _mark_stream_cancelled(self, message_id: str) -> None:
        with self._stream_registry_lock:
            if message_id in self._stream_registry:
                self._stream_registry[message_id]["cancelled"] = True

    def _is_stream_cancelled(self, message_id: str) -> bool:
        with self._stream_registry_lock:
            return bool(self._stream_registry.get(message_id, {}).get("cancelled"))

    def _unregister_stream(self, message_id: str) -> None:
        with self._stream_registry_lock:
            self._stream_registry.pop(message_id, None)

    def get_memory(self, session_id: str) -> SessionMemoryEnvelope:
        self._require_stored_session(session_id)
        memory = self._repository.get_session_memory(session_id)
        return SessionMemoryEnvelope(memory=self._memory_model(memory) if memory is not None else None)

    def build_handoff(self, session_id: str, request: ChatHandoffRequest) -> ChatHandoffResponse:
        session = self._require_stored_session(session_id)
        memory = self._repository.get_session_memory(session_id)
        recent_messages = self._repository.list_chat_messages(session_id=session_id, limit=3 if request.mode == "summary_plus_recent_3" else 1)
        active_annotations = self._repository.list_chat_annotations(session_id=session_id, status="active", visible_only=True, limit=200)
        active_plans = self._repository.list_chat_plan_cards(session_id=session_id, status="active", limit=100)
        packet = ChatHandoffPacket(
            session_meta={
                "session_id": session.session_id,
                "title": session.title,
                "symbol": session.symbol,
                "contract_id": session.contract_id,
                "timeframe": session.timeframe,
                "target_model": request.target_model,
            },
            memory_summary=self._memory_model(memory).model_dump(mode="json") if memory is not None and request.mode != "question_only" else {},
            recent_messages=[self._message_model(item).model_dump(mode="json") for item in recent_messages] if request.mode == "summary_plus_recent_3" else [],
            active_annotations=[self._annotation_model(item).model_dump(mode="json") for item in active_annotations],
            active_plans=[self._plan_card_model(item).model_dump(mode="json") for item in active_plans],
        )
        return ChatHandoffResponse(handoff_packet=packet)

    def list_objects(self, session_id: str, message_id: str) -> ChatObjectsEnvelope:
        self._require_stored_session(session_id)
        message = self._repository.get_chat_message(message_id)
        if message is None or message.session_id != session_id:
            raise ReplayWorkbenchNotFoundError(f"Chat message '{message_id}' not found in session '{session_id}'.")
        annotations = self._repository.list_chat_annotations(session_id=session_id, message_id=message_id, limit=500)
        plans = self._repository.list_chat_plan_cards(session_id=session_id, message_id=message_id, limit=200)
        return ChatObjectsEnvelope(
            annotations=[self._annotation_model(item) for item in annotations],
            plan_cards=[self._plan_card_model(item) for item in plans],
            mounted_to_chart=message.mounted_to_chart,
            mounted_object_ids=message.mounted_object_ids,
        )

    def update_mount_state(self, message_id: str, request: UpdateMountedMessageRequest) -> ChatObjectsEnvelope:
        message = self._repository.get_chat_message(message_id)
        if message is None:
            raise ReplayWorkbenchNotFoundError(f"Chat message '{message_id}' not found.")
        updated = self._repository.update_chat_message(
            message_id,
            mounted_to_chart=request.mounted_to_chart,
            mounted_object_ids=request.mounted_object_ids,
            updated_at=datetime.now(tz=UTC),
        )
        if updated is None:
            raise ReplayWorkbenchChatError(f"Chat message '{message_id}' disappeared during mount update.")
        session = self._require_stored_session(updated.session_id)
        mounted_reply_ids = list(dict.fromkeys([*(session.mounted_reply_ids if request.mount_mode != "replace" else []), message_id] if request.mounted_to_chart else [item for item in session.mounted_reply_ids if item != message_id]))
        self._repository.update_chat_session(updated.session_id, mounted_reply_ids=mounted_reply_ids, updated_at=datetime.now(tz=UTC))
        return self.list_objects(updated.session_id, message_id)

    def _build_prompt_block(self, session: StoredChatSession, replay_payload: ReplayWorkbenchSnapshotPayload | None, latest_message: StoredChatMessage | None, latest_memory: StoredSessionMemory | None, kind: str, now: datetime) -> PromptBlock:
        block_id = f"pb-{uuid4().hex}"
        if kind == "candles_20" and replay_payload is not None:
            candles = replay_payload.candles[-20:]
            preview = f"最近{len(candles)}根K线，最新收盘 {candles[-1].close if candles else '-'}"
            full_payload = {"bars": [item.model_dump(mode="json") for item in candles]}
            title = "最近20根K线"
        elif kind == "event_summary" and replay_payload is not None:
            events = replay_payload.event_annotations[-10:]
            preview = f"最近事件 {len(events)} 条"
            full_payload = {"events": [item.model_dump(mode="json") for item in events]}
            title = "事件摘要"
        elif kind == "selected_bar" and replay_payload is not None and replay_payload.candles:
            candle = replay_payload.candles[-1]
            preview = f"选中K线 O={candle.open} H={candle.high} L={candle.low} C={candle.close}"
            full_payload = {"bar": candle.model_dump(mode="json")}
            title = "当前选中K线"
        elif kind == "manual_region":
            regions = _list_manual_regions(self._repository, self._find_latest_replay_ingestion_id_for_symbol(session.symbol) or "")
            preview = f"手工区域 {len(regions)} 条"
            full_payload = {"regions": [item.model_dump(mode="json") for item in regions[-10:]]}
            title = "手工区域"
        elif kind == "recent_messages":
            messages = self._repository.list_chat_messages(session_id=session.session_id, limit=6)
            preview = f"最近消息 {len(messages)} 条"
            full_payload = {"messages": [self._message_model(item).model_dump(mode="json") for item in messages[-6:]]}
            title = "最近消息"
        elif kind == "session_summary" and latest_memory is not None:
            preview = latest_memory.latest_answer_summary or latest_memory.market_context_summary or "会话摘要"
            full_payload = self._memory_model(latest_memory).model_dump(mode="json")
            title = "会话摘要"
        else:
            preview = latest_message.content[:160] if latest_message is not None else "当前用户输入"
            full_payload = {"message": latest_message.content if latest_message is not None else ""}
            title = kind
        return PromptBlock(
            block_id=block_id,
            session_id=session.session_id,
            symbol=session.symbol,
            contract_id=session.contract_id,
            timeframe=session.timeframe,
            kind=kind,
            title=title,
            preview_text=preview,
            full_payload=full_payload,
            selected_by_default=False,
            pinned=False,
            ephemeral=True,
            created_at=now,
            expires_at=None,
        )

    def _refresh_session_memory(self, session_id: str, active_model: str | None, latest_question: str, reply_text: str, annotations: list[StoredChatAnnotation], plans: list[StoredChatPlanCard]) -> SessionMemory | None:
        session = self._require_stored_session(session_id)
        previous = self._repository.get_session_memory(session_id)
        now = datetime.now(tz=UTC)
        summary_version = 1 if previous is None else previous.summary_version + 1
        key_zones = [item.label for item in annotations if item.annotation_type in {"support_zone", "resistance_zone", "no_trade_zone", "zone"}]
        active_plans_summary = [item.title for item in plans if item.status == "active"]
        stored = self._repository.save_or_update_session_memory(
            memory_summary_id=f"mem-{uuid4().hex}",
            session_id=session_id,
            summary_version=summary_version,
            active_model=active_model,
            symbol=session.symbol,
            contract_id=session.contract_id,
            timeframe=session.timeframe,
            window_range=session.window_range,
            user_goal_summary=(previous.user_goal_summary if previous is not None and previous.user_goal_summary else latest_question[:120]),
            market_context_summary=reply_text[:180],
            key_zones_summary=list(dict.fromkeys([*(previous.key_zones_summary if previous is not None else []), *key_zones]))[-8:],
            active_plans_summary=active_plans_summary[-8:],
            invalidated_plans_summary=previous.invalidated_plans_summary if previous is not None else [],
            important_messages=[item.message_id for item in self._repository.list_chat_messages(session_id=session_id, limit=6) if item.role == "assistant"][-6:],
            current_user_intent=latest_question[:120],
            latest_question=latest_question,
            latest_answer_summary=reply_text[:180],
            selected_annotations=[item.annotation_id for item in annotations][-12:],
            last_updated_at=now,
        )
        self._repository.update_chat_session(session_id, memory_summary_id=stored.memory_summary_id, updated_at=now)
        return self._memory_model(stored)

    def _extract_plan_cards(self, session: StoredChatSession, message_id: str, reply_text: str) -> list[StoredChatPlanCard]:
        text = str(reply_text or "")
        values = [float(item) for item in re.findall(r"\d{4,5}(?:\.\d{1,2})?", text)]
        if len(values) < 2 or not re.search(r"止损|止盈|TP|入场|做多|做空", text):
            return []
        side = "sell" if re.search(r"做空|空", text) and not re.search(r"做多", text) else "buy"
        entry = values[0] if values else None
        stop = values[1] if len(values) > 1 else None
        take_profits = [
            {"id": str(index + 1), "tp_level": index + 1, "target_price": target}
            for index, target in enumerate(values[2:4])
        ]
        now = datetime.now(tz=UTC)
        plan = self._repository.save_chat_plan_card(
            plan_id=f"plan-{uuid4().hex}",
            session_id=session.session_id,
            message_id=message_id,
            title=(f"AI开空 {entry}" if side == "sell" else f"AI开多 {entry}"),
            side=side,
            entry_type="point",
            entry_price=entry,
            entry_price_low=None,
            entry_price_high=None,
            stop_price=stop,
            take_profits=take_profits,
            invalidations=[f"跌破 {stop}"] if side == "buy" and stop is not None else ([f"突破 {stop}"] if stop is not None else []),
            time_validity="session",
            risk_reward=None,
            confidence=None,
            priority=None,
            status="active",
            source_kind="replay_analysis",
            notes=text,
            payload={"reply_text": text},
            created_at=now,
            updated_at=now,
        )
        return [plan]

    def _build_annotations(self, session: StoredChatSession, message_id: str, plans: list[StoredChatPlanCard]) -> list[StoredChatAnnotation]:
        annotations: list[StoredChatAnnotation] = []
        now = datetime.now(tz=UTC)
        for plan in plans:
            if plan.entry_price is not None:
                annotations.append(
                    self._repository.save_chat_annotation(
                        annotation_id=f"ann-{uuid4().hex}",
                        session_id=session.session_id,
                        message_id=message_id,
                        plan_id=plan.plan_id,
                        symbol=session.symbol,
                        contract_id=session.contract_id,
                        timeframe=session.timeframe,
                        annotation_type="entry_line",
                        subtype=None,
                        label=plan.title,
                        reason="AI 计划入场位",
                        start_time=now,
                        end_time=None,
                        expires_at=None,
                        status="active",
                        priority=plan.priority,
                        confidence=plan.confidence,
                        visible=True,
                        pinned=False,
                        source_kind="replay_analysis",
                        payload={"entry_price": plan.entry_price, "side": plan.side},
                        created_at=now,
                        updated_at=now,
                    )
                )
            if plan.stop_price is not None:
                annotations.append(
                    self._repository.save_chat_annotation(
                        annotation_id=f"ann-{uuid4().hex}",
                        session_id=session.session_id,
                        message_id=message_id,
                        plan_id=plan.plan_id,
                        symbol=session.symbol,
                        contract_id=session.contract_id,
                        timeframe=session.timeframe,
                        annotation_type="stop_loss",
                        subtype=None,
                        label=f"SL {plan.stop_price}",
                        reason="AI 计划止损位",
                        start_time=now,
                        end_time=None,
                        expires_at=None,
                        status="active",
                        priority=plan.priority,
                        confidence=plan.confidence,
                        visible=True,
                        pinned=False,
                        source_kind="replay_analysis",
                        payload={"stop_price": plan.stop_price, "side": plan.side},
                        created_at=now,
                        updated_at=now,
                    )
                )
        return annotations

    def _build_history_for_reply(self, session_id: str, include_recent_messages: bool, include_memory_summary: bool):
        from atas_market_structure.models import ReplayAiChatMessage

        history: list[ReplayAiChatMessage] = []
        if include_memory_summary:
            memory = self._repository.get_session_memory(session_id)
            if memory is not None:
                summary_parts = [part for part in [memory.user_goal_summary, memory.market_context_summary, memory.latest_answer_summary] if part]
                if summary_parts:
                    history.append(ReplayAiChatMessage(role="assistant", content="[memory]\n" + "\n".join(summary_parts)))
        if include_recent_messages:
            for item in self._repository.list_chat_messages(session_id=session_id, limit=10)[-10:]:
                if item.role in {"user", "assistant"} and item.content:
                    history.append(ReplayAiChatMessage(role=item.role, content=item.content))
        return history

    def _validate_block_scope(self, session: StoredChatSession, block_ids: list[str]) -> None:
        for block_id in block_ids:
            block = self._repository.get_prompt_block(block_id)
            if block is None:
                raise ReplayWorkbenchChatError(f"Prompt block '{block_id}' not found.")
            if block.session_id != session.session_id and (block.symbol != session.symbol or block.contract_id != session.contract_id):
                raise ReplayWorkbenchChatError("PROMPT_BLOCK_SCOPE_MISMATCH")

    def _find_latest_replay_ingestion_for_symbol(self, symbol: str) -> StoredIngestion | None:
        for item in self._repository.list_ingestions(ingestion_kind="replay_workbench_snapshot", instrument_symbol=symbol, limit=20):
            return item
        return None

    def _find_latest_replay_ingestion_id_for_symbol(self, symbol: str) -> str | None:
        item = self._find_latest_replay_ingestion_for_symbol(symbol)
        return item.ingestion_id if item is not None else None

    def _get_latest_message(self, session_id: str, role: str | None = None) -> StoredChatMessage | None:
        messages = self._repository.list_chat_messages(session_id=session_id, limit=50)
        for item in reversed(messages):
            if role is None or item.role == role:
                return item
        return None

    def _require_stored_session(self, session_id: str) -> StoredChatSession:
        session = self._repository.get_chat_session(session_id)
        if session is None:
            raise ReplayWorkbenchNotFoundError(f"Chat session '{session_id}' not found.")
        return session

    def _require_session(self, session_id: str) -> ChatSession:
        return self._session_model(self._require_stored_session(session_id))

    def _session_model(self, stored: StoredChatSession) -> ChatSession:
        return ChatSession(
            session_id=stored.session_id,
            workspace_id=stored.workspace_id,
            title=stored.title,
            symbol=stored.symbol,
            contract_id=stored.contract_id,
            timeframe=stored.timeframe,
            window_range=ChatWindowRange.model_validate(stored.window_range),
            active_model=stored.active_model,
            status=stored.status,
            draft_text=stored.draft_text,
            draft_attachments=stored.draft_attachments,
            selected_prompt_block_ids=stored.selected_prompt_block_ids,
            pinned_context_block_ids=stored.pinned_context_block_ids,
            mounted_reply_ids=stored.mounted_reply_ids,
            active_plan_id=stored.active_plan_id,
            memory_summary_id=stored.memory_summary_id,
            unread_count=stored.unread_count,
            scroll_offset=stored.scroll_offset,
            pinned=stored.pinned,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _message_model(self, stored: StoredChatMessage) -> ChatMessage:
        return ChatMessage(
            message_id=stored.message_id,
            session_id=stored.session_id,
            parent_message_id=stored.parent_message_id,
            role=stored.role,
            content=stored.content,
            status=stored.status,
            reply_title=stored.reply_title,
            stream_buffer=stored.stream_buffer,
            model=stored.model,
            annotations=stored.annotations,
            plan_cards=stored.plan_cards,
            mounted_to_chart=stored.mounted_to_chart,
            mounted_object_ids=stored.mounted_object_ids,
            is_key_conclusion=stored.is_key_conclusion,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _prompt_block_model(self, stored: StoredPromptBlock) -> PromptBlock:
        return PromptBlock(
            block_id=stored.block_id,
            session_id=stored.session_id,
            symbol=stored.symbol,
            contract_id=stored.contract_id,
            timeframe=stored.timeframe,
            kind=stored.kind,
            title=stored.title,
            preview_text=stored.preview_text,
            full_payload=stored.full_payload,
            selected_by_default=stored.selected_by_default,
            pinned=stored.pinned,
            ephemeral=stored.ephemeral,
            created_at=stored.created_at,
            expires_at=stored.expires_at,
        )

    def _memory_model(self, stored: StoredSessionMemory | None) -> SessionMemory | None:
        if stored is None:
            return None
        return SessionMemory(
            memory_summary_id=stored.memory_summary_id,
            session_id=stored.session_id,
            summary_version=stored.summary_version,
            active_model=stored.active_model,
            symbol=stored.symbol,
            contract_id=stored.contract_id,
            timeframe=stored.timeframe,
            window_range=ChatWindowRange.model_validate(stored.window_range),
            user_goal_summary=stored.user_goal_summary,
            market_context_summary=stored.market_context_summary,
            key_zones_summary=stored.key_zones_summary,
            active_plans_summary=stored.active_plans_summary,
            invalidated_plans_summary=stored.invalidated_plans_summary,
            important_messages=stored.important_messages,
            current_user_intent=stored.current_user_intent,
            latest_question=stored.latest_question,
            latest_answer_summary=stored.latest_answer_summary,
            selected_annotations=stored.selected_annotations,
            last_updated_at=stored.last_updated_at,
        )

    def _annotation_model(self, stored: StoredChatAnnotation) -> ChatAnnotation:
        return ChatAnnotation(
            annotation_id=stored.annotation_id,
            session_id=stored.session_id,
            message_id=stored.message_id,
            plan_id=stored.plan_id,
            symbol=stored.symbol,
            contract_id=stored.contract_id,
            timeframe=stored.timeframe,
            type=stored.annotation_type,
            subtype=stored.subtype,
            label=stored.label,
            reason=stored.reason,
            start_time=stored.start_time,
            end_time=stored.end_time,
            expires_at=stored.expires_at,
            status=stored.status,
            priority=stored.priority,
            confidence=stored.confidence,
            visible=stored.visible,
            pinned=stored.pinned,
            source_kind=stored.source_kind,
            payload=stored.payload,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _plan_card_model(self, stored: StoredChatPlanCard) -> ChatPlanCard:
        return ChatPlanCard(
            plan_id=stored.plan_id,
            session_id=stored.session_id,
            message_id=stored.message_id,
            title=stored.title,
            side=stored.side,
            entry_type=stored.entry_type,
            entry_price=stored.entry_price,
            entry_price_low=stored.entry_price_low,
            entry_price_high=stored.entry_price_high,
            stop_price=stored.stop_price,
            take_profits=stored.take_profits,
            invalidations=stored.invalidations,
            time_validity=stored.time_validity,
            risk_reward=stored.risk_reward,
            confidence=stored.confidence,
            priority=stored.priority,
            status=stored.status,
            source_kind=stored.source_kind,
            notes=stored.notes,
            payload=stored.payload,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )


class ReplayWorkbenchService:
    """Stores replay-workbench packets and builds replay snapshots from local adapter history."""

    _TIMEFRAME_MINUTES: dict[Timeframe, int] = {
        Timeframe.MIN_1: 1,
        Timeframe.MIN_5: 5,
        Timeframe.MIN_15: 15,
        Timeframe.MIN_30: 30,
        Timeframe.HOUR_1: 60,
        Timeframe.DAY_1: 1440,
    }
    _INITIAL_WINDOW_BARS: dict[Timeframe, int] = {
        Timeframe.MIN_1: 180,   # 3h
        Timeframe.MIN_5: 144,   # 12h
        Timeframe.MIN_15: 96,   # 1d
        Timeframe.MIN_30: 96,   # 2d
        Timeframe.HOUR_1: 72,   # 3d
        Timeframe.DAY_1: 30,    # 30d
    }

    # Defensive limit: never insert an unbounded amount of synthetic filler bars.
    # (UI would choke, and it usually indicates upstream history coverage issues.)
    _MAX_GAP_FILL_BARS: int = 600
    _BACKFILL_REQUEST_TTL = timedelta(minutes=5)
    _BACKFILL_DISPATCH_LEASE = timedelta(seconds=12)
    _BACKFILL_RECORD_RETENTION = timedelta(hours=2)

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._backfill_lock = Lock()
        self._backfill_requests: dict[str, ReplayWorkbenchAtasBackfillRecord] = {}

    def ingest_replay_snapshot(self, payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchAcceptedResponse:
        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="replay_workbench_snapshot",
            source_snapshot_id=payload.replay_snapshot_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayWorkbenchAcceptedResponse(
            ingestion_id=ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            stored_at=stored_at,
            summary=self._build_summary(payload),
        )

    def _build_integrity(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        candle_gaps: list[dict[str, Any]] | None,
        latest_backfill_request: ReplayWorkbenchAtasBackfillRecord | None = None,
        status_override: str | None = None,
        window_days: int = 7,
    ) -> ReplayWorkbenchIntegrity:
        missing_segments = self._gap_segments_from_gap_dicts(candle_gaps or [])
        missing_bar_count = sum(segment.missing_bar_count for segment in missing_segments)
        if status_override is not None:
            status = status_override
        elif missing_segments:
            status = "gaps_detected"
        else:
            status = "complete"
        return ReplayWorkbenchIntegrity(
            status=status,
            window_start=window_start,
            window_end=window_end,
            window_days=window_days,
            gap_count=len(missing_segments),
            missing_bar_count=missing_bar_count,
            missing_segments=missing_segments,
            latest_backfill_request_id=latest_backfill_request.request_id if latest_backfill_request is not None else None,
            latest_backfill_status=latest_backfill_request.status if latest_backfill_request is not None else None,
        )

    @staticmethod
    def _gap_segments_from_gap_dicts(candle_gaps: list[dict[str, Any]]) -> list[ReplayWorkbenchGapSegment]:
        segments: list[ReplayWorkbenchGapSegment] = []
        for item in candle_gaps:
            next_started_at = item.get("next_started_at")
            missing_bar_count = item.get("missing_bar_count")
            if next_started_at is None or missing_bar_count is None:
                continue
            prev_ended_at = item.get("prev_ended_at")
            segments.append(
                ReplayWorkbenchGapSegment(
                    prev_ended_at=prev_ended_at,
                    next_started_at=next_started_at,
                    missing_bar_count=max(1, int(missing_bar_count)),
                )
            )
        return segments

    def _find_latest_backfill_request(
        self,
        *,
        cache_key: str | None,
        instrument_symbol: str,
        display_timeframe: Timeframe,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        with self._backfill_lock:
            now = datetime.now(tz=UTC)
            self._expire_backfill_requests_locked(now)
            candidates = [
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and record.display_timeframe == display_timeframe
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda item: item.requested_at, reverse=True)
            if cache_key is not None:
                exact = [record for record in candidates if record.cache_key == cache_key]
                if exact:
                    return exact[0]
            return candidates[0]

    def _maybe_request_backfill_for_integrity(
        self,
        *,
        cache_key: str,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        chart_instance_id: str | None,
        integrity: ReplayWorkbenchIntegrity,
        reason: str,
        request_history_bars: bool = True,
        request_history_footprint: bool = True,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        if not integrity.missing_segments and integrity.status != "missing_local_history":
            return None
        accepted = self.request_atas_backfill(
            ReplayWorkbenchAtasBackfillRequest(
                cache_key=cache_key,
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                window_start=window_start,
                window_end=window_end,
                chart_instance_id=chart_instance_id,
                missing_segments=integrity.missing_segments,
                reason=reason,
                request_history_bars=request_history_bars,
                request_history_footprint=request_history_footprint,
            )
        )
        return accepted.request

    def _with_backfill_metadata(
        self,
        integrity: ReplayWorkbenchIntegrity,
        backfill_request: ReplayWorkbenchAtasBackfillRecord | None,
    ) -> ReplayWorkbenchIntegrity:
        if backfill_request is None:
            return integrity
        return integrity.model_copy(
            update={
                "latest_backfill_request_id": backfill_request.request_id,
                "latest_backfill_status": backfill_request.status,
            }
        )

    def get_cache_record(self, cache_key: str, allow_fuzzy: bool = False) -> ReplayWorkbenchCacheEnvelope:
        stored = self._find_latest_replay_snapshot(cache_key=cache_key)
        matched_cache_key = cache_key

        if stored is None and allow_fuzzy:
            fuzzy_match = self._find_latest_replay_snapshot_by_cache_identity(cache_key)
            if fuzzy_match is not None:
                matched_cache_key, stored = fuzzy_match

        if stored is None:
            return ReplayWorkbenchCacheEnvelope(
                cache_key=cache_key,
                record=None,
                auto_fetch_allowed=True,
                verification_due_now=False,
            )

        payload = ReplayWorkbenchSnapshotPayload.model_validate(stored.observed_payload)
        verification_due_now = self._is_verification_due(payload=payload)
        auto_fetch_allowed = self._is_auto_fetch_allowed(payload=payload)
        return ReplayWorkbenchCacheEnvelope(
            cache_key=matched_cache_key,
            record=self._build_cache_record(stored, payload),
            auto_fetch_allowed=auto_fetch_allowed,
            verification_due_now=verification_due_now,
        )

    def invalidate_cache_record(self, request: ReplayWorkbenchInvalidationRequest) -> ReplayWorkbenchInvalidationResponse:
        stored = self._find_latest_replay_snapshot(
            cache_key=request.cache_key,
            replay_snapshot_id=request.replay_snapshot_id,
            ingestion_id=request.ingestion_id,
        )
        if stored is None:
            raise ReplayWorkbenchNotFoundError("No replay cache record matched the invalidation request.")

        payload = ReplayWorkbenchSnapshotPayload.model_validate(stored.observed_payload)
        invalidated_at = datetime.now(tz=UTC)
        payload.verification_state.status = ReplayVerificationStatus.INVALIDATED
        payload.verification_state.invalidated_at = invalidated_at
        payload.verification_state.invalidation_reason = request.invalidation_reason
        payload.verification_state.locked_until_manual_reset = False
        payload.verification_state.next_verification_due_at = None

        updated = self._repository.update_ingestion_observed_payload(
            ingestion_id=stored.ingestion_id,
            observed_payload=payload.model_dump(mode="json"),
        )
        if updated is None:
            raise ReplayWorkbenchNotFoundError(f"Replay cache record '{stored.ingestion_id}' disappeared before invalidation.")

        return ReplayWorkbenchInvalidationResponse(
            ingestion_id=stored.ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            cache_key=payload.cache_key,
            invalidated_at=invalidated_at,
            invalidation_reason=request.invalidation_reason,
            verification_status=payload.verification_state.status,
            locked_until_manual_reset=payload.verification_state.locked_until_manual_reset,
        )

    def get_live_status(
        self,
        *,
        instrument_symbol: str,
        replay_ingestion_id: str | None = None,
    ) -> ReplayWorkbenchLiveStatusResponse:
        now = datetime.now(tz=UTC)
        latest_continuous_state = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=instrument_symbol,
        )
        latest_history_bars = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_history_bars",
            instrument_symbol=instrument_symbol,
        )
        latest_history_footprint = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_history_footprint",
            instrument_symbol=instrument_symbol,
        )

        latest_times = [
            item.latest_stored_at
            for item in (latest_continuous_state, latest_history_bars, latest_history_footprint)
            if item.latest_stored_at is not None
        ]
        latest_adapter_sync_at = max(latest_times) if latest_times else None
        latest_adapter_sync_lag_seconds = (
            max(0, int((now - latest_adapter_sync_at).total_seconds()))
            if latest_adapter_sync_at is not None
            else None
        )

        if latest_adapter_sync_lag_seconds is None:
            stream_state = ReplayLiveStreamState.OFFLINE
        elif latest_adapter_sync_lag_seconds <= 10:
            stream_state = ReplayLiveStreamState.LIVE
        elif latest_adapter_sync_lag_seconds <= 60:
            stream_state = ReplayLiveStreamState.DELAYED
        else:
            stream_state = ReplayLiveStreamState.STALE

        replay_snapshot_stored_at: datetime | None = None
        if replay_ingestion_id is not None:
            replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
            if replay_ingestion is not None:
                replay_snapshot_stored_at = replay_ingestion.stored_at

        should_refresh_snapshot = bool(
            latest_adapter_sync_at is not None
            and (
                replay_snapshot_stored_at is None
                or latest_adapter_sync_at > replay_snapshot_stored_at
            )
        )

        return ReplayWorkbenchLiveStatusResponse(
            instrument_symbol=instrument_symbol,
            replay_ingestion_id=replay_ingestion_id,
            replay_snapshot_stored_at=replay_snapshot_stored_at,
            latest_adapter_sync_at=latest_adapter_sync_at,
            latest_adapter_sync_lag_seconds=latest_adapter_sync_lag_seconds,
            stream_state=stream_state,
            should_refresh_snapshot=should_refresh_snapshot,
            latest_continuous_state=latest_continuous_state,
            latest_history_bars=latest_history_bars,
            latest_history_footprint=latest_history_footprint,
        )

    def get_live_tail(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None = None,
        lookback_bars: int = 4,
    ) -> ReplayWorkbenchLiveTailResponse:
        # Pull enough recent continuous-state messages to build `lookback_bars` candles.
        # Repository only supports "latest N" so we oversample and filter by time cutoff.
        timeframe_minutes = self._TIMEFRAME_MINUTES.get(display_timeframe, 1)
        required_minutes = (timeframe_minutes * max(lookback_bars, 2)) + 3
        estimated_messages_per_minute = 6  # ~10s cadence (tune if adapter cadence changes)
        candidates_limit = int(required_minutes * estimated_messages_per_minute * 3)
        candidates_limit = max(5000, min(50000, candidates_limit))

        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=instrument_symbol,
            limit=candidates_limit,
        )
        matched: list[tuple[datetime, StoredIngestion]] = []
        latest_payload: dict[str, Any] | None = None
        latest_observed_at: datetime | None = None
        for stored in candidates:
            payload = stored.observed_payload
            if chart_instance_id is not None and payload.get("source", {}).get("chart_instance_id") != chart_instance_id:
                continue
            observed_at = self._payload_observed_at(payload)
            matched.append((observed_at, stored))
            if latest_observed_at is None or observed_at > latest_observed_at:
                latest_observed_at = observed_at
                latest_payload = payload

        if latest_observed_at is None or latest_payload is None:
            return ReplayWorkbenchLiveTailResponse(
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                latest_observed_at=None,
                latest_price=None,
                best_bid=None,
                best_ask=None,
                source_message_count=0,
                candles=[],
                trade_summary=None,
                significant_liquidity=[],
                same_price_replenishment=[],
                active_initiative_drive=None,
                active_post_harvest_response=None,
                integrity=self._build_integrity(
                    window_start=datetime.now(tz=UTC) - timedelta(days=7),
                    window_end=datetime.now(tz=UTC),
                    candle_gaps=[],
                    latest_backfill_request=self._find_latest_backfill_request(
                        cache_key=f"{instrument_symbol}|{display_timeframe}|empty|empty",
                        instrument_symbol=instrument_symbol,
                        display_timeframe=display_timeframe,
                    ),
                    status_override="no_live_data",
                ),
                snapshot_refresh_required=False,
                latest_backfill_request=None,
            )

        recent_cutoff = latest_observed_at - timedelta(
            minutes=(self._TIMEFRAME_MINUTES.get(display_timeframe, 1) * max(lookback_bars, 2)) + 1
        )
        recent_messages = [stored for observed_at, stored in matched if observed_at >= recent_cutoff]
        recent_messages.sort(key=lambda item: self._payload_observed_at(item.observed_payload))
        live_candles = self._build_candles(display_timeframe, recent_messages)[-max(lookback_bars, 1):]

        # --- auto gap-fill: patch holes in live candles using history-bars ---
        live_candles = self._patch_live_candle_gaps(
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=chart_instance_id,
            candles=live_candles,
        )

        # --- still expose remaining gaps as explicit synthetic bars (so UI can see missing time) ---
        live_candles, candle_gaps, _ = self._fill_candle_time_gaps(live_candles, display_timeframe)

        cache_key = None
        if live_candles:
            cache_key = "|".join([
                instrument_symbol,
                str(display_timeframe),
                live_candles[0].started_at.isoformat().replace("+00:00", "Z"),
                live_candles[-1].ended_at.isoformat().replace("+00:00", "Z"),
            ])
        latest_backfill_request = (
            self._find_latest_backfill_request(
                cache_key=cache_key,
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
            )
            if cache_key is not None
            else None
        )
        integrity = self._build_integrity(
            window_start=live_candles[0].started_at if live_candles else latest_observed_at - timedelta(days=7),
            window_end=live_candles[-1].ended_at if live_candles else latest_observed_at,
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        snapshot_refresh_required = bool(
            latest_backfill_request is not None
            and latest_backfill_request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED
            and integrity.status == "complete"
        )

        price_state = latest_payload.get("price_state", {})
        return ReplayWorkbenchLiveTailResponse(
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            latest_observed_at=latest_observed_at,
            latest_price=price_state.get("last_price"),
            best_bid=price_state.get("best_bid"),
            best_ask=price_state.get("best_ask"),
            source_message_count=len(recent_messages),
            candles=live_candles,
            trade_summary=payload_to_model(latest_payload.get("trade_summary"), AdapterTradeSummary),
            significant_liquidity=[
                model
                for model in (
                    payload_to_model(item, AdapterSignificantLiquidityLevel)
                    for item in latest_payload.get("significant_liquidity", [])
                )
                if model is not None
            ],
            same_price_replenishment=[
                model
                for model in (
                    payload_to_model(item, AdapterSamePriceReplenishmentState)
                    for item in latest_payload.get("same_price_replenishment", [])
                )
                if model is not None
            ],
            active_initiative_drive=payload_to_model(
                latest_payload.get("active_initiative_drive"),
                AdapterInitiativeDriveState,
            ),
            active_post_harvest_response=payload_to_model(
                latest_payload.get("active_post_harvest_response"),
                AdapterPostHarvestResponseState,
            ),
            integrity=integrity,
            snapshot_refresh_required=snapshot_refresh_required,
            latest_backfill_request=latest_backfill_request,
        )

    def rebuild_cache_from_latest_sync(
        self,
        request: ReplayWorkbenchRebuildLatestRequest,
    ) -> ReplayWorkbenchRebuildLatestResponse:
        cache = self.get_cache_record(request.cache_key)
        invalidation_result: ReplayWorkbenchInvalidationResponse | None = None
        invalidated_existing_cache = False
        if cache.record is not None and cache.record.verification_state.status != ReplayVerificationStatus.INVALIDATED:
            invalidation_result = self.invalidate_cache_record(
                ReplayWorkbenchInvalidationRequest(
                    cache_key=request.cache_key,
                    invalidation_reason=request.invalidation_reason,
                )
            )
            invalidated_existing_cache = True

        build_result = self.build_replay_snapshot(
            ReplayWorkbenchBuildRequest(
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                force_rebuild=True,
                min_continuous_messages=request.min_continuous_messages,
            )
        )
        return ReplayWorkbenchRebuildLatestResponse(
            cache_key=request.cache_key,
            invalidated_existing_cache=invalidated_existing_cache,
            invalidation_result=invalidation_result,
            build_result=build_result,
        )

    def request_atas_backfill(
        self,
        request: ReplayWorkbenchAtasBackfillRequest,
    ) -> ReplayWorkbenchAtasBackfillAcceptedResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            reusable = self._find_reusable_backfill_request_locked(request, now)
            if reusable is not None:
                return ReplayWorkbenchAtasBackfillAcceptedResponse(
                    request=reusable,
                    reused_existing_request=True,
                )

            record = ReplayWorkbenchAtasBackfillRecord(
                request_id=f"atas-backfill-{uuid4().hex}",
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                missing_segments=request.missing_segments,
                reason=request.reason,
                request_history_bars=request.request_history_bars,
                request_history_footprint=request.request_history_footprint,
                status=ReplayWorkbenchAtasBackfillStatus.PENDING,
                requested_at=now,
                expires_at=now + self._BACKFILL_REQUEST_TTL,
                dispatch_count=0,
            )
            self._backfill_requests[record.request_id] = record
            self._prune_backfill_requests_locked(now)
            return ReplayWorkbenchAtasBackfillAcceptedResponse(
                request=record,
                reused_existing_request=False,
            )

    def poll_atas_backfill(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None = None,
    ) -> AdapterBackfillDispatchResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            for record in self._iter_matching_backfill_requests_locked(
                instrument_symbol=instrument_symbol,
                chart_instance_id=chart_instance_id,
            ):
                if not self._is_backfill_dispatchable(record, now):
                    continue
                updated = record.model_copy(
                    update={
                        "status": ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
                        "dispatch_count": record.dispatch_count + 1,
                        "dispatched_at": now,
                        "dispatched_chart_instance_id": chart_instance_id,
                    }
                )
                self._backfill_requests[record.request_id] = updated
                return AdapterBackfillDispatchResponse(
                    instrument_symbol=instrument_symbol,
                    chart_instance_id=chart_instance_id,
                    polled_at=now,
                    request=self._build_backfill_command(updated),
                )

        return AdapterBackfillDispatchResponse(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            polled_at=now,
            request=None,
        )

    def acknowledge_atas_backfill(
        self,
        request: AdapterBackfillAcknowledgeRequest,
    ) -> AdapterBackfillAcknowledgeResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            record = self._backfill_requests.get(request.request_id)
            if record is None:
                raise ReplayWorkbenchNotFoundError(
                    f"ATAS backfill request '{request.request_id}' not found."
                )

            updated = record.model_copy(
                update={
                    "status": ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED,
                    "acknowledged_at": request.acknowledged_at,
                    "acknowledged_chart_instance_id": request.chart_instance_id,
                    "acknowledged_history_bars": request.acknowledged_history_bars,
                    "acknowledged_history_footprint": request.acknowledged_history_footprint,
                    "latest_loaded_bar_started_at": request.latest_loaded_bar_started_at,
                    "note": request.note,
                }
            )
            self._backfill_requests[request.request_id] = updated
            self._prune_backfill_requests_locked(now)

        verification = self._verify_acknowledged_backfill(updated)
        rebuild_result = ReplayWorkbenchAckRebuildResult(triggered=False, build_result=None)
        if verification.verified:
            rebuild_result = ReplayWorkbenchAckRebuildResult(
                triggered=True,
                build_result=self.build_replay_snapshot(
                    ReplayWorkbenchBuildRequest(
                        cache_key=updated.cache_key,
                        instrument_symbol=updated.instrument_symbol,
                        display_timeframe=updated.display_timeframe,
                        window_start=updated.window_start,
                        window_end=updated.window_end,
                        chart_instance_id=updated.chart_instance_id,
                        force_rebuild=True,
                        min_continuous_messages=1,
                    )
                ),
            )

        return AdapterBackfillAcknowledgeResponse(
            request=updated,
            verification=verification,
            rebuild_result=rebuild_result,
        )

    def _verify_acknowledged_backfill(
        self,
        request: ReplayWorkbenchAtasBackfillRecord,
    ) -> ReplayWorkbenchAckVerification:
        build_request = ReplayWorkbenchBuildRequest(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
            window_start=request.window_start,
            window_end=request.window_end,
            chart_instance_id=request.chart_instance_id,
            force_rebuild=False,
            min_continuous_messages=1,
        )
        history_payload = self._find_matching_history_payload(build_request)
        footprint_payloads = self._find_matching_history_footprint_payloads(build_request)
        if history_payload is None:
            return ReplayWorkbenchAckVerification(
                verified=False,
                bars_verified=False,
                footprint_available=bool(footprint_payloads),
                requested_window_start=request.window_start,
                requested_window_end=request.window_end,
                covered_window_start=None,
                covered_window_end=None,
                missing_segment_count=len(request.missing_segments),
                note="history bars not found after ack",
            )

        candles = self._build_candles_from_history_payload(history_payload, build_request)
        filtered = [
            candle for candle in candles
            if candle.ended_at >= request.window_start and candle.started_at <= request.window_end
        ]
        covered_window_start = filtered[0].started_at if filtered else None
        covered_window_end = filtered[-1].ended_at if filtered else None

        remaining_segments: list[ReplayWorkbenchGapSegment] = []
        for segment in request.missing_segments:
            segment_has_coverage = any(
                candle.started_at <= segment.next_started_at and candle.ended_at >= segment.next_started_at
                for candle in filtered
            )
            if not segment_has_coverage:
                remaining_segments.append(segment)

        verified = bool(filtered) and not remaining_segments
        return ReplayWorkbenchAckVerification(
            verified=verified,
            bars_verified=bool(filtered),
            footprint_available=bool(footprint_payloads),
            requested_window_start=request.window_start,
            requested_window_end=request.window_end,
            covered_window_start=covered_window_start,
            covered_window_end=covered_window_end,
            missing_segment_count=len(remaining_segments),
            note=None if verified else "history coverage still incomplete after ack",
        )

    def build_replay_snapshot(self, request: ReplayWorkbenchBuildRequest) -> ReplayWorkbenchBuildResponse:
        history_payload = self._find_matching_history_payload(request)
        footprint_payloads = self._find_matching_history_footprint_payloads(request)
        cache = self.get_cache_record(request.cache_key)
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        if not request.force_rebuild and cache.record is not None and cache.record.verification_state.status != ReplayVerificationStatus.INVALIDATED:
            cached_ingestion = self._repository.get_ingestion(cache.record.ingestion_id)
            if cached_ingestion is not None and not self._history_snapshot_should_refresh(request, cached_ingestion, history_payload):
                payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
                integrity = payload.integrity or self._build_integrity(
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    candle_gaps=payload.raw_features.get("candle_gaps") or [],
                    latest_backfill_request=latest_backfill_request,
                )
                backfill_request = None
                if integrity.status != "complete":
                    backfill_request = self._maybe_request_backfill_for_integrity(
                        cache_key=request.cache_key,
                        instrument_symbol=request.instrument_symbol,
                        display_timeframe=request.display_timeframe,
                        window_start=request.window_start,
                        window_end=request.window_end,
                        chart_instance_id=request.chart_instance_id,
                        integrity=integrity,
                        reason="snapshot_gap_detected",
                    )
                    integrity = self._with_backfill_metadata(integrity, backfill_request)
                return ReplayWorkbenchBuildResponse(
                    action=ReplayWorkbenchBuildAction.CACHE_HIT,
                    cache_key=request.cache_key,
                    reason="Replay cache already exists and is still eligible for reuse.",
                    local_message_count=0,
                    replay_snapshot_id=payload.replay_snapshot_id,
                    ingestion_id=cache.record.ingestion_id,
                    summary=self._build_summary(payload),
                    cache_record=cache.record,
                    atas_fetch_request=None,
                    atas_backfill_request=backfill_request,
                    integrity=integrity,
                )

        continuous_messages = self._collect_matching_continuous_messages(request)
        if history_payload is not None:
            payload = self._build_snapshot_from_history_bars(
                request,
                history_payload,
                continuous_messages,
                footprint_payloads,
            )
            accepted = self.ingest_replay_snapshot(payload)
            cache_after = self.get_cache_record(request.cache_key)
            return ReplayWorkbenchBuildResponse(
                action=ReplayWorkbenchBuildAction.BUILT_FROM_ATAS_HISTORY,
                cache_key=request.cache_key,
                reason="Replay packet rebuilt from ATAS chart-loaded history bars.",
                local_message_count=len(continuous_messages),
                replay_snapshot_id=accepted.replay_snapshot_id,
                ingestion_id=accepted.ingestion_id,
                summary=accepted.summary,
                cache_record=cache_after.record,
                atas_fetch_request=None,
                atas_backfill_request=None,
                integrity=payload.integrity,
            )

        if len(continuous_messages) < request.min_continuous_messages:
            integrity = self._build_integrity(
                window_start=request.window_start,
                window_end=request.window_end,
                candle_gaps=[],
                latest_backfill_request=latest_backfill_request,
                status_override="missing_local_history",
            )
            backfill_request = self._maybe_request_backfill_for_integrity(
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                integrity=integrity,
                reason="local_history_insufficient",
            )
            integrity = self._with_backfill_metadata(integrity, backfill_request)
            return ReplayWorkbenchBuildResponse(
                action=ReplayWorkbenchBuildAction.ATAS_FETCH_REQUIRED,
                cache_key=request.cache_key,
                reason="Local adapter history is insufficient for this replay window.",
                local_message_count=len(continuous_messages),
                replay_snapshot_id=None,
                ingestion_id=None,
                summary=None,
                cache_record=cache.record,
                atas_fetch_request={
                    "instrument_symbol": request.instrument_symbol,
                    "display_timeframe": request.display_timeframe,
                    "window_start": request.window_start,
                    "window_end": request.window_end,
                    "chart_instance_id": None,
                    "fetch_only_when_missing": True,
                },
                atas_backfill_request=backfill_request,
                integrity=integrity,
            )

        payload = self._build_snapshot_from_local_history(request, continuous_messages)
        accepted = self.ingest_replay_snapshot(payload)
        cache_after = self.get_cache_record(request.cache_key)
        backfill_request = None
        integrity = payload.integrity
        if integrity is not None and integrity.status != "complete":
            backfill_request = self._maybe_request_backfill_for_integrity(
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                integrity=integrity,
                reason="candle_gap_detected",
            )
            integrity = self._with_backfill_metadata(integrity, backfill_request)
        return ReplayWorkbenchBuildResponse(
            action=ReplayWorkbenchBuildAction.BUILT_FROM_LOCAL_HISTORY,
            cache_key=request.cache_key,
            reason="Replay packet rebuilt from locally stored adapter history.",
            local_message_count=len(continuous_messages),
            replay_snapshot_id=accepted.replay_snapshot_id,
            ingestion_id=accepted.ingestion_id,
            summary=accepted.summary,
            cache_record=cache_after.record,
            atas_fetch_request=None,
            atas_backfill_request=backfill_request,
            integrity=integrity,
        )

    def _build_snapshot_from_history_bars(
        self,
        request: ReplayWorkbenchBuildRequest,
        history_payload: AdapterHistoryBarsPayload,
        continuous_messages: list[StoredIngestion],
        footprint_payloads: list[AdapterHistoryFootprintPayload],
    ) -> ReplayWorkbenchSnapshotPayload:
        created_at = datetime.now(tz=UTC)
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        candles = self._build_candles_from_history_payload(history_payload, request)
        if not candles:
            return self._build_snapshot_from_local_history(request, continuous_messages)
        continuous_overlay_count = 0
        if continuous_messages:
            candles, continuous_overlay_count = self._merge_history_candles_with_continuous_overlay(
                history_candles=candles,
                continuous_messages=continuous_messages,
                timeframe=request.display_timeframe,
            )

        # Detect + fill any remaining candle gaps so the UI does not silently compress missing time.
        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)
        candles, initial_window_applied, initial_window_bar_limit = self._apply_initial_snapshot_window(
            candles,
            request.display_timeframe,
        )

        actual_window_start = candles[0].started_at
        actual_window_end = candles[-1].ended_at
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        integrity = self._build_integrity(
            window_start=request.window_start,
            window_end=request.window_end,
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        event_annotations = self._build_event_annotations(continuous_messages) if continuous_messages else []
        focus_regions = self._build_focus_regions(continuous_messages, event_annotations) if continuous_messages else []
        if footprint_payloads:
            event_annotations.extend(self._build_footprint_event_annotations(footprint_payloads, history_payload.instrument.tick_size, request))
            focus_regions.extend(self._build_footprint_focus_regions(footprint_payloads, history_payload.instrument.tick_size, request))
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)
        footprint_digest = self._build_footprint_digest(footprint_payloads, request) if footprint_payloads else None

        return ReplayWorkbenchSnapshotPayload(
            schema_version="1.1.0",
            replay_snapshot_id=replay_snapshot_id,
            cache_key=request.cache_key,
            acquisition_mode=ReplayAcquisitionMode.ATAS_FETCH,
            created_at=created_at,
            source=history_payload.source,
            instrument=history_payload.instrument,
            display_timeframe=request.display_timeframe,
            window_start=actual_window_start,
            window_end=actual_window_end,
            cache_policy=ReplayCachePolicy(),
            verification_state=ReplayVerificationState(
                status=ReplayVerificationStatus.UNVERIFIED,
                verification_count=0,
                last_verified_at=None,
                next_verification_due_at=created_at,
                invalidated_at=None,
                invalidation_reason=None,
                locked_until_manual_reset=False,
            ),
            integrity=integrity,
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": "adapter_history_bars",
                "history_message_id": history_payload.message_id,
                "history_bar_timeframe": history_payload.bar_timeframe,
                "history_bar_count": len(history_payload.bars),
                "history_coverage_start": history_payload.observed_window_start,
                "history_coverage_end": history_payload.observed_window_end,
                "requested_window_start": request.window_start,
                "requested_window_end": request.window_end,
                "actual_window_start": actual_window_start,
                "actual_window_end": actual_window_end,
                "history_footprint_available": bool(footprint_payloads),
                "history_footprint_digest": footprint_digest,
                "local_message_count": len(continuous_messages),
                "continuous_overlay_candle_count": continuous_overlay_count,
                "candle_gap_count": len(candle_gaps),
                "candle_gap_missing_bar_count": sum(item["missing_bar_count"] for item in candle_gaps),
                "candle_gap_fill_bar_count": gap_fill_bar_count,
                "candle_gaps": candle_gaps,
                "build_reason": "atas_chart_loaded_history_rebuild",
                "initial_window_applied": initial_window_applied,
                "initial_window_bar_limit": initial_window_bar_limit,
            },
        )

    def _get_latest_ingestion_status(
        self,
        *,
        now: datetime,
        ingestion_kind: str,
        instrument_symbol: str,
    ) -> ReplayWorkbenchLiveSourceStatus:
        latest = self._repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            limit=1,
        )
        if not latest:
            return ReplayWorkbenchLiveSourceStatus(
                ingestion_kind=ingestion_kind,
                latest_ingestion_id=None,
                latest_stored_at=None,
                lag_seconds=None,
            )

        latest_item = latest[0]
        return ReplayWorkbenchLiveSourceStatus(
            ingestion_kind=ingestion_kind,
            latest_ingestion_id=latest_item.ingestion_id,
            latest_stored_at=latest_item.stored_at,
            lag_seconds=max(0, int((now - latest_item.stored_at).total_seconds())),
        )

    def record_operator_entry(self, request: ReplayOperatorEntryRequest) -> ReplayOperatorEntryAcceptedResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        stored_at = datetime.now(tz=UTC)
        entry = ReplayOperatorEntryRecord(
            entry_id=f"entry-{uuid4().hex}",
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            chart_instance_id=replay_payload.source.chart_instance_id,
            executed_at=request.executed_at,
            side=request.side,
            entry_price=request.entry_price,
            quantity=request.quantity,
            stop_price=request.stop_price,
            target_price=request.target_price,
            timeframe_context=request.timeframe_context,
            thesis=request.thesis,
            context_notes=request.context_notes,
            tags=request.tags,
            stored_at=stored_at,
        )
        self._repository.save_ingestion(
            ingestion_id=f"ing-{uuid4().hex}",
            ingestion_kind="replay_operator_entry",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=entry.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayOperatorEntryAcceptedResponse(entry=entry)

    def list_operator_entries(self, replay_ingestion_id: str) -> ReplayOperatorEntryEnvelope:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        entries: list[ReplayOperatorEntryRecord] = []
        for stored in self._repository.list_ingestions(ingestion_kind="replay_operator_entry", limit=1000):
            if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                continue
            entries.append(ReplayOperatorEntryRecord.model_validate(stored.observed_payload))
        entries.sort(key=lambda item: item.executed_at)
        return ReplayOperatorEntryEnvelope(
            replay_ingestion_id=replay_ingestion_id,
            entries=entries,
        )

    def record_manual_region(
        self,
        request: ReplayManualRegionAnnotationRequest,
    ) -> ReplayManualRegionAnnotationAcceptedResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        stored_at = datetime.now(tz=UTC)
        region = ReplayManualRegionAnnotationRecord(
            region_annotation_id=f"region-{uuid4().hex}",
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            label=request.label,
            thesis=request.thesis,
            price_low=request.price_low,
            price_high=request.price_high,
            started_at=request.started_at,
            ended_at=request.ended_at,
            side_bias=request.side_bias,
            notes=request.notes,
            tags=request.tags,
            stored_at=stored_at,
        )
        self._repository.save_ingestion(
            ingestion_id=f"ing-{uuid4().hex}",
            ingestion_kind="replay_manual_region",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=region.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayManualRegionAnnotationAcceptedResponse(region=region)

    def list_manual_regions(self, replay_ingestion_id: str) -> ReplayManualRegionAnnotationEnvelope:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        regions: list[ReplayManualRegionAnnotationRecord] = []
        for stored in self._repository.list_ingestions(ingestion_kind="replay_manual_region", limit=1000):
            if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                continue
            regions.append(ReplayManualRegionAnnotationRecord.model_validate(stored.observed_payload))
        regions.sort(key=lambda item: (item.started_at, item.price_low))
        return ReplayManualRegionAnnotationEnvelope(
            replay_ingestion_id=replay_ingestion_id,
            regions=regions,
        )

    def get_footprint_bar_detail(
        self,
        *,
        replay_ingestion_id: str,
        bar_started_at: datetime,
    ) -> ReplayFootprintBarDetail:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        matched_bar = self._find_history_footprint_bar(
            instrument_symbol=replay_payload.instrument.symbol,
            chart_instance_id=None,
            timeframe=replay_payload.display_timeframe,
            window_start=replay_payload.window_start,
            window_end=replay_payload.window_end,
            bar_started_at=bar_started_at,
        )
        if matched_bar is None:
            raise ReplayWorkbenchNotFoundError(
                f"No historical footprint detail found for {replay_payload.instrument.symbol} at {bar_started_at.isoformat()}."
            )

        return ReplayFootprintBarDetail(
            replay_ingestion_id=replay_ingestion_id,
            instrument_symbol=replay_payload.instrument.symbol,
            timeframe=replay_payload.display_timeframe,
            started_at=matched_bar.started_at,
            ended_at=matched_bar.ended_at,
            open=matched_bar.open,
            high=matched_bar.high,
            low=matched_bar.low,
            close=matched_bar.close,
            volume=matched_bar.volume,
            delta=matched_bar.delta,
            bid_volume=matched_bar.bid_volume,
            ask_volume=matched_bar.ask_volume,
            price_levels=[
                ReplayFootprintLevelDetail(
                    price=item.price,
                    bid_volume=item.bid_volume,
                    ask_volume=item.ask_volume,
                    total_volume=item.total_volume,
                    delta=item.delta,
                    trade_count=item.trade_count,
                )
                for item in sorted(matched_bar.price_levels, key=lambda level: level.price, reverse=True)
            ],
        )

    def _build_snapshot_from_local_history(
        self,
        request: ReplayWorkbenchBuildRequest,
        ingestions: list[StoredIngestion],
    ) -> ReplayWorkbenchSnapshotPayload:
        created_at = datetime.now(tz=UTC)
        first_payload = ingestions[0].observed_payload
        last_payload = ingestions[-1].observed_payload
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"

        candles = self._build_candles(request.display_timeframe, ingestions)
        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)
        candles, initial_window_applied, initial_window_bar_limit = self._apply_initial_snapshot_window(
            candles,
            request.display_timeframe,
        )
        actual_window_start = candles[0].started_at if candles else request.window_start
        actual_window_end = candles[-1].ended_at if candles else request.window_end
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        integrity = self._build_integrity(
            window_start=request.window_start,
            window_end=request.window_end,
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        event_annotations = self._build_event_annotations(ingestions)
        focus_regions = self._build_focus_regions(ingestions, event_annotations)
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)

        return ReplayWorkbenchSnapshotPayload(
            schema_version="1.1.0",
            replay_snapshot_id=replay_snapshot_id,
            cache_key=request.cache_key,
            acquisition_mode=ReplayAcquisitionMode.CACHE_REUSE,
            created_at=created_at,
            source=last_payload["source"],
            instrument=last_payload["instrument"],
            display_timeframe=request.display_timeframe,
            window_start=actual_window_start,
            window_end=actual_window_end,
            cache_policy=ReplayCachePolicy(),
            verification_state=ReplayVerificationState(
                status=ReplayVerificationStatus.UNVERIFIED,
                verification_count=0,
                last_verified_at=None,
                next_verification_due_at=created_at,
                invalidated_at=None,
                invalidation_reason=None,
                locked_until_manual_reset=False,
            ),
            integrity=integrity,
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": "adapter_continuous_state",
                "local_message_count": len(ingestions),
                "chart_instance_id": request.chart_instance_id or last_payload["source"].get("chart_instance_id"),
                "build_reason": "cache_miss_local_history_rebuild",
                "first_message_id": first_payload["message_id"],
                "last_message_id": last_payload["message_id"],
                "requested_window_start": request.window_start,
                "requested_window_end": request.window_end,
                "actual_window_start": actual_window_start,
                "actual_window_end": actual_window_end,
                "candle_gap_count": len(candle_gaps),
                "candle_gap_missing_bar_count": sum(item["missing_bar_count"] for item in candle_gaps),
                "candle_gap_fill_bar_count": gap_fill_bar_count,
                "candle_gaps": candle_gaps,
                "initial_window_applied": initial_window_applied,
                "initial_window_bar_limit": initial_window_bar_limit,
            },
        )

    def _collect_matching_continuous_messages(self, request: ReplayWorkbenchBuildRequest) -> list[StoredIngestion]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=request.instrument_symbol,
            limit=10000,
        )
        matched: list[StoredIngestion] = []
        for stored in candidates:
            payload = stored.observed_payload
            if request.chart_instance_id is not None and payload.get("source", {}).get("chart_instance_id") != request.chart_instance_id:
                continue
            window_start = datetime.fromisoformat(payload["observed_window_start"])
            window_end = datetime.fromisoformat(payload["observed_window_end"])
            if window_end < request.window_start or window_start > request.window_end:
                continue
            matched.append(stored)
        matched.sort(key=lambda item: item.observed_payload["emitted_at"])
        return matched

    def _apply_initial_snapshot_window(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], bool, int | None]:
        if not candles:
            return candles, False, None
        bar_limit = self._INITIAL_WINDOW_BARS.get(timeframe)
        if bar_limit is None or len(candles) <= bar_limit:
            return candles, False, bar_limit
        return candles[-bar_limit:], True, bar_limit

    def _find_matching_history_payload(self, request: ReplayWorkbenchBuildRequest) -> AdapterHistoryBarsPayload | None:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=request.instrument_symbol,
            limit=200,
        )
        matched_payloads: list[tuple[float, float, int, int, AdapterHistoryBarsPayload]] = []
        for stored in candidates:
            payload = AdapterHistoryBarsPayload.model_validate(stored.observed_payload)
            if request.chart_instance_id is not None and payload.source.chart_instance_id != request.chart_instance_id:
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, request.display_timeframe):
                continue
            overlap_seconds = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                request.window_start,
                request.window_end,
            )
            if overlap_seconds <= 0:
                continue
            requested_seconds = max((request.window_end - request.window_start).total_seconds(), 1.0)
            coverage_ratio = overlap_seconds / requested_seconds
            matched_payloads.append(
                (
                    coverage_ratio,
                    overlap_seconds,
                    len(payload.bars),
                    -self._TIMEFRAME_MINUTES.get(payload.bar_timeframe, 0),
                    payload,
                )
            )

        if not matched_payloads:
            return None

        matched_payloads.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return matched_payloads[0][4]

    def _find_matching_history_footprint_payloads(
        self,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[AdapterHistoryFootprintPayload]:
        return self._find_complete_history_footprint_batch(
            instrument_symbol=request.instrument_symbol,
            chart_instance_id=request.chart_instance_id,
            timeframe=request.display_timeframe,
            window_start=request.window_start,
            window_end=request.window_end,
        )

    def _build_candles_from_history_payload(
        self,
        payload: AdapterHistoryBarsPayload,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayChartBar]:
        filtered_bars = [
            bar
            for bar in payload.bars
            if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        if not filtered_bars and payload.bar_timeframe == request.display_timeframe and payload.bars:
            filtered_bars = payload.bars
        if payload.bar_timeframe == request.display_timeframe:
            return [
                ReplayChartBar(
                    started_at=bar.started_at,
                    ended_at=bar.ended_at,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    delta=bar.delta,
                    bid_volume=bar.bid_volume,
                    ask_volume=bar.ask_volume,
                )
                for bar in filtered_bars
            ]

        source_minutes = self._TIMEFRAME_MINUTES[payload.bar_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[request.display_timeframe]
        buckets: dict[datetime, dict[str, Any]] = {}
        for bar in filtered_bars:
            bucket_start = self._bucket_start(bar.started_at, request.display_timeframe)
            bucket = buckets.setdefault(
                bucket_start,
                {
                    "started_at": bucket_start,
                    "ended_at": bucket_start + timedelta(minutes=target_minutes) - timedelta(seconds=1),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 0,
                    "delta": 0,
                    "bid_volume": 0,
                    "ask_volume": 0,
                },
            )
            if bucket["open"] is None:
                bucket["open"] = bar.open
                bucket["high"] = bar.high
                bucket["low"] = bar.low
            else:
                bucket["high"] = max(bucket["high"], bar.high)
                bucket["low"] = min(bucket["low"], bar.low)
            bucket["close"] = bar.close
            if bar.volume is not None:
                bucket["volume"] += bar.volume
            if bar.delta is not None:
                bucket["delta"] += bar.delta
            if bar.bid_volume is not None:
                bucket["bid_volume"] += bar.bid_volume
            if bar.ask_volume is not None:
                bucket["ask_volume"] += bar.ask_volume

        return [
            ReplayChartBar(
                started_at=bucket["started_at"],
                ended_at=bucket["ended_at"],
                open=bucket["open"],
                high=bucket["high"],
                low=bucket["low"],
                close=bucket["close"],
                volume=bucket["volume"],
                delta=bucket["delta"],
                bid_volume=bucket["bid_volume"],
                ask_volume=bucket["ask_volume"],
            )
            for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
            if bucket["open"] is not None
        ]

    def _build_footprint_digest(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        request: ReplayWorkbenchBuildRequest,
    ) -> dict[str, Any]:
        filtered_bars = [
            bar
            for payload in payloads
            for bar in payload.bars
            if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        level_clusters: dict[float, dict[str, Any]] = {}
        extreme_bars: list[dict[str, Any]] = []
        total_level_count = 0

        for bar in filtered_bars:
            bar_total_volume = 0
            bar_abs_delta = 0
            top_volume_level: dict[str, Any] | None = None
            top_delta_level: dict[str, Any] | None = None
            for level in bar.price_levels:
                total_level_count += 1
                total_volume = level.total_volume or 0
                delta = level.delta or 0
                bar_total_volume += total_volume
                bar_abs_delta += abs(delta)
                cluster = level_clusters.setdefault(
                    level.price,
                    {
                        "price": level.price,
                        "bar_hits": 0,
                        "total_volume": 0,
                        "net_delta": 0,
                    },
                )
                cluster["bar_hits"] += 1
                cluster["total_volume"] += total_volume
                cluster["net_delta"] += delta
                candidate = {
                    "price": level.price,
                    "bid_volume": level.bid_volume,
                    "ask_volume": level.ask_volume,
                    "total_volume": total_volume,
                    "delta": delta,
                }
                if top_volume_level is None or total_volume > top_volume_level["total_volume"]:
                    top_volume_level = candidate
                if top_delta_level is None or abs(delta) > abs(top_delta_level["delta"]):
                    top_delta_level = candidate

            extreme_bars.append(
                {
                    "started_at": bar.started_at,
                    "ended_at": bar.ended_at,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "delta": bar.delta,
                    "price_level_count": len(bar.price_levels),
                    "bar_total_price_level_volume": bar_total_volume,
                    "bar_abs_price_level_delta": bar_abs_delta,
                    "top_volume_level": top_volume_level,
                    "top_delta_level": top_delta_level,
                },
            )

        top_bars = sorted(
            extreme_bars,
            key=lambda item: (
                item.get("volume") or 0,
                abs(item.get("delta") or 0),
                item.get("bar_total_price_level_volume") or 0,
            ),
            reverse=True,
        )[:20]
        repeated_levels = sorted(
            level_clusters.values(),
            key=lambda item: (item["bar_hits"], item["total_volume"], abs(item["net_delta"])),
            reverse=True,
        )[:20]

        return {
            "batch_id": payloads[0].batch_id if payloads else None,
            "bar_timeframe": payloads[0].bar_timeframe if payloads else None,
            "chunk_count": len(payloads),
            "bar_count": len(filtered_bars),
            "price_level_count": total_level_count,
            "top_bars": top_bars,
            "repeated_price_levels": repeated_levels,
        }

    def _build_footprint_event_annotations(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        tick_size: float,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayEventAnnotation]:
        digest = self._build_footprint_digest(payloads, request)
        events: list[ReplayEventAnnotation] = []
        for index, item in enumerate(digest["top_bars"][:8]):
            top_level = item.get("top_volume_level") or item.get("top_delta_level")
            if top_level is None:
                continue
            price = top_level["price"]
            side = None
            if (top_level.get("delta") or 0) > 0:
                side = StructureSide.BUY
            elif (top_level.get("delta") or 0) < 0:
                side = StructureSide.SELL
            events.append(
                ReplayEventAnnotation(
                    event_id=f"historical-footprint-bar-{index}",
                    event_kind="historical_footprint_extreme",
                    source_kind="atas_history_footprint",
                    observed_at=item["started_at"],
                    price=price,
                    price_low=price,
                    price_high=price,
                    side=side,
                    confidence=0.6,
                    linked_ids=[digest["batch_id"]],
                    notes=[
                        f"price_level_count={item['price_level_count']}",
                        f"bar_volume={item.get('volume') or 0}",
                        f"bar_delta={item.get('delta') or 0}",
                    ],
                ),
            )
        return events

    def _build_footprint_focus_regions(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        tick_size: float,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayFocusRegion]:
        digest = self._build_footprint_digest(payloads, request)
        regions: list[ReplayFocusRegion] = []
        price_band = max(tick_size, tick_size / 2)
        started_at = request.window_start
        for index, item in enumerate(digest["repeated_price_levels"][:10]):
            price = item["price"]
            regions.append(
                ReplayFocusRegion(
                    region_id=f"historical-footprint-level-{index}",
                    label=f"历史足迹价位 {price}",
                    started_at=started_at,
                    ended_at=request.window_end,
                    price_low=price - price_band,
                    price_high=price + price_band,
                    priority=max(1, min(10, int(item["bar_hits"]))),
                    reason_codes=["historical_footprint", "repeated_price_level"],
                    linked_event_ids=[],
                    notes=[
                        f"bar_hits={item['bar_hits']}",
                        f"total_volume={item['total_volume']}",
                        f"net_delta={item['net_delta']}",
                    ],
                ),
            )
        return regions

    def _build_candles(self, timeframe: Timeframe, ingestions: list[StoredIngestion]) -> list[ReplayChartBar]:
        if timeframe not in self._TIMEFRAME_MINUTES:
            raise ValueError(f"Replay builder does not support display_timeframe '{timeframe}' yet.")

        buckets: dict[datetime, dict[str, Any]] = {}
        for stored in ingestions:
            payload = stored.observed_payload
            observed_at = self._payload_observed_at(payload)
            bucket_start = self._bucket_start(observed_at, timeframe)
            bucket = buckets.setdefault(
                bucket_start,
                {
                    "started_at": bucket_start,
                    "ended_at": bucket_start + timedelta(minutes=self._TIMEFRAME_MINUTES[timeframe]) - timedelta(seconds=1),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 0,
                    "delta": 0,
                    "bid_volume": 0,
                    "ask_volume": 0,
                },
            )
            last_price = payload["price_state"]["last_price"]
            if bucket["open"] is None:
                bucket["open"] = last_price
                bucket["high"] = last_price
                bucket["low"] = last_price
            bucket["high"] = max(bucket["high"], last_price)
            bucket["low"] = min(bucket["low"], last_price)
            bucket["close"] = last_price
            bucket["volume"] += payload.get("trade_summary", {}).get("volume", 0)
            bucket["delta"] += payload.get("trade_summary", {}).get("net_delta", 0)
            bucket["bid_volume"] += payload.get("trade_summary", {}).get("aggressive_sell_volume", 0)
            bucket["ask_volume"] += payload.get("trade_summary", {}).get("aggressive_buy_volume", 0)

        return [
            ReplayChartBar(
                started_at=bucket["started_at"],
                ended_at=bucket["ended_at"],
                open=bucket["open"],
                high=bucket["high"],
                low=bucket["low"],
                close=bucket["close"],
                volume=bucket["volume"],
                delta=bucket["delta"],
                bid_volume=bucket["bid_volume"],
                ask_volume=bucket["ask_volume"],
            )
            for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
            if bucket["open"] is not None
        ]

    @staticmethod
    def _payload_observed_at(payload: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(payload.get("observed_window_end") or payload["emitted_at"])

    def _patch_live_candle_gaps(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None,
        candles: list[ReplayChartBar],
    ) -> list[ReplayChartBar]:
        """Detect time gaps in live candles and fill them from the latest history-bars payload.

        Note: this runs only for the *live tail* path. The replay snapshot builder has its
        own gap-filling logic.
        """
        if len(candles) < 2:
            return candles

        expected_delta = timedelta(minutes=self._TIMEFRAME_MINUTES.get(display_timeframe, 1))
        tolerance = timedelta(seconds=5)

        # Detect if any gap exists
        has_gap = False
        gap_window_start: datetime | None = None
        gap_window_end: datetime | None = None
        for i in range(1, len(candles)):
            delta = candles[i].started_at - candles[i - 1].started_at
            if delta > expected_delta + tolerance:
                has_gap = True
                # Missing window is between the end of previous candle and start of next candle.
                start = candles[i - 1].ended_at + timedelta(seconds=1)
                end = candles[i].started_at - timedelta(seconds=1)
                if gap_window_start is None or start < gap_window_start:
                    gap_window_start = start
                if gap_window_end is None or end > gap_window_end:
                    gap_window_end = end

        if not has_gap or gap_window_start is None or gap_window_end is None or gap_window_end < gap_window_start:
            return candles

        # Find the best history-bars payload covering the gap
        history_candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=instrument_symbol,
            limit=50,
        )
        best_payload: AdapterHistoryBarsPayload | None = None
        best_overlap = 0.0
        for stored in history_candidates:
            payload = AdapterHistoryBarsPayload.model_validate(stored.observed_payload)
            if chart_instance_id is not None and payload.source.chart_instance_id != chart_instance_id:
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, display_timeframe):
                continue
            overlap = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                gap_window_start,
                gap_window_end,
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_payload = payload

        if best_payload is None:
            return candles

        # Build filler candles from history-bars for the gap region
        filler_request = ReplayWorkbenchBuildRequest(
            cache_key="__gap_fill_internal__",
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            window_start=gap_window_start,
            window_end=gap_window_end,
        )
        filler_candles = self._build_candles_from_history_payload(best_payload, filler_request)
        if not filler_candles:
            return candles

        # Merge: existing candles take priority, fillers only fill empty slots
        merged: dict[datetime, ReplayChartBar] = {}
        for bar in filler_candles:
            merged[bar.started_at] = bar
        for bar in candles:
            merged[bar.started_at] = bar  # live data wins

        return [merged[key] for key in sorted(merged)]

    def _detect_candle_time_gaps(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> list[dict[str, Any]]:
        """Detect missing-time gaps based on candle started_at spacing.

        Returns a list of dicts, each describing a single gap segment.
        """
        if timeframe not in self._TIMEFRAME_MINUTES or len(candles) < 2:
            return []

        expected_seconds = int(self._TIMEFRAME_MINUTES[timeframe] * 60)
        tolerance_seconds = 5

        gaps: list[dict[str, Any]] = []
        for prev, nxt in zip(candles, candles[1:]):
            actual_seconds = int((nxt.started_at - prev.started_at).total_seconds())
            if actual_seconds <= expected_seconds + tolerance_seconds:
                continue

            # Estimate how many bars should exist between these starts.
            # If there is a remainder > tolerance, we treat it as needing one extra bar.
            bars_between = max(1, actual_seconds // expected_seconds)
            remainder = actual_seconds % expected_seconds
            if remainder > tolerance_seconds:
                bars_between += 1
            missing = max(1, bars_between - 1)

            gaps.append(
                {
                    "prev_started_at": prev.started_at,
                    "prev_ended_at": prev.ended_at,
                    "next_started_at": nxt.started_at,
                    "next_ended_at": nxt.ended_at,
                    "expected_delta_seconds": expected_seconds,
                    "actual_delta_seconds": actual_seconds,
                    "missing_bar_count": missing,
                }
            )

        return gaps

    def _fill_candle_time_gaps(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], list[dict[str, Any]], int]:
        """Fill time gaps by inserting synthetic flat bars.

        This is a pragmatic UI/analytics workaround: the replay chart is index-based.
        If we do not insert missing bars, gaps get visually compressed and are easy to miss.

        Returns (filled_candles, gaps, inserted_bar_count).
        """
        gaps = self._detect_candle_time_gaps(candles, timeframe)
        if not gaps:
            return candles, [], 0

        expected_delta = timedelta(minutes=self._TIMEFRAME_MINUTES.get(timeframe, 1))
        inserted = 0
        output: list[ReplayChartBar] = []

        # Ensure sorted and unique by started_at (existing candles win).
        candle_map: dict[datetime, ReplayChartBar] = {bar.started_at: bar for bar in candles}
        sorted_starts = sorted(candle_map)
        sorted_candles = [candle_map[start] for start in sorted_starts]

        for idx, bar in enumerate(sorted_candles):
            output.append(bar)
            if idx >= len(sorted_candles) - 1:
                continue

            next_bar = sorted_candles[idx + 1]
            delta = next_bar.started_at - bar.started_at
            tolerance = timedelta(seconds=5)
            if delta <= expected_delta + tolerance:
                continue

            # Recompute missing count deterministically from timedelta.
            expected_seconds = expected_delta.total_seconds()
            actual_seconds = delta.total_seconds()
            bars_between = int(actual_seconds // expected_seconds)
            remainder = actual_seconds % expected_seconds
            if remainder > tolerance.total_seconds():
                bars_between += 1
            missing = max(1, bars_between - 1)

            for j in range(1, missing + 1):
                if inserted >= self._MAX_GAP_FILL_BARS:
                    return output + sorted_candles[idx + 1 :], gaps, inserted
                start = bar.started_at + expected_delta * j
                end = start + expected_delta - timedelta(seconds=1)
                price = bar.close
                filler = ReplayChartBar(
                    started_at=start,
                    ended_at=end,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    delta=0,
                    bid_volume=0,
                    ask_volume=0,
                )
                # Don't override real bars if they exist
                if filler.started_at not in candle_map:
                    output.append(filler)
                    inserted += 1

        output.sort(key=lambda item: item.started_at)
        return output, gaps, inserted

    def _merge_history_candles_with_continuous_overlay(
        self,
        *,
        history_candles: list[ReplayChartBar],
        continuous_messages: list[StoredIngestion],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], int]:
        if not history_candles or not continuous_messages:
            return history_candles, 0

        continuous_candles = self._build_candles(timeframe, continuous_messages)
        if not continuous_candles:
            return history_candles, 0

        # Only overlay continuous bars that start STRICTLY AFTER the last completed history bar.
        # Using ended_at (exclusive boundary) prevents in-progress real-time bars from
        # overwriting the last completed history bar and creating abnormal giant wicks.
        last_history_bar = history_candles[-1]
        overlay_cutoff = last_history_bar.ended_at
        merged: dict[datetime, ReplayChartBar] = {bar.started_at: bar for bar in history_candles}
        overlay_count = 0
        for bar in continuous_candles:
            if bar.started_at <= overlay_cutoff:
                continue
            merged[bar.started_at] = bar
            overlay_count += 1

        return [merged[key] for key in sorted(merged)], overlay_count


    def _can_build_timeframe_from_history(self, source_timeframe: Timeframe, target_timeframe: Timeframe) -> bool:
        if source_timeframe not in self._TIMEFRAME_MINUTES or target_timeframe not in self._TIMEFRAME_MINUTES:
            return False
        source_minutes = self._TIMEFRAME_MINUTES[source_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[target_timeframe]
        return source_minutes <= target_minutes and target_minutes % source_minutes == 0

    def _build_event_annotations(self, ingestions: list[StoredIngestion]) -> list[ReplayEventAnnotation]:
        events: dict[str, ReplayEventAnnotation] = {}
        for stored in ingestions:
            payload = stored.observed_payload
            emitted_at = datetime.fromisoformat(payload["emitted_at"])
            for item in payload.get("same_price_replenishment", []):
                event_id = f"replenish-{item['track_id']}"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="same_price_replenishment",
                    source_kind="collector",
                    observed_at=emitted_at,
                    price=item["price"],
                    price_low=item["price"],
                    price_high=item["price"],
                    side=item["side"],
                    confidence=min(1.0, 0.5 + (item.get("replenishment_count", 0) * 0.1)),
                    linked_ids=[item["track_id"]],
                    notes=[f"replenishment_count={item.get('replenishment_count', 0)}"],
                )
            for item in payload.get("significant_liquidity", []):
                event_id = f"liquidity-{item['track_id']}"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="significant_liquidity",
                    source_kind="collector",
                    observed_at=datetime.fromisoformat(item["last_observed_at"]),
                    price=item["price"],
                    price_low=item["price"],
                    price_high=item["price"],
                    side=item["side"],
                    confidence=item.get("heat_score"),
                    linked_ids=[item["track_id"]],
                    notes=[
                        f"status={item['status']}",
                        f"replenishment_count={item.get('replenishment_count', 0)}",
                    ],
                )
            drive = payload.get("active_initiative_drive")
            if drive is not None:
                event_id = drive["drive_id"]
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="initiative_drive",
                    source_kind="collector",
                    observed_at=datetime.fromisoformat(drive["started_at"]),
                    price_low=drive["price_low"],
                    price_high=drive["price_high"],
                    side=drive["side"],
                    confidence=min(1.0, abs(drive["net_delta"]) / max(1, drive["aggressive_volume"])),
                    linked_ids=[drive["drive_id"]],
                    notes=[f"price_travel_ticks={drive['price_travel_ticks']}"],
                )
            gap = payload.get("gap_reference")
            if gap is not None:
                event_id = gap["gap_id"]
                gap_kind = "gap_fill_watch" if gap.get("fully_filled_at") is None else "gap_fully_filled"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind=gap_kind,
                    source_kind="collector",
                    observed_at=datetime.fromisoformat(gap["first_touch_at"] or gap["opened_at"]),
                    price_low=gap["gap_low"],
                    price_high=gap["gap_high"],
                    side=StructureSide.BUY if gap["direction"] == "up" else StructureSide.SELL,
                    confidence=gap["fill_ratio"],
                    linked_ids=[gap["gap_id"]],
                    notes=[f"fill_attempt_count={gap['fill_attempt_count']}"],
                )
            post_harvest = payload.get("active_post_harvest_response")
            if post_harvest is not None:
                event_id = post_harvest["response_id"]
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="post_harvest_response",
                    source_kind="collector",
                    observed_at=datetime.fromisoformat(post_harvest["harvest_completed_at"]),
                    price_low=post_harvest["harvested_price_low"],
                    price_high=post_harvest["harvested_price_high"],
                    side=post_harvest["harvest_side"],
                    linked_ids=[post_harvest["harvest_subject_id"]],
                    notes=[f"outcome={post_harvest['outcome']}"],
                )
        return sorted(events.values(), key=lambda item: item.observed_at)

    def _build_focus_regions(
        self,
        ingestions: list[StoredIngestion],
        event_annotations: list[ReplayEventAnnotation],
    ) -> list[ReplayFocusRegion]:
        latest_payload = ingestions[-1].observed_payload
        regions: list[ReplayFocusRegion] = []
        linked_event_ids = {event.event_id for event in event_annotations}
        for item in latest_payload.get("significant_liquidity", []):
            regions.append(
                ReplayFocusRegion(
                    region_id=f"focus-{item['track_id']}",
                    label=f"{item['side']} liquidity {item['price']}",
                    started_at=datetime.fromisoformat(item["first_observed_at"]),
                    ended_at=datetime.fromisoformat(item["last_observed_at"]),
                    price_low=item["price"],
                    price_high=item["price"],
                    priority=max(1, min(10, int((item.get("heat_score") or 0.5) * 10))),
                    reason_codes=[
                        "significant_liquidity",
                        "same_price_replenishment" if item.get("replenishment_count", 0) > 0 else "tracked_liquidity",
                    ],
                    linked_event_ids=[event_id for event_id in linked_event_ids if item["track_id"] in event_id],
                    notes=[f"touch_count={item['touch_count']}"],
                )
            )

        zone = latest_payload.get("active_zone_interaction")
        if zone is not None:
            regions.append(
                ReplayFocusRegion(
                    region_id=f"focus-{zone['zone_id']}",
                    label="active defended zone",
                    started_at=datetime.fromisoformat(zone["started_at"]),
                    ended_at=None,
                    price_low=zone["zone_low"],
                    price_high=zone["zone_high"],
                    priority=8,
                    reason_codes=["zone_interaction", "same_price_replenishment"],
                    linked_event_ids=[zone["zone_id"]],
                    notes=[f"seconds_held={zone['seconds_held']}"],
                )
            )
        regions.sort(key=lambda item: item.priority, reverse=True)
        return regions[:10]

    def _find_complete_history_footprint_batch(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
    ) -> list[AdapterHistoryFootprintPayload]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_footprint",
            instrument_symbol=instrument_symbol,
            limit=4000,
        )
        grouped: dict[str, list[AdapterHistoryFootprintPayload]] = {}
        for stored in candidates:
            payload = AdapterHistoryFootprintPayload.model_validate(stored.observed_payload)
            if chart_instance_id is not None and payload.source.chart_instance_id != chart_instance_id:
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, timeframe):
                continue
            overlap_seconds = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                window_start,
                window_end,
            )
            if overlap_seconds <= 0:
                continue
            grouped.setdefault(payload.batch_id, []).append(payload)

        if not grouped:
            return []

        complete_batches: list[tuple[float, float, int, int, list[AdapterHistoryFootprintPayload]]] = []
        for items in grouped.values():
            expected = items[0].chunk_count
            chunk_indexes = {item.chunk_index for item in items}
            # ATAS may refresh only the overlapping tail of a historical footprint batch.
            # For replay we prefer the best overlapping subset instead of discarding the
            # batch outright when some non-overlapping chunks are missing.
            if len(chunk_indexes) < max(1, expected // 2):
                continue
            overlap_seconds = self._overlap_seconds(
                min(item.observed_window_start for item in items),
                max(item.observed_window_end for item in items),
                window_start,
                window_end,
            )
            if overlap_seconds <= 0:
                continue
            requested_seconds = max((window_end - window_start).total_seconds(), 1.0)
            coverage_ratio = overlap_seconds / requested_seconds
            complete_batches.append(
                (
                    coverage_ratio,
                    overlap_seconds,
                    sum(len(item.bars) for item in items),
                    -self._TIMEFRAME_MINUTES.get(items[0].bar_timeframe, 0),
                    sorted(items, key=lambda item: item.chunk_index),
                )
            )

        if not complete_batches:
            return []

        complete_batches.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return complete_batches[0][4]

    def _history_snapshot_should_refresh(
        self,
        request: ReplayWorkbenchBuildRequest,
        cached_ingestion: StoredIngestion,
        history_payload: AdapterHistoryBarsPayload | None,
    ) -> bool:
        if history_payload is None:
            return False
        cached_payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
        if cached_payload.display_timeframe != request.display_timeframe:
            return True
        estimated_count = self._estimate_history_candle_count(history_payload, request)
        cached_count = len(cached_payload.candles)
        if estimated_count > max(cached_count + 50, int(cached_count * 1.2)):
            return True
        cached_history_message_id = cached_payload.raw_features.get("history_message_id")
        if cached_history_message_id != history_payload.message_id:
            cached_actual_end = cached_payload.raw_features.get("actual_window_end")
            if cached_actual_end is None:
                return True
            try:
                cached_actual_end_dt = datetime.fromisoformat(str(cached_actual_end).replace("Z", "+00:00"))
            except ValueError:
                return True
            if history_payload.observed_window_end > cached_actual_end_dt:
                return True
        return False

    def _estimate_history_candle_count(
        self,
        payload: AdapterHistoryBarsPayload,
        request: ReplayWorkbenchBuildRequest,
    ) -> int:
        filtered_bars = [
            bar for bar in payload.bars if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        if not filtered_bars:
            return 0
        if payload.bar_timeframe == request.display_timeframe:
            return len(filtered_bars)
        source_minutes = self._TIMEFRAME_MINUTES[payload.bar_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[request.display_timeframe]
        if target_minutes <= source_minutes:
            return len(filtered_bars)
        buckets = {self._bucket_start(bar.started_at, request.display_timeframe) for bar in filtered_bars}
        return len(buckets)

    @staticmethod
    def _overlap_seconds(
        source_start: datetime,
        source_end: datetime,
        request_start: datetime,
        request_end: datetime,
    ) -> float:
        overlap_start = max(source_start, request_start)
        overlap_end = min(source_end, request_end)
        if overlap_end < overlap_start:
            return 0.0
        return (overlap_end - overlap_start).total_seconds()

    def _find_history_footprint_bar(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        bar_started_at: datetime,
    ) -> AdapterHistoryFootprintBar | None:
        payloads = self._find_complete_history_footprint_batch(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )
        for payload in payloads:
            for bar in payload.bars:
                if bar.started_at == bar_started_at:
                    return bar
        return None

    def _build_strategy_candidates(
        self,
        event_annotations: list[ReplayEventAnnotation],
        focus_regions: list[ReplayFocusRegion] | None = None,
        instrument_symbol: str = "NQ",
    ) -> list[ReplayStrategyCandidate]:
        # Legacy hardcoded candidates (preserved for backward compat)
        kinds = {item.event_kind for item in event_annotations}
        candidates: list[ReplayStrategyCandidate] = []
        if "same_price_replenishment" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind == "same_price_replenishment"]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="pattern-nq-replenished-bid-launchpad",
                    title="NQ replenished bid launchpad",
                    source_path="docs/strategy_library/patterns/nq_replenished_bid_launchpad_into_upper_liquidity.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["same-price replenishment was observed in the requested replay window"],
                )
            )
        if "post_harvest_response" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind == "post_harvest_response"]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="pattern-nq-upper-liquidity-harvest-then-lower-relocation",
                    title="NQ upper liquidity harvest then lower relocation",
                    source_path="docs/strategy_library/patterns/nq_upper_liquidity_harvest_then_lower_relocation.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["post-harvest reaction was observed after a completed liquidity objective"],
                )
            )
        if "gap_fill_watch" in kinds or "gap_fully_filled" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind in {"gap_fill_watch", "gap_fully_filled"}]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="gap-fill-opening-auction-doctrine",
                    title="Gap fill opening-auction doctrine",
                    source_path="docs/shuyin_gap_fill_system_absorption_checklist.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["gap reference remained active inside the replay window"],
                )
            )
        # Data-driven enrichment from strategy_index.json
        try:
            engine = StrategySelectionEngine(root_dir=self._repository._database_path.parent.parent if hasattr(self._repository, '_database_path') else None)
            engine_candidates = engine.select_candidates(
                event_annotations,
                focus_regions or [],
                instrument_symbol=instrument_symbol,
            )
            existing_ids = {c.strategy_id for c in candidates}
            for ec in engine_candidates:
                if ec.strategy_id not in existing_ids:
                    candidates.append(ec)
                    existing_ids.add(ec.strategy_id)
        except Exception:
            pass  # Graceful fallback to legacy-only
        return candidates

    @staticmethod
    def _build_ai_briefing(
        instrument_symbol: str,
        strategy_candidates: list[ReplayStrategyCandidate],
        focus_regions: list[ReplayFocusRegion],
    ) -> ReplayAiBriefing | None:
        if not strategy_candidates and not focus_regions:
            return None
        return ReplayAiBriefing(
            objective=f"Review the last replay window for {instrument_symbol} and rank the strongest support, resistance, continuation, and reversal zones.",
            focus_questions=[
                "Which focus regions still look defendable on revisit?",
                "Which regions are more likely to fail and convert into post-harvest pullback or reversal?",
            ],
            required_outputs=["key_zones", "continuation_vs_reversal", "invalidations"],
            notes=["Treat event annotations as observed facts and explain the zone logic explicitly."],
        )

    def _find_latest_replay_snapshot(
        self,
        *,
        cache_key: str | None = None,
        replay_snapshot_id: str | None = None,
        ingestion_id: str | None = None,
    ) -> StoredIngestion | None:
        if ingestion_id is not None:
            stored = self._repository.get_ingestion(ingestion_id)
            if stored is None or stored.ingestion_kind != "replay_workbench_snapshot":
                return None
            return stored

        for stored in self._repository.list_ingestions(ingestion_kind="replay_workbench_snapshot", limit=500):
            payload = stored.observed_payload
            if cache_key is not None and payload.get("cache_key") == cache_key:
                return stored
            if replay_snapshot_id is not None and payload.get("replay_snapshot_id") == replay_snapshot_id:
                return stored
        return None

    def _find_latest_replay_snapshot_by_cache_identity(self, cache_key: str) -> tuple[str, StoredIngestion] | None:
        """Find the newest snapshot with the same symbol/timeframe/window_start even if window_end drifted.

        This helps during closed sessions or page refreshes where the UI rebuilds cache_key with a new
        current-time window_end, while the operator really wants to reopen the most recent cached replay
        for the same symbol/timeframe/lookback identity.
        """
        symbol, timeframe, window_start, _window_end = self._split_cache_key(cache_key)
        if symbol is None or timeframe is None or window_start is None:
            return None

        for stored in self._repository.list_ingestions(ingestion_kind="replay_workbench_snapshot", limit=500):
            payload = stored.observed_payload
            payload_key = payload.get("cache_key")
            if not isinstance(payload_key, str):
                continue
            p_symbol, p_timeframe, p_window_start, _p_window_end = self._split_cache_key(payload_key)
            if p_symbol == symbol and p_timeframe == timeframe and p_window_start == window_start:
                return payload_key, stored
        return None

    @staticmethod
    def _split_cache_key(cache_key: str) -> tuple[str | None, str | None, str | None, str | None]:
        parts = (cache_key or "").split("|", 3)
        if len(parts) != 4:
            return None, None, None, None
        return parts[0], parts[1], parts[2], parts[3]

    @staticmethod
    def _build_summary(payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchAcceptedSummary:
        return ReplayWorkbenchAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            display_timeframe=payload.display_timeframe,
            acquisition_mode=payload.acquisition_mode,
            verification_status=payload.verification_state.status,
            verification_count=payload.verification_state.verification_count,
            locked_until_manual_reset=payload.verification_state.locked_until_manual_reset,
            fetch_only_when_missing=payload.cache_policy.fetch_only_when_missing,
            max_verifications_per_day=payload.cache_policy.max_verifications_per_day,
            verification_passes_to_lock=payload.cache_policy.verification_passes_to_lock,
            candle_count=len(payload.candles),
            event_annotation_count=len(payload.event_annotations),
            focus_region_count=len(payload.focus_regions),
            strategy_candidate_count=len(payload.strategy_candidates),
            has_ai_briefing=payload.ai_briefing is not None,
        )

    @staticmethod
    def _build_cache_record(stored: StoredIngestion, payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchCacheRecord:
        return ReplayWorkbenchCacheRecord(
            ingestion_id=stored.ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            cache_key=payload.cache_key,
            stored_at=stored.stored_at,
            created_at=payload.created_at,
            instrument_symbol=payload.instrument.symbol,
            display_timeframe=payload.display_timeframe,
            window_start=payload.window_start,
            window_end=payload.window_end,
            acquisition_mode=payload.acquisition_mode,
            cache_policy=payload.cache_policy,
            verification_state=payload.verification_state,
            candle_count=len(payload.candles),
            event_annotation_count=len(payload.event_annotations),
            focus_region_count=len(payload.focus_regions),
            strategy_candidate_count=len(payload.strategy_candidates),
            has_ai_briefing=payload.ai_briefing is not None,
        )

    @staticmethod
    def _is_auto_fetch_allowed(payload: ReplayWorkbenchSnapshotPayload) -> bool:
        if payload.verification_state.status == ReplayVerificationStatus.INVALIDATED:
            return not payload.cache_policy.manual_reimport_required_after_invalidation
        if payload.cache_policy.fetch_only_when_missing:
            return False
        return True

    @staticmethod
    def _is_verification_due(payload: ReplayWorkbenchSnapshotPayload) -> bool:
        if payload.verification_state.status in {ReplayVerificationStatus.DURABLE, ReplayVerificationStatus.INVALIDATED}:
            return False
        if payload.verification_state.next_verification_due_at is None:
            return payload.verification_state.status == ReplayVerificationStatus.UNVERIFIED
        return payload.verification_state.next_verification_due_at <= datetime.now(tz=UTC)

    def _iter_matching_backfill_requests_locked(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
    ) -> list[ReplayWorkbenchAtasBackfillRecord]:
        return sorted(
            (
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and (
                    record.chart_instance_id is None
                    or (
                        chart_instance_id is not None
                        and record.chart_instance_id == chart_instance_id
                    )
                )
            ),
            key=lambda item: (item.requested_at, item.request_id),
        )

    def _find_reusable_backfill_request_locked(
        self,
        request: ReplayWorkbenchAtasBackfillRequest,
        now: datetime,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        for record in self._backfill_requests.values():
            if record.status not in {
                ReplayWorkbenchAtasBackfillStatus.PENDING,
                ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
            }:
                continue
            if record.expires_at <= now:
                continue
            if (
                record.cache_key == request.cache_key
                and record.instrument_symbol == request.instrument_symbol
                and record.display_timeframe == request.display_timeframe
                and record.window_start == request.window_start
                and record.window_end == request.window_end
                and record.chart_instance_id == request.chart_instance_id
                and record.reason == request.reason
                and record.request_history_bars == request.request_history_bars
                and record.request_history_footprint == request.request_history_footprint
                and self._gap_segments_equal(record.missing_segments, request.missing_segments)
            ):
                return record
        return None

    def _expire_backfill_requests_locked(self, now: datetime) -> None:
        for request_id, record in list(self._backfill_requests.items()):
            if (
                record.status in {
                    ReplayWorkbenchAtasBackfillStatus.PENDING,
                    ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
                }
                and record.expires_at <= now
            ):
                self._backfill_requests[request_id] = record.model_copy(
                    update={
                        "status": ReplayWorkbenchAtasBackfillStatus.EXPIRED,
                        "note": record.note or "expired before adapter acknowledgement",
                    }
                )
        self._prune_backfill_requests_locked(now)

    def _prune_backfill_requests_locked(self, now: datetime) -> None:
        cutoff = now - self._BACKFILL_RECORD_RETENTION
        for request_id, record in list(self._backfill_requests.items()):
            if record.requested_at < cutoff and record.status in {
                ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED,
                ReplayWorkbenchAtasBackfillStatus.EXPIRED,
            }:
                self._backfill_requests.pop(request_id, None)

    def _is_backfill_dispatchable(
        self,
        record: ReplayWorkbenchAtasBackfillRecord,
        now: datetime,
    ) -> bool:
        if record.status == ReplayWorkbenchAtasBackfillStatus.PENDING:
            return True
        if record.status != ReplayWorkbenchAtasBackfillStatus.DISPATCHED:
            return False
        if record.dispatched_at is None:
            return True
        return now - record.dispatched_at >= self._BACKFILL_DISPATCH_LEASE

    @staticmethod
    def _build_backfill_command(record: ReplayWorkbenchAtasBackfillRecord) -> AdapterBackfillCommand:
        dispatched_at = record.dispatched_at or datetime.now(tz=UTC)
        return AdapterBackfillCommand(
            request_id=record.request_id,
            cache_key=record.cache_key,
            instrument_symbol=record.instrument_symbol,
            display_timeframe=record.display_timeframe,
            window_start=record.window_start,
            window_end=record.window_end,
            chart_instance_id=record.chart_instance_id,
            missing_segments=record.missing_segments,
            reason=record.reason,
            request_history_bars=record.request_history_bars,
            request_history_footprint=record.request_history_footprint,
            dispatch_count=record.dispatch_count,
            requested_at=record.requested_at,
            dispatched_at=dispatched_at,
        )

    @staticmethod
    def _gap_segments_equal(left: list[Any], right: list[Any]) -> bool:
        if len(left) != len(right):
            return False

        def _normalize(segment: Any) -> tuple[Any, Any, int]:
            prev_ended_at = getattr(segment, "prev_ended_at", None)
            next_started_at = getattr(segment, "next_started_at", None)
            missing_bar_count = getattr(segment, "missing_bar_count", None)
            return prev_ended_at, next_started_at, int(missing_bar_count or 0)

        return [_normalize(item) for item in left] == [_normalize(item) for item in right]

    def _bucket_start(self, value: datetime, timeframe: Timeframe) -> datetime:
        value = value.astimezone(UTC)
        if timeframe == Timeframe.DAY_1:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes = self._TIMEFRAME_MINUTES[timeframe]
        if minutes >= 60:
            hour_bucket = (value.hour // (minutes // 60)) * (minutes // 60)
            return value.replace(hour=hour_bucket, minute=0, second=0, microsecond=0)
        minute_bucket = (value.minute // minutes) * minutes
        return value.replace(minute=minute_bucket, second=0, microsecond=0)
