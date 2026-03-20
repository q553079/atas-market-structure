from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstrumentRef(BaseModel):
    """Stable instrument metadata for replay and backtests."""

    symbol: str = Field(..., description="Trading symbol.", examples=["NQH6"])
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

