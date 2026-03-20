from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from atas_market_structure.models import (
    AdapterBurstWindow,
    AdapterTriggerBurstPayload,
    AdapterTriggerType,
    DecisionLayerSet,
    LiquidityLevelType,
    MeasurementReferenceKind,
    ObservedExertionZone,
    ObservedInitiativeDrive,
    ObservedLiquidityEpisode,
    ObservedLiquidityLevel,
    ObservedMeasuredMove,
    ObservedOrderFlowSignal,
    ObservedPostHarvestResponse,
    ObservedProcessContext,
    ObservedRange,
    ObservedSessionStats,
    OrderFlowSignalType,
    PostHarvestOutcome,
    StructureSide,
    Timeframe,
)


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


class _AdapterBridgeBurstMixin:
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
