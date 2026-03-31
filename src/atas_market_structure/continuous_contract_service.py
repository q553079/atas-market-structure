from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from atas_market_structure.models import (
    AtasChartBarRaw,
    ContinuousAdjustmentMode,
    ContinuousBarsEnvelope,
    ContinuousContractMarker,
    ContinuousContractSegment,
    ContinuousDerivedBar,
    RollMode,
    Timeframe,
)
from atas_market_structure.repository import AnalysisRepository


LOGGER = logging.getLogger(__name__)


class ContinuousContractServiceError(RuntimeError):
    """Raised when a continuous query cannot be resolved explicitly."""


@dataclass
class _ResolvedSegment:
    contract_symbol: str
    roll_reason: str
    rows: list[AtasChartBarRaw]


class ContinuousContractService:
    """Derive continuous bars from raw mirrored ATAS contract bars."""

    _MAX_FETCH_LIMIT = 50000

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def query_continuous_bars(
        self,
        *,
        root_symbol: str,
        timeframe: Timeframe,
        roll_mode: RollMode,
        window_start: datetime,
        window_end: datetime,
        limit: int = 5000,
        include_contract_markers: bool = False,
        adjustment_mode: ContinuousAdjustmentMode = ContinuousAdjustmentMode.NONE,
        manual_sequence: list[str] | None = None,
    ) -> ContinuousBarsEnvelope:
        if limit <= 0:
            raise ContinuousContractServiceError("limit must be greater than zero")
        if window_end < window_start:
            raise ContinuousContractServiceError("window_end must be greater than or equal to window_start")

        normalized_root = root_symbol.upper().strip()
        canonical_roll_mode, warnings = self._canonicalize_roll_mode(roll_mode)
        adjustment_mode = ContinuousAdjustmentMode(adjustment_mode)
        fetch_limit = min(self._MAX_FETCH_LIMIT, max(limit * 8, 5000))
        raw_rows = self._repository.list_atas_chart_bars_raw(
            root_symbol=normalized_root,
            timeframe=timeframe.value,
            window_start=window_start,
            window_end=window_end,
            limit=fetch_limit,
        )
        deduped_rows = self._dedupe_rows(raw_rows)
        contract_rows = self._group_rows_by_contract(deduped_rows)
        contract_rows, contract_row_warnings = self._filter_generic_root_contract_rows(
            contract_rows=contract_rows,
            normalized_root=normalized_root,
        )
        warnings.extend(contract_row_warnings)

        LOGGER.info(
            "query_continuous_bars: root_symbol=%s timeframe=%s roll_mode=%s canonical_roll_mode=%s raw_rows=%s deduped_rows=%s contracts=%s",
            normalized_root,
            timeframe.value,
            roll_mode.value,
            canonical_roll_mode.value,
            len(raw_rows),
            len(deduped_rows),
            len(contract_rows),
        )

        if not contract_rows:
            warnings.append("No raw mirror bars matched the requested root_symbol/timeframe/window.")
            return ContinuousBarsEnvelope(
                root_symbol=normalized_root,
                timeframe=timeframe,
                roll_mode=canonical_roll_mode,
                adjustment_mode=adjustment_mode,
                window_start=window_start,
                window_end=window_end,
                count=0,
                contract_segments=[],
                candles=[],
                warnings=warnings,
                contract_markers=[],
            )

        resolved_segments, segment_warnings = self._resolve_segments(
            contract_rows=contract_rows,
            roll_mode=canonical_roll_mode,
            manual_sequence=manual_sequence,
        )
        warnings.extend(segment_warnings)
        candles, segments, markers, truncation_warning = self._build_derived_outputs(
            resolved_segments=resolved_segments,
            adjustment_mode=adjustment_mode,
            include_contract_markers=include_contract_markers,
            limit=limit,
        )
        if truncation_warning is not None:
            warnings.append(truncation_warning)

        LOGGER.info(
            "query_continuous_bars: root_symbol=%s roll_mode=%s adjustment_mode=%s segment_count=%s candle_count=%s warnings=%s",
            normalized_root,
            canonical_roll_mode.value,
            adjustment_mode.value,
            len(segments),
            len(candles),
            len(warnings),
        )
        return ContinuousBarsEnvelope(
            root_symbol=normalized_root,
            timeframe=timeframe,
            roll_mode=canonical_roll_mode,
            adjustment_mode=adjustment_mode,
            window_start=window_start,
            window_end=window_end,
            count=len(candles),
            contract_segments=segments,
            candles=candles,
            warnings=warnings,
            contract_markers=markers,
        )

    @staticmethod
    def _canonicalize_roll_mode(roll_mode: RollMode) -> tuple[RollMode, list[str]]:
        if roll_mode in {RollMode.NONE, RollMode.BY_CONTRACT_START, RollMode.BY_VOLUME_PROXY, RollMode.MANUAL_SEQUENCE}:
            return roll_mode, []
        return (
            RollMode.BY_CONTRACT_START,
            [f"Legacy roll_mode '{roll_mode.value}' was mapped to 'by_contract_start'; full legacy semantics are not implemented."],
        )

    @staticmethod
    def _dedupe_rows(raw_rows: list[AtasChartBarRaw]) -> list[AtasChartBarRaw]:
        deduped: dict[tuple[str, datetime], AtasChartBarRaw] = {}
        duplicate_count = 0
        for row in raw_rows:
            contract_symbol = (row.contract_symbol or row.symbol).upper()
            key = (contract_symbol, row.started_at_utc)
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = row
                continue
            duplicate_count += 1
            existing_score = (
                existing.updated_at,
                existing.chart_instance_id or "",
                existing.symbol,
            )
            candidate_score = (
                row.updated_at,
                row.chart_instance_id or "",
                row.symbol,
            )
            if candidate_score >= existing_score:
                deduped[key] = row
        if duplicate_count:
            LOGGER.info("query_continuous_bars: deduped %s duplicate root-level raw rows across chart instances", duplicate_count)
        return sorted(
            deduped.values(),
            key=lambda item: ((item.contract_symbol or item.symbol).upper(), item.started_at_utc, item.updated_at),
        )

    @staticmethod
    def _group_rows_by_contract(rows: list[AtasChartBarRaw]) -> dict[str, list[AtasChartBarRaw]]:
        grouped: dict[str, list[AtasChartBarRaw]] = {}
        for row in rows:
            contract_symbol = (row.contract_symbol or row.symbol).upper()
            grouped.setdefault(contract_symbol, []).append(row)
        for contract_symbol in grouped:
            grouped[contract_symbol].sort(key=lambda item: item.started_at_utc)
        return grouped

    @staticmethod
    def _filter_generic_root_contract_rows(
        *,
        contract_rows: dict[str, list[AtasChartBarRaw]],
        normalized_root: str,
    ) -> tuple[dict[str, list[AtasChartBarRaw]], list[str]]:
        generic_root_contract = normalized_root.upper().strip()
        if not generic_root_contract or generic_root_contract not in contract_rows:
            return contract_rows, []

        explicit_contracts = sorted(
            contract_symbol
            for contract_symbol in contract_rows
            if contract_symbol and contract_symbol != generic_root_contract
        )
        if not explicit_contracts:
            return contract_rows, []

        filtered_rows = {
            contract_symbol: rows
            for contract_symbol, rows in contract_rows.items()
            if contract_symbol != generic_root_contract
        }
        warning = (
            f"Ignored generic root-level contract {generic_root_contract} because explicit contracts were present: "
            + ", ".join(explicit_contracts)
            + "."
        )
        return filtered_rows, [warning]

    def _resolve_segments(
        self,
        *,
        contract_rows: dict[str, list[AtasChartBarRaw]],
        roll_mode: RollMode,
        manual_sequence: list[str] | None,
    ) -> tuple[list[_ResolvedSegment], list[str]]:
        warnings: list[str] = []
        if roll_mode == RollMode.BY_VOLUME_PROXY:
            raise ContinuousContractServiceError(
                "roll_mode 'by_volume_proxy' is not implemented in the current minimal runnable version."
            )

        if roll_mode == RollMode.NONE:
            selected_contract = max(
                contract_rows,
                key=lambda contract_symbol: (
                    contract_rows[contract_symbol][0].started_at_utc,
                    contract_rows[contract_symbol][-1].started_at_utc,
                    contract_symbol,
                ),
            )
            omitted_contracts = sorted(contract for contract in contract_rows if contract != selected_contract)
            if omitted_contracts:
                warnings.append(
                    "roll_mode 'none' does not stitch contracts; returning only the latest available contract "
                    f"{selected_contract} and omitting {', '.join(omitted_contracts)}."
                )
            return (
                [
                    _ResolvedSegment(
                        contract_symbol=selected_contract,
                        roll_reason="roll_mode_none_latest_contract_only",
                        rows=list(contract_rows[selected_contract]),
                    )
                ],
                warnings,
            )

        if roll_mode == RollMode.MANUAL_SEQUENCE:
            ordered_contracts = self._resolve_manual_contract_order(
                contract_rows=contract_rows,
                manual_sequence=manual_sequence,
            )
        else:
            ordered_contracts = sorted(
                contract_rows,
                key=lambda contract_symbol: (
                    contract_rows[contract_symbol][0].started_at_utc,
                    contract_symbol,
                ),
            )

        resolved: list[_ResolvedSegment] = []
        previous_manual_segment_end: datetime | None = None
        for index, contract_symbol in enumerate(ordered_contracts):
            rows = contract_rows[contract_symbol]
            if roll_mode == RollMode.MANUAL_SEQUENCE:
                segment_rows = [
                    row for row in rows
                    if previous_manual_segment_end is None or row.started_at_utc > previous_manual_segment_end
                ]
            else:
                next_start = None
                if index + 1 < len(ordered_contracts):
                    next_contract = ordered_contracts[index + 1]
                    next_start = contract_rows[next_contract][0].started_at_utc
                segment_rows = [row for row in rows if next_start is None or row.started_at_utc < next_start]
            if not segment_rows:
                warnings.append(
                    f"Contract {contract_symbol} had no non-overlapping bars after segment resolution and was skipped."
                )
                continue
            if roll_mode == RollMode.MANUAL_SEQUENCE:
                previous_manual_segment_end = segment_rows[-1].started_at_utc
            if index == 0:
                roll_reason = "initial_contract"
            elif roll_mode == RollMode.MANUAL_SEQUENCE:
                roll_reason = "manual_sequence"
            else:
                roll_reason = "contract_started"
            resolved.append(
                _ResolvedSegment(
                    contract_symbol=contract_symbol,
                    roll_reason=roll_reason,
                    rows=segment_rows,
                )
            )
        return resolved, warnings

    @staticmethod
    def _resolve_manual_contract_order(
        *,
        contract_rows: dict[str, list[AtasChartBarRaw]],
        manual_sequence: list[str] | None,
    ) -> list[str]:
        if manual_sequence is None or not manual_sequence:
            raise ContinuousContractServiceError(
                "roll_mode 'manual_sequence' requires a non-empty contract_sequence query parameter."
            )

        ordered_contracts: list[str] = []
        seen: set[str] = set()
        for item in manual_sequence:
            contract_symbol = item.upper().strip()
            if not contract_symbol or contract_symbol in seen:
                continue
            seen.add(contract_symbol)
            if contract_symbol in contract_rows:
                ordered_contracts.append(contract_symbol)

        if not ordered_contracts:
            raise ContinuousContractServiceError(
                "manual_sequence did not match any raw mirror contracts in the requested window."
            )

        uncovered = sorted(contract for contract in contract_rows if contract not in ordered_contracts)
        if uncovered:
            raise ContinuousContractServiceError(
                "manual_sequence must cover every contract in the requested window; missing "
                + ", ".join(uncovered)
            )

        previous_start: datetime | None = None
        for contract_symbol in ordered_contracts:
            current_start = contract_rows[contract_symbol][0].started_at_utc
            if previous_start is not None and current_start < previous_start:
                raise ContinuousContractServiceError(
                    "manual_sequence contradicts the observed contract start order in raw mirror data."
                )
            previous_start = current_start
        return ordered_contracts

    @staticmethod
    def _build_derived_outputs(
        *,
        resolved_segments: list[_ResolvedSegment],
        adjustment_mode: ContinuousAdjustmentMode,
        include_contract_markers: bool,
        limit: int,
    ) -> tuple[
        list[ContinuousDerivedBar],
        list[ContinuousContractSegment],
        list[ContinuousContractMarker],
        str | None,
    ]:
        segment_offsets = ContinuousContractService._resolve_segment_offsets(
            resolved_segments=resolved_segments,
            adjustment_mode=adjustment_mode,
        )
        candles: list[ContinuousDerivedBar] = []
        segments: list[ContinuousContractSegment] = []
        markers: list[ContinuousContractMarker] = []
        truncated = False

        for segment_index, resolved_segment in enumerate(resolved_segments):
            if len(candles) >= limit:
                truncated = True
                break
            segment_rows = resolved_segment.rows
            if not segment_rows:
                continue

            segment_offset = segment_offsets[segment_index]

            segment_candles: list[ContinuousDerivedBar] = []
            for row in segment_rows:
                if len(candles) + len(segment_candles) >= limit:
                    truncated = True
                    break
                segment_candles.append(
                    ContinuousDerivedBar(
                        started_at_utc=row.started_at_utc,
                        ended_at_utc=row.ended_at_utc,
                        open=row.open + segment_offset,
                        high=row.high + segment_offset,
                        low=row.low + segment_offset,
                        close=row.close + segment_offset,
                        volume=row.volume,
                        delta=row.delta,
                        bid_volume=row.bid_volume,
                        ask_volume=row.ask_volume,
                        source_contract_symbol=resolved_segment.contract_symbol,
                        source_started_at_utc=row.source_started_at,
                        adjustment_offset=segment_offset,
                        adjustment_mode=adjustment_mode,
                    )
                )
            if not segment_candles:
                continue

            candles.extend(segment_candles)
            segments.append(
                ContinuousContractSegment(
                    contract_symbol=resolved_segment.contract_symbol,
                    segment_start_utc=segment_candles[0].started_at_utc,
                    segment_end_utc=segment_candles[-1].ended_at_utc,
                    roll_reason=resolved_segment.roll_reason,
                    source_bar_count=len(segment_candles),
                    adjustment_offset=segment_offset,
                )
            )
            if include_contract_markers:
                markers.append(
                    ContinuousContractMarker(
                        contract_symbol=resolved_segment.contract_symbol,
                        marker_time_utc=segment_candles[0].started_at_utc,
                        marker_kind="segment_start",
                        roll_reason=resolved_segment.roll_reason,
                    )
                )
                markers.append(
                    ContinuousContractMarker(
                        contract_symbol=resolved_segment.contract_symbol,
                        marker_time_utc=segment_candles[-1].ended_at_utc,
                        marker_kind="segment_end",
                        roll_reason=resolved_segment.roll_reason,
                    )
                )

        truncation_warning = None
        if truncated:
            truncation_warning = f"Continuous response was truncated to the requested limit={limit}."
        return candles, segments, markers, truncation_warning

    @staticmethod
    def _resolve_segment_offsets(
        *,
        resolved_segments: list[_ResolvedSegment],
        adjustment_mode: ContinuousAdjustmentMode,
    ) -> list[float]:
        if not resolved_segments:
            return []

        if adjustment_mode == ContinuousAdjustmentMode.NONE:
            return [0.0] * len(resolved_segments)

        if adjustment_mode == ContinuousAdjustmentMode.GAP_SHIFT:
            offsets: list[float] = []
            previous_adjusted_close: float | None = None
            cumulative_offset = 0.0
            for resolved_segment in resolved_segments:
                segment_rows = resolved_segment.rows
                if not segment_rows:
                    offsets.append(cumulative_offset)
                    continue
                segment_offset = cumulative_offset
                if previous_adjusted_close is not None:
                    segment_offset = cumulative_offset + (previous_adjusted_close - segment_rows[0].open)
                    cumulative_offset = segment_offset
                offsets.append(segment_offset)
                previous_adjusted_close = segment_rows[-1].close + segment_offset
            return offsets

        if adjustment_mode == ContinuousAdjustmentMode.LATEST_GAP_SHIFT:
            offsets = [0.0] * len(resolved_segments)
            adjusted_next_first_open: float | None = None
            for index in range(len(resolved_segments) - 1, -1, -1):
                segment_rows = resolved_segments[index].rows
                if not segment_rows:
                    continue
                if adjusted_next_first_open is None:
                    offsets[index] = 0.0
                else:
                    offsets[index] = adjusted_next_first_open - segment_rows[-1].close
                adjusted_next_first_open = segment_rows[0].open + offsets[index]
            return offsets

        raise ContinuousContractServiceError(
            f"adjustment_mode '{adjustment_mode.value}' is not implemented in the current minimal runnable version."
        )
