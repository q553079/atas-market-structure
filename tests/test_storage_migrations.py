from __future__ import annotations

import sqlite3
from pathlib import Path

from atas_market_structure.storage_repository import SQLiteStorageBlueprintRepository


REQUIRED_BLUEPRINT_TABLES = {
    "schema_registry",
    "observation_bar",
    "observation_trade_cluster",
    "observation_depth_event",
    "observation_gap_event",
    "observation_swing_event",
    "observation_absorption_event",
    "observation_adapter_payload",
    "feature_slice",
    "regime_posterior",
    "event_hypothesis_state",
    "belief_state_snapshot",
    "projection_snapshot",
    "memory_anchor",
    "memory_anchor_version",
    "anchor_interaction",
    "event_episode",
    "event_episode_evidence",
    "episode_evaluation",
    "tuning_recommendation",
    "profile_patch_candidate",
    "patch_promotion_history",
    "patch_validation_result",
    "instrument_profile",
    "recognizer_build",
    "ingestion_run_log",
    "rebuild_run_log",
    "dead_letter_payload",
}


def test_storage_migrations_initialize_fresh_database(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    repository = SQLiteStorageBlueprintRepository(database_path=database_path)

    applied = repository.initialize()
    applied_versions = [item.version for item in repository.list_applied_migrations()]

    assert [item.version for item in applied] == ["0001", "0002", "0003", "0004"]
    assert applied_versions == ["0001", "0002", "0003", "0004"]

    with sqlite3.connect(database_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            ).fetchall()
        }

    assert str(journal_mode).lower() == "wal"
    assert REQUIRED_BLUEPRINT_TABLES.issubset(tables)

    registry_entries = repository.list_schema_registry_entries()
    assert any(item.object_name == "belief_state_snapshot" for item in registry_entries)
    assert any(item.object_name == "memory_anchor" for item in registry_entries)


def test_storage_migrations_can_upgrade_from_partial_state(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    repository = SQLiteStorageBlueprintRepository(database_path=database_path)

    first_batch = repository.initialize(target_version="0001")
    second_batch = repository.initialize()
    third_batch = repository.initialize()

    assert [item.version for item in first_batch] == ["0001"]
    assert [item.version for item in second_batch] == ["0002", "0003", "0004"]
    assert third_batch == []
    assert [item.version for item in repository.list_applied_migrations()] == ["0001", "0002", "0003", "0004"]

    registry_entries = repository.list_schema_registry_entries()
    assert any(item.object_name == "dead_letter_payload" for item in registry_entries)
