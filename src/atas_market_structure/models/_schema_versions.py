from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, model_validator


INSTRUMENT_PROFILE_SCHEMA_VERSION = "instrument_profile_v1"
RECOGNIZER_BUILD_SCHEMA_VERSION = "recognizer_build_v1"
FEATURE_SLICE_SCHEMA_VERSION = "feature_slice_v1"
REGIME_POSTERIOR_SCHEMA_VERSION = "regime_posterior_v1"
EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION = "event_hypothesis_state_v1"
BELIEF_STATE_SCHEMA_VERSION = "belief_state_snapshot_v1"
EVENT_EPISODE_SCHEMA_VERSION = "event_episode_v1"
EPISODE_EVALUATION_SCHEMA_VERSION = "episode_evaluation_v1"
TUNING_INPUT_BUNDLE_SCHEMA_VERSION = "tuning_input_bundle_v1"
TUNING_RECOMMENDATION_SCHEMA_VERSION = "tuning_recommendation_v1"
PROFILE_PATCH_CANDIDATE_SCHEMA_VERSION = "profile_patch_candidate_v1"
EVENT_CANDIDATE_SCHEMA_VERSION = "event_candidate_v1"
EVENT_STREAM_ENTRY_SCHEMA_VERSION = "event_stream_entry_v1"
EVENT_MEMORY_ENTRY_SCHEMA_VERSION = "event_memory_entry_v1"
PROMPT_TRACE_SCHEMA_VERSION = "prompt_trace_v1"
EVENT_OUTCOME_LEDGER_SCHEMA_VERSION = "event_outcome_ledger_v1"

ANALYSIS_ENVELOPE_SCHEMA_VERSION = "analysis_envelope_v1"
INGESTION_ENVELOPE_SCHEMA_VERSION = "ingestion_envelope_v1"
BELIEF_LATEST_ENVELOPE_SCHEMA_VERSION = "belief_latest_envelope_v1"
EPISODE_LIST_ENVELOPE_SCHEMA_VERSION = "episode_list_envelope_v1"
EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION = "episode_evaluation_envelope_v1"
REPLAY_WORKBENCH_BELIEF_TIMELINE_ENVELOPE_SCHEMA_VERSION = "replay_workbench_belief_timeline_envelope_v1"
REPLAY_WORKBENCH_EPISODE_REVIEW_ENVELOPE_SCHEMA_VERSION = "replay_workbench_episode_review_envelope_v1"
REPLAY_WORKBENCH_EPISODE_EVALUATION_LIST_ENVELOPE_SCHEMA_VERSION = "replay_workbench_episode_evaluation_list_envelope_v1"
REPLAY_WORKBENCH_TUNING_REVIEW_ENVELOPE_SCHEMA_VERSION = "replay_workbench_tuning_review_envelope_v1"
REPLAY_WORKBENCH_PROFILE_ENGINE_ENVELOPE_SCHEMA_VERSION = "replay_workbench_profile_engine_envelope_v1"
REPLAY_WORKBENCH_HEALTH_STATUS_ENVELOPE_SCHEMA_VERSION = "replay_workbench_health_status_envelope_v1"
REPLAY_WORKBENCH_PROJECTION_ENVELOPE_SCHEMA_VERSION = "replay_workbench_projection_envelope_v1"
WORKBENCH_EVENT_STREAM_ENVELOPE_SCHEMA_VERSION = "workbench_event_stream_envelope_v1"
WORKBENCH_EVENT_MUTATION_ENVELOPE_SCHEMA_VERSION = "workbench_event_mutation_envelope_v1"
WORKBENCH_PROMPT_TRACE_ENVELOPE_SCHEMA_VERSION = "workbench_prompt_trace_envelope_v1"
WORKBENCH_PROMPT_TRACE_LIST_ENVELOPE_SCHEMA_VERSION = "workbench_prompt_trace_list_envelope_v1"
WORKBENCH_EVENT_OUTCOME_LIST_ENVELOPE_SCHEMA_VERSION = "workbench_event_outcome_list_envelope_v1"
WORKBENCH_EVENT_STATS_SUMMARY_ENVELOPE_SCHEMA_VERSION = "workbench_event_stats_summary_envelope_v1"
WORKBENCH_EVENT_STATS_BREAKDOWN_ENVELOPE_SCHEMA_VERSION = "workbench_event_stats_breakdown_envelope_v1"

DEFAULT_LEGACY_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0.0",)

CORE_CANONICAL_SCHEMA_VERSIONS: tuple[str, ...] = (
    INSTRUMENT_PROFILE_SCHEMA_VERSION,
    RECOGNIZER_BUILD_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
    EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION,
    BELIEF_STATE_SCHEMA_VERSION,
    EVENT_EPISODE_SCHEMA_VERSION,
    EPISODE_EVALUATION_SCHEMA_VERSION,
    TUNING_RECOMMENDATION_SCHEMA_VERSION,
)


def canonicalize_schema_version(
    value: Any,
    *,
    canonical: str,
    legacy: tuple[str, ...] = DEFAULT_LEGACY_SCHEMA_VERSIONS,
) -> str:
    """Freeze known contracts on one canonical schema_version string."""

    if value is None:
        return canonical
    if not isinstance(value, str):
        raise ValueError(f"schema_version must be a string; got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        return canonical
    if normalized == canonical or normalized in legacy:
        return canonical
    allowed = ", ".join((canonical, *legacy))
    raise ValueError(f"schema_version must be one of [{allowed}], got {normalized!r}")


class CanonicalSchemaVersionedModel(BaseModel):
    """Compatibility layer: emit canonical schema_version, accept legacy reads."""

    canonical_schema_version: ClassVar[str | None] = None
    accepted_legacy_schema_versions: ClassVar[tuple[str, ...]] = DEFAULT_LEGACY_SCHEMA_VERSIONS

    @model_validator(mode="before")
    @classmethod
    def _freeze_schema_version(cls, data: Any) -> Any:
        canonical = cls.canonical_schema_version
        if canonical is None:
            return data
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="python")
        if isinstance(data, Mapping):
            normalized = dict(data)
            normalized["schema_version"] = canonicalize_schema_version(
                normalized.get("schema_version"),
                canonical=canonical,
                legacy=cls.accepted_legacy_schema_versions,
            )
            return normalized
        return data
