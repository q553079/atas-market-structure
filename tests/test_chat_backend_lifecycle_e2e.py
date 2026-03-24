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

def test_chat_regenerate_creates_new_assistant_message() -> None:
    application, repository = build_application()

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
                "title": "Regenerate测试",
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

    screenshot_attachment = {
        "name": "regenerate-chart.png",
        "media_type": "image/png",
        "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9K2X0NwAAAABJRU5ErkJggg==",
    }

    initial_reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": replay_ingestion_id,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "如果这里回踩，还能不能继续做多？",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": True,
                "model": "fake-chat-e2e",
                "attachments": [screenshot_attachment],
            }
        ).encode("utf-8"),
    )
    initial_payload = json.loads(initial_reply_response.body)
    original_assistant_message_id = initial_payload["assistant_message"]["message_id"]

    regenerate_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages/{original_assistant_message_id}/regenerate",
        b"{}",
    )
    assert regenerate_response.status_code == 200
    regenerate_payload = json.loads(regenerate_response.body)

    assert regenerate_payload["assistant_message"]["role"] == "assistant"
    assert regenerate_payload["assistant_message"]["message_id"] != original_assistant_message_id
    assert regenerate_payload["assistant_message"]["status"] == "completed"
    assert regenerate_payload["user_message"]["attachments"] == [screenshot_attachment]
    assert "做多" in regenerate_payload["reply_text"]

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    messages_payload = json.loads(messages_response.body)
    assert len(messages_payload["messages"]) == 4
    assert messages_payload["messages"][0]["attachments"] == [screenshot_attachment]
    assert messages_payload["messages"][2]["attachments"] == [screenshot_attachment]

    memory_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/memory",
    )
    memory_payload = json.loads(memory_response.body)
    assert memory_payload["memory"]["session_id"] == session_id

def test_chat_lifecycle_evaluate_returns_transitions() -> None:
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
                "title": "Lifecycle测试",
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

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": replay_ingestion_id,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "如果这里回踩，还能不能继续做多？",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": True,
                "model": "fake-chat-e2e",
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    reply_payload = json.loads(reply_response.body)
    object_ids = [item["plan_id"] for item in reply_payload["plan_cards"] if item.get("plan_id")]

    lifecycle_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/lifecycle/evaluate",
        json.dumps(
            {
                "bars": [{"close": 21524.0}],
                "live_tail": None,
                "object_ids": object_ids,
            }
        ).encode("utf-8"),
    )
    assert lifecycle_response.status_code == 200
    lifecycle_payload = json.loads(lifecycle_response.body)
    assert lifecycle_payload["ok"] is True
    assert isinstance(lifecycle_payload["transitions"], list)
