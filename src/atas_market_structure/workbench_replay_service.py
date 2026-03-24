from __future__ import annotations

# workbench replay entrypoint; keep new snapshot/live/backfill helpers out of this file to prevent monolith regrowth

from datetime import UTC, datetime, timedelta
import json
import logging
from threading import Lock
from typing import Any, Sequence
from uuid import uuid4


from atas_market_structure.continuous_contract_service import ContinuousContractService
from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterBackfillCommand,
    AdapterBackfillDispatchResponse,
    AdapterHistoryInventoryPayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintBar,
    AdapterHistoryFootprintPayload,
    AdapterInitiativeDriveState,
    AdapterPostHarvestResponseState,
    AdapterSamePriceReplenishmentState,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
    BeliefDataStatus,
    BuildPromptBlocksRequest,
    ChatAnnotation,
    ChatHandoffPacket,
    ChatHandoffRequest,
    ChatHandoffResponse,
    ChatMessage,
    ChatMessagesEnvelope,
    ChatObjectsEnvelope,
    ChatPlanCard,
    ChatReplyRequest,
    ChatReplyResponse,
    ChatSession,
    ChatSessionEnvelope,
    ChatSessionsEnvelope,
    ChatWindowRange,
    CreateChatMessageRequest,
    CreateChatSessionRequest,
    ContinuousAdjustmentMode,
    PromptBlock,
    PromptBlocksEnvelope,
    SessionMemory,
    SessionMemoryEnvelope,
    UpdateChatSessionRequest,
    UpdateMountedMessageRequest,
    ReplayAcquisitionMode,
    ReplayAiChatAttachment,
    ReplayAiBriefing,
    ReplayCachePolicy,
    ReplayFootprintBarDetail,
    ReplayFootprintLevelDetail,
    ReplayOperatorEntryAcceptedResponse,
    ReplayOperatorEntryEnvelope,
    ReplayOperatorEntryRecord,
    ReplayOperatorEntryRequest,
    ReplayManualRegionAnnotationAcceptedResponse,
    ReplayManualRegionAnnotationEnvelope,
    ReplayManualRegionAnnotationRecord,
    ReplayManualRegionAnnotationRequest,
    ReplayVerificationState,
    ReplayVerificationStatus,
    ReplayWorkbenchAcceptedResponse,
    ReplayWorkbenchAcceptedSummary,
    ReplayWorkbenchAckRebuildResult,
    ReplayWorkbenchAckVerification,
    ReplayWorkbenchAtasBackfillAcceptedResponse,
    ReplayWorkbenchBackfillProgressRange,
    ReplayWorkbenchBackfillProgressResponse,
    ReplayWorkbenchAtasBackfillRecord,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchAtasBackfillStatus,
    ReplayWorkbenchBuildAction,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchCacheRecord,
    ReplayWorkbenchBackfillRange,
    ReplayWorkbenchGapSegment,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchIntegrity,
    ReplayWorkbenchLiveSourceStatus,
    ReplayWorkbenchLiveStatusResponse,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
    ReplayChartBar,
    ReplayEventAnnotation,
    ReplayFocusRegion,
    ReplayLiveStreamState,
    ReplayStrategyCandidate,
    RecognitionMode,
    DegradedMode,
    RollMode,
    StructureSide,
    Timeframe,
)
from atas_market_structure.chart_identity import (
    chart_instance_ids_match,
    is_generic_chart_instance_id,
    normalize_identifier,
    normalize_symbol,
    normalize_timeframe,
)
from atas_market_structure.repository import (
    AnalysisRepository,
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredIngestion,
    StoredPromptBlock,
    StoredSessionMemory,
)
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine
from atas_market_structure.workbench_common import (
    ReplayWorkbenchNotFoundError,
    parse_utc,
    payload_to_model,
)

LOGGER = logging.getLogger(__name__)

class ReplayWorkbenchService:
    _BUILD_RESPONSE_SCHEMA_VERSION = "replay_workbench_build_response_v1"
    _SNAPSHOT_SCHEMA_VERSION = "replay_workbench_snapshot_v1"
    _LIVE_STATUS_SCHEMA_VERSION = "replay_workbench_live_status_v1"
    _LIVE_TAIL_SCHEMA_VERSION = "replay_workbench_live_tail_v1"
    _BACKFILL_PROGRESS_SCHEMA_VERSION = "replay_workbench_backfill_progress_v1"
    _FALLBACK_PROFILE_VERSION = "profile_unassigned"
    _FALLBACK_ENGINE_VERSION = "engine_unassigned"
    """Stores replay-workbench packets and builds replay snapshots from local adapter history."""

    _TIMEFRAME_MINUTES: dict[Timeframe, int] = {
        Timeframe.MIN_1: 1,
        Timeframe.MIN_5: 5,
        Timeframe.MIN_15: 15,
        Timeframe.MIN_30: 30,
        Timeframe.HOUR_1: 60,
        Timeframe.DAY_1: 1440,
    }
    _INITIAL_WINDOW_BARS: dict[Timeframe, int] = {
        Timeframe.MIN_1: 180,   # 3h
        Timeframe.MIN_5: 576,   # 2d
        Timeframe.MIN_15: 480,  # 5d
        Timeframe.MIN_30: 360,  # 7.5d
        Timeframe.HOUR_1: 336,  # 14d
        Timeframe.DAY_1: 365,   # 1y
    }

    # Defensive limit: never insert an unbounded amount of synthetic filler bars.
    # (UI would choke, and it usually indicates upstream history coverage issues.)
    _MAX_GAP_FILL_BARS: int = 600
    _MAX_GAP_FILL_BARS_PER_SEGMENT: int = 30
    _BACKFILL_REQUEST_TTL = timedelta(minutes=5)
    _BACKFILL_DISPATCH_LEASE = timedelta(seconds=12)
    _BACKFILL_RECORD_RETENTION = timedelta(hours=2)

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._replay_ai_chat_service = None
        self._continuous_contract_service = ContinuousContractService(repository=repository)
        self._backfill_lock = Lock()
        self._backfill_requests: dict[str, ReplayWorkbenchAtasBackfillRecord] = {}

    def _resolve_active_versions(self, instrument_symbol: str | None) -> tuple[str, str]:
        profile_version = self._FALLBACK_PROFILE_VERSION
        if instrument_symbol:
            profile = self._repository.get_active_instrument_profile(instrument_symbol.upper())
            if profile is not None:
                profile_version = profile.profile_version
        build = self._repository.get_active_recognizer_build()
        engine_version = build.engine_version if build is not None else self._FALLBACK_ENGINE_VERSION
        return profile_version, engine_version

    def ingest_replay_snapshot(self, payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchAcceptedResponse:
        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="replay_workbench_snapshot",
            source_snapshot_id=payload.replay_snapshot_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayWorkbenchAcceptedResponse(
            ingestion_id=ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            stored_at=stored_at,
            summary=self._build_summary(payload),
        )

    def ingest_history_inventory(self, payload: AdapterHistoryInventoryPayload) -> dict[str, Any]:
        timeframe = payload.bar_timeframe
        timeframe_minutes = self._TIMEFRAME_MINUTES.get(timeframe)
        instrument_symbol = self._normalize_symbol_for_storage(payload.instrument.symbol) or "UNKNOWN"
        contract_symbol = self._normalize_symbol_for_storage(
            payload.instrument.contract_symbol or payload.instrument.symbol
        )
        root_symbol = self._normalize_symbol_for_storage(
            payload.instrument.root_symbol or payload.instrument.symbol
        )
        chart_instance_id = str(payload.source.chart_instance_id or "").strip() or None

        visible_start = payload.first_loaded_bar_started_at_utc or payload.observed_window_start
        visible_end = (
            payload.latest_loaded_bar_started_at_utc
            or payload.latest_completed_bar_started_at_utc
            or payload.observed_window_end
        )
        if visible_start is None or visible_end is None:
            LOGGER.info(
                "ingest_history_inventory: no visible coverage instrument_symbol=%s chart_instance_id=%s timeframe=%s",
                instrument_symbol,
                chart_instance_id,
                timeframe.value,
            )
            return {
                "queued": False,
                "status": "ignored",
                "reason": "missing_visible_window",
                "instrument_symbol": instrument_symbol,
                "chart_instance_id": chart_instance_id,
                "timeframe": timeframe.value,
            }

        visible_start = self._ensure_utc(visible_start)
        visible_end = self._ensure_utc(visible_end)
        if visible_end < visible_start:
            visible_start, visible_end = visible_end, visible_start

        loaded_bar_count = max(
            int(payload.loaded_bar_count or 0),
            int(payload.latest_loaded_bar_index or -1) + 1,
        )
        if loaded_bar_count <= 0:
            LOGGER.info(
                "ingest_history_inventory: loaded_bar_count=0 instrument_symbol=%s chart_instance_id=%s timeframe=%s",
                instrument_symbol,
                chart_instance_id,
                timeframe.value,
            )
            return {
                "queued": False,
                "status": "ignored",
                "reason": "empty_visible_window",
                "instrument_symbol": instrument_symbol,
                "chart_instance_id": chart_instance_id,
                "timeframe": timeframe.value,
            }

        stored_first, stored_last, stored_count = self._repository.get_atas_chart_bars_raw_coverage(
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            root_symbol=root_symbol,
            timeframe=timeframe.value,
            window_start=visible_start,
            window_end=visible_end,
        )
        LOGGER.info(
            "ingest_history_inventory: visible_window instrument_symbol=%s chart_instance_id=%s contract_symbol=%s root_symbol=%s timeframe=%s loaded_bar_count=%s visible_start=%s visible_end=%s stored_count=%s stored_first=%s stored_last=%s",
            instrument_symbol,
            chart_instance_id,
            contract_symbol,
            root_symbol,
            timeframe.value,
            loaded_bar_count,
            visible_start.isoformat(),
            visible_end.isoformat(),
            stored_count,
            stored_first.isoformat() if stored_first is not None else None,
            stored_last.isoformat() if stored_last is not None else None,
        )

        requested_ranges: list[ReplayWorkbenchBackfillRange] = []
        reason = "history_inventory_visible_window_changed"
        if stored_count <= 0 or stored_first is None or stored_last is None:
            requested_ranges.append(
                ReplayWorkbenchBackfillRange(range_start=visible_start, range_end=visible_end)
            )
            reason = "history_inventory_window_unstored"
        else:
            left_gap_end = stored_first - timedelta(seconds=1)
            if visible_start <= left_gap_end:
                requested_ranges.append(
                    ReplayWorkbenchBackfillRange(
                        range_start=visible_start,
                        range_end=min(visible_end, left_gap_end),
                    )
                )

            right_gap_start = stored_last + timedelta(seconds=1)
            if right_gap_start <= visible_end:
                requested_ranges.append(
                    ReplayWorkbenchBackfillRange(
                        range_start=max(visible_start, right_gap_start),
                        range_end=visible_end,
                    )
                )

            if not requested_ranges and stored_count + 1 < loaded_bar_count:
                requested_ranges.append(
                    ReplayWorkbenchBackfillRange(range_start=visible_start, range_end=visible_end)
                )
                reason = "history_inventory_sparse_window_repair"

        if not requested_ranges:
            return {
                "queued": False,
                "status": "up_to_date",
                "reason": "stored_window_covers_visible_window",
                "instrument_symbol": instrument_symbol,
                "chart_instance_id": chart_instance_id,
                "contract_symbol": contract_symbol,
                "root_symbol": root_symbol,
                "timeframe": timeframe.value,
                "visible_window_start": visible_start,
                "visible_window_end": visible_end,
                "stored_count": stored_count,
                "loaded_bar_count": loaded_bar_count,
            }

        cache_key = self._build_history_inventory_cache_key(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            timeframe=timeframe,
            window_start=visible_start,
            window_end=visible_end,
        )
        accepted = self.request_atas_backfill(
            ReplayWorkbenchAtasBackfillRequest(
                cache_key=cache_key,
                instrument_symbol=instrument_symbol,
                contract_symbol=contract_symbol,
                root_symbol=root_symbol,
                target_contract_symbol=contract_symbol,
                target_root_symbol=root_symbol,
                display_timeframe=timeframe,
                window_start=visible_start,
                window_end=visible_end,
                chart_instance_id=chart_instance_id,
                reason=reason,
                request_history_bars=True,
                request_history_footprint=False,
                replace_existing_history=False,
                requested_ranges=requested_ranges,
            )
        )
        LOGGER.info(
            "ingest_history_inventory: queued_backfill request_id=%s reused=%s instrument_symbol=%s chart_instance_id=%s timeframe=%s range_count=%s reason=%s",
            accepted.request.request_id,
            accepted.reused_existing_request,
            instrument_symbol,
            chart_instance_id,
            timeframe.value,
            len(accepted.request.requested_ranges),
            reason,
        )
        return {
            "queued": True,
            "status": "queued",
            "reason": reason,
            "request_id": accepted.request.request_id,
            "reused_existing_request": accepted.reused_existing_request,
            "instrument_symbol": instrument_symbol,
            "chart_instance_id": chart_instance_id,
            "contract_symbol": contract_symbol,
            "root_symbol": root_symbol,
            "timeframe": timeframe.value,
            "visible_window_start": visible_start,
            "visible_window_end": visible_end,
            "stored_count": stored_count,
            "loaded_bar_count": loaded_bar_count,
            "requested_ranges": [
                {
                    "range_start": item.range_start,
                    "range_end": item.range_end,
                }
                for item in accepted.request.requested_ranges
            ],
            "timeframe_minutes": timeframe_minutes,
        }

    def _build_integrity(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        candle_gaps: list[dict[str, Any]] | None,
        latest_backfill_request: ReplayWorkbenchAtasBackfillRecord | None = None,
        status_override: str | None = None,
        window_days: int = 7,
        latest_adapter_sync_at: datetime | None = None,
    ) -> ReplayWorkbenchIntegrity:
        missing_segments = self._gap_segments_from_gap_dicts(candle_gaps or [])
        missing_bar_count = sum(segment.missing_bar_count for segment in missing_segments)
        if status_override is not None:
            status = status_override
        elif missing_segments:
            status = "gaps_detected"
        else:
            status = "complete"
        freshness = self._classify_freshness(latest_adapter_sync_at)
        completeness = self._classify_completeness(status=status, missing_bar_count=missing_bar_count)
        latest_data_status = "degraded" if status != "complete" else "complete"
        return ReplayWorkbenchIntegrity(
            status=status,
            window_start=window_start,
            window_end=window_end,
            window_days=window_days,
            gap_count=len(missing_segments),
            missing_bar_count=missing_bar_count,
            completeness=completeness,
            freshness=freshness,
            latest_data_status=latest_data_status,
            missing_segments=missing_segments,
            latest_backfill_request_id=latest_backfill_request.request_id if latest_backfill_request is not None else None,
            latest_backfill_status=latest_backfill_request.status if latest_backfill_request is not None else None,
        )

    @staticmethod
    def _classify_freshness(latest_adapter_sync_at: datetime | None) -> str:
        if latest_adapter_sync_at is None:
            return "offline"
        lag_seconds = max(0, int((datetime.now(tz=UTC) - latest_adapter_sync_at).total_seconds()))
        if lag_seconds <= 10:
            return "fresh"
        if lag_seconds <= 60:
            return "delayed"
        return "stale"

    @staticmethod
    def _classify_completeness(*, status: str, missing_bar_count: int) -> str:
        if status in {"complete"} and missing_bar_count == 0:
            return "complete"
        if status in {"no_live_data", "missing_local_history"}:
            return "partial"
        if missing_bar_count > 0:
            return "gapped"
        return "partial"

    def _build_data_status(
        self,
        *,
        latest_adapter_sync_at: datetime | None,
        integrity: ReplayWorkbenchIntegrity | None,
        ai_available: bool = False,
    ) -> BeliefDataStatus:
        freshness = self._classify_freshness(latest_adapter_sync_at)
        completeness = "partial"
        degraded_modes: list[DegradedMode] = [DegradedMode.NO_DEPTH, DegradedMode.NO_DOM]
        recognition_mode = RecognitionMode.DEGRADED_NO_DEPTH
        if integrity is not None:
            completeness = integrity.completeness or self._classify_completeness(
                status=integrity.status,
                missing_bar_count=integrity.missing_bar_count,
            )
            if integrity.status in {"missing_local_history", "gaps_detected", "no_live_data"}:
                degraded_modes.append(DegradedMode.REPLAY_REBUILD)
                recognition_mode = RecognitionMode.REPLAY_REBUILD_MODE
        if ai_available:
            ai_flag = True
        else:
            ai_flag = False
            degraded_modes.append(DegradedMode.NO_AI)
        deduped_modes: list[DegradedMode] = []
        for item in degraded_modes:
            if item not in deduped_modes:
                deduped_modes.append(item)
        feature_completeness = 1.0
        if completeness == "gapped":
            feature_completeness = 0.6
        elif completeness == "partial":
            feature_completeness = 0.8
        elif freshness in {"delayed", "stale", "offline"}:
            feature_completeness = 0.85
        freshness_ms = 0
        if latest_adapter_sync_at is not None:
            freshness_ms = max(0, int((datetime.now(tz=UTC) - latest_adapter_sync_at).total_seconds() * 1000))
        return BeliefDataStatus(
            data_freshness_ms=freshness_ms,
            feature_completeness=feature_completeness,
            depth_available=False,
            dom_available=False,
            ai_available=ai_flag,
            degraded_modes=deduped_modes,
            freshness=freshness,
            completeness=completeness,
        )

    @staticmethod
    def _gap_segments_from_gap_dicts(candle_gaps: list[dict[str, Any]]) -> list[ReplayWorkbenchGapSegment]:
        segments: list[ReplayWorkbenchGapSegment] = []
        for item in candle_gaps:
            next_started_at = item.get("next_started_at")
            missing_bar_count = item.get("missing_bar_count")
            if next_started_at is None or missing_bar_count is None:
                continue
            prev_ended_at = item.get("prev_ended_at")
            segments.append(
                ReplayWorkbenchGapSegment(
                    prev_ended_at=prev_ended_at,
                    next_started_at=next_started_at,
                    missing_bar_count=max(1, int(missing_bar_count)),
                )
            )
        return segments

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _derive_backfill_ranges_from_missing_segments(
        self,
        *,
        display_timeframe: Timeframe,
        missing_segments: list[ReplayWorkbenchGapSegment],
    ) -> list[ReplayWorkbenchBackfillRange]:
        if not missing_segments:
            return []
        timeframe_minutes = max(1, self._TIMEFRAME_MINUTES.get(display_timeframe, 1))
        expected_delta = timedelta(minutes=timeframe_minutes)
        derived: list[ReplayWorkbenchBackfillRange] = []
        for segment in missing_segments:
            missing_bar_count = max(1, int(segment.missing_bar_count))
            if segment.prev_ended_at is not None:
                range_start = self._ensure_utc(segment.prev_ended_at) + timedelta(seconds=1)
            else:
                range_start = self._ensure_utc(segment.next_started_at) - (expected_delta * missing_bar_count)
            range_end = range_start + (expected_delta * missing_bar_count) - timedelta(seconds=1)
            derived.append(ReplayWorkbenchBackfillRange(range_start=range_start, range_end=range_end))
        return derived

    def _normalize_backfill_ranges(
        self,
        *,
        requested_ranges: list[ReplayWorkbenchBackfillRange],
        window_start: datetime,
        window_end: datetime,
    ) -> list[ReplayWorkbenchBackfillRange]:
        window_start_utc = self._ensure_utc(window_start)
        window_end_utc = self._ensure_utc(window_end)
        if window_end_utc < window_start_utc:
            return []

        clamped: list[tuple[datetime, datetime]] = []
        for item in requested_ranges:
            range_start_utc = max(self._ensure_utc(item.range_start), window_start_utc)
            range_end_utc = min(self._ensure_utc(item.range_end), window_end_utc)
            if range_end_utc < range_start_utc:
                continue
            clamped.append((range_start_utc, range_end_utc))

        if not clamped:
            return []

        clamped.sort(key=lambda value: (value[0], value[1]))
        merged: list[ReplayWorkbenchBackfillRange] = []
        current_start, current_end = clamped[0]
        for next_start, next_end in clamped[1:]:
            if next_start <= current_end + timedelta(seconds=1):
                current_end = max(current_end, next_end)
                continue
            merged.append(ReplayWorkbenchBackfillRange(range_start=current_start, range_end=current_end))
            current_start, current_end = next_start, next_end
        merged.append(ReplayWorkbenchBackfillRange(range_start=current_start, range_end=current_end))
        return merged

    def _build_requested_backfill_ranges(
        self,
        *,
        display_timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        missing_segments: list[ReplayWorkbenchGapSegment],
        requested_ranges: list[ReplayWorkbenchBackfillRange],
    ) -> list[ReplayWorkbenchBackfillRange]:
        candidates = requested_ranges
        if not candidates:
            candidates = self._derive_backfill_ranges_from_missing_segments(
                display_timeframe=display_timeframe,
                missing_segments=missing_segments,
            )
        normalized = self._normalize_backfill_ranges(
            requested_ranges=candidates,
            window_start=window_start,
            window_end=window_end,
        )
        if normalized:
            return normalized
        fallback = ReplayWorkbenchBackfillRange(
            range_start=self._ensure_utc(window_start),
            range_end=self._ensure_utc(window_end),
        )
        return self._normalize_backfill_ranges(
            requested_ranges=[fallback],
            window_start=window_start,
            window_end=window_end,
        )

    def _find_latest_backfill_request(
        self,
        *,
        cache_key: str | None,
        instrument_symbol: str,
        display_timeframe: Timeframe,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        with self._backfill_lock:
            now = datetime.now(tz=UTC)
            self._expire_backfill_requests_locked(now)
            candidates = [
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and record.display_timeframe == display_timeframe
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda item: item.requested_at, reverse=True)
            if cache_key is not None:
                exact = [record for record in candidates if record.cache_key == cache_key]
                if exact:
                    return exact[0]
                return None
            return candidates[0]

    def _find_matching_backfill_progress_request(
        self,
        *,
        cache_key: str | None,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None,
        contract_symbol: str | None,
        root_symbol: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        exact = self._find_latest_backfill_request(
            cache_key=cache_key,
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
        )
        if exact is not None:
            return exact

        with self._backfill_lock:
            now = datetime.now(tz=UTC)
            self._expire_backfill_requests_locked(now)
            candidates = [
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and record.display_timeframe == display_timeframe
            ]
            if chart_instance_id:
                candidates = [
                    record
                    for record in candidates
                    if record.chart_instance_id is None
                    or self._backfill_chart_instance_matches(
                        chart_instance_id,
                        record.chart_instance_id,
                        instrument_symbol=record.instrument_symbol,
                        contract_symbol=record.contract_symbol or record.target_contract_symbol,
                        display_timeframe=record.display_timeframe,
                    )
                ]
            if contract_symbol:
                candidates = [
                    record
                    for record in candidates
                    if record.contract_symbol is None
                    or record.contract_symbol == contract_symbol
                    or record.target_contract_symbol == contract_symbol
                ]
            if root_symbol:
                candidates = [
                    record
                    for record in candidates
                    if record.root_symbol is None
                    or record.root_symbol == root_symbol
                    or record.target_root_symbol == root_symbol
                ]
            if window_start is not None and window_end is not None:
                candidates = [
                    record
                    for record in candidates
                    if not (record.window_end < window_start or record.window_start > window_end)
                ]
            if not candidates:
                return None
            candidates.sort(key=lambda item: (item.requested_at, item.request_id), reverse=True)
            return candidates[0]

    def _find_relevant_live_tail_backfill_request(
        self,
        *,
        cache_key: str | None,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        exact = self._find_latest_backfill_request(
            cache_key=cache_key,
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
        )
        if exact is not None:
            return exact

        if window_start is None or window_end is None:
            return None

        with self._backfill_lock:
            now = datetime.now(tz=UTC)
            self._expire_backfill_requests_locked(now)
            candidates = [
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and record.display_timeframe == display_timeframe
            ]
            if chart_instance_id:
                candidates = [
                    record
                    for record in candidates
                    if (
                        self._backfill_chart_instance_matches(
                            chart_instance_id,
                            record.chart_instance_id,
                            instrument_symbol=record.instrument_symbol,
                            contract_symbol=record.contract_symbol or record.target_contract_symbol,
                            display_timeframe=record.display_timeframe,
                        )
                        or self._backfill_chart_instance_matches(
                            chart_instance_id,
                            record.dispatched_chart_instance_id,
                            instrument_symbol=record.instrument_symbol,
                            contract_symbol=record.contract_symbol or record.target_contract_symbol,
                            display_timeframe=record.display_timeframe,
                        )
                        or self._backfill_chart_instance_matches(
                            chart_instance_id,
                            record.acknowledged_chart_instance_id,
                            instrument_symbol=record.instrument_symbol,
                            contract_symbol=record.contract_symbol or record.target_contract_symbol,
                            display_timeframe=record.display_timeframe,
                        )
                    )
                ]
            overlapping = [
                record
                for record in candidates
                if record.window_start <= window_end and record.window_end >= window_start
            ]
            if not overlapping:
                return None
            overlapping.sort(
                key=lambda item: (
                    item.acknowledged_at or item.dispatched_at or item.requested_at,
                    item.requested_at,
                ),
                reverse=True,
            )
            return overlapping[0]

    def _maybe_request_backfill_for_integrity(
        self,
        *,
        cache_key: str,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        chart_instance_id: str | None,
        integrity: ReplayWorkbenchIntegrity,
        reason: str,
        request_history_bars: bool = True,
        request_history_footprint: bool = True,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        if not integrity.missing_segments and integrity.status != "missing_local_history":
            return None
        accepted = self.request_atas_backfill(
            ReplayWorkbenchAtasBackfillRequest(
                cache_key=cache_key,
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                window_start=window_start,
                window_end=window_end,
                chart_instance_id=chart_instance_id,
                missing_segments=integrity.missing_segments,
                reason=reason,
                request_history_bars=request_history_bars,
                request_history_footprint=request_history_footprint,
            )
        )
        return accepted.request

    def _with_backfill_metadata(
        self,
        integrity: ReplayWorkbenchIntegrity,
        backfill_request: ReplayWorkbenchAtasBackfillRecord | None,
    ) -> ReplayWorkbenchIntegrity:
        if backfill_request is None:
            return integrity
        return integrity.model_copy(
            update={
                "latest_backfill_request_id": backfill_request.request_id,
                "latest_backfill_status": backfill_request.status,
            }
        )

    def get_cache_record(self, cache_key: str, allow_fuzzy: bool = False) -> ReplayWorkbenchCacheEnvelope:
        stored = self._find_latest_replay_snapshot(cache_key=cache_key)
        matched_cache_key = cache_key

        if stored is None and allow_fuzzy:
            fuzzy_match = self._find_latest_replay_snapshot_by_cache_identity(cache_key)
            if fuzzy_match is not None:
                matched_cache_key, stored = fuzzy_match

        if stored is None:
            return ReplayWorkbenchCacheEnvelope(
                cache_key=cache_key,
                record=None,
                auto_fetch_allowed=True,
                verification_due_now=False,
            )

        payload = ReplayWorkbenchSnapshotPayload.model_validate(stored.observed_payload)
        verification_due_now = self._is_verification_due(payload=payload)
        auto_fetch_allowed = self._is_auto_fetch_allowed(payload=payload)
        return ReplayWorkbenchCacheEnvelope(
            cache_key=matched_cache_key,
            record=self._build_cache_record(stored, payload),
            auto_fetch_allowed=auto_fetch_allowed,
            verification_due_now=verification_due_now,
        )

    def invalidate_cache_record(self, request: ReplayWorkbenchInvalidationRequest) -> ReplayWorkbenchInvalidationResponse:
        stored = self._find_latest_replay_snapshot(
            cache_key=request.cache_key,
            replay_snapshot_id=request.replay_snapshot_id,
            ingestion_id=request.ingestion_id,
        )
        if stored is None:
            raise ReplayWorkbenchNotFoundError("No replay cache record matched the invalidation request.")

        payload = ReplayWorkbenchSnapshotPayload.model_validate(stored.observed_payload)
        invalidated_at = datetime.now(tz=UTC)
        payload.verification_state.status = ReplayVerificationStatus.INVALIDATED
        payload.verification_state.invalidated_at = invalidated_at
        payload.verification_state.invalidation_reason = request.invalidation_reason
        payload.verification_state.locked_until_manual_reset = False
        payload.verification_state.next_verification_due_at = None

        updated = self._repository.update_ingestion_observed_payload(
            ingestion_id=stored.ingestion_id,
            observed_payload=payload.model_dump(mode="json"),
        )
        if updated is None:
            raise ReplayWorkbenchNotFoundError(f"Replay cache record '{stored.ingestion_id}' disappeared before invalidation.")

        return ReplayWorkbenchInvalidationResponse(
            ingestion_id=stored.ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            cache_key=payload.cache_key,
            invalidated_at=invalidated_at,
            invalidation_reason=request.invalidation_reason,
            verification_status=payload.verification_state.status,
            locked_until_manual_reset=payload.verification_state.locked_until_manual_reset,
        )

    def get_live_status(
        self,
        *,
        instrument_symbol: str,
        replay_ingestion_id: str | None = None,
    ) -> ReplayWorkbenchLiveStatusResponse:
        now = datetime.now(tz=UTC)
        profile_version, engine_version = self._resolve_active_versions(instrument_symbol)
        latest_continuous_state = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=instrument_symbol,
        )
        latest_history_bars = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_history_bars",
            instrument_symbol=instrument_symbol,
        )
        latest_history_footprint = self._get_latest_ingestion_status(
            now=now,
            ingestion_kind="adapter_history_footprint",
            instrument_symbol=instrument_symbol,
        )

        latest_times = [
            item.latest_stored_at
            for item in (latest_continuous_state, latest_history_bars, latest_history_footprint)
            if item.latest_stored_at is not None
        ]
        latest_adapter_sync_at = max(latest_times) if latest_times else None
        latest_adapter_sync_lag_seconds = (
            max(0, int((now - latest_adapter_sync_at).total_seconds()))
            if latest_adapter_sync_at is not None
            else None
        )

        if latest_adapter_sync_lag_seconds is None:
            stream_state = ReplayLiveStreamState.OFFLINE
        elif latest_adapter_sync_lag_seconds <= 10:
            stream_state = ReplayLiveStreamState.LIVE
        elif latest_adapter_sync_lag_seconds <= 60:
            stream_state = ReplayLiveStreamState.DELAYED
        else:
            stream_state = ReplayLiveStreamState.STALE

        replay_snapshot_stored_at: datetime | None = None
        if replay_ingestion_id is not None:
            replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
            if replay_ingestion is not None:
                replay_snapshot_stored_at = replay_ingestion.stored_at

        should_refresh_snapshot = bool(
            latest_adapter_sync_at is not None
            and (
                replay_snapshot_stored_at is None
                or latest_adapter_sync_at > replay_snapshot_stored_at
            )
        )

        return ReplayWorkbenchLiveStatusResponse(
            schema_version=self._LIVE_STATUS_SCHEMA_VERSION,
            profile_version=profile_version,
            engine_version=engine_version,
            data_status=self._build_data_status(
                latest_adapter_sync_at=latest_adapter_sync_at,
                integrity=self._build_integrity(
                    window_start=now - timedelta(days=7),
                    window_end=now,
                    candle_gaps=[],
                    status_override="complete" if latest_adapter_sync_at is not None else "no_live_data",
                    latest_adapter_sync_at=latest_adapter_sync_at,
                ),
                ai_available=self._replay_ai_chat_service is not None,
            ),
            instrument_symbol=instrument_symbol,
            replay_ingestion_id=replay_ingestion_id,
            replay_snapshot_stored_at=replay_snapshot_stored_at,
            latest_adapter_sync_at=latest_adapter_sync_at,
            latest_adapter_sync_lag_seconds=latest_adapter_sync_lag_seconds,
            stream_state=stream_state,
            should_refresh_snapshot=should_refresh_snapshot,
            latest_continuous_state=latest_continuous_state,
            latest_history_bars=latest_history_bars,
            latest_history_footprint=latest_history_footprint,
        )

    def get_live_tail(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None = None,
        lookback_bars: int = 4,
    ) -> ReplayWorkbenchLiveTailResponse:
        symbol = instrument_symbol.upper()
        profile_version, engine_version = self._resolve_active_versions(symbol)

        # Fast path: query pre-aggregated bars from chart_candles first.
        timeframe_minutes = self._TIMEFRAME_MINUTES.get(display_timeframe, 1)
        required_minutes = (timeframe_minutes * max(lookback_bars, 2)) + 3
        now_utc = datetime.now(tz=UTC)
        preaggregated_candles: list[ReplayChartBar] = []
        history_source_kind = "none"
        # Keep the chart-candle fast path bounded near "now". Using a wide 7d
        # ASC window with LIMIT can accidentally return an old prefix when the
        # market has already produced >limit bars.
        preaggregated_window_minutes = max(required_minutes * 8, timeframe_minutes * 64, 180)
        preaggregated_window_start = now_utc - timedelta(minutes=preaggregated_window_minutes)
        preaggregated_limit = max(500, lookback_bars * 20)
        preaggregated_candles = self._load_live_tail_raw_mirror_candles(
            instrument_symbol=symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=chart_instance_id,
            window_start=preaggregated_window_start,
            window_end=now_utc,
            limit=preaggregated_limit,
        )
        if preaggregated_candles:
            history_source_kind = "atas_chart_bars_raw"

        try:
            if not preaggregated_candles:
                chart_rows = self._repository.list_chart_candles(
                    symbol=symbol,
                    timeframe=display_timeframe.value,
                    window_start=preaggregated_window_start,
                    window_end=now_utc,
                    limit=preaggregated_limit,
                )
                preaggregated_candles = [
                    ReplayChartBar(
                        started_at=row.started_at,
                        ended_at=row.ended_at,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                        delta=row.delta,
                        bid_volume=None,
                        ask_volume=None,
                        source_kind="chart_candles",
                        is_synthetic=False,
                    )
                    for row in chart_rows
                    # Keep the legacy behavior: pure zero-activity heartbeat bars should
                    # not be surfaced as live candles.
                    if (
                        (row.volume or 0) > 0
                        or abs(float(row.close) - float(row.open)) > 1e-9
                    )
                ]
                if preaggregated_candles:
                    history_source_kind = "chart_candles"
        except Exception:
            if history_source_kind == "none":
                preaggregated_candles = []

        tick_quote = self._try_get_latest_tick_quote(symbol)
        tick_observed_at = tick_quote.get("observed_at") if tick_quote is not None else None
        if isinstance(tick_observed_at, str):
            try:
                tick_observed_at = parse_utc(tick_observed_at)
            except Exception:
                tick_observed_at = None
        if not isinstance(tick_observed_at, datetime):
            tick_observed_at = None

        tick_latest_price = self._to_float_or_none(
            tick_quote.get("last_price") if tick_quote is not None else None
        )
        tick_best_bid = self._to_float_or_none(
            tick_quote.get("best_bid") if tick_quote is not None else None
        )
        tick_best_ask = self._to_float_or_none(
            tick_quote.get("best_ask") if tick_quote is not None else None
        )

        # Pull enough recent continuous-state messages for overlays and rich state.
        estimated_messages_per_minute = 6  # ~10s cadence (tune if adapter cadence changes)
        candidates_limit = int(required_minutes * estimated_messages_per_minute * 3)
        candidates_limit = max(5000, min(50000, candidates_limit))

        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=symbol,
            limit=candidates_limit,
        )
        matched: list[tuple[datetime, StoredIngestion]] = []
        latest_payload: dict[str, Any] | None = None
        latest_observed_at: datetime | None = None
        for stored in candidates:
            payload = stored.observed_payload
            if not self._chart_instance_filter_matches_dict_payload(chart_instance_id, payload):
                continue
            observed_at = self._payload_observed_at(payload)
            matched.append((observed_at, stored))
            if latest_observed_at is None or observed_at > latest_observed_at:
                latest_observed_at = observed_at
                latest_payload = payload

        if tick_observed_at is not None and (latest_observed_at is None or tick_observed_at > latest_observed_at):
            latest_observed_at = tick_observed_at

        if latest_observed_at is None and preaggregated_candles:
            latest_observed_at = preaggregated_candles[-1].ended_at

        if latest_observed_at is None and latest_payload is None and not preaggregated_candles and tick_quote is None:
            return ReplayWorkbenchLiveTailResponse(
                schema_version=self._LIVE_TAIL_SCHEMA_VERSION,
                profile_version=profile_version,
                engine_version=engine_version,
                data_status=self._build_data_status(
                    latest_adapter_sync_at=None,
                    integrity=self._build_integrity(
                        window_start=datetime.now(tz=UTC) - timedelta(days=7),
                        window_end=datetime.now(tz=UTC),
                        candle_gaps=[],
                        latest_backfill_request=self._find_latest_backfill_request(
                            cache_key=f"{instrument_symbol}|{display_timeframe}|empty|empty",
                            instrument_symbol=instrument_symbol,
                            display_timeframe=display_timeframe,
                        ),
                        status_override="no_live_data",
                        latest_adapter_sync_at=None,
                    ),
                    ai_available=self._replay_ai_chat_service is not None,
                ),
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                latest_observed_at=None,
                latest_price=None,
                best_bid=None,
                best_ask=None,
                source_message_count=0,
                candles=[],
                event_annotations=[],
                focus_regions=[],
                trade_summary=None,
                significant_liquidity=[],
                same_price_replenishment=[],
                active_initiative_drive=None,
                active_post_harvest_response=None,
                integrity=self._build_integrity(
                    window_start=datetime.now(tz=UTC) - timedelta(days=7),
                    window_end=datetime.now(tz=UTC),
                    candle_gaps=[],
                    latest_backfill_request=self._find_latest_backfill_request(
                        cache_key=f"{instrument_symbol}|{display_timeframe}|empty|empty",
                        instrument_symbol=instrument_symbol,
                        display_timeframe=display_timeframe,
                    ),
                    status_override="no_live_data",
                    latest_adapter_sync_at=None,
                ),
                snapshot_refresh_required=False,
                latest_backfill_request=None,
            )

        recent_messages: list[StoredIngestion] = []
        if latest_observed_at is not None:
            recent_cutoff = latest_observed_at - timedelta(
                minutes=(self._TIMEFRAME_MINUTES.get(display_timeframe, 1) * max(lookback_bars, 2)) + 1
            )
            if preaggregated_candles:
                chart_tail_cutoff = preaggregated_candles[-1].ended_at - timedelta(minutes=timeframe_minutes)
                if chart_tail_cutoff < recent_cutoff:
                    recent_cutoff = chart_tail_cutoff
            recent_messages = [stored for observed_at, stored in matched if observed_at >= recent_cutoff]
            recent_messages.sort(key=lambda item: self._payload_observed_at(item.observed_payload))

        continuous_overlay_count = 0
        if preaggregated_candles:
            live_candles = preaggregated_candles
            if recent_messages:
                live_candles, continuous_overlay_count = self._merge_history_candles_with_continuous_overlay(
                    history_candles=live_candles,
                    continuous_messages=recent_messages,
                    timeframe=display_timeframe,
                )
            live_candles = live_candles[-max(lookback_bars, 1):]
        else:
            candle_messages = self._select_trade_active_continuous_messages(recent_messages)
            live_candles = self._build_candles(display_timeframe, candle_messages)[-max(lookback_bars, 1):]

        event_annotations = self._build_event_annotations(recent_messages) if recent_messages else []
        focus_regions = self._build_focus_regions(recent_messages, event_annotations) if recent_messages else []

        LOGGER.debug(
            "get_live_tail: symbol=%s timeframe=%s history_source=%s preaggregated=%s overlay=%s recent_messages=%s latest_observed_at=%s",
            symbol,
            display_timeframe.value,
            history_source_kind,
            len(preaggregated_candles),
            continuous_overlay_count,
            len(recent_messages),
            latest_observed_at.isoformat() if latest_observed_at is not None else None,
        )

        # Auto gap-fill: patch holes in live candles using history-bars.
        live_candles = self._patch_live_candle_gaps(
            instrument_symbol=symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=chart_instance_id,
            candles=live_candles,
        )

        # Still expose remaining gaps as explicit synthetic bars (so UI can see missing time).
        live_candles, candle_gaps, _ = self._fill_candle_time_gaps(live_candles, display_timeframe)

        cache_key = None
        if live_candles:
            cache_key = "|".join([
                instrument_symbol,
                str(display_timeframe),
                live_candles[0].started_at.isoformat().replace("+00:00", "Z"),
                live_candles[-1].ended_at.isoformat().replace("+00:00", "Z"),
            ])
        latest_backfill_request = self._find_relevant_live_tail_backfill_request(
            cache_key=cache_key,
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=chart_instance_id,
            window_start=live_candles[0].started_at if live_candles else None,
            window_end=live_candles[-1].ended_at if live_candles else None,
        )
        integrity = self._build_integrity(
            window_start=live_candles[0].started_at if live_candles else (latest_observed_at or now_utc) - timedelta(days=7),
            window_end=live_candles[-1].ended_at if live_candles else (latest_observed_at or now_utc),
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        snapshot_refresh_required = bool(
            latest_backfill_request is not None
            and latest_backfill_request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED
            and integrity.status == "complete"
        )

        if latest_payload is not None:
            price_state = latest_payload.get("price_state", {})
            latest_price = price_state.get("last_price")
            best_bid = price_state.get("best_bid")
            best_ask = price_state.get("best_ask")
            latest_price = self._to_float_or_none(latest_price)
            best_bid = self._to_float_or_none(best_bid)
            best_ask = self._to_float_or_none(best_ask)
            latest_price_source = "continuous_state" if latest_price is not None else None
            best_bid_source = "continuous_state" if best_bid is not None else None
            best_ask_source = "continuous_state" if best_ask is not None else None

            if latest_price is None and tick_latest_price is not None:
                latest_price = tick_latest_price
                latest_price_source = "ticks_raw"
            if latest_price is None and live_candles:
                latest_price = live_candles[-1].close
                latest_price_source = "candle_close"
            if best_bid is None and tick_best_bid is not None:
                best_bid = tick_best_bid
                best_bid_source = "ticks_raw"
            if best_ask is None and tick_best_ask is not None:
                best_ask = tick_best_ask
                best_ask_source = "ticks_raw"

            trade_summary = payload_to_model(latest_payload.get("trade_summary"), AdapterTradeSummary)
            significant_liquidity = [
                model
                for model in (
                    payload_to_model(item, AdapterSignificantLiquidityLevel)
                    for item in latest_payload.get("significant_liquidity", [])
                )
                if model is not None
            ]
            same_price_replenishment = [
                model
                for model in (
                    payload_to_model(item, AdapterSamePriceReplenishmentState)
                    for item in latest_payload.get("same_price_replenishment", [])
                )
                if model is not None
            ]
            active_initiative_drive = payload_to_model(
                latest_payload.get("active_initiative_drive"),
                AdapterInitiativeDriveState,
            )
            active_post_harvest_response = payload_to_model(
                latest_payload.get("active_post_harvest_response"),
                AdapterPostHarvestResponseState,
            )
        else:
            latest_price = tick_latest_price
            latest_price_source = "ticks_raw" if latest_price is not None else None
            if latest_price is None:
                latest_price = live_candles[-1].close if live_candles else None
                latest_price_source = "candle_close" if latest_price is not None else None
            best_bid = tick_best_bid
            best_ask = tick_best_ask
            best_bid_source = "ticks_raw" if best_bid is not None else None
            best_ask_source = "ticks_raw" if best_ask is not None else None
            trade_summary = None
            significant_liquidity = []
            same_price_replenishment = []
            active_initiative_drive = None
            active_post_harvest_response = None

        return ReplayWorkbenchLiveTailResponse(
            schema_version=self._LIVE_TAIL_SCHEMA_VERSION,
            profile_version=profile_version,
            engine_version=engine_version,
            data_status=self._build_data_status(
                latest_adapter_sync_at=latest_observed_at,
                integrity=integrity,
                ai_available=self._replay_ai_chat_service is not None,
            ),
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            latest_observed_at=latest_observed_at,
            latest_price=latest_price,
            best_bid=best_bid,
            best_ask=best_ask,
            latest_price_source=latest_price_source,
            best_bid_source=best_bid_source,
            best_ask_source=best_ask_source,
            source_message_count=len(recent_messages),
            candles=live_candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            trade_summary=trade_summary,
            significant_liquidity=significant_liquidity,
            same_price_replenishment=same_price_replenishment,
            active_initiative_drive=active_initiative_drive,
            active_post_harvest_response=active_post_harvest_response,
            integrity=integrity,
            snapshot_refresh_required=snapshot_refresh_required,
            latest_backfill_request=latest_backfill_request,
        )

    def _load_live_tail_raw_mirror_candles(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None,
        window_start: datetime,
        window_end: datetime,
        limit: int,
    ) -> list[ReplayChartBar]:
        normalized_symbol = self._normalize_symbol_for_storage(instrument_symbol)
        if chart_instance_id is None or normalized_symbol is None:
            return []
        try:
            raw_rows = self._repository.list_atas_chart_bars_raw(
                chart_instance_id=chart_instance_id,
                timeframe=display_timeframe.value,
                window_start=window_start,
                window_end=window_end,
                limit=limit,
            )
        except Exception:
            LOGGER.exception(
                "get_live_tail: raw mirror query failed symbol=%s chart_instance_id=%s timeframe=%s",
                instrument_symbol,
                chart_instance_id,
                display_timeframe.value,
            )
            return []

        candles: list[ReplayChartBar] = []
        for row in raw_rows:
            row_symbols = {
                self._normalize_symbol_for_storage(row.symbol),
                self._normalize_symbol_for_storage(row.contract_symbol),
                self._normalize_symbol_for_storage(row.root_symbol),
            }
            row_symbols.discard(None)
            if normalized_symbol not in row_symbols:
                continue
            candles.append(
                ReplayChartBar(
                    started_at=row.started_at_utc,
                    ended_at=row.ended_at_utc,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    delta=row.delta,
                    bid_volume=row.bid_volume,
                    ask_volume=row.ask_volume,
                    source_kind="atas_chart_bars_raw",
                    is_synthetic=False,
                    bar_timestamp_utc=row.started_at_utc,
                    original_bar_time_text=row.original_bar_time_text,
                )
            )

        candles.sort(key=lambda item: item.started_at)
        if candles:
            LOGGER.info(
                "get_live_tail: using raw mirror history symbol=%s chart_instance_id=%s timeframe=%s candles=%s",
                instrument_symbol,
                chart_instance_id,
                display_timeframe.value,
                len(candles),
            )
        return candles

    def rebuild_cache_from_latest_sync(
        self,
        request: ReplayWorkbenchRebuildLatestRequest,
    ) -> ReplayWorkbenchRebuildLatestResponse:
        cache = self.get_cache_record(request.cache_key)
        invalidation_result: ReplayWorkbenchInvalidationResponse | None = None
        invalidated_existing_cache = False
        if cache.record is not None and cache.record.verification_state.status != ReplayVerificationStatus.INVALIDATED:
            invalidation_result = self.invalidate_cache_record(
                ReplayWorkbenchInvalidationRequest(
                    cache_key=request.cache_key,
                    invalidation_reason=request.invalidation_reason,
                )
            )
            invalidated_existing_cache = True

        build_result = self.build_replay_snapshot(
            ReplayWorkbenchBuildRequest(
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                force_rebuild=True,
                min_continuous_messages=request.min_continuous_messages,
            )
        )
        return ReplayWorkbenchRebuildLatestResponse(
            cache_key=request.cache_key,
            invalidated_existing_cache=invalidated_existing_cache,
            invalidation_result=invalidation_result,
            build_result=build_result,
        )

    def request_atas_backfill(
        self,
        request: ReplayWorkbenchAtasBackfillRequest,
    ) -> ReplayWorkbenchAtasBackfillAcceptedResponse:
        now = datetime.now(tz=UTC)
        normalized_request = request.model_copy(
            update={
                "window_start": self._ensure_utc(request.window_start),
                "window_end": self._ensure_utc(request.window_end),
                "target_contract_symbol": request.target_contract_symbol or request.contract_symbol,
                "target_root_symbol": request.target_root_symbol or request.root_symbol,
                "requested_ranges": self._build_requested_backfill_ranges(
                    display_timeframe=request.display_timeframe,
                    window_start=request.window_start,
                    window_end=request.window_end,
                    missing_segments=request.missing_segments,
                    requested_ranges=request.requested_ranges,
                ),
            }
        )
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            reusable = self._find_reusable_backfill_request_locked(normalized_request, now)
            if reusable is not None:
                LOGGER.info(
                    "request_atas_backfill: reused request_id=%s instrument_symbol=%s chart_instance_id=%s replace_existing_history=%s",
                    reusable.request_id,
                    reusable.instrument_symbol,
                    reusable.chart_instance_id,
                    reusable.replace_existing_history,
                )
                return ReplayWorkbenchAtasBackfillAcceptedResponse(
                    request=reusable,
                    reused_existing_request=True,
                )

            if normalized_request.replace_existing_history and normalized_request.request_history_bars:
                self._replace_existing_history_window(normalized_request)

            record = ReplayWorkbenchAtasBackfillRecord(
                request_id=f"atas-backfill-{uuid4().hex}",
                cache_key=normalized_request.cache_key,
                instrument_symbol=normalized_request.instrument_symbol,
                contract_symbol=normalized_request.contract_symbol,
                root_symbol=normalized_request.root_symbol,
                target_contract_symbol=normalized_request.target_contract_symbol,
                target_root_symbol=normalized_request.target_root_symbol,
                display_timeframe=normalized_request.display_timeframe,
                window_start=normalized_request.window_start,
                window_end=normalized_request.window_end,
                chart_instance_id=normalized_request.chart_instance_id,
                missing_segments=normalized_request.missing_segments,
                requested_ranges=normalized_request.requested_ranges,
                reason=normalized_request.reason,
                request_history_bars=normalized_request.request_history_bars,
                request_history_footprint=normalized_request.request_history_footprint,
                replace_existing_history=normalized_request.replace_existing_history,
                status=ReplayWorkbenchAtasBackfillStatus.PENDING,
                requested_at=now,
                expires_at=now + self._BACKFILL_REQUEST_TTL,
                dispatch_count=0,
            )
            self._backfill_requests[record.request_id] = record
            self._prune_backfill_requests_locked(now)
            LOGGER.info(
                "request_atas_backfill: created request_id=%s instrument_symbol=%s contract_symbol=%s root_symbol=%s chart_instance_id=%s ranges=%s replace_existing_history=%s",
                record.request_id,
                record.instrument_symbol,
                record.contract_symbol,
                record.root_symbol,
                record.chart_instance_id,
                len(record.requested_ranges),
                record.replace_existing_history,
            )
            return ReplayWorkbenchAtasBackfillAcceptedResponse(
                request=record,
                reused_existing_request=False,
            )

    def poll_atas_backfill(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
    ) -> AdapterBackfillDispatchResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            for record in self._iter_matching_backfill_requests_locked(
                instrument_symbol=instrument_symbol,
                chart_instance_id=chart_instance_id,
                contract_symbol=contract_symbol,
                root_symbol=root_symbol,
            ):
                if not self._is_backfill_dispatchable(record, now):
                    continue
                updated = record.model_copy(
                    update={
                        "status": ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
                        "dispatch_count": record.dispatch_count + 1,
                        "dispatched_at": now,
                        "dispatched_chart_instance_id": chart_instance_id,
                    }
                )
                self._backfill_requests[record.request_id] = updated
                LOGGER.info(
                    "poll_atas_backfill: dispatched request_id=%s instrument_symbol=%s chart_instance_id=%s contract_symbol=%s root_symbol=%s",
                    updated.request_id,
                    updated.instrument_symbol,
                    chart_instance_id,
                    updated.contract_symbol,
                    updated.root_symbol,
                )
                return AdapterBackfillDispatchResponse(
                    instrument_symbol=instrument_symbol,
                    chart_instance_id=chart_instance_id,
                    polled_at=now,
                    request=self._build_backfill_command(updated),
                )

        return AdapterBackfillDispatchResponse(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            polled_at=now,
            request=None,
        )

    def acknowledge_atas_backfill(
        self,
        request: AdapterBackfillAcknowledgeRequest,
    ) -> AdapterBackfillAcknowledgeResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            record = self._backfill_requests.get(request.request_id)
            if record is None:
                raise ReplayWorkbenchNotFoundError(
                    f"ATAS backfill request '{request.request_id}' not found."
                )
            if request.cache_key is not None and request.cache_key != record.cache_key:
                raise ReplayWorkbenchNotFoundError(
                    f"ATAS backfill request '{request.request_id}' cache_key mismatch."
                )

            updated = record.model_copy(
                update={
                    "status": ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED,
                    "acknowledged_at": request.acknowledged_at,
                    "acknowledged_chart_instance_id": request.chart_instance_id,
                    "acknowledged_history_bars": request.acknowledged_history_bars,
                    "acknowledged_history_footprint": request.acknowledged_history_footprint,
                    "latest_loaded_bar_started_at": request.latest_loaded_bar_started_at,
                    "note": request.note,
                }
            )
            self._backfill_requests[request.request_id] = updated
            self._prune_backfill_requests_locked(now)
        LOGGER.info(
            "acknowledge_atas_backfill: request_id=%s cache_key=%s history_bars=%s history_footprint=%s latest_loaded_bar_started_at=%s",
            request.request_id,
            request.cache_key or updated.cache_key,
            request.acknowledged_history_bars,
            request.acknowledged_history_footprint,
            request.latest_loaded_bar_started_at.isoformat() if request.latest_loaded_bar_started_at else None,
        )

        verification = self._verify_acknowledged_backfill(updated)
        rebuild_result = ReplayWorkbenchAckRebuildResult(triggered=False, build_result=None)
        if verification.verified:
            rebuild_result = ReplayWorkbenchAckRebuildResult(
                triggered=True,
                build_result=self.build_replay_snapshot(
                    ReplayWorkbenchBuildRequest(
                        cache_key=updated.cache_key,
                        instrument_symbol=updated.instrument_symbol,
                        display_timeframe=updated.display_timeframe,
                        window_start=updated.window_start,
                        window_end=updated.window_end,
                        chart_instance_id=updated.chart_instance_id,
                        force_rebuild=True,
                        min_continuous_messages=1,
                    )
                ),
            )

        return AdapterBackfillAcknowledgeResponse(
            request=updated,
            verification=verification,
            rebuild_result=rebuild_result,
        )

    def get_atas_backfill_progress(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        cache_key: str | None = None,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ReplayWorkbenchBackfillProgressResponse:
        normalized_instrument_symbol = (
            self._normalize_symbol_for_storage(instrument_symbol)
            or instrument_symbol.strip().upper()
            or "UNKNOWN"
        )
        normalized_chart_instance_id = str(chart_instance_id or "").strip() or None
        normalized_contract_symbol = self._normalize_symbol_for_storage(contract_symbol)
        normalized_root_symbol = self._normalize_symbol_for_storage(root_symbol)
        normalized_window_start = self._ensure_utc(window_start) if window_start is not None else None
        normalized_window_end = self._ensure_utc(window_end) if window_end is not None else None

        request = self._find_matching_backfill_progress_request(
            cache_key=cache_key,
            instrument_symbol=normalized_instrument_symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=normalized_chart_instance_id,
            contract_symbol=normalized_contract_symbol,
            root_symbol=normalized_root_symbol,
            window_start=normalized_window_start,
            window_end=normalized_window_end,
        )
        if request is None:
            return ReplayWorkbenchBackfillProgressResponse(
                schema_version=self._BACKFILL_PROGRESS_SCHEMA_VERSION,
                instrument_symbol=normalized_instrument_symbol,
                display_timeframe=display_timeframe,
                cache_key=cache_key,
                chart_instance_id=normalized_chart_instance_id,
                contract_symbol=normalized_contract_symbol,
                root_symbol=normalized_root_symbol,
                window_start=normalized_window_start,
                window_end=normalized_window_end,
                active=False,
                stage="idle",
                status="idle",
                progress_percent=0,
                coverage_progress_percent=0,
                estimated=True,
                label="当前窗口没有 ATAS 传输任务",
                detail="后端当前没有匹配的 history-bars/backfill 任务。",
                expected_bar_count=0,
                received_bar_count=0,
                missing_bar_count=0,
                coverage_window_start=None,
                coverage_window_end=None,
                footprint_requested=False,
                footprint_acknowledged=False,
                verification=None,
                request=None,
                requested_ranges=[],
            )

        coverage_chart_instance_id = str(request.chart_instance_id or normalized_chart_instance_id or "").strip() or None
        coverage_contract_symbol = self._normalize_symbol_for_storage(
            request.target_contract_symbol or request.contract_symbol or normalized_contract_symbol
        )
        coverage_root_symbol = None
        if coverage_contract_symbol is None:
            coverage_root_symbol = self._normalize_symbol_for_storage(
                request.target_root_symbol or request.root_symbol or normalized_root_symbol or request.instrument_symbol
            )

        progress_ranges: list[ReplayWorkbenchBackfillProgressRange] = []
        total_expected_bar_count = 0
        total_received_bar_count = 0
        coverage_window_start_result: datetime | None = None
        coverage_window_end_result: datetime | None = None
        requested_ranges = request.requested_ranges or [
            ReplayWorkbenchBackfillRange(
                range_start=request.window_start,
                range_end=request.window_end,
            )
        ]
        for requested_range in requested_ranges:
            expected_bar_count = (
                self._expected_native_bar_count(
                    display_timeframe,
                    requested_range.range_start,
                    requested_range.range_end,
                )
                if request.request_history_bars
                else 0
            )
            received_bar_count = (
                self._repository.count_atas_chart_bars_raw(
                    chart_instance_id=coverage_chart_instance_id,
                    contract_symbol=coverage_contract_symbol,
                    root_symbol=coverage_root_symbol,
                    timeframe=display_timeframe.value,
                    window_start=requested_range.range_start,
                    window_end=requested_range.range_end,
                )
                if request.request_history_bars
                else 0
            )
            range_first_started_at, range_last_started_at, _ = self._repository.get_atas_chart_bars_raw_coverage(
                chart_instance_id=coverage_chart_instance_id,
                contract_symbol=coverage_contract_symbol,
                root_symbol=coverage_root_symbol,
                timeframe=display_timeframe.value,
                window_start=requested_range.range_start,
                window_end=requested_range.range_end,
            )
            if range_first_started_at is not None and (
                coverage_window_start_result is None or range_first_started_at < coverage_window_start_result
            ):
                coverage_window_start_result = range_first_started_at
            if range_last_started_at is not None and (
                coverage_window_end_result is None or range_last_started_at > coverage_window_end_result
            ):
                coverage_window_end_result = range_last_started_at

            total_expected_bar_count += expected_bar_count
            total_received_bar_count += received_bar_count
            missing_bar_count = max(expected_bar_count - received_bar_count, 0)
            progress_percent = (
                100
                if expected_bar_count <= 0
                else max(0, min(100, round((received_bar_count / max(expected_bar_count, 1)) * 100)))
            )
            progress_ranges.append(
                ReplayWorkbenchBackfillProgressRange(
                    range_start=requested_range.range_start,
                    range_end=requested_range.range_end,
                    expected_bar_count=expected_bar_count,
                    received_bar_count=received_bar_count,
                    missing_bar_count=missing_bar_count,
                    progress_percent=progress_percent,
                    first_received_started_at=range_first_started_at,
                    last_received_started_at=range_last_started_at,
                )
            )

        total_missing_bar_count = max(total_expected_bar_count - total_received_bar_count, 0)
        coverage_progress_percent = (
            100
            if total_expected_bar_count <= 0
            else max(0, min(100, round((total_received_bar_count / max(total_expected_bar_count, 1)) * 100)))
        )
        verification: ReplayWorkbenchAckVerification | None = None
        if request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED:
            verification = self._verify_acknowledged_backfill(request)

        stage, active, label, detail = self._describe_backfill_progress(
            request=request,
            received_bar_count=total_received_bar_count,
            expected_bar_count=total_expected_bar_count,
            missing_bar_count=total_missing_bar_count,
            coverage_progress_percent=coverage_progress_percent,
            verification=verification,
        )
        progress_percent = coverage_progress_percent
        if request.request_history_footprint and not request.acknowledged_history_footprint:
            progress_percent = min(progress_percent, 95)
        if request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED and not (verification is not None and verification.verified):
            progress_percent = min(progress_percent, 98)
        if verification is not None and verification.verified:
            progress_percent = 100

        return ReplayWorkbenchBackfillProgressResponse(
            schema_version=self._BACKFILL_PROGRESS_SCHEMA_VERSION,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
            cache_key=request.cache_key,
            chart_instance_id=coverage_chart_instance_id,
            contract_symbol=coverage_contract_symbol,
            root_symbol=coverage_root_symbol or self._normalize_symbol_for_storage(request.root_symbol),
            window_start=request.window_start,
            window_end=request.window_end,
            active=active,
            stage=stage,
            status=request.status.value,
            progress_percent=progress_percent,
            coverage_progress_percent=coverage_progress_percent,
            estimated=not (verification is not None and verification.verified),
            label=label,
            detail=detail,
            expected_bar_count=total_expected_bar_count,
            received_bar_count=total_received_bar_count,
            missing_bar_count=total_missing_bar_count,
            coverage_window_start=coverage_window_start_result,
            coverage_window_end=coverage_window_end_result,
            footprint_requested=request.request_history_footprint,
            footprint_acknowledged=request.acknowledged_history_footprint,
            verification=verification,
            request=request,
            requested_ranges=progress_ranges,
        )

    def get_mirror_bars(
        self,
        *,
        chart_instance_id: str | None,
        contract_symbol: str,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        limit: int = 5000,
    ) -> list[ReplayChartBar]:
        """Query raw contract bars without continuous/roll adjustments.

        Mirror bars return the exact contract data as stored, useful when
        you need to see the true contract prices without any roll logic.

        Args:
            chart_instance_id: Optional ATAS chart-instance filter.
            contract_symbol: The contract symbol to query (e.g. "NQH6").
            timeframe: Target timeframe for the bars.
            window_start: Inclusive query window start.
            window_end: Inclusive query window end.
            limit: Maximum bars to return.

        Returns:
            List of ReplayChartBar representing raw contract data.
        """
        raw_rows = self._repository.list_atas_chart_bars_raw(
            chart_instance_id=chart_instance_id,
            contract_symbol=contract_symbol,
            timeframe=timeframe.value,
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )
        bars: list[ReplayChartBar] = []
        for row in raw_rows:
            bars.append(
                ReplayChartBar(
                    started_at=row.started_at_utc,
                    ended_at=row.ended_at_utc,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    delta=row.delta,
                    bid_volume=row.bid_volume,
                    ask_volume=row.ask_volume,
                    source_kind="atas_chart_bars_raw",
                    is_synthetic=False,
                    bar_timestamp_utc=row.started_at_utc,
                    original_bar_time_text=row.original_bar_time_text,
                )
            )
        bars.sort(key=lambda b: b.started_at)
        LOGGER.info(
            "get_mirror_bars: chart_instance_id=%s contract_symbol=%s timeframe=%s count=%s",
            chart_instance_id,
            contract_symbol,
            timeframe.value,
            len(bars),
        )
        return bars[:limit]

    def get_continuous_bars(
        self,
        *,
        root_symbol: str,
        timeframe: Timeframe,
        roll_mode: RollMode,
        window_start: datetime,
        window_end: datetime,
        limit: int = 5000,
        adjustment_mode: ContinuousAdjustmentMode = ContinuousAdjustmentMode.NONE,
        manual_sequence: list[str] | None = None,
    ) -> list[ReplayChartBar]:
        """Compatibility helper that projects the continuous layer into ReplayChartBar."""
        envelope = self._continuous_contract_service.query_continuous_bars(
            root_symbol=root_symbol,
            timeframe=timeframe,
            roll_mode=roll_mode,
            window_start=window_start,
            window_end=window_end,
            limit=limit,
            adjustment_mode=adjustment_mode,
            manual_sequence=manual_sequence,
        )
        bars: list[ReplayChartBar] = []
        for candle in envelope.candles:
            bars.append(
                ReplayChartBar(
                    started_at=candle.started_at_utc,
                    ended_at=candle.ended_at_utc,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    delta=candle.delta,
                    bid_volume=candle.bid_volume,
                    ask_volume=candle.ask_volume,
                    source_kind="continuous_derived",
                    is_synthetic=False,
                    bar_timestamp_utc=candle.started_at_utc,
                )
            )
        LOGGER.info(
            "get_continuous_bars: root_symbol=%s timeframe=%s roll_mode=%s adjustment_mode=%s count=%s warnings=%s",
            root_symbol,
            timeframe.value,
            envelope.roll_mode.value,
            adjustment_mode.value,
            len(bars),
            len(envelope.warnings),
        )
        return bars[:limit]

    def _verify_acknowledged_backfill(
        self,
        request: ReplayWorkbenchAtasBackfillRecord,
    ) -> ReplayWorkbenchAckVerification:
        build_request = ReplayWorkbenchBuildRequest(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
            window_start=request.window_start,
            window_end=request.window_end,
            chart_instance_id=request.chart_instance_id,
            force_rebuild=False,
            min_continuous_messages=1,
        )
        history_payloads = self._collect_matching_history_payloads(build_request)
        footprint_payloads = self._find_matching_history_footprint_payloads(build_request)
        if not history_payloads:
            return ReplayWorkbenchAckVerification(
                verified=False,
                bars_verified=False,
                footprint_available=bool(footprint_payloads),
                requested_window_start=request.window_start,
                requested_window_end=request.window_end,
                covered_window_start=None,
                covered_window_end=None,
                missing_segment_count=len(request.missing_segments),
                note="history bars not found after ack",
            )

        candles = self._build_candles_from_history_payloads(history_payloads, build_request)
        filtered = [
            candle for candle in candles
            if candle.ended_at >= request.window_start and candle.started_at <= request.window_end
        ]
        covered_window_start = filtered[0].started_at if filtered else None
        covered_window_end = filtered[-1].ended_at if filtered else None

        remaining_segments: list[ReplayWorkbenchGapSegment] = []
        for segment in request.missing_segments:
            segment_has_coverage = self._gap_segment_is_fully_covered(
                candles=filtered,
                timeframe=request.display_timeframe,
                segment=segment,
            )
            if not segment_has_coverage:
                remaining_segments.append(segment)

        verified = bool(filtered) and not remaining_segments
        return ReplayWorkbenchAckVerification(
            verified=verified,
            bars_verified=bool(filtered),
            footprint_available=bool(footprint_payloads),
            requested_window_start=request.window_start,
            requested_window_end=request.window_end,
            covered_window_start=covered_window_start,
            covered_window_end=covered_window_end,
            missing_segment_count=len(remaining_segments),
            note=None if verified else "history coverage still incomplete after ack",
        )

    def build_replay_snapshot(self, request: ReplayWorkbenchBuildRequest) -> ReplayWorkbenchBuildResponse:
        cache = self.get_cache_record(request.cache_key)
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        history_payloads: list[AdapterHistoryBarsPayload] = []
        if not request.force_rebuild and cache.record is not None and cache.record.verification_state.status != ReplayVerificationStatus.INVALIDATED:
            cached_ingestion = self._repository.get_ingestion(cache.record.ingestion_id)
            if cached_ingestion is not None:
                payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
                integrity = payload.integrity or self._build_integrity(
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    candle_gaps=payload.raw_features.get("candle_gaps") or [],
                    latest_backfill_request=latest_backfill_request,
                )
                backfill_request = None
                if integrity.status != "complete":
                    backfill_request = self._maybe_request_backfill_for_integrity(
                        cache_key=request.cache_key,
                        instrument_symbol=request.instrument_symbol,
                        display_timeframe=request.display_timeframe,
                        window_start=request.window_start,
                        window_end=request.window_end,
                        chart_instance_id=request.chart_instance_id,
                        integrity=integrity,
                        reason="snapshot_gap_detected",
                    )
                    integrity = self._with_backfill_metadata(integrity, backfill_request)
                return ReplayWorkbenchBuildResponse(
                    schema_version=self._BUILD_RESPONSE_SCHEMA_VERSION,
                    profile_version=payload.profile_version,
                    engine_version=payload.engine_version,
                    data_status=payload.data_status,
                    action=ReplayWorkbenchBuildAction.CACHE_HIT,
                    cache_key=request.cache_key,
                    reason="Replay cache already exists and is still eligible for reuse.",
                    local_message_count=0,
                    replay_snapshot_id=payload.replay_snapshot_id,
                    ingestion_id=cache.record.ingestion_id,
                    core_snapshot=payload,
                    summary=self._build_summary(payload),
                    cache_record=cache.record,
                    atas_fetch_request=None,
                    atas_backfill_request=backfill_request,
                    integrity=integrity,
                )

        if not history_payloads:
            history_payloads = self._collect_matching_history_payloads(request)
        footprint_payloads = self._find_matching_history_footprint_payloads(request)

        continuous_messages = self._collect_matching_continuous_messages(request)
        trade_active_continuous_messages = self._select_trade_active_continuous_messages(continuous_messages)
        local_history_insufficient = (
            len(trade_active_continuous_messages) < request.min_continuous_messages
        )
        if history_payloads:
            payload = self._build_snapshot_from_history_bars(
                request,
                history_payloads,
                continuous_messages,
                footprint_payloads,
            )
            accepted = self.ingest_replay_snapshot(payload)
            cache_after = self.get_cache_record(request.cache_key)
            return ReplayWorkbenchBuildResponse(
                schema_version=self._BUILD_RESPONSE_SCHEMA_VERSION,
                profile_version=payload.profile_version,
                engine_version=payload.engine_version,
                data_status=payload.data_status,
                action=ReplayWorkbenchBuildAction.BUILT_FROM_ATAS_HISTORY,
                cache_key=request.cache_key,
                reason="Replay packet rebuilt from ATAS chart-loaded history bars.",
                local_message_count=len(continuous_messages),
                replay_snapshot_id=accepted.replay_snapshot_id,
                ingestion_id=accepted.ingestion_id,
                core_snapshot=payload,
                summary=accepted.summary,
                cache_record=cache_after.record,
                atas_fetch_request=None,
                atas_backfill_request=None,
                integrity=payload.integrity,
            )
        payload = self._build_snapshot_from_local_history(request, continuous_messages)
        if (
            local_history_insufficient
            and payload.integrity is not None
            and payload.integrity.status == "complete"
        ):
            payload = payload.model_copy(
                update={
                    "integrity": payload.integrity.model_copy(
                        update={"status": "missing_local_history"},
                    )
                }
            )
        accepted = self.ingest_replay_snapshot(payload)
        cache_after = self.get_cache_record(request.cache_key)
        backfill_request = None
        integrity = payload.integrity
        if integrity is not None and integrity.status != "complete":
            backfill_request = self._maybe_request_backfill_for_integrity(
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                integrity=integrity,
                reason="local_history_insufficient" if local_history_insufficient else "candle_gap_detected",
            )
            integrity = self._with_backfill_metadata(integrity, backfill_request)
        return ReplayWorkbenchBuildResponse(
            schema_version=self._BUILD_RESPONSE_SCHEMA_VERSION,
            profile_version=payload.profile_version,
            engine_version=payload.engine_version,
            data_status=payload.data_status,
            action=ReplayWorkbenchBuildAction.BUILT_FROM_LOCAL_HISTORY,
            cache_key=request.cache_key,
            reason=(
                "Local adapter history is missing for this replay window; returned a placeholder snapshot and queued backfill."
                if not trade_active_continuous_messages
                else "Replay packet rebuilt from locally stored adapter history."
            ),
            local_message_count=len(continuous_messages),
            replay_snapshot_id=accepted.replay_snapshot_id,
            ingestion_id=accepted.ingestion_id,
            core_snapshot=payload,
            summary=accepted.summary,
            cache_record=cache_after.record,
            atas_fetch_request=None,
            atas_backfill_request=backfill_request,
            integrity=integrity,
        )


    def _build_snapshot_from_history_bars(
        self,
        request: ReplayWorkbenchBuildRequest,
        history_payloads: list[AdapterHistoryBarsPayload],
        continuous_messages: list[StoredIngestion],
        footprint_payloads: list[AdapterHistoryFootprintPayload],
    ) -> ReplayWorkbenchSnapshotPayload:
        history_payload = history_payloads[0]
        created_at = datetime.now(tz=UTC)
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        candles = self._build_candles_from_history_payloads(history_payloads, request)
        if not candles:
            return self._build_snapshot_from_local_history(request, continuous_messages)
        history_candle_count = len(candles)
        continuous_overlay_count = 0
        if continuous_messages:
            candles, continuous_overlay_count = self._merge_history_candles_with_continuous_overlay(
                history_candles=candles,
                continuous_messages=continuous_messages,
                timeframe=request.display_timeframe,
            )

        # Detect + fill any remaining candle gaps so the UI does not silently compress missing time.
        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)
        candles, initial_window_applied, initial_window_bar_limit, total_candle_count = self._apply_initial_snapshot_window(
            candles,
            request.display_timeframe,
        )

        actual_window_start = candles[0].started_at
        actual_window_end = candles[-1].ended_at
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        integrity = self._build_integrity(
            window_start=request.window_start,
            window_end=request.window_end,
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        event_annotations = self._build_event_annotations(continuous_messages) if continuous_messages else []
        focus_regions = self._build_focus_regions(continuous_messages, event_annotations) if continuous_messages else []
        if footprint_payloads:
            event_annotations.extend(self._build_footprint_event_annotations(footprint_payloads, history_payload.instrument.tick_size, request))
            focus_regions.extend(self._build_footprint_focus_regions(footprint_payloads, history_payload.instrument.tick_size, request))
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)
        footprint_digest = self._build_footprint_digest(footprint_payloads, request) if footprint_payloads else None
        history_coverage_start = min(payload.observed_window_start for payload in history_payloads)
        history_coverage_end = max(payload.observed_window_end for payload in history_payloads)
        latest_adapter_sync_at = history_coverage_end
        if continuous_messages:
            latest_adapter_sync_at = max(
                latest_adapter_sync_at,
                max(self._payload_observed_at(item.observed_payload) for item in continuous_messages),
            )
        profile_version, engine_version = self._resolve_active_versions(request.instrument_symbol)

        return ReplayWorkbenchSnapshotPayload(
            schema_version=self._SNAPSHOT_SCHEMA_VERSION,
            profile_version=profile_version,
            engine_version=engine_version,
            data_status=self._build_data_status(
                latest_adapter_sync_at=latest_adapter_sync_at,
                integrity=integrity,
                ai_available=self._replay_ai_chat_service is not None,
            ),
            replay_snapshot_id=replay_snapshot_id,
            cache_key=request.cache_key,
            acquisition_mode=ReplayAcquisitionMode.ATAS_FETCH,
            created_at=created_at,
            source=history_payload.source,
            instrument=history_payload.instrument,
            display_timeframe=request.display_timeframe,
            window_start=actual_window_start,
            window_end=actual_window_end,
            cache_policy=ReplayCachePolicy(),
            verification_state=ReplayVerificationState(
                status=ReplayVerificationStatus.UNVERIFIED,
                verification_count=0,
                last_verified_at=None,
                next_verification_due_at=created_at,
                invalidated_at=None,
                invalidation_reason=None,
                locked_until_manual_reset=False,
            ),
            integrity=integrity,
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": "adapter_history_bars",
                "history_message_id": history_payload.message_id,
                "history_bar_timeframe": history_payload.bar_timeframe,
                "history_bar_count": history_candle_count,
                "history_payload_count": len(history_payloads),
                "history_coverage_start": history_coverage_start,
                "history_coverage_end": history_coverage_end,
                "requested_window_start": request.window_start,
                "requested_window_end": request.window_end,
                "actual_window_start": actual_window_start,
                "actual_window_end": actual_window_end,
                "history_footprint_available": bool(footprint_payloads),
                "history_footprint_digest": footprint_digest,
                "local_message_count": len(continuous_messages),
                "continuous_overlay_candle_count": continuous_overlay_count,
                "candle_gap_count": len(candle_gaps),
                "candle_gap_missing_bar_count": sum(item["missing_bar_count"] for item in candle_gaps),
                "candle_gap_fill_bar_count": gap_fill_bar_count,
                "candle_gaps": candle_gaps,
                "build_reason": "atas_chart_loaded_history_rebuild",
                "initial_window_applied": initial_window_applied,
                "initial_window_bar_limit": initial_window_bar_limit,
                "total_candle_count": total_candle_count,
                "deferred_history_available": total_candle_count > len(candles),
            },
        )

    def _get_latest_ingestion_status(
        self,
        *,
        now: datetime,
        ingestion_kind: str,
        instrument_symbol: str,
    ) -> ReplayWorkbenchLiveSourceStatus:
        latest = self._repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            limit=1,
        )
        if not latest:
            return ReplayWorkbenchLiveSourceStatus(
                ingestion_kind=ingestion_kind,
                latest_ingestion_id=None,
                latest_stored_at=None,
                lag_seconds=None,
            )

        latest_item = latest[0]
        return ReplayWorkbenchLiveSourceStatus(
            ingestion_kind=ingestion_kind,
            latest_ingestion_id=latest_item.ingestion_id,
            latest_stored_at=latest_item.stored_at,
            lag_seconds=max(0, int((now - latest_item.stored_at).total_seconds())),
        )

    def record_operator_entry(self, request: ReplayOperatorEntryRequest) -> ReplayOperatorEntryAcceptedResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        stored_at = datetime.now(tz=UTC)
        entry = ReplayOperatorEntryRecord(
            entry_id=f"entry-{uuid4().hex}",
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            chart_instance_id=replay_payload.source.chart_instance_id,
            executed_at=request.executed_at,
            side=request.side,
            entry_price=request.entry_price,
            quantity=request.quantity,
            stop_price=request.stop_price,
            target_price=request.target_price,
            timeframe_context=request.timeframe_context,
            thesis=request.thesis,
            context_notes=request.context_notes,
            tags=request.tags,
            stored_at=stored_at,
        )
        self._repository.save_ingestion(
            ingestion_id=f"ing-{uuid4().hex}",
            ingestion_kind="replay_operator_entry",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=entry.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayOperatorEntryAcceptedResponse(entry=entry)

    def list_operator_entries(self, replay_ingestion_id: str) -> ReplayOperatorEntryEnvelope:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        entries = [
            ReplayOperatorEntryRecord.model_validate(stored.observed_payload)
            for stored in self._repository.list_ingestions(
                ingestion_kind="replay_operator_entry",
                source_snapshot_id=replay_ingestion.source_snapshot_id,
                limit=1000,
            )
            if stored.observed_payload.get("replay_ingestion_id") == replay_ingestion_id
        ]
        entries.sort(key=lambda item: item.executed_at)
        return ReplayOperatorEntryEnvelope(
            replay_ingestion_id=replay_ingestion_id,
            entries=entries,
        )

    def record_manual_region(
        self,
        request: ReplayManualRegionAnnotationRequest,
    ) -> ReplayManualRegionAnnotationAcceptedResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        stored_at = datetime.now(tz=UTC)
        region = ReplayManualRegionAnnotationRecord(
            region_annotation_id=f"region-{uuid4().hex}",
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            label=request.label,
            thesis=request.thesis,
            price_low=request.price_low,
            price_high=request.price_high,
            started_at=request.started_at,
            ended_at=request.ended_at,
            side_bias=request.side_bias,
            notes=request.notes,
            tags=request.tags,
            stored_at=stored_at,
        )
        self._repository.save_ingestion(
            ingestion_id=f"ing-{uuid4().hex}",
            ingestion_kind="replay_manual_region",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=region.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return ReplayManualRegionAnnotationAcceptedResponse(region=region)

    def list_manual_regions(self, replay_ingestion_id: str) -> ReplayManualRegionAnnotationEnvelope:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        regions = [
            ReplayManualRegionAnnotationRecord.model_validate(stored.observed_payload)
            for stored in self._repository.list_ingestions(
                ingestion_kind="replay_manual_region",
                source_snapshot_id=replay_ingestion.source_snapshot_id,
                limit=1000,
            )
            if stored.observed_payload.get("replay_ingestion_id") == replay_ingestion_id
        ]
        regions.sort(key=lambda item: (item.started_at, item.price_low))
        return ReplayManualRegionAnnotationEnvelope(
            replay_ingestion_id=replay_ingestion_id,
            regions=regions,
        )

    def get_footprint_bar_detail(
        self,
        *,
        replay_ingestion_id: str,
        bar_started_at: datetime,
    ) -> ReplayFootprintBarDetail:
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayWorkbenchNotFoundError(f"Replay ingestion '{replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        matched_bar = self._find_history_footprint_bar(
            instrument_symbol=replay_payload.instrument.symbol,
            chart_instance_id=None,
            timeframe=replay_payload.display_timeframe,
            window_start=replay_payload.window_start,
            window_end=replay_payload.window_end,
            bar_started_at=bar_started_at,
        )
        if matched_bar is None:
            raise ReplayWorkbenchNotFoundError(
                f"No historical footprint detail found for {replay_payload.instrument.symbol} at {bar_started_at.isoformat()}."
            )

        return ReplayFootprintBarDetail(
            replay_ingestion_id=replay_ingestion_id,
            instrument_symbol=replay_payload.instrument.symbol,
            timeframe=replay_payload.display_timeframe,
            started_at=matched_bar.started_at,
            ended_at=matched_bar.ended_at,
            open=matched_bar.open,
            high=matched_bar.high,
            low=matched_bar.low,
            close=matched_bar.close,
            volume=matched_bar.volume,
            delta=matched_bar.delta,
            bid_volume=matched_bar.bid_volume,
            ask_volume=matched_bar.ask_volume,
            price_levels=[
                ReplayFootprintLevelDetail(
                    price=item.price,
                    bid_volume=item.bid_volume,
                    ask_volume=item.ask_volume,
                    total_volume=item.total_volume,
                    delta=item.delta,
                    trade_count=item.trade_count,
                )
                for item in sorted(matched_bar.price_levels, key=lambda level: level.price, reverse=True)
            ],
        )

    def _build_snapshot_from_local_history(
        self,
        request: ReplayWorkbenchBuildRequest,
        ingestions: list[StoredIngestion],
    ) -> ReplayWorkbenchSnapshotPayload:
        created_at = datetime.now(tz=UTC)
        first_payload = ingestions[0].observed_payload if ingestions else None
        last_payload = ingestions[-1].observed_payload if ingestions else None
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        trade_active_messages = self._select_trade_active_continuous_messages(ingestions)
        preaggregate_fallback_used = False

        # ─── Fast path: try pre-aggregated ClickHouse materialized view ───────
        # Queries return sub-100ms regardless of raw message count (109k+ rows).
        # Falls back to raw-message aggregation when MV is empty or unavailable.
        pre_bars = self._try_get_preaggregated_bars(
            symbol=request.instrument_symbol,
            timeframe=request.display_timeframe,
            window_start=request.window_start,
            window_end=request.window_end,
        )
        if pre_bars and self._preaggregated_bars_missing_coverage(
            pre_bars=pre_bars,
            trade_active_messages=trade_active_messages,
            timeframe=request.display_timeframe,
        ):
            pre_bars = []
            preaggregate_fallback_used = True
        if pre_bars:
            candles = [
                ReplayChartBar(
                    started_at=bar["started_at"],
                    ended_at=bar["ended_at"],
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    volume=bar["volume"],
                    delta=bar["delta"],
                    bid_volume=bar["bid_volume"],
                    ask_volume=bar["ask_volume"],
                )
                for bar in pre_bars
            ]
            # Rebuild event annotations from pre-aggregated events table
            pre_events = self._try_get_preaggregated_events(
                symbol=request.instrument_symbol,
                window_start=request.window_start,
                window_end=request.window_end,
            )
            event_annotations = self._build_event_annotations_from_preaggregated(pre_events) if pre_events else []
            focus_regions = self._build_focus_regions_from_preaggregated(pre_events) if pre_events else []
            history_source = "continuous_state_preaggregate"
        else:
            # ─── Slow path: aggregate from raw continuous_state messages ────────
            candle_ingestions = trade_active_messages
            candles = self._build_candles(request.display_timeframe, candle_ingestions)
            event_annotations = self._build_event_annotations(ingestions) if ingestions else []
            focus_regions = self._build_focus_regions(ingestions, event_annotations) if ingestions else []
            history_source = "adapter_continuous_state"

        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)
        candles, initial_window_applied, initial_window_bar_limit, total_candle_count = self._apply_initial_snapshot_window(
            candles,
            request.display_timeframe,
        )
        actual_window_start = candles[0].started_at if candles else request.window_start
        actual_window_end = candles[-1].ended_at if candles else request.window_end
        latest_backfill_request = self._find_latest_backfill_request(
            cache_key=request.cache_key,
            instrument_symbol=request.instrument_symbol,
            display_timeframe=request.display_timeframe,
        )
        integrity = self._build_integrity(
            window_start=request.window_start,
            window_end=request.window_end,
            candle_gaps=candle_gaps,
            latest_backfill_request=latest_backfill_request,
        )
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)
        source_payload = (
            last_payload["source"]
            if last_payload is not None
            else {
                "system": "ATAS",
                "instance_id": "local-service",
                "chart_instance_id": request.chart_instance_id,
                "adapter_version": "unknown",
            }
        )
        instrument_payload = (
            last_payload["instrument"]
            if last_payload is not None
            else {
                "symbol": request.instrument_symbol,
                "venue": "CME",
                "tick_size": 0.25,
                "currency": "USD",
            }
        )
        chart_instance_id = request.chart_instance_id
        if chart_instance_id is None and isinstance(source_payload, dict):
            chart_instance_id = source_payload.get("chart_instance_id")
        latest_adapter_sync_at = actual_window_end
        if last_payload is not None:
            latest_adapter_sync_at = self._payload_observed_at(last_payload)
        profile_version, engine_version = self._resolve_active_versions(request.instrument_symbol)

        return ReplayWorkbenchSnapshotPayload(
            schema_version=self._SNAPSHOT_SCHEMA_VERSION,
            profile_version=profile_version,
            engine_version=engine_version,
            data_status=self._build_data_status(
                latest_adapter_sync_at=latest_adapter_sync_at,
                integrity=integrity,
                ai_available=self._replay_ai_chat_service is not None,
            ),
            replay_snapshot_id=replay_snapshot_id,
            cache_key=request.cache_key,
            acquisition_mode=ReplayAcquisitionMode.CACHE_REUSE,
            created_at=created_at,
            source=source_payload,
            instrument=instrument_payload,
            display_timeframe=request.display_timeframe,
            window_start=actual_window_start,
            window_end=actual_window_end,
            cache_policy=ReplayCachePolicy(),
            verification_state=ReplayVerificationState(
                status=ReplayVerificationStatus.UNVERIFIED,
                verification_count=0,
                last_verified_at=None,
                next_verification_due_at=created_at,
                invalidated_at=None,
                invalidation_reason=None,
                locked_until_manual_reset=False,
            ),
            integrity=integrity,
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": history_source,
                "local_message_count": len(ingestions),
                "chart_instance_id": chart_instance_id,
                "build_reason": "cache_miss_local_history_rebuild",
                "first_message_id": first_payload["message_id"] if first_payload is not None else None,
                "last_message_id": last_payload["message_id"] if last_payload is not None else None,
                "requested_window_start": request.window_start,
                "requested_window_end": request.window_end,
                "actual_window_start": actual_window_start,
                "actual_window_end": actual_window_end,
                "candle_gap_count": len(candle_gaps),
                "candle_gap_missing_bar_count": sum(item["missing_bar_count"] for item in candle_gaps),
                "candle_gap_fill_bar_count": gap_fill_bar_count,
                "candle_gaps": candle_gaps,
                "initial_window_applied": initial_window_applied,
                "initial_window_bar_limit": initial_window_bar_limit,
                "total_candle_count": total_candle_count,
                "deferred_history_available": total_candle_count > len(candles),
                "preaggregate_fallback_used": preaggregate_fallback_used,
            },
        )

    def _try_get_preaggregated_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated bars from the chart_candles table.

        The chart_candles table (in ClickHouse or SQLite) is populated by
        ChartCandleService during ingestion, so queries are sub-100ms regardless
        of the raw message volume.

        Falls back to raw-message aggregation when no chart candles exist.
        """
        try:
            # First check: do we have any chart candles for this symbol/timeframe?
            count = self._repository.count_chart_candles(symbol.upper(), timeframe.value)
            if count == 0:
                return []

            # Query pre-aggregated chart candles from chart_candles table.
            # Both SQLite and ClickHouse repositories support this method.
            candles = self._repository.list_chart_candles(
                symbol=symbol.upper(),
                timeframe=timeframe.value,
                window_start=window_start,
                window_end=window_end,
                limit=limit,
            )

            if not candles:
                return []

            # Convert ChartCandle model objects to the dict format expected
            # by _build_snapshot_from_local_history.
            return [
                {
                    "started_at": bar.started_at,
                    "ended_at": bar.ended_at,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "delta": bar.delta,
                    "bid_volume": None,
                    "ask_volume": None,
                }
                for bar in candles
            ]
        except Exception:
            return []

    def _preaggregated_bars_missing_coverage(
        self,
        *,
        pre_bars: list[dict[str, Any]],
        trade_active_messages: list[StoredIngestion],
        timeframe: Timeframe,
    ) -> bool:
        if not pre_bars or not trade_active_messages:
            return False
        timeframe_minutes = max(1, self._TIMEFRAME_MINUTES.get(timeframe, 1))
        tolerance = timedelta(minutes=timeframe_minutes * 2)
        first_pre_started_at = self._ensure_utc(pre_bars[0]["started_at"])
        last_pre_started_at = self._ensure_utc(pre_bars[-1]["started_at"])
        activity_bucket_starts = [
            self._bucket_start(self._payload_observed_at(item.observed_payload), timeframe)
            for item in trade_active_messages
        ]
        if not activity_bucket_starts:
            return False
        expected_first_started_at = min(activity_bucket_starts)
        expected_last_started_at = max(activity_bucket_starts)
        if first_pre_started_at > expected_first_started_at + tolerance:
            return True
        if last_pre_started_at + tolerance < expected_last_started_at:
            return True
        return False

    def _try_get_preaggregated_events(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated replenishment events from ClickHouse MV."""
        try:
            events = self._repository.list_continuous_state_events(
                symbol=symbol.upper(),
                window_start=window_start,
                window_end=window_end,
                limit=limit,
            )
            return events
        except Exception:
            return []

    def _build_event_annotations_from_preaggregated(
        self,
        pre_events: list[dict[str, Any]],
    ) -> list[ReplayEventAnnotation]:
        """Build ReplayEventAnnotation list from pre-aggregated events."""
        if not pre_events:
            return []
        events: dict[str, ReplayEventAnnotation] = {}
        for item in pre_events:
            event_id = f"replenish-{item['track_id']}"
            if event_id not in events:
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="same_price_replenishment",
                    source_kind="collector",
                    observed_at=item["observed_at"],
                    price=item["price"],
                    price_low=item["price"],
                    price_high=item["price"],
                    side=item.get("side", "unknown"),
                    confidence=min(1.0, 0.5 + (item.get("replenishment_count", 0) * 0.1)),
                    linked_ids=[item["track_id"]],
                    notes=[f"replenishment_count={item.get('replenishment_count', 0)}"],
                )
        return list(events.values())

    def _build_focus_regions_from_preaggregated(
        self,
        pre_events: list[dict[str, Any]],
    ) -> list[ReplayFocusRegion]:
        """Build ReplayFocusRegion list from pre-aggregated events."""
        if not pre_events:
            return []
        regions: dict[str, ReplayFocusRegion] = {}
        for item in pre_events:
            track_id = item["track_id"]
            if track_id not in regions:
                regions[track_id] = ReplayFocusRegion(
                    region_id=f"focus-{track_id}",
                    label=f"补充区域 {item['price']}",
                    started_at=item["observed_at"],
                    ended_at=item["observed_at"],
                    price_low=item["price"],
                    price_high=item["price"],
                    priority=min(10, 1 + int(item.get("replenishment_count", 0))),
                    reason_codes=["same_price_replenishment"],
                    linked_event_ids=[f"replenish-{track_id}"],
                    notes=[f"track_id={track_id}"],
                )
        return list(regions.values())

    def _collect_matching_continuous_messages(self, request: ReplayWorkbenchBuildRequest) -> list[StoredIngestion]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=request.instrument_symbol,
            limit=10000,
        )
        matched: list[StoredIngestion] = []
        for stored in candidates:
            payload = stored.observed_payload
            if not self._chart_instance_filter_matches_dict_payload(request.chart_instance_id, payload):
                continue
            window_start = parse_utc(payload["observed_window_start"])
            window_end = parse_utc(payload["observed_window_end"])
            # Normalize naive datetimes to UTC to ensure consistent comparison.
            if window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=UTC)
            if window_end.tzinfo is None:
                window_end = window_end.replace(tzinfo=UTC)
            if window_end < request.window_start or window_start > request.window_end:
                continue
            matched.append(stored)
        matched.sort(key=lambda item: item.observed_payload["emitted_at"])
        return matched

    def _apply_initial_snapshot_window(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], bool, int | None, int]:
        if not candles:
            return candles, False, None, 0
        total_candles = len(candles)
        bar_limit = self._INITIAL_WINDOW_BARS.get(timeframe)
        if bar_limit is None or total_candles <= bar_limit:
            return candles, False, bar_limit, total_candles
        LOGGER.info(
            "apply_initial_snapshot_window: preserve_full_history timeframe=%s total_candles=%s legacy_bar_limit=%s",
            timeframe.value,
            total_candles,
            bar_limit,
        )
        return candles, False, bar_limit, total_candles

    def _collect_matching_history_payloads(
        self,
        request: ReplayWorkbenchBuildRequest,
        *,
        limit: int = 4000,
    ) -> list[AdapterHistoryBarsPayload]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=request.instrument_symbol,
            limit=limit,
        )
        grouped_payloads: dict[tuple[str | None, datetime, Timeframe], AdapterHistoryBarsPayload] = {}
        for stored in candidates:
            payload = AdapterHistoryBarsPayload.model_validate(stored.observed_payload)
            if not payload.bars:
                continue
            if not self._chart_instance_filter_matches_model_payload(request.chart_instance_id, payload):
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, request.display_timeframe):
                continue
            overlap_seconds = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                request.window_start,
                request.window_end,
            )
            if overlap_seconds <= 0:
                continue
            key = (
                payload.source.chart_instance_id,
                payload.observed_window_start,
                payload.bar_timeframe,
            )
            current = grouped_payloads.get(key)
            if current is None or self._history_payload_rank(payload) > self._history_payload_rank(current):
                grouped_payloads[key] = payload

        payloads = list(grouped_payloads.values())
        payloads.sort(key=lambda item: self._history_payload_sort_key(item, request), reverse=True)
        return payloads

    def _find_matching_history_payload(self, request: ReplayWorkbenchBuildRequest) -> AdapterHistoryBarsPayload | None:
        payloads = self._collect_matching_history_payloads(request)
        return payloads[0] if payloads else None

    def _find_matching_history_footprint_payloads(
        self,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[AdapterHistoryFootprintPayload]:
        return self._find_complete_history_footprint_batch(
            instrument_symbol=request.instrument_symbol,
            chart_instance_id=request.chart_instance_id,
            timeframe=request.display_timeframe,
            window_start=request.window_start,
            window_end=request.window_end,
        )

    def _build_candles_from_history_payload(
        self,
        payload: AdapterHistoryBarsPayload,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayChartBar]:
        filtered_bars = [
            bar
            for bar in payload.bars
            if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        if not filtered_bars and payload.bar_timeframe == request.display_timeframe and payload.bars:
            filtered_bars = payload.bars
        if payload.bar_timeframe == request.display_timeframe:
            return [
                ReplayChartBar(
                    started_at=bar.started_at,
                    ended_at=bar.ended_at,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    delta=bar.delta,
                    bid_volume=bar.bid_volume,
                    ask_volume=bar.ask_volume,
                )
                for bar in filtered_bars
            ]

        source_minutes = self._TIMEFRAME_MINUTES[payload.bar_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[request.display_timeframe]
        buckets: dict[datetime, dict[str, Any]] = {}
        for bar in filtered_bars:
            bucket_start = self._bucket_start(bar.started_at, request.display_timeframe)
            bucket = buckets.setdefault(
                bucket_start,
                {
                    "started_at": bucket_start,
                    "ended_at": bucket_start + timedelta(minutes=target_minutes) - timedelta(seconds=1),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 0,
                    "delta": 0,
                    "bid_volume": 0,
                    "ask_volume": 0,
                },
            )
            if bucket["open"] is None:
                bucket["open"] = bar.open
                bucket["high"] = bar.high
                bucket["low"] = bar.low
            else:
                bucket["high"] = max(bucket["high"], bar.high)
                bucket["low"] = min(bucket["low"], bar.low)
            bucket["close"] = bar.close
            if bar.volume is not None:
                bucket["volume"] += bar.volume
            if bar.delta is not None:
                bucket["delta"] += bar.delta
            if bar.bid_volume is not None:
                bucket["bid_volume"] += bar.bid_volume
            if bar.ask_volume is not None:
                bucket["ask_volume"] += bar.ask_volume

        return [
            ReplayChartBar(
                started_at=bucket["started_at"],
                ended_at=bucket["ended_at"],
                open=bucket["open"],
                high=bucket["high"],
                low=bucket["low"],
                close=bucket["close"],
                volume=bucket["volume"],
                delta=bucket["delta"],
                bid_volume=bucket["bid_volume"],
                ask_volume=bucket["ask_volume"],
            )
            for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
            if bucket["open"] is not None
        ]

    def _build_candles_from_history_payloads(
        self,
        payloads: list[AdapterHistoryBarsPayload],
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayChartBar]:
        if not payloads:
            return []

        candle_map: dict[datetime, ReplayChartBar] = {}
        for payload in sorted(payloads, key=lambda item: self._history_payload_sort_key(item, request), reverse=True):
            for candle in self._build_candles_from_history_payload(payload, request):
                candle_map.setdefault(candle.started_at, candle)
        return [candle_map[start] for start in sorted(candle_map)]

    def _build_footprint_digest(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        request: ReplayWorkbenchBuildRequest,
    ) -> dict[str, Any]:
        filtered_bars = [
            bar
            for payload in payloads
            for bar in payload.bars
            if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        level_clusters: dict[float, dict[str, Any]] = {}
        extreme_bars: list[dict[str, Any]] = []
        total_level_count = 0

        for bar in filtered_bars:
            bar_total_volume = 0
            bar_abs_delta = 0
            top_volume_level: dict[str, Any] | None = None
            top_delta_level: dict[str, Any] | None = None
            for level in bar.price_levels:
                total_level_count += 1
                total_volume = level.total_volume or 0
                delta = level.delta or 0
                bar_total_volume += total_volume
                bar_abs_delta += abs(delta)
                cluster = level_clusters.setdefault(
                    level.price,
                    {
                        "price": level.price,
                        "bar_hits": 0,
                        "total_volume": 0,
                        "net_delta": 0,
                    },
                )
                cluster["bar_hits"] += 1
                cluster["total_volume"] += total_volume
                cluster["net_delta"] += delta
                candidate = {
                    "price": level.price,
                    "bid_volume": level.bid_volume,
                    "ask_volume": level.ask_volume,
                    "total_volume": total_volume,
                    "delta": delta,
                }
                if top_volume_level is None or total_volume > top_volume_level["total_volume"]:
                    top_volume_level = candidate
                if top_delta_level is None or abs(delta) > abs(top_delta_level["delta"]):
                    top_delta_level = candidate

            extreme_bars.append(
                {
                    "started_at": bar.started_at,
                    "ended_at": bar.ended_at,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "delta": bar.delta,
                    "price_level_count": len(bar.price_levels),
                    "bar_total_price_level_volume": bar_total_volume,
                    "bar_abs_price_level_delta": bar_abs_delta,
                    "top_volume_level": top_volume_level,
                    "top_delta_level": top_delta_level,
                },
            )

        top_bars = sorted(
            extreme_bars,
            key=lambda item: (
                item.get("volume") or 0,
                abs(item.get("delta") or 0),
                item.get("bar_total_price_level_volume") or 0,
            ),
            reverse=True,
        )[:20]
        repeated_levels = sorted(
            level_clusters.values(),
            key=lambda item: (item["bar_hits"], item["total_volume"], abs(item["net_delta"])),
            reverse=True,
        )[:20]

        return {
            "batch_id": payloads[0].batch_id if payloads else None,
            "bar_timeframe": payloads[0].bar_timeframe if payloads else None,
            "chunk_count": len(payloads),
            "bar_count": len(filtered_bars),
            "price_level_count": total_level_count,
            "top_bars": top_bars,
            "repeated_price_levels": repeated_levels,
        }

    def _build_footprint_event_annotations(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        tick_size: float,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayEventAnnotation]:
        digest = self._build_footprint_digest(payloads, request)
        events: list[ReplayEventAnnotation] = []
        for index, item in enumerate(digest["top_bars"][:8]):
            top_level = item.get("top_volume_level") or item.get("top_delta_level")
            if top_level is None:
                continue
            price = top_level["price"]
            side = None
            if (top_level.get("delta") or 0) > 0:
                side = StructureSide.BUY
            elif (top_level.get("delta") or 0) < 0:
                side = StructureSide.SELL
            events.append(
                ReplayEventAnnotation(
                    event_id=f"historical-footprint-bar-{index}",
                    event_kind="historical_footprint_extreme",
                    source_kind="atas_history_footprint",
                    observed_at=item["started_at"],
                    price=price,
                    price_low=price,
                    price_high=price,
                    side=side,
                    confidence=0.6,
                    linked_ids=[digest["batch_id"]],
                    notes=[
                        f"price_level_count={item['price_level_count']}",
                        f"bar_volume={item.get('volume') or 0}",
                        f"bar_delta={item.get('delta') or 0}",
                    ],
                ),
            )
        return events

    def _build_footprint_focus_regions(
        self,
        payloads: list[AdapterHistoryFootprintPayload],
        tick_size: float,
        request: ReplayWorkbenchBuildRequest,
    ) -> list[ReplayFocusRegion]:
        digest = self._build_footprint_digest(payloads, request)
        regions: list[ReplayFocusRegion] = []
        price_band = max(tick_size, tick_size / 2)
        started_at = request.window_start
        for index, item in enumerate(digest["repeated_price_levels"][:10]):
            price = item["price"]
            regions.append(
                ReplayFocusRegion(
                    region_id=f"historical-footprint-level-{index}",
                    label=f"历史足迹价位 {price}",
                    started_at=started_at,
                    ended_at=request.window_end,
                    price_low=price - price_band,
                    price_high=price + price_band,
                    priority=max(1, min(10, int(item["bar_hits"]))),
                    reason_codes=["historical_footprint", "repeated_price_level"],
                    linked_event_ids=[],
                    notes=[
                        f"bar_hits={item['bar_hits']}",
                        f"total_volume={item['total_volume']}",
                        f"net_delta={item['net_delta']}",
                    ],
                ),
            )
        return regions

    def _build_candles(self, timeframe: Timeframe, ingestions: list[StoredIngestion]) -> list[ReplayChartBar]:
        if timeframe not in self._TIMEFRAME_MINUTES:
            raise ValueError(f"Replay builder does not support display_timeframe '{timeframe}' yet.")

        buckets: dict[datetime, dict[str, Any]] = {}
        for stored in ingestions:
            payload = stored.observed_payload
            observed_at = self._payload_observed_at(payload)
            bucket_start = self._bucket_start(observed_at, timeframe)
            bucket = buckets.setdefault(
                bucket_start,
                {
                    "started_at": bucket_start,
                    "ended_at": bucket_start + timedelta(minutes=self._TIMEFRAME_MINUTES[timeframe]) - timedelta(seconds=1),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 0,
                    "delta": 0,
                    "bid_volume": 0,
                    "ask_volume": 0,
                },
            )
            last_price = payload["price_state"]["last_price"]
            if bucket["open"] is None:
                bucket["open"] = last_price
                bucket["high"] = last_price
                bucket["low"] = last_price
            bucket["high"] = max(bucket["high"], last_price)
            bucket["low"] = min(bucket["low"], last_price)
            bucket["close"] = last_price
            bucket["volume"] += payload.get("trade_summary", {}).get("volume", 0)
            bucket["delta"] += payload.get("trade_summary", {}).get("net_delta", 0)
            bucket["bid_volume"] += payload.get("trade_summary", {}).get("aggressive_sell_volume", 0)
            bucket["ask_volume"] += payload.get("trade_summary", {}).get("aggressive_buy_volume", 0)

        return [
            ReplayChartBar(
                started_at=bucket["started_at"],
                ended_at=bucket["ended_at"],
                open=bucket["open"],
                high=bucket["high"],
                low=bucket["low"],
                close=bucket["close"],
                volume=bucket["volume"],
                delta=bucket["delta"],
                bid_volume=bucket["bid_volume"],
                ask_volume=bucket["ask_volume"],
            )
            for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
            if bucket["open"] is not None
        ]

    def _select_trade_active_continuous_messages(
        self,
        ingestions: list[StoredIngestion],
    ) -> list[StoredIngestion]:
        if not ingestions:
            return []

        ordered = sorted(ingestions, key=lambda item: self._payload_observed_at(item.observed_payload))
        selected: list[StoredIngestion] = []
        previous_last_price: float | None = None
        for stored in ordered:
            payload = stored.observed_payload
            trade_summary = payload.get("trade_summary") or {}
            has_trade_activity = any(
                (
                    trade_summary.get("trade_count"),
                    trade_summary.get("volume"),
                    trade_summary.get("aggressive_buy_volume"),
                    trade_summary.get("aggressive_sell_volume"),
                    trade_summary.get("net_delta"),
                )
            )
            price_state = payload.get("price_state") or {}
            last_price = price_state.get("last_price")
            price_changed = (
                previous_last_price is not None
                and last_price is not None
                and last_price != previous_last_price
            )
            if has_trade_activity or price_changed:
                selected.append(stored)
            if last_price is not None:
                previous_last_price = last_price
        return selected

    def _try_get_latest_tick_quote(self, symbol: str) -> dict[str, Any] | None:
        repository = self._repository
        if not hasattr(repository, "get_latest_tick_quote"):
            return None
        try:
            quote = repository.get_latest_tick_quote(
                symbol=symbol,
                lookback_seconds=300,
                limit=3000,
            )
        except Exception:
            return None
        return quote if isinstance(quote, dict) else None

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _chart_instance_filter_matches_dict_payload(
        chart_instance_id: str | None,
        payload: dict[str, Any],
    ) -> bool:
        if chart_instance_id is None:
            return True
        instrument = payload.get("instrument", {})
        return chart_instance_ids_match(
            chart_instance_id,
            payload.get("source", {}).get("chart_instance_id"),
            instrument_symbol=instrument.get("symbol"),
            contract_symbol=instrument.get("contract_symbol") or instrument.get("symbol"),
            display_timeframe=payload.get("display_timeframe"),
            venue=instrument.get("venue"),
            currency=instrument.get("currency"),
        )

    @staticmethod
    def _chart_instance_filter_matches_model_payload(
        chart_instance_id: str | None,
        payload: Any,
    ) -> bool:
        if chart_instance_id is None:
            return True
        instrument = payload.instrument
        return chart_instance_ids_match(
            chart_instance_id,
            payload.source.chart_instance_id,
            instrument_symbol=instrument.symbol,
            contract_symbol=instrument.contract_symbol or instrument.symbol,
            display_timeframe=getattr(payload, "bar_timeframe", None) or payload.display_timeframe,
            venue=instrument.venue,
            currency=instrument.currency,
        )

    @staticmethod
    def _backfill_chart_instance_matches(
        requested_chart_instance_id: str | None,
        stored_chart_instance_id: str | None,
        *,
        instrument_symbol: str,
        contract_symbol: str | None,
        display_timeframe: Timeframe | str,
    ) -> bool:
        if stored_chart_instance_id is None:
            return True
        if requested_chart_instance_id is None:
            return False
        if chart_instance_ids_match(
            requested_chart_instance_id,
            stored_chart_instance_id,
            instrument_symbol=instrument_symbol,
            contract_symbol=contract_symbol or instrument_symbol,
            display_timeframe=display_timeframe,
        ):
            return True

        normalized_requested = normalize_identifier(requested_chart_instance_id)
        normalized_stored = normalize_identifier(stored_chart_instance_id)
        normalized_contract = normalize_identifier(normalize_symbol(contract_symbol) or normalize_symbol(instrument_symbol))
        normalized_timeframe = normalize_identifier(normalize_timeframe(display_timeframe))
        if normalized_requested is None or normalized_stored is None or normalized_contract is None or normalized_timeframe is None:
            return False

        prefix = f"chart-{normalized_contract}-{normalized_timeframe}-"
        return (
            is_generic_chart_instance_id(normalized_stored)
            and normalized_requested.startswith(prefix)
        ) or (
            is_generic_chart_instance_id(normalized_requested)
            and normalized_stored.startswith(prefix)
        )

    @staticmethod
    def _payload_observed_at(payload: dict[str, Any]) -> datetime:
        return parse_utc(payload.get("observed_window_end") or payload["emitted_at"])

    def _patch_live_candle_gaps(
        self,
        *,
        instrument_symbol: str,
        display_timeframe: Timeframe,
        chart_instance_id: str | None,
        candles: list[ReplayChartBar],
    ) -> list[ReplayChartBar]:
        """Detect time gaps in live candles and fill them from the latest history-bars payload.

        Note: this runs only for the *live tail* path. The replay snapshot builder has its
        own gap-filling logic.
        """
        if len(candles) < 2:
            return candles

        expected_delta = timedelta(minutes=self._TIMEFRAME_MINUTES.get(display_timeframe, 1))
        tolerance = timedelta(seconds=5)

        # Detect if any gap exists
        has_gap = False
        gap_window_start: datetime | None = None
        gap_window_end: datetime | None = None
        for i in range(1, len(candles)):
            delta = candles[i].started_at - candles[i - 1].started_at
            if delta > expected_delta + tolerance:
                has_gap = True
                # Missing window is between the end of previous candle and start of next candle.
                start = candles[i - 1].ended_at + timedelta(seconds=1)
                end = candles[i].started_at - timedelta(seconds=1)
                if gap_window_start is None or start < gap_window_start:
                    gap_window_start = start
                if gap_window_end is None or end > gap_window_end:
                    gap_window_end = end

        if not has_gap or gap_window_start is None or gap_window_end is None or gap_window_end < gap_window_start:
            return candles

        filler_request = ReplayWorkbenchBuildRequest(
            cache_key="__gap_fill_internal__",
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            window_start=gap_window_start,
            window_end=gap_window_end,
            chart_instance_id=chart_instance_id,
        )
        history_payloads = self._collect_matching_history_payloads(filler_request, limit=400)
        if not history_payloads:
            return candles

        filler_candles = self._build_candles_from_history_payloads(history_payloads, filler_request)
        if not filler_candles:
            return candles

        # Merge: existing candles take priority, fillers only fill empty slots
        merged: dict[datetime, ReplayChartBar] = {}
        for bar in filler_candles:
            merged[bar.started_at] = bar
        for bar in candles:
            merged[bar.started_at] = bar  # live data wins

        return [merged[key] for key in sorted(merged)]

    def _detect_candle_time_gaps(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> list[dict[str, Any]]:
        """Detect missing-time gaps based on candle started_at spacing.

        Returns a list of dicts, each describing a single gap segment.
        """
        if timeframe not in self._TIMEFRAME_MINUTES or len(candles) < 2:
            return []

        expected_seconds = int(self._TIMEFRAME_MINUTES[timeframe] * 60)
        tolerance_seconds = 5

        gaps: list[dict[str, Any]] = []
        for prev, nxt in zip(candles, candles[1:]):
            actual_seconds = int((nxt.started_at - prev.started_at).total_seconds())
            if actual_seconds <= expected_seconds + tolerance_seconds:
                continue

            # Estimate how many bars should exist between these starts.
            # If there is a remainder > tolerance, we treat it as needing one extra bar.
            bars_between = max(1, actual_seconds // expected_seconds)
            remainder = actual_seconds % expected_seconds
            if remainder > tolerance_seconds:
                bars_between += 1
            missing = max(1, bars_between - 1)

            gaps.append(
                {
                    "prev_started_at": prev.started_at,
                    "prev_ended_at": prev.ended_at,
                    "next_started_at": nxt.started_at,
                    "next_ended_at": nxt.ended_at,
                    "expected_delta_seconds": expected_seconds,
                    "actual_delta_seconds": actual_seconds,
                    "missing_bar_count": missing,
                }
            )

        return gaps

    def _fill_candle_time_gaps(
        self,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], list[dict[str, Any]], int]:
        """Fill time gaps by inserting synthetic flat bars.

        This is a pragmatic UI/analytics workaround: the replay chart is index-based.
        If we do not insert missing bars, gaps get visually compressed and are easy to miss.

        Returns (filled_candles, gaps, inserted_bar_count).
        """
        gaps = self._detect_candle_time_gaps(candles, timeframe)
        if not gaps:
            return candles, [], 0

        expected_delta = timedelta(minutes=self._TIMEFRAME_MINUTES.get(timeframe, 1))
        inserted = 0
        output: list[ReplayChartBar] = []

        # Ensure sorted and unique by started_at (existing candles win).
        candle_map: dict[datetime, ReplayChartBar] = {bar.started_at: bar for bar in candles}
        sorted_starts = sorted(candle_map)
        sorted_candles = [candle_map[start] for start in sorted_starts]

        for idx, bar in enumerate(sorted_candles):
            output.append(bar)
            if idx >= len(sorted_candles) - 1:
                continue

            next_bar = sorted_candles[idx + 1]
            delta = next_bar.started_at - bar.started_at
            tolerance = timedelta(seconds=5)
            if delta <= expected_delta + tolerance:
                continue

            # Recompute missing count deterministically from timedelta.
            expected_seconds = expected_delta.total_seconds()
            actual_seconds = delta.total_seconds()
            bars_between = int(actual_seconds // expected_seconds)
            remainder = actual_seconds % expected_seconds
            if remainder > tolerance.total_seconds():
                bars_between += 1
            missing = max(1, bars_between - 1)
            if missing > self._MAX_GAP_FILL_BARS_PER_SEGMENT:
                continue

            for j in range(1, missing + 1):
                if inserted >= self._MAX_GAP_FILL_BARS:
                    return output + sorted_candles[idx + 1 :], gaps, inserted
                start = bar.started_at + expected_delta * j
                end = start + expected_delta - timedelta(seconds=1)
                price = bar.close
                filler = ReplayChartBar(
                    started_at=start,
                    ended_at=end,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    delta=0,
                    bid_volume=0,
                    ask_volume=0,
                    source_kind="synthetic_gap_fill",
                    is_synthetic=True,
                )
                # Don't override real bars if they exist
                if filler.started_at not in candle_map:
                    output.append(filler)
                    inserted += 1

        output.sort(key=lambda item: item.started_at)
        return output, gaps, inserted

    def _merge_history_candles_with_continuous_overlay(
        self,
        *,
        history_candles: list[ReplayChartBar],
        continuous_messages: list[StoredIngestion],
        timeframe: Timeframe,
    ) -> tuple[list[ReplayChartBar], int]:
        if not history_candles or not continuous_messages:
            return history_candles, 0

        active_messages = self._select_trade_active_continuous_messages(continuous_messages)
        continuous_candles = self._build_candles(timeframe, active_messages)
        if not continuous_candles:
            return history_candles, 0

        # Only overlay continuous bars that start STRICTLY AFTER the last completed history bar.
        # Using ended_at (exclusive boundary) prevents in-progress real-time bars from
        # overwriting the last completed history bar and creating abnormal giant wicks.
        last_history_bar = history_candles[-1]
        overlay_cutoff = last_history_bar.ended_at
        merged: dict[datetime, ReplayChartBar] = {bar.started_at: bar for bar in history_candles}
        overlay_count = 0
        for bar in continuous_candles:
            if bar.started_at <= overlay_cutoff:
                continue
            merged[bar.started_at] = bar
            overlay_count += 1

        return [merged[key] for key in sorted(merged)], overlay_count


    def _can_build_timeframe_from_history(self, source_timeframe: Timeframe, target_timeframe: Timeframe) -> bool:
        if source_timeframe not in self._TIMEFRAME_MINUTES or target_timeframe not in self._TIMEFRAME_MINUTES:
            return False
        source_minutes = self._TIMEFRAME_MINUTES[source_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[target_timeframe]
        return source_minutes <= target_minutes and target_minutes % source_minutes == 0

    def _build_event_annotations(self, ingestions: list[StoredIngestion]) -> list[ReplayEventAnnotation]:
        events: dict[str, ReplayEventAnnotation] = {}
        for stored in ingestions:
            payload = stored.observed_payload
            emitted_at = parse_utc(payload["emitted_at"])
            for item in payload.get("same_price_replenishment", []):
                event_id = f"replenish-{item['track_id']}"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="same_price_replenishment",
                    source_kind="collector",
                    observed_at=emitted_at,
                    price=item["price"],
                    price_low=item["price"],
                    price_high=item["price"],
                    side=item["side"],
                    confidence=min(1.0, 0.5 + (item.get("replenishment_count", 0) * 0.1)),
                    linked_ids=[item["track_id"]],
                    notes=[f"replenishment_count={item.get('replenishment_count', 0)}"],
                )
            for item in payload.get("significant_liquidity", []):
                event_id = f"liquidity-{item['track_id']}"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="significant_liquidity",
                    source_kind="collector",
                    observed_at=parse_utc(item["last_observed_at"]),
                    price=item["price"],
                    price_low=item["price"],
                    price_high=item["price"],
                    side=item["side"],
                    confidence=item.get("heat_score"),
                    linked_ids=[item["track_id"]],
                    notes=[
                        f"status={item['status']}",
                        f"replenishment_count={item.get('replenishment_count', 0)}",
                    ],
                )
            drive = payload.get("active_initiative_drive")
            if drive is not None:
                event_id = drive["drive_id"]
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="initiative_drive",
                    source_kind="collector",
                    observed_at=parse_utc(drive["started_at"]),
                    price_low=drive["price_low"],
                    price_high=drive["price_high"],
                    side=drive["side"],
                    confidence=min(1.0, abs(drive["net_delta"]) / max(1, drive["aggressive_volume"])),
                    linked_ids=[drive["drive_id"]],
                    notes=[f"price_travel_ticks={drive['price_travel_ticks']}"],
                )
            gap = payload.get("gap_reference")
            if gap is not None:
                event_id = gap["gap_id"]
                gap_kind = "gap_fill_watch" if gap.get("fully_filled_at") is None else "gap_fully_filled"
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind=gap_kind,
                    source_kind="collector",
                    observed_at=parse_utc(gap["first_touch_at"] or gap["opened_at"]),
                    price_low=gap["gap_low"],
                    price_high=gap["gap_high"],
                    side=StructureSide.BUY if gap["direction"] == "up" else StructureSide.SELL,
                    confidence=gap["fill_ratio"],
                    linked_ids=[gap["gap_id"]],
                    notes=[f"fill_attempt_count={gap['fill_attempt_count']}"],
                )
            post_harvest = payload.get("active_post_harvest_response")
            if post_harvest is not None:
                event_id = post_harvest["response_id"]
                events[event_id] = ReplayEventAnnotation(
                    event_id=event_id,
                    event_kind="post_harvest_response",
                    source_kind="collector",
                    observed_at=parse_utc(post_harvest["harvest_completed_at"]),
                    price_low=post_harvest["harvested_price_low"],
                    price_high=post_harvest["harvested_price_high"],
                    side=post_harvest["harvest_side"],
                    linked_ids=[post_harvest["harvest_subject_id"]],
                    notes=[f"outcome={post_harvest['outcome']}"],
                )
        return sorted(events.values(), key=lambda item: item.observed_at)

    def _build_focus_regions(
        self,
        ingestions: list[StoredIngestion],
        event_annotations: list[ReplayEventAnnotation],
    ) -> list[ReplayFocusRegion]:
        latest_payload = ingestions[-1].observed_payload
        regions: list[ReplayFocusRegion] = []
        linked_event_ids = {event.event_id for event in event_annotations}
        for item in latest_payload.get("significant_liquidity", []):
            regions.append(
                ReplayFocusRegion(
                    region_id=f"focus-{item['track_id']}",
                    label=f"{item['side']} liquidity {item['price']}",
                    started_at=parse_utc(item["first_observed_at"]),
                    ended_at=parse_utc(item["last_observed_at"]),
                    price_low=item["price"],
                    price_high=item["price"],
                    priority=max(1, min(10, int((item.get("heat_score") or 0.5) * 10))),
                    reason_codes=[
                        "significant_liquidity",
                        "same_price_replenishment" if item.get("replenishment_count", 0) > 0 else "tracked_liquidity",
                    ],
                    linked_event_ids=[event_id for event_id in linked_event_ids if item["track_id"] in event_id],
                    notes=[f"touch_count={item['touch_count']}"],
                )
            )

        zone = latest_payload.get("active_zone_interaction")
        if zone is not None:
            regions.append(
                ReplayFocusRegion(
                    region_id=f"focus-{zone['zone_id']}",
                    label="active defended zone",
                    started_at=parse_utc(zone["started_at"]),
                    ended_at=None,
                    price_low=zone["zone_low"],
                    price_high=zone["zone_high"],
                    priority=8,
                    reason_codes=["zone_interaction", "same_price_replenishment"],
                    linked_event_ids=[zone["zone_id"]],
                    notes=[f"seconds_held={zone['seconds_held']}"],
                )
            )
        regions.sort(key=lambda item: item.priority, reverse=True)
        return regions[:10]

    def _find_complete_history_footprint_batch(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
    ) -> list[AdapterHistoryFootprintPayload]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_footprint",
            instrument_symbol=instrument_symbol,
            limit=4000,
        )
        grouped: dict[str, list[AdapterHistoryFootprintPayload]] = {}
        for stored in candidates:
            payload = AdapterHistoryFootprintPayload.model_validate(stored.observed_payload)
            if not payload.bars:
                continue
            if not self._chart_instance_filter_matches_model_payload(chart_instance_id, payload):
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, timeframe):
                continue
            overlap_seconds = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                window_start,
                window_end,
            )
            if overlap_seconds <= 0:
                continue
            grouped.setdefault(payload.batch_id, []).append(payload)

        if not grouped:
            return []

        complete_batches: list[tuple[float, float, int, int, list[AdapterHistoryFootprintPayload]]] = []
        for items in grouped.values():
            expected = items[0].chunk_count
            chunk_indexes = {item.chunk_index for item in items}
            # ATAS may refresh only the overlapping tail of a historical footprint batch.
            # For replay we prefer the best overlapping subset instead of discarding the
            # batch outright when some non-overlapping chunks are missing.
            if len(chunk_indexes) < max(1, expected // 2):
                continue
            overlap_seconds = self._overlap_seconds(
                min(item.observed_window_start for item in items),
                max(item.observed_window_end for item in items),
                window_start,
                window_end,
            )
            if overlap_seconds <= 0:
                continue
            requested_seconds = max((window_end - window_start).total_seconds(), 1.0)
            coverage_ratio = overlap_seconds / requested_seconds
            complete_batches.append(
                (
                    coverage_ratio,
                    overlap_seconds,
                    sum(len(item.bars) for item in items),
                    -self._TIMEFRAME_MINUTES.get(items[0].bar_timeframe, 0),
                    sorted(items, key=lambda item: item.chunk_index),
                )
            )

        if not complete_batches:
            return []

        complete_batches.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return complete_batches[0][4]

    def _history_snapshot_should_refresh(
        self,
        request: ReplayWorkbenchBuildRequest,
        cached_ingestion: StoredIngestion,
        history_payloads: list[AdapterHistoryBarsPayload],
    ) -> bool:
        if not history_payloads:
            return False
        cached_payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
        if cached_payload.display_timeframe != request.display_timeframe:
            return True
        primary_history_payload = history_payloads[0]
        estimated_count = self._estimate_history_candle_count(history_payloads, request)
        cached_count = len(cached_payload.candles)
        if estimated_count > max(cached_count + 50, int(cached_count * 1.2)):
            return True
        cached_history_message_id = cached_payload.raw_features.get("history_message_id")
        if cached_history_message_id != primary_history_payload.message_id:
            cached_actual_end = cached_payload.raw_features.get("actual_window_end")
            if cached_actual_end is None:
                return True
            try:
                cached_actual_end_dt = parse_utc(str(cached_actual_end).replace("Z", "+00:00"))
            except ValueError:
                return True
            latest_history_end = max(payload.observed_window_end for payload in history_payloads)
            if latest_history_end > cached_actual_end_dt:
                return True
        return False

    def _estimate_history_candle_count(
        self,
        payloads: list[AdapterHistoryBarsPayload],
        request: ReplayWorkbenchBuildRequest,
    ) -> int:
        return len(self._build_candles_from_history_payloads(payloads, request))

    def _history_payload_rank(self, payload: AdapterHistoryBarsPayload) -> tuple[datetime, int]:
        return (payload.observed_window_end, len(payload.bars))

    def _history_payload_sort_key(
        self,
        payload: AdapterHistoryBarsPayload,
        request: ReplayWorkbenchBuildRequest,
    ) -> tuple[int, float, datetime, int, int]:
        source_minutes = self._TIMEFRAME_MINUTES.get(payload.bar_timeframe, 0)
        overlap_seconds = self._overlap_seconds(
            payload.observed_window_start,
            payload.observed_window_end,
            request.window_start,
            request.window_end,
        )
        return (
            int(payload.bar_timeframe == request.display_timeframe),
            overlap_seconds,
            payload.observed_window_end,
            len(payload.bars),
            -source_minutes,
        )

    def _gap_segment_is_fully_covered(
        self,
        *,
        candles: list[ReplayChartBar],
        timeframe: Timeframe,
        segment: ReplayWorkbenchGapSegment,
    ) -> bool:
        expected_delta = timedelta(minutes=self._TIMEFRAME_MINUTES.get(timeframe, 1))
        candle_starts = {candle.started_at for candle in candles}
        if segment.prev_ended_at is not None:
            expected_start = segment.prev_ended_at + timedelta(seconds=1)
        else:
            expected_start = segment.next_started_at - (expected_delta * segment.missing_bar_count)
        for index in range(segment.missing_bar_count):
            if expected_start + (expected_delta * index) not in candle_starts:
                return False
        return True

    @staticmethod
    def _overlap_seconds(
        source_start: datetime,
        source_end: datetime,
        request_start: datetime,
        request_end: datetime,
    ) -> float:
        overlap_start = max(source_start, request_start)
        overlap_end = min(source_end, request_end)
        if overlap_end < overlap_start:
            return 0.0
        return (overlap_end - overlap_start).total_seconds()

    def _find_history_footprint_bar(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        bar_started_at: datetime,
    ) -> AdapterHistoryFootprintBar | None:
        payloads = self._find_complete_history_footprint_batch(
            instrument_symbol=instrument_symbol,
            chart_instance_id=chart_instance_id,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )
        for payload in payloads:
            for bar in payload.bars:
                if bar.started_at == bar_started_at:
                    return bar
        return None

    def _build_strategy_candidates(
        self,
        event_annotations: list[ReplayEventAnnotation],
        focus_regions: list[ReplayFocusRegion] | None = None,
        instrument_symbol: str = "NQ",
    ) -> list[ReplayStrategyCandidate]:
        # Legacy hardcoded candidates (preserved for backward compat)
        kinds = {item.event_kind for item in event_annotations}
        candidates: list[ReplayStrategyCandidate] = []
        if "same_price_replenishment" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind == "same_price_replenishment"]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="pattern-nq-replenished-bid-launchpad",
                    title="NQ replenished bid launchpad",
                    source_path="docs/strategy_library/patterns/nq_replenished_bid_launchpad_into_upper_liquidity.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["same-price replenishment was observed in the requested replay window"],
                )
            )
        if "post_harvest_response" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind == "post_harvest_response"]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="pattern-nq-upper-liquidity-harvest-then-lower-relocation",
                    title="NQ upper liquidity harvest then lower relocation",
                    source_path="docs/strategy_library/patterns/nq_upper_liquidity_harvest_then_lower_relocation.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["post-harvest reaction was observed after a completed liquidity objective"],
                )
            )
        if "gap_fill_watch" in kinds or "gap_fully_filled" in kinds:
            matched_ids = [item.event_id for item in event_annotations if item.event_kind in {"gap_fill_watch", "gap_fully_filled"}]
            candidates.append(
                ReplayStrategyCandidate(
                    strategy_id="gap-fill-opening-auction-doctrine",
                    title="Gap fill opening-auction doctrine",
                    source_path="docs/shuyin_gap_fill_system_absorption_checklist.md",
                    matched_event_ids=matched_ids,
                    why_relevant=["gap reference remained active inside the replay window"],
                )
            )
        # Data-driven enrichment from strategy_index.json
        try:
            engine = StrategySelectionEngine(root_dir=self._repository._database_path.parent.parent if hasattr(self._repository, '_database_path') else None)
            engine_candidates = engine.select_candidates(
                event_annotations,
                focus_regions or [],
                instrument_symbol=instrument_symbol,
            )
            existing_ids = {c.strategy_id for c in candidates}
            for ec in engine_candidates:
                if ec.strategy_id not in existing_ids:
                    candidates.append(ec)
                    existing_ids.add(ec.strategy_id)
        except Exception:
            pass  # Graceful fallback to legacy-only
        return candidates

    @staticmethod
    def _build_ai_briefing(
        instrument_symbol: str,
        strategy_candidates: list[ReplayStrategyCandidate],
        focus_regions: list[ReplayFocusRegion],
    ) -> ReplayAiBriefing | None:
        if not strategy_candidates and not focus_regions:
            return None
        return ReplayAiBriefing(
            objective=f"Review the last replay window for {instrument_symbol} and rank the strongest support, resistance, continuation, and reversal zones.",
            focus_questions=[
                "Which focus regions still look defendable on revisit?",
                "Which regions are more likely to fail and convert into post-harvest pullback or reversal?",
            ],
            required_outputs=["key_zones", "continuation_vs_reversal", "invalidations"],
            notes=["Treat event annotations as observed facts and explain the zone logic explicitly."],
        )

    def _find_latest_replay_snapshot(
        self,
        *,
        cache_key: str | None = None,
        replay_snapshot_id: str | None = None,
        ingestion_id: str | None = None,
    ) -> StoredIngestion | None:
        if ingestion_id is not None:
            stored = self._repository.get_ingestion(ingestion_id)
            if stored is None or stored.ingestion_kind != "replay_workbench_snapshot":
                return None
            return stored

        for stored in self._repository.list_ingestions(ingestion_kind="replay_workbench_snapshot", limit=500):
            payload = stored.observed_payload
            if cache_key is not None and payload.get("cache_key") == cache_key:
                return stored
            if replay_snapshot_id is not None and payload.get("replay_snapshot_id") == replay_snapshot_id:
                return stored
        return None

    def _find_latest_replay_snapshot_by_cache_identity(self, cache_key: str) -> tuple[str, StoredIngestion] | None:
        """Find the newest snapshot with the same symbol/timeframe/window_start even if window_end drifted.

        This helps during closed sessions or page refreshes where the UI rebuilds cache_key with a new
        current-time window_end, while the operator really wants to reopen the most recent cached replay
        for the same symbol/timeframe/lookback identity.
        """
        symbol, timeframe, window_start, _window_end = self._split_cache_key(cache_key)
        if symbol is None or timeframe is None or window_start is None:
            return None

        for stored in self._repository.list_ingestions(ingestion_kind="replay_workbench_snapshot", limit=500):
            payload = stored.observed_payload
            payload_key = payload.get("cache_key")
            if not isinstance(payload_key, str):
                continue
            p_symbol, p_timeframe, p_window_start, _p_window_end = self._split_cache_key(payload_key)
            if p_symbol == symbol and p_timeframe == timeframe and p_window_start == window_start:
                return payload_key, stored
        return None

    @staticmethod
    def _split_cache_key(cache_key: str) -> tuple[str | None, str | None, str | None, str | None]:
        parts = (cache_key or "").split("|", 3)
        if len(parts) != 4:
            return None, None, None, None
        return parts[0], parts[1], parts[2], parts[3]

    @staticmethod
    def _build_summary(payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchAcceptedSummary:
        return ReplayWorkbenchAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            display_timeframe=payload.display_timeframe,
            acquisition_mode=payload.acquisition_mode,
            verification_status=payload.verification_state.status,
            verification_count=payload.verification_state.verification_count,
            locked_until_manual_reset=payload.verification_state.locked_until_manual_reset,
            fetch_only_when_missing=payload.cache_policy.fetch_only_when_missing,
            max_verifications_per_day=payload.cache_policy.max_verifications_per_day,
            verification_passes_to_lock=payload.cache_policy.verification_passes_to_lock,
            candle_count=len(payload.candles),
            event_annotation_count=len(payload.event_annotations),
            focus_region_count=len(payload.focus_regions),
            strategy_candidate_count=len(payload.strategy_candidates),
            has_ai_briefing=payload.ai_briefing is not None,
        )

    @staticmethod
    def _build_cache_record(stored: StoredIngestion, payload: ReplayWorkbenchSnapshotPayload) -> ReplayWorkbenchCacheRecord:
        return ReplayWorkbenchCacheRecord(
            ingestion_id=stored.ingestion_id,
            replay_snapshot_id=payload.replay_snapshot_id,
            cache_key=payload.cache_key,
            stored_at=stored.stored_at,
            created_at=payload.created_at,
            instrument_symbol=payload.instrument.symbol,
            display_timeframe=payload.display_timeframe,
            window_start=payload.window_start,
            window_end=payload.window_end,
            acquisition_mode=payload.acquisition_mode,
            cache_policy=payload.cache_policy,
            verification_state=payload.verification_state,
            candle_count=len(payload.candles),
            event_annotation_count=len(payload.event_annotations),
            focus_region_count=len(payload.focus_regions),
            strategy_candidate_count=len(payload.strategy_candidates),
            has_ai_briefing=payload.ai_briefing is not None,
        )

    @staticmethod
    def _is_auto_fetch_allowed(payload: ReplayWorkbenchSnapshotPayload) -> bool:
        if payload.verification_state.status == ReplayVerificationStatus.INVALIDATED:
            return not payload.cache_policy.manual_reimport_required_after_invalidation
        if payload.cache_policy.fetch_only_when_missing:
            return False
        return True

    @staticmethod
    def _is_verification_due(payload: ReplayWorkbenchSnapshotPayload) -> bool:
        if payload.verification_state.status in {ReplayVerificationStatus.DURABLE, ReplayVerificationStatus.INVALIDATED}:
            return False
        if payload.verification_state.next_verification_due_at is None:
            return payload.verification_state.status == ReplayVerificationStatus.UNVERIFIED
        return payload.verification_state.next_verification_due_at <= datetime.now(tz=UTC)

    def _iter_matching_backfill_requests_locked(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
    ) -> list[ReplayWorkbenchAtasBackfillRecord]:
        return sorted(
            (
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and (
                    record.chart_instance_id is None
                    or (
                        self._backfill_chart_instance_matches(
                            chart_instance_id,
                            record.chart_instance_id,
                            instrument_symbol=record.instrument_symbol,
                            contract_symbol=record.contract_symbol or record.target_contract_symbol,
                            display_timeframe=record.display_timeframe,
                        )
                    )
                )
                and (
                    record.contract_symbol is None
                    or (contract_symbol is not None and record.contract_symbol == contract_symbol)
                )
                and (
                    record.root_symbol is None
                    or (root_symbol is not None and record.root_symbol == root_symbol)
                )
            ),
            key=lambda item: (item.requested_at, item.request_id),
        )

    def _find_reusable_backfill_request_locked(
        self,
        request: ReplayWorkbenchAtasBackfillRequest,
        now: datetime,
    ) -> ReplayWorkbenchAtasBackfillRecord | None:
        for record in self._backfill_requests.values():
            if record.status not in {
                ReplayWorkbenchAtasBackfillStatus.PENDING,
                ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
            }:
                continue
            if record.expires_at <= now:
                continue
            if (
                record.cache_key == request.cache_key
                and record.instrument_symbol == request.instrument_symbol
                and record.display_timeframe == request.display_timeframe
                and record.window_start == request.window_start
                and record.window_end == request.window_end
                and (
                    record.chart_instance_id == request.chart_instance_id
                    or self._backfill_chart_instance_matches(
                        request.chart_instance_id,
                        record.chart_instance_id,
                        instrument_symbol=record.instrument_symbol,
                        contract_symbol=record.contract_symbol or record.target_contract_symbol,
                        display_timeframe=record.display_timeframe,
                    )
                )
                and record.reason == request.reason
                and record.request_history_bars == request.request_history_bars
                and record.request_history_footprint == request.request_history_footprint
                and record.replace_existing_history == request.replace_existing_history
                and self._gap_segments_equal(record.missing_segments, request.missing_segments)
                and self._backfill_ranges_equal(record.requested_ranges, request.requested_ranges)
                and record.contract_symbol == request.contract_symbol
                and record.root_symbol == request.root_symbol
                and record.target_contract_symbol == request.target_contract_symbol
                and record.target_root_symbol == request.target_root_symbol
            ):
                return record
        return None

    def _expire_backfill_requests_locked(self, now: datetime) -> None:
        for request_id, record in list(self._backfill_requests.items()):
            if (
                record.status in {
                    ReplayWorkbenchAtasBackfillStatus.PENDING,
                    ReplayWorkbenchAtasBackfillStatus.DISPATCHED,
                }
                and record.expires_at <= now
            ):
                self._backfill_requests[request_id] = record.model_copy(
                    update={
                        "status": ReplayWorkbenchAtasBackfillStatus.EXPIRED,
                        "note": record.note or "expired before adapter acknowledgement",
                    }
                )
        self._prune_backfill_requests_locked(now)

    def _prune_backfill_requests_locked(self, now: datetime) -> None:
        cutoff = now - self._BACKFILL_RECORD_RETENTION
        for request_id, record in list(self._backfill_requests.items()):
            if record.requested_at < cutoff and record.status in {
                ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED,
                ReplayWorkbenchAtasBackfillStatus.EXPIRED,
            }:
                self._backfill_requests.pop(request_id, None)

    def _is_backfill_dispatchable(
        self,
        record: ReplayWorkbenchAtasBackfillRecord,
        now: datetime,
    ) -> bool:
        if record.status == ReplayWorkbenchAtasBackfillStatus.PENDING:
            return True
        if record.status != ReplayWorkbenchAtasBackfillStatus.DISPATCHED:
            return False
        if record.dispatched_at is None:
            return True
        return now - record.dispatched_at >= self._BACKFILL_DISPATCH_LEASE

    def _replace_existing_history_window(
        self,
        request: ReplayWorkbenchAtasBackfillRequest,
    ) -> None:
        contract_symbol = self._normalize_symbol_for_storage(
            request.target_contract_symbol or request.contract_symbol
        )
        root_symbol = self._normalize_symbol_for_storage(
            request.target_root_symbol or request.root_symbol or request.instrument_symbol
        )
        analysis_symbol = root_symbol or self._normalize_symbol_for_storage(request.instrument_symbol)
        raw_deleted = self._repository.delete_atas_chart_bars_raw_window(
            chart_instance_id=request.chart_instance_id,
            contract_symbol=contract_symbol,
            root_symbol=root_symbol,
            timeframe=request.display_timeframe.value,
            window_start=request.window_start,
            window_end=request.window_end,
        )
        candle_deleted = 0
        if analysis_symbol is not None:
            candle_deleted = self._repository.delete_chart_candles_window(
                symbol=analysis_symbol,
                timeframe=request.display_timeframe.value,
                window_start=request.window_start,
                window_end=request.window_end,
            )
        LOGGER.info(
            "request_atas_backfill: replace_existing_history cache_key=%s chart_instance_id=%s contract_symbol=%s root_symbol=%s timeframe=%s raw_deleted=%s candle_deleted=%s scope=%s",
            request.cache_key,
            request.chart_instance_id,
            contract_symbol,
            root_symbol,
            request.display_timeframe.value,
            raw_deleted,
            candle_deleted,
            "chart_scoped" if request.chart_instance_id else "broad_symbol_window",
        )

    def _expected_native_bar_count(
        self,
        timeframe: Timeframe,
        range_start: datetime,
        range_end: datetime,
    ) -> int:
        start = self._ensure_utc(range_start)
        end = self._ensure_utc(range_end)
        if end < start:
            return 0
        interval_minutes = max(1, self._TIMEFRAME_MINUTES.get(timeframe, 1))
        interval_seconds = interval_minutes * 60
        return int(((end - start).total_seconds()) // interval_seconds) + 1

    def _describe_backfill_progress(
        self,
        *,
        request: ReplayWorkbenchAtasBackfillRecord,
        received_bar_count: int,
        expected_bar_count: int,
        missing_bar_count: int,
        coverage_progress_percent: int,
        verification: ReplayWorkbenchAckVerification | None,
    ) -> tuple[str, bool, str, str]:
        bars_summary = f"{received_bar_count}/{expected_bar_count} 根K线" if expected_bar_count > 0 else "本次任务不要求K线回补"
        footprint_summary = (
            " · footprint已确认"
            if request.request_history_footprint and request.acknowledged_history_footprint
            else (" · footprint待确认" if request.request_history_footprint else "")
        )
        chart_summary = (
            f"chart_instance_id={request.chart_instance_id}"
            if request.chart_instance_id
            else "未绑定特定图表实例"
        )
        if verification is not None and verification.verified:
            return (
                "complete",
                False,
                "ATAS 历史回传完成",
                f"{bars_summary} 已落库并通过核对{footprint_summary} · {chart_summary}",
            )
        if request.status == ReplayWorkbenchAtasBackfillStatus.EXPIRED:
            return (
                "expired",
                False,
                "ATAS 回补任务已过期",
                f"{bars_summary} · 仍缺 {missing_bar_count} 根K线{footprint_summary} · {chart_summary}",
            )
        if request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED and (
            (request.request_history_bars and not request.acknowledged_history_bars)
            or (
                request.request_history_footprint
                and not request.acknowledged_history_footprint
                and not request.acknowledged_history_bars
            )
        ):
            adapter_note = request.note or "adapter acknowledged without resending requested history"
            return (
                "failed",
                False,
                "ATAS 已回执，但这次回补没有真正成功",
                f"{bars_summary} · 仍缺 {missing_bar_count} 根K线 · {adapter_note}{footprint_summary} · {chart_summary}",
            )
        if request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED:
            verification_detail = (
                verification.note
                if verification is not None and verification.note
                else (f"仍缺 {missing_bar_count} 根K线" if missing_bar_count > 0 else "等待后端最终核对")
            )
            return (
                "verifying",
                True,
                "ATAS 已回执，后端正在核对",
                f"{bars_summary} · 覆盖 {coverage_progress_percent}% · {verification_detail}{footprint_summary} · {chart_summary}",
            )
        if request.status == ReplayWorkbenchAtasBackfillStatus.DISPATCHED:
            if received_bar_count > 0:
                return (
                    "receiving",
                    True,
                    "ATAS 正在回传历史K线",
                    f"{bars_summary} · 覆盖 {coverage_progress_percent}%{footprint_summary} · {chart_summary}",
                )
            return (
                "receiving",
                True,
                "ATAS 已领取任务，等待首批历史K线",
                f"{bars_summary}{footprint_summary} · {chart_summary}",
            )
        return (
            "pending",
            True,
            "回补任务已排队，等待 ATAS 领取",
            f"{bars_summary}{footprint_summary} · {chart_summary}",
        )

    @staticmethod
    def _build_backfill_command(record: ReplayWorkbenchAtasBackfillRecord) -> AdapterBackfillCommand:
        dispatched_at = record.dispatched_at or datetime.now(tz=UTC)
        return AdapterBackfillCommand(
            request_id=record.request_id,
            cache_key=record.cache_key,
            instrument_symbol=record.instrument_symbol,
            contract_symbol=record.contract_symbol,
            root_symbol=record.root_symbol,
            target_contract_symbol=record.target_contract_symbol,
            target_root_symbol=record.target_root_symbol,
            display_timeframe=record.display_timeframe,
            window_start=record.window_start,
            window_end=record.window_end,
            chart_instance_id=record.chart_instance_id,
            missing_segments=record.missing_segments,
            requested_ranges=record.requested_ranges,
            reason=record.reason,
            request_history_bars=record.request_history_bars,
            request_history_footprint=record.request_history_footprint,
            replace_existing_history=record.replace_existing_history,
            dispatch_count=record.dispatch_count,
            requested_at=record.requested_at,
            dispatched_at=dispatched_at,
        )

    @staticmethod
    def _normalize_symbol_for_storage(value: str | None) -> str | None:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _build_history_inventory_cache_key(
        *,
        instrument_symbol: str,
        chart_instance_id: str | None,
        contract_symbol: str | None,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
    ) -> str:
        scope = chart_instance_id or contract_symbol or instrument_symbol
        return (
            f"auto-history-inventory:{scope}:{timeframe.value}:"
            f"{window_start.astimezone(UTC).isoformat()}:{window_end.astimezone(UTC).isoformat()}"
        )

    @staticmethod
    def _gap_segments_equal(left: list[Any], right: list[Any]) -> bool:
        if len(left) != len(right):
            return False

        def _normalize(segment: Any) -> tuple[Any, Any, int]:
            prev_ended_at = getattr(segment, "prev_ended_at", None)
            next_started_at = getattr(segment, "next_started_at", None)
            missing_bar_count = getattr(segment, "missing_bar_count", None)
            return prev_ended_at, next_started_at, int(missing_bar_count or 0)

        return [_normalize(item) for item in left] == [_normalize(item) for item in right]

    @staticmethod
    def _backfill_ranges_equal(left: list[Any], right: list[Any]) -> bool:
        if len(left) != len(right):
            return False

        def _normalize(item: Any) -> tuple[Any, Any]:
            range_start = getattr(item, "range_start", None)
            range_end = getattr(item, "range_end", None)
            return range_start, range_end

        return [_normalize(item) for item in left] == [_normalize(item) for item in right]

    def _bucket_start(self, value: datetime, timeframe: Timeframe) -> datetime:
        value = value.astimezone(UTC)
        if timeframe == Timeframe.DAY_1:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes = self._TIMEFRAME_MINUTES[timeframe]
        if minutes >= 60:
            hour_bucket = (value.hour // (minutes // 60)) * (minutes // 60)
            return value.replace(hour=hour_bucket, minute=0, second=0, microsecond=0)
        minute_bucket = (value.minute // minutes) * minutes
        return value.replace(minute=minute_bucket, second=0, microsecond=0)
