from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from atas_market_structure.analysis_orchestration_services import (
    DeepRegionAnalysisService,
    FullMarketAnalysisService,
    LightweightMonitorService,
)
from atas_market_structure.app_shared import NotFoundError
from atas_market_structure.focus_region_review_services import FocusRegionReviewService, ScreenshotAnalysisInput
from atas_market_structure.models import (
    ReplayManualRegionAnnotationRecord,
    ReplayOperatorEntryRecord,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_analysis_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "POST" and route_path == "/api/v1/analysis/lightweight-monitor":
        req = json.loads(body or b"{}")
        snapshot = _resolve_snapshot_for_analysis(app, req)
        entries = _resolve_entries_for_analysis(app, req, snapshot)
        engine = StrategySelectionEngine()
        svc = LightweightMonitorService(strategy_engine=engine)
        result = svc.run(snapshot, entries, previous_focus_region_count=req.get("previous_focus_region_count", 0))
        return app._json_response(200, result.to_dict())

    if method == "POST" and route_path == "/api/v1/analysis/full-market":
        req = json.loads(body or b"{}")
        snapshot = _resolve_snapshot_for_analysis(app, req)
        entries = _resolve_entries_for_analysis(app, req, snapshot)
        engine = StrategySelectionEngine()
        svc = FullMarketAnalysisService(strategy_engine=engine)
        result = svc.analyze(snapshot, entries)
        return app._json_response(200, result.to_dict())

    if method == "POST" and route_path == "/api/v1/analysis/deep-region":
        req = json.loads(body or b"{}")
        snapshot = _resolve_snapshot_for_analysis(app, req)
        entries = _resolve_entries_for_analysis(app, req, snapshot)
        region_data = req.get("region")
        if region_data is None:
            return app._json_response(400, {"error": "missing_field", "detail": "region is required."})
        region = ReplayManualRegionAnnotationRecord(**region_data)
        engine = StrategySelectionEngine()
        svc = DeepRegionAnalysisService(strategy_engine=engine)
        source_type = req.get("source_type", "manual_marked")
        result = svc.analyze_region(snapshot, region, entries, source_type=source_type)
        return app._json_response(200, result.to_dict())

    if method == "POST" and route_path == "/api/v1/analysis/store-review":
        req = json.loads(body or b"{}")
        snapshot = _resolve_snapshot_for_analysis(app, req)
        entries = _resolve_entries_for_analysis(app, req, snapshot)
        region_data = req.get("region")
        if region_data is None:
            return app._json_response(400, {"error": "missing_field", "detail": "region is required."})
        region = ReplayManualRegionAnnotationRecord(**region_data)
        engine = StrategySelectionEngine()
        deep_svc = DeepRegionAnalysisService(strategy_engine=engine)
        deep_result = deep_svc.analyze_region(snapshot, region, entries, source_type=req.get("source_type", "manual_marked"))
        review_svc = FocusRegionReviewService(repository=app._repository)
        record = review_svc.store_review(
            deep_result,
            replay_ingestion_id=req.get("replay_ingestion_id", ""),
            market_context=req.get("market_context"),
            reviewer_notes=req.get("reviewer_notes", ""),
        )
        return app._json_response(201, record.to_dict())

    if method == "POST" and route_path == "/api/v1/analysis/confirm-review":
        req = json.loads(body or b"{}")
        review_id = req.get("review_id")
        if not review_id:
            return app._json_response(400, {"error": "missing_field", "detail": "review_id is required."})
        review_svc = FocusRegionReviewService(repository=app._repository)
        record = review_svc.confirm_review(review_id, reviewer_notes=req.get("reviewer_notes", ""))
        if record is None:
            return app._json_response(404, {"error": "not_found", "detail": f"review '{review_id}' not found"})
        return app._json_response(200, record.to_dict())

    if method == "POST" and route_path == "/api/v1/analysis/reject-review":
        req = json.loads(body or b"{}")
        review_id = req.get("review_id")
        if not review_id:
            return app._json_response(400, {"error": "missing_field", "detail": "review_id is required."})
        review_svc = FocusRegionReviewService(repository=app._repository)
        record = review_svc.reject_review(review_id, reviewer_notes=req.get("reviewer_notes", ""))
        if record is None:
            return app._json_response(404, {"error": "not_found", "detail": f"review '{review_id}' not found"})
        return app._json_response(200, record.to_dict())

    if method == "GET" and route_path == "/api/v1/analysis/reviews":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        status_filter = query.get("status", [None])[0]
        review_svc = FocusRegionReviewService(repository=app._repository)
        records = review_svc.list_reviews(instrument_symbol=instrument_symbol, status_filter=status_filter)
        return app._json_response(200, {"reviews": [r.to_dict() for r in records]})

    if method == "GET" and route_path == "/api/v1/analysis/review-feedback":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        if not instrument_symbol:
            return app._json_response(400, {"error": "missing_query_parameter", "detail": "instrument_symbol is required."})
        review_svc = FocusRegionReviewService(repository=app._repository)
        feedback = review_svc.get_feedback_for_briefing(instrument_symbol)
        return app._json_response(200, {"feedback": feedback})

    if method == "POST" and route_path == "/api/v1/analysis/screenshot-input":
        req = json.loads(body or b"{}")
        inp = ScreenshotAnalysisInput(
            input_id=req.get("input_id", f"si-{uuid4().hex[:8]}"),
            source_type=req.get("source_type", "atas_screenshot"),
            instrument_symbol=req.get("instrument_symbol"),
            timeframe=req.get("timeframe"),
            session=req.get("session"),
            time_range_start=datetime.fromisoformat(req["time_range_start"]) if req.get("time_range_start") else None,
            time_range_end=datetime.fromisoformat(req["time_range_end"]) if req.get("time_range_end") else None,
            price_range_low=req.get("price_range_low"),
            price_range_high=req.get("price_range_high"),
            image_url=req.get("image_url"),
            observed_visual_cues=req.get("observed_visual_cues", []),
            chart_id=req.get("chart_id"),
            snapshot_id=req.get("snapshot_id"),
            pane_type=req.get("pane_type"),
            selected_at=datetime.fromisoformat(req["selected_at"]) if req.get("selected_at") else datetime.now(tz=UTC),
            selected_by=req.get("selected_by", "operator"),
            linked_replay_ingestion_id=req.get("linked_replay_ingestion_id"),
            notes=req.get("notes", ""),
        )
        review_svc = FocusRegionReviewService(repository=app._repository)
        ingestion_id = review_svc.store_screenshot_input(inp)
        return app._json_response(201, {"ingestion_id": ingestion_id, "input_id": inp.input_id})

    return None


def _resolve_snapshot_for_analysis(
    app: MarketStructureApplication,
    req: dict[str, Any],
) -> ReplayWorkbenchSnapshotPayload:
    if "snapshot" in req:
        return ReplayWorkbenchSnapshotPayload.model_validate(req["snapshot"])
    cache_key = req.get("cache_key")
    if cache_key:
        cache_record = app._replay_workbench_service.get_cache_record(cache_key)
        return ReplayWorkbenchSnapshotPayload.model_validate_json(json.dumps(cache_record.snapshot_payload).encode())
    raise NotFoundError("Either 'snapshot' or 'cache_key' must be provided.")


def _resolve_entries_for_analysis(
    app: MarketStructureApplication,
    req: dict[str, Any],
    snapshot: ReplayWorkbenchSnapshotPayload,
) -> list[ReplayOperatorEntryRecord]:
    _ = snapshot
    if "entries" in req:
        return [ReplayOperatorEntryRecord(**e) for e in req["entries"]]
    replay_ingestion_id = req.get("replay_ingestion_id")
    if replay_ingestion_id:
        envelope = app._replay_workbench_service.list_operator_entries(replay_ingestion_id)
        return envelope.entries
    return []
