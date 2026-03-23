from __future__ import annotations

from datetime import UTC, datetime

from atas_market_structure.ingestion_reliability_services import IngestionReliabilityService
from atas_market_structure.models import (
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EvaluationFailureMode,
    EventEpisode,
    IngestionHealthResponse,
    InstrumentProfile,
    ProfilePatchCandidate,
    ProfilePatchValidationResult,
    RecognizerBuild,
    ReplayProjectionQuery,
    ReplayProjectionTimelineEntry,
    ReplayWorkbenchBeliefTimelineEntry,
    ReplayWorkbenchBeliefTimelineEnvelope,
    ReplayWorkbenchEpisodeEvaluationItem,
    ReplayWorkbenchEpisodeEvaluationListEnvelope,
    ReplayWorkbenchEpisodeReviewEnvelope,
    ReplayWorkbenchEpisodeReviewItem,
    ReplayWorkbenchHealthStatusEnvelope,
    ReplayWorkbenchProfileEngineEnvelope,
    ReplayWorkbenchProjectionEnvelope,
    ReplayWorkbenchTuningReviewEnvelope,
    ReplayWorkbenchTuningReviewItem,
    TuningRecommendation,
)
from atas_market_structure.repository import AnalysisRepository


class ReplayWorkbenchProjectionService:
    """Build replay/workbench read models without moving recognition into the UI layer."""

    def __init__(
        self,
        *,
        repository: AnalysisRepository,
        ingestion_reliability_service: IngestionReliabilityService,
    ) -> None:
        self._repository = repository
        self._ingestion_reliability_service = ingestion_reliability_service

    def get_belief_state_timeline(self, query: ReplayProjectionQuery) -> ReplayWorkbenchBeliefTimelineEnvelope:
        """Return a timeline-friendly belief-state view for one instrument and time window."""

        beliefs = self._load_beliefs(query)
        return ReplayWorkbenchBeliefTimelineEnvelope(
            query=query,
            current_belief=beliefs[0] if beliefs else None,
            items=[
                ReplayWorkbenchBeliefTimelineEntry(
                    market_time=belief.observed_at,
                    session_date=belief.observed_at.date().isoformat(),
                    belief_state_id=belief.belief_state_id,
                    top_regimes=_format_top_regimes(belief),
                    top_event_hypotheses=_format_top_hypotheses(belief),
                    degraded_badges=_data_status_badges(belief.data_status),
                    freshness=belief.data_status.freshness,
                    completeness=belief.data_status.completeness,
                    belief=belief,
                )
                for belief in beliefs
            ],
        )

    def get_event_episode_reviews(self, query: ReplayProjectionQuery) -> ReplayWorkbenchEpisodeReviewEnvelope:
        """Return closed episodes paired with their latest stored evaluations when available."""

        episodes = self._load_episodes(query)
        evaluations_by_episode_id = {
            item.episode_id: item
            for item in self._load_evaluations(query)
        }
        items: list[ReplayWorkbenchEpisodeReviewItem] = []
        for episode in episodes:
            evaluation = evaluations_by_episode_id.get(episode.episode_id)
            if evaluation is None:
                stored_evaluation = self._repository.get_episode_evaluation(episode.episode_id)
                evaluation = (
                    EpisodeEvaluation.model_validate(stored_evaluation.evaluation_payload)
                    if stored_evaluation is not None
                    else None
                )
            primary_failure = evaluation.diagnosis.primary_failure_mode if evaluation is not None else None
            items.append(
                ReplayWorkbenchEpisodeReviewItem(
                    market_time=episode.ended_at,
                    session_date=episode.ended_at.date().isoformat(),
                    summary_status=_episode_summary_status(episode, evaluation),
                    primary_failure_mode=primary_failure,
                    episode=episode,
                    evaluation=evaluation,
                ),
            )
        return ReplayWorkbenchEpisodeReviewEnvelope(query=query, items=items)

    def get_episode_evaluations(self, query: ReplayProjectionQuery) -> ReplayWorkbenchEpisodeEvaluationListEnvelope:
        """Return timeline-friendly episode evaluations with linked episode context."""

        episodes_by_id = {
            item.episode_id: item
            for item in self._load_episodes(query, limit=max(query.limit * 2, query.limit))
        }
        items: list[ReplayWorkbenchEpisodeEvaluationItem] = []
        for evaluation in self._load_evaluations(query):
            episode = episodes_by_id.get(evaluation.episode_id)
            if episode is None:
                stored_episode = self._repository.get_event_episode(evaluation.episode_id)
                episode = (
                    EventEpisode.model_validate(stored_episode.episode_payload)
                    if stored_episode is not None
                    else None
                )
            items.append(
                ReplayWorkbenchEpisodeEvaluationItem(
                    market_time=evaluation.evaluated_at,
                    session_date=evaluation.evaluated_at.date().isoformat(),
                    primary_failure_mode=evaluation.diagnosis.primary_failure_mode,
                    candidate_parameters=evaluation.diagnosis.candidate_parameters,
                    episode=episode,
                    evaluation=evaluation,
                ),
            )
        return ReplayWorkbenchEpisodeEvaluationListEnvelope(query=query, items=items)

    def get_tuning_reviews(self, query: ReplayProjectionQuery) -> ReplayWorkbenchTuningReviewEnvelope:
        """Return stored tuning recommendations enriched with patch candidate state."""

        recommendations = self._load_recommendations(query)
        candidates = self._repository.list_profile_patch_candidates(
            instrument_symbol=query.instrument_symbol,
            limit=max(query.limit * 3, query.limit),
        )
        candidates_by_recommendation_id: dict[str, tuple[ProfilePatchCandidate, str]] = {}
        validations_by_candidate_id: dict[str, ProfilePatchValidationResult] = {}
        for row in candidates:
            candidate = ProfilePatchCandidate.model_validate(row.patch_payload)
            recommendation_id = candidate.recommendation_id
            if recommendation_id and recommendation_id not in candidates_by_recommendation_id:
                candidates_by_recommendation_id[recommendation_id] = (candidate, row.status)
            validation_rows = self._repository.list_patch_validation_results(candidate_id=row.candidate_id, limit=1)
            if validation_rows and candidate.candidate_id not in validations_by_candidate_id:
                validations_by_candidate_id[candidate.candidate_id] = ProfilePatchValidationResult.model_validate(
                    validation_rows[0].validation_payload,
                )

        items: list[ReplayWorkbenchTuningReviewItem] = []
        for recommendation in recommendations:
            candidate_pair = candidates_by_recommendation_id.get(recommendation.recommendation_id)
            candidate = candidate_pair[0] if candidate_pair is not None else None
            candidate_status = candidate_pair[1] if candidate_pair is not None else None
            validation = (
                validations_by_candidate_id.get(candidate.candidate_id)
                if candidate is not None
                else None
            )
            degraded_badges = _degradation_badges_from_recommendation(recommendation)
            items.append(
                ReplayWorkbenchTuningReviewItem(
                    market_time=recommendation.generated_at,
                    session_date=recommendation.generated_at.date().isoformat(),
                    degraded_badges=degraded_badges,
                    patch_candidate_status=candidate_status,
                    recommendation=recommendation,
                    patch_candidate=candidate,
                    latest_validation_result=validation,
                ),
            )
        return ReplayWorkbenchTuningReviewEnvelope(query=query, items=items)

    def get_profile_engine_metadata(self, query: ReplayProjectionQuery) -> ReplayWorkbenchProfileEngineEnvelope:
        """Return the current active profile/build and latest patch state for one instrument."""

        active_profile_row = self._repository.get_active_instrument_profile(query.instrument_symbol)
        active_build_row = self._repository.get_active_recognizer_build()
        latest_patch_rows = self._repository.list_profile_patch_candidates(
            instrument_symbol=query.instrument_symbol,
            limit=1,
        )
        latest_patch_status = latest_patch_rows[0].status if latest_patch_rows else None
        latest_patch = (
            ProfilePatchCandidate.model_validate(latest_patch_rows[0].patch_payload)
            if latest_patch_rows
            else None
        )
        latest_validation = None
        if latest_patch is not None:
            validation_rows = self._repository.list_patch_validation_results(
                candidate_id=latest_patch.candidate_id,
                limit=1,
            )
            if validation_rows:
                latest_validation = ProfilePatchValidationResult.model_validate(validation_rows[0].validation_payload)
        return ReplayWorkbenchProfileEngineEnvelope(
            query=query,
            active_profile=(
                InstrumentProfile.model_validate(active_profile_row.profile_payload)
                if active_profile_row is not None
                else None
            ),
            active_build=_build_model_from_record(active_build_row),
            latest_patch_candidate_status=latest_patch_status,
            latest_patch_candidate=latest_patch,
            latest_patch_validation_result=latest_validation,
        )

    def get_health_status(self, query: ReplayProjectionQuery) -> ReplayWorkbenchHealthStatusEnvelope:
        """Return health/degraded status together with the latest belief snapshot."""

        health_result = self._ingestion_reliability_service.get_ingestion_health(
            instrument_symbol=query.instrument_symbol,
        )
        quality_result = self._ingestion_reliability_service.get_data_quality(
            instrument_symbol=query.instrument_symbol,
        )
        health = IngestionHealthResponse.model_validate(health_result.body.model_dump(mode="json"))
        data_quality = quality_result.body
        latest_belief_row = self._repository.get_latest_belief_state(query.instrument_symbol)
        latest_belief = (
            BeliefStateSnapshot.model_validate(latest_belief_row.belief_payload)
            if latest_belief_row is not None
            else None
        )
        return ReplayWorkbenchHealthStatusEnvelope(
            query=query,
            health=health,
            data_quality=data_quality,
            latest_belief=latest_belief,
        )

    def build_projection(self, query: ReplayProjectionQuery) -> ReplayWorkbenchProjectionEnvelope:
        """Build the full replay/workbench projection bundle for review surfaces."""

        health_status = self.get_health_status(query)
        metadata = self.get_profile_engine_metadata(query)
        belief_timeline = self.get_belief_state_timeline(query)
        episode_reviews = self.get_event_episode_reviews(query)
        episode_evaluations = self.get_episode_evaluations(query)
        tuning_reviews = self.get_tuning_reviews(query)
        timeline = self._build_timeline(
            health_status=health_status,
            belief_timeline=belief_timeline,
            episode_reviews=episode_reviews,
            episode_evaluations=episode_evaluations,
            tuning_reviews=tuning_reviews,
        )
        return ReplayWorkbenchProjectionEnvelope(
            query=query,
            health_status=health_status,
            metadata=metadata,
            belief_timeline=belief_timeline,
            episode_reviews=episode_reviews,
            episode_evaluations=episode_evaluations,
            tuning_reviews=tuning_reviews,
            timeline=timeline,
        )

    def _load_beliefs(self, query: ReplayProjectionQuery) -> list[BeliefStateSnapshot]:
        rows = self._repository.list_belief_states(
            instrument_symbol=query.instrument_symbol,
            observed_at_after=query.window_start,
            observed_at_before=query.window_end,
            session_date=query.session_date,
            limit=query.limit,
        )
        beliefs = [BeliefStateSnapshot.model_validate(item.belief_payload) for item in rows]
        beliefs.sort(key=lambda item: item.observed_at, reverse=True)
        return beliefs

    def _load_episodes(self, query: ReplayProjectionQuery, *, limit: int | None = None) -> list[EventEpisode]:
        rows = self._repository.list_event_episodes(
            instrument_symbol=query.instrument_symbol,
            ended_at_after=query.window_start,
            ended_at_before=query.window_end,
            session_date=query.session_date,
            limit=limit or query.limit,
        )
        episodes = [EventEpisode.model_validate(item.episode_payload) for item in rows]
        episodes.sort(key=lambda item: item.ended_at, reverse=True)
        return episodes

    def _load_evaluations(self, query: ReplayProjectionQuery) -> list[EpisodeEvaluation]:
        rows = self._repository.list_episode_evaluations(
            instrument_symbol=query.instrument_symbol,
            limit=max(query.limit * 5, query.limit),
        )
        evaluations = [
            item
            for item in (EpisodeEvaluation.model_validate(row.evaluation_payload) for row in rows)
            if _evaluation_matches_query(item, query)
        ]
        evaluations.sort(key=lambda item: item.evaluated_at, reverse=True)
        return evaluations[: query.limit]

    def _load_recommendations(self, query: ReplayProjectionQuery) -> list[TuningRecommendation]:
        rows = self._repository.list_tuning_recommendations(
            instrument_symbol=query.instrument_symbol,
            limit=max(query.limit * 5, query.limit),
        )
        recommendations = [
            item
            for item in (TuningRecommendation.model_validate(row.recommendation_payload) for row in rows)
            if _recommendation_matches_query(item, query)
        ]
        recommendations.sort(key=lambda item: item.generated_at, reverse=True)
        return recommendations[: query.limit]

    def _build_timeline(
        self,
        *,
        health_status: ReplayWorkbenchHealthStatusEnvelope,
        belief_timeline: ReplayWorkbenchBeliefTimelineEnvelope,
        episode_reviews: ReplayWorkbenchEpisodeReviewEnvelope,
        episode_evaluations: ReplayWorkbenchEpisodeEvaluationListEnvelope,
        tuning_reviews: ReplayWorkbenchTuningReviewEnvelope,
    ) -> list[ReplayProjectionTimelineEntry]:
        timeline: list[ReplayProjectionTimelineEntry] = []

        for item in belief_timeline.items:
            timeline.append(
                ReplayProjectionTimelineEntry(
                    entry_type="belief_state",
                    object_id=item.belief_state_id,
                    market_time=item.market_time,
                    session_date=item.session_date,
                    title="belief_state",
                    summary=" | ".join(item.top_event_hypotheses[:2]) or "belief snapshot",
                    degraded_badges=item.degraded_badges,
                    profile_version=item.belief.profile_version,
                    engine_version=item.belief.engine_version,
                ),
            )

        for item in episode_reviews.items:
            timeline.append(
                ReplayProjectionTimelineEntry(
                    entry_type="event_episode",
                    object_id=item.episode.episode_id,
                    market_time=item.market_time,
                    session_date=item.session_date,
                    title=item.episode.event_kind.value,
                    summary=item.summary_status,
                    degraded_badges=_data_status_badges(item.episode.data_status),
                    profile_version=item.episode.profile_version,
                    engine_version=item.episode.engine_version,
                ),
            )

        for item in episode_evaluations.items:
            timeline.append(
                ReplayProjectionTimelineEntry(
                    entry_type="episode_evaluation",
                    object_id=item.evaluation.evaluation_id,
                    market_time=item.market_time,
                    session_date=item.session_date,
                    title=item.evaluation.evaluated_event_kind.value,
                    summary=item.primary_failure_mode.value,
                    degraded_badges=[],
                    profile_version=item.evaluation.profile_version,
                    engine_version=item.evaluation.engine_version,
                ),
            )

        for item in tuning_reviews.items:
            timeline.append(
                ReplayProjectionTimelineEntry(
                    entry_type="tuning_recommendation",
                    object_id=item.recommendation.recommendation_id,
                    market_time=item.market_time,
                    session_date=item.session_date,
                    title=item.recommendation.advisor_kind,
                    summary=item.recommendation.expected_improvement,
                    degraded_badges=item.degraded_badges,
                    profile_version=item.recommendation.profile_version,
                    engine_version=item.recommendation.engine_version,
                ),
            )
            if item.patch_candidate is not None:
                timeline.append(
                    ReplayProjectionTimelineEntry(
                        entry_type="patch_candidate",
                        object_id=item.patch_candidate.candidate_id,
                        market_time=item.patch_candidate.created_at,
                        session_date=item.patch_candidate.created_at.date().isoformat(),
                        title=item.patch_candidate.proposed_profile_version,
                        summary=item.patch_candidate_status or "candidate",
                        degraded_badges=[],
                        profile_version=item.patch_candidate.base_profile_version,
                        engine_version=None,
                    ),
                )

        health_time = (
            health_status.latest_belief.observed_at
            if health_status.latest_belief is not None
            else datetime.now(tz=UTC)
        )
        timeline.append(
            ReplayProjectionTimelineEntry(
                entry_type="health_status",
                object_id=f"health-{health_status.query.instrument_symbol}",
                market_time=health_time,
                session_date=health_time.date().isoformat(),
                title=health_status.health.status.value,
                summary=(
                    f"freshness={health_status.health.freshness or '--'} "
                    f"completeness={health_status.health.completeness or '--'}"
                ),
                degraded_badges=list(health_status.health.degraded_reasons),
                profile_version=health_status.health.profile_version,
                engine_version=health_status.health.engine_version,
            ),
        )
        timeline.sort(key=lambda item: item.market_time, reverse=True)
        return timeline[: max(health_status.query.limit * 4, health_status.query.limit)]


def _format_top_regimes(belief: BeliefStateSnapshot) -> list[str]:
    return [
        f"{item.regime.value}:{item.probability:.2f}"
        for item in sorted(belief.regime_posteriors, key=lambda row: row.probability, reverse=True)[:3]
    ]


def _format_top_hypotheses(belief: BeliefStateSnapshot) -> list[str]:
    labels: list[str] = []
    for item in sorted(belief.event_hypotheses, key=lambda row: row.posterior_probability, reverse=True)[:3]:
        event_label = item.mapped_event_kind.value if item.mapped_event_kind is not None else item.hypothesis_kind.value
        labels.append(f"{event_label}:{item.phase.value}:{item.posterior_probability:.2f}")
    return labels


def _data_status_badges(data_status) -> list[str]:
    badges = [item.value for item in data_status.degraded_modes]
    freshness = data_status.freshness
    completeness = data_status.completeness
    if freshness and freshness not in {"fresh", "live"}:
        badges.append(f"freshness:{freshness}")
    if completeness and completeness not in {"complete"}:
        badges.append(f"completeness:{completeness}")
    return badges


def _episode_summary_status(episode: EventEpisode, evaluation: EpisodeEvaluation | None) -> str:
    if evaluation is None:
        return f"{episode.resolution.value} / evaluation_missing"
    failure_mode = evaluation.diagnosis.primary_failure_mode
    if failure_mode is EvaluationFailureMode.NONE:
        return f"{episode.resolution.value} / healthy"
    return f"{episode.resolution.value} / {failure_mode.value}"


def _degradation_badges_from_recommendation(recommendation: TuningRecommendation) -> list[str]:
    return []


def _build_model_from_record(record) -> RecognizerBuild | None:
    if record is None:
        return None
    raw_notes = record.build_payload.get("notes", [])
    notes = raw_notes if isinstance(raw_notes, list) else [str(raw_notes)] if raw_notes else []
    return RecognizerBuild(
        engine_version=record.engine_version,
        schema_version=record.schema_version,
        ontology_version=record.ontology_version,
        is_active=record.is_active,
        status=record.status,
        notes=notes,
        created_at=record.created_at,
    )


def _evaluation_matches_query(evaluation: EpisodeEvaluation, query: ReplayProjectionQuery) -> bool:
    if query.session_date is not None and evaluation.market_time_end.date().isoformat() != query.session_date:
        return False
    return _window_overlap(
        start=evaluation.market_time_start,
        end=evaluation.market_time_end,
        query_start=query.window_start,
        query_end=query.window_end,
    )


def _recommendation_matches_query(recommendation: TuningRecommendation, query: ReplayProjectionQuery) -> bool:
    window_start = recommendation.analysis_window.date_from
    window_end = recommendation.analysis_window.date_to
    if query.session_date is not None:
        candidate_dates = {
            item.date().isoformat()
            for item in (window_start, window_end)
            if item is not None
        }
        if candidate_dates and query.session_date not in candidate_dates:
            return False
    return _window_overlap(
        start=window_start,
        end=window_end,
        query_start=query.window_start,
        query_end=query.window_end,
    )


def _window_overlap(
    *,
    start: datetime | None,
    end: datetime | None,
    query_start: datetime | None,
    query_end: datetime | None,
) -> bool:
    normalized_start = start or end
    normalized_end = end or start
    if normalized_start is None and normalized_end is None:
        return True
    if query_start is not None and normalized_end is not None and normalized_end < query_start:
        return False
    if query_end is not None and normalized_start is not None and normalized_start > query_end:
        return False
    return True
