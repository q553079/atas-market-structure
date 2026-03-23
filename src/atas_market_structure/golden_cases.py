from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.models import (
    DegradedMode,
    EpisodeResolution,
    EvaluationFailureMode,
    RecognitionMode,
    TradableEventKind,
)
from atas_market_structure.profile_services import default_tick_size_for_symbol


class GoldenReplayBar(BaseModel):
    """Minimal bar input used to build one adapter history-bars payload."""

    model_config = ConfigDict(extra="forbid")

    open: float
    high: float
    low: float
    close: float
    volume: int = Field(..., ge=1)
    delta: int


class GoldenDepthLevel(BaseModel):
    """Compact depth-level spec for one golden replay case."""

    model_config = ConfigDict(extra="forbid")

    track_id: str
    side: Literal["buy", "sell"]
    price: float
    current_size: int = Field(..., ge=0)
    max_seen_size: int = Field(..., ge=0)
    distance_from_price_ticks: int = Field(..., ge=0)
    status: str = "active"
    touch_count: int = Field(1, ge=0)
    executed_volume_estimate: int = Field(0, ge=0)
    replenishment_count: int = Field(0, ge=0)
    pull_count: int = Field(0, ge=0)
    move_count: int = Field(0, ge=0)
    price_reaction_ticks: int = Field(0, ge=0)
    heat_score: float = Field(..., ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class _GoldenReplayStepBase(BaseModel):
    """Common metadata shared by all replay input steps."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    stored_at: datetime
    observed_at: datetime


class GoldenHistoryBarsStep(_GoldenReplayStepBase):
    """Replay step that materializes one `adapter_history_bars` ingestion."""

    template: Literal["adapter_history_bars"]
    start_at: datetime
    bars: list[GoldenReplayBar] = Field(..., min_length=3)
    bar_timeframe: str = "1m"


class GoldenProcessContextStep(_GoldenReplayStepBase):
    """Replay step that materializes one `process_context` ingestion."""

    template: Literal["process_context"]
    point_of_control: float
    initiative_side: Literal["buy", "sell"]
    zone_low: float
    zone_high: float
    include_initiative: bool = True
    include_liquidity_episode: bool = False
    session_code: str = "us_regular"


class GoldenContinuousStateStep(_GoldenReplayStepBase):
    """Replay step that materializes one `adapter_continuous_state` ingestion."""

    template: Literal["adapter_continuous_state"]
    last_price: float
    local_low: float
    local_high: float
    net_delta: int
    volume: int = Field(..., ge=1)
    side: Literal["buy", "sell"]
    drive_low: float
    drive_high: float
    include_post_harvest_response: bool = True


class GoldenEventSnapshotStep(_GoldenReplayStepBase):
    """Replay step that materializes one `event_snapshot` ingestion."""

    template: Literal["event_snapshot"]
    event_type: str = "liquidity_sweep"
    trigger_price: float
    absorption_magnitude: float = Field(0.88, ge=0.0, le=1.0)
    initiative_magnitude: float = Field(0.71, ge=0.0, le=1.0)


class GoldenDepthSnapshotStep(_GoldenReplayStepBase):
    """Replay step that materializes one `depth_snapshot` ingestion."""

    template: Literal["depth_snapshot"]
    coverage_state: str = "depth_live"
    best_bid: float | None = None
    best_ask: float | None = None
    reference_price: float | None = None
    significant_levels: list[GoldenDepthLevel] = Field(default_factory=list)


GoldenReplayStep = Annotated[
    GoldenHistoryBarsStep
    | GoldenProcessContextStep
    | GoldenContinuousStateStep
    | GoldenEventSnapshotStep
    | GoldenDepthSnapshotStep,
    Field(discriminator="template"),
]


class GoldenReplayExpectation(BaseModel):
    """Assertions that one replay run must satisfy."""

    model_config = ConfigDict(extra="forbid")

    top_event_kind: TradableEventKind
    recognition_mode: RecognitionMode
    required_degraded_modes: list[DegradedMode] = Field(default_factory=list)
    forbidden_degraded_modes: list[DegradedMode] = Field(default_factory=list)
    minimum_belief_count: int = Field(1, ge=1)
    minimum_episode_count: int = Field(0, ge=0)
    minimum_evaluation_count: int = Field(0, ge=0)
    minimum_active_anchor_count: int = Field(0, ge=0)
    required_episode_event_kinds: list[TradableEventKind] = Field(default_factory=list)
    required_episode_resolutions: list[EpisodeResolution] = Field(default_factory=list)
    required_evaluation_failure_modes: list[EvaluationFailureMode] = Field(default_factory=list)
    data_completeness: str | None = None
    data_freshness: str | None = None


class GoldenReplayCase(BaseModel):
    """Strict golden replay case spec consumed by the rebuild runner and tests."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    scenario: str
    instrument_symbol: str = Field(..., alias="instrument")
    ai_available: bool = True
    notes: list[str] = Field(default_factory=list)
    steps: list[GoldenReplayStep] = Field(..., min_length=1)
    expected: GoldenReplayExpectation


class GoldenReplayCaseSet(BaseModel):
    """One sample file containing multiple replay cases for the same scenario family."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["golden_replay_case_set_v1"]
    case_group: str
    cases: list[GoldenReplayCase] = Field(..., min_length=1)


@dataclass(frozen=True)
class MaterializedGoldenReplayIngestion:
    """Concrete ingestion row derived from a golden replay case spec."""

    ingestion_id: str
    ingestion_kind: str
    source_snapshot_id: str
    instrument_symbol: str
    stored_at: datetime
    observed_payload: dict[str, object]
    step_id: str


def load_case_sets(path: Path) -> list[GoldenReplayCaseSet]:
    """Load one case file or a directory tree of case files."""

    files = [path] if path.is_file() else sorted(path.rglob("*.json"))
    sets: list[GoldenReplayCaseSet] = []
    for file_path in files:
        if file_path.name.startswith("."):
            continue
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        sets.append(GoldenReplayCaseSet.model_validate(payload))
    return sets


def iter_cases(path: Path) -> list[GoldenReplayCase]:
    """Return all cases from a file or directory, preserving file order."""

    cases: list[GoldenReplayCase] = []
    for case_set in load_case_sets(path):
        cases.extend(case_set.cases)
    return cases


def materialize_case_ingestions(case: GoldenReplayCase) -> list[MaterializedGoldenReplayIngestion]:
    """Convert one case spec into ordered ingestion rows."""

    instrument = _instrument_payload(case.instrument_symbol)
    rendered: list[MaterializedGoldenReplayIngestion] = []
    for step in sorted(case.steps, key=lambda item: item.stored_at):
        step_key = f"{case.case_id}-{step.step_id}"
        if isinstance(step, GoldenHistoryBarsStep):
            payload = _history_bars_payload(case=case, step=step, instrument=instrument, step_key=step_key)
            rendered.append(
                MaterializedGoldenReplayIngestion(
                    ingestion_id=f"ing-{step_key}",
                    ingestion_kind="adapter_history_bars",
                    source_snapshot_id=f"hist-{step_key}",
                    instrument_symbol=case.instrument_symbol,
                    stored_at=step.stored_at,
                    observed_payload=payload,
                    step_id=step.step_id,
                ),
            )
            continue
        if isinstance(step, GoldenProcessContextStep):
            payload = _process_context_payload(case=case, step=step, instrument=instrument, step_key=step_key)
            rendered.append(
                MaterializedGoldenReplayIngestion(
                    ingestion_id=f"ing-{step_key}",
                    ingestion_kind="process_context",
                    source_snapshot_id=f"proc-{step_key}",
                    instrument_symbol=case.instrument_symbol,
                    stored_at=step.stored_at,
                    observed_payload=payload,
                    step_id=step.step_id,
                ),
            )
            continue
        if isinstance(step, GoldenContinuousStateStep):
            payload = _continuous_state_payload(case=case, step=step, instrument=instrument, step_key=step_key)
            rendered.append(
                MaterializedGoldenReplayIngestion(
                    ingestion_id=f"ing-{step_key}",
                    ingestion_kind="adapter_continuous_state",
                    source_snapshot_id=f"msg-{step_key}",
                    instrument_symbol=case.instrument_symbol,
                    stored_at=step.stored_at,
                    observed_payload=payload,
                    step_id=step.step_id,
                ),
            )
            continue
        if isinstance(step, GoldenEventSnapshotStep):
            payload = _event_snapshot_payload(case=case, step=step, instrument=instrument, step_key=step_key)
            rendered.append(
                MaterializedGoldenReplayIngestion(
                    ingestion_id=f"ing-{step_key}",
                    ingestion_kind="event_snapshot",
                    source_snapshot_id=f"evt-{step_key}",
                    instrument_symbol=case.instrument_symbol,
                    stored_at=step.stored_at,
                    observed_payload=payload,
                    step_id=step.step_id,
                ),
            )
            continue
        payload = _depth_snapshot_payload(case=case, step=step, instrument=instrument, step_key=step_key)
        rendered.append(
            MaterializedGoldenReplayIngestion(
                ingestion_id=f"ing-{step_key}",
                ingestion_kind="depth_snapshot",
                source_snapshot_id=f"depth-{step_key}",
                instrument_symbol=case.instrument_symbol,
                stored_at=step.stored_at,
                observed_payload=payload,
                step_id=step.step_id,
            ),
        )
    rendered.sort(key=lambda item: (item.stored_at, item.ingestion_id))
    return rendered


def _instrument_payload(symbol: str) -> dict[str, object]:
    venue = {
        "ES": "CME",
        "NQ": "CME",
        "GC": "COMEX",
        "CL": "NYMEX",
    }.get(symbol.upper(), "CME")
    return {
        "symbol": symbol,
        "venue": venue,
        "tick_size": default_tick_size_for_symbol(symbol),
        "currency": "USD",
    }


def _history_bars_payload(
    *,
    case: GoldenReplayCase,
    step: GoldenHistoryBarsStep,
    instrument: dict[str, object],
    step_key: str,
) -> dict[str, object]:
    payload_bars: list[dict[str, object]] = []
    for index, bar in enumerate(step.bars):
        bar_start = step.start_at + timedelta(minutes=index)
        payload_bars.append(
            {
                "started_at": _iso(bar_start),
                "ended_at": _iso(bar_start + timedelta(seconds=59)),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "delta": bar.delta,
                "bid_volume": max(1, bar.volume // 3),
                "ask_volume": max(1, bar.volume // 2),
            },
        )
    return {
        "schema_version": "1.0.0",
        "message_id": f"collector-history-{step_key}",
        "message_type": "history_bars",
        "emitted_at": _iso(step.observed_at),
        "observed_window_start": _iso(step.start_at),
        "observed_window_end": _iso(step.start_at + timedelta(minutes=len(step.bars) - 1, seconds=59)),
        "source": _source_payload(case.instrument_symbol),
        "instrument": instrument,
        "bar_timeframe": step.bar_timeframe,
        "bars": payload_bars,
    }


def _process_context_payload(
    *,
    case: GoldenReplayCase,
    step: GoldenProcessContextStep,
    instrument: dict[str, object],
    step_key: str,
) -> dict[str, object]:
    process_context = {
        "session_windows": [
            {
                "session_code": step.session_code,
                "started_at": _iso(step.observed_at - timedelta(minutes=30)),
                "ended_at": _iso(step.observed_at),
                "latest_range": {
                    "open": step.point_of_control - 2.0,
                    "high": step.point_of_control + 2.5,
                    "low": step.point_of_control - 2.5,
                    "close": step.point_of_control,
                },
                "value_area": {
                    "low": step.point_of_control - 1.0,
                    "high": step.point_of_control + 1.0,
                    "point_of_control": step.point_of_control,
                },
                "session_stats": {"volume": 1000, "delta": 0, "trades": 300},
                "key_levels": [],
            },
        ],
        "second_features": [],
        "liquidity_episodes": [
            {
                "episode_id": f"liq-{step_key}",
                "started_at": _iso(step.observed_at - timedelta(minutes=8)),
                "ended_at": _iso(step.observed_at - timedelta(minutes=4)),
                "side": step.initiative_side,
                "price_low": step.zone_low,
                "price_high": step.zone_high,
                "executed_volume_against": 1200,
                "replenishment_count": 5,
                "pull_count": 1,
                "price_rejection_ticks": 14,
                "raw_features": {},
            },
        ]
        if step.include_liquidity_episode
        else [],
        "initiative_drives": [
            {
                "drive_id": f"drive-{step_key}",
                "started_at": _iso(step.observed_at - timedelta(minutes=3)),
                "ended_at": _iso(step.observed_at - timedelta(minutes=1)),
                "side": step.initiative_side,
                "price_low": step.zone_low,
                "price_high": step.zone_high + 8.0,
                "aggressive_volume": 800,
                "net_delta": 620 if step.initiative_side == "buy" else -620,
                "trade_count": 180,
                "consumed_price_levels": 5,
                "price_travel_ticks": 20,
                "max_counter_move_ticks": 4,
                "continuation_seconds": 60,
                "raw_features": {},
            },
        ]
        if step.include_initiative
        else [],
        "measured_moves": [],
        "manipulation_legs": [],
        "gap_references": [
            {
                "gap_id": f"gap-{step_key}",
                "session_code": "us_premarket",
                "opened_at": _iso(step.observed_at - timedelta(hours=1)),
                "direction": "up",
                "prior_reference_price": step.point_of_control - 3.0,
                "current_open_price": step.point_of_control - 2.0,
                "gap_low": step.point_of_control - 3.0,
                "gap_high": step.point_of_control - 2.0,
                "gap_size_ticks": 4,
                "first_touch_at": _iso(step.observed_at - timedelta(minutes=10)),
                "max_fill_ticks": 2,
                "fill_ratio": 0.5,
                "fill_attempt_count": 1,
                "accepted_inside_gap": True,
                "rejected_from_gap": False,
                "fully_filled_at": None,
                "raw_features": {},
            },
        ],
        "post_harvest_responses": [],
        "exertion_zones": [
            {
                "zone_id": f"zone-{step_key}",
                "source_drive_id": f"drive-{step_key}",
                "side": step.initiative_side,
                "price_low": step.zone_low,
                "price_high": step.zone_high,
                "established_at": _iso(step.observed_at - timedelta(minutes=15)),
                "last_interacted_at": _iso(step.observed_at - timedelta(minutes=1)),
                "establishing_volume": 1500,
                "establishing_delta": 900 if step.initiative_side == "buy" else -900,
                "establishing_trade_count": 200,
                "peak_price_level_volume": 500,
                "revisit_count": 2,
                "successful_reengagement_count": 1,
                "failed_reengagement_count": 0 if step.include_initiative else 1,
                "last_revisit_delta": 320,
                "last_revisit_volume": 600,
                "last_revisit_trade_count": 100,
                "last_defended_reaction_ticks": 10,
                "last_failed_break_ticks": 0 if step.include_initiative else 8,
                "post_failure_delta": None if step.include_initiative else 180,
                "post_failure_move_ticks": None if step.include_initiative else 10,
                "raw_features": {},
            },
        ],
        "cross_session_sequences": [
            {
                "sequence_id": f"seq-{step_key}",
                "started_at": _iso(step.observed_at - timedelta(minutes=20)),
                "last_observed_at": _iso(step.observed_at),
                "session_sequence": ["europe", step.session_code],
                "price_zone_low": step.zone_low,
                "price_zone_high": step.zone_high,
                "start_price": step.zone_low + 1.0,
                "latest_price": step.zone_high + 2.0,
                "linked_episode_ids": [],
                "linked_drive_ids": [f"drive-{step_key}"] if step.include_initiative else [],
                "linked_exertion_zone_ids": [f"zone-{step_key}"],
                "linked_event_ids": [],
                "raw_features": {},
            },
        ],
    }
    return {
        "schema_version": "1.0.0",
        "process_context_id": f"proc-{step_key}",
        "observed_at": _iso(step.observed_at),
        "source": _source_payload(case.instrument_symbol),
        "instrument": instrument,
        "process_context": process_context,
    }


def _continuous_state_payload(
    *,
    case: GoldenReplayCase,
    step: GoldenContinuousStateStep,
    instrument: dict[str, object],
    step_key: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "message_id": f"msg-{step_key}",
        "message_type": "continuous_state",
        "emitted_at": _iso(step.observed_at),
        "observed_window_start": _iso(step.observed_at - timedelta(seconds=1)),
        "observed_window_end": _iso(step.observed_at),
        "source": _source_payload(case.instrument_symbol),
        "instrument": instrument,
        "session_context": {
            "session_code": "us_regular",
            "trading_date": step.observed_at.date().isoformat(),
            "is_rth_open": True,
        },
        "price_state": {
            "last_price": step.last_price,
            "best_bid": step.last_price - float(instrument["tick_size"]),
            "best_ask": step.last_price,
            "local_range_low": step.local_low,
            "local_range_high": step.local_high,
        },
        "trade_summary": {
            "trade_count": 160,
            "volume": step.volume,
            "aggressive_buy_volume": max(1, step.volume // 2),
            "aggressive_sell_volume": max(1, step.volume // 4),
            "net_delta": step.net_delta,
        },
        "significant_liquidity": [],
        "gap_reference": None,
        "active_initiative_drive": {
            "drive_id": f"drive-live-{step_key}",
            "side": step.side,
            "started_at": _iso(step.observed_at - timedelta(minutes=2)),
            "price_low": step.drive_low,
            "price_high": step.drive_high,
            "aggressive_volume": 1400,
            "net_delta": step.net_delta,
            "trade_count": 268,
            "consumed_price_levels": 7,
            "price_travel_ticks": 57,
            "max_counter_move_ticks": 4,
            "continuation_seconds": 80,
        },
        "active_manipulation_leg": None,
        "active_measured_move": None,
        "active_post_harvest_response": None,
        "active_zone_interaction": None,
        "ema_context": None,
        "reference_levels": [],
    }
    if step.include_post_harvest_response:
        payload["active_post_harvest_response"] = {
            "response_id": f"post-harvest-{step_key}",
            "harvest_subject_id": f"drive-live-{step_key}",
            "harvest_subject_kind": "initiative_drive",
            "harvest_side": step.side,
            "harvest_completed_at": _iso(step.observed_at - timedelta(seconds=30)),
            "harvested_price_low": step.local_high - 1.0,
            "harvested_price_high": step.local_high,
            "completion_ratio": 1.0,
            "continuation_ticks_after_completion": 4,
            "consolidation_range_ticks": 7,
            "pullback_ticks": 9,
            "reversal_ticks": 14,
            "seconds_to_first_pullback": 9,
            "seconds_to_reversal": 44,
            "reached_next_opposing_liquidity": True,
            "next_opposing_liquidity_price": step.local_high - 7.0,
            "post_harvest_delta": -186,
            "outcome": "pullback",
        }
    return payload


def _event_snapshot_payload(
    *,
    case: GoldenReplayCase,
    step: GoldenEventSnapshotStep,
    instrument: dict[str, object],
    step_key: str,
) -> dict[str, object]:
    trigger_at = step.observed_at - timedelta(seconds=8)
    return {
        "schema_version": "1.0.0",
        "event_snapshot_id": f"evt-{step_key}",
        "event_type": step.event_type,
        "observed_at": _iso(step.observed_at),
        "source": {
            "system": "ATAS",
            "instance_id": "TEST",
            "adapter_version": "test",
        },
        "instrument": instrument,
        "trigger_event": {
            "event_type": step.event_type,
            "observed_at": _iso(trigger_at),
            "price": step.trigger_price,
            "details": {"swept_level": "prior_day_high"},
        },
        "decision_layers": {
            "macro_context": [
                {
                    "timeframe": "1d",
                    "bars_considered": 20,
                    "latest_range": {
                        "open": step.trigger_price - 40.0,
                        "high": step.trigger_price + 1.25,
                        "low": step.trigger_price - 42.0,
                        "close": step.trigger_price - 11.75,
                    },
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
            "intraday_bias": [
                {
                    "timeframe": "1h",
                    "bars_considered": 8,
                    "latest_range": {
                        "open": step.trigger_price - 18.75,
                        "high": step.trigger_price + 0.5,
                        "low": step.trigger_price - 14.75,
                        "close": step.trigger_price - 11.75,
                    },
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
            "setup_context": [
                {
                    "timeframe": "15m",
                    "bars_considered": 16,
                    "latest_range": {
                        "open": step.trigger_price - 8.75,
                        "high": step.trigger_price + 0.5,
                        "low": step.trigger_price - 14.75,
                        "close": step.trigger_price - 11.75,
                    },
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
            "execution_context": [
                {
                    "timeframe": "footprint",
                    "bars_considered": 1,
                    "latest_range": {
                        "open": step.trigger_price - 5.75,
                        "high": step.trigger_price + 0.5,
                        "low": step.trigger_price - 14.75,
                        "close": step.trigger_price - 11.75,
                    },
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [
                        {
                            "signal_type": "absorption",
                            "side": "sell",
                            "observed_at": _iso(trigger_at),
                            "price": step.trigger_price,
                            "magnitude": step.absorption_magnitude,
                            "notes": ["seller absorbed sweep"],
                        },
                    ],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
                {
                    "timeframe": "dom",
                    "bars_considered": 1,
                    "latest_range": {
                        "open": step.trigger_price - 3.5,
                        "high": step.trigger_price + 0.5,
                        "low": step.trigger_price - 12.25,
                        "close": step.trigger_price - 11.75,
                    },
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [
                        {
                            "signal_type": "initiative_selling",
                            "side": "sell",
                            "observed_at": _iso(step.observed_at - timedelta(seconds=2)),
                            "price": step.trigger_price - 10.75,
                            "magnitude": step.initiative_magnitude,
                            "notes": ["offers held and rotated lower"],
                        },
                    ],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
        },
    }


def _depth_snapshot_payload(
    *,
    case: GoldenReplayCase,
    step: GoldenDepthSnapshotStep,
    instrument: dict[str, object],
    step_key: str,
) -> dict[str, object]:
    levels: list[dict[str, object]] = []
    for level in step.significant_levels:
        levels.append(
            {
                "track_id": level.track_id,
                "side": level.side,
                "price": level.price,
                "current_size": level.current_size,
                "max_seen_size": level.max_seen_size,
                "distance_from_price_ticks": level.distance_from_price_ticks,
                "first_observed_at": _iso(step.observed_at - timedelta(seconds=30)),
                "last_observed_at": _iso(step.observed_at),
                "first_seen_mode": "live",
                "status": level.status,
                "touch_count": level.touch_count,
                "executed_volume_estimate": level.executed_volume_estimate,
                "replenishment_count": level.replenishment_count,
                "pull_count": level.pull_count,
                "move_count": level.move_count,
                "price_reaction_ticks": level.price_reaction_ticks,
                "heat_score": level.heat_score,
                "notes": level.notes,
                "raw_features": {"seconds_visible": 30},
            },
        )
    return {
        "schema_version": "1.0.0",
        "depth_snapshot_id": f"depth-{step_key}",
        "observed_at": _iso(step.observed_at),
        "source": {
            "system": "ATAS",
            "instance_id": "TEST",
            "adapter_version": "test",
        },
        "instrument": instrument,
        "coverage_state": step.coverage_state,
        "coverage_started_at": _iso(step.observed_at - timedelta(minutes=5)),
        "best_bid": step.best_bid,
        "best_ask": step.best_ask,
        "reference_price": step.reference_price,
        "significant_levels": levels,
    }


def _source_payload(symbol: str) -> dict[str, object]:
    return {
        "system": "ATAS",
        "instance_id": "TEST",
        "chart_instance_id": f"{symbol}-chart",
        "adapter_version": "test",
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
