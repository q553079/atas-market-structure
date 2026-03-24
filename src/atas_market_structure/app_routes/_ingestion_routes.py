from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import ValidationError

from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterHistoryInventoryPayload,
    AdapterTriggerBurstPayload,
    DepthSnapshotPayload,
    EventSnapshotPayload,
    MarketStructurePayload,
)

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_ingestion_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "POST" and route_path == "/api/v1/ingestions/market-structure":
        payload = MarketStructurePayload.model_validate_json(body or b"{}")
        response = app._orchestrator.ingest_market_structure(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/ingest/market-structure":
        result = app._ingestion_reliability_service.ingest_market_structure(body or b"")
        return app._json_model_response(result.status_code, result.body)

    if method == "POST" and route_path == "/api/v1/ingestions/event-snapshot":
        payload = EventSnapshotPayload.model_validate_json(body or b"{}")
        response = app._orchestrator.ingest_event_snapshot(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/ingest/event-snapshot":
        result = app._ingestion_reliability_service.ingest_event_snapshot(body or b"")
        return app._json_model_response(result.status_code, result.body)

    if method == "POST" and route_path == "/api/v1/ingestions/depth-snapshot":
        payload = DepthSnapshotPayload.model_validate_json(body or b"{}")
        response = app._depth_monitoring_service.ingest_depth_snapshot(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/ingest/process-context":
        result = app._ingestion_reliability_service.ingest_process_context(body or b"")
        return app._json_model_response(result.status_code, result.body)

    if method == "POST" and route_path == "/api/v1/ingest/depth-snapshot":
        result = app._ingestion_reliability_service.ingest_depth_snapshot(body or b"")
        return app._json_model_response(result.status_code, result.body)

    if method == "POST" and route_path == "/api/v1/ingest/adapter-payload":
        result = app._ingestion_reliability_service.ingest_adapter_payload(body or b"")
        return app._json_model_response(result.status_code, result.body)

    if method == "POST" and route_path == "/api/v1/adapter/continuous-state":
        payload = AdapterContinuousStatePayload.model_validate_json(body or b"{}")
        response = app._adapter_ingestion_service.ingest_continuous_state(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/adapter/history-bars":
        payload = AdapterHistoryBarsPayload.model_validate_json(body or b"{}")
        response = app._adapter_ingestion_service.ingest_history_bars(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/adapter/history-footprint":
        payload = AdapterHistoryFootprintPayload.model_validate_json(body or b"{}")
        response = app._adapter_ingestion_service.ingest_history_footprint(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/adapter/history-inventory":
        raw_payload = json.loads(body.decode("utf-8") if body else "{}")
        if not isinstance(raw_payload, dict):
            raw_payload = {"payload": raw_payload}
        instrument_payload = raw_payload.get("instrument") if isinstance(raw_payload.get("instrument"), dict) else {}
        source_payload = raw_payload.get("source") if isinstance(raw_payload.get("source"), dict) else {}
        instrument_symbol = str(
            raw_payload.get("instrument_symbol")
            or instrument_payload.get("symbol")
            or raw_payload.get("symbol")
            or "unknown"
        ).strip() or "unknown"
        chart_instance_id = raw_payload.get("chart_instance_id") or source_payload.get("chart_instance_id")
        timeframe = raw_payload.get("timeframe") or raw_payload.get("bar_timeframe")
        stored_at = datetime.now(tz=UTC)
        source_snapshot_id = str(
            raw_payload.get("message_id")
            or raw_payload.get("request_id")
            or raw_payload.get("cache_key")
            or f"history-inventory-{stored_at.isoformat()}"
        ).strip()
        ingestion_id = f"ing-{uuid4().hex}"
        app._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="adapter_history_inventory",
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=raw_payload,
            stored_at=stored_at,
        )
        app._logger.info(
            "ingest_history_inventory: instrument_symbol=%s chart_instance_id=%s timeframe=%s keys=%s",
            instrument_symbol,
            chart_instance_id,
            timeframe,
            sorted(raw_payload.keys()),
        )
        try:
            payload = AdapterHistoryInventoryPayload.model_validate(raw_payload)
        except ValidationError as exc:
            app._logger.warning(
                "ingest_history_inventory: captured unparsed payload ingestion_id=%s chart_instance_id=%s validation_error_count=%s",
                ingestion_id,
                chart_instance_id,
                len(exc.errors()),
            )
            return app._json_response(
                202,
                {
                    "accepted": True,
                    "status": "captured_unparsed",
                    "endpoint": route_path,
                    "ingestion_id": ingestion_id,
                    "source_snapshot_id": source_snapshot_id,
                    "instrument_symbol": instrument_symbol,
                    "chart_instance_id": chart_instance_id,
                    "validation_error_count": len(exc.errors()),
                },
            )

        auto_backfill = app._replay_workbench_service.ingest_history_inventory(payload)
        return app._json_response(
            202,
            {
                "accepted": True,
                "status": "captured",
                "endpoint": route_path,
                "ingestion_id": ingestion_id,
                "source_snapshot_id": source_snapshot_id,
                "instrument_symbol": instrument_symbol,
                "chart_instance_id": chart_instance_id,
                "auto_backfill": auto_backfill,
            },
        )

    if method == "POST" and route_path == "/api/v1/adapter/trigger-burst":
        payload = AdapterTriggerBurstPayload.model_validate_json(body or b"{}")
        response = app._adapter_ingestion_service.ingest_trigger_burst(payload)
        return app._json_model_response(201, response)

    if method == "GET" and route_path == "/api/v1/adapter/backfill-command":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        contract_symbol = query.get("contract_symbol", [None])[0]
        root_symbol = query.get("root_symbol", [None])[0]
        if instrument_symbol is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "instrument_symbol is required."},
            )
        chart_instance_id = query.get("chart_instance_id", [None])[0]
        response = app._replay_workbench_service.poll_atas_backfill(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            root_symbol=root_symbol,
        )
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/adapter/backfill-ack":
        payload = AdapterBackfillAcknowledgeRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.acknowledge_atas_backfill(payload)
        return app._json_model_response(200, response)

    analysis_match = app._analysis_pattern.match(route_path)
    if method == "GET" and analysis_match:
        analysis_id = analysis_match.group("analysis_id")
        stored = app._repository.get_analysis(analysis_id)
        if stored is None:
            raise app._not_found_error(f"analysis '{analysis_id}' not found")
        response = app._analysis_envelope_type.model_validate({"analysis": stored.analysis_payload})
        return app._json_model_response(200, response)

    ingestion_match = app._ingestion_pattern.match(route_path)
    if method == "GET" and ingestion_match:
        ingestion_id = ingestion_match.group("ingestion_id")
        stored = app._repository.get_ingestion(ingestion_id)
        if stored is None:
            raise app._not_found_error(f"ingestion '{ingestion_id}' not found")
        response = app._ingestion_envelope_type(
            ingestion_id=stored.ingestion_id,
            ingestion_kind=stored.ingestion_kind,
            source_snapshot_id=stored.source_snapshot_id,
            observed_payload=stored.observed_payload,
            stored_at=stored.stored_at,
        )
        return app._json_model_response(200, response)

    return None
