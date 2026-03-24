from __future__ import annotations

from datetime import datetime
from typing import Protocol

from atas_market_structure.repository_records import (
    StoredBeliefState,
    StoredEpisodeEvaluation,
    StoredEventEpisode,
    StoredInstrumentProfile,
    StoredLiquidityMemory,
    StoredRecognizerBuild,
)


class RecognitionRepository(Protocol):
    """Deterministic recognition write/read surface.

    Allowed to own:
    belief snapshots, event episodes, episode evaluations, active profile/build lookup,
    liquidity memory used by degraded-mode and anchor-related flows.

    Must not own:
    chat session persistence, operator annotations, patch promotion history.
    """

    def save_belief_state(self, *, belief_state_id: str, instrument_symbol: str, observed_at: datetime, stored_at: datetime, schema_version: str, profile_version: str, engine_version: str, recognition_mode: str, belief_payload: dict[str, object]) -> StoredBeliefState:
        ...

    def get_latest_belief_state(self, instrument_symbol: str) -> StoredBeliefState | None:
        ...

    def list_belief_states(
        self,
        *,
        instrument_symbol: str,
        observed_at_after: datetime | None = None,
        observed_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredBeliefState]:
        ...

    def save_event_episode(self, *, episode_id: str, instrument_symbol: str, event_kind: str, started_at: datetime, ended_at: datetime, resolution: str, schema_version: str, profile_version: str, engine_version: str, episode_payload: dict[str, object]) -> StoredEventEpisode:
        ...

    def get_event_episode(self, episode_id: str) -> StoredEventEpisode | None:
        ...

    def list_event_episodes(
        self,
        *,
        instrument_symbol: str,
        ended_at_after: datetime | None = None,
        ended_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredEventEpisode]:
        ...

    def save_episode_evaluation(self, *, evaluation_id: str, episode_id: str, instrument_symbol: str, event_kind: str, evaluated_at: datetime, schema_version: str, profile_version: str, engine_version: str, evaluation_payload: dict[str, object]) -> StoredEpisodeEvaluation:
        ...

    def get_episode_evaluation(self, episode_id: str) -> StoredEpisodeEvaluation | None:
        ...

    def list_episode_evaluations(
        self,
        *,
        instrument_symbol: str,
        evaluated_at_after: datetime | None = None,
        evaluated_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredEpisodeEvaluation]:
        ...

    def save_instrument_profile(self, *, instrument_symbol: str, profile_version: str, schema_version: str, ontology_version: str, is_active: bool, profile_payload: dict[str, object], created_at: datetime) -> StoredInstrumentProfile:
        ...

    def get_active_instrument_profile(self, instrument_symbol: str) -> StoredInstrumentProfile | None:
        ...

    def save_recognizer_build(self, *, engine_version: str, schema_version: str, ontology_version: str, is_active: bool, status: str, build_payload: dict[str, object], created_at: datetime) -> StoredRecognizerBuild:
        ...

    def get_active_recognizer_build(self) -> StoredRecognizerBuild | None:
        ...

    def save_or_update_liquidity_memory(self, *, memory_id: str, track_key: str, instrument_symbol: str, coverage_state: str, observed_track: dict[str, object], derived_summary: dict[str, object], expires_at: datetime, updated_at: datetime) -> StoredLiquidityMemory:
        ...

    def get_liquidity_memory_by_track_key(self, track_key: str) -> StoredLiquidityMemory | None:
        ...

    def list_liquidity_memories(
        self,
        *,
        instrument_symbol: str | None = None,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> list[StoredLiquidityMemory]:
        ...
