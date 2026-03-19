"""Analysis orchestration: lightweight monitoring, full-market analysis, and deep region analysis.

Three-tier cost model:
1. Lightweight periodic monitor — runs every few minutes, no LLM call, pure local logic
2. Full-market analysis — human-triggered, medium-cost LLM call
3. Deep region analysis — human-triggered on specific regions, focused high-value LLM call

Consumers: app.py routes (new endpoints), workbench UI buttons
Does NOT modify: models.py, existing replay/workbench routes, ATAS collector
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    ReplayOperatorEntryRecord,
    ReplayManualRegionAnnotationRecord,
    ReplayStrategyCandidate,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.position_health_services import PositionHealthEvaluator, PositionHealthResult
from atas_market_structure.regime_monitor_services import RegimeMonitor, RegimeAssessment
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine


# ---------------------------------------------------------------------------
# Shared result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LightweightMonitorResult:
    """Low-cost periodic monitor output — no LLM, pure local logic."""
    monitor_id: str
    generated_at: datetime
    instrument_symbol: str
    regime: RegimeAssessment
    position_health: PositionHealthResult
    no_trade_active: bool
    suppressor_ids: list[str]
    new_focus_region_count: int
    should_trigger_deep_analysis: bool
    trigger_reasons: list[str]
    strategy_candidate_count: int
    top_strategy_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "generated_at": self.generated_at.isoformat(),
            "instrument_symbol": self.instrument_symbol,
            "regime": self.regime.to_dict(),
            "position_health": self.position_health.to_dict(),
            "no_trade_active": self.no_trade_active,
            "suppressor_ids": self.suppressor_ids,
            "new_focus_region_count": self.new_focus_region_count,
            "should_trigger_deep_analysis": self.should_trigger_deep_analysis,
            "trigger_reasons": self.trigger_reasons,
            "strategy_candidate_count": self.strategy_candidate_count,
            "top_strategy_ids": self.top_strategy_ids,
        }


@dataclass
class FullMarketAnalysisResult:
    """Human-triggered full-market analysis — medium-cost."""
    analysis_id: str
    generated_at: datetime
    data_window_start: datetime
    data_window_end: datetime
    instrument_symbol: str
    regime: RegimeAssessment
    position_health: PositionHealthResult
    no_trade_active: bool
    suppressor_ids: list[str]
    strategy_candidates: list[dict[str, Any]]
    focus_regions_summary: list[dict[str, Any]]
    risk_alerts: list[str]
    ai_briefing_objective: str
    ai_briefing_focus_questions: list[str]
    environment_summary: str
    actionable_summary: str
    confidence: float
    context_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "generated_at": self.generated_at.isoformat(),
            "data_window_start": self.data_window_start.isoformat(),
            "data_window_end": self.data_window_end.isoformat(),
            "instrument_symbol": self.instrument_symbol,
            "regime": self.regime.to_dict(),
            "position_health": self.position_health.to_dict(),
            "no_trade_active": self.no_trade_active,
            "suppressor_ids": self.suppressor_ids,
            "strategy_candidates": self.strategy_candidates,
            "focus_regions_summary": self.focus_regions_summary,
            "risk_alerts": self.risk_alerts,
            "ai_briefing_objective": self.ai_briefing_objective,
            "ai_briefing_focus_questions": self.ai_briefing_focus_questions,
            "environment_summary": self.environment_summary,
            "actionable_summary": self.actionable_summary,
            "confidence": round(self.confidence, 2),
            "context_used": self.context_used,
        }


@dataclass
class DeepRegionAnalysisResult:
    """Deep analysis of a specific region — focused high-value output."""
    analysis_id: str
    region_id: str
    generated_at: datetime
    source_type: str  # "manual_marked" | "ai_suggested" | "web_box_select" | "atas_screenshot"
    instrument_symbol: str
    timeframe: str
    session: str | None
    time_range_start: datetime
    time_range_end: datetime
    price_range_low: float
    price_range_high: float
    # What happened
    event_chain: list[dict[str, Any]]
    derived_event_kinds: list[str]
    derived_reason_codes: list[str]
    # Strategy mapping
    strategy_candidates: list[dict[str, Any]]
    no_trade_flags: list[str]
    # Evidence
    required_evidence_seen: list[str]
    required_evidence_missing: list[str]
    invalidation_seen: list[str]
    # Position health impact
    position_health_flags: list[str]
    # Outputs
    region_verdict: str  # "continuation" | "trap" | "control_handoff" | "inventory_release" | "no_trade" | "ambiguous"
    ai_summary_short: str
    confidence: float
    provenance: list[str]  # "market_data" | "ai_inference" | "human_annotation" | "image"
    review_status: str  # "pending" | "confirmed" | "rejected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "region_id": self.region_id,
            "generated_at": self.generated_at.isoformat(),
            "source_type": self.source_type,
            "instrument_symbol": self.instrument_symbol,
            "timeframe": self.timeframe,
            "session": self.session,
            "time_range_start": self.time_range_start.isoformat(),
            "time_range_end": self.time_range_end.isoformat(),
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "event_chain": self.event_chain,
            "derived_event_kinds": self.derived_event_kinds,
            "derived_reason_codes": self.derived_reason_codes,
            "strategy_candidates": self.strategy_candidates,
            "no_trade_flags": self.no_trade_flags,
            "required_evidence_seen": self.required_evidence_seen,
            "required_evidence_missing": self.required_evidence_missing,
            "invalidation_seen": self.invalidation_seen,
            "position_health_flags": self.position_health_flags,
            "region_verdict": self.region_verdict,
            "ai_summary_short": self.ai_summary_short,
            "confidence": round(self.confidence, 2),
            "provenance": self.provenance,
            "review_status": self.review_status,
        }


# ---------------------------------------------------------------------------
# Tier 1: Lightweight periodic monitor (no LLM, pure local)
# ---------------------------------------------------------------------------

class LightweightMonitorService:
    """Runs every few minutes. Zero LLM cost. Pure local logic."""

    def __init__(self, strategy_engine: StrategySelectionEngine | None = None) -> None:
        self._regime_monitor = RegimeMonitor()
        self._health_evaluator = PositionHealthEvaluator()
        self._strategy_engine = strategy_engine or StrategySelectionEngine()

    def run(
        self,
        snapshot: ReplayWorkbenchSnapshotPayload,
        entries: list[ReplayOperatorEntryRecord],
        *,
        previous_focus_region_count: int = 0,
    ) -> LightweightMonitorResult:
        now = datetime.now(tz=UTC)
        regime = self._regime_monitor.assess(snapshot)
        candidates = self._strategy_engine.select_candidates(
            snapshot.event_annotations,
            snapshot.focus_regions,
            instrument_symbol=snapshot.instrument.symbol,
            regime_assessment=regime,
        )
        health = self._health_evaluator.evaluate(snapshot, entries, strategy_candidates=candidates)

        suppressor_ids = [c.strategy_id for c in candidates if "no_trade" in c.strategy_id or "no-trade" in c.strategy_id]
        no_trade_active = len(suppressor_ids) > 0
        new_focus = len(snapshot.focus_regions) - previous_focus_region_count

        # Decide if deep analysis should be triggered
        trigger_reasons: list[str] = []
        if health.health_state in ("unhealthy", "critical"):
            trigger_reasons.append(f"position_health={health.health_state}")
        if regime.regime == "volatile" and regime.confidence > 0.7:
            trigger_reasons.append("high_confidence_volatile_regime")
        if no_trade_active:
            trigger_reasons.append("no_trade_suppressor_active")
        if new_focus > 2:
            trigger_reasons.append(f"new_focus_regions={new_focus}")

        return LightweightMonitorResult(
            monitor_id=f"mon-{uuid4().hex[:12]}",
            generated_at=now,
            instrument_symbol=snapshot.instrument.symbol,
            regime=regime,
            position_health=health,
            no_trade_active=no_trade_active,
            suppressor_ids=suppressor_ids,
            new_focus_region_count=max(0, new_focus),
            should_trigger_deep_analysis=len(trigger_reasons) > 0,
            trigger_reasons=trigger_reasons,
            strategy_candidate_count=len(candidates),
            top_strategy_ids=[c.strategy_id for c in candidates[:5]],
        )


# ---------------------------------------------------------------------------
# Tier 2: Full-market analysis (human-triggered, medium cost)
# ---------------------------------------------------------------------------

class FullMarketAnalysisService:
    """Human-triggered full-market analysis. Produces structured + human-readable output."""

    def __init__(self, strategy_engine: StrategySelectionEngine | None = None) -> None:
        self._regime_monitor = RegimeMonitor()
        self._health_evaluator = PositionHealthEvaluator()
        self._strategy_engine = strategy_engine or StrategySelectionEngine()

    def analyze(
        self,
        snapshot: ReplayWorkbenchSnapshotPayload,
        entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord] | None = None,
    ) -> FullMarketAnalysisResult:
        now = datetime.now(tz=UTC)
        regime = self._regime_monitor.assess(snapshot)
        candidates = self._strategy_engine.select_candidates(
            snapshot.event_annotations,
            snapshot.focus_regions,
            instrument_symbol=snapshot.instrument.symbol,
            regime_assessment=regime,
        )
        health = self._health_evaluator.evaluate(snapshot, entries, strategy_candidates=candidates)
        briefing = self._strategy_engine.build_dynamic_briefing(
            snapshot.instrument.symbol, candidates, snapshot.focus_regions,
            operator_entries_count=len(entries),
        )

        suppressor_ids = [c.strategy_id for c in candidates if "no_trade" in c.strategy_id or "no-trade" in c.strategy_id]
        active_ids = [c for c in candidates if c.strategy_id not in set(suppressor_ids)]

        # Risk alerts
        risk_alerts: list[str] = []
        if suppressor_ids:
            risk_alerts.append(f"⚠ {len(suppressor_ids)} no-trade suppressor(s) active: {', '.join(suppressor_ids)}")
        if health.health_state in ("unhealthy", "critical"):
            risk_alerts.append(f"⚠ Position health: {health.health_state} (score={health.health_score:.2f})")
        if regime.volatility_state == "expanding":
            risk_alerts.append("⚠ Volatility expanding — tighten stops or reduce size.")
        if health.urgent_action_hint:
            risk_alerts.append(health.urgent_action_hint)

        # Focus regions summary
        focus_summary = [
            {
                "region_id": r.region_id,
                "label": r.label,
                "price_low": r.price_low,
                "price_high": r.price_high,
                "priority": r.priority,
                "reason_codes": r.reason_codes,
            }
            for r in sorted(snapshot.focus_regions, key=lambda x: x.priority, reverse=True)[:8]
        ]

        # Strategy candidates summary
        strat_summary = [
            {
                "strategy_id": c.strategy_id,
                "title": c.title,
                "why_relevant": c.why_relevant,
                "is_suppressor": c.strategy_id in set(suppressor_ids),
            }
            for c in candidates[:10]
        ]

        # Environment summary (short, actionable)
        env_parts = [
            f"Regime: {regime.regime} (confidence={regime.confidence:.0%})",
            f"Bias: {regime.directional_bias}",
            f"Volatility: {regime.volatility_state}",
        ]
        if suppressor_ids:
            env_parts.append(f"NO-TRADE active: {', '.join(suppressor_ids)}")
        environment_summary = " | ".join(env_parts)

        # Actionable summary (what to do right now)
        action_parts: list[str] = []
        if suppressor_ids:
            action_parts.append("当前环境有 no-trade 抑制条件，优先不开仓。")
        elif active_ids:
            top = active_ids[0]
            action_parts.append(f"主候选策略: {top.title}")
            if top.why_relevant:
                action_parts.append(f"原因: {top.why_relevant[0]}")
        if health.coaching_message:
            action_parts.append(health.coaching_message)
        actionable_summary = " ".join(action_parts) if action_parts else "当前无明确信号，保持观察。"

        context_used = [
            f"candles={len(snapshot.candles)}",
            f"events={len(snapshot.event_annotations)}",
            f"focus_regions={len(snapshot.focus_regions)}",
            f"entries={len(entries)}",
            f"manual_regions={len(manual_regions or [])}",
        ]

        return FullMarketAnalysisResult(
            analysis_id=f"fma-{uuid4().hex[:12]}",
            generated_at=now,
            data_window_start=snapshot.window_start,
            data_window_end=snapshot.window_end,
            instrument_symbol=snapshot.instrument.symbol,
            regime=regime,
            position_health=health,
            no_trade_active=len(suppressor_ids) > 0,
            suppressor_ids=suppressor_ids,
            strategy_candidates=strat_summary,
            focus_regions_summary=focus_summary,
            risk_alerts=risk_alerts,
            ai_briefing_objective=briefing.objective if briefing else "",
            ai_briefing_focus_questions=briefing.focus_questions if briefing else [],
            environment_summary=environment_summary,
            actionable_summary=actionable_summary,
            confidence=regime.confidence,
            context_used=context_used,
        )


# ---------------------------------------------------------------------------
# Tier 3: Deep region analysis (human-triggered on specific region)
# ---------------------------------------------------------------------------

class DeepRegionAnalysisService:
    """Focused analysis on a specific region. High-value, targeted token spend."""

    def __init__(self, strategy_engine: StrategySelectionEngine | None = None) -> None:
        self._strategy_engine = strategy_engine or StrategySelectionEngine()
        self._health_evaluator = PositionHealthEvaluator()

    def analyze_region(
        self,
        snapshot: ReplayWorkbenchSnapshotPayload,
        region: ReplayManualRegionAnnotationRecord,
        entries: list[ReplayOperatorEntryRecord],
        *,
        source_type: str = "manual_marked",
    ) -> DeepRegionAnalysisResult:
        now = datetime.now(tz=UTC)

        # Filter events within region
        region_events = [
            e for e in snapshot.event_annotations
            if self._event_in_region(e, region)
        ]
        # Filter focus regions overlapping
        overlapping_focus = [
            r for r in snapshot.focus_regions
            if self._regions_overlap(r.price_low, r.price_high, region.price_low, region.price_high)
        ]

        # Derive event_kinds and reason_codes from region
        derived_event_kinds = sorted({e.event_kind for e in region_events})
        derived_reason_codes: set[str] = set()
        for fr in overlapping_focus:
            derived_reason_codes.update(fr.reason_codes)
        if region.tags:
            derived_reason_codes.update(region.tags)

        # Strategy candidates for this region
        candidates = self._strategy_engine.select_candidates(
            region_events, overlapping_focus,
            instrument_symbol=snapshot.instrument.symbol,
        )
        suppressor_ids = [c.strategy_id for c in candidates if "no_trade" in c.strategy_id or "no-trade" in c.strategy_id]

        # Evidence check
        evidence_seen: list[str] = []
        evidence_missing: list[str] = []
        invalidation_seen: list[str] = []

        if any(e.event_kind == "same_price_replenishment" for e in region_events):
            evidence_seen.append("same_price_replenishment observed")
        else:
            evidence_missing.append("same_price_replenishment not observed in region")

        if any(e.event_kind == "initiative_drive" for e in region_events):
            evidence_seen.append("initiative_drive observed")
        if any(e.event_kind == "post_harvest_response" for e in region_events):
            evidence_seen.append("post_harvest_response observed")

        # Check for invalidation signals
        for e in region_events:
            if e.event_kind in ("gap_fully_filled",):
                invalidation_seen.append(f"{e.event_kind} at {e.price_low}")
            if e.confidence is not None and e.confidence < 0.3:
                invalidation_seen.append(f"low_confidence event {e.event_id} ({e.confidence:.2f})")

        # Position health impact
        region_entries = [
            e for e in entries
            if region.price_low <= e.entry_price <= region.price_high
        ]
        health = self._health_evaluator.evaluate(snapshot, region_entries, strategy_candidates=candidates)
        health_flags: list[str] = []
        if health.health_state != "healthy":
            health_flags.append(f"position_health={health.health_state}")
        health_flags.extend(health.warnings[:3])

        # Determine verdict
        verdict = self._determine_verdict(
            region_events, derived_event_kinds, suppressor_ids, evidence_seen, invalidation_seen,
        )

        # Build event chain
        event_chain = [
            {
                "event_id": e.event_id,
                "event_kind": e.event_kind,
                "observed_at": e.observed_at.isoformat(),
                "price_low": e.price_low,
                "price_high": e.price_high,
                "side": e.side.value if e.side else None,
                "confidence": e.confidence,
            }
            for e in sorted(region_events, key=lambda x: x.observed_at)
        ]

        strat_summary = [
            {"strategy_id": c.strategy_id, "title": c.title, "why_relevant": c.why_relevant}
            for c in candidates[:8]
        ]

        # Short summary
        summary_parts = [f"区域 {region.label} ({region.price_low}-{region.price_high})"]
        summary_parts.append(f"判定: {verdict}")
        if suppressor_ids:
            summary_parts.append(f"no-trade: {', '.join(suppressor_ids)}")
        if evidence_seen:
            summary_parts.append(f"已见证据: {', '.join(evidence_seen[:3])}")
        if evidence_missing:
            summary_parts.append(f"缺失证据: {', '.join(evidence_missing[:2])}")
        ai_summary_short = " | ".join(summary_parts)

        confidence = min(1.0, len(evidence_seen) * 0.2 + (0.1 if not invalidation_seen else 0.0))

        return DeepRegionAnalysisResult(
            analysis_id=f"dra-{uuid4().hex[:12]}",
            region_id=region.region_annotation_id,
            generated_at=now,
            source_type=source_type,
            instrument_symbol=snapshot.instrument.symbol,
            timeframe=str(snapshot.display_timeframe),
            session=None,
            time_range_start=region.started_at,
            time_range_end=region.ended_at or snapshot.window_end,
            price_range_low=region.price_low,
            price_range_high=region.price_high,
            event_chain=event_chain,
            derived_event_kinds=derived_event_kinds,
            derived_reason_codes=sorted(derived_reason_codes),
            strategy_candidates=strat_summary,
            no_trade_flags=[f"suppressor: {sid}" for sid in suppressor_ids],
            required_evidence_seen=evidence_seen,
            required_evidence_missing=evidence_missing,
            invalidation_seen=invalidation_seen,
            position_health_flags=health_flags,
            region_verdict=verdict,
            ai_summary_short=ai_summary_short,
            confidence=confidence,
            provenance=["market_data", "ai_inference"],
            review_status="pending",
        )

    @staticmethod
    def _event_in_region(event, region: ReplayManualRegionAnnotationRecord) -> bool:
        e_low = event.price_low if event.price_low is not None else (event.price if hasattr(event, "price") and event.price is not None else None)
        e_high = event.price_high if event.price_high is not None else e_low
        if e_low is None or e_high is None:
            return False
        price_overlap = (
            e_low <= region.price_high and e_high >= region.price_low
        )
        time_overlap = True
        if region.ended_at is not None:
            time_overlap = event.observed_at >= region.started_at and event.observed_at <= region.ended_at
        else:
            time_overlap = event.observed_at >= region.started_at
        return price_overlap and time_overlap

    @staticmethod
    def _regions_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> bool:
        return a_low <= b_high and a_high >= b_low

    @staticmethod
    def _determine_verdict(
        events, event_kinds: list[str], suppressor_ids: list[str],
        evidence_seen: list[str], invalidation_seen: list[str],
    ) -> str:
        if suppressor_ids:
            return "no_trade"
        if invalidation_seen:
            return "trap"
        if "post_harvest_response" in event_kinds:
            return "control_handoff"
        if "initiative_drive" in event_kinds and "same_price_replenishment" in event_kinds:
            return "continuation"
        if "same_price_replenishment" in event_kinds:
            return "continuation"
        if len(evidence_seen) >= 2:
            return "continuation"
        return "ambiguous"
