from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from atas_market_structure.models._enums import (
    DerivedBias,
    GapDirection,
    GapFillLikelihood,
    GapFillState,
    KeyLevelRole,
    KeyLevelState,
    LargeLiquidityStatus,
    LiquidityMemoryClassification,
    StructureSide,
    Timeframe,
    DepthCoverageState,
)
from atas_market_structure.models._observed import (
    DecisionLayerSet,
    ObservedEventMarker,
    ObservedLargeLiquidityLevel,
    ObservedProcessContext,
)
from atas_market_structure.models._refs import InstrumentRef, SourceRef

class DerivedWindowInterpretation(BaseModel):
    """Recognizer output for one timeframe. This is intentionally separate from observed facts."""

    timeframe: Timeframe = Field(..., description="Timeframe being interpreted.")
    directional_bias: DerivedBias = Field(..., description="Minimal derived directional bias.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognizer confidence score.", examples=[0.67])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed facts referenced by the recognizer.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived interpretation statements based on observed facts.",
    )


class DerivedProcessInterpretation(BaseModel):
    """Derived interpretation for process-aware observed data."""

    subject_id: str = Field(..., description="Observed subject identifier used by the recognizer.")
    subject_kind: str = Field(..., description="Observed subject type.", examples=["liquidity_episode"])
    directional_bias: DerivedBias = Field(..., description="Derived directional implication of the process data.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognizer confidence score.", examples=[0.72])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements used by the recognizer.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived interpretation statements for process data.",
    )


class DerivedKeyLevelAssessment(BaseModel):
    """Structured support and resistance context derived from exertion zones."""

    zone_id: str = Field(..., description="Observed exertion-zone identifier.")
    role: KeyLevelRole = Field(..., description="Current role of the zone for trading context.")
    state: KeyLevelState = Field(..., description="Most recent state of the zone.")
    price_low: float = Field(..., description="Lower boundary of the key level zone.")
    price_high: float = Field(..., description="Upper boundary of the key level zone.")
    directional_bias: DerivedBias = Field(..., description="Directional implication when price interacts with the zone.")
    strength_score: float = Field(..., ge=0.0, le=1.0, description="Normalized support or resistance strength score.")
    revisit_count: int = Field(..., ge=0, description="How many revisits the zone has already seen.")
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements referenced when scoring the zone.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about why the zone matters now.",
    )


class DerivedGapAssessment(BaseModel):
    """Derived gap-fill context used by AI and later review workflows."""

    gap_id: str = Field(..., description="Observed gap identifier.")
    direction: GapDirection = Field(..., description="Direction of the gap reference.")
    gap_low: float = Field(..., description="Lower boundary of the observed gap.")
    gap_high: float = Field(..., description="Upper boundary of the observed gap.")
    fill_state: GapFillState = Field(..., description="Observed fill state of the gap.")
    fill_likelihood: GapFillLikelihood = Field(..., description="Derived likelihood that the gap will continue toward full repair.")
    directional_bias: DerivedBias = Field(..., description="Directional implication of the current gap interaction.")
    fill_ratio: float = Field(..., ge=0.0, le=1.0, description="Observed repaired fraction of the gap.")
    remaining_fill_ticks: int = Field(
        ...,
        ge=0,
        description="Ticks still remaining until the gap is fully repaired.",
    )
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed gap measurements referenced by the assessment.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about gap repair, acceptance, or rejection.",
    )


class DerivedLiquidityMemoryInterpretation(BaseModel):
    """Derived interpretation for a tracked significant large order."""

    memory_id: str = Field(..., description="Stable memory identifier.")
    track_id: str = Field(..., description="Observed track identifier.")
    classification: LiquidityMemoryClassification = Field(..., description="High-value classification for the track.")
    directional_bias: DerivedBias = Field(..., description="Directional implication derived from the track outcome.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classifier confidence score.", examples=[0.81])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements referenced by the classifier.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about the track and its likely outcome.",
    )


class KnowledgeRoute(BaseModel):
    """Routing hint for future playbook or retrieval augmentation selection."""

    route_key: str = Field(..., description="Stable route identifier.", examples=["trend_continuation_review"])
    summary: str = Field(..., description="Short explanation for the route choice.")
    required_context: list[str] = Field(
        default_factory=list,
        description="Context categories the next stage should load.",
        examples=[["macro_context", "intraday_bias", "execution_context"]],
    )


class DerivedStructureAnalysis(BaseModel):
    """Top-level derived interpretation stored separately from observed payloads."""

    analysis_id: str = Field(..., description="Analysis record identifier.")
    ingestion_kind: str = Field(..., description="Source ingestion kind.", examples=["market_structure"])
    source_snapshot_id: str = Field(..., description="Original producer snapshot identifier.")
    generated_at: datetime = Field(..., description="When the derived analysis was created.")
    macro_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    intraday_bias: list[DerivedWindowInterpretation] = Field(default_factory=list)
    setup_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    execution_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    process_context: list[DerivedProcessInterpretation] = Field(
        default_factory=list,
        description="Derived process-aware interpretations spanning seconds to cross-session sequences.",
    )
    key_levels: list[DerivedKeyLevelAssessment] = Field(
        default_factory=list,
        description="Structured support and resistance assessments derived from exertion zones.",
    )
    gap_assessments: list[DerivedGapAssessment] = Field(
        default_factory=list,
        description="Derived gap-fill assessments for script and location context.",
    )
    knowledge_route: KnowledgeRoute = Field(..., description="Knowledge-base routing result.")
    analyst_flags: list[str] = Field(
        default_factory=list,
        description="Phase-1 machine-generated flags for operator review.",
    )


