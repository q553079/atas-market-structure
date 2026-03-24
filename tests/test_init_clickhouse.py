from __future__ import annotations

from scripts.init_clickhouse import build_ddl


def test_build_ddl_defaults_to_chart_only_tables() -> None:
    ddls = build_ddl("market_data")
    rendered = "\n".join(ddls)

    assert "market_data.ticks_raw" in rendered
    assert "market_data.chart_candles" in rendered
    assert "market_data.ingestions" not in rendered
    assert "continuous_state_candles" not in rendered
    assert "continuous_state_events" not in rendered


def test_build_ddl_can_include_optional_ingestion_tables() -> None:
    ddls = build_ddl("market_data", include_ingestion_tables=True)
    rendered = "\n".join(ddls)

    assert "market_data.ingestions" in rendered
    assert "continuous_state_candles" in rendered
    assert "continuous_state_events" in rendered
