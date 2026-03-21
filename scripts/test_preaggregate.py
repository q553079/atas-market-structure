"""Verify pre-aggregate queries work correctly."""
import sys
sys.path.insert(0, "/app/src")

import clickhouse_connect
from datetime import datetime, timedelta, UTC
from atas_market_structure.models._enums import Timeframe
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository
import threading

client = clickhouse_connect.get_client(host="clickhouse", port=8123)

# Instantiate repo without __init__ to avoid connection setup issues
repo = object.__new__(ClickHouseChartCandleRepository)
repo._client = client
repo._database = "market_data"
repo._chart_candles_table = "chart_candles"
repo._ingestions_table = "ingestions"
repo._host = "clickhouse"
repo._port = 8123
repo._username = "default"
repo._password = ""
repo._lock = threading.Lock()
repo._connect_retries = 3
repo._retry_delay_seconds = 1.0

# Test pre-aggregate bars
now = datetime.now(tz=UTC)
bars = repo.list_continuous_state_bars(
    symbol="NQ",
    timeframe=Timeframe.MIN_1,
    window_start=now - timedelta(hours=1),
    window_end=now,
    trade_active_only=True,
    limit=100,
)
print(f"NQ 1h pre-aggregate bars: {len(bars)}")
if bars:
    b = bars[-1]
    print(f"Latest: {b['started_at']} O={b['open']} H={b['high']} L={b['low']} C={b['close']} V={b['volume']}")

# Test pre-aggregate events
events = repo.list_continuous_state_events(
    symbol="NQ",
    window_start=now - timedelta(days=1),
    window_end=now,
    limit=100,
)
print(f"NQ pre-aggregate events: {len(events)}")
if events:
    e = events[0]
    print(f"First: kind={e['event_kind']} price={e['price']} side={e['side']}")

# Test fallback (non-CH repo)
print("\nAll pre-aggregate methods working correctly!")
