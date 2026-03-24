from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from atas_market_structure.models import DegradedMode
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.repository import SQLiteAnalysisRepository
from tests.test_app_support import build_application, load_json_fixture
from tests.test_integration_chain import _continuous_payload, _history_bars_payload, _process_context_payload


def test_malformed_payload_does_not_take_down_health_surface() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingest/market-structure",
        b'{"schema_version":"1.0.0",',
    )
    assert response.status_code == 400

    health = application.dispatch("GET", "/health/ingestion")
    assert health.status_code == 200


def test_missing_depth_and_dom_keep_service_available() -> None:
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

    quality = application.dispatch("GET", "/health/data-quality?instrument_symbol=ESM6")
    assert quality.status_code == 200
    quality_payload = json.loads(quality.body)
    assert quality_payload["status"] == "degraded"
    assert "degraded_no_depth" in quality_payload["degraded_reasons"]
    assert "degraded_no_dom" in quality_payload["degraded_reasons"]

    recognition = application.dispatch("GET", "/health/recognition?instrument_symbol=ESM6")
    assert recognition.status_code == 200


def test_ai_unavailable_does_not_block_recognizer_mainline(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    observed_at = datetime(2026, 3, 23, 9, 30, tzinfo=UTC).replace(microsecond=0)

    repository.save_ingestion(
        ingestion_id="ing-hist-ai-off",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-ai-off",
        instrument_symbol="NQ",
        observed_payload=_history_bars_payload(
            symbol="NQ",
            start=observed_at - timedelta(minutes=6),
            bars=[
                (21490.0, 21493.0, 21489.75, 21492.75, 240, 95),
                (21492.75, 21496.0, 21492.5, 21495.75, 260, 112),
                (21495.75, 21499.0, 21495.5, 21498.75, 270, 118),
                (21498.75, 21502.0, 21498.5, 21501.75, 285, 124),
                (21501.75, 21505.0, 21501.5, 21504.75, 300, 138),
                (21504.75, 21508.0, 21504.5, 21507.75, 320, 150),
            ],
            emitted_at=observed_at,
        ),
        stored_at=observed_at,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-ai-off",
        ingestion_kind="process_context",
        source_snapshot_id="proc-ai-off",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=observed_at,
            point_of_control=21484.0,
            initiative_side="buy",
            zone_low=21487.0,
            zone_high=21488.5,
        ),
        stored_at=observed_at,
    )
    repository.save_ingestion(
        ingestion_id="ing-cont-ai-off",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id="msg-ai-off",
        instrument_symbol="NQ",
        observed_payload=_continuous_payload(
            symbol="NQ",
            observed_at=observed_at,
            last_price=21518.25,
            local_low=21505.0,
            local_high=21518.25,
            net_delta=820,
            volume=1400,
            side="buy",
            drive_low=21505.0,
            drive_high=21518.25,
        ),
        stored_at=observed_at,
    )

    result = DeterministicRecognitionService(repository=repository, ai_available=False).run_for_instrument(
        "NQ",
        triggered_by="pytest_ai_unavailable",
    )

    assert result.triggered is True
    assert result.belief_state is not None
    assert DegradedMode.NO_AI in result.belief_state.data_status.degraded_modes


def test_replay_rebuild_mode_leaves_health_surface_available() -> None:
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
        "completeness": "gapped",
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
        "latest_backfill_status": None,
    }

    store = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        json.dumps(replay_payload).encode("utf-8"),
    )
    assert store.status_code == 201

    quality = application.dispatch("GET", "/health/data-quality?instrument_symbol=NQ")
    assert quality.status_code == 200
    quality_payload = json.loads(quality.body)
    assert quality_payload["status"] == "rebuild_required"
    assert "replay_rebuild_mode" in quality_payload["degraded_reasons"]

    recognition = application.dispatch("GET", "/health/recognition?instrument_symbol=NQ")
    assert recognition.status_code == 200


def test_same_input_rebuild_keeps_belief_semantics_stable(tmp_path: Path) -> None:
    def _run_once(base_dir: Path):
        base_dir.mkdir(parents=True, exist_ok=True)
        repository = SQLiteAnalysisRepository(base_dir / "data" / "market_structure.db")
        repository.initialize()
        observed_at = datetime(2026, 3, 23, 9, 30, tzinfo=UTC).replace(microsecond=0)
        repository.save_ingestion(
            ingestion_id=f"ing-hist-{base_dir.name}",
            ingestion_kind="adapter_history_bars",
            source_snapshot_id=f"hist-{base_dir.name}",
            instrument_symbol="NQ",
            observed_payload=_history_bars_payload(
                symbol="NQ",
                start=observed_at - timedelta(minutes=6),
                bars=[
                    (21490.0, 21493.0, 21489.75, 21492.75, 240, 95),
                    (21492.75, 21496.0, 21492.5, 21495.75, 260, 112),
                    (21495.75, 21499.0, 21495.5, 21498.75, 270, 118),
                    (21498.75, 21502.0, 21498.5, 21501.75, 285, 124),
                    (21501.75, 21505.0, 21501.5, 21504.75, 300, 138),
                    (21504.75, 21508.0, 21504.5, 21507.75, 320, 150),
                ],
                emitted_at=observed_at,
            ),
            stored_at=observed_at,
        )
        repository.save_ingestion(
            ingestion_id=f"ing-proc-{base_dir.name}",
            ingestion_kind="process_context",
            source_snapshot_id=f"proc-{base_dir.name}",
            instrument_symbol="NQ",
            observed_payload=_process_context_payload(
                symbol="NQ",
                observed_at=observed_at,
                point_of_control=21484.0,
                initiative_side="buy",
                zone_low=21487.0,
                zone_high=21488.5,
            ),
            stored_at=observed_at,
        )
        repository.save_ingestion(
            ingestion_id=f"ing-cont-{base_dir.name}",
            ingestion_kind="adapter_continuous_state",
            source_snapshot_id=f"msg-{base_dir.name}",
            instrument_symbol="NQ",
            observed_payload=_continuous_payload(
                symbol="NQ",
                observed_at=observed_at,
                last_price=21518.25,
                local_low=21505.0,
                local_high=21518.25,
                net_delta=820,
                volume=1400,
                side="buy",
                drive_low=21505.0,
                drive_high=21518.25,
            ),
            stored_at=observed_at,
        )
        result = DeterministicRecognitionService(repository=repository, ai_available=False).run_for_instrument(
            "NQ",
            triggered_by="pytest_rebuild",
        )
        assert result.belief_state is not None
        return result.belief_state

    first = _run_once(tmp_path / "run_a")
    second = _run_once(tmp_path / "run_b")

    assert first.recognition_mode == second.recognition_mode
    assert first.regime_posteriors[0].regime == second.regime_posteriors[0].regime
    assert first.event_hypotheses[0].mapped_event_kind == second.event_hypotheses[0].mapped_event_kind
    assert first.event_hypotheses[0].phase == second.event_hypotheses[0].phase
