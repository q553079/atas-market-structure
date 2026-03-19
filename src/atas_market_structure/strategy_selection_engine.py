"""Strategy selection engine that maps observed events/reason_codes to strategy candidates.

Replaces the hardcoded 3-strategy matching in workbench_services with a data-driven
approach using strategy_index.json mappings. Also generates dynamic AI briefings
and supports environment-adaptive parameter hints.

Consumers: workbench_services (replay build), ai_review_services (chat/review prompts)
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atas_market_structure.regime_monitor_services import RegimeAssessment

from atas_market_structure.models import (
    ReplayAiBriefing,
    ReplayEventAnnotation,
    ReplayFocusRegion,
    ReplayStrategyCandidate,
)


class StrategySelectionEngine:
    """Data-driven strategy candidate selection from strategy_index.json."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[2]
        self._index_path = self._root_dir / "docs" / "strategy_library" / "strategy_index.json"
        self._index: dict[str, Any] | None = None

    def _load_index(self) -> dict[str, Any]:
        if self._index is not None:
            return self._index
        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        self._index = raw
        return raw

    def select_candidates(
        self,
        event_annotations: list[ReplayEventAnnotation],
        focus_regions: list[ReplayFocusRegion],
        *,
        instrument_symbol: str = "NQ",
        session_scope: str | None = None,
        regime_assessment: RegimeAssessment | None = None,
    ) -> list[ReplayStrategyCandidate]:
        """Select strategy candidates based on observed event_kinds and reason_codes.

        Flow: environment -> evidence -> candidate strategies -> suppression check -> ranked output
        """
        index = self._load_index()
        observed_event_kinds = {e.event_kind for e in event_annotations}
        observed_reason_codes: set[str] = set()
        for region in focus_regions:
            observed_reason_codes.update(region.reason_codes)

        event_map: dict[str, list[str]] = index.get("event_kind_strategy_map", {})
        reason_map: dict[str, list[str]] = index.get("reason_code_strategy_map", {})

        # Collect candidate strategy_ids from both maps
        candidate_ids_from_events: dict[str, set[str]] = {}  # strategy_id -> matched event_kinds
        candidate_ids_from_reasons: dict[str, set[str]] = {}  # strategy_id -> matched reason_codes

        for ek in observed_event_kinds:
            for sid in event_map.get(ek, []):
                candidate_ids_from_events.setdefault(sid, set()).add(ek)

        for rc in observed_reason_codes:
            for sid in reason_map.get(rc, []):
                candidate_ids_from_reasons.setdefault(sid, set()).add(rc)

        all_candidate_ids = set(candidate_ids_from_events) | set(candidate_ids_from_reasons)

        # Build strategy lookup
        strategies_by_id: dict[str, dict[str, Any]] = {}
        for s in index.get("strategies", []):
            strategies_by_id[s["strategy_id"]] = s

        # Check suppression: no-trade strategies get highest priority
        no_trade_ids = set()
        for sid in all_candidate_ids:
            entry = strategies_by_id.get(sid)
            if entry and "no_trade" in sid:
                no_trade_ids.add(sid)

        # Filter by instrument scope
        filtered: list[tuple[float, str, dict[str, Any], set[str], set[str]]] = []
        for sid in all_candidate_ids:
            entry = strategies_by_id.get(sid)
            if entry is None:
                continue
            scope = [x.upper() for x in entry.get("instrument_scope", [])]
            if scope and instrument_symbol.upper() not in scope and "ALL" not in scope:
                continue
            if session_scope:
                s_scope = entry.get("session_scope", [])
                if s_scope and session_scope not in s_scope and "cross_session" not in s_scope:
                    continue

            matched_events = candidate_ids_from_events.get(sid, set())
            matched_reasons = candidate_ids_from_reasons.get(sid, set())
            priority = entry.get("candidate_priority", 0.5)

            if regime_assessment is not None:
                priority = self._apply_regime_priority_adjustment(
                    strategy_id=sid,
                    priority=priority,
                    regime_assessment=regime_assessment,
                    matched_events=matched_events,
                    matched_reasons=matched_reasons,
                )

            # Boost priority if matched from both events AND reasons
            if matched_events and matched_reasons:
                priority = min(1.0, priority + 0.05)
            # No-trade strategies always surface first
            if sid in no_trade_ids:
                priority = min(1.0, priority + 0.1)

            filtered.append((priority, sid, entry, matched_events, matched_reasons))

        # Sort: no-trade first, then by priority descending
        filtered.sort(key=lambda x: (x[1] in no_trade_ids, x[0]), reverse=True)

        # Build event_id linkage
        event_id_by_kind: dict[str, list[str]] = {}
        for e in event_annotations:
            event_id_by_kind.setdefault(e.event_kind, []).append(e.event_id)

        candidates: list[ReplayStrategyCandidate] = []
        for priority, sid, entry, matched_events, matched_reasons in filtered[:15]:
            matched_event_ids: list[str] = []
            for ek in matched_events:
                matched_event_ids.extend(event_id_by_kind.get(ek, []))

            why: list[str] = []
            if matched_events:
                why.append(f"matched event_kinds: {', '.join(sorted(matched_events))}")
            if matched_reasons:
                why.append(f"matched reason_codes: {', '.join(sorted(matched_reasons))}")
            if sid in no_trade_ids:
                why.insert(0, "⚠ NO-TRADE suppressor active")

            candidates.append(ReplayStrategyCandidate(
                strategy_id=sid,
                title=entry.get("title", sid),
                source_path=entry.get("source_path", ""),
                matched_event_ids=matched_event_ids[:20],
                why_relevant=why,
            ))

        return candidates

    def _apply_regime_priority_adjustment(
        self,
        *,
        strategy_id: str,
        priority: float,
        regime_assessment: RegimeAssessment,
        matched_events: set[str],
        matched_reasons: set[str],
    ) -> float:
        sid = strategy_id.lower()
        regime = regime_assessment.regime
        volatility_state = regime_assessment.volatility_state

        if regime == "volatile" or volatility_state == "expanding":
            if any(token in sid for token in ("absorption", "boundary_fade", "fade", "reversal")):
                priority = max(0.0, priority - 0.2)
            if any(token in sid for token in ("initiative", "continuation", "post_harvest", "harvest", "pullback")):
                priority = min(1.0, priority + 0.12)
            if "initiative_drive" in matched_events or "post_harvest_response" in matched_events:
                priority = min(1.0, priority + 0.05)

        if regime in {"ranging", "quiet"} or volatility_state == "contracting":
            if any(token in sid for token in ("boundary_fade", "fade", "absorption", "mean_reversion", "reversal")):
                priority = min(1.0, priority + 0.12)
            if any(token in sid for token in ("initiative", "continuation", "breakout")):
                priority = max(0.0, priority - 0.08)
            if "same_price_replenishment" in matched_events or "significant_liquidity" in matched_events:
                priority = min(1.0, priority + 0.04)

        if matched_reasons and regime_assessment.directional_bias != "neutral":
            priority = min(1.0, priority + 0.02)
        return priority

    def build_dynamic_briefing(
        self,
        instrument_symbol: str,
        candidates: list[ReplayStrategyCandidate],
        focus_regions: list[ReplayFocusRegion],
        *,
        operator_entries_count: int = 0,
    ) -> ReplayAiBriefing | None:
        """Generate AI briefing dynamically from matched candidates and regions."""
        if not candidates and not focus_regions:
            return None

        # Identify no-trade suppressors
        no_trade_ids = [c for c in candidates if "no_trade" in c.strategy_id or "no-trade" in c.strategy_id]
        active_ids = [c for c in candidates if c not in no_trade_ids]

        # Build objective
        parts = [f"Review {instrument_symbol} replay window."]
        if no_trade_ids:
            parts.append(f"⚠ {len(no_trade_ids)} no-trade suppressor(s) active — evaluate first.")
        if active_ids:
            parts.append(f"{len(active_ids)} candidate strategies matched.")
        if focus_regions:
            parts.append(f"{len(focus_regions)} focus regions identified.")
        objective = " ".join(parts)

        # Build focus questions
        focus_questions: list[str] = [
            "Which no-trade conditions are currently active and why?",
            "Which focus regions are still defendable on revisit?",
        ]
        if operator_entries_count > 0:
            focus_questions.append("Are the operator's recorded entries aligned with the current structure?")
        if any("post_harvest" in c.strategy_id for c in candidates):
            focus_questions.append("Has the post-harvest response confirmed continuation or reversal?")
        if any("trapped" in c.strategy_id for c in candidates):
            focus_questions.append("Are any large orders currently trapped and likely to force exit?")
        if any("gap" in c.strategy_id for c in candidates):
            focus_questions.append("What is the gap fill status and does acceptance or rejection dominate?")

        # Required outputs
        required_outputs = [
            "no_trade_zones_and_reasons",
            "key_zones_ranked",
            "continuation_vs_reversal",
            "invalidation_levels",
        ]
        if operator_entries_count > 0:
            required_outputs.append("entry_reviews")

        # Notes
        notes: list[str] = []
        if no_trade_ids:
            notes.append(f"Suppressor strategies: {', '.join(c.strategy_id for c in no_trade_ids)}")
        top3 = active_ids[:3]
        if top3:
            notes.append(f"Top candidates: {', '.join(c.strategy_id for c in top3)}")

        return ReplayAiBriefing(
            objective=objective,
            focus_questions=focus_questions[:6],
            required_outputs=required_outputs,
            notes=notes,
        )
