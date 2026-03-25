from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.models import ChartCandle, EventOutcomeQuery, EventOutcomeResult
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_event_outcome_service import ReplayWorkbenchEventOutcomeService
from tests.test_chat_backend_support import TEST_DB_DIR


def _make_repository() -> SQLiteAnalysisRepository:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return repository


def _seed_session(repository: SQLiteAnalysisRepository) -> tuple[str, str, str]:
    now = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    session_id = f"sess-{uuid4().hex}"
    message_id = f"msg-{uuid4().hex}"
    prompt_trace_id = f"trace-{uuid4().hex}"
    repository.save_chat_session(
        session_id=session_id,
        workspace_id="replay_main",
        title="Outcome Ledger 测试",
        symbol="NQ",
        contract_id="NQM2024",
        timeframe="1m",
        window_range={"start": "2024-03-25T09:30:00Z", "end": "2024-03-25T10:30:00Z"},
        active_model="gpt-test",
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
        prompt_trace_id=prompt_trace_id,
        role="assistant",
        content="计划：回踩做多。",
        status="completed",
        reply_title=None,
        stream_buffer="",
        model="gpt-test",
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
    repository.save_prompt_trace(
        prompt_trace_id=prompt_trace_id,
        session_id=session_id,
        message_id=message_id,
        symbol="NQ",
        timeframe="1m",
        analysis_type="structure",
        analysis_range="current_window",
        analysis_style="standard",
        selected_block_ids=[],
        pinned_block_ids=[],
        attached_event_ids=[],
        prompt_block_summaries=[],
        bar_window_summary={},
        manual_selection_summary={},
        memory_summary={},
        final_system_prompt="system",
        final_user_prompt="user",
        model_name="gpt-test",
        model_input_hash="hash-test",
        snapshot={"preset": "recent_20_bars"},
        metadata={"preset": "recent_20_bars", "resolved_model_name": "gpt-test"},
        created_at=now,
        updated_at=now,
    )
    return session_id, message_id, prompt_trace_id


def _seed_candidate(
    repository: SQLiteAnalysisRepository,
    *,
    session_id: str,
    message_id: str,
    prompt_trace_id: str,
    event_id: str,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    repository.save_event_candidate(
        event_id=event_id,
        session_id=session_id,
        candidate_kind="plan_intent",
        title="回踩做多计划",
        summary="回踩 21524 做多，跌破 21518 失效，目标 21530。",
        symbol="NQ",
        timeframe="1m",
        anchor_start_ts=created_at,
        anchor_end_ts=None,
        price_lower=None,
        price_upper=None,
        price_ref=21524.0,
        side_hint="buy",
        confidence=0.8,
        evidence_refs=[],
        source_type="ai_reply_structured",
        source_message_id=message_id,
        source_prompt_trace_id=prompt_trace_id,
        lifecycle_state="candidate",
        invalidation_rule={"stop_price": 21518.0},
        evaluation_window={"expires_at": expires_at.isoformat()},
        metadata={
            "entry_price": 21524.0,
            "stop_price": 21518.0,
            "take_profits": [{"price": 21530.0, "label": "TP1"}],
        },
        dedup_key=None,
        promoted_projection_type=None,
        promoted_projection_id=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _seed_candles(repository: SQLiteAnalysisRepository, candles: list[tuple[datetime, float, float, float, float]]) -> None:
    repository.upsert_chart_candles(
        [
            ChartCandle(
                symbol="NQ",
                timeframe="1m",
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=1),
                source_started_at=started_at,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=100,
                tick_volume=10,
                delta=5,
                updated_at=started_at + timedelta(minutes=1),
            )
            for started_at, open_price, high_price, low_price, close_price in candles
        ]
    )


def test_event_outcome_service_settles_plan_success_and_persists_ledger() -> None:
    repository = _make_repository()
    session_id, message_id, prompt_trace_id = _seed_session(repository)
    created_at = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    _seed_candidate(
        repository,
        session_id=session_id,
        message_id=message_id,
        prompt_trace_id=prompt_trace_id,
        event_id="evt-success",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=4),
    )
    _seed_candles(
        repository,
        [
            (created_at, 21524.0, 21526.0, 21523.0, 21525.0),
            (created_at + timedelta(minutes=1), 21525.0, 21531.0, 21524.0, 21530.0),
        ],
    )

    service = ReplayWorkbenchEventOutcomeService(repository=repository)
    envelope = service.list_event_outcomes(EventOutcomeQuery(session_id=session_id))

    outcome = envelope.outcomes[0]
    assert outcome.realized_outcome == EventOutcomeResult.SUCCESS
    assert outcome.outcome_label == "success"
    assert outcome.analysis_preset == "recent_20_bars"
    assert outcome.model_name == "gpt-test"
    assert repository.get_event_outcome_by_event("evt-success") is not None


def test_event_outcome_service_settles_failure_when_stop_hits_first() -> None:
    repository = _make_repository()
    session_id, message_id, prompt_trace_id = _seed_session(repository)
    created_at = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    _seed_candidate(
        repository,
        session_id=session_id,
        message_id=message_id,
        prompt_trace_id=prompt_trace_id,
        event_id="evt-failure",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=4),
    )
    _seed_candles(
        repository,
        [
            (created_at, 21524.0, 21525.0, 21517.0, 21518.0),
            (created_at + timedelta(minutes=1), 21518.0, 21531.0, 21517.5, 21530.0),
        ],
    )

    service = ReplayWorkbenchEventOutcomeService(repository=repository)
    envelope = service.list_event_outcomes(EventOutcomeQuery(session_id=session_id))

    assert envelope.outcomes[0].realized_outcome == EventOutcomeResult.FAILURE
    assert envelope.outcomes[0].hit_stop is True


def test_event_outcome_service_settles_timeout_when_window_expires_without_resolution() -> None:
    repository = _make_repository()
    session_id, message_id, prompt_trace_id = _seed_session(repository)
    created_at = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    _seed_candidate(
        repository,
        session_id=session_id,
        message_id=message_id,
        prompt_trace_id=prompt_trace_id,
        event_id="evt-timeout",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=3),
    )
    _seed_candles(
        repository,
        [
            (created_at, 21524.0, 21527.0, 21522.0, 21526.0),
            (created_at + timedelta(minutes=1), 21526.0, 21527.5, 21522.5, 21525.5),
            (created_at + timedelta(minutes=2), 21525.5, 21527.0, 21522.0, 21524.5),
        ],
    )

    service = ReplayWorkbenchEventOutcomeService(repository=repository)
    envelope = service.list_event_outcomes(EventOutcomeQuery(session_id=session_id))

    assert envelope.outcomes[0].realized_outcome == EventOutcomeResult.TIMEOUT
    assert envelope.outcomes[0].timed_out is True


def test_event_outcome_service_marks_same_bar_target_and_stop_as_inconclusive() -> None:
    repository = _make_repository()
    session_id, message_id, prompt_trace_id = _seed_session(repository)
    created_at = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    _seed_candidate(
        repository,
        session_id=session_id,
        message_id=message_id,
        prompt_trace_id=prompt_trace_id,
        event_id="evt-inconclusive",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=2),
    )
    _seed_candles(
        repository,
        [
            (created_at, 21524.0, 21531.0, 21517.0, 21524.0),
        ],
    )

    service = ReplayWorkbenchEventOutcomeService(repository=repository)
    envelope = service.list_event_outcomes(EventOutcomeQuery(session_id=session_id))

    assert envelope.outcomes[0].realized_outcome == EventOutcomeResult.INCONCLUSIVE
    assert envelope.outcomes[0].inconclusive is True
