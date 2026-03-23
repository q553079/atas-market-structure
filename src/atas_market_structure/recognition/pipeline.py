from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging
from typing import Any

from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.models import BeliefDataStatus, BeliefStateSnapshot, InstrumentProfile, RecognitionMode
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.storage_models import (
    StoredEventHypothesisState,
    StoredFeatureSlice,
    StoredRegimePosterior,
)
from atas_market_structure.recognition.anchor_manager import MemoryAnchorManager
from atas_market_structure.recognition.belief_emitter import BeliefStateBuilder
from atas_market_structure.recognition.defaults import (
    BELIEF_STATE_SCHEMA_VERSION,
    EVENT_EPISODE_SCHEMA_VERSION,
    EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    MEMORY_ANCHOR_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
    build_default_instrument_profile,
    build_default_recognizer_build,
)
from atas_market_structure.recognition.degraded_mode import RecognitionQualityEvaluator
from atas_market_structure.recognition.episode_closer import EventEpisodeBuilder
from atas_market_structure.recognition.event_updater import EventHypothesisUpdater
from atas_market_structure.recognition.feature_builder import FeatureBuilder
from atas_market_structure.recognition.regime_updater import RegimeUpdater
from atas_market_structure.recognition.types import RecognitionRunResult


LOGGER = logging.getLogger(__name__)


class DeterministicRecognitionService:
    """Master Spec v2 deterministic recognition V1 skeleton."""

    def __init__(self, repository: AnalysisRepository, *, ai_available: bool = False) -> None:
        self._repository = repository
        self._feature_slice_schema_version = FEATURE_SLICE_SCHEMA_VERSION
        self._regime_posterior_schema_version = REGIME_POSTERIOR_SCHEMA_VERSION
        self._event_hypothesis_schema_version = EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION
        self._quality_evaluator = RecognitionQualityEvaluator(repository, ai_available=ai_available)
        self._feature_builder = FeatureBuilder(repository)
        self._regime_updater = RegimeUpdater()
        self._anchor_manager = MemoryAnchorManager(repository, schema_version=MEMORY_ANCHOR_SCHEMA_VERSION)
        self._event_updater = EventHypothesisUpdater(repository)
        self._belief_builder = BeliefStateBuilder(repository, schema_version=BELIEF_STATE_SCHEMA_VERSION)
        self._episode_builder = EventEpisodeBuilder(repository, schema_version=EVENT_EPISODE_SCHEMA_VERSION)
        self._evaluation_service = EpisodeEvaluationService(repository)

    def try_run_for_instrument(
        self,
        instrument_symbol: str,
        *,
        triggered_by: str | None = None,
        reference_time: datetime | None = None,
    ) -> RecognitionRunResult:
        try:
            return self.run_for_instrument(
                instrument_symbol,
                triggered_by=triggered_by,
                reference_time=reference_time,
            )
        except Exception as exc:  # pragma: no cover - defensive only
            LOGGER.exception("deterministic recognition failed for %s", instrument_symbol)
            return RecognitionRunResult(
                triggered=False,
                instrument_symbol=instrument_symbol,
                market_time=None,
                profile_version="recognition_failed",
                engine_version="recognition_failed",
                recognition_mode=None,
                data_status=None,
                feature_slice_id=None,
                belief_state=None,
                closed_episodes=[],
                episode_evaluations=[],
                notes=[f"recognition_failed:{type(exc).__name__}:{exc}"],
            )

    def run_for_instrument(
        self,
        instrument_symbol: str,
        *,
        triggered_by: str | None = None,
        reference_time: datetime | None = None,
    ) -> RecognitionRunResult:
        profile_version, engine_version, profile_payload = self._ensure_versions(instrument_symbol)
        recorded_at = reference_time or datetime.now(tz=UTC)
        quality = self._quality_evaluator.evaluate(
            instrument_symbol=instrument_symbol,
            reference_time=recorded_at,
        )
        feature = self._feature_builder.build(
            instrument_symbol=instrument_symbol,
            profile_payload=profile_payload,
            data_status=quality.data_status,
        )
        if feature is None:
            return RecognitionRunResult(
                triggered=False,
                instrument_symbol=instrument_symbol,
                market_time=None,
                profile_version=profile_version,
                engine_version=engine_version,
                recognition_mode=quality.recognition_mode,
                data_status=quality.data_status,
                feature_slice_id=None,
                belief_state=None,
                closed_episodes=[],
                episode_evaluations=[],
                notes=["no_observations_available"],
            )

        run_key = _stable_run_key(feature, recorded_at=recorded_at)
        feature_slice_id = f"fs-{instrument_symbol.lower()}-{run_key}"
        self._repository.save_feature_slice(
            StoredFeatureSlice(
                feature_slice_id=feature_slice_id,
                instrument_symbol=instrument_symbol,
                market_time=feature.market_time,
                session_date=feature.session_date,
                ingested_at=recorded_at,
                schema_version=self._feature_slice_schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                source_observation_table=feature.source_observation_table,
                source_observation_id=feature.source_observation_id,
                slice_kind="deterministic_recognition_v1",
                window_start=feature.window_start,
                window_end=feature.window_end,
                data_status=quality.data_status.model_dump(mode="json"),
                feature_payload={
                    "current_price": feature.current_price,
                    "metrics": feature.metrics,
                    "evidence_buckets": {
                        name: {
                            "score": bucket.score,
                            "available": bucket.available,
                            "weight": bucket.weight,
                            "signals": bucket.signals,
                            "metrics": bucket.metrics,
                        }
                        for name, bucket in feature.evidence_buckets.items()
                    },
                    "notes": feature.notes,
                },
            ),
        )

        regimes = self._regime_updater.build(feature=feature, profile_payload=profile_payload)
        self._repository.save_regime_posterior(
            StoredRegimePosterior(
                posterior_id=f"reg-{instrument_symbol.lower()}-{run_key}",
                instrument_symbol=instrument_symbol,
                market_time=feature.market_time,
                session_date=feature.session_date,
                ingested_at=recorded_at,
                schema_version=self._regime_posterior_schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                feature_slice_id=feature_slice_id,
                posterior_payload={
                    "regime_posteriors": [item.model_dump(mode="json") for item in regimes],
                    "top_regime": regimes[0].regime.value if regimes else None,
                },
            ),
        )

        anchors = self._anchor_manager.refresh(
            feature=feature,
            profile_version=profile_version,
            engine_version=engine_version,
            reference_time=recorded_at,
            run_key=run_key,
        )
        hypotheses = self._event_updater.build(
            feature=feature,
            regimes=regimes,
            anchors=anchors,
            profile_payload=profile_payload,
            run_key=run_key,
        )
        for state in hypotheses:
            self._repository.save_event_hypothesis_state(
                StoredEventHypothesisState(
                    hypothesis_state_id=state.hypothesis_id,
                    instrument_symbol=instrument_symbol,
                    market_time=feature.market_time,
                    session_date=feature.session_date,
                    ingested_at=recorded_at,
                    schema_version=self._event_hypothesis_schema_version,
                    profile_version=profile_version,
                    engine_version=engine_version,
                    feature_slice_id=feature_slice_id,
                    hypothesis_kind=state.hypothesis_kind.value,
                    hypothesis_payload=state.model_dump(mode="json"),
                ),
            )

        notes = [*feature.notes]
        if triggered_by:
            notes.append(f"triggered_by={triggered_by}")
        notes.append(f"recognition_mode={quality.recognition_mode.value}")
        notes.append(f"top_regime={regimes[0].regime.value if regimes else 'none'}")
        belief = self._belief_builder.build_and_store(
            instrument_symbol=instrument_symbol,
            market_time=feature.market_time,
            profile_version=profile_version,
            engine_version=engine_version,
            run_key=run_key,
            recorded_at=recorded_at,
            recognition_mode=quality.recognition_mode,
            data_status=quality.data_status,
            regimes=regimes,
            hypotheses=hypotheses,
            anchors=anchors,
            notes=notes,
        )
        episodes = self._episode_builder.close_episodes(feature=feature, belief=belief)
        evaluation_beliefs = [
            BeliefStateSnapshot.model_validate(item.belief_payload)
            for item in self._repository.list_belief_states(instrument_symbol=instrument_symbol, limit=64)
        ]
        profile_model = InstrumentProfile.model_validate(profile_payload)
        evaluations = [
            self._evaluation_service.evaluate_episode(
                episode=episode,
                beliefs=evaluation_beliefs,
                profile=profile_model,
                persist=True,
            )
            for episode in episodes
        ]
        return RecognitionRunResult(
            triggered=True,
            instrument_symbol=instrument_symbol,
            market_time=feature.market_time,
            profile_version=profile_version,
            engine_version=engine_version,
            recognition_mode=quality.recognition_mode,
            data_status=quality.data_status,
            feature_slice_id=feature_slice_id,
            belief_state=belief,
            closed_episodes=episodes,
            episode_evaluations=evaluations,
            notes=notes,
        )

    def _ensure_versions(self, instrument_symbol: str) -> tuple[str, str, dict[str, Any]]:
        profile = self._repository.get_active_instrument_profile(instrument_symbol)
        if profile is None:
            tick_size = self._guess_tick_size(instrument_symbol)
            default_profile = build_default_instrument_profile(instrument_symbol, tick_size=tick_size)
            self._repository.save_instrument_profile(
                instrument_symbol=default_profile.instrument_symbol,
                profile_version=default_profile.profile_version,
                schema_version=default_profile.schema_version,
                ontology_version=default_profile.ontology_version,
                is_active=True,
                profile_payload=default_profile.model_dump(mode="json"),
                created_at=default_profile.created_at,
            )
            profile = self._repository.get_active_instrument_profile(instrument_symbol)
        build = self._repository.get_active_recognizer_build()
        if build is None:
            default_build = build_default_recognizer_build()
            self._repository.save_recognizer_build(
                engine_version=default_build.engine_version,
                schema_version=default_build.schema_version,
                ontology_version=default_build.ontology_version,
                is_active=True,
                status=default_build.status,
                build_payload=default_build.model_dump(mode="json"),
                created_at=default_build.created_at,
            )
            build = self._repository.get_active_recognizer_build()
        if profile is None or build is None:  # pragma: no cover - defensive only
            raise RuntimeError("failed to bootstrap active recognition versions")
        return profile.profile_version, build.engine_version, profile.profile_payload

    def _guess_tick_size(self, instrument_symbol: str) -> float:
        for kind in ("market_structure", "event_snapshot", "process_context", "adapter_continuous_state", "adapter_history_bars"):
            items = self._repository.list_ingestions(
                ingestion_kind=kind,
                instrument_symbol=instrument_symbol,
                limit=1,
            )
            if not items:
                continue
            instrument = items[0].observed_payload.get("instrument")
            if isinstance(instrument, dict) and isinstance(instrument.get("tick_size"), (int, float)):
                return float(instrument["tick_size"])
        return 0.25


def _stable_run_key(feature: Any, *, recorded_at: datetime) -> str:
    material = "|".join(
        (
            feature.instrument_symbol,
            feature.market_time.isoformat(),
            recorded_at.isoformat(),
            feature.source_observation_table,
            feature.source_observation_id,
        ),
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]
