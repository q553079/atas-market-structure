from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._replay import ChartCandle
from atas_market_structure.repository import SQLiteAnalysisRepository, StoredIngestion
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository, HybridAnalysisRepository
import atas_market_structure.repository_clickhouse as repository_clickhouse_module
from atas_market_structure.server import build_repository
from atas_market_structure.config import AppConfig


def test_sqlite_chart_candle_round_trip_preserves_source_started_at(tmp_path: Path) -> None:
    repo = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repo.initialize()

    started_at = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    source_started_at = started_at + timedelta(seconds=15)
    repo.upsert_chart_candles(
        [
            ChartCandle(
                symbol="NQ",
                timeframe=Timeframe.MIN_1,
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=1),
                source_started_at=source_started_at,
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=10,
                tick_volume=2,
                delta=3,
                updated_at=started_at + timedelta(minutes=1),
            )
        ]
    )

    candles = repo.list_chart_candles("NQ", Timeframe.MIN_1.value, started_at, started_at + timedelta(minutes=1))
    assert len(candles) == 1
    assert candles[0].source_started_at == source_started_at


class _FakeMetadataRepository:
    def __init__(self) -> None:
        self.workspace_root = Path("/tmp/workspace")
        self.initialized = False
        self.marker_called = False

    def initialize(self) -> None:
        self.initialized = True

    def marker(self) -> str:
        self.marker_called = True
        return "metadata"


class _FakeChartCandleRepository:
    def __init__(self) -> None:
        self.initialized = False
        self.upserted: list[ChartCandle] = []
        self.latest_tick_quote: dict[str, object] | None = None

    def initialize(self) -> None:
        self.initialized = True

    def upsert_chart_candle(self, candle: ChartCandle) -> ChartCandle:
        self.upserted.append(candle)
        return candle

    def upsert_chart_candles(self, candles: list[ChartCandle]) -> int:
        self.upserted.extend(candles)
        return len(candles)

    def list_chart_candles(self, symbol: str, timeframe: str, window_start: datetime, window_end: datetime, limit: int = 20000) -> list[ChartCandle]:
        return list(self.upserted)

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
        return len(self.upserted)

    def purge_chart_candles(self, *, symbol: str | None, older_than: datetime) -> int:
        deleted = len(self.upserted)
        self.upserted.clear()
        return deleted

    def get_latest_tick_quote(
        self,
        symbol: str,
        *,
        lookback_seconds: int = 300,
        limit: int = 2000,
    ) -> dict[str, object] | None:
        _ = (symbol, lookback_seconds, limit)
        return self.latest_tick_quote


class _FakeIngestionRepository:
    def __init__(self) -> None:
        self.initialized = False
        self.rows: dict[str, StoredIngestion] = {}
        self.paginated_calls = 0

    def initialize(self) -> None:
        self.initialized = True

    def save_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, object],
        stored_at: datetime,
    ) -> StoredIngestion:
        stored = StoredIngestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=dict(observed_payload),
            stored_at=stored_at,
        )
        self.rows[ingestion_id] = stored
        return stored

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        return self.rows.get(ingestion_id)

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, object],
    ) -> StoredIngestion | None:
        stored = self.rows.get(ingestion_id)
        if stored is None:
            return None
        updated = StoredIngestion(
            ingestion_id=stored.ingestion_id,
            ingestion_kind=stored.ingestion_kind,
            source_snapshot_id=stored.source_snapshot_id,
            instrument_symbol=stored.instrument_symbol,
            observed_payload=dict(observed_payload),
            stored_at=stored.stored_at,
        )
        self.rows[ingestion_id] = updated
        return updated

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
        rows = list(self.rows.values())
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
        rows.sort(key=lambda row: row.stored_at, reverse=True)
        return rows[:limit]

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

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        delete_ids = [
            ingestion_id
            for ingestion_id, row in self.rows.items()
            if row.ingestion_kind in ingestion_kinds
            and row.stored_at < cutoff
            and (instrument_symbol is None or row.instrument_symbol == instrument_symbol)
        ]
        for ingestion_id in delete_ids:
            del self.rows[ingestion_id]
        return len(delete_ids)


def test_hybrid_repository_delegates_chart_candles_to_secondary_store() -> None:
    metadata_repo = _FakeMetadataRepository()
    chart_repo = _FakeChartCandleRepository()
    hybrid_repo = HybridAnalysisRepository(
        metadata_repository=metadata_repo,
        chart_candle_repository=chart_repo,
    )

    started_at = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    candle = ChartCandle(
        symbol="ES",
        timeframe=Timeframe.MIN_1,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=1),
        source_started_at=started_at,
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=4,
        tick_volume=1,
        delta=1,
        updated_at=started_at,
    )

    hybrid_repo.initialize()
    written = hybrid_repo.upsert_chart_candles([candle])

    assert metadata_repo.initialized is True
    assert chart_repo.initialized is True
    assert written == 1
    assert chart_repo.count_chart_candles("ES", Timeframe.MIN_1.value) == 1
    assert hybrid_repo.marker() == "metadata"
    assert metadata_repo.marker_called is True


def test_hybrid_repository_can_delegate_ingestions_to_secondary_store() -> None:
    metadata_repo = _FakeMetadataRepository()
    chart_repo = _FakeChartCandleRepository()
    ingestion_repo = _FakeIngestionRepository()
    hybrid_repo = HybridAnalysisRepository(
        metadata_repository=metadata_repo,
        chart_candle_repository=chart_repo,
        ingestion_repository=ingestion_repo,
    )

    stored_at = datetime(2026, 3, 22, 10, 1, tzinfo=UTC)
    hybrid_repo.initialize()
    saved = hybrid_repo.save_ingestion(
        ingestion_id="ing-1",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id="msg-1",
        instrument_symbol="NQ",
        observed_payload={"message_id": "msg-1"},
        stored_at=stored_at,
    )

    listed = hybrid_repo.list_ingestions(ingestion_kind="adapter_continuous_state", instrument_symbol="NQ", limit=10)
    updated = hybrid_repo.update_ingestion_observed_payload(
        ingestion_id="ing-1",
        observed_payload={"message_id": "msg-1", "status": "updated"},
    )

    assert metadata_repo.initialized is True
    assert chart_repo.initialized is True
    assert ingestion_repo.initialized is True
    assert saved.ingestion_id == "ing-1"
    assert len(listed) == 1
    assert listed[0].observed_payload["message_id"] == "msg-1"
    assert updated is not None
    assert updated.observed_payload["status"] == "updated"


def test_hybrid_repository_can_delegate_paginated_ingestion_reads() -> None:
    metadata_repo = _FakeMetadataRepository()
    chart_repo = _FakeChartCandleRepository()
    ingestion_repo = _FakeIngestionRepository()
    hybrid_repo = HybridAnalysisRepository(
        metadata_repository=metadata_repo,
        chart_candle_repository=chart_repo,
        ingestion_repository=ingestion_repo,
    )
    stored_at = datetime(2026, 3, 22, 10, 1, tzinfo=UTC)
    ingestion_repo.save_ingestion(
        ingestion_id="ing-1",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id="msg-1",
        instrument_symbol="NQ",
        observed_payload={"message_id": "msg-1"},
        stored_at=stored_at,
    )

    rows = list(
        hybrid_repo.iter_ingestions_paginated(
            ingestion_kind="adapter_continuous_state",
            instrument_symbol="NQ",
            page_size=1,
        )
    )

    assert len(rows) == 1
    assert rows[0].ingestion_id == "ing-1"
    assert ingestion_repo.paginated_calls == 1


def test_hybrid_repository_can_delegate_tick_quote_lookup() -> None:
    metadata_repo = _FakeMetadataRepository()
    chart_repo = _FakeChartCandleRepository()
    chart_repo.latest_tick_quote = {
        "observed_at": datetime(2026, 3, 22, 10, 3, tzinfo=UTC),
        "last_price": 24843.25,
        "best_bid": 24843.0,
        "best_ask": 24843.25,
        "tick_count": 12,
    }
    hybrid_repo = HybridAnalysisRepository(
        metadata_repository=metadata_repo,
        chart_candle_repository=chart_repo,
    )

    quote = hybrid_repo.get_latest_tick_quote("NQ")

    assert quote is not None
    assert quote["last_price"] == 24843.25
    assert quote["best_bid"] == 24843.0
    assert quote["best_ask"] == 24843.25


def test_build_repository_defaults_to_clickhouse_for_chart_candles_and_sqlite_for_ingestions(tmp_path: Path) -> None:
    repository = build_repository(
        AppConfig(
            database_path=tmp_path / "data" / "market_structure.db",
            storage_mode="clickhouse",
            clickhouse_host="127.0.0.1",
            clickhouse_port=8123,
            clickhouse_user="default",
            clickhouse_password="",
            clickhouse_database="market_data",
            clickhouse_chart_candles_table="chart_candles",
            clickhouse_ingestions_table="ingestions",
        )
    )

    assert isinstance(repository, HybridAnalysisRepository)
    assert isinstance(repository._metadata_repository, SQLiteAnalysisRepository)
    assert repository._chart_candle_repository is not repository._metadata_repository
    assert repository._ingestion_repository is repository._metadata_repository


def test_build_repository_forwards_clickhouse_retry_settings(tmp_path: Path) -> None:
    repository = build_repository(
        AppConfig(
            database_path=tmp_path / "data" / "market_structure.db",
            storage_mode="clickhouse",
            clickhouse_host="127.0.0.1",
            clickhouse_port=8123,
            clickhouse_user="default",
            clickhouse_password="",
            clickhouse_database="market_data",
            clickhouse_chart_candles_table="chart_candles",
            clickhouse_ingestions_table="ingestions",
            clickhouse_connect_retries=7,
            clickhouse_retry_delay_seconds=2.5,
        )
    )

    assert isinstance(repository, HybridAnalysisRepository)
    assert repository._ingestion_repository is repository._metadata_repository
    assert repository._chart_candle_repository._connect_retries == 7
    assert repository._chart_candle_repository._retry_delay_seconds == 2.5
    assert repository._chart_candle_repository._manage_ingestion_tables is False


def test_build_repository_can_opt_in_clickhouse_ingestions(tmp_path: Path) -> None:
    repository = build_repository(
        AppConfig(
            database_path=tmp_path / "data" / "market_structure.db",
            storage_mode="clickhouse",
            clickhouse_host="127.0.0.1",
            clickhouse_port=8123,
            clickhouse_user="default",
            clickhouse_password="",
            clickhouse_database="market_data",
            clickhouse_chart_candles_table="chart_candles",
            clickhouse_ingestions_table="ingestions",
            clickhouse_enable_ingestions=True,
        )
    )

    assert isinstance(repository, HybridAnalysisRepository)
    assert repository._chart_candle_repository is repository._ingestion_repository
    assert repository._chart_candle_repository._manage_ingestion_tables is True


def test_clickhouse_repository_can_skip_ingestion_table_initialization(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []

    class _FakeClient:
        def command(self, sql: str) -> None:
            commands.append(sql)

    repository = ClickHouseChartCandleRepository(
        host="127.0.0.1",
        port=8123,
        username="default",
        password="",
        database="market_data",
        table="chart_candles",
        workspace_root=tmp_path,
        manage_ingestion_tables=False,
    )
    monkeypatch.setattr(repository, "_execute", lambda operation: operation(_FakeClient()))

    repository.initialize()

    rendered = "\n".join(commands)
    assert "CREATE DATABASE IF NOT EXISTS" in rendered
    assert "chart_candles" in rendered
    assert "CREATE TABLE IF NOT EXISTS `market_data`.`ingestions`" not in rendered


def test_clickhouse_repository_retries_initial_connection(monkeypatch, tmp_path: Path) -> None:
    attempts: list[dict[str, object]] = []
    sleep_calls: list[float] = []

    class _FakeClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query(self, sql: str) -> None:
            self.queries.append(sql)

        def close(self) -> None:
            return None

    fake_client = _FakeClient()

    def _fake_get_client(**kwargs):
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise OSError("connection refused")
        return fake_client

    monkeypatch.setitem(sys.modules, "clickhouse_connect", SimpleNamespace(get_client=_fake_get_client))
    monkeypatch.setattr(repository_clickhouse_module, "sleep", lambda delay: sleep_calls.append(delay))

    repository = ClickHouseChartCandleRepository(
        host="127.0.0.1",
        port=8123,
        username="default",
        password="",
        database="market_data",
        table="chart_candles",
        workspace_root=tmp_path,
        connect_retries=3,
        retry_delay_seconds=0.25,
    )

    client = repository._ensure_client()

    assert client is fake_client
    assert len(attempts) == 3
    assert sleep_calls == [0.25, 0.5]
    assert fake_client.queries == ["SELECT 1"]


def test_clickhouse_repository_list_chart_candles_uses_clickhouse_safe_aggregation(monkeypatch, tmp_path: Path) -> None:
    captured_query: dict[str, str] = {}

    class _FakeClient:
        def query(self, sql: str):
            captured_query["sql"] = sql
            return SimpleNamespace(
                result_rows=[
                    [
                        "GC",
                        Timeframe.MIN_1.value,
                        datetime(2026, 3, 21, 15, 0, tzinfo=UTC),
                        datetime(2026, 3, 21, 15, 1, tzinfo=UTC),
                        datetime(2026, 3, 21, 15, 0, tzinfo=UTC),
                        3010.5,
                        3012.0,
                        3009.75,
                        3011.25,
                        144,
                        12,
                        18,
                        datetime(2026, 3, 21, 15, 1, tzinfo=UTC),
                    ]
                ]
            )

    repository = ClickHouseChartCandleRepository(
        host="127.0.0.1",
        port=8123,
        username="default",
        password="",
        database="market_data",
        table="chart_candles",
        workspace_root=tmp_path,
    )
    monkeypatch.setattr(repository, "_execute", lambda operation: operation(_FakeClient()))

    candles = repository.list_chart_candles(
        symbol="GC",
        timeframe=Timeframe.MIN_1.value,
        window_start=datetime(2026, 3, 21, 15, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 21, 16, 0, tzinfo=UTC),
        limit=500,
    )

    assert len(candles) == 1
    assert candles[0].symbol == "GC"
    assert candles[0].source_started_at == datetime(2026, 3, 21, 15, 0, tzinfo=UTC)
    assert "FINAL" not in captured_query["sql"]
    assert "min(source_started_at) AS source_started_at_min" in captured_query["sql"]
    assert "max(updated_at) AS updated_at_max" in captured_query["sql"]
    assert "argMin(open, tuple(source_started_at, updated_at))" in captured_query["sql"]
    assert "argMax(close, tuple(updated_at, source_started_at))" in captured_query["sql"]


def test_clickhouse_repository_count_chart_candles_counts_distinct_buckets_without_final(
    monkeypatch, tmp_path: Path
) -> None:
    captured_query: dict[str, str] = {}

    class _FakeClient:
        def query(self, sql: str):
            captured_query["sql"] = sql
            return SimpleNamespace(result_rows=[[2]])

    repository = ClickHouseChartCandleRepository(
        host="127.0.0.1",
        port=8123,
        username="default",
        password="",
        database="market_data",
        table="chart_candles",
        workspace_root=tmp_path,
    )
    monkeypatch.setattr(repository, "_execute", lambda operation: operation(_FakeClient()))

    count = repository.count_chart_candles("GC", Timeframe.MIN_1.value)

    assert count == 2
    assert "FINAL" not in captured_query["sql"]
    assert "GROUP BY started_at" in captured_query["sql"]


def test_clickhouse_repository_get_latest_tick_quote_reads_ticks_raw(monkeypatch, tmp_path: Path) -> None:
    captured_query: dict[str, str] = {}

    class _FakeClient:
        def query(self, sql: str):
            captured_query["sql"] = sql
            return SimpleNamespace(
                result_rows=[
                    [datetime(2026, 3, 22, 10, 0, 2, tzinfo=UTC), 24843.5, "Ask"],
                    [datetime(2026, 3, 22, 10, 0, 1, tzinfo=UTC), 24843.25, "Bid"],
                    [datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC), 24843.0, "Bid"],
                ]
            )

    repository = ClickHouseChartCandleRepository(
        host="127.0.0.1",
        port=8123,
        username="default",
        password="",
        database="market_data",
        table="chart_candles",
        workspace_root=tmp_path,
    )
    monkeypatch.setattr(repository, "_execute", lambda operation: operation(_FakeClient()))

    quote = repository.get_latest_tick_quote("NQ", lookback_seconds=120, limit=100)

    assert quote is not None
    assert quote["observed_at"] == datetime(2026, 3, 22, 10, 0, 2, tzinfo=UTC)
    assert quote["last_price"] == 24843.5
    assert quote["best_bid"] == 24843.25
    assert quote["best_ask"] == 24843.5
    assert quote["tick_count"] == 3
    assert "ticks_raw" in captured_query["sql"]
    assert "ORDER BY event_time DESC, ts_unix_ms DESC" in captured_query["sql"]
