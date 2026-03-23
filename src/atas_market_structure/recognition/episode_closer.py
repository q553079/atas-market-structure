from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from atas_market_structure.models import (
    BeliefStateSnapshot,
    EpisodeResolution,
    EventEpisode,
    EventHypothesisState,
    EventPhase,
    TradableEventKind,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.storage_models import StoredEventEpisodeEvidence
from atas_market_structure.recognition.types import RecognitionFeatureVector


class EventEpisodeBuilder:
    """Closes append-only event episodes from belief-state transitions."""

    def __init__(self, repository: AnalysisRepository, *, schema_version: str) -> None:
        self._repository = repository
        self._schema_version = schema_version

    def close_episodes(
        self,
        *,
        feature: RecognitionFeatureVector,
        belief: BeliefStateSnapshot,
    ) -> list[EventEpisode]:
        beliefs = [
            BeliefStateSnapshot.model_validate(item.belief_payload)
            for item in self._repository.list_belief_states(instrument_symbol=belief.instrument_symbol, limit=24)
        ]
        if not beliefs or not belief.event_hypotheses:
            return []

        latest = beliefs[0]
        previous = beliefs[1] if len(beliefs) > 1 else None
        candidates: list[tuple[EventHypothesisState, EpisodeResolution, TradableEventKind | None]] = []
        lead = latest.event_hypotheses[0]
        if lead.mapped_event_kind is not None and lead.phase in {EventPhase.RESOLVED, EventPhase.INVALIDATED}:
            candidates.append(
                (
                    lead,
                    EpisodeResolution.CONFIRMED if lead.phase is EventPhase.RESOLVED else EpisodeResolution.INVALIDATED,
                    None,
                ),
            )
        if previous is not None and previous.event_hypotheses:
            prev_lead = previous.event_hypotheses[0]
            if (
                prev_lead.mapped_event_kind is not None
                and lead.mapped_event_kind is not None
                and prev_lead.mapped_event_kind != lead.mapped_event_kind
                and prev_lead.posterior_probability >= 0.30
            ):
                candidates.append((prev_lead, EpisodeResolution.REPLACED, lead.mapped_event_kind))

        closed: list[EventEpisode] = []
        for hypothesis, resolution, replacement_event in candidates:
            if hypothesis.mapped_event_kind is None:
                continue
            sequence = (
                _collect_sequence(beliefs, hypothesis.mapped_event_kind)
                if resolution is not EpisodeResolution.REPLACED
                else _collect_sequence(beliefs[1:], hypothesis.mapped_event_kind)
            )
            if not sequence:
                continue
            started_at = sequence[-1].observed_at
            ended_at = sequence[0].observed_at
            episode_id = f"ep-{belief.instrument_symbol.lower()}-{hypothesis.mapped_event_kind.value}-{started_at.strftime('%Y%m%d%H%M%S')}-{ended_at.strftime('%Y%m%d%H%M%S')}"
            if self._repository.get_event_episode(episode_id) is not None:
                continue
            matched_states = [state for snapshot in sequence for state in snapshot.event_hypotheses if state.mapped_event_kind == hypothesis.mapped_event_kind]
            peak = max((item.posterior_probability for item in matched_states), default=hypothesis.posterior_probability)
            support = _unique_flat(item.supporting_evidence for item in matched_states)[:8]
            invalidating = _unique_flat(item.invalidating_signals for item in matched_states)[:8]
            episode = EventEpisode(
                episode_id=episode_id,
                instrument_symbol=belief.instrument_symbol,
                event_kind=hypothesis.mapped_event_kind,
                hypothesis_kind=hypothesis.hypothesis_kind,
                phase=hypothesis.phase,
                resolution=resolution,
                started_at=started_at,
                ended_at=ended_at,
                peak_probability=round(peak, 6),
                dominant_regime=belief.regime_posteriors[0].regime if belief.regime_posteriors else sequence[0].regime_posteriors[0].regime,
                supporting_evidence=support,
                invalidating_evidence=invalidating,
                key_evidence_summary=(support[:4] + invalidating[:2])[:6],
                active_anchor_ids=[item.anchor_id for item in belief.active_anchors],
                replacement_episode_id=None,
                replacement_event_kind=replacement_event,
                schema_version=self._schema_version,
                profile_version=belief.profile_version,
                engine_version=belief.engine_version,
                data_status=belief.data_status,
            )
            self._repository.save_event_episode(
                episode_id=episode.episode_id,
                instrument_symbol=episode.instrument_symbol,
                event_kind=episode.event_kind.value,
                started_at=episode.started_at,
                ended_at=episode.ended_at,
                resolution=episode.resolution.value,
                schema_version=self._schema_version,
                profile_version=belief.profile_version,
                engine_version=belief.engine_version,
                episode_payload=episode.model_dump(mode="json"),
            )
            self._save_evidence_rows(feature=feature, belief=belief, episode=episode)
            closed.append(episode)
        return closed

    def _save_evidence_rows(
        self,
        *,
        feature: RecognitionFeatureVector,
        belief: BeliefStateSnapshot,
        episode: EventEpisode,
    ) -> None:
        now = datetime.now(tz=UTC)
        for index, evidence in enumerate(episode.key_evidence_summary):
            self._repository.save_event_episode_evidence(
                StoredEventEpisodeEvidence(
                    evidence_id=f"evid-{episode.episode_id}-{index}",
                    episode_id=episode.episode_id,
                    instrument_symbol=episode.instrument_symbol,
                    market_time=episode.ended_at,
                    session_date=feature.session_date,
                    ingested_at=now,
                    schema_version=self._schema_version,
                    profile_version=belief.profile_version,
                    engine_version=belief.engine_version,
                    evidence_kind="episode_summary",
                    source_observation_table=feature.source_observation_table,
                    source_observation_id=feature.source_observation_id,
                    evidence_payload={"summary": evidence},
                ),
            )


def _collect_sequence(beliefs: list[BeliefStateSnapshot], event_kind: TradableEventKind) -> list[BeliefStateSnapshot]:
    sequence: list[BeliefStateSnapshot] = []
    for belief in beliefs:
        lead = belief.event_hypotheses[0] if belief.event_hypotheses else None
        if lead is None or lead.mapped_event_kind != event_kind or lead.posterior_probability < 0.28:
            break
        sequence.append(belief)
    return sequence


def _unique_flat(groups: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for values in groups:
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered
