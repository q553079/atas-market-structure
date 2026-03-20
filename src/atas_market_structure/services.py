from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from atas_market_structure.models import (
    DecisionLayerSet,
    DerivedBias,
    DerivedGapAssessment,
    DerivedKeyLevelAssessment,
    DerivedProcessInterpretation,
    DerivedStructureAnalysis,
    DerivedWindowInterpretation,
    EventSnapshotPayload,
    GapDirection,
    GapFillLikelihood,
    GapFillState,
    IngestionAcceptedResponse,
    KnowledgeRoute,
    KeyLevelRole,
    KeyLevelState,
    MarketStructurePayload,
    ObservedContextWindow,
    ObservedCrossSessionSequence,
    ObservedExertionZone,
    ObservedGapReference,
    ObservedInitiativeDrive,
    ObservedLiquidityEpisode,
    ObservedManipulationLeg,
    ObservedMeasuredMove,
    ObservedPostHarvestResponse,
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
        list[DerivedKeyLevelAssessment],
        list[DerivedGapAssessment],
        list[str],
    ]:
        macro = [self._interpret_window(window) for window in context.decision_layers.macro_context]
        intraday = [self._interpret_window(window) for window in context.decision_layers.intraday_bias]
        setup = [self._interpret_window(window) for window in context.decision_layers.setup_context]
        execution = [self._interpret_window(window) for window in context.decision_layers.execution_context]
        process = self._interpret_process_context(context.process_context)
        key_levels = self._derive_key_levels(context.process_context)
        gap_assessments = self._derive_gap_assessments(context.process_context)

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
        if any(item.subject_kind == "initiative_drive" for item in process):
            flags.append("initiative_drive_present")
        if any(item.subject_kind == "measured_move" for item in process):
            flags.append("measured_move_present")
        if any(item.subject_kind == "manipulation_leg" for item in process):
            flags.append("manipulation_leg_present")
        if any(item.subject_kind == "post_harvest_response" for item in process):
            flags.append("post_harvest_response_present")
        if any(item.subject_kind == "exertion_zone" for item in process):
            flags.append("historical_exertion_zone_present")
        if gap_assessments:
            flags.append("gap_reference_present")
        if any(item.fill_likelihood is GapFillLikelihood.PROBABLE for item in gap_assessments):
            flags.append("probable_gap_fill_present")
        if any(
            item.subject_kind == "exertion_zone" and "trapped inventory" in " ".join(item.reasoning).lower()
            for item in process
        ):
            flags.append("trapped_inventory_watch")
        if any(item.strength_score >= 0.75 for item in key_levels):
            flags.append("strong_key_level_present")
        if any(item.state is KeyLevelState.BROKEN for item in key_levels):
            flags.append("broken_key_level_present")
        if any(
            item.subject_kind == "post_harvest_response" and "reversal" in " ".join(item.reasoning).lower()
            for item in process
        ):
            flags.append("post_harvest_reversal_watch")
        if any(
            item.subject_kind == "post_harvest_response" and "consolidation" in " ".join(item.reasoning).lower()
            for item in process
        ):
            flags.append("post_harvest_consolidation_present")
        return macro, intraday, setup, execution, process, key_levels, gap_assessments, flags

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
        for drive in process_context.initiative_drives:
            interpretations.append(self._interpret_initiative_drive(drive))
        for measured_move in process_context.measured_moves:
            interpretations.append(self._interpret_measured_move(measured_move))
        for manipulation_leg in process_context.manipulation_legs:
            interpretations.append(self._interpret_manipulation_leg(manipulation_leg))
        for gap_reference in process_context.gap_references:
            interpretations.append(self._interpret_gap_reference(gap_reference))
        for post_harvest_response in process_context.post_harvest_responses:
            interpretations.append(self._interpret_post_harvest_response(post_harvest_response))
        for zone in process_context.exertion_zones:
            interpretations.append(self._interpret_exertion_zone(zone))
        for sequence in process_context.cross_session_sequences:
            interpretations.append(self._interpret_cross_session_sequence(sequence))
        return interpretations

    def _derive_key_levels(
        self,
        process_context: ObservedProcessContext | None,
    ) -> list[DerivedKeyLevelAssessment]:
        if process_context is None:
            return []

        return [self._assess_key_level(zone) for zone in process_context.exertion_zones]

    def _derive_gap_assessments(
        self,
        process_context: ObservedProcessContext | None,
    ) -> list[DerivedGapAssessment]:
        if process_context is None:
            return []

        return [self._assess_gap_reference(gap_reference) for gap_reference in process_context.gap_references]

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
    def _interpret_initiative_drive(
        drive: ObservedInitiativeDrive,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "aggressive_volume",
            "net_delta",
            "consumed_price_levels",
            "price_travel_ticks",
            "max_counter_move_ticks",
            "continuation_seconds",
        ]
        reasoning: list[str] = []
        confidence = 0.52
        same_side_delta = (drive.side is StructureSide.BUY and drive.net_delta > 0) or (
            drive.side is StructureSide.SELL and drive.net_delta < 0
        )

        if same_side_delta and drive.price_travel_ticks > drive.max_counter_move_ticks:
            bias = DerivedBias.BULLISH if drive.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.73
            reasoning.append(
                "Aggressive flow consumed nearby liquidity and moved price farther than the largest counter-response."
            )
            if drive.continuation_seconds >= 60:
                confidence = 0.79
                reasoning.append("The push kept extending after the initial burst, so the drive showed usable continuation.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("Aggressive flow was present, but follow-through did not clearly dominate the counter-response.")

        reasoning.append(
            f"Drive crossed {drive.consumed_price_levels} price levels and traveled {drive.price_travel_ticks} ticks with delta {drive.net_delta}."
        )
        return DerivedProcessInterpretation(
            subject_id=drive.drive_id,
            subject_kind="initiative_drive",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_measured_move(
        measured_move: ObservedMeasuredMove,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "achieved_distance_ticks",
            "reference_kind",
            "reference_distance_ticks",
            "achieved_multiple",
            "body_confirmed_threshold_multiple",
            "next_target_multiple",
            "invalidated",
        ]
        reasoning: list[str] = []
        confidence = 0.48

        if measured_move.invalidated:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The measured move was later invalidated by structure, so the ladder is no longer active.")
        elif measured_move.achieved_multiple >= 2.0:
            bias = DerivedBias.BULLISH if measured_move.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.76
            reasoning.append("Price has already expanded at least two reference units, so the measurement ladder is extended.")
        elif measured_move.achieved_multiple >= 1.0:
            bias = DerivedBias.BULLISH if measured_move.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.64
            reasoning.append("Price has cleared the first reference unit, so the move has reached at least one full measured target.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The move is still inside the first reference unit and has not yet completed a full measured expansion.")

        if measured_move.body_confirmed_threshold_multiple is not None:
            confidence = min(0.84, confidence + 0.04)
            reasoning.append(
                f"Body closes have confirmed the move through {measured_move.body_confirmed_threshold_multiple:.2f}x of the reference unit."
            )
        if measured_move.next_target_multiple is not None:
            reasoning.append(
                f"The next ladder threshold to monitor is {measured_move.next_target_multiple:.2f}x of the same reference unit."
            )

        reasoning.append(
            f"Measured move achieved {measured_move.achieved_distance_ticks} ticks, or {measured_move.achieved_multiple:.2f}x the {measured_move.reference_kind.value} unit."
        )
        return DerivedProcessInterpretation(
            subject_id=measured_move.measurement_id,
            subject_kind="measured_move",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_manipulation_leg(
        manipulation_leg: ObservedManipulationLeg,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "displacement_ticks",
            "primary_objective_ticks",
            "secondary_objective_ticks",
            "primary_objective_reached",
            "secondary_objective_reached",
        ]
        reasoning: list[str] = []
        confidence = 0.52

        if manipulation_leg.secondary_objective_reached:
            bias = DerivedBias.BULLISH if manipulation_leg.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.79
            reasoning.append("The manipulation leg reached its secondary objective, so the forcing move completed a deeper extension.")
        elif manipulation_leg.primary_objective_reached:
            bias = DerivedBias.BULLISH if manipulation_leg.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.67
            reasoning.append("The manipulation leg reached its first objective but has not yet confirmed the deeper extension.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The manipulation leg created displacement, but its intended objective has not been fully confirmed yet.")

        reasoning.append(
            f"Manipulation leg displaced price by {manipulation_leg.displacement_ticks} ticks between {manipulation_leg.price_low:.2f} and {manipulation_leg.price_high:.2f}."
        )
        return DerivedProcessInterpretation(
            subject_id=manipulation_leg.leg_id,
            subject_kind="manipulation_leg",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_gap_reference(
        gap_reference: ObservedGapReference,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "direction",
            "gap_size_ticks",
            "max_fill_ticks",
            "fill_ratio",
            "fill_attempt_count",
            "accepted_inside_gap",
            "rejected_from_gap",
            "fully_filled_at",
        ]
        reasoning: list[str] = []
        confidence = 0.5

        if gap_reference.fully_filled_at is not None:
            bias = DerivedBias.NEUTRAL
            confidence = 0.82
            reasoning.append("The gap has already been fully repaired, so it should now be treated as a completed reference rather than an open target.")
        elif gap_reference.accepted_inside_gap:
            bias = DerivedBias.BEARISH if gap_reference.direction is GapDirection.UP else DerivedBias.BULLISH
            confidence = 0.72
            reasoning.append("Price has been accepted inside the gap, which keeps the fill script active.")
        elif gap_reference.rejected_from_gap:
            bias = DerivedBias.BULLISH if gap_reference.direction is GapDirection.UP else DerivedBias.BEARISH
            confidence = 0.69
            reasoning.append("Price rejected from the gap area, so the gap is currently acting more like support or resistance than a fill magnet.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The gap remains a valid location reference, but interaction evidence is still limited.")

        reasoning.append(
            f"Gap {gap_reference.gap_low:.2f}-{gap_reference.gap_high:.2f} has repaired {gap_reference.fill_ratio:.0%} of its {gap_reference.gap_size_ticks}-tick span."
        )
        return DerivedProcessInterpretation(
            subject_id=gap_reference.gap_id,
            subject_kind="gap_reference",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_post_harvest_response(
        response: ObservedPostHarvestResponse,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "completion_ratio",
            "continuation_ticks_after_completion",
            "consolidation_range_ticks",
            "pullback_ticks",
            "reversal_ticks",
            "seconds_to_first_pullback",
            "seconds_to_reversal",
            "reached_next_opposing_liquidity",
            "post_harvest_delta",
            "outcome",
        ]
        reasoning: list[str] = []
        confidence = 0.54

        if response.outcome.value == "continuation":
            bias = DerivedBias.BULLISH if response.harvest_side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.74
            reasoning.append("The harvest completed and price kept extending in the same direction, so the move still showed continuation.")
        elif response.outcome.value == "consolidation":
            bias = DerivedBias.NEUTRAL
            confidence = 0.63
            reasoning.append("The harvest completed and price rotated into a consolidation instead of immediately extending or fully reversing.")
        elif response.outcome.value == "pullback":
            bias = DerivedBias.NEUTRAL
            confidence = 0.66
            reasoning.append("The harvest completed and price shifted into a controlled pullback, which weakens immediate continuation.")
        elif response.outcome.value == "reversal":
            bias = DerivedBias.BEARISH if response.harvest_side is StructureSide.BUY else DerivedBias.BULLISH
            confidence = 0.79
            reasoning.append("The harvest completed and price reversed sharply enough to challenge the completed move.")
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The post-harvest response was mixed, so continuation and reversal evidence remain balanced.")

        if response.reached_next_opposing_liquidity:
            confidence = min(0.86, confidence + 0.04)
            reasoning.append("Price also reached the next opposing liquidity after completion, which makes the harvest response more contextually important.")

        reasoning.append(
            f"After harvesting {response.harvested_price_low:.2f}-{response.harvested_price_high:.2f}, price consolidated {response.consolidation_range_ticks} ticks, pulled back {response.pullback_ticks} ticks, and reversed {response.reversal_ticks} ticks."
        )
        return DerivedProcessInterpretation(
            subject_id=response.response_id,
            subject_kind="post_harvest_response",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _interpret_exertion_zone(
        zone: ObservedExertionZone,
    ) -> DerivedProcessInterpretation:
        observations_used = [
            "establishing_volume",
            "establishing_delta",
            "revisit_count",
            "successful_reengagement_count",
            "failed_reengagement_count",
            "last_revisit_delta",
            "last_revisit_volume",
            "last_defended_reaction_ticks",
            "last_failed_break_ticks",
            "post_failure_delta",
            "post_failure_move_ticks",
        ]
        reasoning: list[str] = []
        confidence = 0.56

        if zone.successful_reengagement_count > zone.failed_reengagement_count and zone.last_defended_reaction_ticks > 0:
            bias = DerivedBias.BULLISH if zone.side is StructureSide.BUY else DerivedBias.BEARISH
            confidence = 0.78
            reasoning.append(
                "A previously important drive-origin zone re-engaged on revisit and produced a fresh reaction."
            )
            reasoning.append(
                f"The latest defense pushed price {zone.last_defended_reaction_ticks} ticks away from the zone."
            )
        elif zone.failed_reengagement_count > 0 and zone.last_failed_break_ticks > 0:
            bias = DerivedBias.BEARISH if zone.side is StructureSide.BUY else DerivedBias.BULLISH
            confidence = 0.74
            reasoning.append(
                "The historical drive-origin zone failed on revisit and price moved through it."
            )
            reasoning.append(
                f"Price extended {zone.last_failed_break_ticks} ticks through the zone after the failure."
            )
            if zone.post_failure_delta is not None and zone.post_failure_move_ticks is not None:
                confidence = min(0.86, confidence + 0.06)
                reasoning.append(
                    "Post-failure delta and follow-through can indicate trapped inventory or stop-driven continuation near the zone."
                )
        else:
            bias = DerivedBias.NEUTRAL
            reasoning.append("The historical drive-origin zone has revisit evidence, but its current behavior is mixed.")

        reasoning.append(
            f"Zone {zone.price_low:.2f}-{zone.price_high:.2f} was established on {zone.establishing_volume} contracts and has been revisited {zone.revisit_count} times."
        )
        return DerivedProcessInterpretation(
            subject_id=zone.zone_id,
            subject_kind="exertion_zone",
            directional_bias=bias,
            confidence=round(confidence, 2),
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _assess_key_level(
        zone: ObservedExertionZone,
    ) -> DerivedKeyLevelAssessment:
        observations_used = [
            "side",
            "price_low",
            "price_high",
            "establishing_volume",
            "establishing_delta",
            "revisit_count",
            "successful_reengagement_count",
            "failed_reengagement_count",
            "last_revisit_delta",
            "last_defended_reaction_ticks",
            "last_failed_break_ticks",
            "post_failure_delta",
            "post_failure_move_ticks",
        ]
        reasoning: list[str] = []

        role = KeyLevelRole.SUPPORT if zone.side is StructureSide.BUY else KeyLevelRole.RESISTANCE
        bias = DerivedBias.BULLISH if zone.side is StructureSide.BUY else DerivedBias.BEARISH
        state = KeyLevelState.MONITORING
        strength = 0.45

        same_side_establishing_delta = (zone.side is StructureSide.BUY and zone.establishing_delta > 0) or (
            zone.side is StructureSide.SELL and zone.establishing_delta < 0
        )
        if same_side_establishing_delta and zone.establishing_volume > 0:
            strength += 0.12
            reasoning.append("The zone was established with large executed volume aligned with the initiating side.")

        if zone.successful_reengagement_count > zone.failed_reengagement_count and zone.last_defended_reaction_ticks > 0:
            state = KeyLevelState.DEFENDED
            strength += 0.2
            reasoning.append("Price revisited the zone and the original side responded again, so the area is acting as live support or resistance.")
        elif zone.failed_reengagement_count > 0 and zone.last_failed_break_ticks > 0:
            state = KeyLevelState.BROKEN
            role = KeyLevelRole.RESISTANCE if role is KeyLevelRole.SUPPORT else KeyLevelRole.SUPPORT
            bias = DerivedBias.BEARISH if bias is DerivedBias.BULLISH else DerivedBias.BULLISH
            strength += 0.08
            reasoning.append("The zone failed on revisit, so it should be watched as a broken level or possible flip area.")
            if zone.post_failure_delta is not None and zone.post_failure_move_ticks is not None:
                strength += 0.1
                reasoning.append("Post-break delta and follow-through suggest trapped inventory or stop-release activity around the level.")

        if zone.revisit_count >= 2:
            strength += 0.06
            reasoning.append("Multiple revisits have confirmed that the market still references this area.")

        if zone.peak_price_level_volume is not None and zone.peak_price_level_volume > 0:
            strength += 0.05
            reasoning.append("The zone contains a concentrated executed-volume pocket, which raises its contextual importance.")

        strength = min(0.95, round(strength, 2))
        if state is KeyLevelState.BROKEN and zone.successful_reengagement_count > 0:
            state = KeyLevelState.FLIPPED
            strength = min(0.95, round(strength + 0.05, 2))
            reasoning.append("The zone has both failed and re-engaged before, so it may function as a flip level.")

        return DerivedKeyLevelAssessment(
            zone_id=zone.zone_id,
            role=role,
            state=state,
            price_low=zone.price_low,
            price_high=zone.price_high,
            directional_bias=bias,
            strength_score=strength,
            revisit_count=zone.revisit_count,
            observations_used=observations_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _assess_gap_reference(
        gap_reference: ObservedGapReference,
    ) -> DerivedGapAssessment:
        observations_used = [
            "direction",
            "gap_low",
            "gap_high",
            "gap_size_ticks",
            "max_fill_ticks",
            "fill_ratio",
            "fill_attempt_count",
            "accepted_inside_gap",
            "rejected_from_gap",
            "fully_filled_at",
        ]
        reasoning: list[str] = []

        remaining_fill_ticks = max(0, gap_reference.gap_size_ticks - gap_reference.max_fill_ticks)
        if gap_reference.fully_filled_at is not None or gap_reference.fill_ratio >= 1.0:
            fill_state = GapFillState.FULLY_FILLED
            fill_likelihood = GapFillLikelihood.COMPLETED
            directional_bias = DerivedBias.NEUTRAL
            reasoning.append("The gap is already fully filled, so there is no remaining repair objective.")
        elif gap_reference.fill_ratio > 0.0:
            fill_state = GapFillState.PARTIAL_FILL
            if gap_reference.accepted_inside_gap or gap_reference.fill_ratio >= 0.5:
                fill_likelihood = GapFillLikelihood.PROBABLE
                reasoning.append("Price has already repaired a meaningful part of the gap and is being accepted inside it.")
            else:
                fill_likelihood = GapFillLikelihood.POSSIBLE
                reasoning.append("The gap has started to repair, but acceptance is still incomplete.")

            if gap_reference.accepted_inside_gap:
                directional_bias = DerivedBias.BEARISH if gap_reference.direction is GapDirection.UP else DerivedBias.BULLISH
                reasoning.append("Acceptance inside the gap favors continuation toward full repair.")
            elif gap_reference.rejected_from_gap:
                directional_bias = DerivedBias.BULLISH if gap_reference.direction is GapDirection.UP else DerivedBias.BEARISH
                reasoning.append("Rejection from the gap favors defending the open rather than completing the fill immediately.")
            else:
                directional_bias = DerivedBias.NEUTRAL
        else:
            fill_state = GapFillState.UNTOUCHED
            if gap_reference.fill_attempt_count > 0:
                fill_likelihood = GapFillLikelihood.POSSIBLE
                reasoning.append("The gap has been tested but remains largely open, so a repair attempt is still plausible.")
            else:
                fill_likelihood = GapFillLikelihood.UNLIKELY
                reasoning.append("No meaningful repair attempt has appeared yet, so the gap currently acts more like an untouched location reference.")
            directional_bias = DerivedBias.NEUTRAL

        reasoning.append(
            f"Remaining distance to a full fill is {remaining_fill_ticks} ticks out of the original {gap_reference.gap_size_ticks}-tick gap."
        )
        return DerivedGapAssessment(
            gap_id=gap_reference.gap_id,
            direction=gap_reference.direction,
            gap_low=gap_reference.gap_low,
            gap_high=gap_reference.gap_high,
            fill_state=fill_state,
            fill_likelihood=fill_likelihood,
            directional_bias=directional_bias,
            fill_ratio=gap_reference.fill_ratio,
            remaining_fill_ticks=remaining_fill_ticks,
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
            "linked_drive_ids",
            "linked_exertion_zone_ids",
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

        macro, intraday, setup, execution, process, key_levels, gap_assessments, analyst_flags = self._recognizer.analyze(context)
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
            key_levels=key_levels,
            gap_assessments=gap_assessments,
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
            analysis=analysis.model_dump(mode="json"),
        )
