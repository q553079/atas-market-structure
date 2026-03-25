from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from atas_market_structure.models import (
    ChartCandle,
    EventCandidateKind,
    EventOutcomeLedger,
    EventOutcomeListEnvelope,
    EventOutcomeQuery,
    EventOutcomeResult,
    EventStatsBreakdownBucket,
    EventStatsBreakdownEnvelope,
    EventStatsQuery,
    EventStatsSummary,
    EventStatsSummaryEnvelope,
)
from atas_market_structure.models._schema_versions import EVENT_OUTCOME_LEDGER_SCHEMA_VERSION
from atas_market_structure.profile_services import default_tick_size_for_symbol
from atas_market_structure.repository import AnalysisRepository, StoredEventCandidate, StoredEventOutcomeLedger, StoredPromptTrace
from atas_market_structure.workbench_common import ReplayWorkbenchNotFoundError
from atas_market_structure.workbench_event_outcome_support import (
    OutcomeSpec,
    SettlementSnapshot,
    coerce_float,
    coerce_int,
    normalize_side,
    normalize_timeframe,
    opposite_side,
    parse_datetime,
    safe_rate,
)


class ReplayWorkbenchEventOutcomeService:
    """Deterministic, workbench-scoped outcome settlement for EventCandidate rows."""

    _SUPPORTED_EVENT_KINDS = {
        EventCandidateKind.KEY_LEVEL.value,
        EventCandidateKind.PRICE_ZONE.value,
        EventCandidateKind.MARKET_EVENT.value,
        EventCandidateKind.PLAN_INTENT.value,
    }
    _TIMEFRAME_SECONDS = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    _DEFAULT_EVALUATION_BARS = 30

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def list_event_outcomes(self, query: EventOutcomeQuery) -> EventOutcomeListEnvelope:
        """Refresh and list outcome-ledger rows for one workbench session."""

        outcomes = self._refresh_session_outcomes(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=normalize_timeframe(query.timeframe),
            limit=query.limit,
        )
        filtered = self._filter_outcomes(
            outcomes,
            event_id=query.event_id,
            event_kind=query.event_kind,
            realized_outcome=query.realized_outcome.value if isinstance(query.realized_outcome, EventOutcomeResult) else query.realized_outcome,
        )
        return EventOutcomeListEnvelope(
            query=query,
            outcomes=[self._outcome_model(item) for item in filtered[: query.limit]],
        )

    def get_event_stats_summary(self, query: EventStatsQuery) -> EventStatsSummaryEnvelope:
        """Return summary accuracy metrics for settled workbench event outcomes."""

        outcomes = self._refresh_session_outcomes(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=normalize_timeframe(query.timeframe),
            limit=query.limit,
        )
        return EventStatsSummaryEnvelope(
            query=query,
            summary=self._build_summary(outcomes),
        )

    def get_event_stats_breakdown(self, query: EventStatsQuery, *, dimension: str) -> EventStatsBreakdownEnvelope:
        """Return bucketed accuracy metrics for one stable breakdown dimension."""

        outcomes = self._refresh_session_outcomes(
            session_id=query.session_id,
            symbol=query.symbol,
            timeframe=normalize_timeframe(query.timeframe),
            limit=query.limit,
        )
        return EventStatsBreakdownEnvelope(
            query=query,
            dimension=dimension,
            buckets=self._build_breakdown(outcomes, dimension=dimension),
        )

    def _refresh_session_outcomes(
        self,
        *,
        session_id: str,
        symbol: str | None,
        timeframe: str | None,
        limit: int,
    ) -> list[StoredEventOutcomeLedger]:
        session = self._require_session(session_id)
        now = datetime.now(tz=UTC)
        trace_cache: dict[str, StoredPromptTrace | None] = {}
        candidates = self._repository.list_event_candidates_by_session(
            session_id=session.session_id,
            symbol=symbol,
            timeframe=timeframe,
            limit=max(limit, 500),
        )
        for candidate in candidates:
            if candidate.candidate_kind not in self._SUPPORTED_EVENT_KINDS:
                continue
            self._refresh_outcome_for_candidate(candidate, evaluated_at=now, trace_cache=trace_cache)
        return self._repository.list_event_outcomes(
            session_id=session.session_id,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

    def _refresh_outcome_for_candidate(
        self,
        candidate: StoredEventCandidate,
        *,
        evaluated_at: datetime,
        trace_cache: dict[str, StoredPromptTrace | None],
    ) -> StoredEventOutcomeLedger:
        existing = self._repository.get_event_outcome_by_event(candidate.event_id)
        prompt_trace = self._resolve_prompt_trace(candidate, trace_cache=trace_cache)
        spec = self._build_outcome_spec(candidate)
        settlement = self._settle_outcome(candidate, spec, evaluated_at=evaluated_at)
        metadata = dict(settlement.metadata)
        metadata.update(
            {
                "candidate_lifecycle_state": candidate.lifecycle_state,
                "candidate_updated_at": candidate.updated_at.isoformat(),
            }
        )
        if prompt_trace is not None:
            metadata["prompt_trace_snapshot_present"] = bool(prompt_trace.snapshot)
        analysis_preset = self._extract_analysis_preset(prompt_trace)
        model_name = self._extract_model_name(prompt_trace)
        created_at = existing.created_at if existing is not None else evaluated_at
        return self._repository.save_event_outcome(
            outcome_id=existing.outcome_id if existing is not None else f"out-{candidate.event_id}",
            event_id=candidate.event_id,
            session_id=candidate.session_id,
            source_message_id=candidate.source_message_id,
            source_prompt_trace_id=candidate.source_prompt_trace_id or getattr(prompt_trace, "prompt_trace_id", None),
            analysis_preset=analysis_preset,
            model_name=model_name,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            event_kind=candidate.candidate_kind,
            born_at=candidate.created_at,
            observed_price=settlement.observed_price,
            target_rule=settlement.target_rule,
            invalidation_rule=settlement.invalidation_rule,
            evaluation_window_start=spec.evaluation_window_start,
            evaluation_window_end=spec.evaluation_window_end,
            expiry_policy=spec.expiry_policy,
            realized_outcome=settlement.realized_outcome.value if settlement.realized_outcome is not None else None,
            outcome_label=settlement.outcome_label,
            mfe=settlement.mfe,
            mae=settlement.mae,
            hit_target=settlement.hit_target,
            hit_stop=settlement.hit_stop,
            timed_out=settlement.timed_out,
            inconclusive=settlement.inconclusive,
            evaluated_at=settlement.evaluated_at,
            metadata=metadata,
            created_at=created_at,
            updated_at=evaluated_at,
        )

    def _build_outcome_spec(self, candidate: StoredEventCandidate) -> OutcomeSpec:
        tick_size = self._tick_size(candidate.symbol)
        side_hint = self._infer_side_hint(candidate)
        window_start, window_end, expiry_policy = self._resolve_evaluation_window(candidate)
        observed_price = coerce_float(
            candidate.price_ref
            if candidate.price_ref is not None
            else candidate.metadata.get("entry_price")
        )
        target_price = self._extract_target_price(candidate)
        stop_price = self._extract_stop_price(candidate)
        metadata: dict[str, Any] = {
            "rule_source": "event_outcome_ledger_v1",
            "candidate_kind": candidate.candidate_kind,
        }
        if candidate.candidate_kind == EventCandidateKind.PRICE_ZONE.value:
            zone_width = self._zone_width(candidate, tick_size=tick_size)
            target_distance = max(zone_width, tick_size * 8.0)
            stop_distance = max(tick_size * 4.0, zone_width * 0.5)
            if stop_price is None and observed_price is not None and side_hint in {"buy", "sell"}:
                if side_hint == "buy":
                    stop_price = (candidate.price_lower or observed_price) - tick_size * 2.0
                else:
                    stop_price = (candidate.price_upper or observed_price) + tick_size * 2.0
            return OutcomeSpec(
                observed_price=observed_price if observed_price is not None else self._zone_midpoint(candidate),
                side_hint=side_hint,
                target_price=target_price,
                stop_price=stop_price,
                target_distance=target_distance,
                stop_distance=stop_distance,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                expiry_policy=expiry_policy,
                target_rule={
                    "type": "zone_reaction",
                    "price": target_price,
                    "distance": target_distance,
                    "side": side_hint,
                },
                invalidation_rule={
                    "type": "zone_break",
                    "price": stop_price,
                    "distance": stop_distance,
                    "side": side_hint,
                },
                metadata=metadata,
            )
        if candidate.candidate_kind == EventCandidateKind.MARKET_EVENT.value:
            return OutcomeSpec(
                observed_price=observed_price,
                side_hint=side_hint,
                target_price=target_price,
                stop_price=stop_price,
                target_distance=max(tick_size * 12.0, tick_size * 8.0),
                stop_distance=max(tick_size * 8.0, tick_size * 4.0),
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                expiry_policy=expiry_policy,
                target_rule={
                    "type": "market_event_follow_through",
                    "price": target_price,
                    "distance": max(tick_size * 12.0, tick_size * 8.0),
                    "side": side_hint,
                },
                invalidation_rule={
                    "type": "market_event_failure",
                    "price": stop_price,
                    "distance": max(tick_size * 8.0, tick_size * 4.0),
                    "side": side_hint,
                },
                metadata=metadata,
            )
        if candidate.candidate_kind == EventCandidateKind.PLAN_INTENT.value:
            stop_distance = max(tick_size * 6.0, tick_size * 4.0)
            target_distance = max(tick_size * 8.0, stop_distance * 1.5)
            return OutcomeSpec(
                observed_price=observed_price if observed_price is not None else self._zone_midpoint(candidate),
                side_hint=side_hint,
                target_price=target_price,
                stop_price=stop_price,
                target_distance=target_distance,
                stop_distance=stop_distance,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                expiry_policy=expiry_policy,
                target_rule={
                    "type": "plan_target",
                    "price": target_price,
                    "distance": target_distance,
                    "side": side_hint,
                },
                invalidation_rule={
                    "type": "plan_stop",
                    "price": stop_price,
                    "distance": stop_distance,
                    "side": side_hint,
                },
                metadata=metadata,
            )
        stop_distance = max(tick_size * 6.0, tick_size * 4.0)
        target_distance = max(tick_size * 8.0, stop_distance * 1.5)
        return OutcomeSpec(
            observed_price=observed_price,
            side_hint=side_hint,
            target_price=target_price,
            stop_price=stop_price,
            target_distance=target_distance,
            stop_distance=stop_distance,
            evaluation_window_start=window_start,
            evaluation_window_end=window_end,
            expiry_policy=expiry_policy,
            target_rule={
                "type": "key_level_reaction",
                "price": target_price,
                "distance": target_distance,
                "side": side_hint,
            },
            invalidation_rule={
                "type": "key_level_invalidation",
                "price": stop_price,
                "distance": stop_distance,
                "side": side_hint,
            },
            metadata=metadata,
        )

    def _settle_outcome(
        self,
        candidate: StoredEventCandidate,
        spec: OutcomeSpec,
        *,
        evaluated_at: datetime,
    ) -> SettlementSnapshot:
        candles = sorted(
            self._repository.list_chart_candles(
                symbol=candidate.symbol,
                timeframe=candidate.timeframe,
                window_start=spec.evaluation_window_start,
                window_end=spec.evaluation_window_end,
                limit=2000,
            ),
            key=lambda item: item.started_at,
        )
        observed_price = spec.observed_price
        if observed_price is None and candles:
            observed_price = coerce_float(candles[0].open if candidate.candidate_kind == EventCandidateKind.MARKET_EVENT.value else candles[0].close)
        if observed_price is None:
            return self._pending_or_inconclusive(
                spec=spec,
                evaluated_at=evaluated_at,
                reason="missing_reference_price",
            )
        side_hint = spec.side_hint
        target_price = spec.target_price if spec.target_price is not None else self._price_from_distance(
            observed_price,
            side_hint,
            spec.target_distance,
        )
        stop_price = spec.stop_price if spec.stop_price is not None else self._price_from_distance(
            observed_price,
            opposite_side(side_hint),
            spec.stop_distance,
        )
        target_rule = {**spec.target_rule, "price": target_price}
        invalidation_rule = {**spec.invalidation_rule, "price": stop_price}
        if side_hint not in {"buy", "sell"} or target_price is None or stop_price is None:
            return self._pending_or_inconclusive(
                spec=spec,
                evaluated_at=evaluated_at,
                observed_price=observed_price,
                target_rule=target_rule,
                invalidation_rule=invalidation_rule,
                reason="insufficient_directional_rules",
            )
        if not candles:
            return self._pending_or_inconclusive(
                spec=spec,
                evaluated_at=evaluated_at,
                observed_price=observed_price,
                target_rule=target_rule,
                invalidation_rule=invalidation_rule,
                reason="no_chart_candles",
            )
        mfe, mae = self._compute_excursions(candles, observed_price=observed_price, side_hint=side_hint)
        coverage_complete = self._coverage_complete(candles, window_end=spec.evaluation_window_end)
        for candle in candles:
            hit_target = self._hits_level(candle, price=target_price, side_hint=side_hint, target=True)
            hit_stop = self._hits_level(candle, price=stop_price, side_hint=side_hint, target=False)
            if hit_target and hit_stop:
                return SettlementSnapshot(
                    observed_price=observed_price,
                    target_rule=target_rule,
                    invalidation_rule=invalidation_rule,
                    realized_outcome=EventOutcomeResult.INCONCLUSIVE,
                    outcome_label=EventOutcomeResult.INCONCLUSIVE.value,
                    mfe=mfe,
                    mae=mae,
                    hit_target=True,
                    hit_stop=True,
                    timed_out=False,
                    inconclusive=True,
                    evaluated_at=evaluated_at,
                    metadata={
                        "resolution_reason": "same_bar_target_stop_ambiguity",
                        "resolution_bar_started_at": candle.started_at.isoformat(),
                    },
                )
            if hit_stop:
                return SettlementSnapshot(
                    observed_price=observed_price,
                    target_rule=target_rule,
                    invalidation_rule=invalidation_rule,
                    realized_outcome=EventOutcomeResult.FAILURE,
                    outcome_label=EventOutcomeResult.FAILURE.value,
                    mfe=mfe,
                    mae=mae,
                    hit_target=False,
                    hit_stop=True,
                    timed_out=False,
                    inconclusive=False,
                    evaluated_at=evaluated_at,
                    metadata={
                        "resolution_reason": "invalidation_rule_hit",
                        "resolution_bar_started_at": candle.started_at.isoformat(),
                    },
                )
            if hit_target:
                return SettlementSnapshot(
                    observed_price=observed_price,
                    target_rule=target_rule,
                    invalidation_rule=invalidation_rule,
                    realized_outcome=EventOutcomeResult.SUCCESS,
                    outcome_label=EventOutcomeResult.SUCCESS.value,
                    mfe=mfe,
                    mae=mae,
                    hit_target=True,
                    hit_stop=False,
                    timed_out=False,
                    inconclusive=False,
                    evaluated_at=evaluated_at,
                    metadata={
                        "resolution_reason": "target_rule_hit",
                        "resolution_bar_started_at": candle.started_at.isoformat(),
                    },
                )
        if evaluated_at < spec.evaluation_window_end:
            return SettlementSnapshot(
                observed_price=observed_price,
                target_rule=target_rule,
                invalidation_rule=invalidation_rule,
                realized_outcome=None,
                outcome_label="pending",
                mfe=mfe,
                mae=mae,
                hit_target=False,
                hit_stop=False,
                timed_out=False,
                inconclusive=False,
                evaluated_at=evaluated_at,
                metadata={"resolution_reason": "window_open"},
            )
        if not coverage_complete:
            return SettlementSnapshot(
                observed_price=observed_price,
                target_rule=target_rule,
                invalidation_rule=invalidation_rule,
                realized_outcome=EventOutcomeResult.INCONCLUSIVE,
                outcome_label=EventOutcomeResult.INCONCLUSIVE.value,
                mfe=mfe,
                mae=mae,
                hit_target=False,
                hit_stop=False,
                timed_out=False,
                inconclusive=True,
                evaluated_at=evaluated_at,
                metadata={
                    "resolution_reason": "insufficient_window_coverage",
                    "last_candle_ended_at": candles[-1].ended_at.isoformat(),
                },
            )
        return SettlementSnapshot(
            observed_price=observed_price,
            target_rule=target_rule,
            invalidation_rule=invalidation_rule,
            realized_outcome=EventOutcomeResult.TIMEOUT,
            outcome_label=EventOutcomeResult.TIMEOUT.value,
            mfe=mfe,
            mae=mae,
            hit_target=False,
            hit_stop=False,
            timed_out=True,
            inconclusive=False,
            evaluated_at=evaluated_at,
            metadata={"resolution_reason": "evaluation_window_expired"},
        )

    def _pending_or_inconclusive(
        self,
        *,
        spec: OutcomeSpec,
        evaluated_at: datetime,
        observed_price: float | None = None,
        target_rule: dict[str, Any] | None = None,
        invalidation_rule: dict[str, Any] | None = None,
        reason: str,
    ) -> SettlementSnapshot:
        if evaluated_at < spec.evaluation_window_end:
            return SettlementSnapshot(
                observed_price=observed_price,
                target_rule=target_rule or dict(spec.target_rule),
                invalidation_rule=invalidation_rule or dict(spec.invalidation_rule),
                realized_outcome=None,
                outcome_label="pending",
                mfe=None,
                mae=None,
                hit_target=False,
                hit_stop=False,
                timed_out=False,
                inconclusive=False,
                evaluated_at=evaluated_at,
                metadata={"resolution_reason": reason},
            )
        return SettlementSnapshot(
            observed_price=observed_price,
            target_rule=target_rule or dict(spec.target_rule),
            invalidation_rule=invalidation_rule or dict(spec.invalidation_rule),
            realized_outcome=EventOutcomeResult.INCONCLUSIVE,
            outcome_label=EventOutcomeResult.INCONCLUSIVE.value,
            mfe=None,
            mae=None,
            hit_target=False,
            hit_stop=False,
            timed_out=False,
            inconclusive=True,
            evaluated_at=evaluated_at,
            metadata={"resolution_reason": reason},
        )

    def _build_summary(self, outcomes: list[StoredEventOutcomeLedger]) -> EventStatsSummary:
        settled = [item for item in outcomes if item.realized_outcome is not None]
        counts = self._count_outcomes(outcomes)
        settled_count = len(settled)
        return EventStatsSummary(
            total_count=len(outcomes),
            settled_count=settled_count,
            open_count=len(outcomes) - settled_count,
            success_count=counts[EventOutcomeResult.SUCCESS.value],
            failure_count=counts[EventOutcomeResult.FAILURE.value],
            timeout_count=counts[EventOutcomeResult.TIMEOUT.value],
            inconclusive_count=counts[EventOutcomeResult.INCONCLUSIVE.value],
            accuracy_rate=safe_rate(counts[EventOutcomeResult.SUCCESS.value], settled_count),
            failure_rate=safe_rate(counts[EventOutcomeResult.FAILURE.value], settled_count),
            timeout_rate=safe_rate(counts[EventOutcomeResult.TIMEOUT.value], settled_count),
            inconclusive_rate=safe_rate(counts[EventOutcomeResult.INCONCLUSIVE.value], settled_count),
        )

    def _build_breakdown(self, outcomes: list[StoredEventOutcomeLedger], *, dimension: str) -> list[EventStatsBreakdownBucket]:
        buckets: dict[str, list[StoredEventOutcomeLedger]] = defaultdict(list)
        labels: dict[str, str] = {}
        for outcome in outcomes:
            bucket_key, bucket_label = self._resolve_bucket(dimension, outcome)
            buckets[bucket_key].append(outcome)
            labels[bucket_key] = bucket_label
        items: list[EventStatsBreakdownBucket] = []
        for bucket_key, bucket_outcomes in buckets.items():
            summary = self._build_summary(bucket_outcomes)
            items.append(
                EventStatsBreakdownBucket(
                    bucket_key=bucket_key,
                    bucket_label=labels.get(bucket_key, bucket_key),
                    total_count=summary.total_count,
                    settled_count=summary.settled_count,
                    open_count=summary.open_count,
                    success_count=summary.success_count,
                    failure_count=summary.failure_count,
                    timeout_count=summary.timeout_count,
                    inconclusive_count=summary.inconclusive_count,
                    accuracy_rate=summary.accuracy_rate,
                    failure_rate=summary.failure_rate,
                    timeout_rate=summary.timeout_rate,
                    inconclusive_rate=summary.inconclusive_rate,
                )
            )
        return sorted(items, key=lambda item: (-item.total_count, item.bucket_key))

    def _resolve_bucket(self, dimension: str, outcome: StoredEventOutcomeLedger) -> tuple[str, str]:
        normalized = str(dimension or "").strip().lower()
        if normalized == "event_kind":
            key = outcome.event_kind or "unknown"
            return key, key
        if normalized == "analysis_preset":
            key = outcome.analysis_preset or "unknown"
            return key, key
        if normalized == "model_name":
            key = outcome.model_name or "unknown"
            return key, key
        if normalized == "time_window":
            hour_key = outcome.born_at.astimezone(UTC).strftime("%H:00")
            return hour_key, f"{hour_key} UTC"
        return "other", "other"

    def _count_outcomes(self, outcomes: list[StoredEventOutcomeLedger]) -> dict[str, int]:
        counts = {
            EventOutcomeResult.SUCCESS.value: 0,
            EventOutcomeResult.FAILURE.value: 0,
            EventOutcomeResult.TIMEOUT.value: 0,
            EventOutcomeResult.INCONCLUSIVE.value: 0,
        }
        for outcome in outcomes:
            if outcome.realized_outcome in counts:
                counts[outcome.realized_outcome] += 1
        return counts

    def _resolve_prompt_trace(
        self,
        candidate: StoredEventCandidate,
        *,
        trace_cache: dict[str, StoredPromptTrace | None],
    ) -> StoredPromptTrace | None:
        trace_key = candidate.source_prompt_trace_id or candidate.source_message_id or ""
        if trace_key in trace_cache:
            return trace_cache[trace_key]
        trace: StoredPromptTrace | None = None
        if candidate.source_prompt_trace_id:
            trace = self._repository.get_prompt_trace(candidate.source_prompt_trace_id)
        elif candidate.source_message_id:
            trace = self._repository.get_prompt_trace_by_message(candidate.source_message_id)
        trace_cache[trace_key] = trace
        return trace

    @staticmethod
    def _extract_analysis_preset(trace: StoredPromptTrace | None) -> str | None:
        if trace is None:
            return None
        metadata = trace.metadata if isinstance(trace.metadata, dict) else {}
        snapshot = trace.snapshot if isinstance(trace.snapshot, dict) else {}
        return str(metadata.get("preset") or snapshot.get("preset") or "").strip() or None

    @staticmethod
    def _extract_model_name(trace: StoredPromptTrace | None) -> str | None:
        if trace is None:
            return None
        metadata = trace.metadata if isinstance(trace.metadata, dict) else {}
        return str(trace.model_name or metadata.get("resolved_model_name") or "").strip() or None

    def _resolve_evaluation_window(self, candidate: StoredEventCandidate) -> tuple[datetime, datetime, dict[str, Any]]:
        evaluation_window = dict(candidate.evaluation_window or {})
        start = parse_datetime(evaluation_window.get("start_at")) or candidate.anchor_start_ts or candidate.created_at
        end = (
            parse_datetime(evaluation_window.get("expires_at"))
            or parse_datetime(evaluation_window.get("end_at"))
        )
        if end is None:
            bars_value = coerce_int(evaluation_window.get("bars"))
            if bars_value is None:
                bars_value = self._DEFAULT_EVALUATION_BARS
            end = start + (self._timeframe_delta(candidate.timeframe) * bars_value)
        if end <= start:
            end = start + self._timeframe_delta(candidate.timeframe)
        expiry_policy = dict(evaluation_window)
        expiry_policy.setdefault("window_start", start.isoformat())
        expiry_policy.setdefault("window_end", end.isoformat())
        return start, end, expiry_policy

    def _extract_target_price(self, candidate: StoredEventCandidate) -> float | None:
        if candidate.metadata.get("target_price") is not None:
            return coerce_float(candidate.metadata.get("target_price"))
        take_profits = candidate.metadata.get("take_profits")
        if isinstance(take_profits, list):
            for item in take_profits:
                if isinstance(item, dict):
                    value = coerce_float(item.get("price") if item.get("price") is not None else item.get("target_price"))
                    if value is not None:
                        return value
        raw_payload = candidate.metadata.get("raw_payload")
        if isinstance(raw_payload, dict):
            return coerce_float(raw_payload.get("target_price"))
        return None

    def _extract_stop_price(self, candidate: StoredEventCandidate) -> float | None:
        invalidation_rule = dict(candidate.invalidation_rule or {})
        if invalidation_rule.get("stop_price") is not None:
            return coerce_float(invalidation_rule.get("stop_price"))
        if candidate.metadata.get("stop_price") is not None:
            return coerce_float(candidate.metadata.get("stop_price"))
        raw_payload = candidate.metadata.get("raw_payload")
        if isinstance(raw_payload, dict):
            return coerce_float(raw_payload.get("stop_price"))
        return None

    def _infer_side_hint(self, candidate: StoredEventCandidate) -> str | None:
        side = normalize_side(candidate.side_hint)
        if side is not None:
            return side
        metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
        for key in ("side", "bias", "direction"):
            side = normalize_side(metadata.get(key))
            if side is not None:
                return side
        text = " ".join(
            part for part in [
                str(candidate.title or ""),
                str(candidate.summary or ""),
                str(metadata.get("excerpt") or ""),
            ]
            if part
        ).lower()
        buy_hints = ("buy", "long", "做多", "多头", "上行", "支撑", "回踩", "需求")
        sell_hints = ("sell", "short", "做空", "空头", "下行", "阻力", "压力", "反抽", "供给")
        if any(token in text for token in buy_hints):
            return "buy"
        if any(token in text for token in sell_hints):
            return "sell"
        return None

    def _compute_excursions(self, candles: list[ChartCandle], *, observed_price: float, side_hint: str) -> tuple[float | None, float | None]:
        if not candles:
            return None, None
        if side_hint == "buy":
            mfe = max((candle.high - observed_price) for candle in candles)
            mae = max((observed_price - candle.low) for candle in candles)
        else:
            mfe = max((observed_price - candle.low) for candle in candles)
            mae = max((candle.high - observed_price) for candle in candles)
        return round(max(mfe, 0.0), 6), round(max(mae, 0.0), 6)

    @staticmethod
    def _hits_level(candle: ChartCandle, *, price: float, side_hint: str, target: bool) -> bool:
        if side_hint == "buy":
            return candle.high >= price if target else candle.low <= price
        return candle.low <= price if target else candle.high >= price

    def _coverage_complete(self, candles: list[ChartCandle], *, window_end: datetime) -> bool:
        if not candles:
            return False
        tolerance = self._timeframe_delta("1m")
        return candles[-1].ended_at >= (window_end - tolerance)

    def _price_from_distance(self, observed_price: float, side_hint: str | None, distance: float | None) -> float | None:
        if distance is None or side_hint not in {"buy", "sell"}:
            return None
        return round(observed_price + distance, 6) if side_hint == "buy" else round(observed_price - distance, 6)

    def _zone_midpoint(self, candidate: StoredEventCandidate) -> float | None:
        if candidate.price_lower is None or candidate.price_upper is None:
            return None
        return round((candidate.price_lower + candidate.price_upper) / 2.0, 6)

    def _zone_width(self, candidate: StoredEventCandidate, *, tick_size: float) -> float:
        if candidate.price_lower is None or candidate.price_upper is None:
            return tick_size * 4.0
        return max(abs(candidate.price_upper - candidate.price_lower), tick_size * 2.0)

    def _timeframe_delta(self, timeframe: str | None) -> timedelta:
        seconds = self._TIMEFRAME_SECONDS.get(str(timeframe or "1m").strip(), 60)
        return timedelta(seconds=seconds)

    def _tick_size(self, symbol: str) -> float:
        try:
            return float(default_tick_size_for_symbol(symbol))
        except Exception:  # pragma: no cover
            return 0.25

    def _filter_outcomes(
        self,
        outcomes: list[StoredEventOutcomeLedger],
        *,
        event_id: str | None,
        event_kind: str | None,
        realized_outcome: str | None,
    ) -> list[StoredEventOutcomeLedger]:
        items = outcomes
        if event_id:
            items = [item for item in items if item.event_id == event_id]
        if event_kind:
            items = [item for item in items if item.event_kind == event_kind]
        if realized_outcome:
            items = [item for item in items if item.realized_outcome == realized_outcome]
        return items

    def _outcome_model(self, stored: StoredEventOutcomeLedger) -> EventOutcomeLedger:
        return EventOutcomeLedger(
            schema_version=EVENT_OUTCOME_LEDGER_SCHEMA_VERSION,
            outcome_id=stored.outcome_id,
            event_id=stored.event_id,
            session_id=stored.session_id,
            source_message_id=stored.source_message_id,
            source_prompt_trace_id=stored.source_prompt_trace_id,
            analysis_preset=stored.analysis_preset,
            model_name=stored.model_name,
            symbol=stored.symbol,
            timeframe=stored.timeframe,
            event_kind=stored.event_kind,
            born_at=stored.born_at,
            observed_price=stored.observed_price,
            target_rule=stored.target_rule,
            invalidation_rule=stored.invalidation_rule,
            evaluation_window_start=stored.evaluation_window_start,
            evaluation_window_end=stored.evaluation_window_end,
            expiry_policy=stored.expiry_policy,
            realized_outcome=stored.realized_outcome,
            outcome_label=stored.outcome_label,
            mfe=stored.mfe,
            mae=stored.mae,
            hit_target=stored.hit_target,
            hit_stop=stored.hit_stop,
            timed_out=stored.timed_out,
            inconclusive=stored.inconclusive,
            evaluated_at=stored.evaluated_at,
            metadata=stored.metadata,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    def _require_session(self, session_id: str):
        session = self._repository.get_chat_session(session_id)
        if session is None:
            raise ReplayWorkbenchNotFoundError(f"Chat session '{session_id}' not found.")
        return session
