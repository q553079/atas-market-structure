from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, model_validator

from atas_market_structure.models._enums import EventHypothesisKind, RegimeKind
from atas_market_structure.models._replay import (
    BeliefDataStatus,
    EventHypothesisState,
    RegimePosteriorRecord,
)
from atas_market_structure.models._schema_versions import (
    CanonicalSchemaVersionedModel,
    EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
)


class FeatureSliceEvidenceBucket(CanonicalSchemaVersionedModel):
    """Typed evidence bucket inside feature_slice_v1."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., description="Normalized evidence score for this bucket.")
    available: bool = Field(..., description="Whether the recognizer had this bucket available.")
    weight: float = Field(..., description="Relative contribution weight for this bucket.")
    signals: list[str] = Field(default_factory=list, description="Observed signals contributing to the bucket.")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Bucket-local metrics preserved for audit.")


class FeatureSlicePayload(CanonicalSchemaVersionedModel):
    """Structured feature payload persisted in feature_slice_v1."""

    model_config = ConfigDict(extra="forbid")

    current_price: float | None = Field(None, description="Reference price used for the derived feature slice.")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Top-level deterministic feature metrics.")
    evidence_buckets: dict[str, FeatureSliceEvidenceBucket] = Field(
        default_factory=dict,
        description="Named evidence buckets used by the deterministic recognizer.",
    )
    notes: list[str] = Field(default_factory=list, description="Operator-facing notes preserved with the slice.")


class FeatureSliceContract(CanonicalSchemaVersionedModel):
    """Public append-only contract for feature_slice_v1 rows."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = FEATURE_SLICE_SCHEMA_VERSION

    feature_slice_id: str = Field(..., description="Stable feature-slice identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol for the feature slice.")
    market_time: datetime = Field(..., description="Market timestamp represented by the feature slice.")
    session_date: str | None = Field(None, description="Optional session date label.")
    ingested_at: datetime = Field(..., description="Persistence timestamp for the feature slice.")
    schema_version: str = Field(..., description="Canonical schema version for the feature slice.")
    profile_version: str = Field(..., description="Instrument profile version used to derive this slice.")
    engine_version: str = Field(..., description="Recognizer engine version used to derive this slice.")
    source_observation_table: str | None = Field(None, description="Primary source observation table when available.")
    source_observation_id: str | None = Field(None, description="Primary source observation identifier when available.")
    slice_kind: str = Field(..., description="Slice family emitted by the recognizer.")
    window_start: datetime | None = Field(None, description="Inclusive slice input window start.")
    window_end: datetime | None = Field(None, description="Inclusive slice input window end.")
    data_status: BeliefDataStatus = Field(..., description="Data-quality state attached to the slice.")
    feature_payload: FeatureSlicePayload = Field(..., description="Structured feature payload.")


class RegimePosteriorPayload(CanonicalSchemaVersionedModel):
    """Structured payload persisted in regime_posterior_v1."""

    model_config = ConfigDict(extra="forbid")

    regime_posteriors: list[RegimePosteriorRecord] = Field(
        default_factory=list,
        description="Ordered regime posterior records emitted by the recognizer.",
    )
    top_regime: RegimeKind | None = Field(None, description="Top regime selected from the posterior list.")


class RegimePosteriorContract(CanonicalSchemaVersionedModel):
    """Public append-only contract for regime_posterior_v1 rows."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REGIME_POSTERIOR_SCHEMA_VERSION

    posterior_id: str = Field(..., description="Stable regime-posterior identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol for this posterior row.")
    market_time: datetime = Field(..., description="Market timestamp represented by this posterior row.")
    session_date: str | None = Field(None, description="Optional session date label.")
    ingested_at: datetime = Field(..., description="Persistence timestamp.")
    schema_version: str = Field(..., description="Canonical schema version for the regime posterior.")
    profile_version: str = Field(..., description="Instrument profile version used to emit the posterior.")
    engine_version: str = Field(..., description="Recognizer engine version used to emit the posterior.")
    feature_slice_id: str | None = Field(None, description="Upstream feature-slice identifier.")
    posterior_payload: RegimePosteriorPayload = Field(..., description="Structured regime posterior payload.")


class EventHypothesisStateContract(CanonicalSchemaVersionedModel):
    """Public append-only contract for event_hypothesis_state_v1 rows."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION

    hypothesis_state_id: str = Field(..., description="Stable hypothesis-state identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol for this hypothesis-state row.")
    market_time: datetime = Field(..., description="Market timestamp represented by this hypothesis-state row.")
    session_date: str | None = Field(None, description="Optional session date label.")
    ingested_at: datetime = Field(..., description="Persistence timestamp.")
    schema_version: str = Field(..., description="Canonical schema version for the hypothesis-state contract.")
    profile_version: str = Field(..., description="Instrument profile version used to emit the state.")
    engine_version: str = Field(..., description="Recognizer engine version used to emit the state.")
    feature_slice_id: str | None = Field(None, description="Upstream feature-slice identifier.")
    hypothesis_kind: EventHypothesisKind = Field(..., description="Top-level hypothesis kind for this row.")
    hypothesis_payload: EventHypothesisState = Field(..., description="Structured hypothesis-state payload.")

    @model_validator(mode="after")
    def validate_hypothesis_kind_match(self) -> "EventHypothesisStateContract":
        if self.hypothesis_payload.hypothesis_kind is not self.hypothesis_kind:
            raise ValueError("hypothesis_kind must match hypothesis_payload.hypothesis_kind")
        return self
