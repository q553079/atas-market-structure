from __future__ import annotations

from atas_market_structure.adapter_bridge._burst import BurstAggregate, _AdapterBridgeBurstMixin
from atas_market_structure.adapter_bridge._continuous import _AdapterBridgeContinuousMixin
from atas_market_structure.adapter_bridge._shared import _AdapterBridgeSharedMixin
from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterTriggerBurstPayload,
    EventSnapshotPayload,
    MarketStructurePayload,
    ObservedEventMarker,
)
from atas_market_structure.regime_monitor_services import RegimeMonitor


class AdapterPayloadBridge(
    _AdapterBridgeContinuousMixin,
    _AdapterBridgeBurstMixin,
    _AdapterBridgeSharedMixin,
):
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
        aggregate: BurstAggregate = self._aggregate_burst(payload.pre_window, payload.event_window, payload.post_window)
        dominant_side = self._dominant_side_from_burst(payload)
        event_type = self._event_type_from_trigger(payload.trigger.trigger_type)
        trigger_event = ObservedEventMarker(
            event_type=event_type,
            observed_at=payload.trigger.triggered_at,
            price=payload.trigger.price,
            details={
                "adapter_trigger_type": payload.trigger.trigger_type.value,
                "reason_codes": payload.trigger.reason_codes,
                "message_id": payload.message_id,
            },
        )
        return EventSnapshotPayload(
            schema_version=payload.schema_version,
            event_snapshot_id=f"bridge-evt-{payload.message_id}",
            event_type=event_type,
            observed_at=payload.trigger.triggered_at,
            source=payload.source.model_dump(mode="json"),
            instrument=payload.instrument.model_dump(mode="json"),
            trigger_event=trigger_event.model_dump(mode="json"),
            decision_layers=self._burst_decision_layers(payload, aggregate, dominant_side).model_dump(mode="json"),
            process_context=self._burst_process_context(payload, aggregate, dominant_side).model_dump(mode="json"),
        )
