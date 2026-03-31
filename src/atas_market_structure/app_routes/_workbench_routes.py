from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atas_market_structure.continuous_contract_service import ContinuousContractServiceError
from atas_market_structure.models import (
    ChartCandleBackfillEnvelope,
    ChartCandleBackfillRequest,
    ChartCandleEnvelope,
    ContinuousAdjustmentMode,
    MirrorBarsEnvelope,
    ReplayManualRegionAnnotationRequest,
    ReplayOperatorEntryRequest,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchSnapshotPayload,
    Timeframe,
)

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_workbench_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "GET" and route_path in {"/workbench/replay", "/static/replay_workbench.html"}:
        html = (app._static_dir / "replay_workbench.html").read_text(encoding="utf-8")
        return app._text_response(
            200,
            html,
            "text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    if method == "GET" and route_path in {"/workbench/pipeline-monitor", "/static/pipeline_monitor.html"}:
        html = (app._static_dir / "pipeline_monitor.html").read_text(encoding="utf-8")
        return app._text_response(
            200,
            html,
            "text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    if method == "GET" and route_path.startswith("/static/"):
        rel = route_path.removeprefix("/static/")
        candidate = (app._static_dir / rel).resolve()
        if app._static_dir not in candidate.parents and candidate != app._static_dir:
            raise app._not_found_error("invalid static path")
        if not candidate.exists() or not candidate.is_file():
            raise app._not_found_error(f"static resource '{rel}' not found")
        content = candidate.read_bytes()
        content_type = "application/octet-stream"
        suffix = candidate.suffix.lower()
        if suffix in {".html", ".htm"}:
            content_type = "text/html; charset=utf-8"
        elif suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
            content_type = f"image/{suffix.lstrip('.')}"
        return app._http_response_type(
            status_code=200,
            body=content,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
                "Cache-Control": "no-store",
            },
        )

    if method == "POST" and route_path == "/api/v1/workbench/replay-snapshots":
        payload = ReplayWorkbenchSnapshotPayload.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.ingest_replay_snapshot(payload)
        return app._json_model_response(201, response)

    if method == "POST" and route_path == "/api/v1/workbench/replay-builder/build":
        payload = ReplayWorkbenchBuildRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.build_replay_snapshot(payload)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/replay-cache":
        cache_key = query.get("cache_key", [None])[0]
        if cache_key is None:
            return app._json_response(400, {"error": "missing_query_parameter", "detail": "cache_key is required."})
        response = app._replay_workbench_service.get_cache_record(cache_key, allow_fuzzy=True)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/replay-cache/invalidate":
        payload = ReplayWorkbenchInvalidationRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.invalidate_cache_record(payload)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/replay-cache/rebuild-latest":
        payload = ReplayWorkbenchRebuildLatestRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.rebuild_cache_from_latest_sync(payload)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/atas-backfill-requests":
        payload = ReplayWorkbenchAtasBackfillRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.request_atas_backfill(payload)
        return app._json_model_response(201, response)

    if method == "GET" and route_path == "/api/v1/workbench/backfill-progress":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        display_timeframe_raw = query.get("display_timeframe", [None])[0]
        if instrument_symbol is None or display_timeframe_raw is None:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "instrument_symbol and display_timeframe are required.",
                },
            )
        try:
            display_timeframe = Timeframe(display_timeframe_raw)
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "display_timeframe is invalid."},
            )
        cache_key = query.get("cache_key", [None])[0]
        chart_instance_id = query.get("chart_instance_id", [None])[0]
        contract_symbol = query.get("contract_symbol", [None])[0]
        root_symbol = query.get("root_symbol", [None])[0]
        window_start_raw = query.get("window_start", [None])[0]
        window_end_raw = query.get("window_end", [None])[0]
        try:
            window_start = app._parse_utc(window_start_raw) if window_start_raw else None
            window_end = app._parse_utc(window_end_raw) if window_end_raw else None
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "window_start/window_end must be ISO UTC timestamps."},
            )
        response = app._replay_workbench_service.get_atas_backfill_progress(
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            cache_key=cache_key,
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            root_symbol=root_symbol,
            window_start=window_start,
            window_end=window_end,
        )
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/live-status":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        if instrument_symbol is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "instrument_symbol is required."},
            )
        replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
        response = app._replay_workbench_service.get_live_status(
            instrument_symbol=instrument_symbol,
            replay_ingestion_id=replay_ingestion_id,
        )
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/live-tail":
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        display_timeframe = query.get("display_timeframe", [None])[0]
        if instrument_symbol is None or display_timeframe is None:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "instrument_symbol and display_timeframe are required.",
                },
            )
        chart_instance_id = query.get("chart_instance_id", [None])[0]
        lookback_bars_raw = query.get("lookback_bars", [None])[0]
        try:
            timeframe = Timeframe(display_timeframe)
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "display_timeframe is invalid."},
            )
        try:
            lookback_bars = int(lookback_bars_raw) if lookback_bars_raw is not None else 4
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "lookback_bars must be an integer."},
            )
        response = app._replay_workbench_service.get_live_tail(
            instrument_symbol=instrument_symbol,
            display_timeframe=timeframe,
            chart_instance_id=chart_instance_id,
            lookback_bars=max(1, min(500, lookback_bars)),
        )
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/instruments":
        ingestions = app._repository.list_ingestions(limit=1000)
        symbols = sorted(set(item.instrument_symbol for item in ingestions))
        return app._json_response(200, {"instruments": symbols})

    if method == "GET" and route_path == "/api/v1/workbench/pipeline-monitor":
        contract_symbol = query.get("contract_symbol", [None])[0]
        root_symbol = query.get("root_symbol", [None])[0]
        try:
            days = int(query.get("days", ["10"])[0])
            flow_window_minutes = int(query.get("flow_window_minutes", ["15"])[0])
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "days and flow_window_minutes must be integers."},
            )
        payload = app._workbench_pipeline_monitor_service.get_monitor_snapshot(
            contract_symbol=contract_symbol,
            root_symbol=root_symbol,
            days=days,
            flow_window_minutes=flow_window_minutes,
        )
        return app._json_response(200, payload)

    if method == "GET" and route_path == "/api/v1/workbench/chart-candles":
        symbol = query.get("symbol", [None])[0]
        tf_raw = query.get("timeframe", [None])[0]
        ws_raw = query.get("window_start", [None])[0]
        we_raw = query.get("window_end", [None])[0]
        if not symbol or not tf_raw or not ws_raw or not we_raw:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "symbol, timeframe, window_start, window_end are required."},
            )
        try:
            tf = Timeframe(tf_raw)
            ws = app._parse_datetime_arg(ws_raw)
            we = app._parse_datetime_arg(we_raw)
            limit = int(query.get("limit", ["20000"])[0])
        except (ValueError, TypeError) as exc:
            return app._json_response(400, {"error": "invalid_parameter", "detail": str(exc)})
        skip_contract_overlay = str(query.get("skip_contract_overlay", ["false"])[0]).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        candles, display_metadata, event_annotations = app._chart_candle_service.get_display_candles_with_metadata(
            symbol,
            tf,
            ws,
            we,
            limit=limit,
            skip_contract_overlay=skip_contract_overlay,
        )
        return app._json_response(
            200,
            {
                "symbol": symbol,
                "timeframe": tf.value,
                "window_start": ws,
                "window_end": we,
                "count": len(candles),
                "candles": [candle.model_dump(mode="json") for candle in candles],
                "display_metadata": display_metadata,
                "event_annotations": [item.model_dump(mode="json") for item in event_annotations],
            },
        )

    if method == "POST" and route_path == "/api/v1/workbench/chart-candles/backfill":
        req = ChartCandleBackfillRequest.model_validate_json(body or b"{}")
        started = datetime.now(tz=UTC)
        result = app._chart_candle_service.backfill_from_ingestions(req.symbol, req.to_timeframes)
        env = ChartCandleBackfillEnvelope(
            symbol=req.symbol,
            backfill_started=started,
            bars_aggregated=0,
            candles_written=sum(result.values()),
        )
        return app._json_model_response(200, env)

    if method == "GET" and route_path == "/api/v1/chart/mirror-bars":
        chart_instance_id = query.get("chart_instance_id", [None])[0]
        contract_symbol = query.get("contract_symbol", [None])[0]
        tf_raw = query.get("timeframe", [None])[0]
        ws_raw = query.get("window_start_utc", [None])[0]
        we_raw = query.get("window_end_utc", [None])[0]
        if not contract_symbol or not tf_raw or not ws_raw or not we_raw:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "contract_symbol, timeframe, window_start_utc, window_end_utc are required.",
                },
            )
        try:
            tf = Timeframe(tf_raw)
            ws = app._parse_datetime_arg(ws_raw)
            we = app._parse_datetime_arg(we_raw)
            limit = app._parse_positive_int_arg(query.get("limit", [None])[0], default=5000)
        except (ValueError, TypeError) as exc:
            return app._json_response(400, {"error": "invalid_parameter", "detail": str(exc)})
        bars = app._repository.list_atas_chart_bars_raw(
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            timeframe=tf.value,
            window_start=ws,
            window_end=we,
            limit=limit,
        )
        return app._json_model_response(
            200,
            MirrorBarsEnvelope(
                chart_instance_id=chart_instance_id,
                contract_symbol=contract_symbol,
                timeframe=tf,
                window_start=ws,
                window_end=we,
                count=len(bars),
                bars=bars,
            ),
        )

    if method == "GET" and route_path == "/api/v1/chart/continuous-bars":
        root_symbol = query.get("root_symbol", [None])[0]
        tf_raw = query.get("timeframe", [None])[0]
        roll_mode_raw = query.get("roll_mode", [None])[0]
        ws_raw = query.get("window_start_utc", [None])[0]
        we_raw = query.get("window_end_utc", [None])[0]
        if not root_symbol or not tf_raw or not roll_mode_raw or not ws_raw or not we_raw:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "root_symbol, timeframe, roll_mode, window_start_utc, window_end_utc are required.",
                },
            )
        try:
            tf = Timeframe(tf_raw)
            roll_mode = app._roll_mode_type(roll_mode_raw)
            adjustment_mode = ContinuousAdjustmentMode(
                query.get("adjustment_mode", [ContinuousAdjustmentMode.NONE.value])[0]
            )
            ws = app._parse_datetime_arg(ws_raw)
            we = app._parse_datetime_arg(we_raw)
            limit = app._parse_positive_int_arg(query.get("limit", [None])[0], default=5000)
            include_contract_markers = app._parse_bool_arg(
                query.get("include_contract_markers", [None])[0],
                default=False,
            )
        except (ValueError, TypeError) as exc:
            return app._json_response(400, {"error": "invalid_parameter", "detail": str(exc)})
        manual_sequence = app._parse_csv_list(query.get("contract_sequence", [None])[0])
        try:
            envelope = app._continuous_contract_service.query_continuous_bars(
                root_symbol=root_symbol,
                timeframe=tf,
                roll_mode=roll_mode,
                window_start=ws,
                window_end=we,
                limit=limit,
                include_contract_markers=include_contract_markers,
                adjustment_mode=adjustment_mode,
                manual_sequence=manual_sequence,
            )
        except ContinuousContractServiceError as exc:
            return app._json_response(
                400,
                {"error": "continuous_query_invalid", "detail": str(exc)},
            )
        return app._json_model_response(200, envelope)

    if method == "POST" and route_path == "/api/v1/workbench/operator-entries":
        payload = ReplayOperatorEntryRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.record_operator_entry(payload)
        return app._json_model_response(201, response)

    if method == "GET" and route_path == "/api/v1/workbench/operator-entries":
        replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
        if replay_ingestion_id is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "replay_ingestion_id is required."},
            )
        response = app._replay_workbench_service.list_operator_entries(replay_ingestion_id)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/manual-regions":
        payload = ReplayManualRegionAnnotationRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_service.record_manual_region(payload)
        return app._json_model_response(201, response)

    if method == "GET" and route_path == "/api/v1/workbench/manual-regions":
        replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
        if replay_ingestion_id is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "replay_ingestion_id is required."},
            )
        response = app._replay_workbench_service.list_manual_regions(replay_ingestion_id)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/footprint-bar":
        replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
        bar_started_at_raw = query.get("bar_started_at", [None])[0]
        if replay_ingestion_id is None or bar_started_at_raw is None:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "replay_ingestion_id and bar_started_at are required.",
                },
            )
        response = app._replay_workbench_service.get_footprint_bar_detail(
            replay_ingestion_id=replay_ingestion_id,
            bar_started_at=datetime.fromisoformat(app._normalize_query_datetime(bar_started_at_raw)),
        )
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/liquidity-memory":
        instrument_symbol = query.get("symbol", [None])[0]
        response = app._depth_monitoring_service.list_liquidity_memory(instrument_symbol=instrument_symbol)
        return app._json_model_response(200, response)

    return None
