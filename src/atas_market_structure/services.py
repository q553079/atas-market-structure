from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from atas_market_structure.models import (
    DecisionLayerSet,
    DerivedBias,
    DerivedProcessInterpretation,
    DerivedStructureAnalysis,
    DerivedWindowInterpretation,
    EventSnapshotPayload,
    IngestionAcceptedResponse,
    KnowledgeRoute,
    MarketStructurePayload,
    ObservedContextWindow,
    ObservedCrossSessionSequence,
    ObservedLiquidityEpisode,
    ObservedProcessContext,
    OrderFlowSignalType,
    StructureSide,
)
from atas_market_structure.repository import AnalysisRepository


PayloadType = MarketStructurePayload | EventSnapshotPayload


@dataclass(frozen=True)
class IngestionContext:
    ingestion_kind: str
    source_snapshot_id: str
    instrument_symbol: str
    decision_layers: DecisionLayerSet
    process_context: ObservedProcessContext | None = None


class StructureRecognizer:
    """Minimal heuristic recognizer for phase 1 plus process-aware context."""

    def analyze(self, context: IngestionContext) -> tuple[
        list[DerivedWindowInterpretation],
        list[DerivedWindowInterpretation],
        list[DerivedWindowInterpretation],
        list[DerivedWindowInterpretation],
        list[DerivedProcessInterpretation],
        list[str],
    ]:
        macro = [self._interpret_window(window) for window in context.decision_layers.macro_context]
        intraday = [self._interpret_window(window) for window in context.decision_layers.intraday_bias]
        setup = [self._interpret_window(window) for window in context.decision_layers.setup_context]
        execution = [self._interpret_window(window) for window in context.decision_layers.execution_context]
        process = self._interpret_process_context(context.process_context)

        flags = []
        if any(item.directional_bias is DerivedBias.BULLISH for item in setup) and any(
            item.directional_bias is DerivedBias.BEARISH for item in execution
        ):
            flags.append("setup_execution_divergence")
        if any("absorption" in reason.lower() for item in execution for reason in item.reasoning):
            flags.append("execution_absorption_present")
        if any(item.subject_kind == "cross_session_sequence" for item in process):
            flags.append("cross_session_sequence_present")
        if any(item.subject_kind == "liquidity_episode" for item in process):
            flags.append("liquidity_episode_present")
        return macro, intraday, setup, execution, process, flags

    def _interpret_window(self, window: ObservedContextWindow) -> DerivedWindowInterpretation:
        bullish_signals = 0
        bearish_signals = 0
        observations_used: list[str] = []
        reasoning: list[str] = []

        range_midpoint = (window.latest_range.high + window.latest_range.low) / 2
        if window.latest_range.close > range_midpoint:
            bullish_signals += 1
            observations_used.append("latest_range.close_above_midpoint")
            reasoning.append("Close finished in the upper half of the observed range.")
        elif window.latest_range.close < range_midpoint:
            bearish_signals += 1
            observations_used.append("latest_range.close_below_midpoint")
            reasoning.append("Close finished in the lower half of the observed range.")

        high_count = sum(1 for point in window.swing_points if point.kind.value == "high")
        low_count = sum(1 for point in window.swing_points if point.kind.value == "low")
        if len(window.swing_points) >= 2 and high_count >= low_count and window.swing_points[-1].kind.value == "high":
            bullish_signals += 1
            observations_used.append("swing_points.last_is_high")
            reasoning.append("Observed swing sequence most recently resolved with a higher push.")
        elif len(window.swing_points) >= 2 and low_count > high_count and window.swing_points[-1].kind.value == "low":
            bearish_signals += 1
            observations_used.append("swing_points.last_is_low")
            reasoning.append("Observed swing sequence most recently resolved with a lower push.")

        for signal in window.orderflow_signals:
            if signal.signal_type in {OrderFlowSignalType.STACKED_IMBALANCE, OrderFlowSignalType.INITIATIVE_BUYING}:
                if signal.side is StructureSide.BUY:
                    bullish_signals += 1
                    observations_used.append(f"orderflow.{signal.signal_type.value}.buy")
                    reasoning.append("Observed buy-side initiative or imbalance in execution data.")
            if signal.signal_type in {OrderFlowSignalType.ABSORPTION, OrderFlowSignalType.INITIATIVE_SELLING}:
                if signal.side is StructureSide.SELL:
                    bearish_signals += 1
                    observations_used.append(f"orderflow.{signal.signal_type.value}.sell")
                    reasoning.append("Observed sell-side pressure or absorption in execution data.")

        if bullish_signals > bearish_signals:
            bias = DerivedBias.BULLISH
        elif bearish_signals > bullish_signals:
            bias = DerivedBias.BEARISH
        else:
            bias = DerivedBias.NEUTRAL

        total_votes = bullish_signals + bearish_signals
        confidence = min(1.0, 0.5 + (total_votes * 0.1))
        if total_votes == 0:
            confidence = 0.35
            reasoning.append("No decisive observed signals were available for this timeframe.")

        return DerivedWindowInterpretation(
            timeframe=window.timeframe,
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    def _interpret_process_context(
        self,
        process_context: ObservedProcessContext | None,
    ) -> list[DerivedProcessInterpretation]:
        if process_context is None:
            return []

        interpretations: list[DerivedProcessInterpretation] = []
        for episode in process_context.liquidity_episodes:
            interpretations.append(self._interpret_liquidity_episode(episode))
        for sequence in process_context.cross_session_sequences:
            interpretations.append(self._interpret_cross_session_sequence(sequence))
        return interpretations

    @staticmethod
    def _interpret_liquidity_episode(
        episode: ObservedLiquidityEpisode,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "executed_volume_against",
            "replenishment_count",
            "pull_count",
            "price_rejection_ticks",
        ]
        reasoning: list[str] = []
        confidence = 0.5

        if episode.replenishment_count > episode.pull_count and episode.price_rejection_ticks > 0:
            bias = DerivedBias.BULLISH if episode.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.7
            reasoning.append("Observed replenishment outpaced liquidity pulling while price rejected from the zone.")
        elif episode.pull_count > episode.replenishment_count:
            bias = DerivedBias.BEARISH if episode.side is StructureSide.BUY else DerivedBias.BULLISH
            confidence = 0.62
            reasoning.append("Observed liquidity pulling exceeded replenishment, weakening the defended zone.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("Observed liquidity episode was active, but side control was mixed.")

        reasoning.append(
            f"Measured zone {episode.price_low:.2f}-{episode.price_high:.2f} absorbed {episode.executed_volume_against} contracts."
        )
        return DerivedProcessInterpretation(
            subject_id=episode.episode_id,
            subject_kind="liquidity_episode",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_cross_session_sequence(
        sequence: ObservedCrossSessionSequence,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "session_sequence",
            "price_zone_low",
            "price_zone_high",
            "latest_price",
            "linked_episode_ids",
        ]
        reasoning: list[str] = []
        confidence = 0.58

        if sequence.latest_price > sequence.price_zone_high:
            bias = DerivedBias.BULLISH
            reasoning.append("Latest observed price moved above the maintained cross-session zone.")
            confidence = 0.76
        elif sequence.latest_price < sequence.price_zone_low:
            bias = DerivedBias.BEARISH
            reasoning.append("Latest observed price moved below the maintained cross-session zone.")
            confidence = 0.76
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("Latest observed price remains inside the cross-session zone.")

        session_values = {session.value for session in sequence.session_sequence}
        if "europe" in session_values and "us_regular" in session_values:
            confidence = min(0.88, confidence + 0.08)
            reasoning.append("The sequence spans Europe and U.S. regular sessions, so it can express longer build-and-release behavior.")

        return DerivedProcessInterpretation(
            subject_id=sequence.sequence_id,
            subject_kind="cross_session_sequence",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )


class KnowledgeRouter:
    """Selects a stable route key for later playbook or retrieval expansion."""

    def route(
        self,
        *,
        macro: Iterable[DerivedWindowInterpretation],
        intraday: Iterable[DerivedWindowInterpretation],
        setup: Iterable[DerivedWindowInterpretation],
        execution: Iterable[DerivedWindowInterpretation],
        process: Iterable[DerivedProcessInterpretation],
    ) -> KnowledgeRoute:
        macro_bias = self._dominant_bias(macro)
        intraday_bias = self._dominant_bias(intraday)
        setup_bias = self._dominant_bias(setup)
        execution_bias = self._dominant_bias(execution)
        process_items = list(process)
        process_bias = self._dominant_process_bias(process_items)
        cross_session_items = [item for item in process_items if item.subject_kind == "cross_session_sequence"]

        if cross_session_items and process_bias == setup_bias == execution_bias and process_bias in {
            DerivedBias.BULLISH,
            DerivedBias.BEARISH,
        }:
            direction = "long" if process_bias is DerivedBias.BULLISH else "short"
            return KnowledgeRoute(
                route_key=f"session_release_review_{direction}",
                summary="Cross-session process data aligns with setup and execution for a release review.",
                required_context=[
                    "macro_context",
                    "intraday_bias",
                    "setup_context",
                    "execution_context",
                    "process_context",
                ],
            )

        if setup_bias == execution_bias and setup_bias in {DerivedBias.BULLISH, DerivedBias.BEARISH}:
            direction = "long" if setup_bias is DerivedBias.BULLISH else "short"
            return KnowledgeRoute(
                route_key=f"trend_continuation_review_{direction}",
                summary="Setup and execution layers are aligned in one direction.",
                required_context=["macro_context", "intraday_bias", "setup_context", "execution_context"],
            )

        if execution_bias in {DerivedBias.BULLISH, DerivedBias.BEARISH} and execution_bias != intraday_bias:
            return KnowledgeRoute(
                route_key="execution_reversal_review",
                summary="Execution layer diverges from the broader intraday bias.",
                required_context=["intraday_bias", "setup_context", "execution_context"],
            )

        if macro_bias is DerivedBias.NEUTRAL and intraday_bias is DerivedBias.NEUTRAL:
            return KnowledgeRoute(
                route_key="balance_auction_review",
                summary="Higher layers are balanced or undecided, so review auction conditions first.",
                required_context=["macro_context", "intraday_bias", "execution_context"],
            )

        if process_bias in {DerivedBias.BULLISH, DerivedBias.BEARISH}:
            return KnowledgeRoute(
                route_key="cross_session_process_review",
                summary="Process-aware data carries directional information that needs operator review.",
                required_context=["intraday_bias", "setup_context", "execution_context", "process_context"],
            )

        return KnowledgeRoute(
            route_key="context_buildout_review",
            summary="No single playbook dominated; preserve context for operator review.",
            required_context=["macro_context", "intraday_bias", "setup_context"],
        )

    @staticmethod
    def _dominant_bias(items: Iterable[DerivedWindowInterpretation]) -> DerivedBias:
        bullish = sum(1 for item in items if item.directional_bias is DerivedBias.BULLISH)
        bearish = sum(1 for item in items if item.directional_bias is DerivedBias.BEARISH)
        if bullish > bearish:
            return DerivedBias.BULLISH
        if bearish > bullish:
            return DerivedBias.BEARISH
        return DerivedBias.NEUTRAL

    @staticmethod
    def _dominant_process_bias(items: Iterable[DerivedProcessInterpretation]) -> DerivedBias:
        bullish = sum(1 for item in items if item.directional_bias is DerivedBias.BULLISH)
        bearish = sum(1 for item in items if item.directional_bias is DerivedBias.BEARISH)
        if bullish > bearish:
            return DerivedBias.BULLISH
        if bearish > bullish:
            return DerivedBias.BEARISH
        return DerivedBias.NEUTRAL


class IngestionOrchestrator:
    """Coordinates validation, storage, recognition, and route selection."""

    def __init__(
        self,
        repository: AnalysisRepository,
        recognizer: StructureRecognizer | None = None,
        knowledge_router: KnowledgeRouter | None = None,
    ) -> None:
        self._repository = repository
        self._recognizer = recognizer or StructureRecognizer()
        self._knowledge_router = knowledge_router or KnowledgeRouter()

    def ingest_market_structure(self, payload: MarketStructurePayload) -> IngestionAcceptedResponse:
        return self._ingest(
            payload=payload,
            context=IngestionContext(
                ingestion_kind="market_structure",
                source_snapshot_id=payload.snapshot_id,
                instrument_symbol=payload.instrument.symbol,
                decision_layers=payload.decision_layers,
                process_context=payload.process_context,
            ),
        )

    def ingest_event_snapshot(self, payload: EventSnapshotPayload) -> IngestionAcceptedResponse:
        return self._ingest(
            payload=payload,
            context=IngestionContext(
                ingestion_kind="event_snapshot",
                source_snapshot_id=payload.event_snapshot_id,
                instrument_symbol=payload.instrument.symbol,
                decision_layers=payload.decision_layers,
                process_context=payload.process_context,
            ),
        )

    def _ingest(self, *, payload: PayloadType, context: IngestionContext) -> IngestionAcceptedResponse:
        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        analysis_id = f"ana-{uuid4().hex}"

        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind=context.ingestion_kind,
            source_snapshot_id=context.source_snapshot_id,
            instrument_symbol=context.instrument_symbol,
            observed_payload=payload.model_dump(mode="json"),
            stored_at=stored_at,
        )

        macro, intraday, setup, execution, process, analyst_flags = self._recognizer.analyze(context)
        knowledge_route = self._knowledge_router.route(
            macro=macro,
            intraday=intraday,
            setup=setup,
            execution=execution,
            process=process,
        )

        analysis = DerivedStructureAnalysis(
            analysis_id=analysis_id,
            ingestion_kind=context.ingestion_kind,
            source_snapshot_id=context.source_snapshot_id,
            generated_at=stored_at,
            macro_context=macro,
            intraday_bias=intraday,
            setup_context=setup,
            execution_context=execution,
            process_context=process,
            knowledge_route=knowledge_route,
            analyst_flags=analyst_flags,
        )

        self._repository.save_analysis(
            analysis_id=analysis_id,
            ingestion_id=ingestion_id,
            route_key=knowledge_route.route_key,
            analysis_payload=analysis.model_dump(mode="json"),
            stored_at=stored_at,
        )

        return IngestionAcceptedResponse(
            ingestion_id=ingestion_id,
            analysis_id=analysis_id,
            route_key=knowledge_route.route_key,
            stored_at=stored_at,
            analysis=analysis,
        )
