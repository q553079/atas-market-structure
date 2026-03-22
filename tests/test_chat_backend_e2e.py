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

from atas_market_structure.ai_review_services import ReplayAiChatService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ReplayAiChatContent, ReplayAiChatPreset
from atas_market_structure.models._replay import ReplayAiChatAnnotationCandidate
from atas_market_structure.repository import SQLiteAnalysisRepository


FIXTURE_DIR = ROOT_DIR / "samples"
TEST_DB_DIR = ROOT_DIR / "data" / "test-runs"


class FakeReplayChatAssistant:
    def generate_reply(
        self,
        payload,
        *,
        strategy_cards,
        operator_entries,
        manual_regions,
        live_context_messages,
        attachments=None,
        preset,
        user_message: str,
        history,
        model_override: str | None = None,
    ):
        model_name = model_override or "fake-chat-e2e"
        return (
            "fake-openai",
            model_name,
            ReplayAiChatContent(
                reply_text=(
                    f"问题：{user_message}\n"
                    "计划：做多，入场 21524，止损 21518，TP1 21530，TP2 21536。"
                ),
                live_context_summary=[f"live_messages={len(live_context_messages)}"],
                referenced_strategy_ids=[item.strategy_id for item in strategy_cards[:1]],
                follow_up_suggestions=["等待回踩确认后再评估是否继续追踪。"],
            ),
        )

    def generate_session_reply(
        self,
        *,
        user_message: str,
        history,
        attachments=None,
        enable_structured_outputs: bool = False,
        model_override: str | None = None,
    ):
        model_name = model_override or "fake-chat-e2e"
        if enable_structured_outputs:
            return (
                "fake-openai",
                model_name,
                ReplayAiChatContent(
                    reply_text=(
                        f"Session-only 结构化回复：{user_message}\n"
                        "文本噪音：22000-22005 与 22123 仅作旧案例说明，不应作为当前事件候选。"
                    ),
                    live_context_summary=[],
                    referenced_strategy_ids=[],
                    follow_up_suggestions=["优先采用结构化事件，不要重复从正文再提取。"],
                    plan_cards=[],
                    annotations=[
                        ReplayAiChatAnnotationCandidate(
                            type="plan",
                            label="结构化计划",
                            reason="若回踩 21524 并守住，可考虑做多。",
                            entry_price=21524.0,
                            side="buy",
                        ),
                        ReplayAiChatAnnotationCandidate(
                            type="price_zone",
                            label="结构化支撑区",
                            reason="21524-21528 是本轮回踩防守区。",
                            price_low=21524.0,
                            price_high=21528.0,
                            side="buy",
                        ),
                        ReplayAiChatAnnotationCandidate(
                            type="risk_note",
                            label="结构化风险位",
                            reason="跌破 21518 则本轮回踩脚本失效。",
                            stop_price=21518.0,
                        ),
                    ],
                ),
            )
        return (
            "fake-openai",
            model_name,
            ReplayAiChatContent(
                reply_text=f"Session-only 回复：{user_message}",
                live_context_summary=[],
                referenced_strategy_ids=[],
                follow_up_suggestions=["如需图表分析，请先加载回放图表。"],
                plan_cards=[],
                annotations=[],
            ),
        )


def load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def build_application() -> tuple[MarketStructureApplication, SQLiteAnalysisRepository]:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    replay_ai_chat_service = ReplayAiChatService(repository=repository, assistant=FakeReplayChatAssistant())
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_chat_service=replay_ai_chat_service,
    )
    return application, repository


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
    assert "做多" in reply_payload["reply_text"]
    assert len(reply_payload["plan_cards"]) >= 1
    assert len(reply_payload["annotations"]) >= 1
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
    assert reply_payload["memory"]["latest_question"] == "还没加载图表，先帮我整理一下当前思路。"

    stored_messages = repository.list_chat_messages(session_id=session_id)
    assert len(stored_messages) == 2
    stored_memory = repository.get_session_memory(session_id)
    assert stored_memory is not None


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
