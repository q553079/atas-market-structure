from __future__ import annotations

import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

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

def test_replay_workbench_page_is_served() -> None:
    application = build_application()

    response = application.dispatch("GET", "/workbench/replay")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert "<title>盘前复盘工作台</title>".encode("utf-8") in response.body
    assert 'href="/static/chat_window.css"'.encode("utf-8") in response.body
    assert 'from "/static/replay_workbench_bootstrap.js"'.encode("utf-8") in response.body
    assert "打开 AI 助手".encode("utf-8") in response.body
    assert "最近7天".encode("utf-8") in response.body
    assert "手工区域".encode("utf-8") in response.body
    assert "标记管理".encode("utf-8") in response.body
    assert "发送当前可视区域到聊天".encode("utf-8") in response.body

def test_replay_workbench_chat_static_assets_are_served() -> None:
    application = build_application()

    css_response = application.dispatch("GET", "/static/chat_window.css")
    js_response = application.dispatch("GET", "/static/chat_window.js")

    assert css_response.status_code == 200
    assert css_response.headers["Content-Type"] == "text/css; charset=utf-8"
    assert ".chat-message.user".encode("utf-8") in css_response.body
    assert ".ai-chat-module".encode("utf-8") in css_response.body

    assert js_response.status_code == 200
    assert js_response.headers["Content-Type"] == "application/javascript; charset=utf-8"
    assert "window.ReplayChatWindow".encode("utf-8") in js_response.body
    assert "renderThread".encode("utf-8") in js_response.body

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
