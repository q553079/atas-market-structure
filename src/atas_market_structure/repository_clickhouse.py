from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from time import sleep
from typing import TYPE_CHECKING, Any, Sequence

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._replay import ChartCandle
from atas_market_structure.repository import (
    AnalysisRepository,
    ChartCandleRepository,
    IngestionRepository,
    StoredIngestion,
)

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client
else:
    Client = Any


def _quote_identifier(identifier: str) -> str:
    parts = [part.strip() for part in identifier.split(".") if part.strip()]
    return ".".join(f"`{part}`" for part in parts)


def _quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _to_ch_datetime64_literal(value: datetime) -> str:
    timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_utc(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _normalize_utc(parsed)


def _serialize_json(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _parse_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def _payload_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _payload_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _normalize_utc(value)
    if isinstance(value, str) and value.strip():
        return _parse_datetime(value.strip())
    return None


def _extract_ingestion_metadata(observed_payload: dict[str, Any]) -> dict[str, Any]:
    source = observed_payload.get("source")
    source_dict = source if isinstance(source, dict) else {}
    return {
        "chart_instance_id": _payload_string(source_dict.get("chart_instance_id")),
        "message_id": _payload_string(observed_payload.get("message_id")),
        "message_type": _payload_string(observed_payload.get("message_type")),
        "observed_window_start": _payload_datetime(observed_payload.get("observed_window_start")),
        "observed_window_end": _payload_datetime(observed_payload.get("observed_window_end")),
        "emitted_at": _payload_datetime(observed_payload.get("emitted_at")),
    }


class ClickHouseChartCandleRepository:
    """ClickHouse-backed store for market-data tables used by the replay UI.

    This repository handles both pre-aggregated chart candles and high-volume
    adapter/replay ingestions. Low-frequency collaborative metadata can stay in
    SQLite while market data is cut over to ClickHouse.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        table: str,
        workspace_root: Path,
        ingestions_table: str = "ingestions",
        connect_retries: int = 5,
        retry_delay_seconds: float = 1.5,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._chart_candles_table = table
        self._ingestions_table = ingestions_table
        self._workspace_root = workspace_root
        self._connect_retries = max(1, connect_retries)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._lock = threading.Lock()
        self._client: Client | None = None

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def initialize(self) -> None:
        database_name = _quote_identifier(self._database)
        chart_candles_table_name = _quote_identifier(f"{self._database}.{self._chart_candles_table}")
        ingestions_table_name = _quote_identifier(f"{self._database}.{self._ingestions_table}")
        self._execute(lambda client: client.command(f"CREATE DATABASE IF NOT EXISTS {database_name}"))
        self._execute(
            lambda client: client.command(
                f"""
                CREATE TABLE IF NOT EXISTS {chart_candles_table_name}
                (
                    symbol LowCardinality(String),
                    timeframe LowCardinality(String),
                    started_at DateTime64(3, 'UTC'),
                    ended_at DateTime64(3, 'UTC'),
                    source_started_at DateTime64(3, 'UTC'),
                    open Float64,
                    high Float64,
                    low Float64,
                    close Float64,
                    volume Int64,
                    tick_volume Int64,
                    delta Int64,
                    updated_at DateTime64(3, 'UTC')
                )
                ENGINE = ReplacingMergeTree(updated_at)
                PARTITION BY (symbol, toYYYYMM(started_at))
                ORDER BY (symbol, timeframe, started_at, source_started_at)
                """
            )
        )
        self._execute(
            lambda client: client.command(
                f"""
                CREATE TABLE IF NOT EXISTS {ingestions_table_name}
                (
                    ingestion_id String,
                    ingestion_kind LowCardinality(String),
                    source_snapshot_id String,
                    instrument_symbol LowCardinality(String),
                    chart_instance_id Nullable(String),
                    message_id Nullable(String),
                    message_type Nullable(String),
                    observed_window_start Nullable(DateTime64(3, 'UTC')),
                    observed_window_end Nullable(DateTime64(3, 'UTC')),
                    emitted_at Nullable(DateTime64(3, 'UTC')),
                    observed_payload_json String,
                    stored_at DateTime64(3, 'UTC'),
                    version_at DateTime64(3, 'UTC')
                )
                ENGINE = ReplacingMergeTree(version_at)
                PARTITION BY (ingestion_kind, toYYYYMM(stored_at))
                ORDER BY (ingestion_kind, instrument_symbol, source_snapshot_id, stored_at, ingestion_id)
                """
            )
        )

    # --- Chart candles -------------------------------------------------

    def upsert_chart_candle(self, candle: ChartCandle) -> ChartCandle:
        self.upsert_chart_candles([candle])
        return candle

    def upsert_chart_candles(self, candles: list[ChartCandle]) -> int:
        if not candles:
            return 0

        rows = [
            [
                candle.symbol,
                candle.timeframe.value,
                _normalize_utc(candle.started_at),
                _normalize_utc(candle.ended_at),
                _normalize_utc(candle.source_started_at or candle.started_at),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.tick_volume,
                candle.delta,
                _normalize_utc(candle.updated_at),
            ]
            for candle in candles
        ]
        self._execute(
            lambda client: client.insert(
                f"{self._database}.{self._chart_candles_table}",
                rows,
                column_names=[
                    "symbol",
                    "timeframe",
                    "started_at",
                    "ended_at",
                    "source_started_at",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "tick_volume",
                    "delta",
                    "updated_at",
                ],
            )
        )
        return len(candles)

    def list_chart_candles(
        self,
        symbol: str,
        timeframe: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list[ChartCandle]:
        tf_value = Timeframe(timeframe).value
        query = f"""
        SELECT
            symbol,
            timeframe,
            started_at,
            max(ended_at) AS ended_at_max,
            min(source_started_at) AS source_started_at_min,
            argMin(open, tuple(source_started_at, updated_at)) AS open,
            max(high) AS high,
            min(low) AS low,
            argMax(close, tuple(updated_at, source_started_at)) AS close,
            toInt64(sum(volume)) AS volume,
            toInt64(sum(tick_volume)) AS tick_volume,
            toInt64(sum(delta)) AS delta,
            max(updated_at) AS updated_at_max
        FROM {_quote_identifier(f"{self._database}.{self._chart_candles_table}")} FINAL
        WHERE symbol = {_quote_string(symbol)}
          AND timeframe = {_quote_string(tf_value)}
          AND started_at >= toDateTime64('{_to_ch_datetime64_literal(window_start)}', 3, 'UTC')
          AND started_at <= toDateTime64('{_to_ch_datetime64_literal(window_end)}', 3, 'UTC')
        GROUP BY symbol, timeframe, started_at
        ORDER BY started_at ASC
        LIMIT {int(limit)}
        """
        result = self._execute(lambda client: client.query(query))
        rows = result.result_rows
        return [
            ChartCandle(
                symbol=row[0],
                timeframe=Timeframe(row[1]),
                started_at=_normalize_utc(row[2]),
                ended_at=_normalize_utc(row[3]),
                source_started_at=_normalize_utc(row[4]),
                open=float(row[5]),
                high=float(row[6]),
                low=float(row[7]),
                close=float(row[8]),
                volume=int(row[9]),
                tick_volume=int(row[10]),
                delta=int(row[11]),
                updated_at=_normalize_utc(row[12]),
            )
            for row in rows
        ]

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
        tf_value = Timeframe(timeframe).value
        query = f"""
        SELECT count()
        FROM
        (
            SELECT started_at
            FROM {_quote_identifier(f"{self._database}.{self._chart_candles_table}")} FINAL
            WHERE symbol = {_quote_string(symbol)}
              AND timeframe = {_quote_string(tf_value)}
            GROUP BY started_at
        )
        """
        result = self._execute(lambda client: client.query(query))
        return int(result.result_rows[0][0]) if result.result_rows else 0

    def purge_chart_candles(self, *, symbol: str | None, older_than: datetime) -> int:
        clauses = [f"updated_at < toDateTime64('{_to_ch_datetime64_literal(older_than)}', 3, 'UTC')"]
        if symbol is not None:
            clauses.insert(0, f"symbol = {_quote_string(symbol)}")
        where_sql = " AND ".join(clauses)

        count_query = f"""
        SELECT count()
        FROM {_quote_identifier(f"{self._database}.{self._chart_candles_table}")} FINAL
        WHERE {where_sql}
        """
        result = self._execute(lambda client: client.query(count_query))
        deleted = int(result.result_rows[0][0]) if result.result_rows else 0
        self._execute(
            lambda client: client.command(
                f"ALTER TABLE {_quote_identifier(f'{self._database}.{self._chart_candles_table}')} DELETE WHERE {where_sql}"
            )
        )
        return deleted

    # ─── Pre-aggregated continuous-state queries ─────────────────────────────────

    def list_continuous_state_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        *,
        trade_active_only: bool = True,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated 1m bars from continuous_state_candles materialized view.

        These bars are pre-computed by ClickHouse so queries are sub-100ms regardless
        of the raw message volume (109,412+ rows → ~1440 pre-aggregated rows per symbol).

        Args:
            symbol: instrument symbol (e.g. "NQ")
            timeframe: target timeframe (only MIN_1 through HOUR_4)
            window_start: inclusive start of query window
            window_end: inclusive end of query window
            trade_active_only: if True, only return bars where has_trade = 1
            limit: maximum rows to return

        Returns:
            List of dicts with keys:
                started_at, ended_at, open, high, low, close,
                volume, delta, bid_volume, ask_volume,
                has_trade, has_replenish, has_liquidity, has_drive, has_phr,
                msg_count
        """
        if timeframe not in {Timeframe.MIN_1, Timeframe.MIN_5, Timeframe.MIN_15,
                            Timeframe.MIN_30, Timeframe.HOUR_1, Timeframe.HOUR_4}:
            return []

        tf_seconds = {
            Timeframe.MIN_1: 60, Timeframe.MIN_5: 300, Timeframe.MIN_15: 900,
            Timeframe.MIN_30: 1800, Timeframe.HOUR_1: 3600, Timeframe.HOUR_4: 14400,
        }[timeframe]

        trade_filter = "AND has_trade = 1" if trade_active_only else ""

        query = f"""
        SELECT
            bucket_start,
            toDateTime64(toDateTime(bucket_start + {tf_seconds} - 1), 3, 'UTC') AS ended_at,
            argMin(open_price, bucket_start)           AS open,
            max(high_price)                            AS high,
            min(low_price)                             AS low,
            argMax(close_price, bucket_start)         AS close,
            toInt64(sum(volume))                       AS volume,
            toInt64(sum(net_delta))                    AS delta,
            toInt64(sum(aggressive_buy))              AS bid_volume,
            toInt64(sum(aggressive_sell))              AS ask_volume,
            max(has_trade)                            AS has_trade,
            max(has_replenish)                        AS has_replenish,
            max(has_liquidity)                        AS has_liquidity,
            max(has_drive)                            AS has_drive,
            max(has_phr)                              AS has_phr,
            sum(msg_count)                            AS msg_count
        FROM {_quote_identifier(f"{self._database}.continuous_state_candles")}
        WHERE symbol = {_quote_string(symbol)}
          AND timeframe = '1m'
          AND bucket_start >= toDateTime64('{_to_ch_datetime64_literal(window_start)}', 3, 'UTC')
          AND bucket_start <= toDateTime64('{_to_ch_datetime64_literal(window_end)}', 3, 'UTC')
          {trade_filter}
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        LIMIT {int(limit)}
        """
        result = self._execute(lambda client: client.query(query))
        return [
            {
                "started_at": _normalize_utc(row[0]),
                "ended_at": _normalize_utc(row[1]),
                "open": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "close": float(row[5]),
                "volume": int(row[6]),
                "delta": int(row[7]),
                "bid_volume": int(row[8]),
                "ask_volume": int(row[9]),
                "has_trade": bool(row[10]),
                "has_replenish": bool(row[11]),
                "has_liquidity": bool(row[12]),
                "has_drive": bool(row[13]),
                "has_phr": bool(row[14]),
                "msg_count": int(row[15]),
            }
            for row in result.result_rows
        ]

    def list_continuous_state_events(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
        *,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated replenishment events from continuous_state_events mv.

        Returns dicts with keys: bucket_start, track_id, event_kind, price, side,
        replenishment_count, observed_at.
        """
        query = f"""
        SELECT
            bucket_start,
            track_id,
            event_kind,
            price,
            side,
            replenishment_count,
            observed_at
        FROM {_quote_identifier(f"{self._database}.continuous_state_events")}
        WHERE symbol = {_quote_string(symbol)}
          AND bucket_start >= toDateTime64('{_to_ch_datetime64_literal(window_start)}', 3, 'UTC')
          AND bucket_start <= toDateTime64('{_to_ch_datetime64_literal(window_end)}', 3, 'UTC')
        ORDER BY bucket_start ASC
        LIMIT {int(limit)}
        """
        result = self._execute(lambda client: client.query(query))
        return [
            {
                "bucket_start": _normalize_utc(row[0]),
                "track_id": row[1],
                "event_kind": row[2],
                "price": float(row[3]),
                "side": row[4],
                "replenishment_count": int(row[5]),
                "observed_at": _normalize_utc(row[6]),
            }
            for row in result.result_rows
        ]

    # --- Ingestions ----------------------------------------------------

    def save_ingestions(self, ingestions: list[StoredIngestion]) -> int:
        if not ingestions:
            return 0

        rows: list[list[Any]] = []
        for ingestion in ingestions:
            stored_at_utc = _normalize_utc(ingestion.stored_at)
            metadata = _extract_ingestion_metadata(ingestion.observed_payload)
            rows.append(
                [
                    ingestion.ingestion_id,
                    ingestion.ingestion_kind,
                    ingestion.source_snapshot_id,
                    ingestion.instrument_symbol,
                    metadata["chart_instance_id"],
                    metadata["message_id"],
                    metadata["message_type"],
                    metadata["observed_window_start"],
                    metadata["observed_window_end"],
                    metadata["emitted_at"],
                    _serialize_json(ingestion.observed_payload),
                    stored_at_utc,
                    stored_at_utc,
                ]
            )

        self._insert_ingestions(rows)
        return len(ingestions)

    def save_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, Any],
        stored_at: datetime,
    ) -> StoredIngestion:
        stored_at_utc = _normalize_utc(stored_at)
        self.save_ingestions(
            [
                StoredIngestion(
                    ingestion_id=ingestion_id,
                    ingestion_kind=ingestion_kind,
                    source_snapshot_id=source_snapshot_id,
                    instrument_symbol=instrument_symbol,
                    observed_payload=observed_payload,
                    stored_at=stored_at_utc,
                )
            ]
        )
        return StoredIngestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=observed_payload,
            stored_at=stored_at_utc,
        )

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        query = f"""
        SELECT
            ingestion_id,
            ingestion_kind,
            source_snapshot_id,
            instrument_symbol,
            observed_payload_json,
            stored_at
        FROM {_quote_identifier(f"{self._database}.{self._ingestions_table}")}
        WHERE ingestion_id = {_quote_string(ingestion_id)}
        ORDER BY version_at DESC
        LIMIT 1
        """
        result = self._execute(lambda client: client.query(query))
        if not result.result_rows:
            return None
        return self._ingestion_row_to_model(result.result_rows[0])

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, Any],
    ) -> StoredIngestion | None:
        existing = self.get_ingestion(ingestion_id)
        if existing is None:
            return None

        metadata = _extract_ingestion_metadata(observed_payload)
        self._insert_ingestions(
            [
                [
                    existing.ingestion_id,
                    existing.ingestion_kind,
                    existing.source_snapshot_id,
                    existing.instrument_symbol,
                    metadata["chart_instance_id"],
                    metadata["message_id"],
                    metadata["message_type"],
                    metadata["observed_window_start"],
                    metadata["observed_window_end"],
                    metadata["emitted_at"],
                    _serialize_json(observed_payload),
                    existing.stored_at,
                    datetime.now(tz=UTC),
                ]
            ]
        )
        return self.get_ingestion(ingestion_id)

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
        clauses: list[str] = []
        if ingestion_kind is not None:
            clauses.append(f"ingestion_kind = {_quote_string(ingestion_kind)}")
        if instrument_symbol is not None:
            clauses.append(f"instrument_symbol = {_quote_string(instrument_symbol)}")
        if source_snapshot_id is not None:
            clauses.append(f"source_snapshot_id = {_quote_string(source_snapshot_id)}")
        if stored_at_after is not None:
            clauses.append(
                f"stored_at >= toDateTime64('{_to_ch_datetime64_literal(stored_at_after)}', 3, 'UTC')"
            )
        if stored_at_before is not None:
            clauses.append(
                f"stored_at <= toDateTime64('{_to_ch_datetime64_literal(stored_at_before)}', 3, 'UTC')"
            )

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
        SELECT
            ingestion_id,
            ingestion_kind,
            source_snapshot_id,
            instrument_symbol,
            observed_payload_json,
            stored_at
        FROM {_quote_identifier(f"{self._database}.{self._ingestions_table}")}
        {where_sql}
        ORDER BY stored_at DESC, version_at DESC, ingestion_id DESC
        LIMIT 1 BY ingestion_id
        LIMIT {int(limit)}
        """
        result = self._execute(lambda client: client.query(query))
        return [self._ingestion_row_to_model(row) for row in result.result_rows]

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        if not ingestion_kinds:
            return 0

        where_parts = [
            f"ingestion_kind IN ({', '.join(_quote_string(item) for item in ingestion_kinds)})",
            f"stored_at < toDateTime64('{_to_ch_datetime64_literal(cutoff)}', 3, 'UTC')",
        ]
        if instrument_symbol is not None:
            where_parts.append(f"instrument_symbol = {_quote_string(instrument_symbol)}")
        where_sql = " AND ".join(where_parts)

        count_query = f"""
        SELECT count()
        FROM
        (
            SELECT ingestion_id
            FROM {_quote_identifier(f"{self._database}.{self._ingestions_table}")}
            WHERE {where_sql}
            GROUP BY ingestion_id
        )
        """
        result = self._execute(lambda client: client.query(count_query))
        deleted = int(result.result_rows[0][0]) if result.result_rows else 0
        self._execute(
            lambda client: client.command(
                f"ALTER TABLE {_quote_identifier(f'{self._database}.{self._ingestions_table}')} DELETE WHERE {where_sql}"
            )
        )
        return deleted

    def _insert_ingestions(self, rows: list[list[Any]]) -> None:
        self._execute(
            lambda client: client.insert(
                f"{self._database}.{self._ingestions_table}",
                rows,
                column_names=[
                    "ingestion_id",
                    "ingestion_kind",
                    "source_snapshot_id",
                    "instrument_symbol",
                    "chart_instance_id",
                    "message_id",
                    "message_type",
                    "observed_window_start",
                    "observed_window_end",
                    "emitted_at",
                    "observed_payload_json",
                    "stored_at",
                    "version_at",
                ],
            )
        )

    @staticmethod
    def _ingestion_row_to_model(row: Sequence[Any]) -> StoredIngestion:
        return StoredIngestion(
            ingestion_id=str(row[0]),
            ingestion_kind=str(row[1]),
            source_snapshot_id=str(row[2]),
            instrument_symbol=str(row[3]),
            observed_payload=_parse_json(str(row[4])),
            stored_at=_normalize_utc(row[5]),
        )

    def _ensure_client(self) -> Client:
        if self._client is None:
            try:
                import clickhouse_connect
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "clickhouse-connect is required when ClickHouse market-data backends are enabled."
                ) from exc

            self._client = self._connect_with_retry(clickhouse_connect)
        return self._client

    def _connect_with_retry(self, clickhouse_connect_module: Any) -> Client:
        last_error: Exception | None = None
        for attempt in range(1, self._connect_retries + 1):
            try:
                client = clickhouse_connect_module.get_client(
                    host=self._host,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                    database=self._database,
                )
                client.query("SELECT 1")
                return client
            except Exception as exc:
                last_error = exc
                if attempt == self._connect_retries:
                    break
                sleep(self._retry_delay_seconds * attempt)

        raise RuntimeError(
            f"Unable to connect to ClickHouse {self._host}:{self._port}/{self._database} after retries."
        ) from last_error

    def _execute(self, operation):
        with self._lock:
            client = self._ensure_client()
            try:
                return operation(client)
            except Exception:
                try:
                    client.close()
                finally:
                    self._client = None
                client = self._ensure_client()
                return operation(client)


class HybridAnalysisRepository:
    """Combine SQLite metadata with ClickHouse market data behind one repository."""

    def __init__(
        self,
        *,
        metadata_repository: AnalysisRepository,
        chart_candle_repository: ChartCandleRepository,
        ingestion_repository: IngestionRepository | None = None,
    ) -> None:
        self._metadata_repository = metadata_repository
        self._chart_candle_repository = chart_candle_repository
        self._ingestion_repository = ingestion_repository or metadata_repository
        self._database_path = getattr(metadata_repository, "_database_path", None)

    @property
    def workspace_root(self) -> Path:
        return self._metadata_repository.workspace_root

    def initialize(self) -> None:
        self._metadata_repository.initialize()
        initialized_ids = {id(self._metadata_repository)}
        for repository in (self._chart_candle_repository, self._ingestion_repository):
            if id(repository) in initialized_ids:
                continue
            repository.initialize()
            initialized_ids.add(id(repository))

    def upsert_chart_candle(self, candle: ChartCandle) -> ChartCandle:
        return self._chart_candle_repository.upsert_chart_candle(candle)

    def upsert_chart_candles(self, candles: list[ChartCandle]) -> int:
        return self._chart_candle_repository.upsert_chart_candles(candles)

    def list_chart_candles(
        self,
        symbol: str,
        timeframe: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list[ChartCandle]:
        return self._chart_candle_repository.list_chart_candles(
            symbol=symbol,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
        return self._chart_candle_repository.count_chart_candles(symbol, timeframe)

    def purge_chart_candles(self, *, symbol: str | None, older_than: datetime) -> int:
        return self._chart_candle_repository.purge_chart_candles(symbol=symbol, older_than=older_than)

    def save_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, Any],
        stored_at: datetime,
    ) -> StoredIngestion:
        return self._ingestion_repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=observed_payload,
            stored_at=stored_at,
        )

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        return self._ingestion_repository.get_ingestion(ingestion_id)

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, Any],
    ) -> StoredIngestion | None:
        return self._ingestion_repository.update_ingestion_observed_payload(
            ingestion_id=ingestion_id,
            observed_payload=observed_payload,
        )

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
        return self._ingestion_repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            limit=limit,
            stored_at_after=stored_at_after,
            stored_at_before=stored_at_before,
        )

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        return self._ingestion_repository.purge_ingestions(
            ingestion_kinds=ingestion_kinds,
            instrument_symbol=instrument_symbol,
            cutoff=cutoff,
        )

    def list_continuous_state_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        *,
        trade_active_only: bool = True,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated continuous-state bars from ClickHouse materialized view.

        Falls back gracefully to an empty list if the materialized view does not exist yet.
        """
        repo = self._chart_candle_repository
        if hasattr(repo, "list_continuous_state_bars"):
            return repo.list_continuous_state_bars(
                symbol=symbol,
                timeframe=timeframe,
                window_start=window_start,
                window_end=window_end,
                trade_active_only=trade_active_only,
                limit=limit,
            )
        return []

    def list_continuous_state_events(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
        *,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """Query pre-aggregated continuous-state events from ClickHouse materialized view."""
        repo = self._chart_candle_repository
        if hasattr(repo, "list_continuous_state_events"):
            return repo.list_continuous_state_events(
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                limit=limit,
            )
        return []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._metadata_repository, name)
