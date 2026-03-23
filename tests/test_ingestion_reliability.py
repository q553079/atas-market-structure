from __future__ import annotations

import json

from test_app import build_application, load_fixture, load_json_fixture


def test_reliable_market_structure_ingestion_deduplicates_by_request_id() -> None:
    application = build_application()

    first_response = application.dispatch(
        "POST",
        "/api/v1/ingest/market-structure",
        load_fixture("market_structure.sample.json"),
    )
    second_response = application.dispatch(
        "POST",
        "/api/v1/ingest/market-structure",
        load_fixture("market_structure.sample.json"),
    )

    assert first_response.status_code == 201
    first_payload = json.loads(first_response.body)
    assert first_payload["status"] == "accepted"
    assert first_payload["duplicate"] is False
    assert first_payload["ingestion_kind"] == "market_structure"
    assert first_payload["downstream_status"] == "completed"
    assert first_payload["downstream_result"]["route_key"] == "trend_continuation_review_long"
    assert first_payload["schema_version"] == "1.0.0"
    assert "data_status" in first_payload

    assert second_response.status_code == 200
    second_payload = json.loads(second_response.body)
    assert second_payload["status"] == "duplicate"
    assert second_payload["duplicate"] is True
    assert second_payload["ingestion_id"] == first_payload["ingestion_id"]
    assert second_payload["dedup_key"] == first_payload["dedup_key"]
    assert second_payload["payload_hash"] == first_payload["payload_hash"]


def test_process_context_endpoint_persists_raw_payload_and_skips_downstream() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingest/process-context",
        load_fixture("process_context.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["status"] == "accepted"
    assert payload["ingestion_kind"] == "process_context"
    assert payload["downstream_status"] == "skipped"
    assert payload["downstream_result"]["stored_only"] is True

    stored_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert stored_response.status_code == 200
    stored_payload = json.loads(stored_response.body)
    assert stored_payload["observed_payload"]["process_context_id"] == "proc-20260315-093100"


def test_invalid_json_is_dead_lettered_and_reported_in_health_metrics() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingest/market-structure",
        b'{"schema_version":"1.0.0",',
    )

    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["error"] == "invalid_json"
    assert payload["dead_letter_id"].startswith("dlq-")

    health_response = application.dispatch("GET", "/health/ingestion")
    assert health_response.status_code == 200
    health_payload = json.loads(health_response.body)
    assert health_payload["metrics"]["dead_letter_count"] >= 1
    assert any(item["outcome"] == "dead_lettered" for item in health_payload["recent_runs"])


def test_depth_snapshot_without_dom_is_accepted_and_marks_degraded_mode() -> None:
    application = build_application()
    payload = load_json_fixture("depth_snapshot.sample.json")
    payload["depth_snapshot_id"] = "depth-20260316-143501-missing"
    payload["coverage_state"] = "depth_unavailable"
    payload["best_bid"] = None
    payload["best_ask"] = None
    payload["significant_levels"] = []

    response = application.dispatch(
        "POST",
        "/api/v1/ingest/depth-snapshot",
        json.dumps(payload).encode("utf-8"),
    )

    assert response.status_code == 201
    body = json.loads(response.body)
    assert body["status"] == "accepted"
    assert body["ingestion_kind"] == "depth_snapshot"
    assert body["downstream_result"]["coverage_state"] == "depth_unavailable"

    quality_response = application.dispatch("GET", "/health/data-quality?instrument_symbol=ESM6")
    assert quality_response.status_code == 200
    quality_payload = json.loads(quality_response.body)
    assert quality_payload["status"] == "degraded"
    assert "degraded_no_depth" in quality_payload["degraded_reasons"]
    assert "degraded_no_dom" in quality_payload["degraded_reasons"]
    assert quality_payload["data_status"]["depth_available"] is False
    assert quality_payload["data_status"]["dom_available"] is False


def test_adapter_payload_endpoint_reuses_existing_adapter_flow_after_raw_store() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingest/adapter-payload",
        load_fixture("atas_adapter.continuous_state.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["status"] == "accepted"
    assert payload["ingestion_kind"] == "adapter_continuous_state"
    assert payload["downstream_status"] == "completed"
    assert payload["downstream_result"]["message_type"] == "continuous_state"
    assert payload["downstream_result"]["bridge_errors"] == []
    assert len(payload["downstream_result"]["durable_outputs"]) == 1

    raw_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert raw_response.status_code == 200
    raw_payload = json.loads(raw_response.body)
    assert raw_payload["observed_payload"]["message_id"] == "adapter-msg-20260316-143001"


def test_health_reports_rebuild_required_when_latest_replay_snapshot_is_in_rebuild_mode() -> None:
    application = build_application()
    replay_payload = load_json_fixture("replay_workbench.snapshot.sample.json")
    replay_payload["profile_version"] = "profile-test-v1"
    replay_payload["engine_version"] = "engine-test-v1"
    replay_payload["data_status"] = {
        "data_freshness_ms": 2500,
        "feature_completeness": 0.5,
        "depth_available": False,
        "dom_available": False,
        "ai_available": False,
        "degraded_modes": ["replay_rebuild_mode", "degraded_no_depth", "degraded_no_dom", "degraded_no_ai"],
        "freshness": "delayed",
        "completeness": "gapped"
    }
    replay_payload["integrity"] = {
        "status": "gaps_detected",
        "window_start": replay_payload["window_start"],
        "window_end": replay_payload["window_end"],
        "window_days": 5,
        "gap_count": 1,
        "missing_bar_count": 4,
        "completeness": "gapped",
        "freshness": "delayed",
        "latest_data_status": "degraded",
        "missing_segments": [],
        "latest_backfill_request_id": None,
        "latest_backfill_status": None
    }

    store_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        json.dumps(replay_payload).encode("utf-8"),
    )
    assert store_response.status_code == 201

    quality_response = application.dispatch("GET", "/health/data-quality?instrument_symbol=NQ")
    assert quality_response.status_code == 200
    quality_payload = json.loads(quality_response.body)
    assert quality_payload["status"] == "rebuild_required"
    assert "replay_rebuild_mode" in quality_payload["degraded_reasons"]


def test_health_reports_paused_when_pause_sentinel_exists() -> None:
    application = build_application()
    pause_file = application._repository.workspace_root / "runtime" / "ingestion.paused"
    pause_file.parent.mkdir(parents=True, exist_ok=True)
    pause_file.write_text("paused", encoding="utf-8")
    try:
        response = application.dispatch("GET", "/health/ingestion")
        assert response.status_code == 200
        payload = json.loads(response.body)
        assert payload["status"] == "paused"
    finally:
        pause_file.unlink(missing_ok=True)
