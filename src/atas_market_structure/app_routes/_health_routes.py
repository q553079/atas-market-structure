from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from atas_market_structure.models import ReplayProjectionQuery

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_health_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
) -> HttpResponse | None:
    if method == "GET" and route_path == "/health":
        return app._json_response(200, {"status": "ok", "timestamp": datetime.now(tz=UTC)})

    if method == "GET" and route_path == "/health/ingestion":
        instrument_symbol = app._query_value(query, "instrument_symbol", "instrument")
        result = app._ingestion_reliability_service.get_ingestion_health(
            instrument_symbol=instrument_symbol,
        )
        return app._json_model_response(result.status_code, result.body)

    if method == "GET" and route_path == "/health/data-quality":
        instrument_symbol = app._query_value(query, "instrument_symbol", "instrument")
        result = app._ingestion_reliability_service.get_data_quality(
            instrument_symbol=instrument_symbol,
        )
        return app._json_model_response(result.status_code, result.body)

    if method == "GET" and route_path == "/health/recognition":
        instrument_symbol = app._query_value(query, "instrument_symbol", "instrument")
        if instrument_symbol is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "instrument or instrument_symbol is required."},
            )
        projection_query = ReplayProjectionQuery(instrument_symbol=instrument_symbol)
        response = app._workbench_projection_service.get_health_status(projection_query)
        return app._json_model_response(200, response)

    return None
