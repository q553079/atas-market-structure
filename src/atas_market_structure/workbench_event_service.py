from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    CreateEventCandidateRequest,
    EventCandidate,
    EventCandidateKind,
    EventCandidateLifecycleState,
    EventCandidateSourceType,
    EventCandidatePatchRequest,
    EventMemoryEntry,
    EventLifecycleAction,
    EventMutationEnvelope,
    EventPromotionTarget,
    EventStreamAction,
    EventStreamEntry,
    EventStreamEnvelope,
    EventStreamExtractRequest,
    EventStreamQuery,
    PromoteEventCandidateRequest,
)
from atas_market_structure.repository import (
    AnalysisRepository,
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventStreamEntry,
    StoredPromptTrace,
)
from atas_market_structure.workbench_common import ReplayWorkbenchChatError, ReplayWorkbenchNotFoundError
from atas_market_structure.workbench_event_draft_support import ReplyEventBackboneResult, ReplayWorkbenchEventDraftSupport
from atas_market_structure.workbench_event_projection_support import ReplayWorkbenchEventProjectionSupport


class ReplayWorkbenchEventService(ReplayWorkbenchEventProjectionSupport, ReplayWorkbenchEventDraftSupport):
    """Owns replay-workbench event candidates, stream history, and derived projections."""

    _TERMINAL_STATES = {
        EventCandidateLifecycleState.IGNORED,
        EventCandidateLifecycleState.EXPIRED,
        EventCandidateLifecycleState.ARCHIVED,
    }
    _LIFECYCLE_ACTION_TARGETS = {
        EventLifecycleAction.CONFIRM: EventCandidateLifecycleState.CONFIRMED,
        EventLifecycleAction.ARCHIVE: EventCandidateLifecycleState.ARCHIVED,
        EventLifecycleAction.EXPIRE: EventCandidateLifecycleState.EXPIRED,
    }
    _ALLOWED_TRANSITIONS = {
        EventCandidateLifecycleState.CANDIDATE: {
            EventCandidateLifecycleState.CONFIRMED,
            EventCandidateLifecycleState.MOUNTED,
            EventCandidateLifecycleState.PROMOTED_PLAN,
            EventCandidateLifecycleState.IGNORED,
            EventCandidateLifecycleState.EXPIRED,
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.CONFIRMED: {
            EventCandidateLifecycleState.MOUNTED,
            EventCandidateLifecycleState.PROMOTED_PLAN,
            EventCandidateLifecycleState.IGNORED,
            EventCandidateLifecycleState.EXPIRED,
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.MOUNTED: {
            EventCandidateLifecycleState.EXPIRED,
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.PROMOTED_PLAN: {
            EventCandidateLifecycleState.EXPIRED,
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.IGNORED: {
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.EXPIRED: {
            EventCandidateLifecycleState.ARCHIVED,
        },
        EventCandidateLifecycleState.ARCHIVED: set(),
    }

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def build_event_stream(self, query: EventStreamQuery) -> EventStreamEnvelope:
        """Return the current event candidates, stream rows, and memory rows for one session."""

        self._reset_presentation_projection_cache()
        self._require_session(query.session_id)
        candidates = self._repository.list_event_candidates_by_session(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=str(query.timeframe) if query.timeframe is not None else None,
            source_message_id=query.source_message_id,
            limit=query.limit,
        )
        stream_entries = self._repository.list_event_stream_entries(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=str(query.timeframe) if query.timeframe is not None else None,
            source_message_id=query.source_message_id,
            limit=max(query.limit, 500),
        )
        memory_entries = self._repository.list_event_memory_entries(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=str(query.timeframe) if query.timeframe is not None else None,
            limit=max(query.limit, 500),
        )
        return EventStreamEnvelope(
            query=query,
            candidates=[self._candidate_model(item) for item in candidates],
            items=[self._stream_model(item) for item in stream_entries],
            memory_entries=[self._memory_model(item) for item in memory_entries],
        )

    def create_event_candidate(self, request: CreateEventCandidateRequest) -> EventMutationEnvelope:
        """Create one operator-authored event candidate and append it to stream and memory."""

        self._reset_presentation_projection_cache()
        session = self._require_session(request.session_id)
        now = datetime.now(tz=UTC)
        source_message_id = request.source_message_id
        if source_message_id is None and request.source_type in {
            EventCandidateSourceType.MANUAL,
            EventCandidateSourceType.USER_CREATED,
        }:
            try:
                source_message_id = self._resolve_source_message(session.session_id, None).message_id
            except ReplayWorkbenchNotFoundError:
                source_message_id = None
        source_message = self._get_source_message_record(session.session_id, source_message_id)
        resolved_prompt_trace_id = self._resolve_source_prompt_trace_id(
            source_message_id=source_message_id,
            source_prompt_trace_id=request.source_prompt_trace_id,
            source_message=source_message,
        )
        metadata = self._with_presentation_metadata(
            request.metadata,
            source_message_id=source_message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            anchor_start_ts=request.anchor_start_ts,
            anchor_end_ts=request.anchor_end_ts,
            price_lower=request.price_lower,
            price_upper=request.price_upper,
            price_ref=request.price_ref,
            is_fixed_anchor=False,
        )
        candidate = self._repository.save_event_candidate(
            event_id=f"evt-{uuid4().hex}",
            session_id=session.session_id,
            candidate_kind=request.candidate_kind.value,
            title=request.title,
            summary=request.summary,
            symbol=request.symbol or session.symbol,
            timeframe=str(request.timeframe or session.timeframe),
            anchor_start_ts=request.anchor_start_ts,
            anchor_end_ts=request.anchor_end_ts,
            price_lower=request.price_lower,
            price_upper=request.price_upper,
            price_ref=request.price_ref,
            side_hint=request.side_hint,
            confidence=request.confidence,
            evidence_refs=request.evidence_refs,
            source_type=request.source_type.value,
            source_message_id=source_message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            lifecycle_state=EventCandidateLifecycleState.CANDIDATE.value,
            invalidation_rule=request.invalidation_rule,
            evaluation_window=request.evaluation_window,
            metadata=metadata,
            dedup_key=None,
            promoted_projection_type=None,
            promoted_projection_id=None,
            created_at=now,
            updated_at=now,
        )
        stream_entry = self._append_stream_entry(candidate, EventStreamAction.CREATED)
        memory_entry = self._upsert_memory_entry(candidate)
        return EventMutationEnvelope(
            session_id=candidate.session_id,
            candidate=self._candidate_model(candidate),
            stream_entry=self._stream_model(stream_entry),
            memory_entry=self._memory_model(memory_entry),
        )

    def extract_event_stream(self, request: EventStreamExtractRequest) -> EventStreamEnvelope:
        """Extract candidates from one assistant message and return the refreshed event stream."""

        self._reset_presentation_projection_cache()
        session = self._require_session(request.session_id)
        message = self._resolve_source_message(request.session_id, request.source_message_id)
        resolved_prompt_trace_id = self._resolve_source_prompt_trace_id(
            source_message_id=message.message_id,
            source_prompt_trace_id=message.prompt_trace_id,
            source_message=message,
        )
        self._extract_and_persist_candidates(
            session=session,
            source_message_id=message.message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            reply_text=message.content,
            response_payload=message.response_payload,
        )
        return self.build_event_stream(
            EventStreamQuery(
                session_id=request.session_id,
                symbol=request.symbol or session.symbol,
                timeframe=request.timeframe or session.timeframe,
                source_message_id=message.message_id,
                limit=request.limit,
            )
        )

    def patch_event_candidate(self, event_id: str, request: EventCandidatePatchRequest) -> EventMutationEnvelope:
        """Patch editable candidate fields and optionally apply one validated lifecycle action."""

        self._reset_presentation_projection_cache()
        current = self._require_candidate(event_id)
        now = datetime.now(tz=UTC)
        metadata = self._merge_event_metadata(current.metadata, request.metadata)
        metadata = self._with_presentation_metadata(
            metadata,
            source_message_id=current.source_message_id,
            source_prompt_trace_id=current.source_prompt_trace_id,
            anchor_start_ts=current.anchor_start_ts,
            anchor_end_ts=current.anchor_end_ts,
            price_lower=current.price_lower,
            price_upper=current.price_upper,
            price_ref=current.price_ref,
        )
        patched_candidate = current
        if any(
            value is not None
            for value in (
                request.title,
                request.summary,
                request.side_hint,
                request.confidence,
                request.invalidation_rule,
                request.evaluation_window,
                request.metadata,
            )
        ):
            patched_candidate = self._repository.patch_event_candidate(
                event_id,
                title=request.title if request.title is not None else current.title,
                summary=request.summary if request.summary is not None else current.summary,
                side_hint=request.side_hint if request.side_hint is not None else current.side_hint,
                confidence=request.confidence if request.confidence is not None else current.confidence,
                invalidation_rule=request.invalidation_rule if request.invalidation_rule is not None else current.invalidation_rule,
                evaluation_window=request.evaluation_window if request.evaluation_window is not None else current.evaluation_window,
                metadata=metadata,
                updated_at=now,
            )
            if patched_candidate is None:  # pragma: no cover
                raise ReplayWorkbenchChatError(f"Event candidate '{event_id}' disappeared during patch.")
        if request.lifecycle_action is not None:
            target_state = self._LIFECYCLE_ACTION_TARGETS[request.lifecycle_action]
            transitioned = self._transition_candidate(patched_candidate, target_state, metadata=request.metadata or {})
            stream_entry = self._append_stream_entry(
                transitioned,
                EventStreamAction.STATE_TRANSITION,
                metadata={"lifecycle_action": request.lifecycle_action.value},
            )
            memory_entry = self._upsert_memory_entry(transitioned)
            return EventMutationEnvelope(
                session_id=transitioned.session_id,
                candidate=self._candidate_model(transitioned),
                stream_entry=self._stream_model(stream_entry),
                memory_entry=self._memory_model(memory_entry),
            )
        updated = patched_candidate
        stream_entry = self._append_stream_entry(updated, EventStreamAction.PATCHED)
        memory_entry = self._upsert_memory_entry(updated)
        return EventMutationEnvelope(
            session_id=updated.session_id,
            candidate=self._candidate_model(updated),
            stream_entry=self._stream_model(stream_entry),
            memory_entry=self._memory_model(memory_entry),
        )

    def promote_event_candidate(self, event_id: str, request: PromoteEventCandidateRequest) -> EventMutationEnvelope:
        """Promote one candidate to a derived annotation or plan card."""

        self._reset_presentation_projection_cache()
        candidate = self._require_candidate(event_id)
        if request.target == EventPromotionTarget.ANNOTATION:
            return self.mount_event_candidate(event_id)
        return self._promote_to_plan_card(candidate)

    def mount_event_candidate(self, event_id: str) -> EventMutationEnvelope:
        """Mount one candidate to the chart-facing annotation layer."""

        self._reset_presentation_projection_cache()
        candidate = self._require_candidate(event_id)
        if candidate.candidate_kind not in {
            EventCandidateKind.KEY_LEVEL.value,
            EventCandidateKind.PRICE_ZONE.value,
            EventCandidateKind.RISK_NOTE.value,
            EventCandidateKind.MARKET_EVENT.value,
        }:
            raise ReplayWorkbenchChatError(f"Candidate kind '{candidate.candidate_kind}' cannot be mounted to chart.")
        updated, annotation = self._ensure_annotation_projection(candidate)
        updated = self._mark_fixed_anchor(updated, is_fixed_anchor=True)
        stream_entry = self._append_stream_entry(
            updated,
            EventStreamAction.PROMOTED,
            metadata={"target": EventPromotionTarget.ANNOTATION.value},
        )
        memory_entry = self._upsert_memory_entry(updated)
        return EventMutationEnvelope(
            session_id=updated.session_id,
            candidate=self._candidate_model(updated),
            stream_entry=self._stream_model(stream_entry),
            memory_entry=self._memory_model(memory_entry),
            projected_annotation=self._annotation_model(annotation),
        )

    def ignore_event_candidate(self, event_id: str) -> EventMutationEnvelope:
        """Transition one candidate to the ignored state."""

        self._reset_presentation_projection_cache()
        candidate = self._require_candidate(event_id)
        updated = self._transition_candidate(candidate, EventCandidateLifecycleState.IGNORED)
        stream_entry = self._append_stream_entry(
            updated,
            EventStreamAction.STATE_TRANSITION,
            metadata={"target_state": EventCandidateLifecycleState.IGNORED.value},
        )
        memory_entry = self._upsert_memory_entry(updated)
        return EventMutationEnvelope(
            session_id=updated.session_id,
            candidate=self._candidate_model(updated),
            stream_entry=self._stream_model(stream_entry),
            memory_entry=self._memory_model(memory_entry),
        )

    def process_reply_event_backbone(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        source_prompt_trace_id: str | None = None,
        replay_response,
    ) -> ReplyEventBackboneResult:
        """Extract candidates from one reply and derive compatibility projections."""

        self._reset_presentation_projection_cache()
        response_payload = replay_response.model_dump(mode="json") if hasattr(replay_response, "model_dump") else {}
        reply_text = str(getattr(replay_response, "reply_text", "") or "")
        resolved_prompt_trace_id = self._resolve_source_prompt_trace_id(
            source_message_id=source_message_id,
            source_prompt_trace_id=source_prompt_trace_id,
            source_message=self._get_source_message_record(session.session_id, source_message_id),
        )
        extracted = self._extract_and_persist_candidates(
            session=session,
            source_message_id=source_message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            reply_text=reply_text,
            response_payload=response_payload,
        )
        annotations: list[StoredChatAnnotation] = []
        plan_cards: list[StoredChatPlanCard] = []
        for candidate in extracted:
            if candidate.candidate_kind == EventCandidateKind.PLAN_INTENT.value:
                if bool(candidate.metadata.get("compat_emit_annotation", False)):
                    _, annotation = self._ensure_annotation_projection(candidate)
                    annotations.append(annotation)
                    candidate = self._require_candidate(candidate.event_id)
                _, plan_card = self._ensure_plan_projection(candidate)
                plan_cards.append(plan_card)
            elif candidate.candidate_kind in {
                EventCandidateKind.KEY_LEVEL.value,
                EventCandidateKind.PRICE_ZONE.value,
                EventCandidateKind.RISK_NOTE.value,
                EventCandidateKind.MARKET_EVENT.value,
            }:
                _, annotation = self._ensure_annotation_projection(candidate)
                annotations.append(annotation)
        latest_candidates = [self._require_candidate(item.event_id) for item in extracted]
        memory_entries = [self._upsert_memory_entry(item) for item in latest_candidates]
        return ReplyEventBackboneResult(
            candidates=latest_candidates,
            stream_entries=self._repository.list_event_stream_entries(
                session_id=session.session_id,
                source_message_id=source_message_id,
                limit=1000,
            ),
            memory_entries=memory_entries,
            annotations=annotations,
            plan_cards=plan_cards,
        )

    def _extract_and_persist_candidates(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        source_prompt_trace_id: str | None = None,
        reply_text: str,
        response_payload: dict[str, Any],
    ) -> list[StoredEventCandidate]:
        existing = self._repository.list_event_candidates_by_session(
            session_id=session.session_id,
            source_message_id=source_message_id,
            limit=1000,
        )
        existing_by_dedup = {item.dedup_key: item for item in existing if item.dedup_key}
        drafts = self._extract_candidate_drafts(
            session=session,
            source_message_id=source_message_id,
            reply_text=reply_text,
            response_payload=response_payload,
        )
        persisted: list[StoredEventCandidate] = []
        for draft in drafts:
            if source_prompt_trace_id and not draft.source_prompt_trace_id:
                draft.source_prompt_trace_id = source_prompt_trace_id
            if draft.dedup_key and draft.dedup_key in existing_by_dedup:
                persisted.append(existing_by_dedup[draft.dedup_key])
                continue
            candidate = self._save_candidate_from_draft(session, draft)
            self._append_stream_entry(candidate, EventStreamAction.EXTRACTED)
            self._upsert_memory_entry(candidate)
            persisted.append(candidate)
        return persisted

    def _save_candidate_from_draft(self, session: StoredChatSession, draft) -> StoredEventCandidate:
        now = datetime.now(tz=UTC)
        resolved_prompt_trace_id = self._resolve_source_prompt_trace_id(
            source_message_id=draft.source_message_id,
            source_prompt_trace_id=draft.source_prompt_trace_id,
            source_message=self._get_source_message_record(session.session_id, draft.source_message_id),
        )
        metadata = self._with_presentation_metadata(
            draft.metadata or {},
            source_message_id=draft.source_message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            anchor_start_ts=draft.anchor_start_ts,
            anchor_end_ts=draft.anchor_end_ts,
            price_lower=draft.price_lower,
            price_upper=draft.price_upper,
            price_ref=draft.price_ref,
            is_fixed_anchor=False,
        )
        return self._repository.save_event_candidate(
            event_id=f"evt-{uuid4().hex}",
            session_id=session.session_id,
            candidate_kind=draft.candidate_kind.value,
            title=draft.title,
            summary=draft.summary,
            symbol=draft.symbol,
            timeframe=draft.timeframe,
            anchor_start_ts=draft.anchor_start_ts,
            anchor_end_ts=draft.anchor_end_ts,
            price_lower=draft.price_lower,
            price_upper=draft.price_upper,
            price_ref=draft.price_ref,
            side_hint=draft.side_hint,
            confidence=draft.confidence,
            evidence_refs=draft.evidence_refs or [],
            source_type=draft.source_type.value,
            source_message_id=draft.source_message_id,
            source_prompt_trace_id=resolved_prompt_trace_id,
            lifecycle_state=EventCandidateLifecycleState.CANDIDATE.value,
            invalidation_rule=draft.invalidation_rule or {},
            evaluation_window=draft.evaluation_window or {},
            metadata=metadata,
            dedup_key=draft.dedup_key or self._build_dedup_key(draft),
            promoted_projection_type=None,
            promoted_projection_id=None,
            created_at=now,
            updated_at=now,
        )

    def _transition_candidate(
        self,
        candidate: StoredEventCandidate,
        target_state: EventCandidateLifecycleState,
        *,
        metadata: dict[str, Any] | None = None,
        promoted_projection_type: str | None = None,
        promoted_projection_id: str | None = None,
    ) -> StoredEventCandidate:
        merged_metadata = self._merge_event_metadata(candidate.metadata, metadata)
        merged_metadata = self._with_presentation_metadata(
            merged_metadata,
            source_message_id=candidate.source_message_id,
            source_prompt_trace_id=candidate.source_prompt_trace_id,
            anchor_start_ts=candidate.anchor_start_ts,
            anchor_end_ts=candidate.anchor_end_ts,
            price_lower=candidate.price_lower,
            price_upper=candidate.price_upper,
            price_ref=candidate.price_ref,
            is_fixed_anchor=None,
        )
        return super()._transition_candidate(
            candidate,
            target_state,
            metadata=merged_metadata,
            promoted_projection_type=promoted_projection_type,
            promoted_projection_id=promoted_projection_id,
        )

    def _candidate_model(self, stored: StoredEventCandidate) -> EventCandidate:
        return super()._candidate_model(stored).model_copy(update={"metadata": self._project_event_metadata(stored)})

    def _stream_model(self, stored: StoredEventStreamEntry) -> EventStreamEntry:
        return super()._stream_model(stored).model_copy(update={"metadata": self._project_event_metadata(stored)})

    def _memory_model(self, stored: StoredEventMemoryEntry) -> EventMemoryEntry:
        return super()._memory_model(stored).model_copy(update={"metadata": self._project_event_metadata(stored)})

    def _project_event_metadata(
        self,
        stored: StoredEventCandidate | StoredEventStreamEntry | StoredEventMemoryEntry,
    ) -> dict[str, Any]:
        return self._with_presentation_metadata(
            stored.metadata,
            source_message_id=stored.source_message_id,
            source_prompt_trace_id=stored.source_prompt_trace_id,
            anchor_start_ts=stored.anchor_start_ts,
            anchor_end_ts=stored.anchor_end_ts,
            price_lower=stored.price_lower,
            price_upper=stored.price_upper,
            price_ref=stored.price_ref,
        )

    def _mark_fixed_anchor(self, candidate: StoredEventCandidate, *, is_fixed_anchor: bool) -> StoredEventCandidate:
        metadata = self._with_presentation_metadata(
            candidate.metadata,
            source_message_id=candidate.source_message_id,
            source_prompt_trace_id=candidate.source_prompt_trace_id,
            anchor_start_ts=candidate.anchor_start_ts,
            anchor_end_ts=candidate.anchor_end_ts,
            price_lower=candidate.price_lower,
            price_upper=candidate.price_upper,
            price_ref=candidate.price_ref,
            is_fixed_anchor=is_fixed_anchor,
        )
        if metadata == candidate.metadata:
            return candidate
        updated = self._repository.patch_event_candidate(
            candidate.event_id,
            metadata=metadata,
            updated_at=datetime.now(tz=UTC),
        )
        return updated if updated is not None else candidate

    def _with_presentation_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        source_message_id: str | None,
        source_prompt_trace_id: str | None,
        anchor_start_ts: datetime | None,
        anchor_end_ts: datetime | None,
        price_lower: float | None,
        price_upper: float | None,
        price_ref: float | None,
        is_fixed_anchor: bool | None = None,
    ) -> dict[str, Any]:
        base_metadata = self._coerce_metadata(metadata)
        existing_presentation = self._coerce_metadata(base_metadata.get("presentation"))
        source_message = self._get_source_message_record(None, source_message_id)
        prompt_trace = self._get_source_prompt_trace_record(
            source_message_id=source_message_id,
            source_prompt_trace_id=source_prompt_trace_id,
            source_message=source_message,
        )
        workbench_ui = self._extract_workbench_ui(source_message)
        resolved_prompt_trace_id = self._clean_string(
            source_prompt_trace_id
            or existing_presentation.get("source_prompt_trace_id")
            or (prompt_trace.prompt_trace_id if prompt_trace is not None else None)
        )
        reply_window_anchor = self._clean_string(
            existing_presentation.get("reply_window_anchor")
            or workbench_ui.get("reply_window_anchor")
            or (prompt_trace.snapshot.get("reply_window_anchor") if prompt_trace is not None else None)
            or (prompt_trace.metadata.get("reply_window_anchor") if prompt_trace is not None else None)
        )
        source_object_ids = self._normalize_string_list(
            existing_presentation.get("source_object_ids")
            or workbench_ui.get("source_object_ids")
        )
        anchor_time = self._serialize_datetime_value(anchor_start_ts or anchor_end_ts)
        anchor_price = self._resolve_anchor_price(price_ref=price_ref, price_lower=price_lower, price_upper=price_upper)
        fixed_anchor_default = bool(existing_presentation.get("is_fixed_anchor") is True or base_metadata.get("fixed_anchor") is True)
        presentation = {
            **existing_presentation,
            "source_message_id": self._clean_string(source_message_id) or self._clean_string(existing_presentation.get("source_message_id")),
            "source_prompt_trace_id": resolved_prompt_trace_id or None,
            "anchor_time": existing_presentation.get("anchor_time") or anchor_time,
            "anchor_price": existing_presentation.get("anchor_price", anchor_price),
            "is_fixed_anchor": fixed_anchor_default if is_fixed_anchor is None else bool(is_fixed_anchor),
            "reply_window_anchor": reply_window_anchor or None,
        }
        if source_object_ids:
            presentation["source_object_ids"] = source_object_ids
        elif "source_object_ids" in presentation and not presentation["source_object_ids"]:
            presentation.pop("source_object_ids", None)
        sanitized_presentation = {
            key: value
            for key, value in presentation.items()
            if value is not None
        }
        sanitized_presentation["is_fixed_anchor"] = bool(presentation.get("is_fixed_anchor"))
        next_metadata = {**base_metadata, "presentation": sanitized_presentation}
        return next_metadata

    def _merge_event_metadata(
        self,
        current_metadata: dict[str, Any] | None,
        patch_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        current = self._coerce_metadata(current_metadata)
        patch = self._coerce_metadata(patch_metadata)
        if not patch:
            return dict(current)
        merged = {**current, **patch}
        if "presentation" in current or "presentation" in patch:
            merged["presentation"] = {
                **self._coerce_metadata(current.get("presentation")),
                **self._coerce_metadata(patch.get("presentation")),
            }
        return merged

    def _reset_presentation_projection_cache(self) -> None:
        self._source_message_cache: dict[str, StoredChatMessage | None] = {}
        self._prompt_trace_cache: dict[str, StoredPromptTrace | None] = {}
        self._prompt_trace_by_message_cache: dict[str, StoredPromptTrace | None] = {}

    def _get_source_message_record(
        self,
        session_id: str | None,
        source_message_id: str | None,
    ) -> StoredChatMessage | None:
        normalized_message_id = self._clean_string(source_message_id)
        if not normalized_message_id:
            return None
        cache = getattr(self, "_source_message_cache", None)
        if cache is None:
            self._reset_presentation_projection_cache()
            cache = self._source_message_cache
        if normalized_message_id in cache:
            return cache[normalized_message_id]
        message = self._repository.get_chat_message(normalized_message_id)
        if message is not None and session_id and message.session_id != session_id:
            message = None
        cache[normalized_message_id] = message
        return message

    def _resolve_source_prompt_trace_id(
        self,
        *,
        source_message_id: str | None,
        source_prompt_trace_id: str | None,
        source_message: StoredChatMessage | None = None,
    ) -> str | None:
        explicit_trace_id = self._clean_string(source_prompt_trace_id)
        if explicit_trace_id:
            return explicit_trace_id
        if source_message is not None:
            message_trace_id = self._clean_string(source_message.prompt_trace_id)
            if message_trace_id:
                return message_trace_id
        trace_by_message = self._get_prompt_trace_by_message(source_message_id)
        return trace_by_message.prompt_trace_id if trace_by_message is not None else None

    def _get_source_prompt_trace_record(
        self,
        *,
        source_message_id: str | None,
        source_prompt_trace_id: str | None,
        source_message: StoredChatMessage | None = None,
    ) -> StoredPromptTrace | None:
        resolved_trace_id = self._resolve_source_prompt_trace_id(
            source_message_id=source_message_id,
            source_prompt_trace_id=source_prompt_trace_id,
            source_message=source_message,
        )
        if not resolved_trace_id:
            return self._get_prompt_trace_by_message(source_message_id)
        cache = getattr(self, "_prompt_trace_cache", None)
        if cache is None:
            self._reset_presentation_projection_cache()
            cache = self._prompt_trace_cache
        if resolved_trace_id in cache:
            return cache[resolved_trace_id]
        prompt_trace = self._repository.get_prompt_trace(resolved_trace_id)
        cache[resolved_trace_id] = prompt_trace
        return prompt_trace

    def _get_prompt_trace_by_message(self, source_message_id: str | None) -> StoredPromptTrace | None:
        normalized_message_id = self._clean_string(source_message_id)
        if not normalized_message_id:
            return None
        cache = getattr(self, "_prompt_trace_by_message_cache", None)
        if cache is None:
            self._reset_presentation_projection_cache()
            cache = self._prompt_trace_by_message_cache
        if normalized_message_id in cache:
            return cache[normalized_message_id]
        prompt_trace = self._repository.get_prompt_trace_by_message(normalized_message_id)
        cache[normalized_message_id] = prompt_trace
        return prompt_trace

    @staticmethod
    def _extract_workbench_ui(source_message: StoredChatMessage | None) -> dict[str, Any]:
        response_payload = source_message.response_payload if source_message is not None else None
        workbench_ui = response_payload.get("workbench_ui") if isinstance(response_payload, dict) else None
        return workbench_ui if isinstance(workbench_ui, dict) else {}

    @staticmethod
    def _resolve_anchor_price(
        *,
        price_ref: float | None,
        price_lower: float | None,
        price_upper: float | None,
    ) -> float | None:
        if price_ref is not None:
            return price_ref
        if price_lower is not None and price_upper is not None:
            return round((price_lower + price_upper) / 2.0, 6)
        return price_lower if price_lower is not None else price_upper

    @staticmethod
    def _serialize_datetime_value(value: datetime | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _coerce_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None

    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for item in value:
            cleaned = cls._clean_string(item)
            if cleaned:
                normalized.append(cleaned)
        return normalized
