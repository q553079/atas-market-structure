from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.golden_cases import (
    GoldenReplayCase,
    MaterializedGoldenReplayIngestion,
    materialize_case_ingestions,
)
from atas_market_structure.models import (
    BeliefStateSnapshot,
    DegradedMode,
    EpisodeEvaluation,
    EpisodeResolution,
    EvaluationFailureMode,
    EventEpisode,
    RecognitionMode,
    TradableEventKind,
)
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.repository import AnalysisRepository, SQLiteAnalysisRepository


RAW_REPLAY_INGESTION_KINDS: tuple[str, ...] = (
    "market_structure",
    "event_snapshot",
    "process_context",
    "depth_snapshot",
    "adapter_continuous_state",
    "adapter_trigger_burst",
    "adapter_history_bars",
    "adapter_history_footprint",
)


class ReplayStepOutcome(BaseModel):
    """One replay step result inside a rebuild run."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    ingestion_id: str
    ingestion_kind: str
    stored_at: datetime
    triggered: bool
    top_event_kind: TradableEventKind | None = None
    recognition_mode: RecognitionMode | None = None
    degraded_modes: list[DegradedMode] = Field(default_factory=list)
    closed_episode_count: int = Field(0, ge=0)
    evaluation_count: int = Field(0, ge=0)
    active_anchor_count: int = Field(0, ge=0)


class ReplayRebuildReport(BaseModel):
    """Summary report emitted by the local replay/rebuild runner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["replay_rebuild_report_v1"]
    run_id: str
    source_kind: Literal["golden_case", "repository"]
    target_database: str
    source_database: str | None = None
    case_id: str | None = None
    instrument_symbol: str
    ai_in_critical_path: Literal[False] = False
    started_at: datetime
    completed_at: datetime
    replayed_ingestion_count: int = Field(..., ge=0)
    belief_count: int = Field(..., ge=0)
    episode_count: int = Field(..., ge=0)
    evaluation_count: int = Field(..., ge=0)
    final_market_time: datetime | None = None
    top_event_kind: TradableEventKind | None = None
    recognition_mode: RecognitionMode | None = None
    degraded_modes: list[DegradedMode] = Field(default_factory=list)
    data_freshness: str | None = None
    data_completeness: str | None = None
    active_anchor_count: int = Field(0, ge=0)
    profile_version: str | None = None
    engine_version: str | None = None
    episode_event_kinds: list[TradableEventKind] = Field(default_factory=list)
    episode_resolutions: list[EpisodeResolution] = Field(default_factory=list)
    evaluation_failure_modes: list[EvaluationFailureMode] = Field(default_factory=list)
    evaluation_schema_versions: list[str] = Field(default_factory=list)
    step_outcomes: list[ReplayStepOutcome] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReplayRebuildRunner:
    """Replay append-only raw inputs into a fresh local SQLite analysis database."""

    def run_case(
        self,
        *,
        case: GoldenReplayCase,
        output_database_path: Path,
    ) -> ReplayRebuildReport:
        """Run one golden replay case against a fresh target database."""

        self._ensure_target_available(output_database_path)
        target_repository = SQLiteAnalysisRepository(output_database_path)
        target_repository.initialize()
        ingestions = materialize_case_ingestions(case)
        return self._replay_ingestions(
            target_repository=target_repository,
            target_database_path=output_database_path,
            ingestions=ingestions,
            instrument_symbol=case.instrument_symbol,
            ai_available=case.ai_available,
            source_kind="golden_case",
            case_id=case.case_id,
            source_database=None,
            notes=[*case.notes, f"scenario={case.scenario}"],
        )

    def run_repository_rebuild(
        self,
        *,
        source_database_path: Path | None = None,
        source_repository: AnalysisRepository | None = None,
        source_label: str | None = None,
        output_database_path: Path,
        instrument_symbol: str,
        ai_available: bool = False,
        session_date: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        page_size: int = 5000,
    ) -> ReplayRebuildReport:
        """Replay repository raw ingestions into a fresh target database.

        Exactly one source backend must be provided:
        - ``source_database_path`` for SQLite-only replay
        - ``source_repository`` for an already-built hybrid/ClickHouse source
        """

        self._ensure_target_available(output_database_path)
        source_repository, resolved_source_label = self._resolve_source_repository(
            source_database_path=source_database_path,
            source_repository=source_repository,
            source_label=source_label,
        )
        target_repository = SQLiteAnalysisRepository(output_database_path)
        target_repository.initialize()
        self._copy_active_versions(
            source_repository=source_repository,
            target_repository=target_repository,
            instrument_symbol=instrument_symbol,
        )
        ingestions = self._collect_repository_ingestions(
            repository=source_repository,
            instrument_symbol=instrument_symbol,
            session_date=session_date,
            window_start=window_start,
            window_end=window_end,
            page_size=page_size,
        )
        notes = [f"source={resolved_source_label}", f"instrument={instrument_symbol}", f"page_size={page_size}"]
        if session_date is not None:
            notes.append(f"session_date={session_date}")
        if window_start is not None:
            notes.append(f"window_start={window_start.isoformat()}")
        if window_end is not None:
            notes.append(f"window_end={window_end.isoformat()}")
        return self._replay_ingestions(
            target_repository=target_repository,
            target_database_path=output_database_path,
            ingestions=ingestions,
            instrument_symbol=instrument_symbol,
            ai_available=ai_available,
            source_kind="repository",
            case_id=None,
            source_database=resolved_source_label,
            notes=notes,
        )

    def validate_case_report(
        self,
        *,
        case: GoldenReplayCase,
        report: ReplayRebuildReport,
    ) -> list[str]:
        """Return human-readable validation errors for one case report."""

        expectation = case.expected
        errors: list[str] = []
        if report.top_event_kind != expectation.top_event_kind:
            errors.append(
                f"top_event_kind expected {expectation.top_event_kind.value} but got {report.top_event_kind.value if report.top_event_kind else 'none'}",
            )
        if report.recognition_mode != expectation.recognition_mode:
            errors.append(
                f"recognition_mode expected {expectation.recognition_mode.value} but got {report.recognition_mode.value if report.recognition_mode else 'none'}",
            )
        degraded = set(report.degraded_modes)
        for mode in expectation.required_degraded_modes:
            if mode not in degraded:
                errors.append(f"required degraded mode missing: {mode.value}")
        for mode in expectation.forbidden_degraded_modes:
            if mode in degraded:
                errors.append(f"forbidden degraded mode present: {mode.value}")
        if report.belief_count < expectation.minimum_belief_count:
            errors.append(
                f"belief_count expected at least {expectation.minimum_belief_count} but got {report.belief_count}",
            )
        if report.episode_count < expectation.minimum_episode_count:
            errors.append(
                f"episode_count expected at least {expectation.minimum_episode_count} but got {report.episode_count}",
            )
        if report.evaluation_count < expectation.minimum_evaluation_count:
            errors.append(
                f"evaluation_count expected at least {expectation.minimum_evaluation_count} but got {report.evaluation_count}",
            )
        if report.active_anchor_count < expectation.minimum_active_anchor_count:
            errors.append(
                f"active_anchor_count expected at least {expectation.minimum_active_anchor_count} but got {report.active_anchor_count}",
            )
        episode_kinds = set(report.episode_event_kinds)
        for kind in expectation.required_episode_event_kinds:
            if kind not in episode_kinds:
                errors.append(f"required episode event kind missing: {kind.value}")
        episode_resolutions = set(report.episode_resolutions)
        for resolution in expectation.required_episode_resolutions:
            if resolution not in episode_resolutions:
                errors.append(f"required episode resolution missing: {resolution.value}")
        failure_modes = set(report.evaluation_failure_modes)
        for failure_mode in expectation.required_evaluation_failure_modes:
            if failure_mode not in failure_modes:
                errors.append(f"required evaluation failure mode missing: {failure_mode.value}")
        if expectation.data_completeness is not None and report.data_completeness != expectation.data_completeness:
            errors.append(
                f"data_completeness expected {expectation.data_completeness} but got {report.data_completeness or 'none'}",
            )
        if expectation.data_freshness is not None and report.data_freshness != expectation.data_freshness:
            errors.append(
                f"data_freshness expected {expectation.data_freshness} but got {report.data_freshness or 'none'}",
            )
        return errors

    def _replay_ingestions(
        self,
        *,
        target_repository: SQLiteAnalysisRepository,
        target_database_path: Path,
        ingestions: list[MaterializedGoldenReplayIngestion],
        instrument_symbol: str,
        ai_available: bool,
        source_kind: Literal["golden_case", "repository"],
        case_id: str | None,
        source_database: str | None,
        notes: list[str],
    ) -> ReplayRebuildReport:
        if not ingestions:
            raise ValueError("no raw ingestions matched the requested replay scope")
        started_at = datetime.now(tz=UTC)
        service = DeterministicRecognitionService(
            repository=target_repository,
            ai_available=ai_available,
        )
        step_outcomes: list[ReplayStepOutcome] = []
        for ingestion in ingestions:
            target_repository.save_ingestion(
                ingestion_id=ingestion.ingestion_id,
                ingestion_kind=ingestion.ingestion_kind,
                source_snapshot_id=ingestion.source_snapshot_id,
                instrument_symbol=instrument_symbol,
                observed_payload=ingestion.observed_payload,
                stored_at=ingestion.stored_at,
            )
            result = service.run_for_instrument(
                instrument_symbol,
                triggered_by=f"replay:{ingestion.ingestion_id}",
                reference_time=ingestion.stored_at,
            )
            belief = result.belief_state
            step_outcomes.append(
                ReplayStepOutcome(
                    step_id=ingestion.step_id,
                    ingestion_id=ingestion.ingestion_id,
                    ingestion_kind=ingestion.ingestion_kind,
                    stored_at=ingestion.stored_at,
                    triggered=result.triggered,
                    top_event_kind=(
                        belief.event_hypotheses[0].mapped_event_kind
                        if belief is not None and belief.event_hypotheses
                        else None
                    ),
                    recognition_mode=result.recognition_mode,
                    degraded_modes=list(result.data_status.degraded_modes) if result.data_status is not None else [],
                    closed_episode_count=len(result.closed_episodes),
                    evaluation_count=len(result.episode_evaluations),
                    active_anchor_count=len(belief.active_anchors) if belief is not None else 0,
                ),
            )
        completed_at = datetime.now(tz=UTC)
        beliefs = [
            BeliefStateSnapshot.model_validate(item.belief_payload)
            for item in target_repository.list_belief_states(instrument_symbol=instrument_symbol, limit=500)
        ]
        beliefs.sort(key=lambda item: (item.observed_at, item.stored_at))
        episodes = [
            EventEpisode.model_validate(item.episode_payload)
            for item in target_repository.list_event_episodes(instrument_symbol=instrument_symbol, limit=500)
        ]
        episodes.sort(key=lambda item: (item.ended_at, item.started_at))
        evaluations = [
            EpisodeEvaluation.model_validate(item.evaluation_payload)
            for item in target_repository.list_episode_evaluations(instrument_symbol=instrument_symbol, limit=500)
        ]
        evaluations.sort(key=lambda item: (item.market_time_end, item.evaluated_at))
        latest_belief = beliefs[-1] if beliefs else None
        return ReplayRebuildReport(
            schema_version="replay_rebuild_report_v1",
            run_id=f"rebuild-{uuid4().hex}",
            source_kind=source_kind,
            target_database=str(target_database_path),
            source_database=source_database,
            case_id=case_id,
            instrument_symbol=instrument_symbol,
            started_at=started_at,
            completed_at=completed_at,
            replayed_ingestion_count=len(ingestions),
            belief_count=len(beliefs),
            episode_count=len(episodes),
            evaluation_count=len(evaluations),
            final_market_time=latest_belief.observed_at if latest_belief is not None else None,
            top_event_kind=(
                latest_belief.event_hypotheses[0].mapped_event_kind
                if latest_belief is not None and latest_belief.event_hypotheses
                else None
            ),
            recognition_mode=latest_belief.recognition_mode if latest_belief is not None else None,
            degraded_modes=list(latest_belief.data_status.degraded_modes) if latest_belief is not None else [],
            data_freshness=latest_belief.data_status.freshness if latest_belief is not None else None,
            data_completeness=latest_belief.data_status.completeness if latest_belief is not None else None,
            active_anchor_count=len(latest_belief.active_anchors) if latest_belief is not None else 0,
            profile_version=latest_belief.profile_version if latest_belief is not None else None,
            engine_version=latest_belief.engine_version if latest_belief is not None else None,
            episode_event_kinds=_unique_in_order(item.event_kind for item in episodes),
            episode_resolutions=_unique_in_order(item.resolution for item in episodes),
            evaluation_failure_modes=_unique_in_order(
                item.diagnosis.primary_failure_mode
                for item in evaluations
            ),
            evaluation_schema_versions=_unique_in_order(item.schema_version for item in evaluations),
            step_outcomes=step_outcomes,
            notes=notes,
        )

    def _collect_repository_ingestions(
        self,
        *,
        repository: AnalysisRepository,
        instrument_symbol: str,
        session_date: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
        page_size: int,
    ) -> list[MaterializedGoldenReplayIngestion]:
        start_dt, end_dt = self._resolve_window(
            session_date=session_date,
            window_start=window_start,
            window_end=window_end,
        )
        ingestions: list[MaterializedGoldenReplayIngestion] = []
        for kind in RAW_REPLAY_INGESTION_KINDS:
            for stored in self._iter_source_ingestions(
                repository=repository,
                ingestion_kind=kind,
                instrument_symbol=instrument_symbol,
                start_dt=start_dt,
                end_dt=end_dt,
                page_size=page_size,
            ):
                ingestions.append(
                    MaterializedGoldenReplayIngestion(
                        ingestion_id=stored.ingestion_id,
                        ingestion_kind=stored.ingestion_kind,
                        source_snapshot_id=stored.source_snapshot_id,
                        instrument_symbol=stored.instrument_symbol,
                        stored_at=stored.stored_at,
                        observed_payload=stored.observed_payload,
                        step_id=stored.ingestion_id,
                    ),
                )
        ingestions.sort(key=lambda item: (item.stored_at, item.ingestion_kind, item.ingestion_id))
        return ingestions

    @staticmethod
    def _iter_source_ingestions(
        *,
        repository: AnalysisRepository,
        ingestion_kind: str,
        instrument_symbol: str,
        start_dt: datetime | None,
        end_dt: datetime | None,
        page_size: int,
    ):
        safe_page_size = max(1, int(page_size))
        if hasattr(repository, "iter_ingestions_paginated"):
            yield from repository.iter_ingestions_paginated(
                ingestion_kind=ingestion_kind,
                instrument_symbol=instrument_symbol,
                page_size=safe_page_size,
                stored_at_after=start_dt,
                stored_at_before=end_dt,
            )
            return
        for stored in repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            limit=safe_page_size,
            stored_at_after=start_dt,
            stored_at_before=end_dt,
        ):
            yield stored

    @staticmethod
    def _copy_active_versions(
        *,
        source_repository: AnalysisRepository,
        target_repository: SQLiteAnalysisRepository,
        instrument_symbol: str,
    ) -> None:
        profile = source_repository.get_active_instrument_profile(instrument_symbol)
        if profile is not None:
            target_repository.save_instrument_profile(
                instrument_symbol=profile.instrument_symbol,
                profile_version=profile.profile_version,
                schema_version=profile.schema_version,
                ontology_version=profile.ontology_version,
                is_active=profile.is_active,
                profile_payload=profile.profile_payload,
                created_at=profile.created_at,
            )
        build = source_repository.get_active_recognizer_build()
        if build is not None:
            target_repository.save_recognizer_build(
                engine_version=build.engine_version,
                schema_version=build.schema_version,
                ontology_version=build.ontology_version,
                is_active=build.is_active,
                status=build.status,
                build_payload=build.build_payload,
                created_at=build.created_at,
            )

    @staticmethod
    def _resolve_window(
        *,
        session_date: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        if session_date is None:
            return window_start, window_end
        date_value = datetime.fromisoformat(session_date).date()
        start = datetime.combine(date_value, time.min, tzinfo=UTC)
        end = datetime.combine(date_value, time.max, tzinfo=UTC)
        if window_start is not None:
            start = max(start, window_start)
        if window_end is not None:
            end = min(end, window_end)
        return start, end

    @staticmethod
    def _ensure_target_available(database_path: Path) -> None:
        if database_path.exists():
            raise ValueError(f"target database already exists: {database_path}")
        database_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_source_repository(
        *,
        source_database_path: Path | None,
        source_repository: AnalysisRepository | None,
        source_label: str | None,
    ) -> tuple[AnalysisRepository, str]:
        if (source_database_path is None) == (source_repository is None):
            raise ValueError("exactly one of source_database_path or source_repository must be provided")
        if source_repository is not None:
            source_repository.initialize()
            return source_repository, source_label or type(source_repository).__name__
        assert source_database_path is not None
        sqlite_source_repository = SQLiteAnalysisRepository(source_database_path)
        sqlite_source_repository.initialize()
        return sqlite_source_repository, source_label or str(source_database_path)


def _unique_in_order(values):
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
