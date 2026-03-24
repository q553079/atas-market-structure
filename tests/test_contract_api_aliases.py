from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from atas_market_structure.models._schema_versions import (
    BELIEF_LATEST_ENVELOPE_SCHEMA_VERSION,
    BELIEF_STATE_SCHEMA_VERSION,
    EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION,
    EPISODE_EVALUATION_SCHEMA_VERSION,
    EPISODE_LIST_ENVELOPE_SCHEMA_VERSION,
    EVENT_EPISODE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_HEALTH_STATUS_ENVELOPE_SCHEMA_VERSION,
)
from tests.contract_support import (
    build_test_belief,
    build_test_episode,
    persist_belief,
    persist_episode,
    persist_profile_build,
)
from tests.test_app_support import build_application


def _seed_review_contracts(application) -> str:
    repository = application._repository
    persist_profile_build(repository)
    base = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    beliefs = [
        build_test_belief(belief_id="b0", observed_at=base, phase="emerging", probability=0.34),
        build_test_belief(belief_id="b1", observed_at=base + timedelta(minutes=1), phase="confirming", probability=0.62),
        build_test_belief(belief_id="b2", observed_at=base + timedelta(minutes=2), phase="resolved", probability=0.78),
    ]
    for belief in beliefs:
        persist_belief(repository, belief)
    episode = build_test_episode(
        started_at=base,
        ended_at=base + timedelta(minutes=2),
        resolution="confirmed",
        data_status=beliefs[-1].data_status,
    )
    persist_episode(repository, episode)
    return episode.episode_id


def test_review_alias_routes_expose_frozen_envelopes() -> None:
    application = build_application()
    episode_id = _seed_review_contracts(application)

    latest_belief = application.dispatch("GET", "/api/v1/belief/latest?instrument_symbol=NQ")
    assert latest_belief.status_code == 200
    latest_belief_payload = json.loads(latest_belief.body)
    assert latest_belief_payload["schema_version"] == BELIEF_LATEST_ENVELOPE_SCHEMA_VERSION
    assert latest_belief_payload["belief"]["schema_version"] == BELIEF_STATE_SCHEMA_VERSION

    latest_episodes = application.dispatch("GET", "/api/v1/episodes/latest?instrument_symbol=NQ&limit=5")
    assert latest_episodes.status_code == 200
    latest_episodes_payload = json.loads(latest_episodes.body)
    assert latest_episodes_payload["schema_version"] == EPISODE_LIST_ENVELOPE_SCHEMA_VERSION
    assert latest_episodes_payload["episodes"][0]["schema_version"] == EVENT_EPISODE_SCHEMA_VERSION

    create_evaluation = application.dispatch(
        "POST",
        "/api/v1/review/episode-evaluation",
        json.dumps({"episode_id": episode_id}).encode("utf-8"),
    )
    assert create_evaluation.status_code == 200
    create_evaluation_payload = json.loads(create_evaluation.body)
    assert create_evaluation_payload["schema_version"] == EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION
    assert create_evaluation_payload["evaluation"]["schema_version"] == EPISODE_EVALUATION_SCHEMA_VERSION

    fetch_evaluation = application.dispatch("GET", f"/api/v1/review/episode-evaluation/{episode_id}")
    assert fetch_evaluation.status_code == 200
    fetch_evaluation_payload = json.loads(fetch_evaluation.body)
    assert fetch_evaluation_payload["schema_version"] == EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION
    assert fetch_evaluation_payload["evaluation"]["schema_version"] == EPISODE_EVALUATION_SCHEMA_VERSION


def test_health_recognition_alias_exposes_frozen_top_level_envelope() -> None:
    application = build_application()
    _seed_review_contracts(application)

    response = application.dispatch("GET", "/health/recognition?instrument_symbol=NQ")

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["schema_version"] == REPLAY_WORKBENCH_HEALTH_STATUS_ENVELOPE_SCHEMA_VERSION
    assert "schema_version" in payload["health"]
    assert "schema_version" in payload["data_quality"]
    assert payload["latest_belief"]["schema_version"] == BELIEF_STATE_SCHEMA_VERSION
