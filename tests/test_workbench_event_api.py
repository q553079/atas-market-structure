from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ChartCandle
from atas_market_structure.repository import SQLiteAnalysisRepository
from tests.test_chat_backend_support import TEST_DB_DIR


def _build_app() -> tuple[MarketStructureApplication, SQLiteAnalysisRepository, str, str]:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    session_id = f"sess-{uuid4().hex}"
    message_id = f"msg-{uuid4().hex}"
    repository.save_chat_session(
        session_id=session_id,
        workspace_id="replay_main",
        title="事件 API 测试",
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
        content="关注 21524，21524-21528 为支撑区，跌破 21518 失效，当前偏延续。",
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
        response_payload={
            "plan_cards": [
                {
                    "title": "回踩做多计划",
                    "side": "buy",
                    "entry_price": 21524.0,
                    "stop_price": 21518.0,
                    "take_profits": [{"price": 21530.0, "label": "TP1"}],
                    "invalidations": ["跌破 21518 失效"],
                }
            ],
            "annotations": [
                {
                    "type": "key_level",
                    "label": "关键价位",
                    "reason": "关注 21524 的回踩确认。",
                    "entry_price": 21524.0,
                    "side": "buy",
                },
                {
                    "type": "price_zone",
                    "label": "结构化支撑区",
                    "reason": "21524-21528 为防守区。",
                    "price_low": 21524.0,
                    "price_high": 21528.0,
                    "side": "buy",
                },
                {
                    "type": "risk_note",
                    "label": "结构化风险位",
                    "reason": "跌破 21518 脚本失效。",
                    "stop_price": 21518.0,
                },
                {
                    "type": "market_event",
                    "label": "延续结构",
                    "reason": "当前更像延续而不是反转。",
                },
            ],
        },
        created_at=now,
        updated_at=now,
    )
    return MarketStructureApplication(repository=repository), repository, session_id, message_id


def test_event_stream_routes_support_extract_mutation_and_filters() -> None:
    application, _repository, session_id, message_id = _build_app()

    extract_response = application.dispatch(
        "POST",
        "/api/v1/workbench/event-stream/extract",
        json.dumps({"session_id": session_id, "source_message_id": message_id}).encode("utf-8"),
    )
    assert extract_response.status_code == 200
    extract_payload = json.loads(extract_response.body)
    assert extract_payload["schema_version"] == "workbench_event_stream_envelope_v1"
    assert len(extract_payload["candidates"]) >= 4

    candidates_by_kind = {item["candidate_kind"]: item for item in extract_payload["candidates"]}
    key_level = candidates_by_kind["key_level"]
    price_zone = candidates_by_kind["price_zone"]
    risk_note = candidates_by_kind["risk_note"]
    plan_intent = candidates_by_kind["plan_intent"]

    patch_response = application.dispatch(
        "PATCH",
        f"/api/v1/workbench/event-candidates/{price_zone['event_id']}",
        json.dumps({"title": "更新后的支撑区", "lifecycle_action": "confirm"}).encode("utf-8"),
    )
    assert patch_response.status_code == 200
    patch_payload = json.loads(patch_response.body)
    assert patch_payload["schema_version"] == "workbench_event_mutation_envelope_v1"
    assert patch_payload["candidate"]["title"] == "更新后的支撑区"
    assert patch_payload["candidate"]["lifecycle_state"] == "confirmed"

    mount_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/event-candidates/{key_level['event_id']}/mount",
        b"{}",
    )
    assert mount_response.status_code == 200
    mount_payload = json.loads(mount_response.body)
    assert mount_payload["candidate"]["lifecycle_state"] == "mounted"
    assert mount_payload["projected_annotation"]["type"] == "entry_line"

    promote_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/event-candidates/{plan_intent['event_id']}/promote",
        json.dumps({"target": "plan_card"}).encode("utf-8"),
    )
    assert promote_response.status_code == 200
    promote_payload = json.loads(promote_response.body)
    assert promote_payload["candidate"]["lifecycle_state"] == "promoted_plan"
    assert promote_payload["projected_plan_card"]["title"] == "回踩做多计划"

    ignore_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/event-candidates/{risk_note['event_id']}/ignore",
        b"{}",
    )
    assert ignore_response.status_code == 200
    ignore_payload = json.loads(ignore_response.body)
    assert ignore_payload["candidate"]["lifecycle_state"] == "ignored"

    list_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stream?session_id={session_id}&symbol=NQ&timeframe=1m&source_message_id={message_id}",
    )
    assert list_response.status_code == 200
    list_payload = json.loads(list_response.body)
    assert list_payload["schema_version"] == "workbench_event_stream_envelope_v1"
    assert {item["stream_action"] for item in list_payload["items"]} >= {"extracted", "promoted", "state_transition"}
    assert all(item["symbol"] == "NQ" for item in list_payload["candidates"])


def test_event_candidate_create_route_supports_manual_candidates() -> None:
    application, _repository, session_id, _message_id = _build_app()

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/event-candidates",
        json.dumps(
            {
                "session_id": session_id,
                "candidate_kind": "price_zone",
                "title": "手工区域",
                "summary": "人工框选的价格区域。",
                "price_lower": 21524.0,
                "price_upper": 21528.0,
                "metadata": {"tool": "manual_zone"},
            }
        ).encode("utf-8"),
    )

    assert create_response.status_code == 200
    create_payload = json.loads(create_response.body)
    assert create_payload["schema_version"] == "workbench_event_mutation_envelope_v1"
    assert create_payload["candidate"]["source_type"] == "manual"
    assert create_payload["candidate"]["candidate_kind"] == "price_zone"
    assert create_payload["candidate"]["source_message_id"] is not None
    assert create_payload["stream_entry"]["stream_action"] == "created"
    assert create_payload["memory_entry"]["memory_bucket"] == "active"


def test_manual_candidate_mount_route_falls_back_to_latest_assistant_message() -> None:
    application, _repository, session_id, _message_id = _build_app()

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/event-candidates",
        json.dumps(
            {
                "session_id": session_id,
                "candidate_kind": "key_level",
                "title": "手工关键位",
                "summary": "人工创建的关键价位。",
                "price_ref": 21524.0,
                "metadata": {"tool": "manual_key_level"},
            }
        ).encode("utf-8"),
    )
    assert create_response.status_code == 200
    create_payload = json.loads(create_response.body)
    event_id = create_payload["candidate"]["event_id"]
    assert create_payload["candidate"]["source_message_id"] is not None

    mount_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/event-candidates/{event_id}/mount",
        b"{}",
    )
    assert mount_response.status_code == 200
    mount_payload = json.loads(mount_response.body)
    assert mount_payload["candidate"]["lifecycle_state"] == "mounted"
    assert mount_payload["projected_annotation"]["type"] == "entry_line"


def test_event_outcome_routes_return_ledger_and_stats_breakdowns() -> None:
    application, repository, session_id, message_id = _build_app()
    created_at = datetime(2024, 3, 25, 9, 30, tzinfo=UTC)
    prompt_trace_id = f"trace-{uuid4().hex}"
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
        created_at=created_at,
        updated_at=created_at,
    )
    repository.save_event_candidate(
        event_id="evt-outcome-success",
        session_id=session_id,
        candidate_kind="plan_intent",
        title="回踩做多计划",
        summary="回踩 21524 做多，目标 21530。",
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
        evaluation_window={"expires_at": (created_at + timedelta(minutes=3)).isoformat()},
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
    repository.upsert_chart_candles(
        [
            ChartCandle(
                symbol="NQ",
                timeframe="1m",
                started_at=created_at,
                ended_at=created_at + timedelta(minutes=1),
                source_started_at=created_at,
                open=21524.0,
                high=21526.0,
                low=21523.0,
                close=21525.0,
                volume=100,
                tick_volume=10,
                delta=5,
                updated_at=created_at + timedelta(minutes=1),
            ),
            ChartCandle(
                symbol="NQ",
                timeframe="1m",
                started_at=created_at + timedelta(minutes=1),
                ended_at=created_at + timedelta(minutes=2),
                source_started_at=created_at + timedelta(minutes=1),
                open=21525.0,
                high=21531.0,
                low=21524.0,
                close=21530.0,
                volume=120,
                tick_volume=12,
                delta=8,
                updated_at=created_at + timedelta(minutes=2),
            ),
        ]
    )

    outcomes_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-outcomes?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert outcomes_response.status_code == 200
    outcomes_payload = json.loads(outcomes_response.body)
    assert outcomes_payload["schema_version"] == "workbench_event_outcome_list_envelope_v1"
    assert outcomes_payload["outcomes"][0]["realized_outcome"] == "success"
    assert outcomes_payload["outcomes"][0]["analysis_preset"] == "recent_20_bars"

    summary_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stats/summary?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert summary_response.status_code == 200
    summary_payload = json.loads(summary_response.body)
    assert summary_payload["schema_version"] == "workbench_event_stats_summary_envelope_v1"
    assert summary_payload["summary"]["success_count"] >= 1

    by_kind_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stats/by-kind?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert by_kind_response.status_code == 200
    by_kind_payload = json.loads(by_kind_response.body)
    assert by_kind_payload["schema_version"] == "workbench_event_stats_breakdown_envelope_v1"
    assert by_kind_payload["dimension"] == "event_kind"
    assert any(bucket["bucket_key"] == "plan_intent" for bucket in by_kind_payload["buckets"])

    by_time_window_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stats/by-time-window?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert by_time_window_response.status_code == 200
    assert json.loads(by_time_window_response.body)["dimension"] == "time_window"

    by_preset_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stats/by-analysis-preset?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert by_preset_response.status_code == 200
    assert any(bucket["bucket_key"] == "recent_20_bars" for bucket in json.loads(by_preset_response.body)["buckets"])

    by_model_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/event-stats/by-model?session_id={session_id}&symbol=NQ&timeframe=1m",
    )
    assert by_model_response.status_code == 200
    assert any(bucket["bucket_key"] == "gpt-test" for bucket in json.loads(by_model_response.body)["buckets"])
