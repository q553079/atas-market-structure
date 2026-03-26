from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from atas_market_structure.models import (
    MachineStrategyCard,
    MachineStrategyIndex,
    ReplayAiChatPreset,
    ReplayWorkbenchSnapshotPayload,
)


class StrategyLibraryService:
    """Loads machine-readable strategy cards and filters them for replay AI tasks."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2]
        self._strategy_dir = self._root_dir / "docs" / "strategy_library"
        self._index_path = self._strategy_dir / "strategy_index.json"
        self._fallback_index_path = self._strategy_dir / "strategy_index.template.json"

    def resolve_relevant_cards(
        self,
        payload: ReplayWorkbenchSnapshotPayload,
        *,
        preset: ReplayAiChatPreset,
    ) -> list[MachineStrategyCard]:
        index = self._load_index()
        candidate_ids = {item.strategy_id for item in payload.strategy_candidates}
        candidate_paths = {item.source_path for item in payload.strategy_candidates}
        matched_cards: list[MachineStrategyCard] = []
        seen_ids: set[str] = set()
        for entry in index.strategies:
            if entry.strategy_id not in candidate_ids and entry.source_path not in candidate_paths:
                continue
            if not self._matches_instrument(entry.instrument_scope, payload.instrument.symbol):
                continue
            if not self._matches_preset(entry.preferred_presets, preset):
                continue
            card = self._load_card(entry.machine_card_path)
            if card.strategy_id in seen_ids:
                continue
            matched_cards.append(card)
            seen_ids.add(card.strategy_id)
        matched_cards.sort(key=lambda item: item.machine_hints.candidate_priority, reverse=True)
        return matched_cards

    @staticmethod
    def compact_cards(cards: list[MachineStrategyCard]) -> list[dict[str, object]]:
        compacted: list[dict[str, object]] = []
        for item in cards:
            compacted.append(
                {
                    "strategy_id": item.strategy_id,
                    "title": item.title,
                    "summary": item.summary.model_dump(mode="json"),
                    "preferred_presets": item.preferred_presets,
                    "context_tags": item.context_tags,
                    "required_evidence": item.required_evidence,
                    "confirmation_signals": item.confirmation_signals,
                    "invalidation_signals": item.invalidation_signals,
                    "no_trade_conditions": item.no_trade_conditions,
                    "management_notes": item.management_notes,
                    "review_questions": item.review_questions,
                    "machine_hints": item.machine_hints.model_dump(mode="json"),
                }
            )
        return compacted

    def _load_index(self) -> MachineStrategyIndex:
        path = self._index_path if self._index_path.exists() else self._fallback_index_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "generated_at" not in payload:
            payload["generated_at"] = datetime.now(tz=UTC).isoformat()
        return MachineStrategyIndex.model_validate(payload)

    def _load_card(self, relative_path: str) -> MachineStrategyCard:
        normalized = Path(relative_path.replace("\\", "/"))
        path = self._root_dir / normalized
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MachineStrategyCard.model_validate(payload)

    @staticmethod
    def _matches_instrument(scope: list[str], symbol: str) -> bool:
        if not scope:
            return True
        normalized_scope = {item.upper() for item in scope}
        return "ALL" in normalized_scope or symbol.upper() in normalized_scope

    @staticmethod
    def _matches_preset(scope: list[str], preset: ReplayAiChatPreset) -> bool:
        if not scope:
            return True
        return preset.value in scope or ReplayAiChatPreset.GENERAL.value in scope
