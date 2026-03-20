from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from atas_market_structure.regime_monitor_services import RegimeMonitor

from atas_market_structure.models import (
    AdapterBurstWindow,
    AdapterContinuousStatePayload,
    AdapterMeasuredMoveState,
    AdapterPostHarvestResponseState,
    AdapterSecondFeature,
    AdapterSessionContext,
    AdapterTradeSummary,
    AdapterTriggerBurstPayload,
    AdapterTriggerType,
    AdapterZoneInteraction,
    DecisionLayerSet,
    EventSnapshotPayload,
    EventType,
    GapDirection,
    LiquidityLevelType,
    MarketStructurePayload,
    MeasurementReferenceKind,
    ObservedContextWindow,
    ObservedCrossSessionSequence,
    ObservedEventMarker,
    ObservedExertionZone,
    ObservedGapReference,
    ObservedInitiativeDrive,
    ObservedLiquidityEpisode,
    ObservedLiquidityLevel,
    ObservedManipulationLeg,
    ObservedMeasuredMove,
    ObservedOrderFlowSignal,
    ObservedPostHarvestResponse,
    ObservedProcessContext,
    ObservedRange,
    ObservedSecondFeature,
    ObservedSessionStats,
    ObservedSessionWindow,
    ObservedSwingPoint,
    ObservedValueArea,
    OrderFlowSignalType,
    PostHarvestOutcome,
    SessionCode,
    StructureSide,
    SwingKind,
    Timeframe,
)


MEASURED_MULTIPLE_PATTERN = re.compile(r"measured(?:_move)?_(?P<multiple>\d+(?:\.\d+)?)x", re.IGNORECASE)


@dataclass(frozen=True)
class BurstAggregate:
    opened_at: datetime
    closed_at: datetime
    price_range: ObservedRange
    trade_count: int
    volume: int
    delta: int
    best_bid: float | None
    best_ask: float | None
    depth_imbalance: float | None


class AdapterPayloadBridge:
    """Maps ATAS adapter payloads into durable market-structure payloads."""

    def __init__(self, regime_monitor: RegimeMonitor | None = None) -> None:
        self.regime_monitor = regime_monitor or RegimeMonitor()

    def build_market_structure(self, payload: AdapterContinuousStatePayload) -> MarketStructurePayload:
        dominant_side = self._dominant_side_from_trade_summary(
            payload.trade_summary,
            payload.active_initiative_drive.side if payload.active_initiative_drive is not None else None,
        )
        return MarketStructurePayload(
            schema_version=payload.schema_version,
            snapshot_id=f"bridge-ms-{payload.message_id}",
            observed_at=payload.observed_window_end,
            source=payload.source.model_dump(mode="json"),
            instrument=payload.instrument.model_dump(mode="json"),
            decision_layers=self._continuous_decision_layers(payload, dominant_side).model_dump(mode="json"),
            process_context=self._continuous_process_context(payload, dominant_side).model_dump(mode="json"),
            observed_events=[item.model_dump(mode="json") for item in self._continuous_events(payload)],
        )

    def build_event_snapshot(self, payload: AdapterTriggerBurstPayload) -> EventSnapshotPayload:
        aggregate = self._aggregate_burst(payload.pre_window, payload.event_window, payload.post_window)
        dominant_side = self._dominant_side_from_burst(payload)
        event_type = self._event_type_from_trigger(payload.trigger.trigger_type)
        return EventSnapshotPayload(
            schema_version=payload.schema_version,
            event_snapshot_id=f"bridge-evt-{payload.message_id}",
            event_type=event_type,
            observed_at=payload.trigger.triggered_at,
            source=payload.source.model_dump(mode="json"),
            instrument=payload.instrument.model_dump(mode="json"),
            trigger_event=ObservedEventMarker(
                event_type=event_type,
                observed_at=payload.trigger.triggered_at,
                price=payload.trigger.price,
                details={
                    "adapter_trigger_type": payload.trigger.trigger_type.value,
                    "reason_codes": payload.trigger.reason_codes,
                    "message_id": payload.message_id,
                },
            ).model_dump(mode="json"),
            decision_layers=self._burst_decision_layers(payload, aggregate, dominant_side).model_dump(mode="json"),
            process_context=self._burst_process_context(payload, aggregate, dominant_side).model_dump(mode="json"),
        )

    def _continuous_decision_layers(
        self,
        payload: AdapterContinuousStatePayload,
        dominant_side: StructureSide,
    ) -> DecisionLayerSet:
        session = payload.session_context
        price_state = payload.price_state
        trade_summary = payload.trade_summary
        liquidity_levels = self._liquidity_levels_from_continuous(payload)
        signals = self._continuous_signals(payload, dominant_side)
        value_area = self._prior_value_area(session)
        session_stats = ObservedSessionStats(
            volume=trade_summary.volume,
            delta=trade_summary.net_delta,
            trades=trade_summary.trade_count,
        )
        macro_range = ObservedRange(
            open=session.prior_rth_close,
            high=max(session.prior_rth_high, price_state.local_range_high, price_state.opening_range_high or price_state.local_range_high),
            low=min(session.prior_rth_low, price_state.local_range_low, price_state.opening_range_low or price_state.local_range_low),
            close=price_state.last_price,
        )
        execution_range = ObservedRange(
            open=price_state.best_bid or price_state.last_price,
            high=price_state.local_range_high,
            low=price_state.local_range_low,
            close=price_state.last_price,
        )
        setup_raw = {
            "bridge_source": "adapter_continuous_state",
            "opening_range_size_ticks": price_state.opening_range_size_ticks,
        }
        if payload.ema_context is not None:
            setup_raw["ema20_reclaim_confirmed"] = payload.ema_context.ema20_reclaim_confirmed
            setup_raw["bars_above_ema20_after_reclaim"] = payload.ema_context.bars_above_ema20_after_reclaim
        if payload.active_zone_interaction is not None:
            setup_raw["buyers_hitting_same_level_count"] = payload.active_zone_interaction.buyers_hitting_same_level_count
            setup_raw["sellers_hitting_same_level_count"] = payload.active_zone_interaction.sellers_hitting_same_level_count

        return DecisionLayerSet(
            macro_context=[
                self._window(Timeframe.DAY_1, 20, macro_range, payload.observed_window_end, dominant_side, liquidity_levels[:2], signals[:1], value_area, session_stats, {"bridge_source": "adapter_continuous_state"}),
            ],
            intraday_bias=[
                self._window(Timeframe.HOUR_1, 12, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:2], signals[:1], None, None, {"bridge_source": "adapter_continuous_state"}),
                self._window(Timeframe.MIN_30, 20, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:3], signals[:2], None, None, {"trade_count": trade_summary.trade_count}),
            ],
            setup_context=[
                self._window(Timeframe.MIN_15, 16, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:2], signals[:2], None, None, setup_raw),
                self._window(Timeframe.MIN_5, 24, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:3], signals[:2], None, None, setup_raw),
            ],
            execution_context=[
                self._window(Timeframe.MIN_1, 20, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:3], signals, None, None, {"net_delta": trade_summary.net_delta}),
                self._window(Timeframe.DOM, 1, execution_range, payload.observed_window_end, dominant_side, liquidity_levels[:4], signals, None, None, {"significant_liquidity_count": len(payload.significant_liquidity)}),
            ],
        )

    def _continuous_process_context(
        self,
        payload: AdapterContinuousStatePayload,
        dominant_side: StructureSide,
    ) -> ObservedProcessContext:
        liquidity_episode = self._episode_from_zone(payload.active_zone_interaction, dominant_side, payload.observed_window_end)
        initiative_drive = self._continuous_drive(payload)
        measured_move = self._continuous_measured_move(payload.active_measured_move, payload.observed_window_start, payload.observed_window_end)
        manipulation_leg = self._continuous_leg(payload)
        gap_reference = self._continuous_gap(payload)
        post_harvest = self._continuous_post_harvest(payload.active_post_harvest_response)
        exertion_zone = self._continuous_exertion_zone(payload, liquidity_episode, initiative_drive, dominant_side)
        cross_session = self._continuous_cross_session(payload, liquidity_episode, initiative_drive, exertion_zone)
        return ObservedProcessContext(
            session_windows=self._continuous_session_windows(payload),
            second_features=[],
            liquidity_episodes=[liquidity_episode] if liquidity_episode is not None else [],
            initiative_drives=[initiative_drive] if initiative_drive is not None else [],
            measured_moves=[measured_move] if measured_move is not None else [],
            manipulation_legs=[manipulation_leg] if manipulation_leg is not None else [],
            gap_references=[gap_reference] if gap_reference is not None else [],
            post_harvest_responses=[post_harvest] if post_harvest is not None else [],
            exertion_zones=[exertion_zone] if exertion_zone is not None else [],
            cross_session_sequences=[cross_session] if cross_session is not None else [],
        )

    def _burst_decision_layers(
        self,
        payload: AdapterTriggerBurstPayload,
        aggregate: BurstAggregate,
        dominant_side: StructureSide,
    ) -> DecisionLayerSet:
        liquidity_levels = self._liquidity_levels_from_burst(payload)
        signals = self._burst_signals(payload, dominant_side)
        session_stats = ObservedSessionStats(volume=aggregate.volume, delta=aggregate.delta, trades=aggregate.trade_count)
        shared_raw = {"bridge_source": "adapter_trigger_burst", "trigger_type": payload.trigger.trigger_type.value}
        return DecisionLayerSet(
            macro_context=[self._window(Timeframe.DAY_1, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:2], signals[:1], None, session_stats, shared_raw)],
            intraday_bias=[
                self._window(Timeframe.HOUR_1, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:2], signals[:2], None, None, {"reason_codes": payload.trigger.reason_codes}),
                self._window(Timeframe.MIN_30, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:3], signals[:2], None, None, {"bookmark_count": self._bookmark_count(payload)}),
            ],
            setup_context=[
                self._window(Timeframe.MIN_15, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:3], signals[:2], None, None, shared_raw),
                self._window(Timeframe.MIN_5, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:3], signals[:2], None, None, {"post_window_second_features": len(payload.post_window.second_features)}),
            ],
            execution_context=[
                self._window(Timeframe.MIN_1, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:4], signals, None, None, {"trade_event_count": self._trade_count(payload), "depth_event_count": self._depth_count(payload)}),
                self._window(Timeframe.FOOTPRINT, 1, aggregate.price_range, payload.trigger.triggered_at, dominant_side, liquidity_levels[:4], signals, None, None, {"depth_imbalance": aggregate.depth_imbalance}),
            ],
        )

    def _burst_process_context(
        self,
        payload: AdapterTriggerBurstPayload,
        aggregate: BurstAggregate,
        dominant_side: StructureSide,
    ) -> ObservedProcessContext:
        second_features = [self._second_feature(feature) for feature in self._iter_second_features(payload)]
        liquidity_episodes = self._burst_episodes(payload, dominant_side)
        initiative_drive = self._burst_drive(payload, aggregate, dominant_side)
        measured_move = self._burst_measured_move(payload, initiative_drive)
        post_harvest = self._burst_post_harvest(payload, aggregate, dominant_side)
        exertion_zone = self._burst_exertion_zone(payload, liquidity_episodes, initiative_drive, dominant_side)
        return ObservedProcessContext(
            session_windows=[],
            second_features=second_features,
            liquidity_episodes=liquidity_episodes,
            initiative_drives=[initiative_drive] if initiative_drive is not None else [],
            measured_moves=[measured_move] if measured_move is not None else [],
            manipulation_legs=[],
            gap_references=[],
            post_harvest_responses=[post_harvest] if post_harvest is not None else [],
            exertion_zones=[exertion_zone] if exertion_zone is not None else [],
            cross_session_sequences=[],
        )

    def _continuous_events(self, payload: AdapterContinuousStatePayload) -> list[ObservedEventMarker]:
        events: list[ObservedEventMarker] = []
        if payload.gap_reference is not None and payload.gap_reference.first_touch_at is not None:
            events.append(
                ObservedEventMarker(
                    event_type=EventType.LIQUIDITY_SWEEP,
                    observed_at=payload.gap_reference.first_touch_at,
                    price=payload.gap_reference.gap_low if payload.gap_reference.direction is GapDirection.UP else payload.gap_reference.gap_high,
                    details={"bridge_origin": "gap_first_touch", "gap_id": payload.gap_reference.gap_id},
                ),
            )
        if payload.active_post_harvest_response is not None:
            outcome = payload.active_post_harvest_response.outcome
            event_type = EventType.CHANGE_OF_CHARACTER if outcome is PostHarvestOutcome.REVERSAL else EventType.OTHER
            events.append(
                ObservedEventMarker(
                    event_type=event_type,
                    observed_at=payload.active_post_harvest_response.harvest_completed_at,
                    price=payload.active_post_harvest_response.next_opposing_liquidity_price,
                    details={"bridge_origin": "post_harvest_response", "outcome": outcome.value},
                ),
            )
        return events

    def _continuous_session_windows(self, payload: AdapterContinuousStatePayload) -> list[ObservedSessionWindow]:
        session = payload.session_context
        price_state = payload.price_state
        windows = [
            ObservedSessionWindow(
                session_code=session.session_code,
                started_at=payload.observed_window_start,
                ended_at=payload.observed_window_end,
                latest_range=ObservedRange(
                    open=price_state.best_bid or price_state.last_price,
                    high=price_state.local_range_high,
                    low=price_state.local_range_low,
                    close=price_state.last_price,
                ),
                value_area=self._prior_value_area(session),
                session_stats=ObservedSessionStats(
                    volume=payload.trade_summary.volume,
                    delta=payload.trade_summary.net_delta,
                    trades=payload.trade_summary.trade_count,
                ),
                key_levels=self._liquidity_levels_from_continuous(payload)[:3],
            ),
        ]
        if session.overnight_high is not None and session.overnight_low is not None:
            windows.append(
                ObservedSessionWindow(
                    session_code=SessionCode.US_PREMARKET,
                    started_at=payload.observed_window_start,
                    ended_at=payload.observed_window_start,
                    latest_range=ObservedRange(
                        open=session.prior_rth_close,
                        high=session.overnight_high,
                        low=session.overnight_low,
                        close=session.overnight_mid or session.overnight_high,
                    ),
                    value_area=self._prior_value_area(session),
                    session_stats=None,
                    key_levels=[],
                ),
            )
        return windows

    def _continuous_signals(
        self,
        payload: AdapterContinuousStatePayload,
        dominant_side: StructureSide,
    ) -> list[ObservedOrderFlowSignal]:
        signals: list[ObservedOrderFlowSignal] = []
        magnitude = self._delta_magnitude(payload.trade_summary)
        if dominant_side is StructureSide.BUY:
            signals.append(
                ObservedOrderFlowSignal(
                    signal_type=OrderFlowSignalType.INITIATIVE_BUYING,
                    side=StructureSide.BUY,
                    observed_at=payload.observed_window_end,
                    price=payload.price_state.last_price,
                    magnitude=magnitude,
                    notes=["adapter bridge: buy-side initiative from net delta"],
                ),
            )
        elif dominant_side is StructureSide.SELL:
            signals.append(
                ObservedOrderFlowSignal(
                    signal_type=OrderFlowSignalType.INITIATIVE_SELLING,
                    side=StructureSide.SELL,
                    observed_at=payload.observed_window_end,
                    price=payload.price_state.last_price,
                    magnitude=magnitude,
                    notes=["adapter bridge: sell-side initiative from net delta"],
                ),
            )
        zone = payload.active_zone_interaction
        if zone is not None and zone.replenishment_count > zone.pull_count and zone.price_rejection_ticks > 0:
            zone_side = self._zone_side(zone, dominant_side)
            signals.append(
                ObservedOrderFlowSignal(
                    signal_type=OrderFlowSignalType.STACKED_IMBALANCE if zone_side is dominant_side else OrderFlowSignalType.ABSORPTION,
                    side=zone_side,
                    observed_at=payload.observed_window_end,
                    price=(zone.zone_low + zone.zone_high) / 2,
                    magnitude=min(1.0, 0.2 + (zone.replenishment_count * 0.12)),
                    notes=[
                        f"buyers_hitting_same_level_count={zone.buyers_hitting_same_level_count}",
                        f"sellers_hitting_same_level_count={zone.sellers_hitting_same_level_count}",
                    ],
                ),
            )
        return signals

    def _burst_signals(
        self,
        payload: AdapterTriggerBurstPayload,
        dominant_side: StructureSide,
    ) -> list[ObservedOrderFlowSignal]:
        side = dominant_side if dominant_side is not StructureSide.NEUTRAL else StructureSide.BUY
        signal_type = OrderFlowSignalType.INITIATIVE_BUYING if side is StructureSide.BUY else OrderFlowSignalType.INITIATIVE_SELLING
        signals = [
            ObservedOrderFlowSignal(
                signal_type=signal_type,
                side=side,
                observed_at=payload.trigger.triggered_at,
                price=payload.trigger.price,
                magnitude=min(1.0, 0.25 + (len(payload.trigger.reason_codes) * 0.08)),
                notes=[f"adapter trigger: {code}" for code in payload.trigger.reason_codes],
            ),
        ]
        if payload.trigger.trigger_type in {AdapterTriggerType.FAILED_OVERHEAD_CAPPING, AdapterTriggerType.OFFER_REVERSAL_RELEASE}:
            signals.append(
                ObservedOrderFlowSignal(
                    signal_type=OrderFlowSignalType.ABSORPTION,
                    side=StructureSide.SELL if side is StructureSide.BUY else StructureSide.BUY,
                    observed_at=payload.trigger.triggered_at,
                    price=payload.trigger.price,
                    magnitude=0.72,
                    notes=["failed cap or offer reversal context"],
                ),
            )
        return signals

    def _continuous_drive(self, payload: AdapterContinuousStatePayload) -> ObservedInitiativeDrive | None:
        drive = payload.active_initiative_drive
        if drive is None:
            return None
        if not self._drive_passes_dynamic_thresholds(
            instrument_symbol=payload.instrument.symbol,
            observed_at=payload.observed_window_end,
            tick_size=payload.instrument.tick_size,
            price_travel_ticks=drive.price_travel_ticks,
            net_delta=drive.net_delta,
            fallback_price_range=payload.price_state.local_range_high - payload.price_state.local_range_low,
            fallback_volume=payload.trade_summary.volume,
            fallback_abs_delta=abs(payload.trade_summary.net_delta),
        ):
            return None
        return ObservedInitiativeDrive(
            drive_id=drive.drive_id,
            started_at=drive.started_at,
            ended_at=payload.observed_window_end,
            side=drive.side,
            price_low=drive.price_low,
            price_high=drive.price_high,
            aggressive_volume=drive.aggressive_volume,
            net_delta=drive.net_delta,
            trade_count=drive.trade_count,
            consumed_price_levels=drive.consumed_price_levels,
            price_travel_ticks=drive.price_travel_ticks,
            max_counter_move_ticks=drive.max_counter_move_ticks,
            continuation_seconds=drive.continuation_seconds,
            raw_features={"bridge_source": "adapter_continuous_state"},
        )

    def _continuous_measured_move(
        self,
        move: AdapterMeasuredMoveState | None,
        observed_window_start: datetime,
        observed_window_end: datetime,
    ) -> ObservedMeasuredMove | None:
        if move is None:
            return None
        return ObservedMeasuredMove(
            measurement_id=move.measurement_id,
            measured_subject_id=move.measured_subject_id,
            measured_subject_kind=move.measured_subject_kind,
            started_at=observed_window_start,
            ended_at=observed_window_end,
            side=move.side,
            anchor_price=move.anchor_price,
            latest_price=move.latest_price,
            achieved_distance_ticks=move.achieved_distance_ticks,
            reference_kind=move.reference_kind,
            reference_id=move.reference_id,
            reference_distance_ticks=move.reference_distance_ticks,
            achieved_multiple=move.achieved_multiple,
            body_confirmed_threshold_multiple=move.body_confirmed_threshold_multiple,
            next_target_multiple=move.next_target_multiple,
            invalidated=move.invalidated,
            raw_features={"bridge_source": "adapter_continuous_state"},
        )

    def _continuous_leg(self, payload: AdapterContinuousStatePayload) -> ObservedManipulationLeg | None:
        leg = payload.active_manipulation_leg
        if leg is None:
            return None
        return ObservedManipulationLeg(
            leg_id=leg.leg_id,
            started_at=leg.started_at,
            ended_at=leg.ended_at,
            side=leg.side,
            price_low=leg.price_low,
            price_high=leg.price_high,
            displacement_ticks=leg.displacement_ticks,
            linked_zone_id=payload.active_zone_interaction.zone_id if payload.active_zone_interaction is not None else None,
            primary_objective_ticks=leg.primary_objective_ticks,
            secondary_objective_ticks=leg.secondary_objective_ticks,
            primary_objective_reached=leg.primary_objective_reached,
            secondary_objective_reached=leg.secondary_objective_reached,
            raw_features={"bridge_source": "adapter_continuous_state"},
        )

    def _continuous_gap(self, payload: AdapterContinuousStatePayload) -> ObservedGapReference | None:
        gap = payload.gap_reference
        if gap is None:
            return None
        prior_reference_price = gap.gap_low if gap.direction is GapDirection.UP else gap.gap_high
        current_open_price = gap.gap_high if gap.direction is GapDirection.UP else gap.gap_low
        return ObservedGapReference(
            gap_id=gap.gap_id,
            session_code=payload.session_context.session_code,
            opened_at=gap.opened_at,
            direction=gap.direction,
            prior_reference_price=prior_reference_price,
            current_open_price=current_open_price,
            gap_low=gap.gap_low,
            gap_high=gap.gap_high,
            gap_size_ticks=gap.gap_size_ticks,
            first_touch_at=gap.first_touch_at,
            max_fill_ticks=gap.max_fill_ticks,
            fill_ratio=gap.fill_ratio,
            fill_attempt_count=gap.fill_attempt_count,
            accepted_inside_gap=gap.accepted_inside_gap,
            rejected_from_gap=gap.rejected_from_gap,
            fully_filled_at=gap.fully_filled_at,
            raw_features={"bridge_source": "adapter_continuous_state"},
        )

    def _continuous_post_harvest(self, response: AdapterPostHarvestResponseState | None) -> ObservedPostHarvestResponse | None:
        if response is None:
            return None
        return ObservedPostHarvestResponse(
            response_id=response.response_id,
            harvest_subject_id=response.harvest_subject_id,
            harvest_subject_kind=response.harvest_subject_kind,
            harvest_completed_at=response.harvest_completed_at,
            harvest_side=response.harvest_side,
            harvested_price_low=response.harvested_price_low,
            harvested_price_high=response.harvested_price_high,
            completion_ratio=response.completion_ratio,
            continuation_ticks_after_completion=response.continuation_ticks_after_completion,
            consolidation_range_ticks=response.consolidation_range_ticks,
            pullback_ticks=response.pullback_ticks,
            reversal_ticks=response.reversal_ticks,
            seconds_to_first_pullback=response.seconds_to_first_pullback,
            seconds_to_reversal=response.seconds_to_reversal,
            reached_next_opposing_liquidity=response.reached_next_opposing_liquidity,
            next_opposing_liquidity_price=response.next_opposing_liquidity_price,
            post_harvest_delta=response.post_harvest_delta,
            outcome=response.outcome,
            raw_features={"bridge_source": "adapter_continuous_state"},
        )

    def _continuous_exertion_zone(
        self,
        payload: AdapterContinuousStatePayload,
        liquidity_episode: ObservedLiquidityEpisode | None,
        initiative_drive: ObservedInitiativeDrive | None,
        dominant_side: StructureSide,
    ) -> ObservedExertionZone | None:
        if liquidity_episode is None:
            return None
        return ObservedExertionZone(
            zone_id=f"zone-{liquidity_episode.episode_id}",
            source_drive_id=initiative_drive.drive_id if initiative_drive is not None else liquidity_episode.episode_id,
            side=initiative_drive.side if initiative_drive is not None else (liquidity_episode.side if liquidity_episode.side is not StructureSide.NEUTRAL else dominant_side),
            price_low=liquidity_episode.price_low,
            price_high=liquidity_episode.price_high,
            established_at=liquidity_episode.started_at,
            last_interacted_at=payload.observed_window_end,
            establishing_volume=max(liquidity_episode.executed_volume_against, initiative_drive.aggressive_volume if initiative_drive is not None else payload.trade_summary.volume),
            establishing_delta=initiative_drive.net_delta if initiative_drive is not None else payload.trade_summary.net_delta,
            establishing_trade_count=initiative_drive.trade_count if initiative_drive is not None else payload.trade_summary.trade_count,
            peak_price_level_volume=max((level.current_size for level in payload.significant_liquidity if liquidity_episode.price_low <= level.price <= liquidity_episode.price_high), default=None),
            revisit_count=1,
            successful_reengagement_count=1 if liquidity_episode.price_rejection_ticks > 0 else 0,
            failed_reengagement_count=1 if liquidity_episode.pull_count > liquidity_episode.replenishment_count else 0,
            last_revisit_delta=payload.trade_summary.net_delta,
            last_revisit_volume=liquidity_episode.executed_volume_against,
            last_revisit_trade_count=payload.trade_summary.trade_count,
            last_defended_reaction_ticks=liquidity_episode.price_rejection_ticks,
            last_failed_break_ticks=0,
            post_failure_delta=None,
            post_failure_move_ticks=None,
            raw_features={
                "bridge_source": "adapter_continuous_state",
                "buyers_hitting_same_level_count": liquidity_episode.buyers_hitting_same_level_count,
                "sellers_hitting_same_level_count": liquidity_episode.sellers_hitting_same_level_count,
            },
        )

    def _continuous_cross_session(
        self,
        payload: AdapterContinuousStatePayload,
        liquidity_episode: ObservedLiquidityEpisode | None,
        initiative_drive: ObservedInitiativeDrive | None,
        exertion_zone: ObservedExertionZone | None,
    ) -> ObservedCrossSessionSequence | None:
        if payload.gap_reference is None or initiative_drive is None:
            return None
        session_sequence = [payload.session_context.session_code]
        if payload.session_context.session_code is SessionCode.US_REGULAR:
            session_sequence = [SessionCode.US_PREMARKET, SessionCode.US_REGULAR]
        return ObservedCrossSessionSequence(
            sequence_id=f"seq-{payload.message_id}",
            started_at=payload.gap_reference.opened_at,
            last_observed_at=payload.observed_window_end,
            session_sequence=session_sequence,
            price_zone_low=min(payload.gap_reference.gap_low, initiative_drive.price_low),
            price_zone_high=max(payload.gap_reference.gap_high, initiative_drive.price_high),
            start_price=payload.gap_reference.gap_low if payload.gap_reference.direction is GapDirection.UP else payload.gap_reference.gap_high,
            latest_price=payload.price_state.last_price,
            linked_episode_ids=[liquidity_episode.episode_id] if liquidity_episode is not None else [],
            linked_drive_ids=[initiative_drive.drive_id],
            linked_exertion_zone_ids=[exertion_zone.zone_id] if exertion_zone is not None else [],
            linked_event_ids=[],
            raw_features={"bridge_source": "adapter_continuous_state", "gap_fill_ratio": payload.gap_reference.fill_ratio},
        )

    def _burst_episodes(self, payload: AdapterTriggerBurstPayload, dominant_side: StructureSide) -> list[ObservedLiquidityEpisode]:
        grouped: dict[str, list] = {}
        for event in self._iter_depth_events(payload):
            grouped.setdefault(event.track_id, []).append(event)
        episodes: list[ObservedLiquidityEpisode] = []
        for track_id, events in grouped.items():
            events = sorted(events, key=lambda item: item.event_time)
            first = events[0]
            executed_volume = sum(max(0, item.size_before - item.size_after) for item in events)
            replenishment_count = sum(1 for item in events if item.size_after >= item.size_before)
            pull_count = sum(1 for item in events if item.size_after < item.size_before and item.status_after.value in {"pulled", "moved"})
            episodes.append(
                ObservedLiquidityEpisode(
                    episode_id=f"ep-{payload.trigger.trigger_id}-{track_id}",
                    started_at=events[0].event_time,
                    ended_at=events[-1].event_time,
                    side=dominant_side if dominant_side is not StructureSide.NEUTRAL else first.side,
                    price_low=first.price,
                    price_high=first.price,
                    executed_volume_against=executed_volume,
                    replenishment_count=replenishment_count,
                    buyers_hitting_same_level_count=self._count_trades_near_price(payload, first.price, StructureSide.BUY),
                    sellers_hitting_same_level_count=self._count_trades_near_price(payload, first.price, StructureSide.SELL),
                    pull_count=pull_count,
                    price_rejection_ticks=self._burst_reaction_ticks(payload, first.price, first.side),
                    raw_features={"bridge_source": "adapter_trigger_burst"},
                ),
            )
        return episodes

    def _burst_drive(
        self,
        payload: AdapterTriggerBurstPayload,
        aggregate: BurstAggregate,
        dominant_side: StructureSide,
    ) -> ObservedInitiativeDrive | None:
        trades = payload.event_window.trade_events
        if not trades or dominant_side is StructureSide.NEUTRAL:
            return None
        aggressive_volume = sum(item.size for item in trades if item.aggressor_side is dominant_side)
        price_travel_ticks = self._ticks_between(aggregate.price_range.low, aggregate.price_range.high, payload.instrument.tick_size)
        signed_delta = aggregate.delta if dominant_side is StructureSide.BUY else -aggregate.delta
        if not self._drive_passes_dynamic_thresholds(
            instrument_symbol=payload.instrument.symbol,
            observed_at=payload.trigger.triggered_at,
            tick_size=payload.instrument.tick_size,
            price_travel_ticks=price_travel_ticks,
            net_delta=signed_delta,
            fallback_price_range=aggregate.price_range.high - aggregate.price_range.low,
            fallback_volume=aggregate.volume,
            fallback_abs_delta=abs(aggregate.delta),
        ):
            return None
        return ObservedInitiativeDrive(
            drive_id=f"drive-{payload.trigger.trigger_id}",
            started_at=min(item.event_time for item in trades),
            ended_at=max(item.event_time for item in trades),
            side=dominant_side,
            price_low=aggregate.price_range.low,
            price_high=aggregate.price_range.high,
            aggressive_volume=aggressive_volume,
            net_delta=signed_delta,
            trade_count=len(trades),
            consumed_price_levels=price_travel_ticks,
            price_travel_ticks=price_travel_ticks,
            max_counter_move_ticks=self._burst_counter_move_ticks(payload, dominant_side),
            continuation_seconds=self._window_seconds(max(item.event_time for item in trades), self._latest_burst_time(payload) or max(item.event_time for item in trades)),
            raw_features={"bridge_source": "adapter_trigger_burst"},
        )

    def _burst_measured_move(
        self,
        payload: AdapterTriggerBurstPayload,
        initiative_drive: ObservedInitiativeDrive | None,
    ) -> ObservedMeasuredMove | None:
        if initiative_drive is None:
            return None
        multiple = self._extract_measured_multiple(payload.trigger.reason_codes)
        if multiple is None:
            return None
        reference_distance_ticks = max(1, int(round(initiative_drive.price_travel_ticks / multiple)))
        return ObservedMeasuredMove(
            measurement_id=f"measure-{payload.trigger.trigger_id}",
            measured_subject_id=initiative_drive.drive_id,
            measured_subject_kind="initiative_drive",
            started_at=initiative_drive.started_at,
            ended_at=payload.observed_window_end,
            side=initiative_drive.side,
            anchor_price=initiative_drive.price_low if initiative_drive.side is StructureSide.BUY else initiative_drive.price_high,
            latest_price=initiative_drive.price_high if initiative_drive.side is StructureSide.BUY else initiative_drive.price_low,
            achieved_distance_ticks=initiative_drive.price_travel_ticks,
            reference_kind=MeasurementReferenceKind.MANIPULATION_LEG,
            reference_id=None,
            reference_distance_ticks=reference_distance_ticks,
            achieved_multiple=round(initiative_drive.price_travel_ticks / reference_distance_ticks, 2),
            body_confirmed_threshold_multiple=multiple,
            next_target_multiple=round(multiple * 2.0, 2),
            invalidated=False,
            raw_features={"bridge_source": "adapter_trigger_burst"},
        )

    def _burst_post_harvest(
        self,
        payload: AdapterTriggerBurstPayload,
        aggregate: BurstAggregate,
        dominant_side: StructureSide,
    ) -> ObservedPostHarvestResponse | None:
        if payload.trigger.trigger_type not in {AdapterTriggerType.HARVEST_COMPLETED, AdapterTriggerType.POST_HARVEST_PULLBACK, AdapterTriggerType.POST_HARVEST_REVERSAL}:
            return None
        post_aggregate = self._aggregate_window(payload.post_window)
        event_aggregate = self._aggregate_window(payload.event_window)
        outcome = {
            AdapterTriggerType.HARVEST_COMPLETED: PostHarvestOutcome.CONSOLIDATION,
            AdapterTriggerType.POST_HARVEST_PULLBACK: PostHarvestOutcome.PULLBACK,
            AdapterTriggerType.POST_HARVEST_REVERSAL: PostHarvestOutcome.REVERSAL,
        }[payload.trigger.trigger_type]
        side = dominant_side if dominant_side is not StructureSide.NEUTRAL else StructureSide.BUY
        return ObservedPostHarvestResponse(
            response_id=f"post-harvest-{payload.trigger.trigger_id}",
            harvest_subject_id=f"trigger-{payload.trigger.trigger_id}",
            harvest_subject_kind="adapter_trigger",
            harvest_completed_at=payload.trigger.triggered_at,
            harvest_side=side,
            harvested_price_low=event_aggregate.price_range.low,
            harvested_price_high=event_aggregate.price_range.high,
            completion_ratio=1.0,
            continuation_ticks_after_completion=self._ticks_between(event_aggregate.price_range.close, aggregate.price_range.close, payload.instrument.tick_size),
            consolidation_range_ticks=self._ticks_between(post_aggregate.price_range.low, post_aggregate.price_range.high, payload.instrument.tick_size),
            pullback_ticks=self._ticks_between(post_aggregate.price_range.low, event_aggregate.price_range.high, payload.instrument.tick_size),
            reversal_ticks=self._ticks_between(aggregate.price_range.low, aggregate.price_range.high, payload.instrument.tick_size),
            seconds_to_first_pullback=self._window_seconds(payload.trigger.triggered_at, post_aggregate.opened_at),
            seconds_to_reversal=self._window_seconds(payload.trigger.triggered_at, post_aggregate.closed_at),
            reached_next_opposing_liquidity=bool(payload.post_window.depth_events or payload.post_window.bookmarks),
            next_opposing_liquidity_price=post_aggregate.price_range.close,
            post_harvest_delta=post_aggregate.delta,
            outcome=outcome,
            raw_features={"bridge_source": "adapter_trigger_burst"},
        )

    def _burst_exertion_zone(
        self,
        payload: AdapterTriggerBurstPayload,
        liquidity_episodes: list[ObservedLiquidityEpisode],
        initiative_drive: ObservedInitiativeDrive | None,
        dominant_side: StructureSide,
    ) -> ObservedExertionZone | None:
        if not liquidity_episodes:
            return None
        episode = liquidity_episodes[0]
        return ObservedExertionZone(
            zone_id=f"zone-{episode.episode_id}",
            source_drive_id=initiative_drive.drive_id if initiative_drive is not None else episode.episode_id,
            side=initiative_drive.side if initiative_drive is not None else (episode.side if episode.side is not StructureSide.NEUTRAL else dominant_side),
            price_low=episode.price_low,
            price_high=episode.price_high,
            established_at=episode.started_at,
            last_interacted_at=payload.observed_window_end,
            establishing_volume=max(episode.executed_volume_against, initiative_drive.aggressive_volume if initiative_drive is not None else 0),
            establishing_delta=initiative_drive.net_delta if initiative_drive is not None else 0,
            establishing_trade_count=initiative_drive.trade_count if initiative_drive is not None else 0,
            peak_price_level_volume=episode.executed_volume_against,
            revisit_count=1,
            successful_reengagement_count=1 if episode.price_rejection_ticks > 0 else 0,
            failed_reengagement_count=0,
            last_revisit_delta=initiative_drive.net_delta if initiative_drive is not None else 0,
            last_revisit_volume=episode.executed_volume_against,
            last_revisit_trade_count=initiative_drive.trade_count if initiative_drive is not None else 0,
            last_defended_reaction_ticks=episode.price_rejection_ticks,
            last_failed_break_ticks=0,
            post_failure_delta=None,
            post_failure_move_ticks=None,
            raw_features={"bridge_source": "adapter_trigger_burst"},
        )

    def _liquidity_levels_from_continuous(self, payload: AdapterContinuousStatePayload) -> list[ObservedLiquidityLevel]:
        return [
            ObservedLiquidityLevel(
                level_type=LiquidityLevelType.MANUAL,
                price=level.price,
                first_seen_at=level.first_observed_at,
                touch_count=level.touch_count,
                swept=level.status.value in {"filled", "partially_filled"},
            )
            for level in sorted(payload.significant_liquidity, key=lambda item: item.distance_from_price_ticks)
        ]

    def _liquidity_levels_from_burst(self, payload: AdapterTriggerBurstPayload) -> list[ObservedLiquidityLevel]:
        levels: list[ObservedLiquidityLevel] = []
        seen: set[tuple[str, float]] = set()
        for event in self._iter_depth_events(payload):
            key = (event.track_id, event.price)
            if key in seen:
                continue
            seen.add(key)
            levels.append(
                ObservedLiquidityLevel(
                    level_type=LiquidityLevelType.MANUAL,
                    price=event.price,
                    first_seen_at=event.event_time,
                    touch_count=1,
                    swept=event.status_after.value in {"filled", "partially_filled"},
                ),
            )
        return levels

    def _window(
        self,
        timeframe: Timeframe,
        bars_considered: int,
        latest_range: ObservedRange,
        observed_at: datetime,
        dominant_side: StructureSide,
        liquidity_levels: list[ObservedLiquidityLevel],
        signals: list[ObservedOrderFlowSignal],
        value_area: ObservedValueArea | None,
        session_stats: ObservedSessionStats | None,
        raw_features: dict[str, object],
    ) -> ObservedContextWindow:
        return ObservedContextWindow(
            timeframe=timeframe,
            bars_considered=bars_considered,
            latest_range=latest_range,
            swing_points=self._swing_points(latest_range, observed_at, dominant_side),
            liquidity_levels=liquidity_levels,
            orderflow_signals=signals,
            value_area=value_area,
            session_stats=session_stats,
            raw_features=raw_features,
        )

    def _swing_points(self, latest_range: ObservedRange, observed_at: datetime, dominant_side: StructureSide) -> list[ObservedSwingPoint]:
        if dominant_side is StructureSide.SELL:
            return [
                ObservedSwingPoint(kind=SwingKind.HIGH, price=latest_range.high, formed_at=observed_at, leg_index=0, tags=["bridge_high"]),
                ObservedSwingPoint(kind=SwingKind.LOW, price=latest_range.low, formed_at=observed_at, leg_index=1, tags=["bridge_low"]),
            ]
        return [
            ObservedSwingPoint(kind=SwingKind.LOW, price=latest_range.low, formed_at=observed_at, leg_index=0, tags=["bridge_low"]),
            ObservedSwingPoint(kind=SwingKind.HIGH, price=latest_range.high, formed_at=observed_at, leg_index=1, tags=["bridge_high"]),
        ]

    def _second_feature(self, feature: AdapterSecondFeature) -> ObservedSecondFeature:
        return ObservedSecondFeature(
            second_started_at=feature.second_started_at,
            second_ended_at=feature.second_ended_at,
            latest_range=ObservedRange(open=feature.open, high=feature.high, low=feature.low, close=feature.close),
            trade_count=feature.trade_count,
            volume=feature.volume,
            delta=feature.delta,
            best_bid=feature.best_bid,
            best_ask=feature.best_ask,
            max_bid_depth=None,
            max_ask_depth=None,
            depth_imbalance=feature.depth_imbalance,
            raw_features={"bridge_source": "adapter_trigger_burst"},
        )

    def _prior_value_area(self, session: AdapterSessionContext) -> ObservedValueArea | None:
        if session.prior_value_area_low is None or session.prior_value_area_high is None or session.prior_point_of_control is None:
            return None
        return ObservedValueArea(low=session.prior_value_area_low, high=session.prior_value_area_high, point_of_control=session.prior_point_of_control)

    def _episode_from_zone(
        self,
        zone: AdapterZoneInteraction | None,
        dominant_side: StructureSide,
        observed_end: datetime,
    ) -> ObservedLiquidityEpisode | None:
        if zone is None:
            return None
        return ObservedLiquidityEpisode(
            episode_id=f"ep-{zone.zone_id}",
            started_at=zone.started_at,
            ended_at=observed_end,
            side=self._zone_side(zone, dominant_side),
            price_low=zone.zone_low,
            price_high=zone.zone_high,
            executed_volume_against=zone.executed_volume_against,
            replenishment_count=zone.replenishment_count,
            buyers_hitting_same_level_count=zone.buyers_hitting_same_level_count,
            sellers_hitting_same_level_count=zone.sellers_hitting_same_level_count,
            pull_count=zone.pull_count,
            price_rejection_ticks=zone.price_rejection_ticks,
            raw_features={"seconds_held": zone.seconds_held, "bridge_source": "adapter_continuous_state"},
        )

    def _zone_side(self, zone: AdapterZoneInteraction, dominant_side: StructureSide) -> StructureSide:
        if zone.buyers_hitting_same_level_count > zone.sellers_hitting_same_level_count:
            return StructureSide.BUY
        if zone.sellers_hitting_same_level_count > zone.buyers_hitting_same_level_count:
            return StructureSide.SELL
        return dominant_side

    def _dominant_side_from_trade_summary(self, trade_summary: AdapterTradeSummary, drive_side: StructureSide | None) -> StructureSide:
        if drive_side in {StructureSide.BUY, StructureSide.SELL}:
            return drive_side
        if trade_summary.net_delta > 0 or trade_summary.aggressive_buy_volume > trade_summary.aggressive_sell_volume:
            return StructureSide.BUY
        if trade_summary.net_delta < 0 or trade_summary.aggressive_sell_volume > trade_summary.aggressive_buy_volume:
            return StructureSide.SELL
        return StructureSide.NEUTRAL

    def _dominant_side_from_burst(self, payload: AdapterTriggerBurstPayload) -> StructureSide:
        buy_volume = sum(item.size for item in self._iter_trade_events(payload) if item.aggressor_side is StructureSide.BUY)
        sell_volume = sum(item.size for item in self._iter_trade_events(payload) if item.aggressor_side is StructureSide.SELL)
        if buy_volume > sell_volume:
            return StructureSide.BUY
        if sell_volume > buy_volume:
            return StructureSide.SELL
        if payload.trigger.trigger_type in {AdapterTriggerType.FAILED_OVERHEAD_CAPPING, AdapterTriggerType.OFFER_REVERSAL_RELEASE}:
            return StructureSide.BUY
        return StructureSide.NEUTRAL

    def _event_type_from_trigger(self, trigger_type: AdapterTriggerType) -> EventType:
        if trigger_type in {AdapterTriggerType.LIQUIDITY_FILL, AdapterTriggerType.HARVEST_COMPLETED}:
            return EventType.LIQUIDITY_SWEEP
        if trigger_type in {AdapterTriggerType.PROBE_REVERSAL_CANDIDATE, AdapterTriggerType.POST_HARVEST_REVERSAL}:
            return EventType.CHANGE_OF_CHARACTER
        if trigger_type in {AdapterTriggerType.MEASURED_MOVE_THRESHOLD, AdapterTriggerType.OFFER_REVERSAL_RELEASE}:
            return EventType.BREAK_OF_STRUCTURE
        if trigger_type in {AdapterTriggerType.GAP_FIRST_TOUCH, AdapterTriggerType.GAP_PARTIAL_FILL}:
            return EventType.VALUE_AREA_REJECTION
        return EventType.ORDERFLOW_IMBALANCE

    def _delta_magnitude(self, trade_summary: AdapterTradeSummary) -> float:
        if trade_summary.volume <= 0:
            return 0.0
        return round(min(1.0, abs(trade_summary.net_delta) / max(1, trade_summary.volume)), 2)

    def _drive_passes_dynamic_thresholds(
        self,
        *,
        instrument_symbol: str,
        observed_at: datetime,
        tick_size: float,
        price_travel_ticks: int,
        net_delta: int,
        fallback_price_range: float,
        fallback_volume: int,
        fallback_abs_delta: int,
    ) -> bool:
        thresholds = self.regime_monitor.get_dynamic_thresholds(
            instrument_symbol,
            observed_at,
            tick_size=tick_size,
            lookback_bars=20,
            fallback_price_range=fallback_price_range,
            fallback_volume=fallback_volume,
            fallback_abs_delta=fallback_abs_delta,
        )
        min_travel_ticks = max(5.0, thresholds.current_atr_ticks * 0.45)
        min_abs_delta = max(25.0, thresholds.baseline_abs_delta * 1.5)
        return float(price_travel_ticks) >= min_travel_ticks and abs(net_delta) >= min_abs_delta

    def _extract_measured_multiple(self, values: list[str]) -> float | None:
        for value in values:
            match = MEASURED_MULTIPLE_PATTERN.search(value)
            if match is not None:
                return float(match.group("multiple"))
        return None

    def _aggregate_window(self, window: AdapterBurstWindow) -> BurstAggregate:
        if window.second_features:
            first = min(window.second_features, key=lambda item: item.second_started_at)
            last = max(window.second_features, key=lambda item: item.second_ended_at)
            return BurstAggregate(
                opened_at=first.second_started_at,
                closed_at=last.second_ended_at,
                price_range=ObservedRange(open=first.open, high=max(item.high for item in window.second_features), low=min(item.low for item in window.second_features), close=last.close),
                trade_count=sum(item.trade_count for item in window.second_features),
                volume=sum(item.volume for item in window.second_features),
                delta=sum(item.delta for item in window.second_features),
                best_bid=last.best_bid,
                best_ask=last.best_ask,
                depth_imbalance=last.depth_imbalance,
            )
        if window.trade_events:
            first = min(window.trade_events, key=lambda item: item.event_time)
            last = max(window.trade_events, key=lambda item: item.event_time)
            return BurstAggregate(
                opened_at=first.event_time,
                closed_at=last.event_time,
                price_range=ObservedRange(open=first.price, high=max(item.price for item in window.trade_events), low=min(item.price for item in window.trade_events), close=last.price),
                trade_count=len(window.trade_events),
                volume=sum(item.size for item in window.trade_events),
                delta=sum(item.size if item.aggressor_side is StructureSide.BUY else -item.size for item in window.trade_events),
                best_bid=last.best_bid_after,
                best_ask=last.best_ask_after,
                depth_imbalance=None,
            )
        now = datetime.now(tz=UTC)
        return BurstAggregate(now, now, ObservedRange(open=0.0, high=0.0, low=0.0, close=0.0), 0, 0, 0, None, None, None)

    def _aggregate_burst(self, pre_window: AdapterBurstWindow, event_window: AdapterBurstWindow, post_window: AdapterBurstWindow) -> BurstAggregate:
        features = [*pre_window.second_features, *event_window.second_features, *post_window.second_features]
        if features:
            first = min(features, key=lambda item: item.second_started_at)
            last = max(features, key=lambda item: item.second_ended_at)
            return BurstAggregate(
                opened_at=first.second_started_at,
                closed_at=last.second_ended_at,
                price_range=ObservedRange(open=first.open, high=max(item.high for item in features), low=min(item.low for item in features), close=last.close),
                trade_count=sum(item.trade_count for item in features),
                volume=sum(item.volume for item in features),
                delta=sum(item.delta for item in features),
                best_bid=last.best_bid,
                best_ask=last.best_ask,
                depth_imbalance=last.depth_imbalance,
            )
        return self._aggregate_window(event_window)

    def _count_trades_near_price(self, payload: AdapterTriggerBurstPayload, price: float, side: StructureSide) -> int:
        tick = payload.instrument.tick_size
        return sum(1 for trade in self._iter_trade_events(payload) if trade.aggressor_side is side and abs(trade.price - price) <= tick)

    def _burst_reaction_ticks(self, payload: AdapterTriggerBurstPayload, price: float, track_side: StructureSide) -> int:
        features = list(self._iter_second_features(payload))
        if not features:
            return 0
        reaction_price = min(item.low for item in features) if track_side is StructureSide.SELL else max(item.high for item in features)
        return self._ticks_between(price, reaction_price, payload.instrument.tick_size)

    def _burst_counter_move_ticks(self, payload: AdapterTriggerBurstPayload, dominant_side: StructureSide) -> int:
        event_features = payload.event_window.second_features
        post_features = payload.post_window.second_features or event_features
        if not event_features or dominant_side is StructureSide.NEUTRAL:
            return 0
        if dominant_side is StructureSide.BUY:
            return self._ticks_between(min(item.low for item in event_features), min(item.low for item in post_features), payload.instrument.tick_size)
        return self._ticks_between(max(item.high for item in post_features), max(item.high for item in event_features), payload.instrument.tick_size)

    def _latest_burst_time(self, payload: AdapterTriggerBurstPayload) -> datetime | None:
        timestamps = [
            *(item.event_time for item in self._iter_trade_events(payload)),
            *(item.event_time for item in self._iter_depth_events(payload)),
            *(item.second_ended_at for item in self._iter_second_features(payload)),
        ]
        return max(timestamps) if timestamps else None

    def _trade_count(self, payload: AdapterTriggerBurstPayload) -> int:
        return len(payload.pre_window.trade_events) + len(payload.event_window.trade_events) + len(payload.post_window.trade_events)

    def _depth_count(self, payload: AdapterTriggerBurstPayload) -> int:
        return len(payload.pre_window.depth_events) + len(payload.event_window.depth_events) + len(payload.post_window.depth_events)

    def _bookmark_count(self, payload: AdapterTriggerBurstPayload) -> int:
        return len(payload.pre_window.bookmarks) + len(payload.event_window.bookmarks) + len(payload.post_window.bookmarks)

    def _window_seconds(self, started_at: datetime, ended_at: datetime) -> int:
        return max(0, int((ended_at - started_at).total_seconds()))

    def _ticks_between(self, left: float, right: float, tick_size: float) -> int:
        if tick_size <= 0:
            return 0
        return max(0, int(round(abs(right - left) / tick_size)))

    def _iter_trade_events(self, payload: AdapterTriggerBurstPayload):
        yield from payload.pre_window.trade_events
        yield from payload.event_window.trade_events
        yield from payload.post_window.trade_events

    def _iter_depth_events(self, payload: AdapterTriggerBurstPayload):
        yield from payload.pre_window.depth_events
        yield from payload.event_window.depth_events
        yield from payload.post_window.depth_events

    def _iter_second_features(self, payload: AdapterTriggerBurstPayload):
        yield from payload.pre_window.second_features
        yield from payload.event_window.second_features
        yield from payload.post_window.second_features
