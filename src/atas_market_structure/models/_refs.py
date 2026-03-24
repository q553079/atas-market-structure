from __future__ import annotations

from datetime import datetime
import logging

from pydantic import BaseModel, Field, model_validator

from atas_market_structure.tick_size_defaults import default_tick_size_for_symbol


LOGGER = logging.getLogger(__name__)


class InstrumentRef(BaseModel):
    """Stable instrument metadata for replay and backtests."""

    symbol: str = Field(..., description="Trading symbol.", examples=["NQH6"])
    root_symbol: str | None = Field(None, description="Root or continuous symbol when known.", examples=["NQ"])
    contract_symbol: str | None = Field(None, description="Resolved contract symbol when known.", examples=["NQH6"])
    venue: str = Field(..., description="Execution or quote venue.", examples=["CME"])
    tick_size: float = Field(
        ...,
        ge=0,
        description="Minimum price increment. A value of 0 means the collector could not resolve tick size and the payload is degraded.",
        examples=[0.25],
    )
    currency: str = Field(..., description="PnL currency.", examples=["USD"])

    @model_validator(mode="before")
    @classmethod
    def apply_tick_size_fallback(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        raw_tick_size = value.get("tick_size")
        try:
            numeric_tick_size = float(raw_tick_size)
        except (TypeError, ValueError):
            numeric_tick_size = None
        if numeric_tick_size is not None and numeric_tick_size > 0:
            return value
        fallback_symbol = (
            value.get("root_symbol")
            or value.get("contract_symbol")
            or value.get("symbol")
            or ""
        )
        fallback_tick_size = default_tick_size_for_symbol(str(fallback_symbol))
        LOGGER.warning(
            "InstrumentRef tick_size fallback applied: symbol=%s raw_tick_size=%s fallback_tick_size=%s",
            fallback_symbol,
            raw_tick_size,
            fallback_tick_size,
        )
        normalized = dict(value)
        normalized["tick_size"] = fallback_tick_size
        return normalized


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

