from __future__ import annotations

from datetime import UTC, datetime

from atas_market_structure.models import InstrumentProfile, RecognizerBuild
from atas_market_structure.profile_services import build_instrument_profile_v1


INSTRUMENT_PROFILE_SCHEMA_VERSION = "instrument_profile_v1"
RECOGNIZER_BUILD_SCHEMA_VERSION = "recognizer_build_v1"
FEATURE_SLICE_SCHEMA_VERSION = "feature_slice_v1"
REGIME_POSTERIOR_SCHEMA_VERSION = "regime_posterior_v1"
EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION = "event_hypothesis_state_v1"
MEMORY_ANCHOR_SCHEMA_VERSION = "memory_anchor_v1"
BELIEF_STATE_SCHEMA_VERSION = "belief_state_snapshot_v1"
EVENT_EPISODE_SCHEMA_VERSION = "event_episode_v1"
RECOGNITION_ONTOLOGY_VERSION = "master_spec_v2_v1"
DEFAULT_ENGINE_VERSION = "recognizer_deterministic_v1"


def default_profile_version(instrument_symbol: str) -> str:
    normalized = instrument_symbol.strip().lower().replace(" ", "_")
    return f"{normalized}_profile_v1_default"


def build_default_profile_payload(instrument_symbol: str, *, tick_size: float) -> dict[str, object]:
    """Return a deterministic default profile for instruments with no active profile."""

    return build_default_instrument_profile(instrument_symbol, tick_size=tick_size).model_dump(mode="json")


def build_default_instrument_profile(instrument_symbol: str, *, tick_size: float) -> InstrumentProfile:
    return build_instrument_profile_v1(
        instrument_symbol,
        tick_size=tick_size,
        profile_version=default_profile_version(instrument_symbol),
        schema_version=INSTRUMENT_PROFILE_SCHEMA_VERSION,
        ontology_version=RECOGNITION_ONTOLOGY_VERSION,
        created_at=datetime.now(tz=UTC),
        is_active=True,
    )


def build_default_recognizer_build() -> RecognizerBuild:
    now = datetime.now(tz=UTC)
    return RecognizerBuild(
        engine_version=DEFAULT_ENGINE_VERSION,
        schema_version=RECOGNIZER_BUILD_SCHEMA_VERSION,
        ontology_version=RECOGNITION_ONTOLOGY_VERSION,
        is_active=True,
        status="active",
        notes=[
            "Deterministic V1 recognizer skeleton.",
            "No AI is used in the critical recognition path.",
        ],
        created_at=now,
    )
