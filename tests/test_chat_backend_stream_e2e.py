from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ReplayAiChatPreset
from atas_market_structure.repository import SQLiteAnalysisRepository
from tests.test_chat_backend_support import (
    FakeReplayChatAssistant,
    TEST_DB_DIR,
    build_application,
    load_fixture,
)

def test_chat_stream_endpoint_returns_sse_events_without_replay_snapshot() -> None:
    application, _repository = build_application()

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "无图表SSE测试",
                "symbol": "NQ",
                "contract_id": "NQM2026",
                "timeframe": "1m",
                "window_range": {
                    "start": "2026-03-17T13:30:00Z",
                    "end": "2026-03-17T20:00:00Z",
                },
                "active_model": "fake-chat-e2e",
                "start_blank": True,
            }
        ).encode("utf-8"),
    )
    session_id = json.loads(create_session_response.body)["session"]["session_id"]

    stream_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/stream",
        json.dumps(
            {
                "replay_ingestion_id": None,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "没有图表，先做纯聊天。",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": True,
                "model": "fake-chat-e2e",
                "attachments": [],
            }
        ).encode("utf-8"),
    )

    assert stream_response.status_code == 200
    body = b"".join(stream_response.stream_chunks).decode("utf-8")
    assert "event: message_start" in body
    assert "event: token" in body
    assert "event: message_end" in body

def test_chat_stream_endpoint_returns_sse_events() -> None:
    application, _repository = build_application()

    snapshot_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_ingestion_id = json.loads(snapshot_response.body)["ingestion_id"]

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "SSE测试",
                "symbol": "NQ",
                "contract_id": "NQM2026",
                "timeframe": "1m",
                "window_range": {
                    "start": "2026-03-17T13:30:00Z",
                    "end": "2026-03-17T20:00:00Z",
                },
                "active_model": "fake-chat-e2e",
                "start_blank": True,
            }
        ).encode("utf-8"),
    )
    session_id = json.loads(create_session_response.body)["session"]["session_id"]

    stream_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/stream",
        json.dumps(
            {
                "replay_ingestion_id": replay_ingestion_id,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "这里如果回踩还做不做？",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": False,
                "model": "fake-chat-e2e",
                "attachments": [],
            }
        ).encode("utf-8"),
    )

    assert stream_response.status_code == 200
    assert stream_response.headers["Content-Type"] == "text/event-stream; charset=utf-8"
    assert stream_response.stream_chunks is not None
    body = b"".join(stream_response.stream_chunks).decode("utf-8")
    assert "event: message_start" in body
    assert "event: token" in body
    assert "event: message_end" in body
    assert "\\u505a\\u591a" in body or "reply_text" not in body

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    assert messages_response.status_code == 200
    messages_payload = json.loads(messages_response.body)
    assert len(messages_payload["messages"]) == 2
    assert messages_payload["messages"][-1]["status"] == "completed"

    memory_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/memory",
    )
    assert memory_response.status_code == 200
    memory_payload = json.loads(memory_response.body)
    assert memory_payload["memory"]["session_id"] == session_id
