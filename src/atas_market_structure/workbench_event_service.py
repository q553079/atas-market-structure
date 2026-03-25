from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    CreateEventCandidateRequest,
    EventCandidateKind,
    EventCandidateLifecycleState,
    EventCandidateSourceType,
    EventCandidatePatchRequest,
    EventLifecycleAction,
    EventMutationEnvelope,
    EventPromotionTarget,
    EventStreamAction,
    EventStreamEnvelope,
    EventStreamExtractRequest,
    EventStreamQuery,
    PromoteEventCandidateRequest,
)
from atas_market_structure.repository import (
    AnalysisRepository,
    StoredChatAnnotation,
    StoredChatPlanCard,
    StoredChatSession,
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventStreamEntry,
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
            source_prompt_trace_id=request.source_prompt_trace_id,
            lifecycle_state=EventCandidateLifecycleState.CANDIDATE.value,
            invalidation_rule=request.invalidation_rule,
            evaluation_window=request.evaluation_window,
            metadata=request.metadata,
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

        session = self._require_session(request.session_id)
        message = self._resolve_source_message(request.session_id, request.source_message_id)
        self._extract_and_persist_candidates(
            session=session,
            source_message_id=message.message_id,
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

        current = self._require_candidate(event_id)
        now = datetime.now(tz=UTC)
        metadata = dict(current.metadata)
        if request.metadata:
            metadata.update(request.metadata)
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

        candidate = self._require_candidate(event_id)
        if request.target == EventPromotionTarget.ANNOTATION:
            return self.mount_event_candidate(event_id)
        return self._promote_to_plan_card(candidate)

    def mount_event_candidate(self, event_id: str) -> EventMutationEnvelope:
        """Mount one candidate to the chart-facing annotation layer."""

        candidate = self._require_candidate(event_id)
        if candidate.candidate_kind not in {
            EventCandidateKind.KEY_LEVEL.value,
            EventCandidateKind.PRICE_ZONE.value,
            EventCandidateKind.RISK_NOTE.value,
            EventCandidateKind.MARKET_EVENT.value,
        }:
            raise ReplayWorkbenchChatError(f"Candidate kind '{candidate.candidate_kind}' cannot be mounted to chart.")
        updated, annotation = self._ensure_annotation_projection(candidate)
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

        response_payload = replay_response.model_dump(mode="json") if hasattr(replay_response, "model_dump") else {}
        reply_text = str(getattr(replay_response, "reply_text", "") or "")
        extracted = self._extract_and_persist_candidates(
            session=session,
            source_message_id=source_message_id,
            source_prompt_trace_id=source_prompt_trace_id,
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
