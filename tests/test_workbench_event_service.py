from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.models import (
    CreateEventCandidateRequest,
    EventCandidateKind,
    EventCandidatePatchRequest,
    EventLifecycleAction,
    EventPromotionTarget,
    EventStreamExtractRequest,
    PromoteEventCandidateRequest,
    ReplayAiChatContent,
)
from atas_market_structure.models._replay import ReplayAiChatAnnotationCandidate, ReplayAiChatPlanCandidate
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_common import ReplayWorkbenchChatError
from atas_market_structure.workbench_event_service import ReplayWorkbenchEventService
from tests.test_chat_backend_support import TEST_DB_DIR


def _make_repository() -> SQLiteAnalysisRepository:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return repository


def _seed_session(repository: SQLiteAnalysisRepository) -> tuple[str, str]:
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    session_id = f"sess-{uuid4().hex}"
    message_id = f"msg-{uuid4().hex}"
    repository.save_chat_session(
        session_id=session_id,
        workspace_id="replay_main",
        title="事件骨架测试",
        symbol="NQ",
        contract_id="NQM2026",
        timeframe="1m",
        window_range={"start": "2026-03-25T09:30:00Z", "end": "2026-03-25T10:30:00Z"},
        active_model="test-model",
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
    repository.save_chat_message(
        message_id=message_id,
        session_id=session_id,
        parent_message_id=None,
        role="assistant",
        content="关注 21524 关键位，21524-21528 为支撑区，跌破 21518 失效，当前更像延续结构。",
        status="completed",
        reply_title=None,
        stream_buffer="",
        model="test-model",
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
    return session_id, message_id


def test_event_service_extracts_candidates_and_persists_stream_memory() -> None:
    repository = _make_repository()
    session_id, message_id = _seed_session(repository)
    service = ReplayWorkbenchEventService(repository=repository)

    envelope = service.extract_event_stream(
        EventStreamExtractRequest(session_id=session_id, source_message_id=message_id)
    )

    assert envelope.schema_version == "workbench_event_stream_envelope_v1"
    candidate_kinds = {item.candidate_kind for item in envelope.candidates}
    assert {
        EventCandidateKind.KEY_LEVEL,
        EventCandidateKind.PRICE_ZONE,
        EventCandidateKind.RISK_NOTE,
        EventCandidateKind.MARKET_EVENT,
    }.issubset(candidate_kinds)
    assert len(envelope.items) == len(envelope.candidates)
    assert len(envelope.memory_entries) == len(envelope.candidates)

    stored_candidates = repository.list_event_candidates_by_session(session_id=session_id)
    assert len(stored_candidates) == len(envelope.candidates)
    for candidate in stored_candidates:
        assert repository.get_event_candidate(candidate.event_id) is not None


def test_event_service_creates_manual_candidate_and_persists_stream_memory() -> None:
    repository = _make_repository()
    session_id, _message_id = _seed_session(repository)
    service = ReplayWorkbenchEventService(repository=repository)

    mutation = service.create_event_candidate(
        CreateEventCandidateRequest(
            session_id=session_id,
            candidate_kind=EventCandidateKind.KEY_LEVEL,
            title="手工关键位",
            summary="交易员手工标记的关键价位。",
            price_ref=21524.0,
            metadata={"tool": "manual_key_level"},
        )
    )

    assert mutation.candidate.title == "手工关键位"
    assert mutation.candidate.source_type.value == "manual"
    assert mutation.candidate.source_message_id is not None
    assert mutation.stream_entry is not None
    assert mutation.stream_entry.stream_action.value == "created"
    assert mutation.memory_entry is not None
    stored = repository.get_event_candidate(mutation.candidate.event_id)
    assert stored is not None
    assert stored.metadata["tool"] == "manual_key_level"


def test_manual_candidate_can_mount_without_explicit_source_message_id() -> None:
    repository = _make_repository()
    session_id, _message_id = _seed_session(repository)
    service = ReplayWorkbenchEventService(repository=repository)

    mutation = service.create_event_candidate(
        CreateEventCandidateRequest(
            session_id=session_id,
            candidate_kind=EventCandidateKind.PRICE_ZONE,
            title="手工支撑区",
            summary="交易员手工框选的价格区域。",
            price_lower=21524.0,
            price_upper=21528.0,
            metadata={"tool": "manual_price_zone"},
        )
    )

    assert mutation.candidate.source_message_id is not None
    mounted = service.mount_event_candidate(mutation.candidate.event_id)
    assert mounted.candidate.lifecycle_state.value == "mounted"
    assert mounted.projected_annotation is not None
    assert mounted.projected_annotation.type in {"support_zone", "resistance_zone", "zone"}


def test_event_service_state_transitions_and_projections_are_validated() -> None:
    repository = _make_repository()
    session_id, message_id = _seed_session(repository)
    repository.update_chat_message(
        message_id,
        content="计划：做多，入场 21524，止损 21518，TP1 21530，TP2 21536。",
        response_payload={
            "plan_cards": [
                ReplayAiChatPlanCandidate(
                    title="回踩做多计划",
                    side="buy",
                    entry_price=21524.0,
                    stop_price=21518.0,
                    take_profits=[{"price": 21530.0, "label": "TP1"}],
                    invalidations=["跌破 21518 失效"],
                ).model_dump(mode="json")
            ]
        },
        updated_at=datetime(2026, 3, 25, 9, 31, tzinfo=UTC),
    )
    service = ReplayWorkbenchEventService(repository=repository)

    envelope = service.extract_event_stream(
        EventStreamExtractRequest(session_id=session_id, source_message_id=message_id)
    )
    candidates_by_kind = {}
    for candidate in envelope.candidates:
        candidates_by_kind.setdefault(candidate.candidate_kind.value, candidate)

    key_level = candidates_by_kind["key_level"]
    risk_note = candidates_by_kind["risk_note"]
    plan_intent = candidates_by_kind["plan_intent"]

    confirmed = service.patch_event_candidate(
        key_level.event_id,
        EventCandidatePatchRequest(lifecycle_action=EventLifecycleAction.CONFIRM),
    )
    assert confirmed.candidate.lifecycle_state.value == "confirmed"

    mounted = service.mount_event_candidate(key_level.event_id)
    assert mounted.candidate.lifecycle_state.value == "mounted"
    assert mounted.projected_annotation is not None

    promoted = service.promote_event_candidate(
        plan_intent.event_id,
        PromoteEventCandidateRequest(target=EventPromotionTarget.PLAN_CARD),
    )
    assert promoted.candidate.lifecycle_state.value == "promoted_plan"
    assert promoted.projected_plan_card is not None

    ignored = service.ignore_event_candidate(risk_note.event_id)
    assert ignored.candidate.lifecycle_state.value == "ignored"

    with pytest.raises(ReplayWorkbenchChatError):
        service.mount_event_candidate(risk_note.event_id)


def test_process_reply_event_backbone_preserves_annotation_compatibility() -> None:
    repository = _make_repository()
    session_id, message_id = _seed_session(repository)
    service = ReplayWorkbenchEventService(repository=repository)
    session = repository.get_chat_session(session_id)
    assert session is not None

    content = ReplayAiChatContent(
        reply_text="结构化事件抽取测试",
        annotations=[
            ReplayAiChatAnnotationCandidate(
                type="plan",
                label="结构化计划",
                reason="若回踩 21524 并守住，可考虑做多。",
                entry_price=21524.0,
                side="buy",
            ),
            ReplayAiChatAnnotationCandidate(
                type="price_zone",
                label="结构化支撑区",
                reason="21524-21528 是本轮回踩防守区。",
                price_low=21524.0,
                price_high=21528.0,
                side="buy",
            ),
            ReplayAiChatAnnotationCandidate(
                type="risk_note",
                label="结构化风险位",
                reason="跌破 21518 则本轮回踩脚本失效。",
                stop_price=21518.0,
            ),
        ],
    )

    result = service.process_reply_event_backbone(
        session=session,
        source_message_id=message_id,
        replay_response=content,
    )

    annotations_by_label = {item.label: item for item in result.annotations}
    assert annotations_by_label["结构化计划"].annotation_type == "entry_line"
    assert annotations_by_label["结构化支撑区"].annotation_type == "support_zone"
    assert annotations_by_label["结构化风险位"].annotation_type == "stop_loss"
    assert any(item.title == "结构化计划" for item in result.plan_cards)
