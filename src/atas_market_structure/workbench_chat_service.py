from __future__ import annotations

# workbench chat entrypoint; keep new session/reply helper logic in adjacent helper modules instead of regrowing this file

from datetime import UTC, datetime, timedelta
import json
import logging
import re
from threading import Lock
from typing import Any, Sequence
from uuid import uuid4


from atas_market_structure.continuous_contract_service import ContinuousContractService
from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterBackfillCommand,
    AdapterBackfillDispatchResponse,
    AdapterHistoryInventoryPayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintBar,
    AdapterHistoryFootprintPayload,
    AdapterInitiativeDriveState,
    AdapterPostHarvestResponseState,
    AdapterSamePriceReplenishmentState,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
    BeliefDataStatus,
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
    ContinuousAdjustmentMode,
    PromptBlock,
    PromptBlocksEnvelope,
    SessionMemory,
    SessionMemoryEnvelope,
    UpdateChatSessionRequest,
    UpdateMountedMessageRequest,
    ReplayAcquisitionMode,
    ReplayAiChatAttachment,
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
    ReplayWorkbenchBackfillProgressRange,
    ReplayWorkbenchBackfillProgressResponse,
    ReplayWorkbenchAtasBackfillRecord,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchAtasBackfillStatus,
    ReplayWorkbenchBuildAction,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchCacheRecord,
    ReplayWorkbenchBackfillRange,
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
    RecognitionMode,
    DegradedMode,
    RollMode,
    StructureSide,
    Timeframe,
)
from atas_market_structure.chart_identity import (
    chart_instance_ids_match,
    is_generic_chart_instance_id,
    normalize_identifier,
    normalize_symbol,
    normalize_timeframe,
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
from atas_market_structure.workbench_common import (
    FinalizedReplyTurn,
    PreparedReplyTurn,
    ReplayWorkbenchChatError,
    ReplayWorkbenchChatUnavailableError,
    ReplayWorkbenchNotFoundError,
    chunk_stream_text,
    slugify_chat_title,
)

LOGGER = logging.getLogger(__name__)


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
        title = slugify_chat_title(request.title)
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
            include_memory_summary=False,
            include_recent_messages=False,
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
        self._require_reply_backend()
        prepared = self._prepare_reply_turn(session_id, request)
        replay_response = self._run_reply_model(prepared)
        finalized = self._finalize_reply_turn(prepared, replay_response)
        return self._build_reply_response(finalized)

    def build_reply_event_preview(self, session_id: str, request: ChatReplyRequest) -> list[dict[str, Any]]:
        self._require_reply_backend()
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
        self._require_reply_backend()
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
            analysis_type=request_payload.get("analysis_type"),
            analysis_range=request_payload.get("analysis_range"),
            analysis_style=request_payload.get("analysis_style"),
            extra_context=request_payload.get("extra_context") if isinstance(request_payload.get("extra_context"), dict) else None,
            attachments=self._attachments_from_payload(request_payload),
            replay_ingestion_id=message.response_payload.get("replay_ingestion_id") or request_payload.get("replay_ingestion_id"),
        )
        prepared = self._prepare_reply_turn(session_id, request, parent_message_id=message.message_id)
        replay_response = self._run_reply_model(prepared)
        finalized = self._finalize_reply_turn(prepared, replay_response)
        return self._build_reply_response(finalized)

    def evaluate_lifecycle(self, session_id: str, bars: list[dict[str, Any]], live_tail: dict[str, Any] | None, object_ids: list[str]) -> dict[str, Any]:
        self._require_stored_session(session_id)
        annotations = self._repository.list_chat_annotations(session_id=session_id, limit=1000)
        plans = self._repository.list_chat_plan_cards(session_id=session_id, limit=1000)
        transitions: list[dict[str, Any]] = []

        latest_close = None
        if bars:
            latest_bar = bars[-1] if isinstance(bars[-1], dict) else None
            latest_close = latest_bar.get("close") if latest_bar else None
        if latest_close is None and isinstance(live_tail, dict):
            latest_close = live_tail.get("latest_price") or live_tail.get("last_price")

        for annotation in annotations:
            if object_ids and annotation.annotation_id not in object_ids and (annotation.plan_id or "") not in object_ids:
                continue
            if latest_close is None:
                continue
            if annotation.annotation_type == "entry_line":
                entry_price = annotation.payload.get("entry_price")
                if entry_price is not None and annotation.status == "active" and latest_close == entry_price:
                    transitions.append({
                        "object_id": annotation.annotation_id,
                        "from_status": annotation.status,
                        "to_status": "triggered",
                        "event": "touch_entry",
                    })
            if annotation.annotation_type == "stop_loss":
                stop_price = annotation.payload.get("stop_price")
                if stop_price is not None and annotation.status == "active":
                    transitions.append({
                        "object_id": annotation.annotation_id,
                        "from_status": annotation.status,
                        "to_status": "completed" if latest_close == stop_price else annotation.status,
                        "event": "touch_stop" if latest_close == stop_price else "no_change",
                    })

        for plan in plans:
            if object_ids and plan.plan_id not in object_ids:
                continue
            if latest_close is None or plan.entry_price is None:
                continue
            if plan.status == "active" and latest_close == plan.entry_price:
                transitions.append({
                    "object_id": plan.plan_id,
                    "from_status": plan.status,
                    "to_status": "triggered",
                    "event": "touch_entry",
                })
            elif plan.status == "active" and plan.stop_price is not None and latest_close == plan.stop_price:
                transitions.append({
                    "object_id": plan.plan_id,
                    "from_status": plan.status,
                    "to_status": "invalidated",
                    "event": "touch_stop",
                })

        return {"ok": True, "transitions": transitions}

    def _find_regenerate_user_message(self, session_id: str, assistant_message: StoredChatMessage) -> StoredChatMessage | None:
        messages = self._repository.list_chat_messages(session_id=session_id, limit=500)
        assistant_index = next((index for index, item in enumerate(messages) if item.message_id == assistant_message.message_id), None)
        if assistant_index is None:
            return None
        for candidate in reversed(messages[:assistant_index]):
            if candidate.role == "user":
                return candidate
        return None

    def _prepare_reply_turn(self, session_id: str, request: ChatReplyRequest, parent_message_id: str | None = None) -> PreparedReplyTurn:
        session = self._require_stored_session(session_id)
        replay_ingestion_id = request.replay_ingestion_id or self._find_latest_replay_ingestion_id_for_symbol(session.symbol)
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
                "analysis_type": request.analysis_type,
                "analysis_range": request.analysis_range,
                "analysis_style": request.analysis_style,
                "extra_context": request.extra_context or {},
                "attachments": [item.model_dump(mode="json") for item in request.attachments],
            },
            response_payload={},
            created_at=now,
            updated_at=now,
        )
        assistant_pending = self._repository.save_chat_message(
            message_id=f"msg-{uuid4().hex}",
            session_id=session_id,
            parent_message_id=parent_message_id,
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
        return PreparedReplyTurn(
            session=session,
            replay_ingestion_id=replay_ingestion_id,
            user_record=user_record,
            assistant_pending=assistant_pending,
            history=history,
            request=request,
            parent_message_id=parent_message_id,
        )

    def _run_reply_model(self, prepared: PreparedReplyTurn):
        if self._replay_ai_chat_service is None:
            raise ReplayWorkbenchChatUnavailableError(
                "Replay workbench chat service is not configured. Configure AI provider credentials before sending a reply."
            )
        model_user_input = self._build_model_user_input(prepared)
        allow_session_structured_outputs = self._should_enable_session_structured_output(prepared.request)
        if prepared.has_replay_context:
            return self._replay_ai_chat_service.chat(
                __import__("atas_market_structure.models", fromlist=["ReplayAiChatRequest"]).ReplayAiChatRequest(
                    replay_ingestion_id=prepared.replay_ingestion_id,
                    preset=prepared.request.preset,
                    user_message=model_user_input,
                    history=prepared.history,
                    model_override=prepared.request.model or prepared.session.active_model,
                    include_live_context=True,
                    attachments=prepared.request.attachments,
                )
            )
        provider, model, content = self._replay_ai_chat_service._assistant.generate_session_reply(
            user_message=model_user_input,
            history=prepared.history,
            attachments=prepared.request.attachments,
            enable_structured_outputs=allow_session_structured_outputs,
            model_override=prepared.request.model or prepared.session.active_model,
        )
        return __import__("types").SimpleNamespace(
            reply_text=content.reply_text,
            provider=provider,
            model=model,
            preset=prepared.request.preset,
            referenced_strategy_ids=[],
            live_context_summary=[],
            follow_up_suggestions=content.follow_up_suggestions,
            attachment_summaries=content.attachment_summaries,
            plan_cards=content.plan_cards if allow_session_structured_outputs else [],
            annotations=content.annotations if allow_session_structured_outputs else [],
            session_only=True,
            model_dump=lambda mode="json": {
                "reply_text": content.reply_text,
                "provider": provider,
                "model": model,
                "preset": str(prepared.request.preset),
                "referenced_strategy_ids": [],
                "live_context_summary": [],
                "follow_up_suggestions": content.follow_up_suggestions,
                "attachment_summaries": content.attachment_summaries,
                "plan_cards": [item.model_dump(mode="json") for item in (content.plan_cards if allow_session_structured_outputs else [])],
                "annotations": [item.model_dump(mode="json") for item in (content.annotations if allow_session_structured_outputs else [])],
                "session_only": True,
            },
        )

    def _require_reply_backend(self) -> None:
        if self._replay_ai_chat_service is None:
            raise ReplayWorkbenchChatUnavailableError(
                "Replay workbench chat service is not configured. Configure AI provider credentials before sending a reply."
            )

    def _finalize_reply_turn(self, prepared: PreparedReplyTurn, replay_response) -> FinalizedReplyTurn:
        plan_cards = self._extract_plan_cards(prepared.session, prepared.assistant_pending.message_id, replay_response)
        annotations = self._build_annotations(
            prepared.session,
            prepared.assistant_pending.message_id,
            replay_response,
            plan_cards,
            prepared.request,
        )
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
        return FinalizedReplyTurn(
            session_id=prepared.session.session_id,
            user_record=prepared.user_record,
            assistant_record=assistant_record,
            plan_cards=plan_cards,
            annotations=annotations,
            memory=memory,
            replay_response=replay_response,
        )

    def _build_reply_response(self, finalized: FinalizedReplyTurn) -> ChatReplyResponse:
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
            session_only=bool(getattr(replay_response, "session_only", False)),
        )

    def _build_reply_events(self, finalized: FinalizedReplyTurn) -> list[dict[str, Any]]:
        replay_response = finalized.replay_response
        events: list[dict[str, Any]] = [
            {
                "event": "message_start",
                "data": {
                    "session_id": finalized.session_id,
                    "message_id": finalized.assistant_record.message_id,
                    "model": replay_response.model,
                    "provider": replay_response.provider,
                    "session_only": bool(getattr(replay_response, "session_only", False)),
                },
            },
            {
                "event": "message_status",
                "data": {
                    "message_id": finalized.assistant_record.message_id,
                    "status": "streaming",
                },
            },
        ]
        for chunk in chunk_stream_text(replay_response.reply_text):
            events.append(
                {
                    "event": "token",
                    "data": {
                        "message_id": finalized.assistant_record.message_id,
                        "delta": chunk,
                    },
                }
            )
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
                    "session_only": bool(getattr(replay_response, "session_only", False)),
                },
            }
        )
        return events

    def _interrupt_reply_turn(self, prepared: PreparedReplyTurn) -> StoredChatMessage:
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

    def refresh_memory(self, session_id: str, request: ChatHandoffRequest) -> SessionMemoryEnvelope:
        self._require_stored_session(session_id)
        messages = self._list_recent_chat_messages(
            session_id,
            limit=6,
            roles={"user", "assistant"},
            require_content=True,
        )
        latest_user_message = next((item for item in reversed(messages) if item.role == "user"), None)
        latest_assistant_message = next((item for item in reversed(messages) if item.role == "assistant"), None)
        annotations = self._repository.list_chat_annotations(session_id=session_id, limit=500)
        plans = self._repository.list_chat_plan_cards(session_id=session_id, limit=200)
        memory = self._refresh_session_memory(
            session_id,
            request.target_model,
            latest_user_message.content if latest_user_message is not None else "",
            latest_assistant_message.content if latest_assistant_message is not None else "",
            annotations,
            plans,
        )
        return SessionMemoryEnvelope(memory=memory)

    def build_handoff(self, session_id: str, request: ChatHandoffRequest) -> ChatHandoffResponse:
        session = self._require_stored_session(session_id)
        memory = self._repository.get_session_memory(session_id)
        recent_messages = (
            self._list_recent_chat_messages(
                session_id,
                limit=6,
                roles={"user", "assistant"},
                require_content=True,
            )
            if request.mode == "summary_plus_recent_3"
            else []
        )
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
        now = datetime.now(tz=UTC)
        updated = self._repository.update_chat_message(
            message_id,
            mounted_to_chart=request.mounted_to_chart,
            mounted_object_ids=request.mounted_object_ids,
            updated_at=now,
        )
        if updated is None:
            raise ReplayWorkbenchChatError(f"Chat message '{message_id}' disappeared during mount update.")
        session = self._require_stored_session(updated.session_id)
        existing_ids = list(session.mounted_reply_ids)

        if request.mount_mode == "replace":
            for mounted_id in existing_ids:
                if mounted_id == message_id:
                    continue
                self._repository.update_chat_message(
                    mounted_id,
                    mounted_to_chart=False,
                    mounted_object_ids=[],
                    updated_at=now,
                )
            mounted_reply_ids = [message_id] if request.mounted_to_chart else []
        elif request.mount_mode == "focus_only":
            mounted_reply_ids = existing_ids if request.mounted_to_chart else [item for item in existing_ids if item != message_id]
        else:
            mounted_reply_ids = list(dict.fromkeys([*existing_ids, message_id])) if request.mounted_to_chart else [item for item in existing_ids if item != message_id]

        self._repository.update_chat_session(updated.session_id, mounted_reply_ids=mounted_reply_ids, updated_at=now)
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
        elif kind == "manual_region" and replay_payload is not None:
            replay_ingestion_id = self._find_latest_replay_ingestion_id_for_symbol(session.symbol) or ""
            regions = []
            if replay_ingestion_id:
                for stored in self._repository.list_ingestions(ingestion_kind="replay_manual_region", limit=1000):
                    if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                        continue
                    regions.append(ReplayManualRegionAnnotationRecord.model_validate(stored.observed_payload))
                regions.sort(key=lambda item: (item.started_at, item.price_low))
            preview = f"手工区域 {len(regions)} 条"
            full_payload = {"regions": [item.model_dump(mode="json") for item in regions[-10:]]}
            title = "手工区域"
        elif kind == "recent_messages":
            messages = self._list_recent_chat_messages(
                session.session_id,
                limit=6,
                roles={"user", "assistant"},
                require_content=True,
            )
            preview = f"最近消息 {len(messages)} 条"
            full_payload = {"messages": [self._message_model(item).model_dump(mode="json") for item in messages]}
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
            important_messages=[
                item.message_id
                for item in self._list_recent_chat_messages(
                    session_id,
                    limit=6,
                    roles={"assistant"},
                    require_content=True,
                )
            ],
            current_user_intent=latest_question[:120],
            latest_question=latest_question,
            latest_answer_summary=reply_text[:180],
            selected_annotations=[item.annotation_id for item in annotations][-12:],
            last_updated_at=now,
        )
        self._repository.update_chat_session(session_id, memory_summary_id=stored.memory_summary_id, updated_at=now)
        return self._memory_model(stored)

    def _extract_plan_cards(self, session: StoredChatSession, message_id: str, replay_response) -> list[StoredChatPlanCard]:
        structured_candidates = list(getattr(replay_response, "plan_cards", []) or [])
        if structured_candidates:
            now = datetime.now(tz=UTC)
            plans: list[StoredChatPlanCard] = []
            for candidate in structured_candidates:
                plan = self._repository.save_chat_plan_card(
                    plan_id=f"plan-{uuid4().hex}",
                    session_id=session.session_id,
                    message_id=message_id,
                    title=candidate.title or "AI计划卡",
                    side=candidate.side or "buy",
                    entry_type="range" if candidate.entry_price_low is not None or candidate.entry_price_high is not None else "point",
                    entry_price=candidate.entry_price,
                    entry_price_low=candidate.entry_price_low,
                    entry_price_high=candidate.entry_price_high,
                    stop_price=candidate.stop_price,
                    take_profits=candidate.take_profits,
                    invalidations=candidate.invalidations,
                    time_validity=None,
                    risk_reward=None,
                    confidence=candidate.confidence,
                    priority=candidate.priority,
                    status="active",
                    source_kind="session_chat" if getattr(replay_response, "session_only", False) else "replay_analysis",
                    notes=candidate.notes or candidate.summary or replay_response.reply_text,
                    payload=candidate.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
                plans.append(plan)
            return plans

        text = str(replay_response.reply_text or "")
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
            source_kind="session_chat" if getattr(replay_response, "session_only", False) else "replay_analysis",
            notes=text,
            payload={"reply_text": text},
            created_at=now,
            updated_at=now,
        )
        return [plan]

    def _build_annotations(
        self,
        session: StoredChatSession,
        message_id: str,
        replay_response,
        plans: list[StoredChatPlanCard],
        request: ChatReplyRequest | None = None,
    ) -> list[StoredChatAnnotation]:
        structured_candidates = list(getattr(replay_response, "annotations", []) or [])
        if structured_candidates:
            annotations: list[StoredChatAnnotation] = []
            now = datetime.now(tz=UTC)
            for candidate in structured_candidates:
                annotation_type, event_kind = self._normalize_structured_annotation_candidate(candidate)
                payload = candidate.model_dump(mode="json")
                payload["event_kind"] = event_kind
                if annotation_type != candidate.type:
                    payload["raw_annotation_type"] = candidate.type
                annotations.append(
                    self._repository.save_chat_annotation(
                        annotation_id=f"ann-{uuid4().hex}",
                        session_id=session.session_id,
                        message_id=message_id,
                        plan_id=None,
                        symbol=session.symbol,
                        contract_id=session.contract_id,
                        timeframe=session.timeframe,
                        annotation_type=annotation_type,
                        subtype=candidate.subtype or (candidate.type if annotation_type != candidate.type else None),
                        label=candidate.label or self._default_annotation_label(annotation_type),
                        reason=candidate.reason or "",
                        start_time=candidate.start_time or now,
                        end_time=candidate.end_time,
                        expires_at=candidate.expires_at,
                        status=candidate.status or "active",
                        priority=candidate.priority,
                        confidence=candidate.confidence,
                        visible=candidate.visible,
                        pinned=candidate.pinned,
                        source_kind=candidate.source_kind or ("replay_analysis" if getattr(replay_response, "live_context_summary", None) else "session_chat"),
                        payload=payload,
                        created_at=now,
                        updated_at=now,
                    )
                )
            return annotations

        annotations: list[StoredChatAnnotation] = []
        now = datetime.now(tz=UTC)
        if request is not None and self._should_enable_session_structured_output(request):
            annotations.extend(
                self._build_text_fallback_annotations(
                    session=session,
                    message_id=message_id,
                    reply_text=str(getattr(replay_response, "reply_text", "") or ""),
                    source_kind="session_chat" if getattr(replay_response, "session_only", False) else "replay_analysis",
                    now=now,
                )
            )
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
                        source_kind="session_chat" if getattr(replay_response, "session_only", False) else "replay_analysis",
                        payload={"entry_price": plan.entry_price, "side": plan.side, "event_kind": "plan"},
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
                        source_kind="session_chat" if getattr(replay_response, "session_only", False) else "replay_analysis",
                        payload={"stop_price": plan.stop_price, "side": plan.side, "event_kind": "plan"},
                        created_at=now,
                        updated_at=now,
                    )
                )
        return annotations

    @classmethod
    def _normalize_structured_annotation_candidate(cls, candidate) -> tuple[str, str]:
        raw_type = str(getattr(candidate, "type", "") or "").strip().lower()
        hint_parts = [
            str(getattr(candidate, "label", "") or ""),
            str(getattr(candidate, "reason", "") or ""),
            str(getattr(candidate, "subtype", "") or ""),
        ]
        hint_text = " ".join(part for part in hint_parts if part).lower()
        has_zone = getattr(candidate, "price_low", None) is not None or getattr(candidate, "price_high", None) is not None
        has_stop = getattr(candidate, "stop_price", None) is not None
        has_target = getattr(candidate, "target_price", None) is not None or getattr(candidate, "tp_level", None) is not None
        has_entry = getattr(candidate, "entry_price", None) is not None

        if raw_type in {"entry_line", "stop_loss", "take_profit", "support_zone", "resistance_zone", "no_trade_zone"}:
            return raw_type, cls._derive_annotation_event_kind(raw_type)
        if raw_type in {"plan", "plan_intent"}:
            if has_zone:
                return cls._infer_zone_annotation_type(hint_text, side=getattr(candidate, "side", None)), "plan"
            if has_stop and not has_entry and not has_target:
                return "stop_loss", "plan"
            if has_target:
                return "take_profit", "plan"
            return "entry_line", "plan"
        if raw_type in {"risk", "risk_note"}:
            return ("no_trade_zone" if has_zone else "stop_loss"), "risk"
        if raw_type in {"zone", "price_zone"}:
            return cls._infer_zone_annotation_type(hint_text, side=getattr(candidate, "side", None)), "zone"
        if raw_type in {"price", "key_level", "market_event", "thesis_fragment"}:
            if has_stop and not has_entry and not has_target:
                return "stop_loss", "risk"
            if has_target:
                return "take_profit", "price"
            if has_zone:
                return cls._infer_zone_annotation_type(hint_text, side=getattr(candidate, "side", None)), "zone"
            return "entry_line", "price"
        if has_zone:
            return cls._infer_zone_annotation_type(hint_text, side=getattr(candidate, "side", None)), "zone"
        if has_stop and not has_entry and not has_target:
            return "stop_loss", "risk"
        if has_target:
            return "take_profit", "price"
        return "entry_line", "price"

    @staticmethod
    def _infer_zone_annotation_type(hint_text: str, *, side: str | None = None) -> str:
        side_value = str(side or "").strip().lower()
        if re.search(r"风险|失效|无交易|谨慎|放弃|不要追|不能追|risk|invalid", hint_text):
            return "no_trade_zone"
        if re.search(r"阻力|压力|供给|反抽|空头|resistance|supply", hint_text) or side_value in {"sell", "short"}:
            return "resistance_zone"
        if re.search(r"支撑|需求|回踩|多头|support|demand", hint_text) or side_value in {"buy", "long"}:
            return "support_zone"
        return "zone"

    @staticmethod
    def _derive_annotation_event_kind(annotation_type: str, *, plan_id: str | None = None, payload: dict[str, Any] | None = None) -> str:
        payload_dict = payload if isinstance(payload, dict) else {}
        explicit_kind = str(payload_dict.get("event_kind") or "").strip().lower()
        if explicit_kind in {"plan", "zone", "risk", "price"}:
            return explicit_kind
        if plan_id:
            return "plan"
        normalized_type = str(annotation_type or "").strip().lower()
        if normalized_type in {"support_zone", "resistance_zone", "zone", "price_zone"}:
            return "zone"
        if normalized_type in {"no_trade_zone", "stop_loss", "risk", "risk_note"}:
            return "risk"
        if normalized_type in {"plan", "plan_intent"}:
            return "plan"
        return "price"

    @staticmethod
    def _default_annotation_label(annotation_type: str) -> str:
        return {
            "entry_line": "关键价位",
            "stop_loss": "风险位",
            "take_profit": "目标位",
            "support_zone": "支撑区域",
            "resistance_zone": "阻力区域",
            "no_trade_zone": "风险区域",
            "zone": "候选区域",
        }.get(annotation_type, "AI标记")

    def _build_text_fallback_annotations(
        self,
        *,
        session: StoredChatSession,
        message_id: str,
        reply_text: str,
        source_kind: str,
        now: datetime,
    ) -> list[StoredChatAnnotation]:
        text = (reply_text or "").strip()
        if not text:
            return []

        annotations: list[StoredChatAnnotation] = []
        seen_keys: set[str] = set()
        range_pattern = re.compile(r"(\d{3,6}(?:\.\d+)?)[\s]*(?:-|~|到|至)[\s]*(\d{3,6}(?:\.\d+)?)")
        single_pattern = re.compile(r"\d{3,6}(?:\.\d+)?")
        single_prices: list[tuple[float, int]] = []

        def _save_candidate(
            *,
            annotation_type: str,
            label: str,
            reason: str,
            payload: dict[str, Any],
        ) -> None:
            payload = dict(payload)
            payload.setdefault("event_kind", self._derive_annotation_event_kind(annotation_type, payload=payload))
            dedup_key = json.dumps(
                {
                    "type": annotation_type,
                    "label": label,
                    "price_low": payload.get("price_low"),
                    "price_high": payload.get("price_high"),
                    "entry_price": payload.get("entry_price"),
                    "stop_price": payload.get("stop_price"),
                    "target_price": payload.get("target_price"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if dedup_key in seen_keys:
                return
            seen_keys.add(dedup_key)
            annotations.append(
                self._repository.save_chat_annotation(
                    annotation_id=f"ann-{uuid4().hex}",
                    session_id=session.session_id,
                    message_id=message_id,
                    plan_id=None,
                    symbol=session.symbol,
                    contract_id=session.contract_id,
                    timeframe=session.timeframe,
                    annotation_type=annotation_type,
                    subtype=None,
                    label=label,
                    reason=reason,
                    start_time=now,
                    end_time=None,
                    expires_at=None,
                    status="active",
                    priority=None,
                    confidence=None,
                    visible=True,
                    pinned=False,
                    source_kind=source_kind,
                    payload=payload,
                    created_at=now,
                    updated_at=now,
                )
            )

        for match in range_pattern.finditer(text):
            low = float(match.group(1))
            high = float(match.group(2))
            price_low = min(low, high)
            price_high = max(low, high)
            context = text[max(0, match.start() - 24): min(len(text), match.end() + 24)]
            if re.search(r"风险|失效|谨慎|放弃|不要追|不能追", context):
                annotation_type = "no_trade_zone"
                label = "风险区域"
            elif re.search(r"阻力|压力|供给|反抽|空头", context):
                annotation_type = "resistance_zone"
                label = "阻力区域"
            elif re.search(r"支撑|需求|回踩|多头", context):
                annotation_type = "support_zone"
                label = "支撑区域"
            else:
                annotation_type = "zone"
                label = "候选区域"
            _save_candidate(
                annotation_type=annotation_type,
                label=label,
                reason=context.strip() or text[:120],
                payload={
                    "price_low": price_low,
                    "price_high": price_high,
                },
            )

        occupied_spans = [(m.start(), m.end()) for m in range_pattern.finditer(text)]
        for match in single_pattern.finditer(text):
            if any(start <= match.start() < end for start, end in occupied_spans):
                continue
            price = float(match.group(0))
            context = text[max(0, match.start() - 18): min(len(text), match.end() + 18)]
            if re.search(r"止损|失效|跌破|站不上|风险", context):
                single_prices.append((price, match.start()))
                _save_candidate(
                    annotation_type="no_trade_zone",
                    label="风险位",
                    reason=context.strip(),
                    payload={
                        "price_low": price - 6,
                        "price_high": price + 6,
                        "stop_price": price,
                    },
                )
                continue
            if re.search(r"止盈|目标|TP", context):
                _save_candidate(
                    annotation_type="take_profit",
                    label="目标位",
                    reason=context.strip(),
                    payload={
                        "target_price": price,
                        "tp_level": 1,
                    },
                )
                continue
            if re.search(r"入场|回踩|关注|突破", context):
                _save_candidate(
                    annotation_type="entry_line",
                    label="关键价位",
                    reason=context.strip(),
                    payload={
                        "entry_price": price,
                    },
                )

        if not annotations:
            risk_match = re.search(r"(风险|失效|谨慎|放弃|不要追|不能追)[^。；\n]*", text)
            anchor_price = single_prices[0][0] if single_prices else None
            if risk_match and anchor_price is not None:
                _save_candidate(
                    annotation_type="no_trade_zone",
                    label="风险提示",
                    reason=risk_match.group(0).strip(),
                    payload={
                        "price_low": anchor_price - 6,
                        "price_high": anchor_price + 6,
                        "stop_price": anchor_price,
                    },
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
            for item in self._list_recent_chat_messages(
                session_id,
                limit=10,
                roles={"user", "assistant"},
                require_content=True,
            ):
                if item.role in {"user", "assistant"} and item.content:
                    history.append(ReplayAiChatMessage(role=item.role, content=item.content))
        return history

    def _build_model_user_input(self, prepared: PreparedReplyTurn) -> str:
        request = prepared.request
        base_input = (request.user_input or "").strip()
        sections: list[str] = [base_input] if base_input else []

        contract_lines: list[str] = []
        if request.analysis_type:
            contract_lines.append(f"- analysis_type: {request.analysis_type}")
        if request.analysis_range:
            contract_lines.append(f"- analysis_range: {request.analysis_range}")
        if request.analysis_style:
            contract_lines.append(f"- analysis_style: {request.analysis_style}")
        if contract_lines:
            sections.append("[analysis_contract]\n" + "\n".join(contract_lines))

        if isinstance(request.extra_context, dict) and request.extra_context:
            context_lines: list[str] = []
            for key in sorted(request.extra_context.keys()):
                value = request.extra_context.get(key)
                if value in (None, "", [], {}):
                    continue
                if isinstance(value, str):
                    rendered = value.strip()
                else:
                    rendered = json.dumps(value, ensure_ascii=False)
                rendered = rendered[:600] + ("..." if len(rendered) > 600 else "")
                context_lines.append(f"- {key}: {rendered}")
            if context_lines:
                sections.append("[extra_context]\n" + "\n".join(context_lines))

        block_lines = self._collect_prompt_block_context(
            prepared.session,
            [*request.selected_block_ids, *request.pinned_block_ids],
        )
        if block_lines:
            sections.append("[selected_prompt_blocks]\n" + "\n".join(block_lines))

        if self._should_enable_session_structured_output(request):
            sections.append(
                "[output_requirements]\n"
                "- Prefer structured annotations for concrete price levels/zones/invalidation points.\n"
                "- Prefer one compact plan card when a clear executable plan is present.\n"
                "- Keep reply_text concise and evidence-first."
            )

        combined = "\n\n".join(part for part in sections if part.strip())
        return combined or request.user_input

    def _collect_prompt_block_context(self, session: StoredChatSession, block_ids: list[str]) -> list[str]:
        ordered_ids = list(dict.fromkeys(block_ids))
        lines: list[str] = []
        for block_id in ordered_ids:
            block = self._repository.get_prompt_block(block_id)
            if block is None:
                continue
            if block.session_id != session.session_id and (block.symbol != session.symbol or block.contract_id != session.contract_id):
                continue
            preview = (block.preview_text or "").strip()
            preview = preview[:200] + ("..." if len(preview) > 200 else "")
            head = f"- {block.kind}: {block.title}"
            if preview:
                head = f"{head} | {preview}"
            payload_excerpt = self._compact_prompt_block_payload(block.full_payload)
            if payload_excerpt:
                head = f"{head}\n  full_payload: {payload_excerpt}"
            lines.append(head)
        return lines[:12]

    @staticmethod
    def _compact_prompt_block_payload(payload: dict[str, Any] | None, max_chars: int = 900) -> str:
        if not isinstance(payload, dict) or not payload:
            return ""
        try:
            rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            rendered = str(payload)
        rendered = re.sub(r"\s+", " ", rendered).strip()
        if len(rendered) > max_chars:
            rendered = rendered[:max_chars] + "..."
        return rendered

    @staticmethod
    def _should_enable_session_structured_output(request: ChatReplyRequest) -> bool:
        analysis_type = (request.analysis_type or "").strip().lower()
        if analysis_type in {"event_timeline", "event_extraction", "event_scribe", "event_summary"}:
            return True
        return False

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
        messages = self._repository.list_chat_messages(session_id=session_id, limit=50, latest=True)
        for item in reversed(messages):
            if role is None or item.role == role:
                return item
        return None

    def _list_recent_chat_messages(
        self,
        session_id: str,
        *,
        limit: int,
        roles: set[str] | None = None,
        include_pending: bool = False,
        require_content: bool = False,
    ) -> list[StoredChatMessage]:
        if limit <= 0:
            return []
        messages = self._repository.list_chat_messages(
            session_id=session_id,
            limit=max(limit * 10, 100),
            latest=True,
        )
        filtered: list[StoredChatMessage] = []
        for item in messages:
            if roles is not None and item.role not in roles:
                continue
            if not include_pending and item.status == "pending":
                continue
            content = (item.content or "").strip()
            if content == "正在思考中…":
                continue
            if require_content and not content:
                continue
            filtered.append(item)
        return filtered[-limit:]

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
            include_memory_summary=stored.include_memory_summary,
            include_recent_messages=stored.include_recent_messages,
            mounted_reply_ids=stored.mounted_reply_ids,
            active_plan_id=stored.active_plan_id,
            memory_summary_id=stored.memory_summary_id,
            unread_count=stored.unread_count,
            scroll_offset=stored.scroll_offset,
            pinned=stored.pinned,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    @staticmethod
    def _attachments_from_payload(payload: dict[str, Any] | None) -> list[ReplayAiChatAttachment]:
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("attachments")
        if not isinstance(raw_items, list):
            return []
        attachments: list[ReplayAiChatAttachment] = []
        for item in raw_items:
            try:
                attachments.append(ReplayAiChatAttachment.model_validate(item))
            except Exception:
                continue
        return attachments

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
            attachments=self._attachments_from_payload(stored.request_payload),
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
        payload = stored.payload if isinstance(stored.payload, dict) else {}
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
            event_kind=self._derive_annotation_event_kind(stored.annotation_type, plan_id=stored.plan_id, payload=payload),
            side=payload.get("side"),
            entry_price=payload.get("entry_price"),
            stop_price=payload.get("stop_price"),
            target_price=payload.get("target_price"),
            tp_level=payload.get("tp_level"),
            price_low=payload.get("price_low"),
            price_high=payload.get("price_high"),
            path_points=payload.get("path_points") if isinstance(payload.get("path_points"), list) else [],
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

