from __future__ import annotations

import re
from typing import Any


_IDENTIFIER_UNSAFE_CHARS = (" ", ":", "/", "\\", "\t", "\r", "\n")
_GENERIC_CHART_INSTANCE_IDS = frozenset(
    {
        "chart",
        "panel",
        "container",
    }
)
_TIMEFRAME_ALIASES = {
    "m1": "1m",
    "1min": "1m",
    "1minute": "1m",
    "m5": "5m",
    "5min": "5m",
    "5minute": "5m",
    "m15": "15m",
    "15min": "15m",
    "15minute": "15m",
    "m30": "30m",
    "30min": "30m",
    "30minute": "30m",
    "h1": "1h",
    "60m": "1h",
    "60min": "1h",
    "1hour": "1h",
    "d1": "1d",
    "1day": "1d",
}
_FUTURES_MONTH_CODES = frozenset("FGHJKMNQUVXZ")
_TRAILING_SYMBOL_PUNCTUATION_RE = re.compile(r"[^A-Z0-9]+$")
_CONTINUOUS_SYMBOL_RE = re.compile(r"^(?P<root>[A-Z0-9]{2,})(?P<sequence>\d+)$")
_FUTURES_CONTRACT_RE = re.compile(r"^(?P<root>[A-Z0-9]{2,})(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{1,2})$")


def normalize_identifier(raw: Any) -> str | None:
    if raw is None:
        return None
    candidate = str(raw).strip()
    if not candidate:
        return None
    for unsafe_char in _IDENTIFIER_UNSAFE_CHARS:
        candidate = candidate.replace(unsafe_char, "_")
    return candidate or None


def normalize_symbol(raw: Any) -> str | None:
    if raw is None:
        return None
    candidate = str(raw).strip()
    if not candidate:
        return None
    return candidate.upper()


def strip_symbol_suffix(raw: Any) -> str | None:
    normalized = normalize_symbol(raw)
    if normalized is None:
        return None
    stripped = _TRAILING_SYMBOL_PUNCTUATION_RE.sub("", normalized)
    return stripped or normalized


def derive_root_symbol(raw: Any) -> str | None:
    symbol = strip_symbol_suffix(raw)
    if symbol is None:
        return None

    contract_match = _FUTURES_CONTRACT_RE.fullmatch(symbol)
    if contract_match is not None:
        root = contract_match.group("root")
        if len(root) >= 2:
            return root

    continuous_match = _CONTINUOUS_SYMBOL_RE.fullmatch(symbol)
    if continuous_match is not None:
        root = continuous_match.group("root")
        if len(root) >= 2:
            return root

    if (
        len(symbol) >= 4
        and symbol[-1].isdigit()
        and symbol[-2] in _FUTURES_MONTH_CODES
        and len(symbol[:-2]) >= 2
    ):
        return symbol[:-2]

    return symbol


def normalize_timeframe(raw: Any) -> str | None:
    if raw is None:
        return None
    candidate_raw = getattr(raw, "value", raw)
    candidate = str(candidate_raw).strip().lower().replace(" ", "")
    if not candidate:
        return None
    return _TIMEFRAME_ALIASES.get(candidate, candidate)


def is_generic_chart_instance_id(chart_instance_id: Any) -> bool:
    normalized = normalize_identifier(chart_instance_id)
    if normalized is None:
        return False
    return normalized.lower() in _GENERIC_CHART_INSTANCE_IDS


def build_fallback_chart_instance_id(
    *,
    instrument_symbol: Any = None,
    contract_symbol: Any = None,
    display_timeframe: Any = None,
    venue: Any = None,
    currency: Any = None,
) -> str:
    normalized_contract_symbol = normalize_identifier(
        normalize_symbol(contract_symbol) or normalize_symbol(instrument_symbol)
    )
    normalized_timeframe = normalize_identifier(normalize_timeframe(display_timeframe))
    normalized_venue = normalize_identifier(venue)
    normalized_currency = normalize_identifier(currency)
    return "-".join(
        [
            "chart",
            normalized_contract_symbol or "unknown_symbol",
            normalized_timeframe or "unknown_tf",
            normalized_venue or "unknown_venue",
            normalized_currency or "unknown_ccy",
        ]
    )


def canonical_chart_instance_id(
    chart_instance_id: Any,
    *,
    instrument_symbol: Any = None,
    contract_symbol: Any = None,
    display_timeframe: Any = None,
    venue: Any = None,
    currency: Any = None,
) -> str | None:
    normalized = normalize_identifier(chart_instance_id)
    if normalized is not None and not is_generic_chart_instance_id(normalized):
        return normalized
    return build_fallback_chart_instance_id(
        instrument_symbol=instrument_symbol,
        contract_symbol=contract_symbol,
        display_timeframe=display_timeframe,
        venue=venue,
        currency=currency,
    )


def chart_instance_id_aliases(
    chart_instance_id: Any,
    *,
    instrument_symbol: Any = None,
    contract_symbol: Any = None,
    display_timeframe: Any = None,
    venue: Any = None,
    currency: Any = None,
) -> set[str]:
    aliases: set[str] = set()
    normalized = normalize_identifier(chart_instance_id)
    if normalized is not None:
        aliases.add(normalized)
    canonical = canonical_chart_instance_id(
        chart_instance_id,
        instrument_symbol=instrument_symbol,
        contract_symbol=contract_symbol,
        display_timeframe=display_timeframe,
        venue=venue,
        currency=currency,
    )
    if canonical is not None:
        aliases.add(canonical)
    return aliases


def chart_instance_ids_match(
    requested_chart_instance_id: Any,
    observed_chart_instance_id: Any,
    *,
    instrument_symbol: Any = None,
    contract_symbol: Any = None,
    display_timeframe: Any = None,
    venue: Any = None,
    currency: Any = None,
) -> bool:
    if requested_chart_instance_id is None:
        return True
    requested_aliases = chart_instance_id_aliases(
        requested_chart_instance_id,
        instrument_symbol=instrument_symbol,
        contract_symbol=contract_symbol,
        display_timeframe=display_timeframe,
        venue=venue,
        currency=currency,
    )
    observed_aliases = chart_instance_id_aliases(
        observed_chart_instance_id,
        instrument_symbol=instrument_symbol,
        contract_symbol=contract_symbol,
        display_timeframe=display_timeframe,
        venue=venue,
        currency=currency,
    )
    if not requested_aliases or not observed_aliases:
        return False
    return not requested_aliases.isdisjoint(observed_aliases)
