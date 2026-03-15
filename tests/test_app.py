from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.repository import SQLiteAnalysisRepository


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "samples"
TEST_DB_DIR = Path(__file__).resolve().parents[1] / "data" / "test-runs"


def build_application() -> MarketStructureApplication:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return MarketStructureApplication(repository=repository)


def load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def test_market_structure_ingestion_returns_derived_analysis() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        load_fixture("market_structure.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["route_key"] == "trend_continuation_review_long"
    assert payload["analysis"]["knowledge_route"]["route_key"] == "trend_continuation_review_long"

    analysis_response = application.dispatch("GET", f"/api/v1/analyses/{payload['analysis_id']}")
    assert analysis_response.status_code == 200
    analysis_payload = json.loads(analysis_response.body)
    assert analysis_payload["analysis"]["analysis_id"] == payload["analysis_id"]

    ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert ingestion_response.status_code == 200
    ingestion_payload = json.loads(ingestion_response.body)
    assert ingestion_payload["observed_payload"]["snapshot_id"] == "ms-20260315-093000"


def test_invalid_layer_timeframe_is_rejected() -> None:
    application = build_application()
    invalid_payload = json.loads(load_fixture("market_structure.sample.json"))
    invalid_payload["decision_layers"]["macro_context"][0]["timeframe"] = "1m"

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        json.dumps(invalid_payload).encode("utf-8"),
    )

    assert response.status_code == 422
    payload = json.loads(response.body)
    assert payload["error"] == "validation_error"


def test_event_snapshot_ingestion_supports_execution_reversal_route() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/event-snapshot",
        load_fixture("event_snapshot.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["analysis"]["knowledge_route"]["route_key"] == "execution_reversal_review"


def test_process_context_supports_cross_session_release_route() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        load_fixture("market_structure.process.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["analysis"]["knowledge_route"]["route_key"] == "session_release_review_long"
    assert payload["analysis"]["process_context"]
    subject_kinds = {item["subject_kind"] for item in payload["analysis"]["process_context"]}
    assert "cross_session_sequence" in subject_kinds
    assert "liquidity_episode" in subject_kinds


def test_depth_snapshot_updates_significant_liquidity_memory() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/depth-snapshot",
        load_fixture("depth_snapshot.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["coverage_state"] == "depth_live"
    assert len(payload["updated_memories"]) == 2

    classifications = {item["derived_interpretation"]["classification"] for item in payload["updated_memories"]}
    assert "spoof_candidate" in classifications
    assert "absorption_candidate" in classifications


def test_liquidity_memory_endpoint_lists_active_records() -> None:
    application = build_application()
    application.dispatch(
        "POST",
        "/api/v1/ingestions/depth-snapshot",
        load_fixture("depth_snapshot.sample.json"),
    )

    response = application.dispatch("GET", "/api/v1/liquidity-memory?symbol=ESM6")
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert len(payload["memories"]) == 2
    assert all(item["instrument_symbol"] == "ESM6" for item in payload["memories"])
