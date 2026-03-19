from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterBackfillCommand,
    AdapterBackfillDispatchResponse,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintBar,
    AdapterHistoryFootprintPayload,
    AdapterInitiativeDriveState,
    AdapterPostHarvestResponseState,
    AdapterSamePriceReplenishmentState,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
    ReplayAcquisitionMode,
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
    ReplayWorkbenchAtasBackfillAcceptedResponse,
    ReplayWorkbenchAtasBackfillRecord,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchAtasBackfillStatus,
    ReplayWorkbenchBuildAction,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchCacheRecord,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
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
    StructureSide,
    Timeframe,
)
from atas_market_structure.repository import AnalysisRepository, StoredIngestion
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine


class ReplayWorkbenchNotFoundError(RuntimeError):
    """Raised when a requested replay cache record does not exist."""


def payload_to_model(payload: Any, model_type):
    if payload is None:
        return None
    return model_type.model_validate(payload)


class ReplayWorkbenchService:
    """Stores replay-workbench packets and builds replay snapshots from local adapter history."""

    _TIMEFRAME_MINUTES: dict[Timeframe, int] = {
        Timeframe.MIN_1: 1,
        Timeframe.MIN_5: 5,
        Timeframe.MIN_15: 15,
        Timeframe.MIN_30: 30,
        Timeframe.HOUR_1: 60,
        Timeframe.DAY_1: 1440,
    }

    # Defensive limit: never insert an unbounded amount of synthetic filler bars.
    # (UI would choke, and it usually indicates upstream history coverage issues.)
    _MAX_GAP_FILL_BARS: int = 600
    _BACKFILL_REQUEST_TTL = timedelta(minutes=5)
    _BACKFILL_DISPATCH_LEASE = timedelta(seconds=12)
    _BACKFILL_RECORD_RETENTION = timedelta(hours=2)

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository
        self._backfill_lock = Lock()
        self._backfill_requests: dict[str, ReplayWorkbenchAtasBackfillRecord] = {}

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
        # Pull enough recent continuous-state messages to build `lookback_bars` candles.
        # Repository only supports "latest N" so we oversample and filter by time cutoff.
        timeframe_minutes = self._TIMEFRAME_MINUTES.get(display_timeframe, 1)
        required_minutes = (timeframe_minutes * max(lookback_bars, 2)) + 3
        estimated_messages_per_minute = 6  # ~10s cadence (tune if adapter cadence changes)
        candidates_limit = int(required_minutes * estimated_messages_per_minute * 3)
        candidates_limit = max(5000, min(50000, candidates_limit))

        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=instrument_symbol,
            limit=candidates_limit,
        )
        matched: list[tuple[datetime, StoredIngestion]] = []
        latest_payload: dict[str, Any] | None = None
        latest_observed_at: datetime | None = None
        for stored in candidates:
            payload = stored.observed_payload
            if chart_instance_id is not None and payload.get("source", {}).get("chart_instance_id") != chart_instance_id:
                continue
            observed_at = self._payload_observed_at(payload)
            matched.append((observed_at, stored))
            if latest_observed_at is None or observed_at > latest_observed_at:
                latest_observed_at = observed_at
                latest_payload = payload

        if latest_observed_at is None or latest_payload is None:
            return ReplayWorkbenchLiveTailResponse(
                instrument_symbol=instrument_symbol,
                display_timeframe=display_timeframe,
                latest_observed_at=None,
                latest_price=None,
                best_bid=None,
                best_ask=None,
                source_message_count=0,
                candles=[],
                trade_summary=None,
                significant_liquidity=[],
                same_price_replenishment=[],
                active_initiative_drive=None,
                active_post_harvest_response=None,
            )

        recent_cutoff = latest_observed_at - timedelta(
            minutes=(self._TIMEFRAME_MINUTES.get(display_timeframe, 1) * max(lookback_bars, 2)) + 1
        )
        recent_messages = [stored for observed_at, stored in matched if observed_at >= recent_cutoff]
        recent_messages.sort(key=lambda item: self._payload_observed_at(item.observed_payload))
        live_candles = self._build_candles(display_timeframe, recent_messages)[-max(lookback_bars, 1):]

        # --- auto gap-fill: patch holes in live candles using history-bars ---
        live_candles = self._patch_live_candle_gaps(
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            chart_instance_id=chart_instance_id,
            candles=live_candles,
        )

        # --- still expose remaining gaps as explicit synthetic bars (so UI can see missing time) ---
        live_candles, _, _ = self._fill_candle_time_gaps(live_candles, display_timeframe)

        price_state = latest_payload.get("price_state", {})
        return ReplayWorkbenchLiveTailResponse(
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            latest_observed_at=latest_observed_at,
            latest_price=price_state.get("last_price"),
            best_bid=price_state.get("best_bid"),
            best_ask=price_state.get("best_ask"),
            source_message_count=len(recent_messages),
            candles=live_candles,
            trade_summary=payload_to_model(latest_payload.get("trade_summary"), AdapterTradeSummary),
            significant_liquidity=[
                model
                for model in (
                    payload_to_model(item, AdapterSignificantLiquidityLevel)
                    for item in latest_payload.get("significant_liquidity", [])
                )
                if model is not None
            ],
            same_price_replenishment=[
                model
                for model in (
                    payload_to_model(item, AdapterSamePriceReplenishmentState)
                    for item in latest_payload.get("same_price_replenishment", [])
                )
                if model is not None
            ],
            active_initiative_drive=payload_to_model(
                latest_payload.get("active_initiative_drive"),
                AdapterInitiativeDriveState,
            ),
            active_post_harvest_response=payload_to_model(
                latest_payload.get("active_post_harvest_response"),
                AdapterPostHarvestResponseState,
            ),
        )

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
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            reusable = self._find_reusable_backfill_request_locked(request, now)
            if reusable is not None:
                return ReplayWorkbenchAtasBackfillAcceptedResponse(
                    request=reusable,
                    reused_existing_request=True,
                )

            record = ReplayWorkbenchAtasBackfillRecord(
                request_id=f"atas-backfill-{uuid4().hex}",
                cache_key=request.cache_key,
                instrument_symbol=request.instrument_symbol,
                display_timeframe=request.display_timeframe,
                window_start=request.window_start,
                window_end=request.window_end,
                chart_instance_id=request.chart_instance_id,
                missing_segments=request.missing_segments,
                reason=request.reason,
                request_history_bars=request.request_history_bars,
                request_history_footprint=request.request_history_footprint,
                status=ReplayWorkbenchAtasBackfillStatus.PENDING,
                requested_at=now,
                expires_at=now + self._BACKFILL_REQUEST_TTL,
                dispatch_count=0,
            )
            self._backfill_requests[record.request_id] = record
            self._prune_backfill_requests_locked(now)
            return ReplayWorkbenchAtasBackfillAcceptedResponse(
                request=record,
                reused_existing_request=False,
            )

    def poll_atas_backfill(
        self,
        *,
        instrument_symbol: str,
        chart_instance_id: str | None = None,
    ) -> AdapterBackfillDispatchResponse:
        now = datetime.now(tz=UTC)
        with self._backfill_lock:
            self._expire_backfill_requests_locked(now)
            for record in self._iter_matching_backfill_requests_locked(
                instrument_symbol=instrument_symbol,
                chart_instance_id=chart_instance_id,
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
        with self._backfill_lock:
            record = self._backfill_requests.get(request.request_id)
            if record is None:
                raise ReplayWorkbenchNotFoundError(
                    f"ATAS backfill request '{request.request_id}' not found."
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
            self._prune_backfill_requests_locked(request.acknowledged_at)
            return AdapterBackfillAcknowledgeResponse(request=updated)

    def build_replay_snapshot(self, request: ReplayWorkbenchBuildRequest) -> ReplayWorkbenchBuildResponse:
        history_payload = self._find_matching_history_payload(request)
        footprint_payloads = self._find_matching_history_footprint_payloads(request)
        cache = self.get_cache_record(request.cache_key)
        if not request.force_rebuild and cache.record is not None and cache.record.verification_state.status != ReplayVerificationStatus.INVALIDATED:
            cached_ingestion = self._repository.get_ingestion(cache.record.ingestion_id)
            if cached_ingestion is not None and not self._history_snapshot_should_refresh(request, cached_ingestion, history_payload):
                payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
                return ReplayWorkbenchBuildResponse(
                    action=ReplayWorkbenchBuildAction.CACHE_HIT,
                    cache_key=request.cache_key,
                    reason="Replay cache already exists and is still eligible for reuse.",
                    local_message_count=0,
                    replay_snapshot_id=payload.replay_snapshot_id,
                    ingestion_id=cache.record.ingestion_id,
                    summary=self._build_summary(payload),
                    cache_record=cache.record,
                    atas_fetch_request=None,
                )

        continuous_messages = self._collect_matching_continuous_messages(request)
        if history_payload is not None:
            payload = self._build_snapshot_from_history_bars(
                request,
                history_payload,
                continuous_messages,
                footprint_payloads,
            )
            accepted = self.ingest_replay_snapshot(payload)
            cache_after = self.get_cache_record(request.cache_key)
            return ReplayWorkbenchBuildResponse(
                action=ReplayWorkbenchBuildAction.BUILT_FROM_ATAS_HISTORY,
                cache_key=request.cache_key,
                reason="Replay packet rebuilt from ATAS chart-loaded history bars.",
                local_message_count=len(continuous_messages),
                replay_snapshot_id=accepted.replay_snapshot_id,
                ingestion_id=accepted.ingestion_id,
                summary=accepted.summary,
                cache_record=cache_after.record,
                atas_fetch_request=None,
            )

        if len(continuous_messages) < request.min_continuous_messages:
            return ReplayWorkbenchBuildResponse(
                action=ReplayWorkbenchBuildAction.ATAS_FETCH_REQUIRED,
                cache_key=request.cache_key,
                reason="Local adapter history is insufficient for this replay window.",
                local_message_count=len(continuous_messages),
                replay_snapshot_id=None,
                ingestion_id=None,
                summary=None,
                cache_record=cache.record,
                atas_fetch_request={
                    "instrument_symbol": request.instrument_symbol,
                    "display_timeframe": request.display_timeframe,
                    "window_start": request.window_start,
                    "window_end": request.window_end,
                    "chart_instance_id": None,
                    "fetch_only_when_missing": True,
                },
            )

        payload = self._build_snapshot_from_local_history(request, continuous_messages)
        accepted = self.ingest_replay_snapshot(payload)
        cache_after = self.get_cache_record(request.cache_key)
        return ReplayWorkbenchBuildResponse(
            action=ReplayWorkbenchBuildAction.BUILT_FROM_LOCAL_HISTORY,
            cache_key=request.cache_key,
            reason="Replay packet rebuilt from locally stored adapter history.",
            local_message_count=len(continuous_messages),
            replay_snapshot_id=accepted.replay_snapshot_id,
            ingestion_id=accepted.ingestion_id,
            summary=accepted.summary,
            cache_record=cache_after.record,
            atas_fetch_request=None,
        )

    def _build_snapshot_from_history_bars(
        self,
        request: ReplayWorkbenchBuildRequest,
        history_payload: AdapterHistoryBarsPayload,
        continuous_messages: list[StoredIngestion],
        footprint_payloads: list[AdapterHistoryFootprintPayload],
    ) -> ReplayWorkbenchSnapshotPayload:
        created_at = datetime.now(tz=UTC)
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        candles = self._build_candles_from_history_payload(history_payload, request)
        if not candles:
            return self._build_snapshot_from_local_history(request, continuous_messages)
        continuous_overlay_count = 0
        if continuous_messages:
            candles, continuous_overlay_count = self._merge_history_candles_with_continuous_overlay(
                history_candles=candles,
                continuous_messages=continuous_messages,
                timeframe=request.display_timeframe,
            )

        # Detect + fill any remaining candle gaps so the UI does not silently compress missing time.
        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)

        actual_window_start = candles[0].started_at
        actual_window_end = candles[-1].ended_at
        event_annotations = self._build_event_annotations(continuous_messages) if continuous_messages else []
        focus_regions = self._build_focus_regions(continuous_messages, event_annotations) if continuous_messages else []
        if footprint_payloads:
            event_annotations.extend(self._build_footprint_event_annotations(footprint_payloads, history_payload.instrument.tick_size, request))
            focus_regions.extend(self._build_footprint_focus_regions(footprint_payloads, history_payload.instrument.tick_size, request))
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)
        footprint_digest = self._build_footprint_digest(footprint_payloads, request) if footprint_payloads else None

        return ReplayWorkbenchSnapshotPayload(
            schema_version="1.1.0",
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
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": "adapter_history_bars",
                "history_message_id": history_payload.message_id,
                "history_bar_timeframe": history_payload.bar_timeframe,
                "history_bar_count": len(history_payload.bars),
                "history_coverage_start": history_payload.observed_window_start,
                "history_coverage_end": history_payload.observed_window_end,
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

        entries: list[ReplayOperatorEntryRecord] = []
        for stored in self._repository.list_ingestions(ingestion_kind="replay_operator_entry", limit=1000):
            if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                continue
            entries.append(ReplayOperatorEntryRecord.model_validate(stored.observed_payload))
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

        regions: list[ReplayManualRegionAnnotationRecord] = []
        for stored in self._repository.list_ingestions(ingestion_kind="replay_manual_region", limit=1000):
            if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                continue
            regions.append(ReplayManualRegionAnnotationRecord.model_validate(stored.observed_payload))
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
        first_payload = ingestions[0].observed_payload
        last_payload = ingestions[-1].observed_payload
        replay_snapshot_id = f"replay-{request.instrument_symbol.lower()}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"

        candles = self._build_candles(request.display_timeframe, ingestions)
        candles, candle_gaps, gap_fill_bar_count = self._fill_candle_time_gaps(candles, request.display_timeframe)
        actual_window_start = candles[0].started_at if candles else request.window_start
        actual_window_end = candles[-1].ended_at if candles else request.window_end
        event_annotations = self._build_event_annotations(ingestions)
        focus_regions = self._build_focus_regions(ingestions, event_annotations)
        strategy_candidates = self._build_strategy_candidates(event_annotations)
        ai_briefing = self._build_ai_briefing(request.instrument_symbol, strategy_candidates, focus_regions)

        return ReplayWorkbenchSnapshotPayload(
            schema_version="1.1.0",
            replay_snapshot_id=replay_snapshot_id,
            cache_key=request.cache_key,
            acquisition_mode=ReplayAcquisitionMode.CACHE_REUSE,
            created_at=created_at,
            source=last_payload["source"],
            instrument=last_payload["instrument"],
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
            candles=candles,
            event_annotations=event_annotations,
            focus_regions=focus_regions,
            strategy_candidates=strategy_candidates,
            ai_briefing=ai_briefing,
            raw_features={
                "history_source": "adapter_continuous_state",
                "local_message_count": len(ingestions),
                "chart_instance_id": request.chart_instance_id or last_payload["source"].get("chart_instance_id"),
                "build_reason": "cache_miss_local_history_rebuild",
                "first_message_id": first_payload["message_id"],
                "last_message_id": last_payload["message_id"],
                "requested_window_start": request.window_start,
                "requested_window_end": request.window_end,
                "actual_window_start": actual_window_start,
                "actual_window_end": actual_window_end,
                "candle_gap_count": len(candle_gaps),
                "candle_gap_missing_bar_count": sum(item["missing_bar_count"] for item in candle_gaps),
                "candle_gap_fill_bar_count": gap_fill_bar_count,
                "candle_gaps": candle_gaps,
            },
        )

    def _collect_matching_continuous_messages(self, request: ReplayWorkbenchBuildRequest) -> list[StoredIngestion]:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol=request.instrument_symbol,
            limit=10000,
        )
        matched: list[StoredIngestion] = []
        for stored in candidates:
            payload = stored.observed_payload
            if request.chart_instance_id is not None and payload.get("source", {}).get("chart_instance_id") != request.chart_instance_id:
                continue
            window_start = datetime.fromisoformat(payload["observed_window_start"])
            window_end = datetime.fromisoformat(payload["observed_window_end"])
            if window_end < request.window_start or window_start > request.window_end:
                continue
            matched.append(stored)
        matched.sort(key=lambda item: item.observed_payload["emitted_at"])
        return matched

    def _find_matching_history_payload(self, request: ReplayWorkbenchBuildRequest) -> AdapterHistoryBarsPayload | None:
        candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=request.instrument_symbol,
            limit=200,
        )
        matched_payloads: list[tuple[float, float, int, int, AdapterHistoryBarsPayload]] = []
        for stored in candidates:
            payload = AdapterHistoryBarsPayload.model_validate(stored.observed_payload)
            if request.chart_instance_id is not None and payload.source.chart_instance_id != request.chart_instance_id:
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
            requested_seconds = max((request.window_end - request.window_start).total_seconds(), 1.0)
            coverage_ratio = overlap_seconds / requested_seconds
            matched_payloads.append(
                (
                    coverage_ratio,
                    overlap_seconds,
                    len(payload.bars),
                    -self._TIMEFRAME_MINUTES.get(payload.bar_timeframe, 0),
                    payload,
                )
            )

        if not matched_payloads:
            return None

        matched_payloads.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return matched_payloads[0][4]

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

    @staticmethod
    def _payload_observed_at(payload: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(payload.get("observed_window_end") or payload["emitted_at"])

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

        # Find the best history-bars payload covering the gap
        history_candidates = self._repository.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=instrument_symbol,
            limit=50,
        )
        best_payload: AdapterHistoryBarsPayload | None = None
        best_overlap = 0.0
        for stored in history_candidates:
            payload = AdapterHistoryBarsPayload.model_validate(stored.observed_payload)
            if chart_instance_id is not None and payload.source.chart_instance_id != chart_instance_id:
                continue
            if not self._can_build_timeframe_from_history(payload.bar_timeframe, display_timeframe):
                continue
            overlap = self._overlap_seconds(
                payload.observed_window_start,
                payload.observed_window_end,
                gap_window_start,
                gap_window_end,
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_payload = payload

        if best_payload is None:
            return candles

        # Build filler candles from history-bars for the gap region
        filler_request = ReplayWorkbenchBuildRequest(
            cache_key="__gap_fill_internal__",
            instrument_symbol=instrument_symbol,
            display_timeframe=display_timeframe,
            window_start=gap_window_start,
            window_end=gap_window_end,
        )
        filler_candles = self._build_candles_from_history_payload(best_payload, filler_request)
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

        continuous_candles = self._build_candles(timeframe, continuous_messages)
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
            emitted_at = datetime.fromisoformat(payload["emitted_at"])
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
                    observed_at=datetime.fromisoformat(item["last_observed_at"]),
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
                    observed_at=datetime.fromisoformat(drive["started_at"]),
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
                    observed_at=datetime.fromisoformat(gap["first_touch_at"] or gap["opened_at"]),
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
                    observed_at=datetime.fromisoformat(post_harvest["harvest_completed_at"]),
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
                    started_at=datetime.fromisoformat(item["first_observed_at"]),
                    ended_at=datetime.fromisoformat(item["last_observed_at"]),
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
                    started_at=datetime.fromisoformat(zone["started_at"]),
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
            if chart_instance_id is not None and payload.source.chart_instance_id != chart_instance_id:
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
        history_payload: AdapterHistoryBarsPayload | None,
    ) -> bool:
        if history_payload is None:
            return False
        cached_payload = ReplayWorkbenchSnapshotPayload.model_validate(cached_ingestion.observed_payload)
        if cached_payload.display_timeframe != request.display_timeframe:
            return True
        estimated_count = self._estimate_history_candle_count(history_payload, request)
        cached_count = len(cached_payload.candles)
        if estimated_count > max(cached_count + 50, int(cached_count * 1.2)):
            return True
        cached_history_message_id = cached_payload.raw_features.get("history_message_id")
        if cached_history_message_id != history_payload.message_id:
            cached_actual_end = cached_payload.raw_features.get("actual_window_end")
            if cached_actual_end is None:
                return True
            try:
                cached_actual_end_dt = datetime.fromisoformat(str(cached_actual_end).replace("Z", "+00:00"))
            except ValueError:
                return True
            if history_payload.observed_window_end > cached_actual_end_dt:
                return True
        return False

    def _estimate_history_candle_count(
        self,
        payload: AdapterHistoryBarsPayload,
        request: ReplayWorkbenchBuildRequest,
    ) -> int:
        filtered_bars = [
            bar for bar in payload.bars if bar.ended_at >= request.window_start and bar.started_at <= request.window_end
        ]
        if not filtered_bars:
            return 0
        if payload.bar_timeframe == request.display_timeframe:
            return len(filtered_bars)
        source_minutes = self._TIMEFRAME_MINUTES[payload.bar_timeframe]
        target_minutes = self._TIMEFRAME_MINUTES[request.display_timeframe]
        if target_minutes <= source_minutes:
            return len(filtered_bars)
        buckets = {self._bucket_start(bar.started_at, request.display_timeframe) for bar in filtered_bars}
        return len(buckets)

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
    ) -> list[ReplayWorkbenchAtasBackfillRecord]:
        return sorted(
            (
                record
                for record in self._backfill_requests.values()
                if record.instrument_symbol == instrument_symbol
                and (
                    record.chart_instance_id is None
                    or (
                        chart_instance_id is not None
                        and record.chart_instance_id == chart_instance_id
                    )
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
                and record.chart_instance_id == request.chart_instance_id
                and record.reason == request.reason
                and record.request_history_bars == request.request_history_bars
                and record.request_history_footprint == request.request_history_footprint
                and self._gap_segments_equal(record.missing_segments, request.missing_segments)
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

    @staticmethod
    def _build_backfill_command(record: ReplayWorkbenchAtasBackfillRecord) -> AdapterBackfillCommand:
        dispatched_at = record.dispatched_at or datetime.now(tz=UTC)
        return AdapterBackfillCommand(
            request_id=record.request_id,
            cache_key=record.cache_key,
            instrument_symbol=record.instrument_symbol,
            display_timeframe=record.display_timeframe,
            window_start=record.window_start,
            window_end=record.window_end,
            chart_instance_id=record.chart_instance_id,
            missing_segments=record.missing_segments,
            reason=record.reason,
            request_history_bars=record.request_history_bars,
            request_history_footprint=record.request_history_footprint,
            dispatch_count=record.dispatch_count,
            requested_at=record.requested_at,
            dispatched_at=dispatched_at,
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
