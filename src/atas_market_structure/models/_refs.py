from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstrumentRef(BaseModel):
    """Stable instrument metadata for replay and backtests."""

    symbol: str = Field(..., description="Trading symbol.", examples=["NQH6"])
    root_symbol: str | None = Field(None, description="Root or continuous symbol when known.", examples=["NQ"])
    contract_symbol: str | None = Field(None, description="Resolved contract symbol when known.", examples=["NQH6"])
    venue: str = Field(..., description="Execution or quote venue.", examples=["CME"])
    tick_size: float = Field(..., gt=0, description="Minimum price increment.", examples=[0.25])
    currency: str = Field(..., description="PnL currency.", examples=["USD"])


class SourceRef(BaseModel):
    """Producer metadata for tracing and support."""

    system: str = Field(..., description="Source system name.", examples=["ATAS"])
    instance_id: str = Field(..., description="Producer instance identifier.", examples=["DESKTOP-ATAS-01"])
    chart_instance_id: str | None = Field(
        None,
        description="Chart or indicator-instance identifier used to separate multiple live ATAS charts.",
        examples=["NQM6-7fa31b2c"],
    )
    adapter_version: str = Field(..., description="Source adapter version.", examples=["0.1.0"])
    chart_display_timezone_mode: str | None = Field(
        None,
        description="ATAS chart display timezone mode captured at payload emission.",
        examples=["exchange", "local", "exchange_dst"],
    )
    chart_display_timezone_name: str | None = Field(
        None,
        description="ATAS chart display timezone name or abbreviation captured at payload emission.",
        examples=["America/New_York", "EST5EDT", "UTC"],
    )
    chart_display_utc_offset_minutes: int | None = Field(
        None,
        description="ATAS chart display UTC offset in minutes captured at payload emission.",
        examples=[-300],
    )
    instrument_timezone_value: int | str | None = Field(
        None,
        description="Raw instrument timezone value from ATAS metadata captured at payload emission.",
    )
    instrument_timezone_source: str | None = Field(
        None,
        description="Where the instrument timezone came from, captured at payload emission.",
        examples=["exchange_profile", "symbol_suffix"],
    )
    collector_local_timezone_name: str | None = Field(
        None,
        description="Collector machine local timezone name at payload emission.",
        examples=["America/New_York"],
    )
    collector_local_utc_offset_minutes: int | None = Field(
        None,
        description="Collector machine local UTC offset in minutes at payload emission.",
        examples=[-300],
    )
    timestamp_basis: str | None = Field(
        None,
        description="Primary basis used to normalize timestamps to UTC at payload emission.",
        examples=["exchange_tick_time", "collector_local_time", "chart_display_time"],
    )
    timezone_capture_confidence: str | None = Field(
        None,
        description="Confidence level of the timezone capture at payload emission: high, medium, low, or unknown.",
        examples=["high", "medium", "low", "unknown"],
    )

