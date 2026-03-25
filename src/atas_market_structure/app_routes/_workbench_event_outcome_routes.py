from __future__ import annotations

from typing import TYPE_CHECKING

from atas_market_structure.models import EventOutcomeQuery, EventStatsQuery

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_workbench_event_outcome_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
) -> HttpResponse | None:
    service = getattr(app, "_replay_workbench_event_outcome_service", None)
    if service is None or method != "GET":
        return None

    if route_path == "/api/v1/workbench/event-outcomes":
        payload = EventOutcomeQuery.model_validate(_query_payload(query))
        response = service.list_event_outcomes(payload)
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/event-stats/summary":
        payload = EventStatsQuery.model_validate(_query_payload(query))
        response = service.get_event_stats_summary(payload)
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/event-stats/by-kind":
        payload = EventStatsQuery.model_validate(_query_payload(query))
        response = service.get_event_stats_breakdown(payload, dimension="event_kind")
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/event-stats/by-time-window":
        payload = EventStatsQuery.model_validate(_query_payload(query))
        response = service.get_event_stats_breakdown(payload, dimension="time_window")
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/event-stats/by-analysis-preset":
        payload = EventStatsQuery.model_validate(_query_payload(query))
        response = service.get_event_stats_breakdown(payload, dimension="analysis_preset")
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/event-stats/by-model":
        payload = EventStatsQuery.model_validate(_query_payload(query))
        response = service.get_event_stats_breakdown(payload, dimension="model_name")
        return app._json_model_response(200, response)

    return None


def _query_payload(query: dict[str, list[str]]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, values in query.items():
        if not values:
            continue
        if values[0] in {"", None}:
            continue
        payload[key] = values[0]
    return payload
