from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from atas_market_structure.golden_cases import GoldenReplayCase, iter_cases, materialize_case_ingestions
from atas_market_structure.profile_services import build_instrument_profile_v1, default_tick_size_for_symbol
from atas_market_structure.rebuild_runner import RAW_REPLAY_INGESTION_KINDS, ReplayRebuildRunner
from atas_market_structure.repository import SQLiteAnalysisRepository, StoredIngestion
from atas_market_structure.repository_clickhouse import HybridAnalysisRepository


ROOT = Path(__file__).resolve().parents[1]
CASES_BY_ID = {case.case_id: case for case in iter_cases(ROOT / "samples" / "golden_cases")}


def test_repository_rebuild_replays_filtered_instrument_and_session(tmp_path: Path) -> None:
    source_database = _seed_repository(
        tmp_path=tmp_path,
        cases=[
            CASES_BY_ID["momentum_nq_normal_01"],
            CASES_BY_ID["balance_es_normal_01"],
        ],
    )
    runner = ReplayRebuildRunner()

    report = runner.run_repository_rebuild(
        source_database_path=source_database,
        output_database_path=tmp_path / "rebuild" / "nq-rebuild.db",
        instrument_symbol="NQ",
        ai_available=True,
        session_date="2026-03-23",
    )

    assert runner.validate_case_report(case=CASES_BY_ID["momentum_nq_normal_01"], report=report) == []
    assert report.instrument_symbol == "NQ"


def test_repository_rebuild_is_semantically_consistent_across_two_runs(tmp_path: Path) -> None:
    source_database = _seed_repository(
        tmp_path=tmp_path,
        cases=[CASES_BY_ID["failure_missed_transition_04"]],
    )
    runner = ReplayRebuildRunner()

    first = runner.run_repository_rebuild(
        source_database_path=source_database,
        output_database_path=tmp_path / "rebuild" / "first.db",
        instrument_symbol="ES",
        ai_available=True,
        session_date="2026-03-23",
    )
    second = runner.run_repository_rebuild(
        source_database_path=source_database,
        output_database_path=tmp_path / "rebuild" / "second.db",
        instrument_symbol="ES",
        ai_available=True,
        session_date="2026-03-23",
    )

    assert _semantic_signature(first) == _semantic_signature(second)


def test_repository_rebuild_keeps_ai_out_of_critical_path(tmp_path: Path) -> None:
    source_database = _seed_repository(
        tmp_path=tmp_path,
        cases=[CASES_BY_ID["degraded_no_ai_momentum_02"]],
    )
    runner = ReplayRebuildRunner()

    report = runner.run_repository_rebuild(
        source_database_path=source_database,
        output_database_path=tmp_path / "rebuild" / "no-ai.db",
        instrument_symbol="NQ",
        ai_available=False,
        session_date="2026-03-23",
    )

    assert runner.validate_case_report(case=CASES_BY_ID["degraded_no_ai_momentum_02"], report=report) == []
    assert report.ai_in_critical_path is False


def test_repository_rebuild_can_read_raw_ingestions_from_hybrid_clickhouse_source(tmp_path: Path) -> None:
    metadata_database = tmp_path / "metadata" / "metadata.db"
    metadata_repository = SQLiteAnalysisRepository(database_path=metadata_database)
    metadata_repository.initialize()
    _seed_active_versions(repository=metadata_repository, instrument_symbol="NQ")

    fake_clickhouse_ingestions = _FakeReplayIngestionRepository(
        rows=[
            StoredIngestion(
                ingestion_id=ingestion.ingestion_id,
                ingestion_kind=ingestion.ingestion_kind,
                source_snapshot_id=ingestion.source_snapshot_id,
                instrument_symbol=ingestion.instrument_symbol,
                observed_payload=ingestion.observed_payload,
                stored_at=ingestion.stored_at,
            )
            for ingestion in materialize_case_ingestions(CASES_BY_ID["momentum_nq_normal_01"])
        ]
    )
    source_repository = HybridAnalysisRepository(
        metadata_repository=metadata_repository,
        chart_candle_repository=metadata_repository,
        ingestion_repository=fake_clickhouse_ingestions,
    )
    runner = ReplayRebuildRunner()

    report = runner.run_repository_rebuild(
        source_repository=source_repository,
        source_label="clickhouse://127.0.0.1:8123/market_data.ingestions",
        output_database_path=tmp_path / "rebuild" / "nq-clickhouse.db",
        instrument_symbol="NQ",
        ai_available=True,
        session_date="2026-03-23",
        page_size=2,
    )

    assert fake_clickhouse_ingestions.initialized is True
    assert fake_clickhouse_ingestions.paginated_calls == len(RAW_REPLAY_INGESTION_KINDS)
    assert runner.validate_case_report(case=CASES_BY_ID["momentum_nq_normal_01"], report=report) == []
    assert report.source_database == "clickhouse://127.0.0.1:8123/market_data.ingestions"
    assert report.profile_version == "instrument_profile_v1"
    assert report.engine_version == "recognizer_build_v1"


def test_repository_rebuild_requires_exactly_one_source_backend(tmp_path: Path) -> None:
    source_database = _seed_repository(
        tmp_path=tmp_path,
        cases=[CASES_BY_ID["momentum_nq_normal_01"]],
    )
    source_repository = SQLiteAnalysisRepository(database_path=source_database)
    runner = ReplayRebuildRunner()

    try:
        runner.run_repository_rebuild(
            source_database_path=source_database,
            source_repository=source_repository,
            output_database_path=tmp_path / "rebuild" / "ambiguous.db",
            instrument_symbol="NQ",
        )
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("expected ambiguous source configuration to fail")


def _seed_repository(*, tmp_path: Path, cases: list[GoldenReplayCase]) -> Path:
    database_path = tmp_path / "source" / "source.db"
    repository = SQLiteAnalysisRepository(database_path=database_path)
    repository.initialize()
    for case in cases:
        for ingestion in materialize_case_ingestions(case):
            repository.save_ingestion(
                ingestion_id=ingestion.ingestion_id,
                ingestion_kind=ingestion.ingestion_kind,
                source_snapshot_id=ingestion.source_snapshot_id,
                instrument_symbol=ingestion.instrument_symbol,
                observed_payload=ingestion.observed_payload,
                stored_at=ingestion.stored_at,
            )
    return database_path


def _seed_active_versions(*, repository: SQLiteAnalysisRepository, instrument_symbol: str) -> None:
    created_at = datetime(2026, 3, 23, 9, 0, tzinfo=UTC)
    profile = build_instrument_profile_v1(
        instrument_symbol,
        tick_size=default_tick_size_for_symbol(instrument_symbol),
        profile_version="instrument_profile_v1",
        schema_version="instrument_profile_v1",
        ontology_version="master_spec_v2_v1",
        created_at=created_at,
    )
    repository.save_instrument_profile(
        instrument_symbol=profile.instrument_symbol,
        profile_version=profile.profile_version,
        schema_version=profile.schema_version,
        ontology_version=profile.ontology_version,
        is_active=profile.is_active,
        profile_payload=profile.model_dump(mode="json", by_alias=True),
        created_at=profile.created_at,
    )
    repository.save_recognizer_build(
        engine_version="recognizer_build_v1",
        schema_version="recognizer_build_v1",
        ontology_version=profile.ontology_version,
        is_active=True,
        status="active",
        build_payload={
            "schema_version": "recognizer_build_v1",
            "engine_version": "recognizer_build_v1",
            "ontology_version": profile.ontology_version,
        },
        created_at=created_at,
    )


class _FakeReplayIngestionRepository:
    def __init__(self, rows: list[StoredIngestion]) -> None:
        self.initialized = False
        self.rows = list(rows)
        self.paginated_calls = 0

    def initialize(self) -> None:
        self.initialized = True

    def iter_ingestions_paginated(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        source_snapshot_id: str | None = None,
        page_size: int = 1000,
        stored_at_after: datetime | None = None,
        stored_at_before: datetime | None = None,
    ):
        self.paginated_calls += 1
        rows = self.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            limit=10_000,
            stored_at_after=stored_at_after,
            stored_at_before=stored_at_before,
        )
        for index in range(0, len(rows), page_size):
            for row in rows[index : index + page_size]:
                yield row

    def list_ingestions(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        source_snapshot_id: str | None = None,
        limit: int = 100,
        stored_at_after: datetime | None = None,
        stored_at_before: datetime | None = None,
    ) -> list[StoredIngestion]:
        rows = list(self.rows)
        if ingestion_kind is not None:
            rows = [row for row in rows if row.ingestion_kind == ingestion_kind]
        if instrument_symbol is not None:
            rows = [row for row in rows if row.instrument_symbol == instrument_symbol]
        if source_snapshot_id is not None:
            rows = [row for row in rows if row.source_snapshot_id == source_snapshot_id]
        if stored_at_after is not None:
            rows = [row for row in rows if row.stored_at >= stored_at_after]
        if stored_at_before is not None:
            rows = [row for row in rows if row.stored_at <= stored_at_before]
        rows.sort(key=lambda row: (row.stored_at, row.ingestion_kind, row.ingestion_id), reverse=True)
        return rows[:limit]


def _semantic_signature(report) -> tuple[object, ...]:
    return (
        report.instrument_symbol,
        report.replayed_ingestion_count,
        report.belief_count,
        report.episode_count,
        report.evaluation_count,
        report.top_event_kind,
        report.recognition_mode,
        tuple(report.degraded_modes),
        tuple(report.episode_event_kinds),
        tuple(report.episode_resolutions),
        tuple(report.evaluation_failure_modes),
        report.data_freshness,
        report.data_completeness,
        report.profile_version,
        report.engine_version,
    )
