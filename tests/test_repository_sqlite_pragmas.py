from __future__ import annotations

import logging
from pathlib import Path
import sqlite3

from atas_market_structure.repository import SQLiteAnalysisRepository


class _FakeConnection:
    def __init__(self) -> None:
        self.row_factory = None
        self.executed: list[str] = []

    def execute(self, sql: str):
        self.executed.append(sql)
        if sql in {"PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL"}:
            raise sqlite3.OperationalError("unable to open database file")
        return self


def test_connect_degrades_when_sqlite_pragmas_fail(monkeypatch, caplog, tmp_path: Path) -> None:
    fake_connection = _FakeConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: fake_connection)
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")

    with caplog.at_level(logging.WARNING):
        connection = repository._connect()
        repository._connect()

    assert connection is fake_connection
    assert "PRAGMA busy_timeout=30000" in fake_connection.executed
    assert "PRAGMA journal_mode=WAL" in fake_connection.executed
    assert "PRAGMA synchronous=NORMAL" in fake_connection.executed
    warnings = [record.getMessage() for record in caplog.records]
    assert sum("pragma=journal_mode=WAL" in message for message in warnings) == 1
    assert sum("pragma=synchronous=NORMAL" in message for message in warnings) == 1
