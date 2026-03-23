from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.models import DegradedMode, EventPhase, TradableEventKind
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.repository import SQLiteAnalysisRepository


def test_momentum_continuation_scenario_builds_belief_and_episode(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    now = datetime.now(tz=UTC).replace(microsecond=0)

    repository.save_ingestion(
        ingestion_id="ing-hist-momo",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-momo",
        instrument_symbol="NQ",
        observed_payload=_history_bars_payload(
            symbol="NQ",
            start=now - timedelta(minutes=6),
            bars=[
                (21498.0, 21500.0, 21497.75, 21499.25, 210, 42),
                (21499.25, 21501.25, 21499.0, 21500.75, 240, 68),
                (21500.75, 21502.25, 21500.5, 21501.75, 198, 35),
                (21501.75, 21503.0, 21501.25, 21502.75, 205, 54),
                (21502.75, 21504.0, 21502.5, 21503.5, 230, 71),
                (21503.5, 21504.75, 21503.0, 21504.25, 220, 60),
            ],
            emitted_at=now,
        ),
        stored_at=now,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-momo",
        ingestion_kind="process_context",
        source_snapshot_id="proc-momo",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=now,
            point_of_control=21492.0,
            initiative_side="buy",
            zone_low=21496.5,
            zone_high=21498.0,
        ),
        stored_at=now,
    )
    repository.save_ingestion(
        ingestion_id="ing-adapter-momo",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id="msg-momo",
        instrument_symbol="NQ",
        observed_payload=_continuous_payload(
            symbol="NQ",
            observed_at=now,
            last_price=21574.25,
            local_low=21560.0,
            local_high=21574.25,
            net_delta=370,
            volume=914,
            side="buy",
            drive_low=21560.0,
            drive_high=21574.25,
        ),
        stored_at=now,
    )

    service = DeterministicRecognitionService(repository=repository)
    result = service.run_for_instrument("NQ", triggered_by="pytest_momentum")

    assert result.triggered is True
    assert result.belief_state is not None
    assert result.belief_state.event_hypotheses[0].mapped_event_kind is TradableEventKind.MOMENTUM_CONTINUATION
    assert result.belief_state.event_hypotheses[0].phase in {EventPhase.CONFIRMING, EventPhase.RESOLVED}
    assert repository.list_feature_slices(instrument_symbol="NQ", limit=10)
    assert repository.list_regime_posteriors(instrument_symbol="NQ", limit=10)
    assert repository.list_event_hypothesis_states(instrument_symbol="NQ", limit=10)
    assert any(item.event_kind is TradableEventKind.MOMENTUM_CONTINUATION for item in result.closed_episodes) or result.belief_state.event_hypotheses[0].phase is EventPhase.CONFIRMING


def test_balance_mean_reversion_scenario_prefers_balance_hypothesis(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    now = datetime.now(tz=UTC).replace(microsecond=0)

    repository.save_ingestion(
        ingestion_id="ing-hist-balance",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-balance",
        instrument_symbol="NQ",
        observed_payload=_history_bars_payload(
            symbol="NQ",
            start=now - timedelta(minutes=6),
            bars=[
                (21500.0, 21502.0, 21499.5, 21501.0, 100, 4),
                (21501.0, 21502.25, 21499.75, 21500.25, 98, -3),
                (21500.25, 21501.75, 21499.75, 21500.5, 96, 2),
                (21500.5, 21501.5, 21499.5, 21500.0, 95, -2),
                (21500.0, 21501.25, 21499.25, 21499.75, 94, -1),
                (21499.75, 21500.75, 21499.25, 21500.0, 92, 1),
            ],
            emitted_at=now,
        ),
        stored_at=now,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-balance",
        ingestion_kind="process_context",
        source_snapshot_id="proc-balance",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=now,
            point_of_control=21500.0,
            initiative_side="buy",
            zone_low=21499.5,
            zone_high=21500.5,
            include_initiative=False,
        ),
        stored_at=now,
    )

    service = DeterministicRecognitionService(repository=repository)
    result = service.run_for_instrument("NQ", triggered_by="pytest_balance")

    assert result.triggered is True
    assert result.belief_state is not None
    top = result.belief_state.event_hypotheses[0]
    assert top.mapped_event_kind is TradableEventKind.BALANCE_MEAN_REVERSION
    assert result.belief_state.transition_watch
    assert result.belief_state.missing_confirmation
    assert result.belief_state.active_anchors


def test_absorption_reversal_scenario_runs_in_degraded_no_depth_mode_without_depth(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    now = datetime.now(tz=UTC).replace(microsecond=0)

    repository.save_ingestion(
        ingestion_id="ing-event-absorb",
        ingestion_kind="event_snapshot",
        source_snapshot_id="evt-absorb",
        instrument_symbol="NQ",
        observed_payload=_event_snapshot_payload(symbol="NQ", observed_at=now),
        stored_at=now,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-absorb",
        ingestion_kind="process_context",
        source_snapshot_id="proc-absorb",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=now,
            point_of_control=21572.0,
            initiative_side="sell",
            zone_low=21579.75,
            zone_high=21580.75,
            include_initiative=False,
            include_liquidity_episode=True,
        ),
        stored_at=now,
    )

    service = DeterministicRecognitionService(repository=repository)
    result = service.run_for_instrument("NQ", triggered_by="pytest_absorption")

    assert result.triggered is True
    assert result.belief_state is not None
    assert result.recognition_mode is not None
    assert result.recognition_mode.value == "degraded_no_depth"
    assert result.data_status is not None
    assert result.data_status.depth_available is False
    assert result.data_status.dom_available is False
    assert {item.mapped_event_kind for item in result.belief_state.event_hypotheses[:2]} == {
        TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
    }
    assert result.belief_state.event_hypotheses[0].hypothesis_kind.value in {
        "absorption_accumulation",
        "reversal_preparation",
    }


def test_stale_macro_keeps_belief_output_available_with_versions(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    now = datetime(2020, 1, 2, 14, 30, tzinfo=UTC)

    repository.save_ingestion(
        ingestion_id="ing-hist-stale",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-stale",
        instrument_symbol="NQ",
        observed_payload=_history_bars_payload(
            symbol="NQ",
            start=now - timedelta(minutes=6),
            bars=[
                (21500.0, 21501.0, 21498.75, 21499.0, 118, -9),
                (21499.0, 21500.0, 21498.5, 21499.25, 96, 3),
                (21499.25, 21500.25, 21498.75, 21499.75, 92, 4),
                (21499.75, 21500.5, 21499.0, 21500.0, 88, 2),
                (21500.0, 21500.75, 21499.25, 21499.5, 90, -2),
                (21499.5, 21500.25, 21499.0, 21499.75, 86, 1),
            ],
            emitted_at=now,
        ),
        stored_at=now,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-stale",
        ingestion_kind="process_context",
        source_snapshot_id="proc-stale",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=now,
            point_of_control=21499.75,
            initiative_side="sell",
            zone_low=21499.25,
            zone_high=21500.25,
            include_initiative=False,
        ),
        stored_at=now,
    )

    service = DeterministicRecognitionService(repository=repository)
    result = service.run_for_instrument("NQ", triggered_by="pytest_stale_macro")

    assert result.triggered is True
    assert result.data_status is not None
    assert DegradedMode.STALE_MACRO in result.data_status.degraded_modes
    assert result.belief_state is not None
    assert result.belief_state.profile_version == result.profile_version
    assert result.belief_state.engine_version == result.engine_version
    assert len(result.belief_state.regime_posteriors) == 3
    assert len(result.belief_state.event_hypotheses) == 3
    assert result.belief_state.active_anchors
    assert result.belief_state.missing_confirmation
    assert result.belief_state.transition_watch
    assert result.belief_state.data_status.completeness == "partial"


def _history_bars_payload(*, symbol: str, start: datetime, bars: list[tuple[float, float, float, float, int, int]], emitted_at: datetime) -> dict[str, object]:
    payload_bars = []
    for index, (open_, high, low, close, volume, delta) in enumerate(bars):
        bar_start = start + timedelta(minutes=index)
        payload_bars.append(
            {
                "started_at": _iso(bar_start),
                "ended_at": _iso(bar_start + timedelta(seconds=59)),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "delta": delta,
                "bid_volume": max(1, volume // 3),
                "ask_volume": max(1, volume // 2),
            },
        )
    return {
        "schema_version": "1.0.0",
        "message_id": f"collector-history-{symbol.lower()}",
        "message_type": "history_bars",
        "emitted_at": _iso(emitted_at),
        "observed_window_start": _iso(start),
        "observed_window_end": _iso(start + timedelta(minutes=len(bars) - 1, seconds=59)),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "bar_timeframe": "1m",
        "bars": payload_bars,
    }


def _process_context_payload(
    *,
    symbol: str,
    observed_at: datetime,
    point_of_control: float,
    initiative_side: str,
    zone_low: float,
    zone_high: float,
    include_initiative: bool = True,
    include_liquidity_episode: bool = False,
) -> dict[str, object]:
    process_context = {
        "session_windows": [
            {
                "session_code": "us_regular",
                "started_at": _iso(observed_at - timedelta(minutes=30)),
                "ended_at": _iso(observed_at),
                "latest_range": {"open": point_of_control - 2.0, "high": point_of_control + 2.5, "low": point_of_control - 2.5, "close": point_of_control},
                "value_area": {"low": point_of_control - 1.0, "high": point_of_control + 1.0, "point_of_control": point_of_control},
                "session_stats": {"volume": 1000, "delta": 0, "trades": 300},
                "key_levels": [],
            }
        ],
        "second_features": [],
        "liquidity_episodes": [
            {
                "episode_id": "liq-episode-1",
                "started_at": _iso(observed_at - timedelta(minutes=8)),
                "ended_at": _iso(observed_at - timedelta(minutes=4)),
                "side": "sell",
                "price_low": zone_low,
                "price_high": zone_high,
                "executed_volume_against": 1200,
                "replenishment_count": 5,
                "pull_count": 1,
                "price_rejection_ticks": 14,
                "raw_features": {},
            }
        ] if include_liquidity_episode else [],
        "initiative_drives": [
            {
                "drive_id": "drive-1",
                "started_at": _iso(observed_at - timedelta(minutes=3)),
                "ended_at": _iso(observed_at - timedelta(minutes=1)),
                "side": initiative_side,
                "price_low": zone_low,
                "price_high": zone_high + 8.0,
                "aggressive_volume": 800,
                "net_delta": 620 if initiative_side == "buy" else -620,
                "trade_count": 180,
                "consumed_price_levels": 5,
                "price_travel_ticks": 20,
                "max_counter_move_ticks": 4,
                "continuation_seconds": 60,
                "raw_features": {},
            }
        ] if include_initiative else [],
        "measured_moves": [],
        "manipulation_legs": [],
        "gap_references": [
            {
                "gap_id": "gap-1",
                "session_code": "us_premarket",
                "opened_at": _iso(observed_at - timedelta(hours=1)),
                "direction": "up",
                "prior_reference_price": point_of_control - 3.0,
                "current_open_price": point_of_control - 2.0,
                "gap_low": point_of_control - 3.0,
                "gap_high": point_of_control - 2.0,
                "gap_size_ticks": 4,
                "first_touch_at": _iso(observed_at - timedelta(minutes=10)),
                "max_fill_ticks": 2,
                "fill_ratio": 0.5,
                "fill_attempt_count": 1,
                "accepted_inside_gap": True,
                "rejected_from_gap": False,
                "fully_filled_at": None,
                "raw_features": {},
            }
        ],
        "post_harvest_responses": [],
        "exertion_zones": [
            {
                "zone_id": "zone-1",
                "source_drive_id": "drive-1",
                "side": initiative_side,
                "price_low": zone_low,
                "price_high": zone_high,
                "established_at": _iso(observed_at - timedelta(minutes=15)),
                "last_interacted_at": _iso(observed_at - timedelta(minutes=1)),
                "establishing_volume": 1500,
                "establishing_delta": 900 if initiative_side == "buy" else -900,
                "establishing_trade_count": 200,
                "peak_price_level_volume": 500,
                "revisit_count": 2,
                "successful_reengagement_count": 1,
                "failed_reengagement_count": 1 if not include_initiative else 0,
                "last_revisit_delta": 320,
                "last_revisit_volume": 600,
                "last_revisit_trade_count": 100,
                "last_defended_reaction_ticks": 10,
                "last_failed_break_ticks": 8 if not include_initiative else 0,
                "post_failure_delta": 180 if not include_initiative else None,
                "post_failure_move_ticks": 10 if not include_initiative else None,
                "raw_features": {},
            }
        ],
        "cross_session_sequences": [
            {
                "sequence_id": "seq-1",
                "started_at": _iso(observed_at - timedelta(minutes=20)),
                "last_observed_at": _iso(observed_at),
                "session_sequence": ["europe", "us_regular"],
                "price_zone_low": zone_low,
                "price_zone_high": zone_high,
                "start_price": zone_low + 1.0,
                "latest_price": zone_high + 2.0,
                "linked_episode_ids": [],
                "linked_drive_ids": ["drive-1"] if include_initiative else [],
                "linked_exertion_zone_ids": ["zone-1"],
                "linked_event_ids": [],
                "raw_features": {},
            }
        ],
    }
    return {
        "schema_version": "1.0.0",
        "process_context_id": f"proc-{symbol.lower()}",
        "observed_at": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "process_context": process_context,
    }


def _continuous_payload(
    *,
    symbol: str,
    observed_at: datetime,
    last_price: float,
    local_low: float,
    local_high: float,
    net_delta: int,
    volume: int,
    side: str,
    drive_low: float,
    drive_high: float,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "message_id": f"msg-{symbol.lower()}",
        "message_type": "continuous_state",
        "emitted_at": _iso(observed_at),
        "observed_window_start": _iso(observed_at - timedelta(seconds=1)),
        "observed_window_end": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "session_context": {"session_code": "us_regular", "trading_date": observed_at.date().isoformat(), "is_rth_open": True},
        "price_state": {"last_price": last_price, "best_bid": last_price - 0.25, "best_ask": last_price, "local_range_low": local_low, "local_range_high": local_high},
        "trade_summary": {"trade_count": 160, "volume": volume, "aggressive_buy_volume": max(1, volume // 2), "aggressive_sell_volume": max(1, volume // 4), "net_delta": net_delta},
        "significant_liquidity": [],
        "gap_reference": None,
        "active_initiative_drive": {
            "drive_id": "drive-live",
            "side": side,
            "started_at": _iso(observed_at - timedelta(minutes=2)),
            "price_low": drive_low,
            "price_high": drive_high,
            "aggressive_volume": 1400,
            "net_delta": net_delta,
            "trade_count": 268,
            "consumed_price_levels": 7,
            "price_travel_ticks": 57,
            "max_counter_move_ticks": 4,
            "continuation_seconds": 80,
        },
        "active_manipulation_leg": None,
        "active_measured_move": None,
        "active_post_harvest_response": {
            "response_id": "post-harvest-1",
            "harvest_subject_id": "drive-live",
            "harvest_subject_kind": "initiative_drive",
            "harvest_side": side,
            "harvest_completed_at": _iso(observed_at - timedelta(seconds=30)),
            "harvested_price_low": local_high - 1.0,
            "harvested_price_high": local_high,
            "completion_ratio": 1.0,
            "continuation_ticks_after_completion": 4,
            "consolidation_range_ticks": 7,
            "pullback_ticks": 9,
            "reversal_ticks": 14,
            "seconds_to_first_pullback": 9,
            "seconds_to_reversal": 44,
            "reached_next_opposing_liquidity": True,
            "next_opposing_liquidity_price": local_high - 7.0,
            "post_harvest_delta": -186,
            "outcome": "pullback",
        },
        "active_zone_interaction": None,
        "ema_context": None,
        "reference_levels": [],
    }


def _event_snapshot_payload(*, symbol: str, observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "event_snapshot_id": f"evt-{symbol.lower()}",
        "event_type": "liquidity_sweep",
        "observed_at": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "trigger_event": {"event_type": "liquidity_sweep", "observed_at": _iso(observed_at - timedelta(seconds=8)), "price": 21580.75, "details": {"swept_level": "prior_day_high"}},
        "decision_layers": {
            "macro_context": [{"timeframe": "1d", "bars_considered": 20, "latest_range": {"open": 21540.0, "high": 21582.0, "low": 21538.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "intraday_bias": [{"timeframe": "1h", "bars_considered": 8, "latest_range": {"open": 21562.0, "high": 21581.25, "low": 21566.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "setup_context": [{"timeframe": "15m", "bars_considered": 16, "latest_range": {"open": 21572.0, "high": 21581.25, "low": 21566.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "execution_context": [
                {
                    "timeframe": "footprint",
                    "bars_considered": 1,
                    "latest_range": {"open": 21575.0, "high": 21581.25, "low": 21566.0, "close": 21569.0},
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [{"signal_type": "absorption", "side": "sell", "observed_at": _iso(observed_at - timedelta(seconds=8)), "price": 21580.75, "magnitude": 0.88, "notes": ["seller absorbed sweep"]}],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
                {
                    "timeframe": "dom",
                    "bars_considered": 1,
                    "latest_range": {"open": 21577.25, "high": 21581.25, "low": 21568.5, "close": 21569.0},
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [{"signal_type": "initiative_selling", "side": "sell", "observed_at": _iso(observed_at - timedelta(seconds=2)), "price": 21570.0, "magnitude": 0.71, "notes": ["offers held and rotated lower"]}],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
        },
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
