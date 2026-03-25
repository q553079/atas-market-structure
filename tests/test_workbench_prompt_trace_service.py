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

from atas_market_structure.models import ChatReplyRequest, ReplayAiChatAttachment, ReplayAiChatMessage
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_prompt_trace_service import ReplayWorkbenchPromptTraceService
from tests.test_chat_backend_support import TEST_DB_DIR


def _make_repository() -> SQLiteAnalysisRepository:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return repository


def _seed_session(repository: SQLiteAnalysisRepository) -> tuple[str, str]:
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    session_id = f"sess-{uuid4().hex}"
    block_id = f"pb-{uuid4().hex}"
    repository.save_chat_session(
        session_id=session_id,
        workspace_id="replay_main",
        title="Prompt Trace 测试",
        symbol="NQ",
        contract_id="NQM2026",
        timeframe="1m",
        window_range={"start": "2026-03-25T09:30:00Z", "end": "2026-03-25T10:30:00Z"},
        active_model="fake-chat-e2e",
        status="active",
        draft_text="",
        draft_attachments=[],
        selected_prompt_block_ids=[],
        pinned_context_block_ids=[],
        include_memory_summary=True,
        include_recent_messages=True,
        mounted_reply_ids=[],
        active_plan_id=None,
        memory_summary_id=None,
        unread_count=0,
        scroll_offset=0,
        pinned=False,
        created_at=now,
        updated_at=now,
    )
    repository.save_prompt_block(
        block_id=block_id,
        session_id=session_id,
        symbol="NQ",
        contract_id="NQM2026",
        timeframe="1m",
        kind="candles_20",
        title="最近 20 根 K 线",
        preview_text="最近 20 根 K 线与结构摘要。",
        full_payload={
            "bars": [
                {
                    "started_at": "2026-03-25T09:30:00Z",
                    "ended_at": "2026-03-25T09:31:00Z",
                    "open": 21520.0,
                    "high": 21525.0,
                    "low": 21518.0,
                    "close": 21524.0,
                },
                {
                    "started_at": "2026-03-25T09:31:00Z",
                    "ended_at": "2026-03-25T09:32:00Z",
                    "open": 21524.0,
                    "high": 21529.0,
                    "low": 21522.0,
                    "close": 21528.0,
                },
            ]
        },
        selected_by_default=True,
        pinned=False,
        ephemeral=True,
        created_at=now,
        expires_at=None,
    )
    repository.save_or_update_session_memory(
        memory_summary_id=f"mem-{uuid4().hex}",
        session_id=session_id,
        summary_version=1,
        active_model="fake-chat-e2e",
        symbol="NQ",
        contract_id="NQM2026",
        timeframe="1m",
        window_range={"start": "2026-03-25T09:30:00Z", "end": "2026-03-25T10:30:00Z"},
        user_goal_summary="等待回踩后评估做多延续。",
        market_context_summary="当前更像延续结构。",
        key_zones_summary=["21524-21528 支撑"],
        active_plans_summary=["回踩做多"],
        invalidated_plans_summary=[],
        important_messages=[],
        current_user_intent="确认是否还能继续做多。",
        latest_question="如果这里回踩，还能不能继续做多？",
        latest_answer_summary="优先等回踩确认。",
        selected_annotations=[],
        last_updated_at=now,
    )
    return session_id, block_id


def test_prompt_trace_service_builds_summary_snapshot_and_finalizes_links() -> None:
    repository = _make_repository()
    session_id, block_id = _seed_session(repository)
    service = ReplayWorkbenchPromptTraceService(repository=repository)
    session = repository.get_chat_session(session_id)
    assert session is not None

    request = ChatReplyRequest(
        user_input="如果这里回踩，还能不能继续做多？",
        selected_block_ids=[block_id],
        pinned_block_ids=[],
        include_memory_summary=True,
        include_recent_messages=True,
        model="fake-chat-e2e",
        preset="recent_20_bars",
        analysis_type="structure",
        analysis_range="current_window",
        analysis_style="standard",
        extra_context={"manual_reason": "关注 21524 回踩", "selected_price": 21524.0},
        attachments=[
            ReplayAiChatAttachment(
                name="chart-snap.png",
                media_type="image/png",
                data_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9K2X0NwAAAABJRU5ErkJggg==",
            )
        ],
    )
    trace = service.create_prompt_trace(
        session=session,
        message_id="msg-trace-test",
        replay_ingestion_id=None,
        request=request,
        history=[
            ReplayAiChatMessage(role="user", content="上一轮关注哪里不能追？"),
            ReplayAiChatMessage(role="assistant", content="上一轮结论是等回踩确认。"),
        ],
        model_user_input="如果这里回踩，还能不能继续做多？",
    )

    assert trace.session_id == session_id
    assert trace.message_id == "msg-trace-test"
    assert trace.selected_block_ids == [block_id]
    assert trace.bar_window_summary["selected_bar_count"] == 2
    assert trace.manual_selection_summary["extra_context_keys"] == ["manual_reason", "selected_price"]
    assert trace.memory_summary["include_memory_summary"] is True
    assert trace.memory_summary["include_recent_messages"] is True
    assert trace.memory_summary["session_memory"]["market_context_summary"] == "当前更像延续结构。"
    assert trace.model_input_hash
    assert "data:image" not in json.dumps(trace.snapshot, ensure_ascii=False)
    assert trace.metadata["attachment_summaries"]

    finalized = service.finalize_prompt_trace(
        trace.prompt_trace_id,
        model_name="fake-chat-e2e-resolved",
        attached_event_ids=["evt-1", "evt-2"],
    )
    assert finalized is not None
    assert finalized.model_name == "fake-chat-e2e-resolved"
    assert finalized.attached_event_ids == ["evt-1", "evt-2"]
    assert finalized.metadata["attached_event_count"] == 2

    fetched = service.get_prompt_trace_by_message("msg-trace-test")
    assert fetched.trace.prompt_trace_id == trace.prompt_trace_id
    assert fetched.trace.prompt_block_summaries[0].kind == "candles_20"
    assert fetched.trace.attached_event_ids == ["evt-1", "evt-2"]
