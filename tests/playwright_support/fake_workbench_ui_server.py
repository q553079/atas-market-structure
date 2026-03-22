from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.ai_review_services import ReplayAiChatService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import ReplayAiChatContent
from atas_market_structure.models._replay import ReplayAiChatAnnotationCandidate
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import ApplicationRequestHandler


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
        model_name = model_override or "fake-ui-chat"
        return (
            "fake-openai",
            model_name,
            ReplayAiChatContent(
                reply_text=f"常规回复：{user_message}",
                live_context_summary=[],
                referenced_strategy_ids=[],
                follow_up_suggestions=[],
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
        model_name = model_override or "fake-ui-chat"
        if enable_structured_outputs:
            return (
                "fake-openai",
                model_name,
                ReplayAiChatContent(
                    reply_text=(
                        f"结构化事件整理：{user_message}\n"
                        "文本噪音：22000-22005 与 22123 只用于历史案例说明，不应进入当前候选。"
                    ),
                    live_context_summary=[],
                    referenced_strategy_ids=[],
                    follow_up_suggestions=["优先采用结构化结果。"],
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
                follow_up_suggestions=[],
                plan_cards=[],
                annotations=[],
            ),
        )


def main() -> None:
    db_dir = ROOT_DIR / "data" / "test-runs"
    db_dir.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=db_dir / f"ui-playwright-{uuid4().hex}.db")
    repository.initialize()
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_chat_service=ReplayAiChatService(
            repository=repository,
            assistant=FakeReplayChatAssistant(),
        ),
    )
    ApplicationRequestHandler.application = application
    port = int(os.getenv("UI_TEST_PORT", "18080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), ApplicationRequestHandler)
    print(f"fake-workbench-ui-server listening on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
