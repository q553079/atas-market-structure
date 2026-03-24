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

def test_chat_handoff_summary_plus_recent_three_returns_latest_three_rounds() -> None:
    application, repository = build_application()

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "AI切换交接",
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

    prompts = [
        "第一轮：先记录开盘后的主观判断。",
        "第二轮：回踩支撑后还能继续做多吗？",
        "第三轮：如果跌破防守位要怎么处理？",
        "第四轮：现在只保留最新的执行结论。",
    ]
    for prompt in prompts:
        reply_response = application.dispatch(
            "POST",
            f"/api/v1/workbench/chat/sessions/{session_id}/reply",
            json.dumps(
                {
                    "replay_ingestion_id": None,
                    "preset": ReplayAiChatPreset.GENERAL.value,
                    "user_input": prompt,
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

    now = datetime.now(tz=UTC)
    repository.save_chat_message(
        message_id=f"msg-{uuid4().hex}",
        session_id=session_id,
        parent_message_id=None,
        role="system",
        content="系统提示：仅用于验证交接 recent 过滤。",
        status="completed",
        reply_title=None,
        stream_buffer="",
        model="system",
        annotations=[],
        plan_cards=[],
        mounted_to_chart=False,
        mounted_object_ids=[],
        is_key_conclusion=False,
        request_payload={},
        response_payload={},
        created_at=now,
        updated_at=now,
    )

    handoff_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/handoff",
        json.dumps(
            {
                "target_model": "fake-chat-handoff",
                "mode": "summary_plus_recent_3",
            }
        ).encode("utf-8"),
    )
    assert handoff_response.status_code == 200
    handoff_packet = json.loads(handoff_response.body)["handoff_packet"]

    assert handoff_packet["session_meta"]["target_model"] == "fake-chat-handoff"
    assert handoff_packet["memory_summary"]["session_id"] == session_id
    assert [item["role"] for item in handoff_packet["recent_messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    expected_recent_contents: list[str] = []
    for prompt in prompts[-3:]:
        expected_recent_contents.extend([prompt, f"Session-only 回复：{prompt}"])
    assert [item["content"] for item in handoff_packet["recent_messages"]] == expected_recent_contents

    question_only_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/handoff",
        json.dumps(
            {
                "target_model": "fake-chat-handoff",
                "mode": "question_only",
            }
        ).encode("utf-8"),
    )
    assert question_only_response.status_code == 200
    question_only_packet = json.loads(question_only_response.body)["handoff_packet"]
    assert question_only_packet["memory_summary"] == {}
    assert question_only_packet["recent_messages"] == []

def test_chat_session_event_timeline_prefers_structured_annotations_without_replay_snapshot() -> None:
    application, repository = build_application()

    create_session_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "事件整理会话",
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

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "replay_ingestion_id": None,
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "请整理当前窗口的关键计划、区域和风险。",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": True,
                "include_recent_messages": True,
                "analysis_type": "event_timeline",
                "analysis_range": "current_window",
                "analysis_style": "standard",
                "extra_context": {"analyst_latest_reply": "关注 21524 回踩是否守住。"},
                "model": "fake-chat-e2e",
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 200
    reply_payload = json.loads(reply_response.body)

    assert reply_payload["ok"] is True
    assert reply_payload["session_only"] is True
    assert len(reply_payload["annotations"]) == 3

    labels = {item["label"] for item in reply_payload["annotations"]}
    assert labels == {"结构化计划", "结构化支撑区", "结构化风险位"}

    annotations_by_label = {item["label"]: item for item in reply_payload["annotations"]}
    assert annotations_by_label["结构化计划"]["event_kind"] == "plan"
    assert annotations_by_label["结构化计划"]["type"] == "entry_line"
    assert annotations_by_label["结构化计划"]["entry_price"] == 21524.0
    assert annotations_by_label["结构化支撑区"]["event_kind"] == "zone"
    assert annotations_by_label["结构化支撑区"]["type"] == "support_zone"
    assert annotations_by_label["结构化支撑区"]["price_low"] == 21524.0
    assert annotations_by_label["结构化支撑区"]["price_high"] == 21528.0
    assert annotations_by_label["结构化风险位"]["event_kind"] == "risk"
    assert annotations_by_label["结构化风险位"]["type"] == "stop_loss"
    assert annotations_by_label["结构化风险位"]["stop_price"] == 21518.0

    stored_annotations = repository.list_chat_annotations(session_id=session_id)
    assert len(stored_annotations) == 3
