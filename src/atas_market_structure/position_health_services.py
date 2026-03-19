"""Position health monitoring service.

Evaluates whether operator entries exhibit healthy or unhealthy trading behaviors
based on replay context, focus regions, strategy candidates, and no-trade conditions.

Consumers: ai_review_services (prompt enrichment), workbench UI (health badge)
Does NOT modify: models.py, app.py routes, replay/workbench contracts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atas_market_structure.models import (
    ReplayEventAnnotation,
    ReplayFocusRegion,
    ReplayOperatorEntryRecord,
    ReplayStrategyCandidate,
    ReplayWorkbenchSnapshotPayload,
    StructureSide,
)


@dataclass
class PositionHealthResult:
    """Structured position health assessment — machine-readable + human-readable."""
    health_score: float  # 0.0 (critical) to 1.0 (excellent)
    health_state: str  # "healthy", "caution", "unhealthy", "critical"
    warnings: list[str] = field(default_factory=list)
    healthy_behaviors: list[str] = field(default_factory=list)
    coaching_message: str = ""
    urgent_action_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": round(self.health_score, 2),
            "health_state": self.health_state,
            "warnings": self.warnings,
            "healthy_behaviors": self.healthy_behaviors,
            "coaching_message": self.coaching_message,
            "urgent_action_hint": self.urgent_action_hint,
            "details": self.details,
        }


class PositionHealthEvaluator:
    """Evaluates position health from replay snapshot + operator entries."""

    def evaluate(
        self,
        snapshot: ReplayWorkbenchSnapshotPayload,
        entries: list[ReplayOperatorEntryRecord],
        *,
        strategy_candidates: list[ReplayStrategyCandidate] | None = None,
    ) -> PositionHealthResult:
        if not entries:
            return PositionHealthResult(
                health_score=1.0,
                health_state="healthy",
                healthy_behaviors=["No open positions — flat is a valid position."],
                coaching_message="当前无持仓，保持观察。",
            )

        warnings: list[str] = []
        healthy: list[str] = []
        penalty = 0.0
        bonus = 0.0
        candidates = strategy_candidates or snapshot.strategy_candidates
        no_trade_active = any("no_trade" in c.strategy_id or "no-trade" in c.strategy_id for c in candidates)

        for entry in entries:
            entry_warnings, entry_healthy, entry_penalty, entry_bonus = self._evaluate_single_entry(
                entry, snapshot, no_trade_active,
            )
            warnings.extend(entry_warnings)
            healthy.extend(entry_healthy)
            penalty += entry_penalty
            bonus += entry_bonus

        # Multi-entry pattern checks
        if len(entries) >= 3:
            warnings.append("多次开仓（≥3次）：检查是否在追单或情绪化加仓。")
            penalty += 0.15
        same_side = len({e.side for e in entries})
        if same_side == 1 and len(entries) >= 2:
            warnings.append("同方向连续开仓：确认是计划内加仓还是情绪驱动。")
            penalty += 0.08

        # Compute final score
        raw_score = max(0.0, min(1.0, 1.0 - penalty + bonus))
        health_state = self._score_to_state(raw_score)

        coaching = self._build_coaching(health_state, warnings, healthy)
        urgent = None
        if health_state == "critical":
            urgent = "立即检查持仓：当前环境或行为存在严重风险。"
        elif health_state == "unhealthy":
            urgent = "建议减仓或收紧止损，当前持仓行为偏离计划。"

        return PositionHealthResult(
            health_score=raw_score,
            health_state=health_state,
            warnings=warnings[:10],
            healthy_behaviors=healthy[:10],
            coaching_message=coaching,
            urgent_action_hint=urgent,
            details={
                "entry_count": len(entries),
                "no_trade_suppressor_active": no_trade_active,
                "penalty": round(penalty, 3),
                "bonus": round(bonus, 3),
            },
        )

    def _evaluate_single_entry(
        self,
        entry: ReplayOperatorEntryRecord,
        snapshot: ReplayWorkbenchSnapshotPayload,
        no_trade_active: bool,
    ) -> tuple[list[str], list[str], float, float]:
        warnings: list[str] = []
        healthy: list[str] = []
        penalty = 0.0
        bonus = 0.0

        # 1. Trading in no-trade environment
        if no_trade_active:
            warnings.append(f"在 no-trade 环境中开仓 @ {entry.entry_price}：当前有抑制策略激活。")
            penalty += 0.3

        # 2. No stop price
        if entry.stop_price is None:
            warnings.append(f"开仓 @ {entry.entry_price} 没有设置止损。")
            penalty += 0.15
        else:
            # Check stop distance reasonableness
            stop_dist = abs(entry.entry_price - entry.stop_price)
            if stop_dist < 0.5:
                warnings.append(f"止损距离过近（{stop_dist:.2f}），容易被噪音扫出。")
                penalty += 0.05
            else:
                healthy.append("已设置止损，风险可控。")
                bonus += 0.05

        # 3. No thesis
        if not entry.thesis:
            warnings.append("开仓没有记录交易逻辑（thesis）。")
            penalty += 0.1
        else:
            healthy.append("开仓时记录了交易逻辑。")
            bonus += 0.03

        # 4. Check if entry is inside a focus region
        in_focus = False
        for region in snapshot.focus_regions:
            if region.price_low <= entry.entry_price <= region.price_high:
                in_focus = True
                break
        if in_focus:
            healthy.append(f"开仓价 {entry.entry_price} 在重点区域内，有结构支撑。")
            bonus += 0.05
        else:
            warnings.append(f"开仓价 {entry.entry_price} 不在任何重点区域内。")
            penalty += 0.05

        # 5. Check if entry price is near candle extremes (chasing)
        if snapshot.candles:
            last_candle = snapshot.candles[-1]
            candle_range = last_candle.high - last_candle.low
            if candle_range > 0:
                if entry.side == StructureSide.BUY and entry.entry_price > last_candle.high - candle_range * 0.1:
                    warnings.append("做多开仓价接近最近K线高点，可能在追高。")
                    penalty += 0.1
                elif entry.side == StructureSide.SELL and entry.entry_price < last_candle.low + candle_range * 0.1:
                    warnings.append("做空开仓价接近最近K线低点，可能在追低。")
                    penalty += 0.1

        return warnings, healthy, penalty, bonus

    @staticmethod
    def _score_to_state(score: float) -> str:
        if score >= 0.75:
            return "healthy"
        if score >= 0.5:
            return "caution"
        if score >= 0.25:
            return "unhealthy"
        return "critical"

    @staticmethod
    def _build_coaching(state: str, warnings: list[str], healthy: list[str]) -> str:
        if state == "healthy":
            return "持仓行为整体健康，继续按计划执行。"
        if state == "caution":
            return f"持仓需要注意：{warnings[0] if warnings else '检查当前环境是否仍支持持仓。'}"
        if state == "unhealthy":
            return f"持仓行为偏离计划：{'; '.join(warnings[:2])}"
        return f"持仓状态危险：{'; '.join(warnings[:3])}"
