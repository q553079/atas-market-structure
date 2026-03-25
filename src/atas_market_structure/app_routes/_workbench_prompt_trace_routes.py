from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


_PROMPT_TRACE_PATTERN = re.compile(r"^/api/v1/workbench/prompt-traces/(?P<prompt_trace_id>[^/]+)$")
_MESSAGE_PROMPT_TRACE_PATTERN = re.compile(r"^/api/v1/workbench/messages/(?P<message_id>[^/]+)/prompt-trace$")


def handle_workbench_prompt_trace_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
) -> HttpResponse | None:
    service = getattr(app, "_replay_workbench_prompt_trace_service", None)
    if service is None or method != "GET":
        return None

    if route_path == "/api/v1/workbench/prompt-traces":
        session_id = query.get("session_id", [None])[0]
        if not session_id:
            return app._json_response(
                400,
                {
                    "error": "missing_query_parameter",
                    "detail": "session_id is required.",
                },
            )
        limit_raw = query.get("limit", [None])[0]
        limit = int(limit_raw) if limit_raw is not None else 200
        response = service.list_prompt_traces(session_id=session_id, limit=limit)
        return app._json_model_response(200, response)

    trace_match = _PROMPT_TRACE_PATTERN.match(route_path)
    if trace_match:
        response = service.get_prompt_trace(trace_match.group("prompt_trace_id"))
        return app._json_model_response(200, response)

    message_match = _MESSAGE_PROMPT_TRACE_PATTERN.match(route_path)
    if message_match:
        response = service.get_prompt_trace_by_message(message_match.group("message_id"))
        return app._json_model_response(200, response)

    return None
