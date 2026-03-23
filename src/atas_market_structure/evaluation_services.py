from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable
from uuid import uuid4

from atas_market_structure.models import (
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EpisodeEvaluationDeclaredTimeWindow,
    EpisodeEvaluationDiagnosis,
    EpisodeEvaluationLifecycle,
    EpisodeEvaluationOutcome,
    EpisodeEvaluationScorecard,
    EpisodeEvaluationTuningHints,
    EpisodeResolution,
    EvaluationFailureMode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    InstrumentProfile,
    RegimeKind,
    ReviewSource,
    TradableEventKind,
)
from atas_market_structure.profile_services import get_parameter_metadata_registry
from atas_market_structure.repository import AnalysisRepository


EPISODE_EVALUATION_SCHEMA_VERSION = "episode_evaluation_v1"

_EVENT_TO_HYPOTHESIS = {
    TradableEventKind.MOMENTUM_CONTINUATION: {EventHypothesisKind.CONTINUATION_BASE},
    TradableEventKind.BALANCE_MEAN_REVERSION: {EventHypothesisKind.DISTRIBUTION_BALANCE},
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION: {
        EventHypothesisKind.ABSORPTION_ACCUMULATION,
        EventHypothesisKind.REVERSAL_PREPARATION,
    },
}

_EVENT_TO_WATCH_LABELS = {
    TradableEventKind.MOMENTUM_CONTINUATION: {"watch_continuation_base"},
    TradableEventKind.BALANCE_MEAN_REVERSION: {"watch_distribution_balance"},
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION: {
        "watch_absorption_accumulation",
        "watch_reversal_preparation",
    },
}

_EVENT_TO_PRIOR_PATH = {
    TradableEventKind.MOMENTUM_CONTINUATION: "priors.hypotheses.continuation_base",
    TradableEventKind.BALANCE_MEAN_REVERSION: "priors.hypotheses.distribution_balance",
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION: "priors.hypotheses.absorption_accumulation",
}

_EVENT_TO_WEIGHT_PATHS = {
    TradableEventKind.MOMENTUM_CONTINUATION: ("weights.initiative", "weights.trend_efficiency"),
    TradableEventKind.BALANCE_MEAN_REVERSION: ("weights.balance", "weights.anchor_interaction"),
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION: ("weights.absorption", "weights.anchor_interaction"),
}


@dataclass(frozen=True)
class EpisodeRuleReviewContext:
    """Resolved rule-review context for one closed episode."""

    ordered_beliefs: list[BeliefStateSnapshot]
    sequence: list[BeliefStateSnapshot]
    prior_belief: BeliefStateSnapshot | None
    next_belief: BeliefStateSnapshot | None
    initial_belief: BeliefStateSnapshot
    final_belief: BeliefStateSnapshot
    initial_state: EventHypothesisState
    final_state: EventHypothesisState
    event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]]


class EpisodeEvaluationService:
    """Generate deterministic `episode_evaluation_v1` payloads for closed episodes."""

    def __init__(self, repository: AnalysisRepository | None = None) -> None:
        self._repository = repository

    def evaluate_episode(
        self,
        *,
        episode,
        beliefs: Iterable[BeliefStateSnapshot],
        profile: InstrumentProfile,
        judgement_source: ReviewSource = ReviewSource.RULE_REVIEW_V1,
        session: str | None = None,
        bar_tf: str | None = None,
        persist: bool = False,
    ) -> EpisodeEvaluation:
        """Evaluate one closed episode against belief-state history and the active profile."""

        if judgement_source is not ReviewSource.RULE_REVIEW_V1:
            raise NotImplementedError("V1 only implements rule_review_v1 generation")

        ordered_beliefs = sorted(beliefs, key=lambda item: item.observed_at)
        if not ordered_beliefs:
            raise ValueError("belief history is required for episode evaluation")

        context = _build_context(ordered_beliefs=ordered_beliefs, episode=episode)
        declared_window = _declared_time_window(
            profile=profile,
            initial_regime=context.initial_belief.regime_posteriors[0].regime if context.initial_belief.regime_posteriors else None,
            event_kind=episode.event_kind,
        )
        first_validation = _first_validation(
            event_states=context.event_states,
            confirming_threshold=profile.thresholds.confirming_hypothesis_probability,
        )
        first_negative_signal = _first_negative_signal(
            event_states=context.event_states,
            sequence=context.sequence,
        )
        first_invalidation = _first_invalidation(event_states=context.event_states)
        downgraded_at = _first_phase_hit(
            event_states=context.event_states,
            target_phase=EventPhase.WEAKENING,
        )
        peak_prob, peak_prob_at = _peak_probability(context.event_states)
        outcome = _build_outcome(
            episode=episode,
            judgement_source=judgement_source,
            validating_at=first_validation,
            building_threshold=profile.thresholds.building_hypothesis_probability,
            peak_prob=peak_prob,
        )
        scores = _build_scores(
            episode=episode,
            context=context,
            profile=profile,
            declared_window=declared_window,
            first_validation=first_validation,
            first_negative_signal=first_negative_signal,
            first_invalidation=first_invalidation,
            peak_prob=peak_prob,
        )
        failure_mode = _primary_failure_mode(
            episode=episode,
            outcome=outcome,
            scores=scores,
            declared_window=declared_window,
            first_validation=first_validation,
        )
        candidate_parameters, suggested_direction, tuning_confidence = _build_tuning_hints(
            instrument_symbol=episode.instrument_symbol,
            event_kind=episode.event_kind,
            replacement_event=episode.replacement_event_kind,
            failure_mode=failure_mode,
            data_is_degraded=bool(context.initial_belief.data_status.degraded_modes),
        )
        diagnosis = EpisodeEvaluationDiagnosis(
            primary_failure_mode=failure_mode,
            supporting_reasons=_supporting_reasons(
                episode=episode,
                outcome=outcome,
                scores=scores,
                declared_window=declared_window,
                first_validation=first_validation,
                first_negative_signal=first_negative_signal,
                first_invalidation=first_invalidation,
                context=context,
                peak_prob=peak_prob,
            ),
            missing_confirmation=[] if outcome.did_event_materialize and failure_mode is EvaluationFailureMode.NONE else list(context.initial_state.missing_confirmation),
            invalidating_signals_seen=[] if outcome.did_event_materialize and failure_mode is EvaluationFailureMode.NONE else _unique(
                list(context.final_state.invalidating_signals) + list(context.final_belief.invalidating_signals_seen)
            ),
            candidate_parameters=candidate_parameters,
            suggested_direction=suggested_direction,
        )
        evaluation = EpisodeEvaluation(
            evaluation_id=f"eval-{uuid4().hex}",
            episode_id=episode.episode_id,
            instrument=episode.instrument_symbol,
            session=session,
            bar_tf=bar_tf,
            market_time_start=episode.started_at,
            market_time_end=episode.ended_at,
            profile_version=episode.profile_version,
            engine_version=episode.engine_version,
            schema_version=EPISODE_EVALUATION_SCHEMA_VERSION,
            initial_regime_top1=context.initial_belief.regime_posteriors[0].regime if context.initial_belief.regime_posteriors else None,
            initial_regime_prob=context.initial_belief.regime_posteriors[0].probability if context.initial_belief.regime_posteriors else None,
            evaluated_event_kind=episode.event_kind,
            initial_phase=context.initial_state.phase,
            initial_prob=context.initial_state.posterior_probability,
            declared_time_window=declared_window,
            anchor_context=_anchor_context(context.initial_belief),
            lifecycle=EpisodeEvaluationLifecycle(
                started_at=episode.started_at,
                first_validation_hit_at=first_validation,
                peak_prob=peak_prob,
                peak_prob_at=peak_prob_at,
                first_invalidation_hit_at=first_invalidation,
                downgraded_at=downgraded_at,
                resolved_at=episode.ended_at if episode.resolution is EpisodeResolution.CONFIRMED else None,
                resolution=episode.resolution,
                replacement_event=episode.replacement_event_kind,
            ),
            outcome=outcome,
            scores=scores,
            diagnosis=diagnosis,
            tuning_hints=EpisodeEvaluationTuningHints(
                candidate_parameters=candidate_parameters,
                suggested_direction=suggested_direction,
                confidence=tuning_confidence,
            ),
            evaluated_at=datetime.now(tz=UTC),
        )
        if persist:
            self.persist_evaluation(evaluation)
        return evaluation

    def evaluate_episode_from_repository(self, episode_id: str, *, persist: bool = True) -> EpisodeEvaluation:
        """Load one episode and its context from the repository, then run rule_review_v1."""

        if self._repository is None:
            raise RuntimeError("repository is required for repository-backed evaluation")
        existing = self._repository.get_episode_evaluation(episode_id)
        if existing is not None:
            return EpisodeEvaluation.model_validate(existing.evaluation_payload)

        from atas_market_structure.models import EventEpisode  # local import to avoid circular rebuild timing issues

        stored_episode = self._repository.get_event_episode(episode_id)
        if stored_episode is None:
            raise ValueError(f"unknown episode_id: {episode_id}")
        episode = EventEpisode.model_validate(stored_episode.episode_payload)
        profile_record = self._repository.get_active_instrument_profile(episode.instrument_symbol)
        if profile_record is None:
            raise ValueError(f"no active instrument profile for {episode.instrument_symbol}")
        profile = InstrumentProfile.model_validate(profile_record.profile_payload)
        beliefs = [
            BeliefStateSnapshot.model_validate(item.belief_payload)
            for item in self._repository.list_belief_states(instrument_symbol=episode.instrument_symbol, limit=500)
        ]
        session, bar_tf = _infer_context_from_repository(
            repository=self._repository,
            instrument_symbol=episode.instrument_symbol,
            window_start=episode.started_at - timedelta(hours=8),
            window_end=episode.ended_at + timedelta(hours=8),
        )
        return self.evaluate_episode(
            episode=episode,
            beliefs=beliefs,
            profile=profile,
            session=session,
            bar_tf=bar_tf,
            persist=persist,
        )

    def persist_evaluation(self, evaluation: EpisodeEvaluation) -> None:
        """Persist one evaluation payload through the existing repository abstraction."""

        if self._repository is None:
            return
        self._repository.save_episode_evaluation(
            evaluation_id=evaluation.evaluation_id,
            episode_id=evaluation.episode_id,
            instrument_symbol=evaluation.instrument_symbol,
            event_kind=evaluation.evaluated_event_kind.value,
            evaluated_at=evaluation.evaluated_at,
            schema_version=evaluation.schema_version,
            profile_version=evaluation.profile_version,
            engine_version=evaluation.engine_version,
            evaluation_payload=evaluation.model_dump(mode="json", by_alias=True),
        )


def _build_context(*, ordered_beliefs: list[BeliefStateSnapshot], episode) -> EpisodeRuleReviewContext:
    sequence = [belief for belief in ordered_beliefs if episode.started_at <= belief.observed_at <= episode.ended_at]
    if not sequence:
        raise ValueError("belief history does not cover the episode window")
    prior = next((belief for belief in reversed(ordered_beliefs) if belief.observed_at < episode.started_at), None)
    next_belief = next((belief for belief in ordered_beliefs if belief.observed_at > episode.ended_at), None)
    event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]] = []
    for belief in sequence:
        state = _event_state_for_belief(belief, episode.event_kind)
        if state is not None:
            event_states.append((belief, state))
    if not event_states:
        raise ValueError("belief history does not include the evaluated event inside the episode window")
    initial_belief, initial_state = event_states[0]
    final_belief, final_state = event_states[-1]
    return EpisodeRuleReviewContext(
        ordered_beliefs=ordered_beliefs,
        sequence=sequence,
        prior_belief=prior,
        next_belief=next_belief,
        initial_belief=initial_belief,
        final_belief=final_belief,
        initial_state=initial_state,
        final_state=final_state,
        event_states=event_states,
    )


def _event_state_for_belief(belief: BeliefStateSnapshot, event_kind: TradableEventKind) -> EventHypothesisState | None:
    matching = [state for state in belief.event_hypotheses if state.mapped_event_kind == event_kind]
    if not matching:
        return None
    matching.sort(key=lambda item: (item.posterior_probability, -_phase_rank(item.phase)), reverse=True)
    return matching[0]


def _declared_time_window(
    *,
    profile: InstrumentProfile,
    initial_regime,
    event_kind: TradableEventKind,
) -> EpisodeEvaluationDeclaredTimeWindow:
    if event_kind is TradableEventKind.MOMENTUM_CONTINUATION:
        use_strong = initial_regime is RegimeKind.STRONG_MOMENTUM_TREND
        window = profile.time_windows.momentum_continuation.strong if use_strong else profile.time_windows.momentum_continuation.normal
    elif event_kind is TradableEventKind.BALANCE_MEAN_REVERSION:
        window = profile.time_windows.balance_mean_reversion.normal
    else:
        window = profile.time_windows.absorption_to_reversal_preparation.normal
    return EpisodeEvaluationDeclaredTimeWindow(
        mode=f"next_{window.bars_max}_bars",
        bars_min=window.bars_min,
        bars_max=window.bars_max,
    )


def _first_validation(*, event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]], confirming_threshold: float) -> datetime | None:
    for belief, state in event_states:
        if state.phase in {EventPhase.CONFIRMING, EventPhase.RESOLVED} or state.posterior_probability >= confirming_threshold:
            return belief.observed_at
    return None


def _first_negative_signal(*, event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]], sequence: list[BeliefStateSnapshot]) -> datetime | None:
    for belief, state in event_states:
        if state.invalidating_signals or belief.invalidating_signals_seen:
            return belief.observed_at
    for belief in sequence:
        if belief.invalidating_signals_seen:
            return belief.observed_at
    return None


def _first_invalidation(*, event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]]) -> datetime | None:
    for belief, state in event_states:
        if state.phase is EventPhase.INVALIDATED:
            return belief.observed_at
    return None


def _first_phase_hit(*, event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]], target_phase: EventPhase) -> datetime | None:
    for belief, state in event_states:
        if state.phase is target_phase:
            return belief.observed_at
    return None


def _peak_probability(event_states: list[tuple[BeliefStateSnapshot, EventHypothesisState]]) -> tuple[float, datetime | None]:
    best_probability = -1.0
    best_time: datetime | None = None
    for belief, state in event_states:
        if state.posterior_probability > best_probability:
            best_probability = state.posterior_probability
            best_time = belief.observed_at
    return max(best_probability, 0.0), best_time


def _build_outcome(
    *,
    episode,
    judgement_source: ReviewSource,
    validating_at: datetime | None,
    building_threshold: float,
    peak_prob: float,
) -> EpisodeEvaluationOutcome:
    did_materialize = episode.resolution is EpisodeResolution.CONFIRMED
    did_partial_materialize = (not did_materialize) and (validating_at is not None or peak_prob >= building_threshold)
    dominant_final_event = episode.replacement_event_kind if episode.replacement_event_kind is not None else (episode.event_kind if did_materialize else None)
    return EpisodeEvaluationOutcome(
        did_event_materialize=did_materialize,
        did_partial_materialize=did_partial_materialize,
        dominant_final_event=dominant_final_event,
        judgement_source=judgement_source,
    )


def _build_scores(
    *,
    episode,
    context: EpisodeRuleReviewContext,
    profile: InstrumentProfile,
    declared_window: EpisodeEvaluationDeclaredTimeWindow,
    first_validation: datetime | None,
    first_negative_signal: datetime | None,
    first_invalidation: datetime | None,
    peak_prob: float,
) -> EpisodeEvaluationScorecard:
    build_threshold = profile.thresholds.building_hypothesis_probability
    confirm_threshold = profile.thresholds.confirming_hypothesis_probability
    resolved_threshold = profile.thresholds.resolved_hypothesis_probability
    active_threshold = profile.thresholds.active_hypothesis_probability

    validation_bar = _bar_offset(context=context, timestamp=first_validation)
    negative_bar = _bar_offset(context=context, timestamp=first_negative_signal)
    invalidation_bar = _bar_offset(context=context, timestamp=first_invalidation)
    tracked_before = _tracked_before_event(context=context, event_kind=episode.event_kind)

    if episode.resolution is EpisodeResolution.CONFIRMED:
        if tracked_before:
            hypothesis_selection = 2
        elif context.initial_state.posterior_probability >= build_threshold:
            hypothesis_selection = 1
        elif context.initial_state.posterior_probability >= active_threshold:
            hypothesis_selection = 0
        else:
            hypothesis_selection = -2
    else:
        if peak_prob >= confirm_threshold:
            hypothesis_selection = -2
        elif peak_prob >= build_threshold:
            hypothesis_selection = -1
        else:
            hypothesis_selection = 0

    if validation_bar is None:
        confirmation_timing = -2 if episode.resolution is EpisodeResolution.CONFIRMED else 0
    elif declared_window.bars_min is not None and validation_bar < declared_window.bars_min:
        confirmation_timing = -2 if declared_window.bars_min - validation_bar >= 2 else -1
    elif declared_window.bars_max is not None and validation_bar > declared_window.bars_max:
        confirmation_timing = -2 if validation_bar - declared_window.bars_max >= 2 else -1
    elif validation_bar in {declared_window.bars_min, declared_window.bars_max}:
        confirmation_timing = 1
    else:
        confirmation_timing = 2

    invalidation_timing = 0
    if episode.resolution in {EpisodeResolution.INVALIDATED, EpisodeResolution.REPLACED, EpisodeResolution.EXPIRED, EpisodeResolution.TIMED_OUT}:
        if invalidation_bar is None:
            invalidation_timing = -2
        elif negative_bar is None:
            invalidation_timing = 1
        else:
            lag = invalidation_bar - negative_bar
            if lag <= 1:
                invalidation_timing = 2
            elif lag == 2:
                invalidation_timing = 1
            elif lag <= 3:
                invalidation_timing = -1
            else:
                invalidation_timing = -2

    transition_handling = 0
    if episode.replacement_event_kind is not None:
        transition_handling = 2 if _replacement_was_tracked(context=context, replacement_event=episode.replacement_event_kind) else -2

    if episode.resolution is EpisodeResolution.CONFIRMED:
        if context.initial_state.posterior_probability >= active_threshold and peak_prob >= confirm_threshold:
            calibration = 2
        elif context.initial_state.posterior_probability < active_threshold:
            calibration = -2 if not tracked_before else -1
        else:
            calibration = 1
    else:
        if peak_prob >= resolved_threshold:
            calibration = -2
        elif peak_prob >= confirm_threshold:
            calibration = -1
        elif peak_prob < build_threshold:
            calibration = 1
        else:
            calibration = 0

    return EpisodeEvaluationScorecard(
        hypothesis_selection_score=hypothesis_selection,
        confirmation_timing_score=confirmation_timing,
        invalidation_timing_score=invalidation_timing,
        transition_handling_score=transition_handling,
        calibration_score=calibration,
    )


def _primary_failure_mode(
    *,
    episode,
    outcome: EpisodeEvaluationOutcome,
    scores: EpisodeEvaluationScorecard,
    declared_window: EpisodeEvaluationDeclaredTimeWindow,
    first_validation: datetime | None,
) -> EvaluationFailureMode:
    validation_bar = _bar_offset_from_window(
        started_at=episode.started_at,
        sequence_end=episode.ended_at,
        timestamp=first_validation,
    )
    if episode.replacement_event_kind is not None and scores.transition_handling_score < 0:
        return EvaluationFailureMode.MISSED_TRANSITION
    if scores.invalidation_timing_score < 0:
        return EvaluationFailureMode.LATE_INVALIDATION
    if validation_bar is not None and declared_window.bars_min is not None and validation_bar < declared_window.bars_min and scores.confirmation_timing_score < 0:
        return EvaluationFailureMode.EARLY_CONFIRMATION
    if (validation_bar is not None and declared_window.bars_max is not None and validation_bar > declared_window.bars_max and scores.confirmation_timing_score < 0) or (
        outcome.did_event_materialize and first_validation is None
    ):
        return EvaluationFailureMode.LATE_CONFIRMATION
    if (not outcome.did_event_materialize) and scores.hypothesis_selection_score <= -2 and scores.calibration_score <= -1:
        return EvaluationFailureMode.FALSE_POSITIVE
    if outcome.did_event_materialize and scores.hypothesis_selection_score <= -1 and scores.calibration_score <= -1:
        return EvaluationFailureMode.FALSE_NEGATIVE
    return EvaluationFailureMode.NONE


def _supporting_reasons(
    *,
    episode,
    outcome: EpisodeEvaluationOutcome,
    scores: EpisodeEvaluationScorecard,
    declared_window: EpisodeEvaluationDeclaredTimeWindow,
    first_validation: datetime | None,
    first_negative_signal: datetime | None,
    first_invalidation: datetime | None,
    context: EpisodeRuleReviewContext,
    peak_prob: float,
) -> list[str]:
    reasons: list[str] = []
    validation_bar = _bar_offset(context=context, timestamp=first_validation)
    if validation_bar is not None and declared_window.bars_min is not None and validation_bar < declared_window.bars_min:
        reasons.append("validation_before_declared_window")
    elif validation_bar is not None and declared_window.bars_max is not None and validation_bar > declared_window.bars_max:
        reasons.append("validation_after_declared_window")
    elif validation_bar is not None:
        reasons.append("validation_within_declared_window")

    if first_negative_signal is not None and first_invalidation is not None:
        lag = (_bar_offset(context=context, timestamp=first_invalidation) or 0) - (_bar_offset(context=context, timestamp=first_negative_signal) or 0)
        reasons.append("invalidation_prompt_after_negative_signals" if lag <= 1 else "invalidation_lagged_after_negative_signals")

    if episode.replacement_event_kind is not None:
        reasons.append(
            "replacement_event_was_tracked"
            if _replacement_was_tracked(context=context, replacement_event=episode.replacement_event_kind)
            else "replacement_event_not_preannounced_in_transition_watch"
        )

    if outcome.did_event_materialize:
        reasons.append("event_materialized")
    elif outcome.did_partial_materialize:
        reasons.append("event_partially_materialized")
    else:
        reasons.append("event_failed_to_materialize")

    reasons.append("confidence_matched_outcome" if scores.calibration_score > 0 else "confidence_misaligned_with_outcome")
    if peak_prob >= 0.74:
        reasons.append("resolved_level_peak_probability_seen")
    elif peak_prob >= 0.56:
        reasons.append("confirming_level_peak_probability_seen")

    if _tracked_before_event(context=context, event_kind=episode.event_kind):
        reasons.append("event_was_tracked_before_materialization")
    elif outcome.did_event_materialize:
        reasons.append("event_materialized_before_being_selected")

    return _unique(reasons)


def _build_tuning_hints(
    *,
    instrument_symbol: str,
    event_kind: TradableEventKind,
    replacement_event: TradableEventKind | None,
    failure_mode: EvaluationFailureMode,
    data_is_degraded: bool,
) -> tuple[list[str], dict[str, str], str]:
    registry = get_parameter_metadata_registry(instrument_symbol)
    event_time_paths = _event_time_window_paths(event_kind)
    candidates: list[str] = []
    directions: dict[str, str] = {}

    def add(path: str, direction: str) -> None:
        if path in registry and path not in candidates:
            candidates.append(path)
            directions[path] = direction

    if failure_mode is EvaluationFailureMode.EARLY_CONFIRMATION:
        add("thresholds.confirming_hypothesis_probability", "increase")
        add("thresholds.resolved_hypothesis_probability", "increase")
        add(event_time_paths["bars_min"], "increase")
    elif failure_mode is EvaluationFailureMode.LATE_CONFIRMATION:
        add("thresholds.confirming_hypothesis_probability", "decrease")
        add(_EVENT_TO_PRIOR_PATH[event_kind], "increase")
        add(event_time_paths["bars_max"], "increase")
    elif failure_mode is EvaluationFailureMode.LATE_INVALIDATION:
        add("thresholds.active_hypothesis_probability", "increase")
        add("thresholds.weakening_drop_threshold", "decrease")
        add(_EVENT_TO_WEIGHT_PATHS[event_kind][0], "decrease")
    elif failure_mode is EvaluationFailureMode.MISSED_TRANSITION:
        add("weights.path_dependency", "increase")
        add("weights.anchor_interaction", "increase")
        if replacement_event is not None:
            add(_EVENT_TO_PRIOR_PATH[replacement_event], "increase")
    elif failure_mode is EvaluationFailureMode.FALSE_POSITIVE:
        add(_EVENT_TO_PRIOR_PATH[event_kind], "decrease")
        add("thresholds.confirming_hypothesis_probability", "increase")
        add(_EVENT_TO_WEIGHT_PATHS[event_kind][0], "decrease")
    elif failure_mode is EvaluationFailureMode.FALSE_NEGATIVE:
        add(_EVENT_TO_PRIOR_PATH[event_kind], "increase")
        add("thresholds.active_hypothesis_probability", "decrease")
        add(_EVENT_TO_WEIGHT_PATHS[event_kind][0], "increase")

    confidence = "low" if (failure_mode is EvaluationFailureMode.NONE or data_is_degraded) else "medium"
    return candidates, directions, confidence


def _tracked_before_event(*, context: EpisodeRuleReviewContext, event_kind: TradableEventKind) -> bool:
    prior = context.prior_belief
    if prior is None:
        return False
    if _event_rank(prior, event_kind) <= 2:
        return True
    return bool(set(prior.transition_watch) & _EVENT_TO_WATCH_LABELS[event_kind])


def _replacement_was_tracked(*, context: EpisodeRuleReviewContext, replacement_event: TradableEventKind) -> bool:
    watches = set(context.initial_belief.transition_watch)
    if context.prior_belief is not None:
        watches.update(context.prior_belief.transition_watch)
    return bool(watches & _EVENT_TO_WATCH_LABELS[replacement_event])


def _event_rank(belief: BeliefStateSnapshot, event_kind: TradableEventKind) -> int:
    for index, state in enumerate(belief.event_hypotheses, start=1):
        if state.mapped_event_kind == event_kind:
            return index
    return 99


def _bar_offset(*, context: EpisodeRuleReviewContext, timestamp: datetime | None) -> int | None:
    if timestamp is None:
        return None
    for index, (belief, _) in enumerate(context.event_states, start=1):
        if belief.observed_at == timestamp:
            return index
    return None


def _bar_offset_from_window(*, started_at: datetime, sequence_end: datetime, timestamp: datetime | None) -> int | None:
    if timestamp is None or timestamp < started_at or timestamp > sequence_end:
        return None
    return int(((timestamp - started_at).total_seconds() // 60) + 1)


def _anchor_context(belief: BeliefStateSnapshot) -> list[str]:
    labels = []
    for anchor in belief.active_anchors[:4]:
        suffix = "nearby"
        if anchor.distance_ticks is not None and anchor.distance_ticks <= 0:
            suffix = "at_price"
        labels.append(f"{anchor.anchor_type}_{suffix}")
    return _unique(labels)


def _event_time_window_paths(event_kind: TradableEventKind) -> dict[str, str]:
    if event_kind is TradableEventKind.MOMENTUM_CONTINUATION:
        base = "time_windows.momentum_continuation.normal"
    elif event_kind is TradableEventKind.BALANCE_MEAN_REVERSION:
        base = "time_windows.balance_mean_reversion.normal"
    else:
        base = "time_windows.absorption_to_reversal_preparation.normal"
    return {
        "bars_min": f"{base}.bars_min",
        "bars_max": f"{base}.bars_max",
    }


def _infer_context_from_repository(
    *,
    repository: AnalysisRepository,
    instrument_symbol: str,
    window_start: datetime,
    window_end: datetime,
) -> tuple[str | None, str | None]:
    session: str | None = None
    bar_tf: str | None = None
    for item in repository.list_ingestions(
        instrument_symbol=instrument_symbol,
        limit=50,
        stored_at_after=window_start,
        stored_at_before=window_end,
    ):
        payload = item.observed_payload
        if bar_tf is None and isinstance(payload, dict):
            timeframe = payload.get("bar_timeframe")
            if isinstance(timeframe, str) and timeframe:
                bar_tf = timeframe
        if session is None and isinstance(payload, dict):
            session_context = payload.get("session_context")
            if isinstance(session_context, dict):
                session_code = session_context.get("session_code")
                if isinstance(session_code, str) and session_code:
                    session = session_code
            process_context = payload.get("process_context")
            if session is None and isinstance(process_context, dict):
                windows = process_context.get("session_windows")
                if isinstance(windows, list) and windows:
                    first = windows[0]
                    if isinstance(first, dict):
                        session_code = first.get("session_code")
                        if isinstance(session_code, str) and session_code:
                            session = session_code
        if session is not None and bar_tf is not None:
            break
    return session, bar_tf


def _phase_rank(phase: EventPhase) -> int:
    order = {
        EventPhase.EMERGING: 0,
        EventPhase.BUILDING: 1,
        EventPhase.CONFIRMING: 2,
        EventPhase.WEAKENING: 3,
        EventPhase.RESOLVED: 4,
        EventPhase.INVALIDATED: 5,
    }
    return order[phase]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
