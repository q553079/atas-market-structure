from __future__ import annotations

import json
from typing import TYPE_CHECKING

from atas_market_structure.app_shared import NotFoundError
from atas_market_structure.models import (
    BeliefLatestEnvelope,
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EpisodeEvaluationEnvelope,
    EpisodeListEnvelope,
    EventEpisode,
)

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_review_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "GET" and route_path == "/api/v1/workbench/review/belief-state-timeline":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_belief_state_timeline(projection_query)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/belief/latest":
        instrument_symbol = app._query_value(query, "instrument_symbol", "instrument")
        if instrument_symbol is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "instrument or instrument_symbol is required."},
            )
        stored = app._repository.get_latest_belief_state(instrument_symbol)
        belief = BeliefStateSnapshot.model_validate(stored.belief_payload) if stored is not None else None
        return app._json_model_response(200, BeliefLatestEnvelope(belief=belief))

    if method == "GET" and route_path == "/api/v1/workbench/review/event-episodes":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_event_episode_reviews(projection_query)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/episodes/latest":
        instrument_symbol = app._query_value(query, "instrument_symbol", "instrument")
        if instrument_symbol is None:
            return app._json_response(
                400,
                {"error": "missing_query_parameter", "detail": "instrument or instrument_symbol is required."},
            )
        limit_raw = app._query_value(query, "limit")
        try:
            limit = max(1, min(1000, int(limit_raw))) if limit_raw is not None else 20
        except ValueError:
            return app._json_response(
                400,
                {"error": "invalid_query_parameter", "detail": "limit must be an integer."},
            )
        episodes = [
            EventEpisode.model_validate(item.episode_payload)
            for item in app._repository.list_event_episodes(
                instrument_symbol=instrument_symbol,
                limit=limit,
            )
        ]
        return app._json_model_response(
            200,
            EpisodeListEnvelope(instrument_symbol=instrument_symbol, episodes=episodes),
        )

    if method == "GET" and route_path == "/api/v1/workbench/review/episode-evaluations":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_episode_evaluations(projection_query)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/review/episode-evaluation":
        payload = json.loads(body or b"{}")
        episode_id = payload.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id.strip():
            return app._json_response(
                400,
                {"error": "missing_required_field", "detail": "episode_id is required."},
            )
        evaluation = app._episode_evaluation_service.evaluate_episode_from_repository(
            episode_id.strip(),
            persist=True,
        )
        return app._json_model_response(200, EpisodeEvaluationEnvelope(evaluation=evaluation))

    episode_evaluation_match = app._episode_evaluation_pattern.match(route_path)
    if method == "GET" and episode_evaluation_match:
        episode_id = episode_evaluation_match.group("episode_id")
        stored = app._repository.get_episode_evaluation(episode_id)
        if stored is None:
            raise NotFoundError(f"episode evaluation '{episode_id}' not found")
        evaluation = EpisodeEvaluation.model_validate(stored.evaluation_payload)
        return app._json_model_response(200, EpisodeEvaluationEnvelope(evaluation=evaluation))

    if method == "GET" and route_path == "/api/v1/workbench/review/tuning-recommendations":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_tuning_reviews(projection_query)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/review/profile-engine":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_profile_engine_metadata(projection_query)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/review/health-status":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.get_health_status(projection_query)
        return app._json_model_response(200, response)

    if method == "GET" and route_path == "/api/v1/workbench/review/projection":
        projection_query = app._parse_projection_query(query)
        response = app._workbench_projection_service.build_projection(projection_query)
        return app._json_model_response(200, response)

    return None
