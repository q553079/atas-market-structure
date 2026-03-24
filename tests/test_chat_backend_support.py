from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiChatService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ReplayAiChatContent
from atas_market_structure.models._replay import ReplayAiChatAnnotationCandidate
from atas_market_structure.repository import SQLiteAnalysisRepository

ROOT_DIR = Path(__file__).resolve().parents[1]

SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

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
