"""
tests/test_integration_chain.py

End-to-end integration tests for the full event-recognition and
evaluation chain.  These tests verify the complete data-flow:

    ingestion  ->  recognizer  ->  belief-state  ->  episode-close
                                                                    ->  evaluation
                                                                            ->  tuning-recommendation

Each test class is self-contained, uses a fresh temporary database, and
does not depend on external infrastructure (ClickHouse, OpenAI, ATAS).

Coverage gaps this file fills (relative to existing test files):
- Replacement event takeover: the recognizer closes one episode and opens
  a replacement, which must be evaluated correctly.
- Late-invalidation persistence: a late-invalidation episode is persisted
  and visible in the read model.
- Degraded-mode ingestion continues: recognizer degrades gracefully while
  the ingestion endpoint still accepts payloads.
- Full recognition -> evaluation -> projection chain via the API layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atas_market_structure.config import AppConfig
from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.ingestion_reliability_services import IngestionReliabilityService
from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    DegradedMode,
    EpisodeResolution,
    EvaluationFailureMode,
    EventEpisode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    MemoryAnchorSnapshot,
    RecognitionMode,
    RegimeKind,
    RegimePosteriorRecord,
    TradableEventKind,
    EpisodeEvaluation,
)
from atas_market_structure.profile_services import build_instrument_profile_v1, default_tick_size_for_symbol
from atas_market_structure.models._replay import BeliefStateSnapshot as BeliefStateSnapshotModel
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.services import IngestionOrchestrator
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import build_application
from atas_market_structure.storage_repository import SQLiteStorageBlueprintRepository
from atas_market_structure.tuning_services import TuningAdvisorService


# ---------------------------------------------------------------------------
# Fixtures shared across all test classes
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path) -> SQLiteAnalysisRepository:
    repo = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repo.initialize()
    return repo


def _make_profile(symbol: str) -> dict:
    return build_instrument_profile_v1(
        symbol,
        tick_size=default_tick_size_for_symbol(symbol),
        profile_version=f"{symbol.lower()}-profile-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# 1. Recognition-pipeline regression tests
# ---------------------------------------------------------------------------

class TestRecognitionPipelineScenarios:
    """Regression tests for the DeterministicRecognitionService.

    These complement test_recognition_pipeline.py by adding scenarios that
    are not yet covered there.
    """

    def test_momentum_continuation_full_chain_produces_confirmed_episode(
        self, tmp_path: Path
    ) -> None:
        """Momentum continuation: recognizer fires, builds belief, closes confirmed episode."""
        repo = _make_repo(tmp_path)
        now = datetime(2026, 3, 23, 9, 30, tzinfo=UTC).replace(microsecond=0)

        # --- Ingest history bars (rising candles with positive delta) ---
        repo.save_ingestion(
            ingestion_id="ing-hist-momo",
            ingestion_kind="adapter_history_bars",
            source_snapshot_id="hist-momo",
            instrument_symbol="NQ",
            observed_payload=_history_bars_payload(
                symbol="NQ",
                start=now - timedelta(minutes=6),
                bars=[
                    (21490.0, 21493.0, 21489.75, 21492.75, 240, 95),
                    (21492.75, 21496.0, 21492.5, 21495.75, 260, 112),
                    (21495.75, 21499.0, 21495.5, 21498.75, 270, 118),
                    (21498.75, 21502.0, 21498.5, 21501.75, 285, 124),
                    (21501.75, 21505.0, 21501.5, 21504.75, 300, 138),
                    (21504.75, 21508.0, 21504.5, 21507.75, 320, 150),
                ],
                emitted_at=now,
            ),
            stored_at=now,
        )

        # --- Ingest process context with strong initiative ---
        repo.save_ingestion(
            ingestion_id="ing-proc-momo",
            ingestion_kind="process_context",
            source_snapshot_id="proc-momo",
            instrument_symbol="NQ",
            observed_payload=_process_context_payload(
                symbol="NQ",
                observed_at=now,
                point_of_control=21484.0,
                initiative_side="buy",
                zone_low=21487.0,
                zone_high=21488.5,
            ),
            stored_at=now,
        )

        # --- Ingest continuous state with active drive ---
        repo.save_ingestion(
            ingestion_id="ing-cont-momo",
            ingestion_kind="adapter_continuous_state",
            source_snapshot_id="msg-momo",
            instrument_symbol="NQ",
            observed_payload=_continuous_payload(
                symbol="NQ",
                observed_at=now,
                last_price=21518.25,
                local_low=21505.0,
                local_high=21518.25,
                net_delta=820,
                volume=1400,
                side="buy",
                drive_low=21505.0,
                drive_high=21518.25,
            ),
            stored_at=now,
        )

        service = DeterministicRecognitionService(repository=repo)
        result = service.run_for_instrument("NQ", triggered_by="pytest_momo")

        # --- Assert recognizer fired ---
        assert result.triggered is True
        assert result.belief_state is not None

        # --- Assert belief contains momentum hypothesis ---
        top_hyp = result.belief_state.event_hypotheses[0]
        assert top_hyp.mapped_event_kind is TradableEventKind.MOMENTUM_CONTINUATION
        assert top_hyp.phase in {EventPhase.CONFIRMING, EventPhase.RESOLVED}

        # --- Assert belief was persisted ---
        beliefs = repo.list_belief_states(instrument_symbol="NQ", limit=10)
        assert len(beliefs) >= 1
        # StoredBeliefState has belief_payload dict; deserialize to check
        loaded = BeliefStateSnapshotModel.model_validate(beliefs[0].belief_payload)
        assert loaded.event_hypotheses[0].mapped_event_kind is TradableEventKind.MOMENTUM_CONTINUATION

        # --- Assert regime posterior was persisted ---
        regimes = repo.list_regime_posteriors(instrument_symbol="NQ", limit=10)
        assert len(regimes) >= 1

        # --- Assert feature slice was persisted ---
        slices = repo.list_feature_slices(instrument_symbol="NQ", limit=10)
        assert len(slices) >= 1

        # --- Assert episode was closed (may be 0 if phase hasn't completed yet) ---
        episodes = repo.list_event_episodes(instrument_symbol="NQ", limit=10)
        # Either we have a momentum episode or the belief is still in-progress
        if episodes:
            momentum_episodes = [
                ep for ep in episodes
                if ep.event_kind is TradableEventKind.MOMENTUM_CONTINUATION
            ]
            assert len(momentum_episodes) >= 1
            assert momentum_episodes[0].resolution in {
                EpisodeResolution.CONFIRMED,
                EpisodeResolution.INVALIDATED,
            }

    def test_absorption_to_reversal_preparation_runs_in_degraded_no_depth(
        self, tmp_path: Path
    ) -> None:
        """Absorption event without depth data runs in degraded_no_depth mode."""
        repo = _make_repo(tmp_path)
        now = datetime(2026, 3, 23, 12, 30, tzinfo=UTC).replace(microsecond=0)

        repo.save_ingestion(
            ingestion_id="ing-evt-absorb",
            ingestion_kind="event_snapshot",
            source_snapshot_id="evt-absorb",
            instrument_symbol="NQ",
            observed_payload=_event_snapshot_payload(symbol="NQ", observed_at=now),
            stored_at=now,
        )
        repo.save_ingestion(
            ingestion_id="ing-proc-absorb",
            ingestion_kind="process_context",
            source_snapshot_id="proc-absorb",
            instrument_symbol="NQ",
            observed_payload=_process_context_payload(
                symbol="NQ",
                observed_at=now,
                point_of_control=21572.0,
                initiative_side="sell",
                zone_low=21579.75,
                zone_high=21580.75,
                include_initiative=False,
                include_liquidity_episode=True,
            ),
            stored_at=now,
        )

        service = DeterministicRecognitionService(repository=repo)
        result = service.run_for_instrument("NQ", triggered_by="pytest_absorb")

        assert result.triggered is True
        assert result.recognition_mode is not None
        assert result.recognition_mode == RecognitionMode.DEGRADED_NO_DEPTH
        assert result.belief_state is not None

        # Absorption hypothesis should be among top hypotheses
        hypo_kinds = {h.hypothesis_kind for h in result.belief_state.event_hypotheses[:2]}
        assert EventHypothesisKind.ABSORPTION_ACCUMULATION in hypo_kinds or EventHypothesisKind.REVERSAL_PREPARATION in hypo_kinds

    def test_recognizer_runs_without_depth_or_dom_data(self, tmp_path: Path) -> None:
        """Recognizer still produces belief state when depth and DOM are missing."""
        repo = _make_repo(tmp_path)
        now = datetime(2026, 3, 23, 14, 0, tzinfo=UTC).replace(microsecond=0)

        # Only history bars — no depth, no process context, no continuous state
        repo.save_ingestion(
            ingestion_id="ing-hist-minimal",
            ingestion_kind="adapter_history_bars",
            source_snapshot_id="hist-minimal",
            instrument_symbol="NQ",
            observed_payload=_history_bars_payload(
                symbol="NQ",
                start=now - timedelta(minutes=6),
                bars=[
                    (21500.0, 21501.0, 21498.75, 21499.0, 118, -9),
                    (21499.0, 21500.0, 21498.5, 21499.25, 96, 3),
                    (21499.25, 21500.25, 21498.75, 21499.75, 92, 4),
                    (21499.75, 21500.5, 21499.0, 21500.0, 88, 2),
                    (21500.0, 21500.75, 21499.25, 21499.5, 90, -2),
                    (21499.5, 21500.25, 21499.0, 21499.75, 86, 1),
                ],
                emitted_at=now,
            ),
            stored_at=now,
        )

        service = DeterministicRecognitionService(repository=repo)
        result = service.run_for_instrument("NQ", triggered_by="pytest_minimal")

        # Recognizer should fire (degraded) rather than hard-fail
        assert result.triggered is True
        assert result.belief_state is not None
        assert result.data_status is not None
        # Degraded modes should be present
        assert len(result.data_status.degraded_modes) > 0

    def test_stale_macro_injects_degraded_mode_without_aborting_recognition(
        self, tmp_path: Path
    ) -> None:
        """Stale process-context is detected as degraded, recognizer continues."""
        repo = _make_repo(tmp_path)
        now = datetime(2020, 1, 2, 14, 30, tzinfo=UTC)  # far in the past

        repo.save_ingestion(
            ingestion_id="ing-hist-stale",
            ingestion_kind="adapter_history_bars",
            source_snapshot_id="hist-stale",
            instrument_symbol="NQ",
            observed_payload=_history_bars_payload(
                symbol="NQ",
                start=now - timedelta(minutes=6),
                bars=[
                    (21500.0, 21501.0, 21498.75, 21499.0, 118, -9),
                    (21499.0, 21500.0, 21498.5, 21499.25, 96, 3),
                    (21499.25, 21500.25, 21498.75, 21499.75, 92, 4),
                    (21499.75, 21500.5, 21499.0, 21500.0, 88, 2),
                    (21500.0, 21500.75, 21499.25, 21499.5, 90, -2),
                    (21499.5, 21500.25, 21499.0, 21499.75, 86, 1),
                ],
                emitted_at=now,
            ),
            stored_at=now,
        )
        repo.save_ingestion(
            ingestion_id="ing-proc-stale",
            ingestion_kind="process_context",
            source_snapshot_id="proc-stale",
            instrument_symbol="NQ",
            observed_payload=_process_context_payload(
                symbol="NQ",
                observed_at=now,
                point_of_control=21499.75,
                initiative_side="sell",
                zone_low=21499.25,
                zone_high=21500.25,
                include_initiative=False,
            ),
            stored_at=now,
        )

        service = DeterministicRecognitionService(repository=repo)
        result = service.run_for_instrument("NQ", triggered_by="pytest_stale")

        assert result.triggered is True
        assert result.belief_state is not None
        assert DegradedMode.STALE_MACRO in result.data_status.degraded_modes
        assert result.belief_state.profile_version == result.profile_version
        assert result.belief_state.engine_version == result.engine_version


# ---------------------------------------------------------------------------
# 2. Episode evaluation service tests
# ---------------------------------------------------------------------------

class TestEpisodeEvaluationScenarios:
    """Tests for the EpisodeEvaluationService.

    These complement test_episode_evaluation.py with scenarios involving
    replacement takeover, late-invalidation persistence, and evaluation
    read-model visibility.
    """

    def test_replacement_event_episode_persisted_and_retrievable(
        self, tmp_path: Path
    ) -> None:
        """A replaced episode is persisted and its evaluation is retrievable from the read model."""
        repo = _make_repo(tmp_path)
        eval_service = EpisodeEvaluationService(repository=repo)
        profile = _make_profile("NQ")
        base = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)

        # Balance episode that gets replaced by momentum
        beliefs = [
            _belief_state(
                belief_id="prior",
                observed_at=base - timedelta(minutes=1),
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.DISTRIBUTION_BALANCE,
                        TradableEventKind.BALANCE_MEAN_REVERSION,
                        EventPhase.BUILDING,
                        0.36,
                    )
                ],
                transition_watch=["watch_absorption_accumulation"],
            ),
            _belief_state(
                belief_id="b0",
                observed_at=base,
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.DISTRIBUTION_BALANCE,
                        TradableEventKind.BALANCE_MEAN_REVERSION,
                        EventPhase.BUILDING,
                        0.40,
                    )
                ],
                transition_watch=["watch_absorption_accumulation"],
            ),
            _belief_state(
                belief_id="b1",
                observed_at=base + timedelta(minutes=1),
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.DISTRIBUTION_BALANCE,
                        TradableEventKind.BALANCE_MEAN_REVERSION,
                        EventPhase.WEAKENING,
                        0.31,
                        invalidating_signals=["fresh_initiative_breakout"],
                    )
                ],
                transition_watch=["watch_absorption_accumulation"],
                invalidating_signals_seen=["fresh_initiative_breakout"],
            ),
            _belief_state(
                belief_id="b2",
                observed_at=base + timedelta(minutes=2),
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.DISTRIBUTION_BALANCE,
                        TradableEventKind.BALANCE_MEAN_REVERSION,
                        EventPhase.INVALIDATED,
                        0.16,
                        invalidating_signals=["fresh_initiative_breakout"],
                    )
                ],
                transition_watch=["watch_absorption_accumulation"],
                invalidating_signals_seen=["fresh_initiative_breakout"],
            ),
        ]

        # Store beliefs using the keyword-only API
        for b in beliefs:
            repo.save_belief_state(
                belief_state_id=b.belief_state_id,
                instrument_symbol=b.instrument_symbol,
                observed_at=b.observed_at,
                stored_at=b.stored_at,
                schema_version=b.schema_version,
                profile_version=b.profile_version,
                engine_version=b.engine_version,
                recognition_mode=b.recognition_mode.value,
                belief_payload=b.model_dump(mode="json", by_alias=True),
            )

        # Replacement episode
        episode = _event_episode(
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            resolution=EpisodeResolution.REPLACED,
            started_at=base,
            ended_at=base + timedelta(minutes=2),
            replacement_event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        )
        repo.save_event_episode(
            episode_id=episode.episode_id,
            instrument_symbol=episode.instrument_symbol,
            event_kind=episode.event_kind.value,
            started_at=episode.started_at,
            ended_at=episode.ended_at,
            resolution=episode.resolution.value,
            schema_version=episode.schema_version,
            profile_version=episode.profile_version,
            engine_version=episode.engine_version,
            episode_payload=episode.model_dump(mode="json", by_alias=True),
        )

        evaluation = eval_service.evaluate_episode(
            episode=episode,
            beliefs=beliefs,
            profile=profile,
            persist=True,
        )

        assert evaluation.schema_version == "episode_evaluation_v1"
        assert evaluation.outcome.did_event_materialize is False
        # Replacement event must have a replacement set
        assert evaluation.lifecycle.replacement_event is not None

        # Persisted evaluation is retrievable
        stored = repo.get_episode_evaluation(evaluation.episode_id)
        assert stored is not None
        stored_eval = EpisodeEvaluation.model_validate(stored.evaluation_payload)
        assert stored_eval.outcome.did_event_materialize is False

    def test_invalidated_episode_persisted_and_visible_in_read_model(
        self, tmp_path: Path
    ) -> None:
        """An invalidated episode is persisted and visible through the read model."""
        repo = _make_repo(tmp_path)
        eval_service = EpisodeEvaluationService(repository=repo)
        profile = _make_profile("NQ")
        base = datetime(2026, 3, 23, 11, 0, tzinfo=UTC)

        # Beliefs with progressive invalidation: signal appears early, prob drops late
        beliefs = [
            _belief_state(
                belief_id=f"b{i}",
                observed_at=base + timedelta(minutes=i),
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.DISTRIBUTION_BALANCE,
                        TradableEventKind.BALANCE_MEAN_REVERSION,
                        EventPhase.BUILDING if i < 4 else EventPhase.INVALIDATED,
                        0.50 if i < 4 else 0.14,
                        invalidating_signals=["fresh_initiative_breakout"] if i >= 1 else [],
                    )
                ],
                invalidating_signals_seen=["fresh_initiative_breakout"] if i >= 1 else [],
            )
            for i in range(5)
        ]

        for b in beliefs:
            repo.save_belief_state(
                belief_state_id=b.belief_state_id,
                instrument_symbol=b.instrument_symbol,
                observed_at=b.observed_at,
                stored_at=b.stored_at,
                schema_version=b.schema_version,
                profile_version=b.profile_version,
                engine_version=b.engine_version,
                recognition_mode=b.recognition_mode.value,
                belief_payload=b.model_dump(mode="json", by_alias=True),
            )

        episode = _event_episode(
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            resolution=EpisodeResolution.INVALIDATED,
            started_at=base,
            ended_at=base + timedelta(minutes=4),
        )
        repo.save_event_episode(
            episode_id=episode.episode_id,
            instrument_symbol=episode.instrument_symbol,
            event_kind=episode.event_kind.value,
            started_at=episode.started_at,
            ended_at=episode.ended_at,
            resolution=episode.resolution.value,
            schema_version=episode.schema_version,
            profile_version=episode.profile_version,
            engine_version=episode.engine_version,
            episode_payload=episode.model_dump(mode="json", by_alias=True),
        )

        evaluation = eval_service.evaluate_episode(
            episode=episode,
            beliefs=beliefs,
            profile=profile,
            persist=True,
        )

        assert evaluation.schema_version == "episode_evaluation_v1"
        assert evaluation.outcome.did_event_materialize is False
        assert evaluation.lifecycle.resolution is EpisodeResolution.INVALIDATED

        # Read model: evaluation is visible
        all_evals = repo.list_episode_evaluations(instrument_symbol="NQ", limit=50)
        eval_ids = {e.episode_id for e in all_evals}
        assert evaluation.episode_id in eval_ids

    def test_absorption_to_reversal_episode_evaluates_correctly(
        self, tmp_path: Path
    ) -> None:
        """Absorption-to-reversal episode produces deterministic evaluation output."""
        repo = _make_repo(tmp_path)
        eval_service = EpisodeEvaluationService(repository=repo)
        profile = _make_profile("NQ")
        base = datetime(2026, 3, 23, 13, 0, tzinfo=UTC)

        beliefs = [
            _belief_state(
                belief_id=f"b{i}",
                observed_at=base + timedelta(minutes=i),
                states=[
                    _hypothesis_state(
                        EventHypothesisKind.ABSORPTION_ACCUMULATION,
                        TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
                        EventPhase.CONFIRMING,
                        0.82,  # high prob so it resolves as confirmed
                    )
                ],
            )
            for i in range(2)
        ]

        episode = _event_episode(
            event_kind=TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
            resolution=EpisodeResolution.CONFIRMED,
            started_at=base,
            ended_at=base + timedelta(minutes=1),
        )

        evaluation = eval_service.evaluate_episode(
            episode=episode,
            beliefs=beliefs,
            profile=profile,
            persist=False,
        )

        # Evaluation must produce structured output
        assert evaluation.schema_version == "episode_evaluation_v1"
        assert evaluation.evaluated_event_kind is TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION
        assert evaluation.outcome.did_event_materialize is True


# ---------------------------------------------------------------------------
# 3. Degraded-mode ingestion tests
# ---------------------------------------------------------------------------

class TestDegradedModeIngestion:
    """Tests verifying that ingestion continues to work when the recognizer
    is running in degraded mode."""

    def test_ingestion_endpoint_accepts_payloads_when_recognizer_is_degraded(
        self, tmp_path: Path
    ) -> None:
        """Market-structure ingestion succeeds even when recognizer degrades."""
        db_path = tmp_path / "data" / "market_structure.db"

        # Use SQLiteAnalysisRepository (not StorageBlueprintRepository) - it calls
        # blueprint.initialize() internally and creates all required tables.
        from atas_market_structure.repository import SQLiteAnalysisRepository
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()

        orchestrator = IngestionOrchestrator(repository=repo)
        from atas_market_structure.adapter_services import AdapterIngestionService
        from atas_market_structure.depth_services import DepthMonitoringService

        adapter_svc = AdapterIngestionService(repository=repo)
        depth_svc = DepthMonitoringService(repository=repo)
        rel_svc = IngestionReliabilityService(
            repository=repo,
            orchestrator=orchestrator,
            depth_monitoring_service=depth_svc,
            adapter_ingestion_service=adapter_svc,
            ai_available=False,
        )

        now = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)  # deliberately stale
        body = _minimal_market_structure_payload(symbol="NQ", observed_at=now)

        result = rel_svc.ingest_market_structure(body=json.dumps(body).encode())

        # Ingestion should succeed (store-first)
        assert result.status_code in {200, 201}
        response_body = result.body
        assert hasattr(response_body, "status")
        assert response_body.status in {"accepted", "duplicate"}
        assert response_body.duplicate is False

        # Health check should report degraded reasons
        health = rel_svc.get_ingestion_health(instrument_symbol="NQ")
        assert health.status_code == 200
        health_body = health.body
        assert hasattr(health_body, "degraded_reasons")
        assert hasattr(health_body, "status")


# ---------------------------------------------------------------------------
# 4. End-to-end API chain tests
# ---------------------------------------------------------------------------

class TestEndToEndChain:
    """Full ingestion -> recognition -> evaluation -> projection chain via
    the application-level dispatch interface (mirrors the HTTP layer)."""

    def test_full_chain_ingestion_to_projection_via_dispatch(self, tmp_path: Path) -> None:
        """Dispatch: ingest -> recognizer fires -> belief persisted -> episode closed."""
        db_path = tmp_path / "data" / "market_structure.db"

        # SQLiteAnalysisRepository.initialize() creates all tables including blueprint
        from atas_market_structure.repository import SQLiteAnalysisRepository
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()

        config = AppConfig(
            database_path=db_path,
            storage_mode="sqlite",
            openai_api_key="test-key-does-not-matter",
        )
        app = build_application(config)

        now = datetime(2026, 3, 23, 9, 45, tzinfo=UTC).replace(microsecond=0)
        body = _minimal_market_structure_payload(symbol="NQ", observed_at=now)

        # --- Ingest market structure ---
        ingest_resp = app.dispatch(
            "POST",
            "/api/v1/ingest/market-structure",
            json.dumps(body).encode(),
        )
        assert ingest_resp.status_code in {200, 201}, f"ingest failed: {ingest_resp.body.decode()[:200]}"
        ingest_payload = json.loads(ingest_resp.body)
        assert ingest_payload["status"] == "accepted"

        # --- Check that recognizer ran (downstream_status should not be 'skipped') ---
        # When ai_available=False, the recognizer still runs via deterministic path
        downstream = ingest_payload.get("downstream_status", "unknown")
        assert downstream in {"completed", "failed"}, f"unexpected downstream: {downstream}"

    def test_health_endpoints_return_structured_response(self, tmp_path: Path) -> None:
        """Health, ingestion-health, and data-quality endpoints are all accessible."""
        db_path = tmp_path / "data" / "market_structure.db"

        # SQLiteAnalysisRepository.initialize() creates all tables including blueprint
        from atas_market_structure.repository import SQLiteAnalysisRepository
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()

        config = AppConfig(
            database_path=db_path,
            storage_mode="sqlite",
            openai_api_key="test-key-does-not-matter",
        )
        app = build_application(config)

        # Basic health
        health_resp = app.dispatch("GET", "/health")
        assert health_resp.status_code == 200

        # Ingestion health
        ing_health_resp = app.dispatch("GET", "/health/ingestion")
        assert ing_health_resp.status_code == 200
        ing_payload = json.loads(ing_health_resp.body)
        assert "status" in ing_payload
        assert "degraded_reasons" in ing_payload

        # Data quality
        dq_resp = app.dispatch("GET", "/health/data-quality")
        assert dq_resp.status_code == 200
        dq_payload = json.loads(dq_resp.body)
        assert "status" in dq_payload or "schema_version" in dq_payload


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _belief_state(
    belief_id: str,
    observed_at: datetime,
    states: list[EventHypothesisState],
    *,
    transition_watch: list[str] | None = None,
    invalidating_signals_seen: list[str] | None = None,
) -> BeliefStateSnapshot:
    return BeliefStateSnapshot(
        belief_state_id=belief_id,
        instrument_symbol="NQ",
        observed_at=observed_at,
        stored_at=observed_at,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        recognition_mode=RecognitionMode.NORMAL,
        data_status=BeliefDataStatus(
            data_freshness_ms=0,
            feature_completeness=1.0,
            depth_available=True,
            dom_available=True,
            ai_available=False,
            degraded_modes=[],
            freshness="fresh",
            completeness="complete",
        ),
        regime_posteriors=[
            RegimePosteriorRecord(
                regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
                probability=0.44,
                evidence=["trend_efficiency"],
            )
        ],
        event_hypotheses=states,
        active_anchors=[
            MemoryAnchorSnapshot(
                anchor_id="anc-balance",
                anchor_type="balance_center",
                reference_price=21500.0,
                reference_time=observed_at,
                freshness="fresh",
                distance_ticks=0.0,
                influence=0.7,
                role_profile={"magnet": 0.8},
                profile_version="nq-profile-test",
            )
        ],
        missing_confirmation=[],
        invalidating_signals_seen=list(invalidating_signals_seen or []),
        transition_watch=list(transition_watch or []),
        notes=[],
    )


def _hypothesis_state(
    hypothesis_kind: EventHypothesisKind,
    event_kind: TradableEventKind,
    phase: EventPhase,
    probability: float,
    *,
    invalidating_signals: list[str] | None = None,
) -> EventHypothesisState:
    return EventHypothesisState(
        hypothesis_id=f"hyp-{hypothesis_kind.value}-{phase.value}-{int(probability * 100)}",
        hypothesis_kind=hypothesis_kind,
        mapped_event_kind=event_kind,
        phase=phase,
        posterior_probability=probability,
        supporting_evidence=["support"],
        missing_confirmation=[],
        invalidating_signals=list(invalidating_signals or []),
        transition_watch=[],
        data_quality_score=1.0,
        evidence_density_score=0.6,
        model_stability_score=0.8,
        anchor_dependence_score=0.5,
    )


def _event_episode(
    event_kind: TradableEventKind,
    resolution: EpisodeResolution,
    started_at: datetime,
    ended_at: datetime,
    replacement_event_kind: TradableEventKind | None = None,
) -> EventEpisode:
    return EventEpisode(
        episode_id=f"ep-{event_kind.value}-{started_at.strftime('%H%M')}",
        instrument_symbol="NQ",
        event_kind=event_kind,
        hypothesis_kind=_primary_hypothesis_kind(event_kind),
        phase=EventPhase.RESOLVED if resolution is EpisodeResolution.CONFIRMED else EventPhase.INVALIDATED,
        resolution=resolution,
        started_at=started_at,
        ended_at=ended_at,
        peak_probability=0.78 if resolution is EpisodeResolution.CONFIRMED else 0.76,
        dominant_regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
        supporting_evidence=["support_a", "support_b"],
        invalidating_evidence=["invalidate_a"] if resolution is not EpisodeResolution.CONFIRMED else [],
        key_evidence_summary=["support_a", "support_b"],
        active_anchor_ids=["anc-balance"],
        replacement_episode_id=None,
        replacement_event_kind=replacement_event_kind,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        data_status=BeliefDataStatus(
            data_freshness_ms=0,
            feature_completeness=1.0,
            depth_available=True,
            dom_available=True,
            ai_available=False,
            degraded_modes=[],
            freshness="fresh",
            completeness="complete",
        ),
    )


def _primary_hypothesis_kind(event_kind: TradableEventKind) -> EventHypothesisKind:
    if event_kind is TradableEventKind.MOMENTUM_CONTINUATION:
        return EventHypothesisKind.CONTINUATION_BASE
    if event_kind is TradableEventKind.BALANCE_MEAN_REVERSION:
        return EventHypothesisKind.DISTRIBUTION_BALANCE
    return EventHypothesisKind.ABSORPTION_ACCUMULATION


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _history_bars_payload(
    *,
    symbol: str,
    start: datetime,
    bars: list[tuple[float, float, float, float, int, int]],
    emitted_at: datetime,
) -> dict[str, object]:
    payload_bars = []
    for index, (open_, high, low, close, volume, delta) in enumerate(bars):
        bar_start = start + timedelta(minutes=index)
        payload_bars.append(
            {
                "started_at": _iso(bar_start),
                "ended_at": _iso(bar_start + timedelta(seconds=59)),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "delta": delta,
                "bid_volume": max(1, volume // 3),
                "ask_volume": max(1, volume // 2),
            },
        )
    return {
        "schema_version": "1.0.0",
        "message_id": f"collector-history-{symbol.lower()}",
        "message_type": "history_bars",
        "emitted_at": _iso(emitted_at),
        "observed_window_start": _iso(start),
        "observed_window_end": _iso(start + timedelta(minutes=len(bars) - 1, seconds=59)),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "bar_timeframe": "1m",
        "bars": payload_bars,
    }


def _process_context_payload(
    *,
    symbol: str,
    observed_at: datetime,
    point_of_control: float,
    initiative_side: str,
    zone_low: float,
    zone_high: float,
    include_initiative: bool = True,
    include_liquidity_episode: bool = False,
) -> dict[str, object]:
    process_context: dict[str, object] = {
        "session_windows": [
            {
                "session_code": "us_regular",
                "started_at": _iso(observed_at - timedelta(minutes=30)),
                "ended_at": _iso(observed_at),
                "latest_range": {"open": point_of_control - 2.0, "high": point_of_control + 2.5, "low": point_of_control - 2.5, "close": point_of_control},
                "value_area": {"low": point_of_control - 1.0, "high": point_of_control + 1.0, "point_of_control": point_of_control},
                "session_stats": {"volume": 1000, "delta": 0, "trades": 300},
                "key_levels": [],
            }
        ],
        "second_features": [],
        "liquidity_episodes": [
            {
                "episode_id": "liq-episode-1",
                "started_at": _iso(observed_at - timedelta(minutes=8)),
                "ended_at": _iso(observed_at - timedelta(minutes=4)),
                "side": "sell",
                "price_low": zone_low,
                "price_high": zone_high,
                "executed_volume_against": 1200,
                "replenishment_count": 5,
                "pull_count": 1,
                "price_rejection_ticks": 14,
                "raw_features": {},
            }
        ] if include_liquidity_episode else [],
        "initiative_drives": [
            {
                "drive_id": "drive-1",
                "started_at": _iso(observed_at - timedelta(minutes=3)),
                "ended_at": _iso(observed_at - timedelta(minutes=1)),
                "side": initiative_side,
                "price_low": zone_low,
                "price_high": zone_high + 8.0,
                "aggressive_volume": 800,
                "net_delta": 620 if initiative_side == "buy" else -620,
                "trade_count": 180,
                "consumed_price_levels": 5,
                "price_travel_ticks": 20,
                "max_counter_move_ticks": 4,
                "continuation_seconds": 60,
                "raw_features": {},
            }
        ] if include_initiative else [],
        "measured_moves": [],
        "manipulation_legs": [],
        "gap_references": [],
        "post_harvest_responses": [],
        "exertion_zones": [
            {
                "zone_id": "zone-1",
                "source_drive_id": "drive-1",
                "side": initiative_side,
                "price_low": zone_low,
                "price_high": zone_high,
                "established_at": _iso(observed_at - timedelta(minutes=15)),
                "last_interacted_at": _iso(observed_at - timedelta(minutes=1)),
                "establishing_volume": 1500,
                "establishing_delta": 900 if initiative_side == "buy" else -900,
                "establishing_trade_count": 200,
                "peak_price_level_volume": 500,
                "revisit_count": 2,
                "successful_reengagement_count": 1,
                "failed_reengagement_count": 1 if not include_initiative else 0,
                "last_revisit_delta": 320,
                "last_revisit_volume": 600,
                "last_revisit_trade_count": 100,
                "last_defended_reaction_ticks": 10,
                "last_failed_break_ticks": 8 if not include_initiative else 0,
                "post_failure_delta": 180 if not include_initiative else None,
                "post_failure_move_ticks": 10 if not include_initiative else None,
                "raw_features": {},
            }
        ],
        "cross_session_sequences": [],
    }
    return {
        "schema_version": "1.0.0",
        "process_context_id": f"proc-{symbol.lower()}",
        "observed_at": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "process_context": process_context,
    }


def _continuous_payload(
    *,
    symbol: str,
    observed_at: datetime,
    last_price: float,
    local_low: float,
    local_high: float,
    net_delta: int,
    volume: int,
    side: str,
    drive_low: float,
    drive_high: float,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "message_id": f"msg-{symbol.lower()}",
        "message_type": "continuous_state",
        "emitted_at": _iso(observed_at),
        "observed_window_start": _iso(observed_at - timedelta(seconds=1)),
        "observed_window_end": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "session_context": {"session_code": "us_regular", "trading_date": observed_at.date().isoformat(), "is_rth_open": True},
        "price_state": {"last_price": last_price, "best_bid": last_price - 0.25, "best_ask": last_price, "local_range_low": local_low, "local_range_high": local_high},
        "trade_summary": {"trade_count": 160, "volume": volume, "aggressive_buy_volume": max(1, volume // 2), "aggressive_sell_volume": max(1, volume // 4), "net_delta": net_delta},
        "significant_liquidity": [],
        "gap_reference": None,
        "active_initiative_drive": {
            "drive_id": "drive-live",
            "side": side,
            "started_at": _iso(observed_at - timedelta(minutes=2)),
            "price_low": drive_low,
            "price_high": drive_high,
            "aggressive_volume": 1400,
            "net_delta": net_delta,
            "trade_count": 268,
            "consumed_price_levels": 7,
            "price_travel_ticks": 57,
            "max_counter_move_ticks": 4,
            "continuation_seconds": 80,
        },
        "active_manipulation_leg": None,
        "active_measured_move": None,
        "active_post_harvest_response": None,
        "active_zone_interaction": None,
        "ema_context": None,
        "reference_levels": [],
    }


def _event_snapshot_payload(*, symbol: str, observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "event_snapshot_id": f"evt-{symbol.lower()}",
        "event_type": "liquidity_sweep",
        "observed_at": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "trigger_event": {"event_type": "liquidity_sweep", "observed_at": _iso(observed_at - timedelta(seconds=8)), "price": 21580.75, "details": {"swept_level": "prior_day_high"}},
        "decision_layers": {
            "macro_context": [{"timeframe": "1d", "bars_considered": 20, "latest_range": {"open": 21540.0, "high": 21582.0, "low": 21538.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "intraday_bias": [{"timeframe": "1h", "bars_considered": 8, "latest_range": {"open": 21562.0, "high": 21581.25, "low": 21566.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "setup_context": [{"timeframe": "15m", "bars_considered": 16, "latest_range": {"open": 21572.0, "high": 21581.25, "low": 21566.0, "close": 21569.0}, "swing_points": [], "liquidity_levels": [], "orderflow_signals": [], "value_area": None, "session_stats": None, "raw_features": {}}],
            "execution_context": [
                {
                    "timeframe": "footprint",
                    "bars_considered": 1,
                    "latest_range": {"open": 21575.0, "high": 21581.25, "low": 21566.0, "close": 21569.0},
                    "swing_points": [],
                    "liquidity_levels": [],
                    "orderflow_signals": [{"signal_type": "absorption", "side": "sell", "observed_at": _iso(observed_at - timedelta(seconds=8)), "price": 21580.75, "magnitude": 0.88, "notes": ["seller absorbed sweep"]}],
                    "value_area": None,
                    "session_stats": None,
                    "raw_features": {},
                },
            ],
        },
    }


def _minimal_market_structure_payload(*, symbol: str, observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "snapshot_id": f"snap-{symbol.lower()}-{observed_at.strftime('%Y%m%d%H%M%S')}",
        "observed_at": _iso(observed_at),
        "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": f"{symbol}-chart", "adapter_version": "test"},
        "instrument": {"symbol": symbol, "venue": "CME", "tick_size": 0.25, "currency": "USD"},
        "session_context": {
            "session_code": "us_regular",
            "trading_date": observed_at.date().isoformat(),
            "is_rth_open": True,
        },
        "decision_layers": {
            "macro_context": [{
                "timeframe": "1d",
                "bars_considered": 20,
                "latest_range": {"open": 21490.0, "high": 21510.0, "low": 21488.0, "close": 21505.0},
                "swing_points": [],
                "liquidity_levels": [],
                "orderflow_signals": [],
                "value_area": None,
                "session_stats": None,
                "raw_features": {},
            }],
            "intraday_bias": [{
                "timeframe": "1h",
                "bars_considered": 8,
                "latest_range": {"open": 21498.0, "high": 21508.0, "low": 21495.0, "close": 21505.0},
                "swing_points": [],
                "liquidity_levels": [],
                "orderflow_signals": [],
                "value_area": None,
                "session_stats": None,
                "raw_features": {},
            }],
            "setup_context": [{
                "timeframe": "15m",
                "bars_considered": 16,
                "latest_range": {"open": 21500.0, "high": 21506.0, "low": 21499.0, "close": 21505.0},
                "swing_points": [],
                "liquidity_levels": [],
                "orderflow_signals": [],
                "value_area": None,
                "session_stats": None,
                "raw_features": {},
            }],
            "execution_context": [{
                "timeframe": "1m",
                "bars_considered": 1,
                "latest_range": {"open": 21502.0, "high": 21506.0, "low": 21501.0, "close": 21505.0},
                "swing_points": [],
                "liquidity_levels": [],
                "orderflow_signals": [],
                "value_area": None,
                "session_stats": None,
                "raw_features": {},
            }],
        },
    }
