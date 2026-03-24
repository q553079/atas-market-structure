from __future__ import annotations


DEFAULT_TICK_SIZES: dict[str, float] = {
    "ES": 0.25,
    "NQ": 0.25,
    "GC": 0.1,
    "CL": 0.01,
}


def default_tick_size_for_symbol(instrument_symbol: str) -> float:
    symbol = (instrument_symbol or "").strip().upper()
    return DEFAULT_TICK_SIZES.get(symbol, 0.25)
