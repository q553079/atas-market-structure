from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable, Protocol
from uuid import uuid4

from atas_market_structure.models import (
    BeliefStateSnapshot,
    DegradedMode,
    EpisodeEvaluation,
    EvaluationFailureMode,
    InstrumentProfile,
    InstrumentProfileParameterMetadata,
    OfflineReplayValidationSummary,
    PatchHumanApproval,
    PatchPromotionHistoryEntry,
    PatchValidationStatus,
    ProfilePatchCandidate,
    ProfilePatchValidationResult,
    RecognizerBuild,
    TradableEventKind,
    TuningAnalysisWindow,
    TuningDegradationStatistics,
    TuningFailureModeSummary,
    TuningInputBundle,
    TuningPatchHistoryEntry,
    TuningPositiveNegativeSummary,
    TuningRecommendation,
    TuningRecommendationItem,
)
from atas_market_structure.profile_services import InstrumentProfileService, get_parameter_metadata_registry
from atas_market_structure.repository import AnalysisRepository


TUNING_INPUT_BUNDLE_SCHEMA_VERSION = "tuning_input_bundle_v1"
TUNING_RECOMMENDATION_SCHEMA_VERSION = "tuning_recommendation_v1"
LOCAL_TUNING_ADVISOR_KIND = "offline_stub_v1"
PATCH_CANDIDATE_STATUS_AWAITING_REPLAY = "awaiting_offline_replay"
PATCH_CANDIDATE_STATUS_BOUNDARY_REJECTED = "boundary_rejected"

_SCORE_FIELDS = (
    "hypothesis_selection_score",
    "confirmation_timing_score",
    "invalidation_timing_score",
    "transition_handling_score",
    "calibration_score",
)


class OfflineTuningAiAdapter(Protocol):
    """Contract for an offline-only AI tuning adapter."""

    def generate_recommendation(
        self,
        *,
        bundle: TuningInputBundle,
        profile_service: InstrumentProfileService,
    ) -> tuple[TuningRecommendation, ProfilePatchCandidate | None, ProfilePatchValidationResult | None]:
        """Build one structured recommendation from a bundle."""


class OfflineReplayPatchValidator(Protocol):
    """Contract for the non-critical-path offline replay validator hook."""

    def validate(
        self,
        *,
        bundle: TuningInputBundle,
        recommendation: TuningRecommendation,
        candidate: ProfilePatchCandidate,
        boundary_validation: ProfilePatchValidationResult,
    ) -> OfflineReplayValidationSummary:
        """Return an offline replay validation summary for one candidate patch."""


@dataclass(frozen=True)
class TuningAdvisoryRun:
    """Full offline tuning advisory result for one instrument or bundle."""

    bundle: TuningInputBundle
    recommendation: TuningRecommendation
    patch_candidate: ProfilePatchCandidate | None
    validation_result: ProfilePatchValidationResult | None


@dataclass
class _ParameterVote:
    """Aggregated recommendation vote for one profile parameter."""

    path: str
    support_count: int = 0
    direction_counts: Counter[str] = field(default_factory=Counter)
    failure_mode_counts: Counter[EvaluationFailureMode] = field(default_factory=Counter)
    event_kind_counts: Counter[TradableEventKind] = field(default_factory=Counter)
    reason_counts: Counter[str] = field(default_factory=Counter)


class TuningBundleBuilder:
    """Build `tuning_input_bundle_v1` from repository-backed profile, episode, and ops history."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def build_for_instrument(
        self,
        instrument_symbol: str,
        *,
        episode_limit: int = 40,
        patch_history_limit: int = 12,
        belief_limit: int = 200,
    ) -> TuningInputBundle:
        """Assemble a deterministic bundle for the requested instrument."""

        profile_record = self._repository.get_active_instrument_profile(instrument_symbol)
        if profile_record is None:
            raise ValueError(f"no active instrument profile for {instrument_symbol}")
        profile = InstrumentProfile.model_validate(profile_record.profile_payload)

        episode_records = self._repository.list_event_episodes(
            instrument_symbol=instrument_symbol,
            limit=episode_limit,
        )
        episodes = sorted(
            (self._model_validate(item.episode_payload) for item in episode_records),
            key=lambda item: item.started_at,
        )
        evaluations: list[EpisodeEvaluation] = []
        unevaluated_episode_ids: list[str] = []
        for episode in episodes:
            stored = self._repository.get_episode_evaluation(episode.episode_id)
            if stored is None:
                unevaluated_episode_ids.append(episode.episode_id)
                continue
            evaluations.append(EpisodeEvaluation.model_validate(stored.evaluation_payload))
        evaluations.sort(key=lambda item: item.market_time_start)

        build = self._resolve_recognizer_build(
            profile=profile,
            episodes=episodes,
            evaluations=evaluations,
        )
        beliefs = [
            BeliefStateSnapshot.model_validate(item.belief_payload)
            for item in self._repository.list_belief_states(
                instrument_symbol=instrument_symbol,
                limit=belief_limit,
            )
        ]
        beliefs.sort(key=lambda item: item.observed_at)
        patch_history = self._load_patch_history(
            instrument_symbol=instrument_symbol,
            limit=patch_history_limit,
        )

        return TuningInputBundle(
            bundle_id=f"bundle-{uuid4().hex}",
            instrument_symbol=profile.instrument_symbol,
            schema_version=TUNING_INPUT_BUNDLE_SCHEMA_VERSION,
            built_at=datetime.now(tz=UTC),
            profile_version=profile.profile_version,
            engine_version=build.engine_version,
            analysis_window=_build_analysis_window(episodes=episodes, evaluations=evaluations),
            instrument_profile=profile,
            recognizer_build=build,
            recent_closed_episodes=episodes,
            episode_evaluations=evaluations,
            positive_negative_summary=_build_positive_negative_summary(
                episodes=episodes,
                evaluations=evaluations,
            ),
            patch_history=patch_history,
            degradation_statistics=_build_degradation_statistics(beliefs),
            unevaluated_episode_ids=unevaluated_episode_ids,
        )

    @staticmethod
    def _model_validate(payload: dict[str, Any]):
        from atas_market_structure.models import EventEpisode

        return EventEpisode.model_validate(payload)

    def _resolve_recognizer_build(
        self,
        *,
        profile: InstrumentProfile,
        episodes: list[Any],
        evaluations: list[EpisodeEvaluation],
    ) -> RecognizerBuild:
        active_build = self._repository.get_active_recognizer_build()
        if active_build is not None:
            raw_notes = active_build.build_payload.get("notes", [])
            notes = raw_notes if isinstance(raw_notes, list) else [str(raw_notes)] if raw_notes else []
            return RecognizerBuild(
                engine_version=active_build.engine_version,
                schema_version=active_build.schema_version,
                ontology_version=active_build.ontology_version,
                is_active=active_build.is_active,
                status=active_build.status,
                notes=notes,
                created_at=active_build.created_at,
            )

        fallback_engine_version = (
            evaluations[-1].engine_version
            if evaluations
            else episodes[-1].engine_version
            if episodes
            else "unknown"
        )
        return RecognizerBuild(
            engine_version=fallback_engine_version,
            schema_version="recognizer_build_v1",
            ontology_version=profile.ontology_version,
            is_active=False,
            status="missing_registry_record",
            notes=["No active recognizer_build row was found; bundle uses a derived placeholder."],
            created_at=datetime.now(tz=UTC),
        )

    def _load_patch_history(
        self,
        *,
        instrument_symbol: str,
        limit: int,
    ) -> list[TuningPatchHistoryEntry]:
        history: list[TuningPatchHistoryEntry] = []
        for row in self._repository.list_profile_patch_candidates(
            instrument_symbol=instrument_symbol,
            limit=limit,
        ):
            candidate = ProfilePatchCandidate.model_validate(row.patch_payload)
            latest_validation = None
            validation_rows = self._repository.list_patch_validation_results(
                candidate_id=row.candidate_id,
                limit=1,
            )
            if validation_rows:
                latest_validation = ProfilePatchValidationResult.model_validate(
                    validation_rows[0].validation_payload,
                )
            latest_promotion = None
            promotion_rows = self._repository.list_patch_promotions(
                candidate_id=row.candidate_id,
                limit=1,
            )
            if promotion_rows:
                latest_promotion = PatchPromotionHistoryEntry(
                    promotion_id=promotion_rows[0].promotion_id,
                    candidate_id=promotion_rows[0].candidate_id,
                    instrument_symbol=promotion_rows[0].instrument_symbol,
                    promoted_profile_version=promotion_rows[0].promoted_profile_version,
                    previous_profile_version=promotion_rows[0].previous_profile_version,
                    promoted_at=promotion_rows[0].promoted_at,
                    promoted_by=promotion_rows[0].promoted_by,
                    promotion_notes=promotion_rows[0].promotion_notes,
                )
            history.append(
                TuningPatchHistoryEntry(
                    candidate=candidate,
                    latest_validation_result=latest_validation,
                    latest_promotion=latest_promotion,
                ),
            )
        history.sort(key=lambda item: item.candidate.created_at, reverse=True)
        return history


class LocalStubOfflineReplayValidator:
    """Deterministic placeholder validator that records replay-compare intent without executing it."""

    def validate(
        self,
        *,
        bundle: TuningInputBundle,
        recommendation: TuningRecommendation,
        candidate: ProfilePatchCandidate,
        boundary_validation: ProfilePatchValidationResult,
    ) -> OfflineReplayValidationSummary:
        """Return a structured placeholder until the full replay compare runner is wired in."""

        now = datetime.now(tz=UTC)
        if boundary_validation.validation_status is PatchValidationStatus.REJECTED:
            return OfflineReplayValidationSummary(
                status="not_run",
                runner="local_stub",
                compared_episode_count=bundle.analysis_window.evaluation_count,
                metrics={"proposed_parameter_count": float(len(candidate.candidate_parameters))},
                summary="Offline replay compare skipped because boundary validation rejected the patch candidate.",
                notes=["Replay compare must not run on candidates that already failed bounded parameter validation."],
                validated_at=now,
            )
        return OfflineReplayValidationSummary(
            status="not_run",
            runner="local_stub",
            compared_episode_count=bundle.analysis_window.evaluation_count,
            metrics={
                "proposed_parameter_count": float(len(candidate.candidate_parameters)),
                "top_failure_mode_count": float(len(recommendation.top_failure_modes)),
            },
            summary="Local stub validator recorded the candidate for later offline replay compare; no replay was executed in V1.",
            notes=[
                "This hook is intentionally off the recognition critical path.",
                "Promotion remains blocked until a replay compare run and human approval are both completed.",
            ],
            validated_at=now,
        )


class HeuristicOfflineTuningAdapter:
    """Deterministic offline advisor that converts episode evaluations into bounded tuning proposals."""

    def generate_recommendation(
        self,
        *,
        bundle: TuningInputBundle,
        profile_service: InstrumentProfileService,
    ) -> tuple[TuningRecommendation, ProfilePatchCandidate | None, ProfilePatchValidationResult | None]:
        """Generate a recommendation and optional bounded patch candidate."""

        now = datetime.now(tz=UTC)
        recommendation_id = f"tune-{uuid4().hex}"
        failure_summaries = _build_failure_mode_summaries(bundle.episode_evaluations)
        items = self._build_recommendation_items(bundle)
        candidate: ProfilePatchCandidate | None = None
        validation: ProfilePatchValidationResult | None = None

        if items:
            patch_payload = {item.parameter: item.proposed_value for item in items}
            candidate, validation = profile_service.validate_patch(
                base_profile=bundle.instrument_profile,
                patch=patch_payload,
                proposed_profile_version=_derive_candidate_profile_version(bundle.instrument_profile.profile_version),
                recommendation_id=recommendation_id,
                persist=False,
            )

        recommendation = TuningRecommendation(
            recommendation_id=recommendation_id,
            bundle_id=bundle.bundle_id,
            instrument_symbol=bundle.instrument_symbol,
            schema_version=TUNING_RECOMMENDATION_SCHEMA_VERSION,
            profile_version=bundle.profile_version,
            engine_version=bundle.engine_version,
            generated_at=now,
            advisor_kind=LOCAL_TUNING_ADVISOR_KIND,
            analysis_window=bundle.analysis_window,
            top_failure_modes=failure_summaries,
            recommendations=items,
            expected_improvement=_expected_improvement_summary(
                failure_summaries=failure_summaries,
                items=items,
            ),
            risk=_top_level_risk(candidate=candidate, items=items),
            confidence=_overall_confidence(
                items=items,
                evaluation_count=bundle.analysis_window.evaluation_count,
            ),
            patch_candidate_ref=candidate.candidate_id if candidate is not None else None,
        )
        return recommendation, candidate, validation

    def _build_recommendation_items(self, bundle: TuningInputBundle) -> list[TuningRecommendationItem]:
        metadata = get_parameter_metadata_registry(bundle.instrument_symbol)
        profile_payload = bundle.instrument_profile.model_dump(mode="python")
        votes = _collect_parameter_votes(bundle.episode_evaluations)
        ranked_votes = sorted(
            votes.values(),
            key=lambda item: (
                item.support_count,
                max(item.direction_counts.values(), default=0),
                item.path,
            ),
            reverse=True,
        )

        items: list[TuningRecommendationItem] = []
        for vote in ranked_votes[:5]:
            meta = metadata.get(vote.path)
            if meta is None:
                continue
            direction, direction_count = _dominant_direction(vote.direction_counts)
            if direction is None or direction == "hold":
                continue
            current_value = _get_path(profile_payload, vote.path)
            if current_value is None:
                continue
            proposed_value = _propose_bounded_value(
                current_value=current_value,
                meta=meta,
                direction=direction,
                support_count=vote.support_count,
            )
            if proposed_value == current_value:
                continue
            reason_code = vote.reason_counts.most_common(1)[0][0] if vote.reason_counts else vote.path
            dominant_failure_mode = (
                vote.failure_mode_counts.most_common(1)[0][0]
                if vote.failure_mode_counts
                else None
            )
            event_kind = vote.event_kind_counts.most_common(1)[0][0] if vote.event_kind_counts else None
            items.append(
                TuningRecommendationItem(
                    event_kind=event_kind,
                    parameter=vote.path,
                    direction=direction,
                    current_value=current_value,
                    proposed_value=proposed_value,
                    support_count=vote.support_count,
                    reason=_build_reason(
                        failure_mode=dominant_failure_mode,
                        reason_code=reason_code,
                        direction=direction,
                    ),
                    expected_improvement=_build_expected_improvement(
                        failure_mode=dominant_failure_mode,
                        event_kind=event_kind,
                    ),
                    risk=_parameter_risk(meta),
                    confidence=_item_confidence(
                        support_count=vote.support_count,
                        evaluation_count=max(bundle.analysis_window.evaluation_count, 1),
                        direction_agreement=direction_count / vote.support_count,
                    ),
                ),
            )
        return items


class TuningAdvisorService:
    """Orchestrate bundle building, offline recommendation, and patch validation scaffolding."""

    def __init__(
        self,
        *,
        repository: AnalysisRepository | None = None,
        bundle_builder: TuningBundleBuilder | None = None,
        profile_service: InstrumentProfileService | None = None,
        adapter: OfflineTuningAiAdapter | None = None,
        replay_validator: OfflineReplayPatchValidator | None = None,
    ) -> None:
        self._repository = repository
        self._bundle_builder = bundle_builder or (
            TuningBundleBuilder(repository) if repository is not None else None
        )
        self._profile_service = profile_service or InstrumentProfileService(repository=repository)
        self._adapter = adapter or HeuristicOfflineTuningAdapter()
        self._replay_validator = replay_validator or LocalStubOfflineReplayValidator()

    def build_bundle_for_instrument(
        self,
        instrument_symbol: str,
        *,
        episode_limit: int = 40,
        patch_history_limit: int = 12,
        belief_limit: int = 200,
    ) -> TuningInputBundle:
        """Build a repository-backed tuning bundle for the requested instrument."""

        if self._bundle_builder is None:
            raise RuntimeError("repository-backed bundle building requires a repository")
        return self._bundle_builder.build_for_instrument(
            instrument_symbol,
            episode_limit=episode_limit,
            patch_history_limit=patch_history_limit,
            belief_limit=belief_limit,
        )

    def recommend_for_bundle(
        self,
        bundle: TuningInputBundle,
        *,
        persist: bool = False,
    ) -> TuningAdvisoryRun:
        """Generate a recommendation and validation scaffold from a prepared bundle."""

        recommendation, candidate, boundary_validation = self._adapter.generate_recommendation(
            bundle=bundle,
            profile_service=self._profile_service,
        )
        final_validation = None
        if candidate is not None and boundary_validation is not None:
            offline_summary = self._replay_validator.validate(
                bundle=bundle,
                recommendation=recommendation,
                candidate=candidate,
                boundary_validation=boundary_validation,
            )
            human_approval = PatchHumanApproval()
            final_validation = boundary_validation.model_copy(
                update={
                    "recommendation_id": recommendation.recommendation_id,
                    "base_profile_version": candidate.base_profile_version,
                    "proposed_profile_version": candidate.proposed_profile_version,
                    "boundary_validation_status": boundary_validation.validation_status,
                    "offline_replay_validation": offline_summary,
                    "human_approval": human_approval,
                    "promotion_ready": (
                        boundary_validation.validation_status is PatchValidationStatus.ACCEPTED
                        and offline_summary.status == "passed"
                        and human_approval.status == "approved"
                    ),
                },
            )

        if persist:
            self._persist_recommendation(recommendation)
            if candidate is not None and final_validation is not None:
                self._persist_candidate_and_validation(
                    candidate=candidate,
                    validation=final_validation,
                )

        return TuningAdvisoryRun(
            bundle=bundle,
            recommendation=recommendation,
            patch_candidate=candidate,
            validation_result=final_validation,
        )

    def recommend_for_instrument(
        self,
        instrument_symbol: str,
        *,
        episode_limit: int = 40,
        patch_history_limit: int = 12,
        belief_limit: int = 200,
        persist: bool = False,
    ) -> TuningAdvisoryRun:
        """Build a bundle from repository state, then generate the tuning advisory output."""

        bundle = self.build_bundle_for_instrument(
            instrument_symbol,
            episode_limit=episode_limit,
            patch_history_limit=patch_history_limit,
            belief_limit=belief_limit,
        )
        return self.recommend_for_bundle(bundle, persist=persist)

    def _persist_recommendation(self, recommendation: TuningRecommendation) -> None:
        if self._repository is None:
            return
        self._repository.save_tuning_recommendation(
            recommendation_id=recommendation.recommendation_id,
            instrument_symbol=recommendation.instrument_symbol,
            market_time=recommendation.generated_at,
            ingested_at=recommendation.generated_at,
            schema_version=recommendation.schema_version,
            profile_version=recommendation.profile_version,
            engine_version=recommendation.engine_version,
            episode_id=None,
            evaluation_id=None,
            source_kind=recommendation.advisor_kind,
            recommendation_payload=recommendation.model_dump(mode="json", by_alias=True),
        )

    def _persist_candidate_and_validation(
        self,
        *,
        candidate: ProfilePatchCandidate,
        validation: ProfilePatchValidationResult,
    ) -> None:
        if self._repository is None:
            return
        self._repository.save_profile_patch_candidate(
            candidate_id=candidate.candidate_id,
            instrument_symbol=candidate.instrument_symbol,
            market_time=candidate.created_at,
            ingested_at=candidate.created_at,
            schema_version=candidate.schema_version,
            base_profile_version=candidate.base_profile_version,
            proposed_profile_version=candidate.proposed_profile_version,
            recommendation_id=candidate.recommendation_id,
            status=(
                PATCH_CANDIDATE_STATUS_AWAITING_REPLAY
                if validation.validation_status is PatchValidationStatus.ACCEPTED
                else PATCH_CANDIDATE_STATUS_BOUNDARY_REJECTED
            ),
            patch_payload=candidate.model_dump(mode="json", by_alias=True),
        )
        self._repository.save_patch_validation_result(
            validation_result_id=f"pvr-{uuid4().hex}",
            instrument_symbol=validation.instrument_symbol,
            market_time=validation.validated_at,
            ingested_at=validation.validated_at,
            schema_version=validation.schema_version,
            candidate_id=validation.candidate_id,
            validation_status=validation.validation_status.value,
            validation_payload=validation.model_dump(mode="json"),
        )


def _build_analysis_window(
    *,
    episodes: list[Any],
    evaluations: list[EpisodeEvaluation],
) -> TuningAnalysisWindow:
    if episodes:
        date_from = min(item.started_at for item in episodes)
        date_to = max(item.ended_at for item in episodes)
    elif evaluations:
        date_from = min(item.market_time_start for item in evaluations)
        date_to = max(item.market_time_end for item in evaluations)
    else:
        date_from = None
        date_to = None
    return TuningAnalysisWindow(
        episode_count=len(episodes),
        evaluation_count=len(evaluations),
        date_from=date_from,
        date_to=date_to,
    )


def _build_positive_negative_summary(
    *,
    episodes: list[Any],
    evaluations: list[EpisodeEvaluation],
) -> TuningPositiveNegativeSummary:
    failure_counts = Counter(item.diagnosis.primary_failure_mode.value for item in evaluations)
    event_counts = Counter(item.evaluated_event_kind.value for item in evaluations)
    positive = sum(1 for item in evaluations if item.diagnosis.primary_failure_mode is EvaluationFailureMode.NONE)
    negative = len(evaluations) - positive
    average_scores: dict[str, float] = {}
    if evaluations:
        for field_name in _SCORE_FIELDS:
            average_scores[field_name] = round(
                sum(getattr(item.scores, field_name) for item in evaluations) / len(evaluations),
                4,
            )
    return TuningPositiveNegativeSummary(
        positive_episode_count=positive,
        negative_episode_count=negative,
        unevaluated_episode_count=max(len(episodes) - len(evaluations), 0),
        failure_mode_counts=dict(sorted(failure_counts.items())),
        event_kind_counts=dict(sorted(event_counts.items())),
        average_scores=average_scores,
    )


def _build_degradation_statistics(
    beliefs: Iterable[BeliefStateSnapshot],
) -> TuningDegradationStatistics | None:
    ordered_beliefs = list(beliefs)
    if not ordered_beliefs:
        return None
    degraded_mode_counts: Counter[str] = Counter()
    degraded_belief_count = 0
    depth_unavailable_count = 0
    dom_unavailable_count = 0
    ai_unavailable_count = 0

    for belief in ordered_beliefs:
        status = belief.data_status
        active_modes = [mode for mode in status.degraded_modes if mode is not DegradedMode.NONE]
        if active_modes:
            degraded_belief_count += 1
        for mode in active_modes:
            degraded_mode_counts[mode.value] += 1
        if not status.depth_available:
            depth_unavailable_count += 1
        if not status.dom_available:
            dom_unavailable_count += 1
        if not status.ai_available:
            ai_unavailable_count += 1

    latest_status = ordered_beliefs[-1].data_status
    return TuningDegradationStatistics(
        belief_sample_count=len(ordered_beliefs),
        degraded_belief_count=degraded_belief_count,
        degraded_mode_counts=dict(sorted(degraded_mode_counts.items())),
        depth_unavailable_count=depth_unavailable_count,
        dom_unavailable_count=dom_unavailable_count,
        ai_unavailable_count=ai_unavailable_count,
        latest_freshness=latest_status.freshness,
        latest_completeness=latest_status.completeness,
    )


def _build_failure_mode_summaries(
    evaluations: Iterable[EpisodeEvaluation],
) -> list[TuningFailureModeSummary]:
    grouped: defaultdict[EvaluationFailureMode, list[EpisodeEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        mode = evaluation.diagnosis.primary_failure_mode
        if mode is EvaluationFailureMode.NONE:
            continue
        grouped[mode].append(evaluation)
    summaries: list[TuningFailureModeSummary] = []
    for mode, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].value)):
        event_counts = Counter(evaluation.evaluated_event_kind.value for evaluation in items)
        top_event = event_counts.most_common(1)[0][0] if event_counts else "unknown_event"
        summaries.append(
            TuningFailureModeSummary(
                kind=mode,
                count=len(items),
                summary=f"{top_event} shows recurring {mode.value} across {len(items)} recent evaluations.",
            ),
        )
    return summaries[:3]


def _collect_parameter_votes(
    evaluations: Iterable[EpisodeEvaluation],
) -> dict[str, _ParameterVote]:
    votes: dict[str, _ParameterVote] = {}
    for evaluation in evaluations:
        failure_mode = evaluation.diagnosis.primary_failure_mode
        if failure_mode is EvaluationFailureMode.NONE:
            continue
        reason_codes = evaluation.diagnosis.supporting_reasons or [failure_mode.value]
        for path in evaluation.diagnosis.candidate_parameters:
            direction = evaluation.diagnosis.suggested_direction.get(path, "hold")
            vote = votes.setdefault(path, _ParameterVote(path=path))
            vote.support_count += 1
            vote.direction_counts[direction] += 1
            vote.failure_mode_counts[failure_mode] += 1
            vote.event_kind_counts[evaluation.evaluated_event_kind] += 1
            for code in reason_codes[:3]:
                vote.reason_counts[code] += 1
    return votes


def _dominant_direction(direction_counts: Counter[str]) -> tuple[str | None, int]:
    filtered = [(direction, count) for direction, count in direction_counts.items() if direction != "hold"]
    if not filtered:
        return None, 0
    filtered.sort(key=lambda item: (-item[1], item[0]))
    return filtered[0]


def _propose_bounded_value(
    *,
    current_value: float | int,
    meta: InstrumentProfileParameterMetadata,
    direction: str,
    support_count: int,
) -> float | int:
    step_multiplier = 1 if support_count < 3 else 2 if support_count < 6 else 3
    delta = meta.step * step_multiplier
    if direction == "increase":
        proposed = float(current_value) + delta
    elif direction == "decrease":
        proposed = float(current_value) - delta
    else:
        proposed = float(current_value)
    proposed = min(max(proposed, meta.min), meta.max)
    if meta.value_type == "int":
        bounded = int(round(proposed))
        bounded = max(int(meta.min), min(int(meta.max), bounded))
        return bounded
    return round(proposed, _decimal_places(meta.step))


def _build_reason(
    *,
    failure_mode: EvaluationFailureMode | None,
    reason_code: str,
    direction: str,
) -> str:
    if failure_mode is None:
        return f"Recent evaluations repeatedly pointed to {reason_code}; propose to {direction} the bounded parameter."
    return f"Recent {failure_mode.value} diagnoses repeatedly surfaced {reason_code}; propose to {direction} the bounded parameter."


def _build_expected_improvement(
    *,
    failure_mode: EvaluationFailureMode | None,
    event_kind: TradableEventKind | None,
) -> str:
    if failure_mode is None:
        return "tighten parameter behavior for offline replay review"
    if event_kind is None:
        return f"reduce recurring {failure_mode.value} outcomes"
    return f"reduce recurring {failure_mode.value} outcomes in {event_kind.value}"


def _parameter_risk(meta: InstrumentProfileParameterMetadata) -> str:
    if meta.criticality.value == "critical":
        return "critical parameter; offline replay compare and human approval remain mandatory"
    if meta.criticality.value == "high":
        return "high-impact parameter; validate on replay before promoting"
    return "bounded parameter change still requires offline replay and explicit approval"


def _item_confidence(
    *,
    support_count: int,
    evaluation_count: int,
    direction_agreement: float,
) -> str:
    if support_count >= 4 and evaluation_count >= 6 and direction_agreement >= 0.75:
        return "high"
    if support_count >= 2 and direction_agreement >= 0.60:
        return "medium"
    return "low"


def _expected_improvement_summary(
    *,
    failure_summaries: list[TuningFailureModeSummary],
    items: list[TuningRecommendationItem],
) -> str:
    if not items:
        return "No bounded patch candidate was generated because no dominant recurring failure cluster was detected."
    if not failure_summaries:
        return "Apply offline replay review to confirm whether bounded parameter changes improve recent calibration."
    top_modes = ", ".join(item.kind.value for item in failure_summaries[:2])
    return f"Target the dominant failure clusters ({top_modes}) with bounded offline-only parameter candidates."


def _top_level_risk(
    *,
    candidate: ProfilePatchCandidate | None,
    items: list[TuningRecommendationItem],
) -> str:
    if not items:
        return "No auto-apply path exists; recommendation is informational only."
    if candidate is None or not candidate.risk_notes:
        return "All proposed changes remain subject to boundary validation, offline replay compare, and human approval."
    return "; ".join(candidate.risk_notes[:2])


def _overall_confidence(
    *,
    items: list[TuningRecommendationItem],
    evaluation_count: int,
) -> str:
    if not items:
        return "low"
    item_levels = {item.confidence for item in items}
    if "high" in item_levels and evaluation_count >= 6:
        return "high"
    if "medium" in item_levels or evaluation_count >= 3:
        return "medium"
    return "low"


def _derive_candidate_profile_version(base_profile_version: str) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    return f"{base_profile_version}.candidate.{timestamp}"


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _decimal_places(step: float) -> int:
    text = f"{step:.8f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".", maxsplit=1)[1])
