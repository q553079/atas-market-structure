from __future__ import annotations

import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiChatService
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

def test_replay_ai_chat_endpoint_uses_strategy_library_cards() -> None:
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    chat_service = ReplayAiChatService(
        repository=repository,
        assistant=FakeReplayChatAssistant(),
        strategy_library_service=StrategyLibraryService(root_dir=Path(__file__).resolve().parents[1]),
    )
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_chat_service=chat_service,
    )

    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)
    application.dispatch(
        "POST",
        "/api/v1/workbench/manual-regions",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "label": "bullish defense candidate",
                "thesis": "This region may hold only if absorption appears on retest.",
                "price_low": 21508.5,
                "price_high": 21514.25,
                "started_at": "2026-03-17T00:30:00Z",
                "ended_at": "2026-03-17T01:15:00Z",
                "side_bias": "buy",
                "notes": ["wait for confirmation"],
                "tags": ["support", "manual_region"],
            }
        ).encode("utf-8"),
    )

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["message_id"] = "adapter-msg-chat-01"
    continuous_payload["emitted_at"] = "2026-03-17T01:04:30Z"
    continuous_payload["observed_window_start"] = "2026-03-17T01:04:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T01:05:00Z"
    continuous_payload["source"]["chart_instance_id"] = "NQ-03d4a876"
    continuous_payload["instrument"]["symbol"] = "NQ"
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-ai-chat",
        json.dumps(
            ReplayAiChatRequest(
                replay_ingestion_id=replay_payload["ingestion_id"],
                preset=ReplayAiChatPreset.FOCUS_REGIONS,
                user_message="分析重点价格区域，并说明哪里不能开仓。",
                history=[],
                model_override="fake-chat-override",
                include_live_context=True,
            ).model_dump(mode="json")
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["provider"] == "fake-openai"
    assert payload["model"] == "fake-chat-override"
    assert payload["preset"] == "focus_regions"
    assert payload["reply_text"].startswith("preset=focus_regions")
    assert payload["referenced_strategy_ids"] == ["pattern-nq-replenished-bid-launchpad"]
    assert payload["live_context_summary"][0] == "live_messages=1"
    assert payload["live_context_summary"][3] == "manual_regions=1"
    assert len(payload["follow_up_suggestions"]) == 2

def test_chat_session_routes_remain_available_without_ai_backend() -> None:
    application = build_application()

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "无模型会话",
                "symbol": "NQ",
                "contract_id": "NQ",
                "timeframe": "1m",
                "window_range": {
                    "start": "2026-03-17T13:30:00Z",
                    "end": "2026-03-17T20:00:00Z",
                },
                "start_blank": True,
            }
        ).encode("utf-8"),
    )
    assert create_response.status_code == 201
    session_id = json.loads(create_response.body)["session"]["session_id"]

    list_response = application.dispatch("GET", "/api/v1/workbench/chat/sessions")
    assert list_response.status_code == 200
    assert len(json.loads(list_response.body)["sessions"]) == 1

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "这里还能不能继续做多？",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": False,
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 503
    reply_payload = json.loads(reply_response.body)
    assert reply_payload["error"] == "chat_unavailable"

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    assert messages_response.status_code == 200
    assert json.loads(messages_response.body)["messages"] == []

def test_http_bridge_supports_patch_requests_for_chat_sessions() -> None:
    application = build_application()
    ApplicationRequestHandler.application = application
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApplicationRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        create_response = application.dispatch(
            "POST",
            "/api/v1/workbench/chat/sessions",
            json.dumps(
                {
                    "workspace_id": "replay_main",
                    "title": "PATCH 会话",
                    "symbol": "NQ",
                    "contract_id": "NQ",
                    "timeframe": "1m",
                    "window_range": {
                        "start": "2026-03-17T13:30:00Z",
                        "end": "2026-03-17T20:00:00Z",
                    },
                    "start_blank": True,
                }
            ).encode("utf-8"),
        )
        session_id = json.loads(create_response.body)["session"]["session_id"]

        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request(
            "PATCH",
            f"/api/v1/workbench/chat/sessions/{session_id}",
            body=json.dumps({"title": "PATCH 已更新", "pinned": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

        assert response.status == 200
        assert payload["session"]["title"] == "PATCH 已更新"
        assert payload["session"]["pinned"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_prompt_trace_routes_expose_trace_by_message_trace_id_and_session() -> None:
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_chat_service=ReplayAiChatService(repository=repository, assistant=FakeReplayChatAssistant()),
    )

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "Prompt Trace 路由",
                "symbol": "NQ",
                "contract_id": "NQ",
                "timeframe": "1m",
                "window_range": {
                    "start": "2026-03-17T13:30:00Z",
                    "end": "2026-03-17T20:00:00Z",
                },
                "start_blank": True,
            }
        ).encode("utf-8"),
    )
    assert create_response.status_code == 201
    session_id = json.loads(create_response.body)["session"]["session_id"]

    snapshot_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    assert snapshot_response.status_code == 201
    replay_ingestion_id = json.loads(snapshot_response.body)["ingestion_id"]

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": replay_ingestion_id,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "请解释一下这轮分析到底看了什么。",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": True,
                "include_recent_messages": True,
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 200
    reply_payload = json.loads(reply_response.body)
    prompt_trace_id = reply_payload["assistant_message"]["prompt_trace_id"]
    message_id = reply_payload["assistant_message"]["message_id"]
    assert reply_payload["assistant_message"]["meta"]["prompt_trace_id"] == prompt_trace_id
    assert reply_payload["assistant_message"]["meta"]["workbench_ui"]["schema_version"] == "workbench_ui_contract_v1"
    assert reply_payload["assistant_message"]["meta"]["workbench_ui"]["context_version"]
    assert "context_blocks" in reply_payload["assistant_message"]["meta"]["workbench_ui"]
    assert reply_payload["assistant_message"]["meta"]["workbench_ui"]["include_memory_summary"] is True
    assert reply_payload["assistant_message"]["meta"]["workbench_ui"]["include_recent_messages"] is True
    assert "stale_state" not in reply_payload["assistant_message"]["meta"]["workbench_ui"]

    by_message_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/messages/{message_id}/prompt-trace",
    )
    assert by_message_response.status_code == 200
    by_message_payload = json.loads(by_message_response.body)
    assert by_message_payload["trace"]["prompt_trace_id"] == prompt_trace_id
    assert by_message_payload["trace"]["message_id"] == message_id
    assert by_message_payload["trace"]["context_version"] == by_message_payload["trace"]["snapshot"]["context_version"]
    assert by_message_payload["trace"]["context_blocks"] == by_message_payload["trace"]["snapshot"]["context_blocks"]
    assert by_message_payload["trace"]["block_version_refs"] == by_message_payload["trace"]["metadata"]["block_version_refs"]
    assert by_message_payload["trace"]["reply_window_anchor"] == by_message_payload["trace"]["metadata"]["reply_window_anchor"]
    assert by_message_payload["trace"]["metadata"]["context_version"] == reply_payload["assistant_message"]["meta"]["workbench_ui"]["context_version"]
    assert by_message_payload["trace"]["metadata"]["reply_window_anchor"] == reply_payload["assistant_message"]["meta"]["workbench_ui"]["reply_window_anchor"]
    assert reply_payload["assistant_message"]["meta"]["workbench_ui"]["context_blocks"] == by_message_payload["trace"]["context_blocks"]

    by_id_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/prompt-traces/{prompt_trace_id}",
    )
    assert by_id_response.status_code == 200
    by_id_payload = json.loads(by_id_response.body)
    assert by_id_payload["trace"]["prompt_trace_id"] == prompt_trace_id
    assert by_id_payload["trace"]["session_id"] == session_id
    assert by_id_payload["trace"]["context_version"] == by_id_payload["trace"]["snapshot"]["context_version"]
    assert by_id_payload["trace"]["context_blocks"] == by_id_payload["trace"]["snapshot"]["context_blocks"]
    assert by_id_payload["trace"]["block_version_refs"] == by_id_payload["trace"]["metadata"]["block_version_refs"]
    assert by_id_payload["trace"]["reply_window_anchor"] == by_id_payload["trace"]["metadata"]["reply_window_anchor"]
    assert by_id_payload["trace"]["metadata"]["context_version"] == by_id_payload["trace"]["snapshot"]["context_version"]
    assert by_id_payload["trace"]["metadata"]["block_version_refs"] == by_id_payload["trace"]["snapshot"]["context_blocks"]

    by_session_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/prompt-traces?session_id={session_id}",
    )
    assert by_session_response.status_code == 200
    by_session_payload = json.loads(by_session_response.body)
    assert by_session_payload["schema_version"] == "workbench_prompt_trace_list_envelope_v1"
    assert len(by_session_payload["traces"]) == 1
    assert by_session_payload["traces"][0]["prompt_trace_id"] == prompt_trace_id
    assert by_session_payload["traces"][0]["context_version"] == by_session_payload["traces"][0]["snapshot"]["context_version"]
    assert by_session_payload["traces"][0]["context_blocks"] == by_session_payload["traces"][0]["snapshot"]["context_blocks"]
    assert by_session_payload["traces"][0]["metadata"]["context_version"] == reply_payload["assistant_message"]["meta"]["workbench_ui"]["context_version"]


def test_prompt_trace_list_route_requires_session_id_query_parameter() -> None:
    application = build_application()

    response = application.dispatch(
        "GET",
        "/api/v1/workbench/prompt-traces",
    )

    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["error"] == "missing_query_parameter"
    assert payload["detail"] == "session_id is required."
