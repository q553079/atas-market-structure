from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.ai_review_services import ReplayAiChatService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ReplayAiChatContent, ReplayAiChatPreset
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
        model_override: str | None = None,
    ):
        model_name = model_override or "fake-chat-e2e"
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
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 200
    reply_payload = json.loads(reply_response.body)

    assert reply_payload["ok"] is True
    assert reply_payload["session"]["session_id"] == session_id
    assert reply_payload["user_message"]["role"] == "user"
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
                "attachments": [],
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
    assert "做多" in regenerate_payload["reply_text"]

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    messages_payload = json.loads(messages_response.body)
    assert len(messages_payload["messages"]) == 4

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
