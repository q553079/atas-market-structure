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

def test_chat_session_reply_flow_persists_session_objects_and_memory() -> None:
    application, repository = build_application()

    snapshot_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    assert snapshot_response.status_code == 201
    snapshot_payload = json.loads(snapshot_response.body)
    replay_ingestion_id = snapshot_payload["ingestion_id"]

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "回踩做多",
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
    assert create_session_response.status_code == 201
    session_payload = json.loads(create_session_response.body)
    session_id = session_payload["session"]["session_id"]

    prompt_blocks_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/prompt-blocks/build",
        json.dumps({"candidates": ["candles_20", "event_summary", "recent_messages"]}).encode("utf-8"),
    )
    assert prompt_blocks_response.status_code == 200
    prompt_blocks_payload = json.loads(prompt_blocks_response.body)
    assert len(prompt_blocks_payload["blocks"]) == 3

    screenshot_attachment = {
        "name": "chart-snap.png",
        "media_type": "image/png",
        "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9K2X0NwAAAABJRU5ErkJggg==",
    }

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": replay_ingestion_id,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "如果这里回踩，还能不能继续做多？",
                "selected_block_ids": [prompt_blocks_payload["blocks"][0]["block_id"]],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": True,
                "model": "fake-chat-e2e",
                "attachments": [screenshot_attachment],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 200
    reply_payload = json.loads(reply_response.body)

    assert reply_payload["ok"] is True
    assert reply_payload["session"]["session_id"] == session_id
    assert reply_payload["user_message"]["role"] == "user"
    assert reply_payload["user_message"]["attachments"] == [screenshot_attachment]
    assert reply_payload["assistant_message"]["role"] == "assistant"
    assert reply_payload["assistant_message"]["status"] == "completed"
    assert reply_payload["assistant_message"]["prompt_trace_id"]
    assert "做多" in reply_payload["reply_text"]
    assert len(reply_payload["plan_cards"]) >= 1
    assert len(reply_payload["annotations"]) >= 1
    assert len(reply_payload["assistant_message"]["annotations"]) >= 1
    assert len(reply_payload["assistant_message"]["plan_cards"]) >= 1
    assert reply_payload["memory"]["session_id"] == session_id
    assert reply_payload["memory"]["latest_question"] == "如果这里回踩，还能不能继续做多？"

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    assert messages_response.status_code == 200
    messages_payload = json.loads(messages_response.body)
    assert len(messages_payload["messages"]) == 2
    assert messages_payload["messages"][0]["attachments"] == [screenshot_attachment]

    memory_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/memory",
    )
    assert memory_response.status_code == 200
    memory_payload = json.loads(memory_response.body)
    assert memory_payload["memory"]["session_id"] == session_id

    assistant_message_id = reply_payload["assistant_message"]["message_id"]
    objects_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages/{assistant_message_id}/objects",
    )
    assert objects_response.status_code == 200
    objects_payload = json.loads(objects_response.body)
    assert len(objects_payload["plan_cards"]) >= 1
    assert len(objects_payload["annotations"]) >= 1

    stored_session = repository.get_chat_session(session_id)
    assert stored_session is not None
    stored_memory = repository.get_session_memory(session_id)
    assert stored_memory is not None
    stored_messages = repository.list_chat_messages(session_id=session_id)
    assert len(stored_messages) == 2
    stored_annotations = repository.list_chat_annotations(session_id=session_id)
    assert len(stored_annotations) >= 1
    stored_plans = repository.list_chat_plan_cards(session_id=session_id)
    assert len(stored_plans) >= 1
    stored_event_candidates = repository.list_event_candidates_by_session(session_id=session_id)
    stored_event_stream = repository.list_event_stream_entries(session_id=session_id)
    stored_event_memory = repository.list_event_memory_entries(session_id=session_id)
    stored_prompt_trace = repository.get_prompt_trace(reply_payload["assistant_message"]["prompt_trace_id"])
    assert len(stored_event_candidates) >= 2
    assert len(stored_event_stream) >= len(stored_event_candidates)
    assert len(stored_event_memory) >= len(stored_event_candidates)
    assert len(stored_messages[-1].response_payload.get("event_candidate_ids", [])) >= 2
    assert stored_prompt_trace is not None
    assert stored_prompt_trace.message_id == assistant_message_id
    assert stored_prompt_trace.attached_event_ids
    assert all(item.source_prompt_trace_id == stored_prompt_trace.prompt_trace_id for item in stored_event_candidates)

def test_chat_session_reply_flow_works_without_replay_snapshot() -> None:
    application, repository = build_application()

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "无图表聊天",
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
    assert create_session_response.status_code == 201
    session_id = json.loads(create_session_response.body)["session"]["session_id"]

    prompt_blocks_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/prompt-blocks/build",
        json.dumps({"candidates": ["session_summary", "recent_messages"]}).encode("utf-8"),
    )
    assert prompt_blocks_response.status_code == 200
    prompt_blocks_payload = json.loads(prompt_blocks_response.body)
    assert len(prompt_blocks_payload["blocks"]) == 2

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": None,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "还没加载图表，先帮我整理一下当前思路。",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": True,
                "include_recent_messages": True,
                "model": "fake-chat-e2e",
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 200
    reply_payload = json.loads(reply_response.body)

    assert reply_payload["ok"] is True
    assert reply_payload["session_only"] is True
    assert reply_payload["live_context_summary"] == []
    assert reply_payload["referenced_strategy_ids"] == []
    assert reply_payload["plan_cards"] == []
    assert reply_payload["annotations"] == []
    assert reply_payload["assistant_message"]["status"] == "completed"
    assert reply_payload["assistant_message"]["prompt_trace_id"]
    assert reply_payload["memory"]["latest_question"] == "还没加载图表，先帮我整理一下当前思路。"

    stored_messages = repository.list_chat_messages(session_id=session_id)
    assert len(stored_messages) == 2
    stored_memory = repository.get_session_memory(session_id)
    assert stored_memory is not None
    stored_trace = repository.get_prompt_trace(reply_payload["assistant_message"]["prompt_trace_id"])
    assert stored_trace is not None
    assert stored_trace.message_id == reply_payload["assistant_message"]["message_id"]
