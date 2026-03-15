from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from atas_market_structure.models import (
    DepthCoverageState,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    DerivedBias,
    DerivedLiquidityMemoryInterpretation,
    LiquidityMemoryClassification,
    LiquidityMemoryEnvelope,
    LiquidityMemoryRecord,
    ObservationOriginMode,
    ObservedLargeLiquidityLevel,
    LargeLiquidityStatus,
    StructureSide,
)
from atas_market_structure.repository import AnalysisRepository


MEMORY_TTL = timedelta(days=3)


class DepthMonitoringService:
    """Tracks only significant large orders and retains a 3-day memory."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def ingest_depth_snapshot(self, payload: DepthSnapshotPayload) -> DepthSnapshotAcceptedResponse:
        stored_at = datetime.now(tz=UTC)
        self._repository.expire_liquidity_memories(stored_at)

        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="depth_snapshot",
            source_snapshot_id=payload.depth_snapshot_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            stored_at=stored_at,
        )

        updated_memories = [
            self._upsert_memory(payload=payload, level=level, stored_at=stored_at)
            for level in payload.significant_levels
        ]

        return DepthSnapshotAcceptedResponse(
            ingestion_id=ingestion_id,
            coverage_state=payload.coverage_state,
            stored_at=stored_at,
            updated_memories=updated_memories,
        )

    def list_liquidity_memory(self, instrument_symbol: str | None = None) -> LiquidityMemoryEnvelope:
        records = self._repository.list_liquidity_memories(
            instrument_symbol=instrument_symbol,
            as_of=datetime.now(tz=UTC),
            limit=100,
        )
        return LiquidityMemoryEnvelope(
            memories=[
                LiquidityMemoryRecord(
                    memory_id=record.memory_id,
                    track_key=record.track_key,
                    instrument_symbol=record.instrument_symbol,
                    coverage_state=DepthCoverageState(record.coverage_state),
                    observed_track=ObservedLargeLiquidityLevel.model_validate(record.observed_track),
                    derived_interpretation=DerivedLiquidityMemoryInterpretation.model_validate(record.derived_summary),
                    expires_at=record.expires_at,
                    updated_at=record.updated_at,
                )
                for record in records
            ],
        )

    def _upsert_memory(
        self,
        *,
        payload: DepthSnapshotPayload,
        level: ObservedLargeLiquidityLevel,
        stored_at: datetime,
    ) -> LiquidityMemoryRecord:
        track_key = f"{payload.instrument.symbol}:{level.track_id}"
        existing = self._repository.get_liquidity_memory_by_track_key(track_key)
        merged_level = self._merge_level(
            existing=ObservedLargeLiquidityLevel.model_validate(existing.observed_track) if existing is not None else None,
            incoming=level,
        )

        memory_id = existing.memory_id if existing is not None else f"mem-{uuid4().hex}"
        interpretation = self._classify_track(memory_id=memory_id, level=merged_level)
        expires_at = stored_at + MEMORY_TTL

        stored = self._repository.save_or_update_liquidity_memory(
            memory_id=memory_id,
            track_key=track_key,
            instrument_symbol=payload.instrument.symbol,
            coverage_state=payload.coverage_state.value,
            observed_track=merged_level.model_dump(mode="json"),
            derived_summary=interpretation.model_dump(mode="json"),
            expires_at=expires_at,
            updated_at=stored_at,
        )

        return LiquidityMemoryRecord(
            memory_id=stored.memory_id,
            track_key=stored.track_key,
            instrument_symbol=stored.instrument_symbol,
            coverage_state=DepthCoverageState(stored.coverage_state),
            observed_track=ObservedLargeLiquidityLevel.model_validate(stored.observed_track),
            derived_interpretation=DerivedLiquidityMemoryInterpretation.model_validate(stored.derived_summary),
            expires_at=stored.expires_at,
            updated_at=stored.updated_at,
        )

    @staticmethod
    def _merge_level(
        *,
        existing: ObservedLargeLiquidityLevel | None,
        incoming: ObservedLargeLiquidityLevel,
    ) -> ObservedLargeLiquidityLevel:
        if existing is None:
            return incoming

        return ObservedLargeLiquidityLevel(
            track_id=incoming.track_id,
            side=incoming.side,
            price=incoming.price,
            current_size=incoming.current_size,
            max_seen_size=max(existing.max_seen_size, incoming.max_seen_size, incoming.current_size),
            distance_from_price_ticks=incoming.distance_from_price_ticks,
            first_observed_at=min(existing.first_observed_at, incoming.first_observed_at),
            last_observed_at=max(existing.last_observed_at, incoming.last_observed_at),
            first_seen_mode=existing.first_seen_mode if existing.first_seen_mode is ObservationOriginMode.BOOTSTRAP else incoming.first_seen_mode,
            status=incoming.status,
            touch_count=max(existing.touch_count, incoming.touch_count),
            executed_volume_estimate=max(existing.executed_volume_estimate, incoming.executed_volume_estimate),
            replenishment_count=max(existing.replenishment_count, incoming.replenishment_count),
            pull_count=max(existing.pull_count, incoming.pull_count),
            move_count=max(existing.move_count, incoming.move_count),
            price_reaction_ticks=max(existing.price_reaction_ticks or 0, incoming.price_reaction_ticks or 0) or None,
            heat_score=max(existing.heat_score or 0.0, incoming.heat_score or 0.0) or None,
            notes=_merge_unique(existing.notes, incoming.notes),
            raw_features={**existing.raw_features, **incoming.raw_features},
        )

    @staticmethod
    def _classify_track(
        *,
        memory_id: str,
        level: ObservedLargeLiquidityLevel,
    ) -> DerivedLiquidityMemoryInterpretation:
        observations_used = [
            "status",
            "executed_volume_estimate",
            "touch_count",
            "replenishment_count",
            "pull_count",
            "price_reaction_ticks",
        ]
        reasoning: list[str] = []

        if level.status is LargeLiquidityStatus.PULLED and level.executed_volume_estimate == 0:
            classification = LiquidityMemoryClassification.SPOOF_CANDIDATE
            directional_bias = _opposite_bias(level.side)
            confidence = 0.82 if level.touch_count > 0 else 0.68
            reasoning.append("Large displayed liquidity was pulled without measured execution, which is consistent with spoof-like behavior.")
        elif level.status in {LargeLiquidityStatus.FILLED, LargeLiquidityStatus.PARTIALLY_FILLED} and level.price_reaction_ticks:
            classification = LiquidityMemoryClassification.ABSORPTION_CANDIDATE
            directional_bias = _same_side_bias(level.side)
            confidence = 0.79 if level.replenishment_count > 0 else 0.71
            reasoning.append("Displayed liquidity traded and price reacted away from the level, which is consistent with absorption or genuine defense.")
        elif level.status is LargeLiquidityStatus.ACTIVE and level.touch_count > 0 and (level.price_reaction_ticks or 0) >= 8:
            classification = LiquidityMemoryClassification.DEFENDED_LEVEL_CANDIDATE
            directional_bias = _same_side_bias(level.side)
            confidence = 0.7
            reasoning.append("Price interacted with the large order and reacted away while the order remained visible.")
        elif level.status is LargeLiquidityStatus.ACTIVE and level.distance_from_price_ticks <= 8:
            classification = LiquidityMemoryClassification.MAGNET_CANDIDATE
            directional_bias = _same_side_bias(level.side)
            confidence = 0.61
            reasoning.append("The large order remains active near current price and can still influence short-term price path.")
        else:
            classification = LiquidityMemoryClassification.MONITORING
            directional_bias = DerivedBias.NEUTRAL
            confidence = 0.5
            reasoning.append("The large order is being tracked, but outcome evidence is still incomplete.")

        if level.first_seen_mode is ObservationOriginMode.BOOTSTRAP:
            reasoning.append("This track was already visible when depth coverage started, so pre-bootstrap history is unknown.")
            confidence = max(0.45, confidence - 0.05)

        reasoning.append(
            f"Track size peaked at {level.max_seen_size} contracts with {level.touch_count} touches and {level.pull_count} pull events."
        )

        return DerivedLiquidityMemoryInterpretation(
            memory_id=memory_id,
            track_id=level.track_id,
            classification=classification,
            directional_bias=directional_bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )


def _merge_unique(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*left, *right]:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _same_side_bias(side: StructureSide) -> DerivedBias:
    if side is StructureSide.BUY:
        return DerivedBias.BULLISH
    if side is StructureSide.SELL:
        return DerivedBias.BEARISH
    return DerivedBias.NEUTRAL


def _opposite_bias(side: StructureSide) -> DerivedBias:
    if side is StructureSide.BUY:
        return DerivedBias.BEARISH
    if side is StructureSide.SELL:
        return DerivedBias.BULLISH
    return DerivedBias.NEUTRAL
