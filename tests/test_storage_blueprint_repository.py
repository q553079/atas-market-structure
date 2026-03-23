from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.storage_models import (
    ObservationTable,
    StoredAnchorInteraction,
    StoredBeliefStateSnapshot,
    StoredFeatureSlice,
    StoredIngestionRunLogRecord,
    StoredMemoryAnchor,
    StoredMemoryAnchorVersion,
    StoredObservationRecord,
    StoredRegimePosterior,
)


def test_observation_adapter_payload_dedupes_and_filters_by_market_time(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    first_time = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    second_time = first_time + timedelta(minutes=1)
    first_record = StoredObservationRecord(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        observation_id="obs-adapter-1",
        instrument_symbol="NQ",
        market_time=first_time,
        session_date=first_time.date().isoformat(),
        ingested_at=first_time,
        schema_version="1.0.0",
        source_ingestion_id="ing-1",
        source_request_id="msg-1",
        dedup_key="msg-1",
        payload_hash="hash-1",
        observation_payload={"message_type": "continuous_state", "last_price": 21510.25},
    )
    duplicate = StoredObservationRecord(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        observation_id="obs-adapter-duplicate-ignored",
        instrument_symbol="NQ",
        market_time=first_time,
        session_date=first_time.date().isoformat(),
        ingested_at=first_time,
        schema_version="1.0.0",
        source_ingestion_id="ing-1b",
        source_request_id="msg-1",
        dedup_key="msg-1",
        payload_hash="hash-1",
        observation_payload={"message_type": "continuous_state", "last_price": 21510.25},
    )
    second_record = StoredObservationRecord(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        observation_id="obs-adapter-2",
        instrument_symbol="NQ",
        market_time=second_time,
        session_date=second_time.date().isoformat(),
        ingested_at=second_time,
        schema_version="1.0.0",
        source_ingestion_id="ing-2",
        source_request_id="msg-2",
        dedup_key="msg-2",
        payload_hash="hash-2",
        observation_payload={"message_type": "continuous_state", "last_price": 21514.5},
    )

    first_saved = repository.save_observation_adapter_payload(first_record)
    duplicate_saved = repository.save_observation_adapter_payload(duplicate)
    repository.save_observation_adapter_payload(second_record)

    assert duplicate_saved.observation_id == first_saved.observation_id

    recent = repository.list_observation_records(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        instrument_symbol="NQ",
        market_time_after=second_time,
        limit=10,
    )
    all_rows = repository.list_observation_records(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        instrument_symbol="NQ",
        limit=10,
    )

    assert len(recent) == 1
    assert recent[0].observation_id == "obs-adapter-2"
    assert [item.observation_id for item in all_rows] == ["obs-adapter-2", "obs-adapter-1"]


def test_versioned_memory_anchor_keeps_current_state_and_history(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    t0 = datetime(2026, 3, 23, 9, 31, tzinfo=UTC)
    repository.save_memory_anchor_version(
        StoredMemoryAnchorVersion(
            anchor_version_id="ancv-1",
            anchor_id="anc-1",
            instrument_symbol="NQ",
            market_time=t0,
            ingested_at=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            freshness="fresh",
            anchor_payload={"reference_price": 21520.0, "role": "balance_center"},
        ),
    )
    repository.upsert_memory_anchor(
        StoredMemoryAnchor(
            anchor_id="anc-1",
            instrument_symbol="NQ",
            anchor_type="balance_center",
            status="active",
            freshness="fresh",
            current_version_id="ancv-1",
            reference_price=21520.0,
            reference_time=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            anchor_payload={"reference_price": 21520.0, "role": "balance_center"},
            updated_at=t0,
        ),
    )

    t1 = t0 + timedelta(minutes=5)
    repository.save_memory_anchor_version(
        StoredMemoryAnchorVersion(
            anchor_version_id="ancv-2",
            anchor_id="anc-1",
            instrument_symbol="NQ",
            market_time=t1,
            ingested_at=t1,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            freshness="aging",
            anchor_payload={"reference_price": 21524.0, "role": "balance_center"},
        ),
    )
    repository.upsert_memory_anchor(
        StoredMemoryAnchor(
            anchor_id="anc-1",
            instrument_symbol="NQ",
            anchor_type="balance_center",
            status="active",
            freshness="aging",
            current_version_id="ancv-2",
            reference_price=21524.0,
            reference_time=t1,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            anchor_payload={"reference_price": 21524.0, "role": "balance_center"},
            updated_at=t1,
        ),
    )

    current = repository.list_memory_anchors(instrument_symbol="NQ", limit=10)
    history = repository.list_memory_anchor_versions(anchor_id="anc-1", limit=10)

    assert len(current) == 1
    assert current[0].current_version_id == "ancv-2"
    assert [item.anchor_version_id for item in history] == ["ancv-2", "ancv-1"]


def test_clear_derived_storage_for_rebuild_preserves_observations(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    t0 = datetime(2026, 3, 23, 9, 32, tzinfo=UTC)
    repository.save_observation_record(
        StoredObservationRecord(
            table_name=ObservationTable.TRADE_CLUSTER,
            observation_id="obs-trade-1",
            instrument_symbol="NQ",
            market_time=t0,
            session_date=t0.date().isoformat(),
            ingested_at=t0,
            schema_version="1.0.0",
            source_ingestion_id="ing-trade-1",
            source_request_id="evt-1",
            dedup_key=None,
            payload_hash=None,
            observation_payload={"event_type": "liquidity_sweep"},
        ),
    )
    repository.save_feature_slice(
        StoredFeatureSlice(
            feature_slice_id="fs-1",
            instrument_symbol="NQ",
            market_time=t0,
            session_date=t0.date().isoformat(),
            ingested_at=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            source_observation_table=ObservationTable.TRADE_CLUSTER.value,
            source_observation_id="obs-trade-1",
            slice_kind="window_1m",
            window_start=t0 - timedelta(minutes=1),
            window_end=t0,
            data_status={"freshness": "fresh"},
            feature_payload={"efficiency": 0.8},
        ),
    )
    repository.save_regime_posterior(
        StoredRegimePosterior(
            posterior_id="rp-1",
            instrument_symbol="NQ",
            market_time=t0,
            session_date=t0.date().isoformat(),
            ingested_at=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            feature_slice_id="fs-1",
            posterior_payload={"balance_mean_reversion": 0.62},
        ),
    )
    repository.save_belief_state_snapshot(
        StoredBeliefStateSnapshot(
            belief_state_id="bs-1",
            instrument_symbol="NQ",
            market_time=t0,
            session_date=t0.date().isoformat(),
            ingested_at=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            recognition_mode="normal",
            data_status={"freshness": "fresh"},
            belief_payload={"regime_probs": {"balance_mean_reversion": 0.62}},
        ),
    )
    repository.save_anchor_interaction(
        StoredAnchorInteraction(
            anchor_interaction_id="ai-1",
            anchor_id="anc-1",
            instrument_symbol="NQ",
            market_time=t0,
            session_date=t0.date().isoformat(),
            ingested_at=t0,
            schema_version="1.0.0",
            profile_version="profile-v1",
            engine_version="build-v1",
            interaction_kind="retest",
            source_observation_table=ObservationTable.TRADE_CLUSTER.value,
            source_observation_id="obs-trade-1",
            interaction_payload={"distance_ticks": 3},
        ),
    )

    rebuild_log = repository.clear_derived_storage_for_rebuild(
        instrument_symbol="NQ",
        reason="test_clear",
        triggered_by="pytest",
    )

    assert rebuild_log.status == "cleared"
    assert repository.list_feature_slices(instrument_symbol="NQ", limit=10) == []
    assert repository.list_regime_posteriors(instrument_symbol="NQ", limit=10) == []
    assert repository.list_belief_state_snapshots(instrument_symbol="NQ", limit=10) == []
    assert repository.list_anchor_interactions(anchor_id="anc-1", limit=10) == []

    remaining_observations = repository.list_observation_records(
        table_name=ObservationTable.TRADE_CLUSTER,
        instrument_symbol="NQ",
        limit=10,
    )
    rebuild_logs = repository.list_rebuild_run_logs(instrument_symbol="NQ", limit=10)

    assert len(remaining_observations) == 1
    assert len(rebuild_logs) == 1
    assert rebuild_logs[0].detail["cleared_counts"]["feature_slice"] == 1


def test_legacy_save_ingestion_mirrors_into_blueprint_observation_tables(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    stored_at = datetime(2026, 3, 23, 9, 33, tzinfo=UTC)
    payload = {
        "schema_version": "1.0.0",
        "message_id": "hist-1",
        "message_type": "history_bars",
        "observed_window_end": "2026-03-23T09:31:59Z",
        "bars": [
            {
                "started_at": "2026-03-23T09:30:00Z",
                "ended_at": "2026-03-23T09:30:59Z",
                "open": 21500.0,
                "high": 21502.0,
                "low": 21499.0,
                "close": 21501.5,
                "volume": 10,
            },
            {
                "started_at": "2026-03-23T09:31:00Z",
                "ended_at": "2026-03-23T09:31:59Z",
                "open": 21501.5,
                "high": 21504.0,
                "low": 21501.0,
                "close": 21503.25,
                "volume": 12,
            },
        ],
    }

    repository.save_ingestion(
        ingestion_id="ing-hist-1",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-1",
        instrument_symbol="NQ",
        observed_payload=payload,
        stored_at=stored_at,
    )

    adapter_payload_rows = repository.list_observation_records(
        table_name=ObservationTable.ADAPTER_PAYLOAD,
        instrument_symbol="NQ",
        limit=10,
    )
    bar_rows = repository.list_observation_records(
        table_name=ObservationTable.BAR,
        instrument_symbol="NQ",
        limit=10,
    )

    assert len(adapter_payload_rows) == 1
    assert adapter_payload_rows[0].source_ingestion_id == "ing-hist-1"
    assert len(bar_rows) == 2
    assert bar_rows[0].observation_payload["close"] == 21503.25


def test_legacy_profile_and_run_log_writes_are_mirrored_to_blueprint_tables(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    t0 = datetime(2026, 3, 23, 9, 34, tzinfo=UTC)
    repository.save_instrument_profile(
        instrument_symbol="NQ",
        profile_version="profile-v2",
        schema_version="1.0.0",
        ontology_version="ontology-v1",
        is_active=True,
        profile_payload={"thresholds": {"continuation": 0.62}},
        created_at=t0,
    )
    repository.save_recognizer_build(
        engine_version="build-v2",
        schema_version="1.0.0",
        ontology_version="ontology-v1",
        is_active=True,
        status="active",
        build_payload={"notes": ["storage-blueprint-test"]},
        created_at=t0,
    )
    repository.save_ingestion_run_log(
        run_id="run-1",
        endpoint="/api/v1/ingest/adapter-payload",
        ingestion_kind="adapter_payload",
        instrument_symbol="NQ",
        request_id="msg-9",
        dedup_key="msg-9",
        payload_hash="hash-9",
        outcome="accepted",
        http_status=201,
        ingestion_id="ing-9",
        dead_letter_id=None,
        detail={"downstream_status": "completed"},
        started_at=t0,
        completed_at=t0 + timedelta(seconds=2),
    )

    profile_rows = repository.list_instrument_profile_versions(instrument_symbol="NQ", limit=10)
    build_rows = repository.list_recognizer_build_versions(limit=10)
    run_rows = repository.list_ingestion_run_log_records(instrument_symbol="NQ", limit=10)

    assert profile_rows[0].profile_version == "profile-v2"
    assert build_rows[0].engine_version == "build-v2"
    assert run_rows[0].run_id == "run-1"


def test_market_structure_mirror_dedupes_exact_duplicates_but_keeps_distinct_same_time_facts(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    stored_at = datetime(2026, 3, 23, 9, 35, tzinfo=UTC)
    payload = {
        "schema_version": "1.0.0",
        "snapshot_id": "bridge-ms-1",
        "observed_at": "2026-03-23T09:35:00Z",
        "decision_layers": {
            "execution_context": [
                {
                    "swing_points": [
                        {"kind": "low", "price": 100.0, "formed_at": "2026-03-23T09:34:00Z"},
                        {"kind": "high", "price": 110.0, "formed_at": "2026-03-23T09:34:00Z"},
                    ],
                    "orderflow_signals": [
                        {
                            "signal_type": "absorption",
                            "side": "sell",
                            "observed_at": "2026-03-23T09:34:30Z",
                            "price": 109.5,
                        },
                    ],
                },
                {
                    "swing_points": [
                        {"kind": "high", "price": 110.0, "formed_at": "2026-03-23T09:34:00Z"},
                    ],
                    "orderflow_signals": [
                        {
                            "signal_type": "absorption",
                            "side": "sell",
                            "observed_at": "2026-03-23T09:34:30Z",
                            "price": 109.5,
                        },
                    ],
                },
            ],
        },
    }

    repository.save_ingestion(
        ingestion_id="ing-ms-dedupe-1",
        ingestion_kind="market_structure",
        source_snapshot_id="bridge-ms-1",
        instrument_symbol="NQ",
        observed_payload=payload,
        stored_at=stored_at,
    )

    swing_rows = repository.list_observation_records(
        table_name=ObservationTable.SWING_EVENT,
        instrument_symbol="NQ",
        limit=10,
    )
    absorption_rows = repository.list_observation_records(
        table_name=ObservationTable.ABSORPTION_EVENT,
        instrument_symbol="NQ",
        limit=10,
    )

    assert len(swing_rows) == 2
    assert {row.observation_payload["kind"] for row in swing_rows} == {"low", "high"}
    assert len(absorption_rows) == 1


def test_event_snapshot_mirror_dedupes_repeated_absorption_signals(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    stored_at = datetime(2026, 3, 23, 9, 36, tzinfo=UTC)
    payload = {
        "schema_version": "1.0.0",
        "event_snapshot_id": "bridge-evt-1",
        "observed_at": "2026-03-23T09:36:00Z",
        "trigger_event": {
            "event_type": "initiative_relaunch",
            "observed_at": "2026-03-23T09:35:55Z",
        },
        "decision_layers": {
            "execution_context": [
                {
                    "orderflow_signals": [
                        {
                            "signal_type": "absorption",
                            "side": "sell",
                            "observed_at": "2026-03-23T09:35:58Z",
                            "price": 110.25,
                        },
                    ],
                },
                {
                    "orderflow_signals": [
                        {
                            "signal_type": "absorption",
                            "side": "sell",
                            "observed_at": "2026-03-23T09:35:58Z",
                            "price": 110.25,
                        },
                    ],
                },
            ],
        },
    }

    repository.save_ingestion(
        ingestion_id="ing-evt-dedupe-1",
        ingestion_kind="event_snapshot",
        source_snapshot_id="bridge-evt-1",
        instrument_symbol="NQ",
        observed_payload=payload,
        stored_at=stored_at,
    )

    cluster_rows = repository.list_observation_records(
        table_name=ObservationTable.TRADE_CLUSTER,
        instrument_symbol="NQ",
        limit=10,
    )
    absorption_rows = repository.list_observation_records(
        table_name=ObservationTable.ABSORPTION_EVENT,
        instrument_symbol="NQ",
        limit=10,
    )

    assert len(cluster_rows) == 1
    assert len(absorption_rows) == 1


def test_clear_derived_storage_for_rebuild_rejects_window_scoped_clear_in_v1(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    t0 = datetime(2026, 3, 23, 9, 37, tzinfo=UTC)

    try:
        repository.clear_derived_storage_for_rebuild(
            instrument_symbol="NQ",
            reason="windowed_clear_not_supported",
            triggered_by="pytest",
            window_start=t0 - timedelta(minutes=5),
            window_end=t0,
        )
    except ValueError as exc:
        assert "not implemented in V1" in str(exc)
    else:
        raise AssertionError("Expected clear_derived_storage_for_rebuild to reject window-scoped clears in V1")
