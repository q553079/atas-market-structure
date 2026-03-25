from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    ChatAnnotation,
    ChatPlanCard,
    EventCandidate,
    EventCandidateKind,
    EventCandidateLifecycleState,
    EventMemoryBucket,
    EventMemoryEntry,
    EventMutationEnvelope,
    EventPromotionTarget,
    EventStreamAction,
    EventStreamEntry,
)
from atas_market_structure.repository import (
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventStreamEntry,
)
from atas_market_structure.workbench_common import ReplayWorkbenchChatError, ReplayWorkbenchNotFoundError


class ReplayWorkbenchEventProjectionSupport:
    def _append_stream_entry(
        self,
        candidate: StoredEventCandidate,
        action: EventStreamAction,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> StoredEventStreamEntry:
        now = datetime.now(tz=UTC)
        merged_metadata = dict(candidate.metadata)
        if metadata:
            merged_metadata.update(metadata)
        return self._repository.save_event_stream_entry(
            stream_entry_id=f"estream-{uuid4().hex}",
            event_id=candidate.event_id,
            session_id=candidate.session_id,
            candidate_kind=candidate.candidate_kind,
            title=candidate.title,
            summary=candidate.summary,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            anchor_start_ts=candidate.anchor_start_ts,
            anchor_end_ts=candidate.anchor_end_ts,
            price_lower=candidate.price_lower,
            price_upper=candidate.price_upper,
            price_ref=candidate.price_ref,
            side_hint=candidate.side_hint,
            confidence=candidate.confidence,
            evidence_refs=candidate.evidence_refs,
            source_type=candidate.source_type,
            source_message_id=candidate.source_message_id,
            source_prompt_trace_id=candidate.source_prompt_trace_id,
            lifecycle_state=candidate.lifecycle_state,
            invalidation_rule=candidate.invalidation_rule,
            evaluation_window=candidate.evaluation_window,
            metadata=merged_metadata,
            stream_action=action.value,
            created_at=now,
            updated_at=now,
        )

    def _upsert_memory_entry(self, candidate: StoredEventCandidate) -> StoredEventMemoryEntry:
        existing = self._repository.list_event_memory_entries(
            session_id=candidate.session_id,
            event_id=candidate.event_id,
            limit=1,
        )
        current = existing[0] if existing else None
        lifecycle_state = EventCandidateLifecycleState(candidate.lifecycle_state)
        if lifecycle_state in {EventCandidateLifecycleState.MOUNTED, EventCandidateLifecycleState.PROMOTED_PLAN}:
            memory_bucket = EventMemoryBucket.PROJECTED
        elif lifecycle_state == EventCandidateLifecycleState.CONFIRMED:
            memory_bucket = EventMemoryBucket.WATCHLIST
        elif lifecycle_state in self._TERMINAL_STATES:
            memory_bucket = EventMemoryBucket.INACTIVE
        else:
            memory_bucket = EventMemoryBucket.ACTIVE
        now = datetime.now(tz=UTC)
        return self._repository.save_event_memory_entry(
            memory_entry_id=current.memory_entry_id if current is not None else f"emem-{candidate.event_id}",
            event_id=candidate.event_id,
            session_id=candidate.session_id,
            candidate_kind=candidate.candidate_kind,
            title=candidate.title,
            summary=candidate.summary,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            anchor_start_ts=candidate.anchor_start_ts,
            anchor_end_ts=candidate.anchor_end_ts,
            price_lower=candidate.price_lower,
            price_upper=candidate.price_upper,
            price_ref=candidate.price_ref,
            side_hint=candidate.side_hint,
            confidence=candidate.confidence,
            evidence_refs=candidate.evidence_refs,
            source_type=candidate.source_type,
            source_message_id=candidate.source_message_id,
            source_prompt_trace_id=candidate.source_prompt_trace_id,
            lifecycle_state=candidate.lifecycle_state,
            invalidation_rule=candidate.invalidation_rule,
            evaluation_window=candidate.evaluation_window,
            metadata=candidate.metadata,
            memory_bucket=memory_bucket.value,
            created_at=current.created_at if current is not None else candidate.created_at,
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
        current_state = EventCandidateLifecycleState(candidate.lifecycle_state)
        if current_state != target_state and target_state not in self._ALLOWED_TRANSITIONS[current_state]:
            raise ReplayWorkbenchChatError(
                f"Illegal event candidate transition: {current_state.value} -> {target_state.value} for '{candidate.event_id}'."
            )
        updated = self._repository.transition_event_candidate_state(
            candidate.event_id,
            lifecycle_state=target_state.value,
            updated_at=datetime.now(tz=UTC),
            metadata=metadata,
            promoted_projection_type=promoted_projection_type,
            promoted_projection_id=promoted_projection_id,
        )
        if updated is None:  # pragma: no cover
            raise ReplayWorkbenchChatError(f"Event candidate '{candidate.event_id}' disappeared during transition.")
        return updated

    def _ensure_annotation_projection(self, candidate: StoredEventCandidate) -> tuple[StoredEventCandidate, StoredChatAnnotation]:
        compat_annotation_id = str(candidate.metadata.get("compat_annotation_id") or "").strip()
        if candidate.promoted_projection_type == EventPromotionTarget.ANNOTATION.value and candidate.promoted_projection_id:
            return candidate, self._require_annotation(candidate.session_id, candidate.promoted_projection_id)
        if compat_annotation_id and candidate.candidate_kind == EventCandidateKind.PLAN_INTENT.value:
            return candidate, self._require_annotation(candidate.session_id, compat_annotation_id)
        source_message = self._require_source_message(candidate)
        session = self._require_session(candidate.session_id)
        projection = self._annotation_payload_for_candidate(candidate)
        now = datetime.now(tz=UTC)
        annotation = self._repository.save_chat_annotation(
            annotation_id=f"ann-{uuid4().hex}",
            session_id=session.session_id,
            message_id=source_message.message_id,
            plan_id=candidate.promoted_projection_id if candidate.promoted_projection_type == EventPromotionTarget.PLAN_CARD.value else None,
            symbol=session.symbol,
            contract_id=session.contract_id,
            timeframe=session.timeframe,
            annotation_type=projection["annotation_type"],
            subtype=projection.get("subtype"),
            label=projection["label"],
            reason=projection["reason"],
            start_time=projection["start_time"],
            end_time=projection.get("end_time"),
            expires_at=projection.get("expires_at"),
            status=projection["status"],
            priority=projection.get("priority"),
            confidence=projection.get("confidence"),
            visible=projection["visible"],
            pinned=projection["pinned"],
            source_kind=projection["source_kind"],
            payload=projection["payload"],
            created_at=now,
            updated_at=now,
        )
        self._append_message_object_id(source_message, "annotations", annotation.annotation_id)
        if candidate.candidate_kind == EventCandidateKind.PLAN_INTENT.value:
            merged_metadata = dict(candidate.metadata)
            merged_metadata["compat_annotation_id"] = annotation.annotation_id
            merged_metadata.setdefault("compat_annotation_type", projection["annotation_type"])
            updated = self._repository.patch_event_candidate(
                candidate.event_id,
                metadata=merged_metadata,
                updated_at=now,
            )
            if updated is None:  # pragma: no cover
                raise ReplayWorkbenchChatError(f"Event candidate '{candidate.event_id}' disappeared during annotation projection.")
            return updated, annotation
        updated = self._transition_candidate(
            candidate,
            EventCandidateLifecycleState.MOUNTED,
            metadata={"projection_reason": "annotation"},
            promoted_projection_type=EventPromotionTarget.ANNOTATION.value,
            promoted_projection_id=annotation.annotation_id,
        )
        return updated, annotation

    def _promote_to_plan_card(self, candidate: StoredEventCandidate) -> EventMutationEnvelope:
        updated, plan_card = self._ensure_plan_projection(candidate)
        stream_entry = self._append_stream_entry(
            updated,
            EventStreamAction.PROMOTED,
            metadata={"target": EventPromotionTarget.PLAN_CARD.value},
        )
        memory_entry = self._upsert_memory_entry(updated)
        return EventMutationEnvelope(
            session_id=updated.session_id,
            candidate=self._candidate_model(updated),
            stream_entry=self._stream_model(stream_entry),
            memory_entry=self._memory_model(memory_entry),
            projected_plan_card=self._plan_model(plan_card),
        )

    def _ensure_plan_projection(self, candidate: StoredEventCandidate) -> tuple[StoredEventCandidate, StoredChatPlanCard]:
        if candidate.candidate_kind != EventCandidateKind.PLAN_INTENT.value:
            raise ReplayWorkbenchChatError(f"Candidate kind '{candidate.candidate_kind}' cannot be promoted to plan card.")
        if candidate.promoted_projection_type == EventPromotionTarget.PLAN_CARD.value and candidate.promoted_projection_id:
            return candidate, self._require_plan(candidate.session_id, candidate.promoted_projection_id)
        source_message = self._require_source_message(candidate)
        metadata = dict(candidate.metadata)
        entry_price = self._coerce_float(metadata.get("entry_price")) or candidate.price_ref
        stop_price = self._coerce_float(metadata.get("stop_price")) or self._coerce_float(candidate.invalidation_rule.get("stop_price"))
        take_profits = list(metadata.get("take_profits") or []) if isinstance(metadata.get("take_profits"), list) else []
        invalidations = list(metadata.get("invalidations") or []) if isinstance(metadata.get("invalidations"), list) else []
        if stop_price is not None and not invalidations:
            invalidations = [f"{'上破' if candidate.side_hint == 'sell' else '跌破'} {stop_price} 计划失效"]
        side = self._normalize_side(candidate.side_hint) or "buy"
        entry_type = "range" if candidate.price_lower is not None or candidate.price_upper is not None else ("point" if entry_price is not None else None)
        now = datetime.now(tz=UTC)
        plan_card = self._repository.save_chat_plan_card(
            plan_id=f"plan-{uuid4().hex}",
            session_id=candidate.session_id,
            message_id=source_message.message_id,
            title=candidate.title,
            side=side,
            entry_type=entry_type,
            entry_price=entry_price,
            entry_price_low=candidate.price_lower,
            entry_price_high=candidate.price_upper,
            stop_price=stop_price,
            take_profits=take_profits,
            invalidations=invalidations,
            time_validity=str(metadata.get("time_validity")) if metadata.get("time_validity") else None,
            risk_reward=self._coerce_float(metadata.get("risk_reward")),
            confidence=candidate.confidence,
            priority=self._coerce_int(metadata.get("priority")),
            status="active",
            source_kind="event_candidate_projection",
            notes=str(metadata.get("notes") or candidate.summary or "").strip(),
            payload={
                "event_id": candidate.event_id,
                "candidate_kind": candidate.candidate_kind,
                "entry_price": entry_price,
                "entry_price_low": candidate.price_lower,
                "entry_price_high": candidate.price_upper,
                "stop_price": stop_price,
                "take_profits": take_profits,
                "invalidations": invalidations,
                "metadata": metadata,
            },
            created_at=now,
            updated_at=now,
        )
        self._append_message_object_id(source_message, "plan_cards", plan_card.plan_id)
        updated = self._transition_candidate(
            candidate,
            EventCandidateLifecycleState.PROMOTED_PLAN,
            metadata={"projection_reason": "plan_card"},
            promoted_projection_type=EventPromotionTarget.PLAN_CARD.value,
            promoted_projection_id=plan_card.plan_id,
        )
        return updated, plan_card

    def _annotation_payload_for_candidate(self, candidate: StoredEventCandidate) -> dict[str, Any]:
        metadata = dict(candidate.metadata)
        raw_type = str(metadata.get("compat_annotation_type") or "").strip().lower()
        if raw_type:
            annotation_type = raw_type
        elif candidate.candidate_kind == EventCandidateKind.PRICE_ZONE.value:
            annotation_type = self._infer_zone_annotation_type(f"{candidate.title} {candidate.summary}", side_hint=candidate.side_hint)
        elif candidate.candidate_kind == EventCandidateKind.RISK_NOTE.value:
            annotation_type = "no_trade_zone" if candidate.price_lower is not None or candidate.price_upper is not None else "stop_loss"
        elif candidate.candidate_kind == EventCandidateKind.MARKET_EVENT.value:
            annotation_type = "event_marker"
        else:
            annotation_type = "entry_line"
        event_kind = str(
            metadata.get("compat_annotation_event_kind")
            or self._derive_annotation_event_kind(annotation_type, plan_like=candidate.candidate_kind == EventCandidateKind.PLAN_INTENT.value)
        )
        stop_price = self._coerce_float(metadata.get("stop_price")) or self._coerce_float(candidate.invalidation_rule.get("stop_price"))
        target_price = self._coerce_float(metadata.get("target_price"))
        entry_price = self._coerce_float(metadata.get("entry_price")) or candidate.price_ref
        payload = {
            "event_id": candidate.event_id,
            "candidate_kind": candidate.candidate_kind,
            "event_kind": event_kind,
            "side": self._normalize_side(candidate.side_hint),
            "entry_price": entry_price if annotation_type == "entry_line" else metadata.get("entry_price"),
            "stop_price": stop_price if annotation_type == "stop_loss" else metadata.get("stop_price"),
            "target_price": target_price if annotation_type == "take_profit" else metadata.get("target_price"),
            "price_low": candidate.price_lower,
            "price_high": candidate.price_upper,
            "path_points": list(metadata.get("path_points") or []) if isinstance(metadata.get("path_points"), list) else [],
            "projection_source": "event_candidate",
        }
        return {
            "annotation_type": annotation_type,
            "subtype": str(metadata.get("raw_annotation_type") or "").strip() or None,
            "label": candidate.title or self._default_annotation_label(annotation_type),
            "reason": candidate.summary,
            "start_time": candidate.anchor_start_ts or candidate.created_at,
            "end_time": candidate.anchor_end_ts,
            "expires_at": self._coerce_datetime(candidate.evaluation_window.get("expires_at")),
            "status": "active",
            "priority": self._coerce_int(metadata.get("priority")),
            "confidence": candidate.confidence,
            "visible": bool(metadata.get("visible", True)),
            "pinned": bool(metadata.get("pinned", False)),
            "source_kind": "event_candidate_projection",
            "payload": payload,
        }

    def _append_message_object_id(self, message: StoredChatMessage, collection: str, object_id: str) -> None:
        if collection == "annotations":
            existing = list(message.annotations)
            if object_id in existing:
                return
            existing.append(object_id)
            self._repository.update_chat_message(message.message_id, annotations=existing, updated_at=datetime.now(tz=UTC))
            return
        if collection == "plan_cards":
            existing = list(message.plan_cards)
            if object_id in existing:
                return
            existing.append(object_id)
            self._repository.update_chat_message(message.message_id, plan_cards=existing, updated_at=datetime.now(tz=UTC))
            return
        raise ReplayWorkbenchChatError(f"Unsupported message object collection '{collection}'.")

    def _require_session(self, session_id: str) -> StoredChatSession:
        session = self._repository.get_chat_session(session_id)
        if session is None:
            raise ReplayWorkbenchNotFoundError(f"Chat session '{session_id}' not found.")
        return session

    def _require_candidate(self, event_id: str) -> StoredEventCandidate:
        candidate = self._repository.get_event_candidate(event_id)
        if candidate is None:
            raise ReplayWorkbenchNotFoundError(f"Event candidate '{event_id}' not found.")
        return candidate

    def _resolve_source_message(self, session_id: str, source_message_id: str | None) -> StoredChatMessage:
        if source_message_id:
            message = self._repository.get_chat_message(source_message_id)
            if message is None or message.session_id != session_id:
                raise ReplayWorkbenchNotFoundError(f"Chat message '{source_message_id}' not found in session '{session_id}'.")
            if message.role != "assistant":
                raise ReplayWorkbenchChatError(f"Message '{source_message_id}' is not an assistant message and cannot seed event extraction.")
            return message
        messages = self._repository.list_chat_messages(session_id=session_id, limit=500)
        for message in reversed(messages):
            if message.role == "assistant":
                return message
        raise ReplayWorkbenchNotFoundError(f"No assistant message found in session '{session_id}'.")

    def _require_source_message(self, candidate: StoredEventCandidate) -> StoredChatMessage:
        """Resolve a projection source message, falling back to the latest assistant reply."""

        return self._resolve_source_message(candidate.session_id, candidate.source_message_id)

    def _require_annotation(self, session_id: str, annotation_id: str) -> StoredChatAnnotation:
        annotations = self._repository.list_chat_annotations(session_id=session_id, limit=2000)
        for annotation in annotations:
            if annotation.annotation_id == annotation_id:
                return annotation
        raise ReplayWorkbenchNotFoundError(f"Annotation '{annotation_id}' not found in session '{session_id}'.")

    def _require_plan(self, session_id: str, plan_id: str) -> StoredChatPlanCard:
        plans = self._repository.list_chat_plan_cards(session_id=session_id, limit=2000)
        for plan in plans:
            if plan.plan_id == plan_id:
                return plan
        raise ReplayWorkbenchNotFoundError(f"Plan card '{plan_id}' not found in session '{session_id}'.")

    def _candidate_model(self, stored: StoredEventCandidate) -> EventCandidate:
        return EventCandidate(
            event_id=stored.event_id,
            session_id=stored.session_id,
            candidate_kind=stored.candidate_kind,
            title=stored.title,
            summary=stored.summary,
            symbol=stored.symbol,
            timeframe=stored.timeframe,
            anchor_start_ts=stored.anchor_start_ts,
            anchor_end_ts=stored.anchor_end_ts,
            price_lower=stored.price_lower,
            price_upper=stored.price_upper,
            price_ref=stored.price_ref,
            side_hint=stored.side_hint,
            confidence=stored.confidence,
            evidence_refs=stored.evidence_refs,
            source_type=stored.source_type,
            source_message_id=stored.source_message_id,
            source_prompt_trace_id=stored.source_prompt_trace_id,
            lifecycle_state=stored.lifecycle_state,
            invalidation_rule=stored.invalidation_rule,
            evaluation_window=stored.evaluation_window,
            metadata=stored.metadata,
            dedup_key=stored.dedup_key,
            promoted_projection_type=stored.promoted_projection_type,
            promoted_projection_id=stored.promoted_projection_id,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _stream_model(self, stored: StoredEventStreamEntry) -> EventStreamEntry:
        return EventStreamEntry(
            stream_entry_id=stored.stream_entry_id,
            event_id=stored.event_id,
            session_id=stored.session_id,
            candidate_kind=stored.candidate_kind,
            title=stored.title,
            summary=stored.summary,
            symbol=stored.symbol,
            timeframe=stored.timeframe,
            anchor_start_ts=stored.anchor_start_ts,
            anchor_end_ts=stored.anchor_end_ts,
            price_lower=stored.price_lower,
            price_upper=stored.price_upper,
            price_ref=stored.price_ref,
            side_hint=stored.side_hint,
            confidence=stored.confidence,
            evidence_refs=stored.evidence_refs,
            source_type=stored.source_type,
            source_message_id=stored.source_message_id,
            source_prompt_trace_id=stored.source_prompt_trace_id,
            lifecycle_state=stored.lifecycle_state,
            invalidation_rule=stored.invalidation_rule,
            evaluation_window=stored.evaluation_window,
            metadata=stored.metadata,
            stream_action=stored.stream_action,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _memory_model(self, stored: StoredEventMemoryEntry) -> EventMemoryEntry:
        return EventMemoryEntry(
            memory_entry_id=stored.memory_entry_id,
            event_id=stored.event_id,
            session_id=stored.session_id,
            candidate_kind=stored.candidate_kind,
            title=stored.title,
            summary=stored.summary,
            symbol=stored.symbol,
            timeframe=stored.timeframe,
            anchor_start_ts=stored.anchor_start_ts,
            anchor_end_ts=stored.anchor_end_ts,
            price_lower=stored.price_lower,
            price_upper=stored.price_upper,
            price_ref=stored.price_ref,
            side_hint=stored.side_hint,
            confidence=stored.confidence,
            evidence_refs=stored.evidence_refs,
            source_type=stored.source_type,
            source_message_id=stored.source_message_id,
            source_prompt_trace_id=stored.source_prompt_trace_id,
            lifecycle_state=stored.lifecycle_state,
            invalidation_rule=stored.invalidation_rule,
            evaluation_window=stored.evaluation_window,
            metadata=stored.metadata,
            memory_bucket=stored.memory_bucket,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
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
            event_kind=str(payload.get("event_kind") or self._derive_annotation_event_kind(stored.annotation_type, plan_like=bool(stored.plan_id))),
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

    def _plan_model(self, stored: StoredChatPlanCard) -> ChatPlanCard:
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
