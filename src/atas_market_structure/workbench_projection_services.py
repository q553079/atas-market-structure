from __future__ import annotations

from datetime import UTC, datetime

from atas_market_structure.ingestion_reliability_services import IngestionReliabilityService
from atas_market_structure.models import (
    BeliefStateSnapshot,
    ReplayProjectionQuery,
    ReplayProjectionTimelineEntry,
    ReplayWorkbenchBeliefTimelineEntry,
    ReplayWorkbenchBeliefTimelineEnvelope,
    ReplayWorkbenchEpisodeEvaluationListEnvelope,
    ReplayWorkbenchEpisodeReviewEnvelope,
    ReplayWorkbenchHealthStatusEnvelope,
    ReplayWorkbenchProfileEngineEnvelope,
    ReplayWorkbenchProjectionEnvelope,
    ReplayWorkbenchTuningReviewEnvelope,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.workbench_review_service import ReplayWorkbenchReviewService


class ReplayWorkbenchProjectionService:
    """Build projection bundles while delegating review-specific aggregation to a dedicated service."""

    def __init__(
        self,
        *,
        repository: AnalysisRepository,
        ingestion_reliability_service: IngestionReliabilityService,
    ) -> None:
        self._repository = repository
        self._review_service = ReplayWorkbenchReviewService(
            repository=repository,
            ingestion_reliability_service=ingestion_reliability_service,
        )

    def get_belief_state_timeline(self, query: ReplayProjectionQuery) -> ReplayWorkbenchBeliefTimelineEnvelope:
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
        return self._review_service.get_event_episode_reviews(query)

    def get_episode_evaluations(self, query: ReplayProjectionQuery) -> ReplayWorkbenchEpisodeEvaluationListEnvelope:
        return self._review_service.get_episode_evaluations(query)

    def get_tuning_reviews(self, query: ReplayProjectionQuery) -> ReplayWorkbenchTuningReviewEnvelope:
        return self._review_service.get_tuning_reviews(query)

    def get_profile_engine_metadata(self, query: ReplayProjectionQuery) -> ReplayWorkbenchProfileEngineEnvelope:
        return self._review_service.get_profile_engine_metadata(query)

    def get_health_status(self, query: ReplayProjectionQuery) -> ReplayWorkbenchHealthStatusEnvelope:
        return self._review_service.get_health_status(query)

    def build_projection(self, query: ReplayProjectionQuery) -> ReplayWorkbenchProjectionEnvelope:
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
