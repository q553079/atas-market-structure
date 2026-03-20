from __future__ import annotations

from datetime import datetime

from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterMeasuredMoveState,
    AdapterPostHarvestResponseState,
    DecisionLayerSet,
    EventType,
    GapDirection,
    LiquidityLevelType,
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
    ObservedSessionStats,
    ObservedSessionWindow,
    OrderFlowSignalType,
    PostHarvestOutcome,
    SessionCode,
    StructureSide,
    Timeframe,
)


class _AdapterBridgeContinuousMixin:
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
