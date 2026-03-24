from __future__ import annotations

import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiReviewService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ChartCandle,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiReviewRequest,
    ReplayWorkbenchBuildRequest,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import ApplicationRequestHandler
from atas_market_structure.strategy_library_services import StrategyLibraryService
from tests.test_app_support import (
    FakeReplayChatAssistant,
    FakeReplayReviewer,
    TEST_DB_DIR,
    build_application,
    load_fixture,
    load_json_fixture,
)

def test_replay_ai_review_endpoint_returns_structured_review() -> None:
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    review_service = ReplayAiReviewService(repository=repository, reviewer=FakeReplayReviewer())
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_review_service=review_service,
    )

    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)
    entry_response = application.dispatch(
        "POST",
        "/api/v1/workbench/operator-entries",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "executed_at": "2026-03-17T01:05:00Z",
                "side": "buy",
                "entry_price": 21524.25,
                "quantity": 1,
                "stop_price": 21518.25,
                "timeframe_context": "1m",
                "thesis": "micro trend continuation",
                "context_notes": ["defended bid held twice"],
                "tags": ["scalp", "continuation"],
            }
        ).encode("utf-8"),
    )
    assert entry_response.status_code == 201

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-ai-review",
        json.dumps(
            ReplayAiReviewRequest(
                replay_ingestion_id=replay_payload["ingestion_id"],
                model_override="fake-gpt-override",
                force_refresh=False,
            ).model_dump(mode="json")
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["provider"] == "fake-openai"
    assert payload["model"] == "fake-gpt-override"
    assert payload["replay_ingestion_id"] == replay_payload["ingestion_id"]
    assert payload["review"]["script_review"]["preferred_script"] == "continuation"
    assert payload["review"]["key_zones"][0]["role"] == "support"
    assert payload["review"]["entry_reviews"][0]["verdict"] == "valid"
    assert payload["review"]["no_trade_guidance"][0].startswith("Do not open")

def test_operator_entry_is_stored_and_listed() -> None:
    application = build_application()
    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/operator-entries",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "executed_at": "2026-03-17T01:05:00Z",
                "side": "sell",
                "entry_price": 21531.5,
                "quantity": 2,
                "stop_price": 21535.0,
                "target_price": 21521.0,
                "timeframe_context": "1m",
                "thesis": "fade failed overhead cap",
                "context_notes": ["upper liquidity already harvested"],
                "tags": ["scalp", "fade"],
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["entry"]["side"] == "sell"
    assert payload["entry"]["instrument_symbol"] == "NQ"

    list_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/operator-entries?replay_ingestion_id={replay_payload['ingestion_id']}",
    )
    assert list_response.status_code == 200
    list_payload = json.loads(list_response.body)
    assert list_payload["replay_ingestion_id"] == replay_payload["ingestion_id"]
    assert len(list_payload["entries"]) == 1
    assert list_payload["entries"][0]["thesis"] == "fade failed overhead cap"

def test_manual_region_is_stored_and_listed() -> None:
    application = build_application()
    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/manual-regions",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "label": "bullish defense candidate",
                "thesis": "If price returns here with absorption, the region may reverse higher.",
                "price_low": 21508.5,
                "price_high": 21514.25,
                "started_at": "2026-03-17T00:30:00Z",
                "ended_at": "2026-03-17T01:15:00Z",
                "side_bias": "buy",
                "notes": ["watch replenishment", "wait for rejection"],
                "tags": ["support", "trapped_inventory"],
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["region"]["label"] == "bullish defense candidate"
    assert payload["region"]["side_bias"] == "buy"

    list_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/manual-regions?replay_ingestion_id={replay_payload['ingestion_id']}",
    )
    assert list_response.status_code == 200
    list_payload = json.loads(list_response.body)
    assert len(list_payload["regions"]) == 1
    assert list_payload["regions"][0]["tags"] == ["support", "trapped_inventory"]

def test_replay_footprint_bar_detail_endpoint_returns_price_levels() -> None:
    application = build_application()
    history_bars_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_footprint_payload = load_json_fixture("atas_adapter.history_footprint.sample.json")

    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_bars_payload).encode("utf-8"),
    )
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-footprint",
        json.dumps(history_footprint_payload).encode("utf-8"),
    )

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T08:59:00Z|2026-03-17T09:00:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T08:59:00Z",
        "window_end": "2026-03-17T09:00:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    build_body = json.loads(build_response.body)

    detail_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/footprint-bar?replay_ingestion_id={build_body['ingestion_id']}&bar_started_at=2026-03-17T09:00:00+00:00",
    )
    assert detail_response.status_code == 200
    detail_payload = json.loads(detail_response.body)
    assert detail_payload["instrument_symbol"] == "NQ"
    assert len(detail_payload["price_levels"]) == 5
    assert detail_payload["price_levels"][0]["price"] >= detail_payload["price_levels"][-1]["price"]
