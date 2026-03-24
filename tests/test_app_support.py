from __future__ import annotations


import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiChatService, ReplayAiReviewService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ChartCandle,
    ReplayAiChatContent,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiInvalidationReview,
    ReplayAiEntryReview,
    ReplayAiReviewContent,
    ReplayAiReviewRequest,
    ReplayAiScriptReview,
    ReplayAiZoneReview,
    ReplayWorkbenchBuildRequest,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import ApplicationRequestHandler
from atas_market_structure.strategy_library_services import StrategyLibraryService

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "samples"

TEST_DB_DIR = Path(__file__).resolve().parents[1] / "data" / "test-runs"

class FakeReplayReviewer:
    def generate_review(self, payload, *, operator_entries, manual_regions, model_override: str | None = None):
        model_name = model_override or "fake-gpt-test"
        return (
            "fake-openai",
            model_name,
            ReplayAiReviewContent(
                narrative_summary="Replay shows defended support and a continuation bias into upper liquidity.",
                key_zones=[
                    ReplayAiZoneReview(
                        label="Europe defended bid",
                        zone_low=payload.focus_regions[0].price_low if payload.focus_regions else 21500.0,
                        zone_high=payload.focus_regions[0].price_high if payload.focus_regions else 21504.0,
                        role="support",
                        strength_score=0.82,
                        evidence=["same_price_replenishment", "initiative_drive_follow_through"],
                    ),
                ],
                script_review=ReplayAiScriptReview(
                    preferred_script="continuation",
                    continuation_case=["initiative drive is still active"],
                    reversal_case=["upper liquidity has not failed yet"],
                    preferred_rationale=["defended bid and higher-lows sequence remain intact"],
                ),
                entry_reviews=[
                    ReplayAiEntryReview(
                        entry_id=(operator_entries[0].entry_id if operator_entries else "entry-none"),
                        verdict="valid" if operator_entries else "not_reviewed",
                        context_alignment_score=0.76 if operator_entries else 0.0,
                        rationale=["entry aligned with defended support"] if operator_entries else [],
                        mistakes=["entry was slightly early"] if operator_entries else [],
                        better_conditions=["wait for one more confirming higher low"] if operator_entries else [],
                    )
                ] if operator_entries else [],
                invalidations=[
                    ReplayAiInvalidationReview(
                        label="Defended bid fails",
                        price=payload.focus_regions[0].price_low if payload.focus_regions else 21500.0,
                        reason="Loss of the defended bid breaks the continuation case.",
                    )
                ],
                no_trade_guidance=["Do not open inside the middle of the balance without fresh initiative."],
                unresolved_conflicts=["Need to confirm whether upper liquidity absorbs or releases."],
                operator_focus=["Watch the first retest of the defended bid."],
            ),
        )

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
        model_name = model_override or "fake-chat-test"
        live_summary = [
            f"live_messages={len(live_context_messages)}",
            f"strategy_cards={len(strategy_cards)}",
            f"operator_entries={len(operator_entries)}",
            f"manual_regions={len(manual_regions)}",
        ]
        referenced_strategy_ids = [item.strategy_id for item in strategy_cards[:2]]
        return (
            "fake-openai",
            model_name,
            ReplayAiChatContent(
                reply_text=f"preset={preset.value}; user={user_message}",
                live_context_summary=live_summary,
                referenced_strategy_ids=referenced_strategy_ids,
                follow_up_suggestions=[
                    "确认当前 focus region 是否已经被消耗。",
                    "检查大单是否仍在原价位连续补单。",
                ],
            ),
        )

def build_application(
    *,
    replay_ai_review_service: ReplayAiReviewService | None = None,
    replay_ai_chat_service: ReplayAiChatService | None = None,
) -> MarketStructureApplication:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return MarketStructureApplication(
        repository=repository,
        replay_ai_review_service=replay_ai_review_service,
        replay_ai_chat_service=replay_ai_chat_service,
    )

def load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()

def load_json_fixture(name: str) -> dict[str, object]:
    return json.loads(load_fixture(name))
