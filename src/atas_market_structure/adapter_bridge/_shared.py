from __future__ import annotations

from datetime import datetime
import re

from atas_market_structure.models import (
    AdapterSecondFeature,
    AdapterSessionContext,
    AdapterTradeSummary,
    AdapterTriggerBurstPayload,
    AdapterTriggerType,
    AdapterZoneInteraction,
    EventType,
    ObservedContextWindow,
    ObservedLiquidityEpisode,
    ObservedOrderFlowSignal,
    ObservedRange,
    ObservedSecondFeature,
    ObservedSessionStats,
    ObservedSwingPoint,
    ObservedValueArea,
    StructureSide,
    SwingKind,
    Timeframe,
)

MEASURED_MULTIPLE_PATTERN = re.compile(r"measured(?:_move)?_(?P<multiple>\d+(?:\.\d+)?)x", re.IGNORECASE)


class _AdapterBridgeSharedMixin:
    def _window(
        self,
        timeframe: Timeframe,
        bars_considered: int,
        latest_range: ObservedRange,
        observed_at: datetime,
        dominant_side: StructureSide,
        liquidity_levels: list,
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

    def _window_seconds(self, started_at: datetime, ended_at: datetime) -> int:
        return max(0, int((ended_at - started_at).total_seconds()))

    def _ticks_between(self, left: float, right: float, tick_size: float) -> int:
        if tick_size <= 0:
            return 0
        return max(0, int(round(abs(right - left) / tick_size)))
