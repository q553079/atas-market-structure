from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from atas_market_structure.models import Timeframe
from atas_market_structure.repository import AnalysisRepository


class WorkbenchPipelineMonitorService:
    """Read-only monitoring view for ATAS raw-bar ingress and K-line aggregation."""

    _DEFAULT_DAYS = 10
    _DEFAULT_FLOW_WINDOW_MINUTES = 15
    _DEFAULT_INSTANT_WINDOW_SECONDS = 8
    _DAY_1M_CAPACITY = 1440
    _TIMEFRAME_CAPACITY = {
        Timeframe.MIN_1.value: 1440,
        Timeframe.MIN_5.value: 288,
        Timeframe.MIN_15.value: 96,
    }
    _MONITORED_TIMEFRAMES = (
        Timeframe.MIN_1.value,
        Timeframe.MIN_5.value,
        Timeframe.MIN_15.value,
    )

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def get_monitor_snapshot(
        self,
        *,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        days: int = _DEFAULT_DAYS,
        flow_window_minutes: int = _DEFAULT_FLOW_WINDOW_MINUTES,
        contract_limit: int = 120,
    ) -> dict[str, Any]:
        days = max(1, min(int(days), 60))
        flow_window_minutes = max(5, min(int(flow_window_minutes), 180))
        contracts = self._repository.list_atas_pipeline_contracts(limit=max(contract_limit, 50))
        chart_backend = self._resolve_chart_backend()
        storage_locations = self._build_storage_locations(chart_backend)
        if not contracts:
            return {
                "generated_at": self._iso(datetime.now(tz=UTC)),
                "contracts": [],
                "selected_contract": None,
                "chart_backend": chart_backend,
                "storage_locations": storage_locations,
                "recent_pools": self._build_recent_pools(
                    flow_window_minutes=flow_window_minutes,
                    raw_recent=0,
                    chart_recent={timeframe: 0 for timeframe in self._MONITORED_TIMEFRAMES},
                    chart_backend=chart_backend,
                ),
                "instant_flow": self._build_instant_flow(
                    instant_window_seconds=self._DEFAULT_INSTANT_WINDOW_SECONDS,
                    raw_count=0,
                    chart_counts={timeframe: 0 for timeframe in self._MONITORED_TIMEFRAMES},
                    chart_backend=chart_backend,
                ),
                "write_pressure": self._build_write_pressure(
                    flow_window_minutes=flow_window_minutes,
                    raw_recent=0,
                    chart_recent={timeframe: 0 for timeframe in self._MONITORED_TIMEFRAMES},
                ),
                "message": "No ATAS raw bars have been mirrored yet.",
            }

        selected = self._select_contract(contracts, contract_symbol=contract_symbol, root_symbol=root_symbol)
        root_symbol = (selected.root_symbol or selected.contract_symbol).upper()
        now = datetime.now(tz=UTC)
        flow_start = now - timedelta(minutes=flow_window_minutes)
        instant_window_seconds = self._DEFAULT_INSTANT_WINDOW_SECONDS
        instant_start = now - timedelta(seconds=instant_window_seconds)

        raw_daily_rows = self._repository.list_atas_raw_bar_daily_counts(
            contract_symbol=selected.contract_symbol,
            timeframe=Timeframe.MIN_1.value,
            limit=days,
        )
        chart_daily_rows = self._repository.list_chart_candle_daily_counts(
            symbol=root_symbol,
            timeframes=self._MONITORED_TIMEFRAMES,
            limit=days * len(self._MONITORED_TIMEFRAMES),
        )
        raw_daily_map = {(row.bar_date, row.timeframe): row for row in raw_daily_rows}
        chart_daily_map = {(row.bar_date, row.timeframe): row for row in chart_daily_rows}

        seen_dates: list[str] = []
        for row in raw_daily_rows:
            if row.bar_date not in seen_dates:
                seen_dates.append(row.bar_date)
        for row in chart_daily_rows:
            if row.bar_date not in seen_dates:
                seen_dates.append(row.bar_date)
        seen_dates = sorted(seen_dates, reverse=True)[:days]

        daily_rows = [
            self._build_daily_row(
                bar_date=bar_date,
                raw_daily_map=raw_daily_map,
                chart_daily_map=chart_daily_map,
            )
            for bar_date in seen_dates
        ]

        raw_recent = self._repository.count_atas_chart_bars_raw_updated_since(
            contract_symbol=selected.contract_symbol,
            timeframe=Timeframe.MIN_1.value,
            updated_since=flow_start,
        )
        chart_recent = {
            timeframe: self._repository.count_chart_candles_updated_since(
                symbol=root_symbol,
                timeframe=timeframe,
                updated_since=flow_start,
            )
            for timeframe in self._MONITORED_TIMEFRAMES
        }
        instant_raw = self._repository.count_atas_chart_bars_raw_updated_since(
            contract_symbol=selected.contract_symbol,
            timeframe=Timeframe.MIN_1.value,
            updated_since=instant_start,
        )
        instant_chart = {
            timeframe: self._repository.count_chart_candles_updated_since(
                symbol=root_symbol,
                timeframe=timeframe,
                updated_since=instant_start,
            )
            for timeframe in self._MONITORED_TIMEFRAMES
        }

        total_raw_1m = self._repository.count_atas_chart_bars_raw(
            contract_symbol=selected.contract_symbol,
            timeframe=Timeframe.MIN_1.value,
        )
        total_chart = {
            timeframe: self._repository.count_chart_candles(root_symbol, timeframe)
            for timeframe in self._MONITORED_TIMEFRAMES
        }

        today_key = now.date().isoformat()
        today_row = next((row for row in daily_rows if row["bar_date"] == today_key), None)
        recent_pools = self._build_recent_pools(
            flow_window_minutes=flow_window_minutes,
            raw_recent=raw_recent,
            chart_recent=chart_recent,
            chart_backend=chart_backend,
        )

        return {
            "generated_at": self._iso(now),
            "contracts": [
                {
                    "contract_symbol": item.contract_symbol,
                    "root_symbol": item.root_symbol,
                    "latest_raw_started_at": self._iso(item.latest_raw_started_at),
                    "latest_raw_updated_at": self._iso(item.latest_raw_updated_at),
                    "total_raw_1m_count": item.total_raw_1m_count,
                    "today_raw_1m_count": item.today_raw_1m_count,
                }
                for item in contracts
            ],
            "selected_contract": {
                "contract_symbol": selected.contract_symbol,
                "root_symbol": root_symbol,
                "latest_raw_started_at": self._iso(selected.latest_raw_started_at),
                "latest_raw_updated_at": self._iso(selected.latest_raw_updated_at),
                "shared_chart_pool": root_symbol != selected.contract_symbol,
            },
            "chart_backend": chart_backend,
            "storage_locations": storage_locations,
            "flow_window_minutes": flow_window_minutes,
            "totals": {
                "sqlite_raw_1m": total_raw_1m,
                "chart_1m": total_chart[Timeframe.MIN_1.value],
                "chart_5m": total_chart[Timeframe.MIN_5.value],
                "chart_15m": total_chart[Timeframe.MIN_15.value],
                "clickhouse_1m": total_chart[Timeframe.MIN_1.value],
                "clickhouse_5m": total_chart[Timeframe.MIN_5.value],
                "clickhouse_15m": total_chart[Timeframe.MIN_15.value],
            },
            "today": today_row
            or {
                "bar_date": today_key,
                "quota_1m": self._DAY_1M_CAPACITY,
                "sqlite_raw_1m": 0,
                "chart_1m": 0,
                "chart_5m": 0,
                "chart_15m": 0,
                "clickhouse_1m": 0,
                "clickhouse_5m": 0,
                "clickhouse_15m": 0,
                "raw_fill_percent": 0,
                "chart_fill_percent": {"1m": 0, "5m": 0, "15m": 0},
                "write_gap_1m": 0,
                "latest_updated_at": None,
            },
            "daily_rows": daily_rows,
            "recent_pools": recent_pools,
            "instant_flow": self._build_instant_flow(
                instant_window_seconds=instant_window_seconds,
                raw_count=instant_raw,
                chart_counts=instant_chart,
                chart_backend=chart_backend,
            ),
            "write_pressure": self._build_write_pressure(
                flow_window_minutes=flow_window_minutes,
                raw_recent=raw_recent,
                chart_recent=chart_recent,
            ),
        }

    def _select_contract(self, contracts, *, contract_symbol: str | None, root_symbol: str | None):
        normalized_contract = (contract_symbol or "").strip().upper()
        if normalized_contract:
            for item in contracts:
                if item.contract_symbol.upper() == normalized_contract:
                    return item
        normalized_root = (root_symbol or "").strip().upper()
        if normalized_root:
            for item in contracts:
                if item.root_symbol.upper() == normalized_root:
                    return item
        return contracts[0]

    def _build_daily_row(
        self,
        *,
        bar_date: str,
        raw_daily_map: dict[tuple[str, str], Any],
        chart_daily_map: dict[tuple[str, str], Any],
    ) -> dict[str, Any]:
        raw_row = raw_daily_map.get((bar_date, Timeframe.MIN_1.value))
        raw_count = int(raw_row.candle_count) if raw_row is not None else 0
        chart_counts = {
            timeframe: int(chart_daily_map.get((bar_date, timeframe)).candle_count)
            if chart_daily_map.get((bar_date, timeframe)) is not None
            else 0
            for timeframe in self._MONITORED_TIMEFRAMES
        }
        latest_candidates = [
            raw_row.latest_updated_at if raw_row is not None else None,
            *[
                chart_daily_map.get((bar_date, timeframe)).latest_updated_at
                if chart_daily_map.get((bar_date, timeframe)) is not None
                else None
                for timeframe in self._MONITORED_TIMEFRAMES
            ],
        ]
        latest_updated_at = max((item for item in latest_candidates if item is not None), default=None)
        return {
            "bar_date": bar_date,
            "quota_1m": self._DAY_1M_CAPACITY,
            "sqlite_raw_1m": raw_count,
            "chart_1m": chart_counts[Timeframe.MIN_1.value],
            "chart_5m": chart_counts[Timeframe.MIN_5.value],
            "chart_15m": chart_counts[Timeframe.MIN_15.value],
            "clickhouse_1m": chart_counts[Timeframe.MIN_1.value],
            "clickhouse_5m": chart_counts[Timeframe.MIN_5.value],
            "clickhouse_15m": chart_counts[Timeframe.MIN_15.value],
            "raw_fill_percent": self._percent(raw_count, self._DAY_1M_CAPACITY),
            "chart_fill_percent": {
                timeframe: self._percent(chart_counts[timeframe], self._TIMEFRAME_CAPACITY[timeframe])
                for timeframe in self._MONITORED_TIMEFRAMES
            },
            "write_gap_1m": max(raw_count - chart_counts[Timeframe.MIN_1.value], 0),
            "latest_updated_at": self._iso(latest_updated_at),
        }

    def _build_recent_pools(
        self,
        *,
        flow_window_minutes: int,
        raw_recent: int,
        chart_recent: dict[str, int],
        chart_backend: dict[str, str],
    ) -> list[dict[str, Any]]:
        pools = [
            self._build_pool(
                key="sqlite_raw",
                label="SQLite 暂存池",
                count=raw_recent,
                capacity=max(flow_window_minutes, 1),
                timeframe="1m",
            ),
            self._build_pool(
                key="clickhouse_1m",
                label="主图 1m",
                count=chart_recent[Timeframe.MIN_1.value],
                capacity=max(flow_window_minutes, 1),
                timeframe="1m",
            ),
            self._build_pool(
                key="clickhouse_5m",
                label="主图 5m",
                count=chart_recent[Timeframe.MIN_5.value],
                capacity=max(ceil(flow_window_minutes / 5), 1),
                timeframe="5m",
            ),
            self._build_pool(
                key="clickhouse_15m",
                label="主图 15m",
                count=chart_recent[Timeframe.MIN_15.value],
                capacity=max(ceil(flow_window_minutes / 15), 1),
                timeframe="15m",
            ),
        ]
        return pools

    def _build_pool(self, *, key: str, label: str, count: int, capacity: int, timeframe: str) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "timeframe": timeframe,
            "count": int(count),
            "capacity": int(capacity),
            "fill_percent": self._percent(count, capacity),
        }

    def _build_write_pressure(
        self,
        *,
        flow_window_minutes: int,
        raw_recent: int,
        chart_recent: dict[str, int],
    ) -> dict[str, Any]:
        raw_wpm = raw_recent / max(flow_window_minutes, 1)
        ck_1m_wpm = chart_recent[Timeframe.MIN_1.value] / max(flow_window_minutes, 1)
        total_recent = raw_recent + sum(chart_recent.values())
        status = "quiet"
        if raw_wpm >= 2.5 or total_recent >= flow_window_minutes * 4:
            status = "hot"
        elif raw_wpm >= 1.0 or total_recent >= flow_window_minutes * 2:
            status = "busy"
        return {
            "status": status,
            "raw_writes_per_minute": round(raw_wpm, 2),
            "chart_1m_writes_per_minute": round(ck_1m_wpm, 2),
            "recent_total_writes": int(total_recent),
            "note": {
                "quiet": "最近写入很少，ATAS 可能空闲、休市或已停止。",
                "busy": "最近写入正常偏高，说明正在持续入库。",
                "hot": "最近写入明显偏高，常见于补历史、切合约或异常重发。",
            }[status],
        }

    def _build_instant_flow(
        self,
        *,
        instant_window_seconds: int,
        raw_count: int,
        chart_counts: dict[str, int],
        chart_backend: dict[str, str],
    ) -> dict[str, Any]:
        window_seconds = max(1, int(instant_window_seconds))
        chart_prefix = chart_backend.get("engine_short", "Chart")

        def build_leg(label: str, count: int) -> dict[str, Any]:
            per_second = count / window_seconds
            return {
                "label": label,
                "count": int(count),
                "per_second": round(per_second, 3),
                "per_minute": round(per_second * 60, 2),
                "active": bool(count),
            }

        chart_1m = build_leg(f"SQLite -> {chart_prefix} 1m", chart_counts.get(Timeframe.MIN_1.value, 0))
        chart_5m = build_leg(f"SQLite -> {chart_prefix} 5m", chart_counts.get(Timeframe.MIN_5.value, 0))
        chart_15m = build_leg(f"SQLite -> {chart_prefix} 15m", chart_counts.get(Timeframe.MIN_15.value, 0))
        downstream = {
            Timeframe.MIN_1.value: chart_1m,
            Timeframe.MIN_5.value: chart_5m,
            Timeframe.MIN_15.value: chart_15m,
        }
        return {
            "window_seconds": window_seconds,
            "atas_to_sqlite": build_leg("ATAS -> SQLite", raw_count),
            "sqlite_to_chart": downstream,
            "sqlite_to_clickhouse": downstream,
            "downstream_total_count": int(
                chart_1m["count"] + chart_5m["count"] + chart_15m["count"]
            ),
            "total_writes": int(raw_count + chart_1m["count"] + chart_5m["count"] + chart_15m["count"]),
        }

    def _resolve_chart_backend(self) -> dict[str, str]:
        metadata_repository = getattr(self._repository, "_metadata_repository", self._repository)
        chart_repository = getattr(self._repository, "_chart_candle_repository", self._repository)
        sqlite_path = getattr(metadata_repository, "_database_path", None)
        clickhouse_database = getattr(chart_repository, "_database", None)
        clickhouse_chart_table = getattr(chart_repository, "_chart_candles_table", None)
        chart_available = getattr(self._repository, "_chart_candle_repository_available", None)

        if chart_available is False:
            return {
                "mode": "sqlite_fallback",
                "engine": "SQLite",
                "engine_short": "SQLite",
                "storage_key": "clickhouse_chart",
                "location": f"{sqlite_path} :: chart_candles" if sqlite_path else "SQLite :: chart_candles",
                "purpose": "主图 K 线读取与聚合查询（当前已回退到 SQLite）",
            }

        if clickhouse_database and clickhouse_chart_table:
            return {
                "mode": "clickhouse",
                "engine": "ClickHouse",
                "engine_short": "CK",
                "storage_key": "clickhouse_chart",
                "location": f"{clickhouse_database}.{clickhouse_chart_table}",
                "purpose": "主图 K 线读取与聚合查询",
            }

        return {
            "mode": "sqlite_authoritative",
            "engine": "SQLite",
            "engine_short": "SQLite",
            "storage_key": "clickhouse_chart",
            "location": f"{sqlite_path} :: chart_candles" if sqlite_path else "SQLite :: chart_candles",
            "purpose": "主图 K 线读取与聚合查询",
        }

    def _build_storage_locations(self, chart_backend: dict[str, str]) -> list[dict[str, str]]:
        metadata_repository = getattr(self._repository, "_metadata_repository", self._repository)
        sqlite_path = getattr(metadata_repository, "_database_path", None)
        return [
            {
                "key": "sqlite_raw",
                "label": "SQLite 原始镜像",
                "engine": "SQLite",
                "location": f"{sqlite_path} :: atas_chart_bars_raw" if sqlite_path else "SQLite :: atas_chart_bars_raw",
                "purpose": "ATAS 原始 bars 暂存与镜像",
            },
            {
                "key": "sqlite_metadata",
                "label": "SQLite 元数据",
                "engine": "SQLite",
                "location": f"{sqlite_path} :: ingestions" if sqlite_path else "SQLite :: ingestions",
                "purpose": "ingestion 元数据、重放状态、事件与缓存",
            },
            {
                "key": "clickhouse_chart",
                "label": f"{chart_backend.get('engine', 'Chart')} K 线池",
                "engine": chart_backend.get("engine", "Chart"),
                "location": chart_backend.get("location", "Chart :: chart_candles"),
                "purpose": chart_backend.get("purpose", "主图 K 线读取与聚合查询"),
            },
        ]

    @staticmethod
    def _percent(value: int, capacity: int) -> int:
        if capacity <= 0:
            return 0
        return max(0, min(100, round((value / capacity) * 100)))

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
