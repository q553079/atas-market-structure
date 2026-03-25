from __future__ import annotations

import re
from typing import TYPE_CHECKING

from atas_market_structure.models import (
    CreateEventCandidateRequest,
    EventCandidatePatchRequest,
    EventStreamExtractRequest,
    EventStreamQuery,
    PromoteEventCandidateRequest,
)

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


_EVENT_CANDIDATE_PATTERN = re.compile(r"^/api/v1/workbench/event-candidates/(?P<event_id>[^/]+)$")
_EVENT_CANDIDATE_PROMOTE_PATTERN = re.compile(r"^/api/v1/workbench/event-candidates/(?P<event_id>[^/]+)/promote$")
_EVENT_CANDIDATE_MOUNT_PATTERN = re.compile(r"^/api/v1/workbench/event-candidates/(?P<event_id>[^/]+)/mount$")
_EVENT_CANDIDATE_IGNORE_PATTERN = re.compile(r"^/api/v1/workbench/event-candidates/(?P<event_id>[^/]+)/ignore$")


def handle_workbench_event_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "GET" and route_path == "/api/v1/workbench/event-stream":
        session_id = query.get("session_id", [None])[0]
        if session_id is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "session_id is required."},
            )
        limit_raw = query.get("limit", [None])[0]
        limit = 200
        if limit_raw is not None:
            try:
                limit = int(limit_raw)
            except ValueError:
                return app._json_response(
                    400,
                    {"error": "invalid_query_parameter", "detail": "limit must be an integer."},
                )
        response = app._replay_workbench_event_service.build_event_stream(
            EventStreamQuery(
                session_id=session_id,
                symbol=query.get("symbol", [None])[0],
                timeframe=query.get("timeframe", [None])[0],
                source_message_id=query.get("source_message_id", [None])[0],
                limit=limit,
            )
        )
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/event-stream/extract":
        payload = EventStreamExtractRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_event_service.extract_event_stream(payload)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/event-candidates":
        payload = CreateEventCandidateRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_event_service.create_event_candidate(payload)
        return app._json_model_response(200, response)

    candidate_match = _EVENT_CANDIDATE_PATTERN.match(route_path)
    if candidate_match and method == "PATCH":
        payload = EventCandidatePatchRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_event_service.patch_event_candidate(candidate_match.group("event_id"), payload)
        return app._json_model_response(200, response)

    promote_match = _EVENT_CANDIDATE_PROMOTE_PATTERN.match(route_path)
    if promote_match and method == "POST":
        payload = PromoteEventCandidateRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_event_service.promote_event_candidate(promote_match.group("event_id"), payload)
        return app._json_model_response(200, response)

    mount_match = _EVENT_CANDIDATE_MOUNT_PATTERN.match(route_path)
    if mount_match and method == "POST":
        response = app._replay_workbench_event_service.mount_event_candidate(mount_match.group("event_id"))
        return app._json_model_response(200, response)

    ignore_match = _EVENT_CANDIDATE_IGNORE_PATTERN.match(route_path)
    if ignore_match and method == "POST":
        response = app._replay_workbench_event_service.ignore_event_candidate(ignore_match.group("event_id"))
        return app._json_model_response(200, response)

    return None
