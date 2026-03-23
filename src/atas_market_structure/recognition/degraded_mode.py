from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from atas_market_structure.models import (
    BeliefDataStatus,
    DegradedMode,
    RecognitionMode,
)
from atas_market_structure.repository import AnalysisRepository


MACRO_STALE_AFTER = timedelta(minutes=20)
DEPTH_STALE_AFTER = timedelta(minutes=2)


@dataclass(frozen=True)
class RecognitionQualityState:
    """Recognition-ready data quality summary compatible with health semantics."""

    data_status: BeliefDataStatus
    recognition_mode: RecognitionMode


class RecognitionQualityEvaluator:
    """Reuses the ingestion-health semantics for deterministic recognition outputs."""

    def __init__(self, repository: AnalysisRepository, *, ai_available: bool = False) -> None:
        self._repository = repository
        self._ai_available = ai_available

    def evaluate(
        self,
        *,
        instrument_symbol: str,
        reference_time: datetime | None = None,
    ) -> RecognitionQualityState:
        now = reference_time or datetime.now(tz=UTC)
        latest_market = self._latest_ingestion(
            "market_structure",
            instrument_symbol=instrument_symbol,
            stored_at_before=now,
        )
        latest_process = self._latest_ingestion(
            "process_context",
            instrument_symbol=instrument_symbol,
            stored_at_before=now,
        )
        latest_depth = self._latest_ingestion(
            "depth_snapshot",
            instrument_symbol=instrument_symbol,
            stored_at_before=now,
        )
        latest_event = self._latest_ingestion(
            "event_snapshot",
            instrument_symbol=instrument_symbol,
            stored_at_before=now,
        )
        latest_adapter = self._latest_adapter_ingestion(
            instrument_symbol=instrument_symbol,
            stored_at_before=now,
        )

        macro_dt = self._latest_timestamp(
            self._extract_payload_timestamp(latest_market.observed_payload) if latest_market is not None else None,
            self._extract_payload_timestamp(latest_process.observed_payload) if latest_process is not None else None,
        )
        latest_any = self._latest_timestamp(
            macro_dt,
            self._extract_payload_timestamp(latest_depth.observed_payload) if latest_depth is not None else None,
            self._extract_payload_timestamp(latest_event.observed_payload) if latest_event is not None else None,
            self._extract_payload_timestamp(latest_adapter.observed_payload) if latest_adapter is not None else None,
        )

        depth_available = self._depth_available(latest_depth, reference_time=now)
        dom_available = self._dom_available(latest_depth, reference_time=now)
        degraded_modes: list[DegradedMode] = []
        if not depth_available:
            degraded_modes.append(DegradedMode.NO_DEPTH)
        if not dom_available:
            degraded_modes.append(DegradedMode.NO_DOM)
        if not self._ai_available:
            degraded_modes.append(DegradedMode.NO_AI)
        if macro_dt is None or now - macro_dt > MACRO_STALE_AFTER:
            degraded_modes.append(DegradedMode.STALE_MACRO)
        if self._replay_rebuild_active(instrument_symbol=instrument_symbol, stored_at_before=now):
            degraded_modes.append(DegradedMode.REPLAY_REBUILD)

        unique_modes = _dedupe_modes(degraded_modes)
        freshness = self._classify_freshness(latest_any, reference_time=now)
        completeness = "complete" if not unique_modes else "partial"
        if DegradedMode.REPLAY_REBUILD in unique_modes:
            completeness = "gapped"

        feature_completeness = 1.0
        if DegradedMode.REPLAY_REBUILD in unique_modes:
            feature_completeness = 0.5
        elif not depth_available and not dom_available:
            feature_completeness = 0.6
        elif not depth_available or not dom_available:
            feature_completeness = 0.75
        if DegradedMode.STALE_MACRO in unique_modes:
            feature_completeness = min(feature_completeness, 0.7)
        if DegradedMode.NO_AI in unique_modes:
            feature_completeness = min(feature_completeness, 0.95)

        freshness_ms = 0
        if latest_any is not None:
            freshness_ms = max(0, int((now - latest_any).total_seconds() * 1000))

        if DegradedMode.REPLAY_REBUILD in unique_modes:
            recognition_mode = RecognitionMode.REPLAY_REBUILD_MODE
        elif not depth_available:
            recognition_mode = RecognitionMode.DEGRADED_NO_DEPTH
        elif not dom_available:
            recognition_mode = RecognitionMode.DEGRADED_NO_DOM
        else:
            recognition_mode = RecognitionMode.NORMAL

        return RecognitionQualityState(
            data_status=BeliefDataStatus(
                data_freshness_ms=freshness_ms,
                feature_completeness=feature_completeness,
                depth_available=depth_available,
                dom_available=dom_available,
                ai_available=self._ai_available,
                degraded_modes=unique_modes,
                freshness=freshness,
                completeness=completeness,
            ),
            recognition_mode=recognition_mode,
        )

    def _depth_available(self, stored_ingestion: Any, *, reference_time: datetime) -> bool:
        if stored_ingestion is None:
            return False
        payload = stored_ingestion.observed_payload
        observed_at = self._extract_payload_timestamp(payload)
        if observed_at is None or reference_time - observed_at > DEPTH_STALE_AFTER:
            return False
        coverage_state = payload.get("coverage_state")
        return coverage_state not in {"depth_unavailable", "depth_interrupted"}

    def _dom_available(self, stored_ingestion: Any, *, reference_time: datetime) -> bool:
        if not self._depth_available(stored_ingestion, reference_time=reference_time):
            return False
        payload = stored_ingestion.observed_payload
        return payload.get("best_bid") is not None and payload.get("best_ask") is not None

    def _replay_rebuild_active(
        self,
        *,
        instrument_symbol: str,
        stored_at_before: datetime | None = None,
    ) -> bool:
        stored = self._latest_ingestion(
            "replay_workbench_snapshot",
            instrument_symbol=instrument_symbol,
            stored_at_before=stored_at_before,
        )
        if stored is None:
            return False
        payload = stored.observed_payload
        data_status = payload.get("data_status")
        if isinstance(data_status, dict):
            modes = data_status.get("degraded_modes") or []
            if "replay_rebuild" in modes:
                return True
        integrity = payload.get("integrity")
        if isinstance(integrity, dict):
            return integrity.get("status") in {"missing_local_history", "gaps_detected", "no_live_data"}
        return False

    def _latest_ingestion(
        self,
        ingestion_kind: str,
        *,
        instrument_symbol: str,
        stored_at_before: datetime | None = None,
    ) -> Any:
        items = self._repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            limit=1,
            stored_at_before=stored_at_before,
        )
        return items[0] if items else None

    def _latest_adapter_ingestion(
        self,
        *,
        instrument_symbol: str,
        stored_at_before: datetime | None = None,
    ) -> Any:
        candidates = [
            self._latest_ingestion(
                "adapter_continuous_state",
                instrument_symbol=instrument_symbol,
                stored_at_before=stored_at_before,
            ),
            self._latest_ingestion(
                "adapter_trigger_burst",
                instrument_symbol=instrument_symbol,
                stored_at_before=stored_at_before,
            ),
            self._latest_ingestion(
                "adapter_history_bars",
                instrument_symbol=instrument_symbol,
                stored_at_before=stored_at_before,
            ),
            self._latest_ingestion(
                "adapter_history_footprint",
                instrument_symbol=instrument_symbol,
                stored_at_before=stored_at_before,
            ),
        ]
        ranked = [
            (self._extract_payload_timestamp(item.observed_payload), item)
            for item in candidates
            if item is not None and self._extract_payload_timestamp(item.observed_payload) is not None
        ]
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return ranked[0][1]

    @staticmethod
    def _extract_payload_timestamp(payload: dict[str, Any]) -> datetime | None:
        for key in ("observed_at", "observed_window_end", "emitted_at", "stored_at"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                try:
                    return _parse_datetime(value)
                except ValueError:
                    continue
            if isinstance(value, datetime):
                return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return None

    @staticmethod
    def _classify_freshness(latest_at: datetime | None, *, reference_time: datetime) -> str:
        if latest_at is None:
            return "offline"
        lag_seconds = max(0, int((reference_time - latest_at).total_seconds()))
        if lag_seconds <= 10:
            return "fresh"
        if lag_seconds <= 60:
            return "delayed"
        return "stale"

    @staticmethod
    def _latest_timestamp(*values: datetime | None) -> datetime | None:
        available = [item for item in values if item is not None]
        if not available:
            return None
        return max(available)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _dedupe_modes(modes: list[DegradedMode]) -> list[DegradedMode]:
    unique: list[DegradedMode] = []
    for item in modes:
        if item not in unique:
            unique.append(item)
    return unique
