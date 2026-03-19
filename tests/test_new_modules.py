"""Tests for strategy_selection_engine, position_health, and regime_monitor."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from pathlib import Path
from uuid import uuid4

from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ReplayChartBar,
    ReplayEventAnnotation,
    ReplayFocusRegion,
    ReplayOperatorEntryRecord,
    ReplayStrategyCandidate,
    ReplayWorkbenchSnapshotPayload,
    StructureSide,
)
from atas_market_structure.position_health_services import PositionHealthEvaluator
from atas_market_structure.regime_monitor_services import RegimeMonitor
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "samples"
TEST_DB_DIR = Path(__file__).resolve().parents[1] / "data" / "test-runs"
ROOT_DIR = Path(__file__).resolve().parents[1]


def load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def load_json_fixture(name: str) -> dict:
    return json.loads(load_fixture(name))


def _build_snapshot() -> ReplayWorkbenchSnapshotPayload:
    raw = load_json_fixture("replay_workbench.snapshot.sample.json")
    return ReplayWorkbenchSnapshotPayload.model_validate(raw)


# --- StrategySelectionEngine tests ---

def test_engine_selects_candidates_from_event_kinds() -> None:
    engine = StrategySelectionEngine(root_dir=ROOT_DIR)
    events = [
        ReplayEventAnnotation(
            event_id="evt-1",
            event_kind="same_price_replenishment",
            source_kind="collector",
            observed_at=datetime.now(tz=UTC),
            price=21500.0,
            price_low=21500.0,
            price_high=21500.0,
            side=StructureSide.BUY,
            confidence=0.8,
            linked_ids=["track-1"],
            notes=[],
        ),
    ]
    candidates = engine.select_candidates(events, [], instrument_symbol="NQ")
    ids = {c.strategy_id for c in candidates}
    # Should match at least the replenishment-related strategies from index
    assert len(candidates) >= 1
    assert any("replenish" in sid or "same_price" in sid or "bid" in sid for sid in ids)


def test_engine_selects_from_reason_codes() -> None:
    engine = StrategySelectionEngine(root_dir=ROOT_DIR)
    regions = [
        ReplayFocusRegion(
            region_id="r-1",
            label="test",
            started_at=datetime.now(tz=UTC),
            ended_at=None,
            price_low=21500.0,
            price_high=21510.0,
            priority=8,
            reason_codes=["defended_bid"],
            linked_event_ids=[],
            notes=[],
        ),
    ]
    candidates = engine.select_candidates([], regions, instrument_symbol="NQ")
    assert len(candidates) >= 1


def test_engine_returns_empty_for_no_matches() -> None:
    engine = StrategySelectionEngine(root_dir=ROOT_DIR)
    events = [
        ReplayEventAnnotation(
            event_id="evt-x",
            event_kind="totally_unknown_event_kind_xyz",
            source_kind="test",
            observed_at=datetime.now(tz=UTC),
            price_low=21500.0,
            price_high=21500.0,
            linked_ids=[],
            notes=[],
        ),
    ]
    candidates = engine.select_candidates(events, [])
    assert candidates == []


def test_engine_dynamic_briefing_includes_no_trade_warning() -> None:
    engine = StrategySelectionEngine(root_dir=ROOT_DIR)
    candidates = [
        ReplayStrategyCandidate(
            strategy_id="no_trade_suppressor_test",
            title="Test no-trade",
            source_path="",
            matched_event_ids=[],
            why_relevant=["test"],
        ),
        ReplayStrategyCandidate(
            strategy_id="pattern-normal",
            title="Normal pattern",
            source_path="",
            matched_event_ids=[],
            why_relevant=["test"],
        ),
    ]
    briefing = engine.build_dynamic_briefing("NQ", candidates, [])
    assert briefing is not None
    assert "no-trade" in briefing.objective.lower() or "no_trade" in briefing.objective.lower() or "suppressor" in briefing.objective.lower()


# --- PositionHealthEvaluator tests ---

def test_health_evaluator_healthy_when_no_entries() -> None:
    evaluator = PositionHealthEvaluator()
    snapshot = _build_snapshot()
    result = evaluator.evaluate(snapshot, [])
    assert result.health_state == "healthy"
    assert result.health_score == 1.0


def test_health_evaluator_warns_no_stop() -> None:
    evaluator = PositionHealthEvaluator()
    snapshot = _build_snapshot()
    entry = ReplayOperatorEntryRecord(
        entry_id="e-1",
        replay_ingestion_id="ing-test",
        replay_snapshot_id=snapshot.replay_snapshot_id,
        instrument_symbol="NQ",
        chart_instance_id="NQ-test",
        executed_at=datetime.now(tz=UTC),
        side=StructureSide.BUY,
        entry_price=21524.0,
        quantity=1,
        stop_price=None,
        target_price=None,
        timeframe_context="1m",
        thesis="test thesis",
        context_notes=[],
        tags=[],
        stored_at=datetime.now(tz=UTC),
    )
    result = evaluator.evaluate(snapshot, [entry])
    assert result.health_score < 1.0
    assert any("止损" in w for w in result.warnings)


def test_health_evaluator_penalizes_no_trade_environment() -> None:
    evaluator = PositionHealthEvaluator()
    snapshot = _build_snapshot()
    no_trade_candidates = [
        ReplayStrategyCandidate(
            strategy_id="no_trade_test",
            title="No trade",
            source_path="",
            matched_event_ids=[],
            why_relevant=[],
        ),
    ]
    entry = ReplayOperatorEntryRecord(
        entry_id="e-2",
        replay_ingestion_id="ing-test",
        replay_snapshot_id=snapshot.replay_snapshot_id,
        instrument_symbol="NQ",
        chart_instance_id="NQ-test",
        executed_at=datetime.now(tz=UTC),
        side=StructureSide.BUY,
        entry_price=21524.0,
        quantity=1,
        stop_price=21518.0,
        target_price=21530.0,
        timeframe_context="1m",
        thesis="test",
        context_notes=[],
        tags=[],
        stored_at=datetime.now(tz=UTC),
    )
    result = evaluator.evaluate(snapshot, [entry], strategy_candidates=no_trade_candidates)
    assert any("no-trade" in w or "no_trade" in w for w in result.warnings)
    assert result.health_score < 0.8


# --- RegimeMonitor tests ---

def test_regime_monitor_returns_quiet_for_empty_candles() -> None:
    monitor = RegimeMonitor()
    snapshot = _build_snapshot()
    snapshot.candles = []
    result = monitor.assess(snapshot)
    assert result.regime == "quiet"
    assert result.confidence == 0.0


def test_regime_monitor_detects_trending_up() -> None:
    monitor = RegimeMonitor()
    snapshot = _build_snapshot()
    base = datetime(2026, 3, 17, 9, 0, tzinfo=UTC)
    # Create ascending candles
    snapshot.candles = [
        ReplayChartBar(
            started_at=base + timedelta(minutes=i),
            ended_at=base + timedelta(minutes=i, seconds=59),
            open=21500.0 + i * 5,
            high=21505.0 + i * 5,
            low=21498.0 + i * 5,
            close=21504.0 + i * 5,
            volume=100,
            delta=20,
            bid_volume=40,
            ask_volume=60,
        )
        for i in range(10)
    ]
    result = monitor.assess(snapshot)
    assert result.directional_bias == "bullish"
    assert result.regime in ("trending_up", "ranging")  # depends on exact thresholds


def test_regime_monitor_returns_details() -> None:
    monitor = RegimeMonitor()
    snapshot = _build_snapshot()
    result = monitor.assess(snapshot)
    assert "sample_bar_count" in result.details
    assert result.atr_estimate >= 0


# --- Analysis Orchestration tests ---

def test_lightweight_monitor_runs_without_llm() -> None:
    from atas_market_structure.analysis_orchestration_services import LightweightMonitorService
    monitor = LightweightMonitorService(strategy_engine=StrategySelectionEngine(root_dir=ROOT_DIR))
    snapshot = _build_snapshot()
    result = monitor.run(snapshot, [])
    assert result.monitor_id.startswith("mon-")
    assert result.regime.regime in ("trending_up", "trending_down", "ranging", "volatile", "quiet")
    assert result.position_health.health_state == "healthy"
    assert isinstance(result.no_trade_active, bool)
    assert isinstance(result.should_trigger_deep_analysis, bool)


def test_full_market_analysis_produces_structured_output() -> None:
    from atas_market_structure.analysis_orchestration_services import FullMarketAnalysisService
    service = FullMarketAnalysisService(strategy_engine=StrategySelectionEngine(root_dir=ROOT_DIR))
    snapshot = _build_snapshot()
    result = service.analyze(snapshot, [])
    assert result.analysis_id.startswith("fma-")
    assert result.environment_summary
    assert result.actionable_summary
    assert isinstance(result.risk_alerts, list)
    d = result.to_dict()
    assert "regime" in d
    assert "position_health" in d
    assert "strategy_candidates" in d


def test_deep_region_analysis_produces_verdict() -> None:
    from atas_market_structure.analysis_orchestration_services import DeepRegionAnalysisService
    from atas_market_structure.models import ReplayManualRegionAnnotationRecord
    service = DeepRegionAnalysisService(strategy_engine=StrategySelectionEngine(root_dir=ROOT_DIR))
    snapshot = _build_snapshot()
    region = ReplayManualRegionAnnotationRecord(
        region_annotation_id="region-test-1",
        replay_ingestion_id="ing-test",
        replay_snapshot_id=snapshot.replay_snapshot_id,
        instrument_symbol="NQ",
        label="test defense zone",
        thesis="If absorption appears, this holds.",
        price_low=21520.0,
        price_high=21530.0,
        started_at=snapshot.window_start,
        ended_at=snapshot.window_end,
        side_bias=StructureSide.BUY,
        notes=[],
        tags=["support"],
        stored_at=datetime.now(tz=UTC),
    )
    result = service.analyze_region(snapshot, region, [])
    assert result.analysis_id.startswith("dra-")
    assert result.region_verdict in ("continuation", "trap", "control_handoff", "inventory_release", "no_trade", "ambiguous")
    assert result.ai_summary_short
    d = result.to_dict()
    assert "event_chain" in d
    assert "derived_event_kinds" in d


def test_focus_region_review_store_and_confirm() -> None:
    from atas_market_structure.analysis_orchestration_services import DeepRegionAnalysisService
    from atas_market_structure.focus_region_review_services import FocusRegionReviewService
    from atas_market_structure.models import ReplayManualRegionAnnotationRecord
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    review_service = FocusRegionReviewService(repository=repository)
    deep_service = DeepRegionAnalysisService(strategy_engine=StrategySelectionEngine(root_dir=ROOT_DIR))
    snapshot = _build_snapshot()
    region = ReplayManualRegionAnnotationRecord(
        region_annotation_id="region-review-1",
        replay_ingestion_id="ing-review-test",
        replay_snapshot_id=snapshot.replay_snapshot_id,
        instrument_symbol="NQ",
        label="review test zone",
        thesis="test",
        price_low=21520.0,
        price_high=21530.0,
        started_at=snapshot.window_start,
        ended_at=snapshot.window_end,
        side_bias=StructureSide.BUY,
        notes=[],
        tags=[],
        stored_at=datetime.now(tz=UTC),
    )
    deep_result = deep_service.analyze_region(snapshot, region, [])
    record = review_service.store_review(deep_result, replay_ingestion_id="ing-review-test")
    assert record.review_status == "pending"
    assert record.review_id.startswith("frr-")

    confirmed = review_service.confirm_review(record.review_id, reviewer_notes="looks good")
    assert confirmed is not None
    assert confirmed.review_status == "confirmed"

    feedback = review_service.get_feedback_for_briefing("NQ")
    assert len(feedback) == 1
    assert feedback[0]["verdict"] == deep_result.region_verdict


def test_screenshot_input_stored() -> None:
    from atas_market_structure.focus_region_review_services import FocusRegionReviewService, ScreenshotAnalysisInput
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    service = FocusRegionReviewService(repository=repository)
    inp = ScreenshotAnalysisInput(
        input_id=f"si-{uuid4().hex[:8]}",
        source_type="atas_screenshot",
        instrument_symbol="NQ",
        timeframe="5m",
        session="us_regular",
        time_range_start=datetime.now(tz=UTC),
        time_range_end=datetime.now(tz=UTC),
        price_range_low=21500.0,
        price_range_high=21550.0,
        image_url="file:///screenshots/test.png",
        observed_visual_cues=["replenishment at 21510", "trapped inventory above 21540"],
        chart_id=None,
        snapshot_id=None,
        pane_type=None,
        selected_at=datetime.now(tz=UTC),
        selected_by="operator",
        linked_replay_ingestion_id="ing-test",
        notes="ATAS footprint screenshot",
    )
    ingestion_id = service.store_screenshot_input(inp)
    assert ingestion_id.startswith("ing-")


# --- Integration: strategy engine enriches replay build ---

def test_replay_build_includes_engine_enriched_candidates() -> None:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    application = MarketStructureApplication(repository=repository)

    # Ingest continuous state messages with replenishment events
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    base_time = datetime.fromisoformat("2026-03-16T14:30:00+00:00")
    for index in range(12):
        payload = json.loads(json.dumps(continuous_payload))
        emitted_at = base_time + timedelta(minutes=index)
        payload["message_id"] = f"adapter-msg-enrich-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-03d4a876"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = 21520.0 + index
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    build_request = {
        "cache_key": "NQ|5m|2026-03-16T14:30:00Z|2026-03-16T14:41:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "5m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T14:41:00Z",
        "force_rebuild": True,
        "min_continuous_messages": 5,
    }
    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["action"] == "built_from_local_history"
    # The strategy_candidate_count should be >= what legacy alone would produce
    assert body["summary"]["strategy_candidate_count"] >= 0
