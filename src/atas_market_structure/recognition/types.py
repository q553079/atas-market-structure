from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EventEpisode,
    RecognitionMode,
)


@dataclass(frozen=True)
class EvidenceBucket:
    """Deterministic evidence-bucket summary used by the V1 recognizer."""

    name: str
    score: float
    available: bool
    weight: float
    signals: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecognitionFeatureVector:
    """Numerical feature slice derived from append-only observations."""

    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    window_start: datetime | None
    window_end: datetime | None
    tick_size: float
    current_price: float | None
    source_observation_table: str | None
    source_observation_id: str | None
    metrics: dict[str, float]
    evidence_buckets: dict[str, EvidenceBucket]
    context_payloads: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecognitionRunResult:
    """Operational summary returned after one deterministic recognition run."""

    triggered: bool
    instrument_symbol: str
    market_time: datetime | None
    profile_version: str
    engine_version: str
    recognition_mode: RecognitionMode | None
    data_status: BeliefDataStatus | None
    feature_slice_id: str | None
    belief_state: BeliefStateSnapshot | None
    closed_episodes: list[EventEpisode] = field(default_factory=list)
    episode_evaluations: list[EpisodeEvaluation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
