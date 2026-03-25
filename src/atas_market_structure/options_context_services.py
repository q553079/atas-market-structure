from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from atas_market_structure.spx_gamma_map import GammaMapSummary


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _safe_abs(value: float | None) -> float | None:
    return abs(value) if value is not None else None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


@dataclass(frozen=True, slots=True)
class OptionsSnapshotMetrics:
    quote_time: str | None
    source_file: str | None
    spx_spot: float
    zero_gamma_proxy: float | None
    total_net_gex_1pct: float
    local_net_gex_1pct: float | None
    gap_chop_score: int | None
    front_put_call_iv_ratio_25d: float | None
    dominant_call_wall_strike: float | None
    dominant_put_wall_strike: float | None
    strike_step: float
    regime: str
    term_structure_label: str | None


@dataclass(frozen=True, slots=True)
class StrategyArchetypeCandidate:
    strategy_id: str
    label: str
    environment_fit: int
    thesis: str
    rationale: list[str]
    cautions: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HistoricalContextEntry:
    quote_time: str | None
    source_file: str | None
    zero_gamma_proxy: float | None
    total_net_gex_1pct: float
    local_net_gex_1pct: float | None
    front_put_call_iv_ratio_25d: float | None
    dominant_call_wall_strike: float | None
    dominant_put_wall_strike: float | None
    regime: str
    gap_chop_score: int | None

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OptionsStrategyContext:
    environment_label: str
    range_harvest_score: int
    breakout_pressure_score: int
    downside_hedge_demand_score: int
    upside_chase_score: int
    short_vol_friendliness: int
    long_gamma_friendliness: int
    context_window_count: int
    context_signals: list[str] = field(default_factory=list)
    structural_signals: list[str] = field(default_factory=list)
    strategy_candidates: list[StrategyArchetypeCandidate] = field(default_factory=list)
    recent_history: list[HistoricalContextEntry] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "environment_label": self.environment_label,
            "range_harvest_score": self.range_harvest_score,
            "breakout_pressure_score": self.breakout_pressure_score,
            "downside_hedge_demand_score": self.downside_hedge_demand_score,
            "upside_chase_score": self.upside_chase_score,
            "short_vol_friendliness": self.short_vol_friendliness,
            "long_gamma_friendliness": self.long_gamma_friendliness,
            "context_window_count": self.context_window_count,
            "context_signals": list(self.context_signals),
            "structural_signals": list(self.structural_signals),
            "strategy_candidates": [item.to_jsonable() for item in self.strategy_candidates],
            "recent_history": [item.to_jsonable() for item in self.recent_history],
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True, slots=True)
class OptionsStrategyContextArtifacts:
    json_path: Path
    report_path: Path


def _summary_to_metrics(summary: GammaMapSummary) -> OptionsSnapshotMetrics:
    structural = summary.structural_regime
    return OptionsSnapshotMetrics(
        quote_time=summary.quote_time,
        source_file=summary.source_file,
        spx_spot=summary.spx_spot,
        zero_gamma_proxy=summary.zero_gamma_proxy,
        total_net_gex_1pct=summary.total_net_gex_1pct,
        local_net_gex_1pct=structural.local_net_gex_1pct if structural is not None else None,
        gap_chop_score=structural.gap_chop_score if structural is not None else None,
        front_put_call_iv_ratio_25d=structural.front_put_call_iv_ratio_25d if structural is not None else None,
        dominant_call_wall_strike=(
            structural.dominant_call_wall.strike if structural is not None and structural.dominant_call_wall is not None else None
        ),
        dominant_put_wall_strike=(
            structural.dominant_put_wall.strike if structural is not None and structural.dominant_put_wall is not None else None
        ),
        strike_step=summary.strike_step,
        regime=summary.regime,
        term_structure_label=structural.term_structure_label if structural is not None else None,
    )


def _payload_to_metrics(payload: dict[str, Any]) -> OptionsSnapshotMetrics | None:
    structural = payload.get("structural_regime") or {}
    try:
        return OptionsSnapshotMetrics(
            quote_time=payload.get("quote_time"),
            source_file=payload.get("source_file"),
            spx_spot=float(payload.get("spx_spot")),
            zero_gamma_proxy=(
                float(payload["zero_gamma_proxy"]) if payload.get("zero_gamma_proxy") is not None else None
            ),
            total_net_gex_1pct=float(payload.get("total_net_gex_1pct", 0.0)),
            local_net_gex_1pct=(
                float(structural["local_net_gex_1pct"]) if structural.get("local_net_gex_1pct") is not None else None
            ),
            gap_chop_score=int(structural["gap_chop_score"]) if structural.get("gap_chop_score") is not None else None,
            front_put_call_iv_ratio_25d=(
                float(structural["front_put_call_iv_ratio_25d"])
                if structural.get("front_put_call_iv_ratio_25d") is not None
                else None
            ),
            dominant_call_wall_strike=(
                float(structural["dominant_call_wall"]["strike"])
                if structural.get("dominant_call_wall") and structural["dominant_call_wall"].get("strike") is not None
                else None
            ),
            dominant_put_wall_strike=(
                float(structural["dominant_put_wall"]["strike"])
                if structural.get("dominant_put_wall") and structural["dominant_put_wall"].get("strike") is not None
                else None
            ),
            strike_step=float(payload.get("strike_step", 5.0)),
            regime=str(payload.get("regime") or "unknown"),
            term_structure_label=(
                str(structural["term_structure_label"]) if structural.get("term_structure_label") is not None else None
            ),
        )
    except (TypeError, ValueError):
        return None


def _history_entry_from_metrics(metrics: OptionsSnapshotMetrics) -> HistoricalContextEntry:
    return HistoricalContextEntry(
        quote_time=metrics.quote_time,
        source_file=metrics.source_file,
        zero_gamma_proxy=metrics.zero_gamma_proxy,
        total_net_gex_1pct=metrics.total_net_gex_1pct,
        local_net_gex_1pct=metrics.local_net_gex_1pct,
        front_put_call_iv_ratio_25d=metrics.front_put_call_iv_ratio_25d,
        dominant_call_wall_strike=metrics.dominant_call_wall_strike,
        dominant_put_wall_strike=metrics.dominant_put_wall_strike,
        regime=metrics.regime,
        gap_chop_score=metrics.gap_chop_score,
    )


def _parse_quote_time(raw: str | None) -> datetime | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            return None


def load_recent_options_history(
    history_dir: Path,
    *,
    exclude_path: Path | None = None,
    limit: int = 8,
) -> list[OptionsSnapshotMetrics]:
    if not history_dir.exists():
        return []

    candidates = sorted(history_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    results: list[OptionsSnapshotMetrics] = []
    resolved_exclude = exclude_path.resolve() if exclude_path is not None and exclude_path.exists() else None

    for candidate in candidates:
        if resolved_exclude is not None and candidate.resolve() == resolved_exclude:
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        metrics = _payload_to_metrics(payload)
        if metrics is None:
            continue
        results.append(metrics)
        if len(results) >= limit:
            break
    return results


def _wall_balance(current: OptionsSnapshotMetrics) -> float | None:
    if current.dominant_call_wall_strike is None or current.dominant_put_wall_strike is None:
        return None
    upside = current.dominant_call_wall_strike - current.spx_spot
    downside = current.spx_spot - current.dominant_put_wall_strike
    if upside <= 0 or downside <= 0:
        return 0.0
    span = upside + downside
    if span <= 0:
        return None
    return 1.0 - abs(upside - downside) / span


def _score_environment(current: OptionsSnapshotMetrics, previous: list[OptionsSnapshotMetrics]) -> tuple[dict[str, int], list[str], list[str]]:
    step = current.strike_step or 5.0
    previous_zero_shifts = [
        _safe_abs(current.zero_gamma_proxy - item.zero_gamma_proxy)
        for item in previous
        if current.zero_gamma_proxy is not None and item.zero_gamma_proxy is not None
    ]
    previous_call_wall_shifts = [
        _safe_abs(current.dominant_call_wall_strike - item.dominant_call_wall_strike)
        for item in previous
        if current.dominant_call_wall_strike is not None and item.dominant_call_wall_strike is not None
    ]
    previous_put_wall_shifts = [
        _safe_abs(current.dominant_put_wall_strike - item.dominant_put_wall_strike)
        for item in previous
        if current.dominant_put_wall_strike is not None and item.dominant_put_wall_strike is not None
    ]
    avg_zero_shift = _mean([item for item in previous_zero_shifts if item is not None])
    avg_call_wall_shift = _mean([item for item in previous_call_wall_shifts if item is not None])
    avg_put_wall_shift = _mean([item for item in previous_put_wall_shifts if item is not None])
    previous_ratio = previous[0].front_put_call_iv_ratio_25d if previous else None
    ratio_change = None
    if current.front_put_call_iv_ratio_25d is not None and previous_ratio is not None:
        ratio_change = current.front_put_call_iv_ratio_25d - previous_ratio

    wall_balance = _wall_balance(current)
    zero_distance = (
        abs(current.spx_spot - current.zero_gamma_proxy) if current.zero_gamma_proxy is not None else None
    )
    spot_between_walls = (
        current.dominant_put_wall_strike is not None
        and current.dominant_call_wall_strike is not None
        and current.dominant_put_wall_strike <= current.spx_spot <= current.dominant_call_wall_strike
    )

    range_harvest = 20.0
    breakout_pressure = 15.0
    downside_hedge_demand = 10.0
    upside_chase = 10.0

    structural_signals: list[str] = []
    context_signals: list[str] = []

    if current.local_net_gex_1pct is not None and current.local_net_gex_1pct > 0:
        range_harvest += 22
        structural_signals.append("Local gamma stays positive, which favors pinning and slower reversion-heavy tape.")
    if current.total_net_gex_1pct > 0:
        range_harvest += 10
    if current.gap_chop_score is not None:
        if current.gap_chop_score >= 60:
            range_harvest += 18
            structural_signals.append(f"Gap&Chop score is {current.gap_chop_score}, consistent with range-harvest conditions.")
        elif current.gap_chop_score <= 40:
            breakout_pressure += 18
            structural_signals.append(f"Gap&Chop score is only {current.gap_chop_score}, so clean pin conditions are weaker.")
    if zero_distance is not None:
        if zero_distance <= step * 1.5:
            range_harvest += 15
            structural_signals.append("Spot is still close to zero gamma, so dealer hedging can keep the tape sticky.")
        elif zero_distance >= step * 3:
            breakout_pressure += 14
            structural_signals.append("Spot has drifted away from zero gamma, raising breakout pressure.")
    if spot_between_walls:
        range_harvest += 12
        structural_signals.append("Spot is still sitting between the dominant put and call walls.")
    if wall_balance is not None and wall_balance >= 0.6:
        range_harvest += 8
    if current.local_net_gex_1pct is not None and current.local_net_gex_1pct < 0:
        breakout_pressure += 24
        structural_signals.append("Local gamma has flipped negative, so hedging can amplify directional moves.")
    if current.total_net_gex_1pct < 0:
        breakout_pressure += 12
    if current.front_put_call_iv_ratio_25d is not None:
        if current.front_put_call_iv_ratio_25d >= 1.08:
            downside_hedge_demand += 20
            structural_signals.append(
                f"Front put/call IV ratio is {current.front_put_call_iv_ratio_25d:.2f}, showing downside skew demand."
            )
        elif current.front_put_call_iv_ratio_25d <= 0.98:
            upside_chase += 10
    if ratio_change is not None:
        if ratio_change >= 0.02:
            downside_hedge_demand += 14
            context_signals.append(
                f"Front skew rose by {ratio_change:.2f} versus the prior snapshot, consistent with fresh downside hedge demand."
            )
        elif ratio_change <= -0.02:
            upside_chase += 8
            context_signals.append(
                f"Front skew fell by {abs(ratio_change):.2f} versus the prior snapshot, reducing downside urgency."
            )
    if avg_zero_shift is not None:
        if avg_zero_shift <= step * 1.25:
            range_harvest += 10
            context_signals.append(
                f"Zero gamma moved only about {avg_zero_shift:.1f} handles on average across recent snapshots."
            )
        elif avg_zero_shift >= step * 2.5:
            breakout_pressure += 14
            context_signals.append(
                f"Zero gamma has been moving about {avg_zero_shift:.1f} handles on average, so the structure is not static."
            )
    if avg_call_wall_shift is not None and avg_call_wall_shift >= step * 2:
        breakout_pressure += 8
        upside_chase += 8
        context_signals.append(
            f"Call wall migration has been active, averaging {avg_call_wall_shift:.1f} handles."
        )
    if avg_put_wall_shift is not None and avg_put_wall_shift >= step * 2:
        breakout_pressure += 8
        downside_hedge_demand += 8
        context_signals.append(
            f"Put wall migration has been active, averaging {avg_put_wall_shift:.1f} handles."
        )

    range_like_history = sum(
        1
        for item in previous
        if (item.local_net_gex_1pct or 0.0) > 0 and (item.gap_chop_score or 0) >= 55
    )
    hedge_like_history = sum(
        1
        for item in previous
        if item.front_put_call_iv_ratio_25d is not None and item.front_put_call_iv_ratio_25d >= 1.08
    )
    if previous:
        context_signals.append(
            f"Recent context: {range_like_history}/{len(previous)} snapshots looked range-friendly and {hedge_like_history}/{len(previous)} showed elevated downside skew."
        )

    scores = {
        "range_harvest_score": _clamp_score(range_harvest),
        "breakout_pressure_score": _clamp_score(breakout_pressure),
        "downside_hedge_demand_score": _clamp_score(downside_hedge_demand),
        "upside_chase_score": _clamp_score(upside_chase),
    }
    scores["short_vol_friendliness"] = _clamp_score(
        scores["range_harvest_score"] * 0.60
        + (100 - scores["breakout_pressure_score"]) * 0.25
        + (100 - scores["downside_hedge_demand_score"]) * 0.15
    )
    scores["long_gamma_friendliness"] = _clamp_score(
        scores["breakout_pressure_score"] * 0.55
        + scores["downside_hedge_demand_score"] * 0.25
        + scores["upside_chase_score"] * 0.20
    )
    return scores, structural_signals, context_signals


def _build_strategy_candidates(
    scores: dict[str, int],
    current: OptionsSnapshotMetrics,
) -> list[StrategyArchetypeCandidate]:
    cautions = [
        "This is an environment-fit inference from delayed chain structure, not proof of actual market inventory.",
        "Zero/flat D0 IV or gamma fields can distort the shortest-expiry layer and should be treated carefully.",
    ]
    candidates: list[StrategyArchetypeCandidate] = []

    if scores["short_vol_friendliness"] >= scores["long_gamma_friendliness"]:
        candidates.append(
            StrategyArchetypeCandidate(
                strategy_id="iron_condor_environment",
                label="Iron Condor Friendly",
                environment_fit=_clamp_score(scores["range_harvest_score"] * 0.7 + scores["short_vol_friendliness"] * 0.3),
                thesis="The tape still looks more pin-and-harvest than expansion-driven.",
                rationale=[
                    "Range-harvest score is leading the board.",
                    "Short-vol friendliness still exceeds long-gamma friendliness.",
                    "Dominant walls and zero gamma remain relevant reference points.",
                ],
                cautions=cautions,
            )
        )
        candidates.append(
            StrategyArchetypeCandidate(
                strategy_id="iron_fly_environment",
                label="Iron Fly / Tight Pin",
                environment_fit=_clamp_score(scores["range_harvest_score"] * 0.65 + scores["short_vol_friendliness"] * 0.35),
                thesis="If spot keeps pinning near the same strikes, tighter premium-harvest structures fit better than directional longs.",
                rationale=[
                    "The current read still favors a sticky tape around key strikes.",
                    "The environment is more compatible with theta harvest than breakout chasing.",
                ],
                cautions=cautions,
            )
        )

    if scores["downside_hedge_demand_score"] >= 45:
        candidates.append(
            StrategyArchetypeCandidate(
                strategy_id="put_debit_spread_environment",
                label="Put Debit Spread Friendly",
                environment_fit=_clamp_score(scores["downside_hedge_demand_score"] * 0.65 + scores["long_gamma_friendliness"] * 0.35),
                thesis="Downside skew demand is elevated enough that bearish protection structures deserve more respect than blind short-vol trades.",
                rationale=[
                    "Front skew is elevated or rising.",
                    "Put-side demand is strong enough to keep downside hedges relevant.",
                ],
                cautions=cautions,
            )
        )

    if scores["upside_chase_score"] >= 40 or (
        scores["breakout_pressure_score"] >= 55 and current.total_net_gex_1pct < 0
    ):
        candidates.append(
            StrategyArchetypeCandidate(
                strategy_id="call_debit_spread_environment",
                label="Directional Debit Spread Friendly",
                environment_fit=_clamp_score(scores["upside_chase_score"] * 0.4 + scores["breakout_pressure_score"] * 0.6),
                thesis="If the tape is shifting away from pinning and walls are migrating, defined-risk directional structures fit better than static income trades.",
                rationale=[
                    "Breakout pressure is elevated.",
                    "Wall migration or zero-gamma drift suggests a less stable pin regime.",
                ],
                cautions=cautions,
            )
        )

    if not candidates:
        candidates.append(
            StrategyArchetypeCandidate(
                strategy_id="mixed_environment",
                label="Mixed / Wait for Cleaner Structure",
                environment_fit=_clamp_score(max(scores.values())),
                thesis="The structure is mixed enough that regime clarity matters more than forcing a favorite strategy label.",
                rationale=[
                    "No single environment score is dominant enough to support a clean archetype call.",
                    "Use the wall and zero-gamma drift more than the strategy label itself.",
                ],
                cautions=cautions,
            )
        )

    candidates.sort(key=lambda item: item.environment_fit, reverse=True)
    return candidates[:3]


def _environment_label(scores: dict[str, int]) -> str:
    if scores["range_harvest_score"] >= max(
        scores["breakout_pressure_score"],
        scores["downside_hedge_demand_score"],
        scores["upside_chase_score"],
    ):
        return "range_harvest"
    if scores["downside_hedge_demand_score"] >= max(
        scores["breakout_pressure_score"],
        scores["upside_chase_score"],
    ):
        return "downside_hedge_demand"
    if scores["upside_chase_score"] >= scores["breakout_pressure_score"]:
        return "upside_chase"
    return "breakout_pressure"


def analyze_options_strategy_context(
    summary: GammaMapSummary,
    *,
    history_dir: Path,
    exclude_history_path: Path | None = None,
    history_limit: int = 8,
) -> OptionsStrategyContext:
    current = _summary_to_metrics(summary)
    previous = load_recent_options_history(history_dir, exclude_path=exclude_history_path, limit=history_limit)
    scores, structural_signals, context_signals = _score_environment(current, previous)
    candidates = _build_strategy_candidates(scores, current)
    return OptionsStrategyContext(
        environment_label=_environment_label(scores),
        range_harvest_score=scores["range_harvest_score"],
        breakout_pressure_score=scores["breakout_pressure_score"],
        downside_hedge_demand_score=scores["downside_hedge_demand_score"],
        upside_chase_score=scores["upside_chase_score"],
        short_vol_friendliness=scores["short_vol_friendliness"],
        long_gamma_friendliness=scores["long_gamma_friendliness"],
        context_window_count=len(previous),
        context_signals=context_signals,
        structural_signals=structural_signals,
        strategy_candidates=candidates,
        recent_history=[_history_entry_from_metrics(item) for item in previous],
        caveats=[
            "These labels describe which payoff shapes the current environment resembles, not what the market definitively owns.",
            "Use delayed-chain context together with underlying price action before promoting a strategy bias.",
        ],
    )


def render_options_strategy_context_report(context: OptionsStrategyContext) -> str:
    lines = [
        f"环境标签: {context.environment_label}",
        f"Range Harvest: {context.range_harvest_score}",
        f"Breakout Pressure: {context.breakout_pressure_score}",
        f"Downside Hedge Demand: {context.downside_hedge_demand_score}",
        f"Upside Chase: {context.upside_chase_score}",
        f"Short Vol Friendliness: {context.short_vol_friendliness}",
        f"Long Gamma Friendliness: {context.long_gamma_friendliness}",
        f"上下文窗口: {context.context_window_count}",
        "",
        "结构信号:",
    ]
    if context.structural_signals:
        lines.extend(f"  - {item}" for item in context.structural_signals)
    else:
        lines.append("  - 无明显结构信号。")

    lines.append("")
    lines.append("上下文信号:")
    if context.context_signals:
        lines.extend(f"  - {item}" for item in context.context_signals)
    else:
        lines.append("  - 历史上下文不足。")

    lines.append("")
    lines.append("更匹配的策略环境:")
    for index, candidate in enumerate(context.strategy_candidates, start=1):
        lines.append(f"  {index}. {candidate.label} ({candidate.environment_fit})")
        lines.append(f"     逻辑: {candidate.thesis}")
        for reason in candidate.rationale:
            lines.append(f"     - {reason}")

    lines.append("")
    lines.append("注意:")
    lines.extend(f"  - {item}" for item in context.caveats)
    return "\n".join(lines)


def write_options_strategy_context_artifacts(
    context: OptionsStrategyContext,
    output_dir: Path,
    *,
    stem: str,
) -> OptionsStrategyContextArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}_strategy_context.json"
    report_path = output_dir / f"{stem}_strategy_context.txt"
    json_path.write_text(json.dumps(context.to_jsonable(), indent=2), encoding="utf-8")
    report_path.write_text(render_options_strategy_context_report(context), encoding="utf-8")
    return OptionsStrategyContextArtifacts(
        json_path=json_path,
        report_path=report_path,
    )
