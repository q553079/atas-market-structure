from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    EventHypothesisState,
    MemoryAnchorSnapshot,
    RecognitionMode,
    RegimePosteriorRecord,
)
from atas_market_structure.repository import AnalysisRepository


class BeliefStateBuilder:
    """Builds and persists append-only belief-state snapshots."""

    def __init__(self, repository: AnalysisRepository, *, schema_version: str) -> None:
        self._repository = repository
        self._schema_version = schema_version

    def build_and_store(
        self,
        *,
        instrument_symbol: str,
        market_time: datetime,
        profile_version: str,
        engine_version: str,
        run_key: str | None = None,
        recorded_at: datetime | None = None,
        recognition_mode: RecognitionMode,
        data_status: BeliefDataStatus,
        regimes: list[RegimePosteriorRecord],
        hypotheses: list[EventHypothesisState],
        anchors: list[MemoryAnchorSnapshot],
        notes: list[str],
    ) -> BeliefStateSnapshot:
        stored_at = recorded_at or datetime.now(tz=UTC)
        belief_state_id = f"bs-{instrument_symbol.lower()}-{run_key}" if run_key else f"bs-{instrument_symbol.lower()}-{market_time.strftime('%Y%m%d%H%M%S')}"
        top_regimes = regimes[:3]
        top_hypotheses = hypotheses[:3]
        belief = BeliefStateSnapshot(
            belief_state_id=belief_state_id,
            instrument_symbol=instrument_symbol,
            observed_at=market_time,
            stored_at=stored_at,
            schema_version=self._schema_version,
            profile_version=profile_version,
            engine_version=engine_version,
            recognition_mode=recognition_mode,
            data_status=data_status,
            regime_posteriors=top_regimes,
            event_hypotheses=top_hypotheses,
            active_anchors=anchors[:3],
            missing_confirmation=_unique_flat(item.missing_confirmation for item in top_hypotheses)[:6],
            invalidating_signals_seen=_unique_flat(item.invalidating_signals for item in top_hypotheses)[:6],
            transition_watch=_unique_flat(item.transition_watch for item in top_hypotheses)[:6],
            notes=notes,
        )
        self._repository.save_belief_state(
            belief_state_id=belief.belief_state_id,
            instrument_symbol=instrument_symbol,
            observed_at=market_time,
            stored_at=stored_at,
            schema_version=self._schema_version,
            profile_version=profile_version,
            engine_version=engine_version,
            recognition_mode=recognition_mode.value,
            belief_payload=belief.model_dump(mode="json"),
        )
        return belief


def _unique_flat(groups: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for values in groups:
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered
