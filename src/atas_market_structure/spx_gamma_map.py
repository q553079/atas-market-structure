from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path

from openai import OpenAI

from atas_market_structure.config import AppConfig


CONTRACT_MULTIPLIER = 100
DEFAULT_CSV_PATTERNS = ("^spx_quotedata*.csv", "*spx*quotedata*.csv", "*quotedata*.csv", "*.csv")


@dataclass(slots=True)
class OptionRow:
    expiration: date
    strike: float
    call_symbol: str
    call_volume: int
    call_iv: float
    call_delta: float
    call_gamma: float
    call_open_interest: int
    put_symbol: str
    put_volume: int
    put_iv: float
    put_delta: float
    put_gamma: float
    put_open_interest: int


@dataclass(slots=True)
class StrikeMetrics:
    strike: float
    call_proxy: float = 0.0
    put_proxy: float = 0.0
    net_proxy: float = 0.0
    call_gex_1pct: float = 0.0
    put_gex_1pct: float = 0.0
    net_gex_1pct: float = 0.0
    call_volume: int = 0
    put_volume: int = 0
    call_open_interest: int = 0
    put_open_interest: int = 0
    expirations: int = 0


@dataclass(slots=True)
class Level:
    strike: float
    es_equivalent: float | None
    score: float
    label: str
    call_open_interest: int
    put_open_interest: int
    call_volume: int
    put_volume: int


@dataclass(slots=True)
class AccelerationZone:
    direction: str
    trigger_strike: float
    trigger_es: float | None
    target_strike: float
    target_es: float | None
    label: str
    score: float


@dataclass(slots=True)
class ExpirationMetrics:
    expiration: str
    dte: int
    rows: int
    call_gex_1pct: float
    put_gex_1pct: float
    net_gex_1pct: float
    atm_strike: float | None
    atm_call_iv: float | None
    atm_put_iv: float | None
    atm_iv: float | None
    call_25d_iv: float | None
    put_25d_iv: float | None
    put_call_iv_ratio_25d: float | None
    risk_reversal_25d: float | None
    dominant_call_oi_strike: float | None
    dominant_put_oi_strike: float | None


@dataclass(slots=True)
class WallMetrics:
    label: str
    strike: float
    es_equivalent: float | None
    open_interest: int
    gex_1pct: float
    distance_from_spot: float


@dataclass(slots=True)
class StructuralRegime:
    macro_gamma_regime: str
    local_gamma_regime: str
    local_net_gex_1pct: float
    local_strike_span_low: float
    local_strike_span_high: float
    dominant_call_wall: WallMetrics | None
    dominant_put_wall: WallMetrics | None
    term_structure_label: str
    front_expiry: str | None
    front_atm_iv: float | None
    next_expiry: str | None
    next_atm_iv: float | None
    front_put_call_iv_ratio_25d: float | None
    front_risk_reversal_25d: float | None
    gap_chop_score: int
    gap_chop_bias: str
    gap_chop_reasons: list[str]


@dataclass(slots=True)
class TrackingDelta:
    previous_quote_time: str | None
    previous_source_file: str | None
    net_gex_change_1pct: float | None
    zero_gamma_shift: float | None
    local_net_gex_change_1pct: float | None
    dominant_put_wall_shift: float | None
    dominant_call_wall_shift: float | None
    gap_chop_score_change: int | None
    front_put_call_iv_ratio_25d_change: float | None
    interpretation: list[str]


@dataclass(slots=True)
class GammaMapSummary:
    source_file: str
    quote_time: str | None
    spx_spot: float
    es_price: float | None
    max_dte: int
    min_open_interest: int
    strike_step: float
    included_expirations: list[str]
    regime: str
    zero_gamma_proxy: float | None
    zero_gamma_proxy_es: float | None
    total_call_gex_1pct: float
    total_put_gex_1pct: float
    total_net_gex_1pct: float
    resistance_levels: list[Level]
    support_levels: list[Level]
    upside_acceleration_zones: list[AccelerationZone]
    downside_acceleration_zones: list[AccelerationZone]
    strike_metrics: list[StrikeMetrics]
    expiration_metrics: list[ExpirationMetrics] = field(default_factory=list)
    structural_regime: StructuralRegime | None = None
    tracking_delta: TrackingDelta | None = None

    def to_jsonable(self) -> dict:
        return {
            "source_file": self.source_file,
            "quote_time": self.quote_time,
            "spx_spot": self.spx_spot,
            "es_price": self.es_price,
            "max_dte": self.max_dte,
            "min_open_interest": self.min_open_interest,
            "strike_step": self.strike_step,
            "included_expirations": self.included_expirations,
            "regime": self.regime,
            "zero_gamma_proxy": self.zero_gamma_proxy,
            "zero_gamma_proxy_es": self.zero_gamma_proxy_es,
            "total_call_gex_1pct": self.total_call_gex_1pct,
            "total_put_gex_1pct": self.total_put_gex_1pct,
            "total_net_gex_1pct": self.total_net_gex_1pct,
            "resistance_levels": [asdict(level) for level in self.resistance_levels],
            "support_levels": [asdict(level) for level in self.support_levels],
            "upside_acceleration_zones": [asdict(zone) for zone in self.upside_acceleration_zones],
            "downside_acceleration_zones": [asdict(zone) for zone in self.downside_acceleration_zones],
            "strike_metrics": [asdict(item) for item in self.strike_metrics],
            "expiration_metrics": [asdict(item) for item in self.expiration_metrics],
            "structural_regime": asdict(self.structural_regime) if self.structural_regime else None,
            "tracking_delta": asdict(self.tracking_delta) if self.tracking_delta else None,
        }


@dataclass(slots=True)
class GeneratedArtifacts:
    summary: GammaMapSummary
    svg_path: Path
    json_path: Path
    report_path: Path
    history_json_path: Path | None = None
    ai_report_path: Path | None = None


@dataclass(slots=True)
class AiAnalysisResult:
    provider: str
    model: str
    content: str


def parse_float(value: str) -> float:
    value = value.strip().replace(",", "")
    if not value:
        return 0.0
    return float(value)


def parse_int(value: str) -> int:
    value = value.strip().replace(",", "")
    if not value:
        return 0
    return int(float(value))


def parse_quote_date(line: str) -> datetime | None:
    match = re.search(r"Date:\s*(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2}):(\d{2})", line)
    if not match:
        return None
    year, month, day, hour, minute = map(int, match.groups())
    return datetime(year, month, day, hour, minute)


def parse_spot(line: str) -> float | None:
    match = re.search(r"Last:\s*([0-9.,]+)", line)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_expiration(value: str) -> date:
    return datetime.strptime(value.strip(), "%a %b %d %Y").date()


def load_options_csv(csv_path: Path) -> tuple[float | None, datetime | None, list[OptionRow]]:
    rows: list[OptionRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        non_empty_rows = [row for row in reader if row and any(cell.strip() for cell in row)]
        if len(non_empty_rows) < 4:
            return None, None, []

        first_line = non_empty_rows[0]
        second_line = non_empty_rows[1]
        data_rows = non_empty_rows[3:]

        spot = parse_spot(",".join(first_line))
        quote_dt = parse_quote_date(",".join(second_line))

        for raw in data_rows:
            if len(raw) < 22 or raw[0].strip() == "Expiration Date":
                continue
            rows.append(
                OptionRow(
                    expiration=parse_expiration(raw[0]),
                    strike=parse_float(raw[11]),
                    call_symbol=raw[1].strip(),
                    call_volume=parse_int(raw[6]),
                    call_iv=parse_float(raw[7]),
                    call_delta=parse_float(raw[8]),
                    call_gamma=parse_float(raw[9]),
                    call_open_interest=parse_int(raw[10]),
                    put_symbol=raw[12].strip(),
                    put_volume=parse_int(raw[17]),
                    put_iv=parse_float(raw[18]),
                    put_delta=parse_float(raw[19]),
                    put_gamma=parse_float(raw[20]),
                    put_open_interest=parse_int(raw[21]),
                )
            )

    return spot, quote_dt, rows


def load_powershell_env_file(env_ps1_path: Path) -> None:
    if not env_ps1_path.exists():
        return
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    target_keys = [
        "ATAS_MS_AI_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ATAS_MS_AI_MODEL",
        "ATAS_MS_AI_TIMEOUT_SECONDS",
    ]
    if powershell:
        env_ps1_literal = str(env_ps1_path).replace("'", "''")
        script = "\n".join(
            [
                f". '{env_ps1_literal}'",
                "$result = @{}",
                *[
                    f"$result['{key}'] = [Environment]::GetEnvironmentVariable('{key}', 'Process')"
                    for key in target_keys
                ],
                "$result | ConvertTo-Json -Compress",
            ]
        )
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            try:
                payload = json.loads(completed.stdout.strip())
                for key, value in payload.items():
                    if value:
                        os.environ[str(key)] = str(value)
                return
            except json.JSONDecodeError:
                pass

    assignment_pattern = re.compile(r'^\$env:(?P<key>[A-Za-z0-9_]+)\s*=\s*"(?P<value>.*)"\s*$')
    for raw_line in env_ps1_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = assignment_pattern.match(line)
        if not match:
            continue
        key = match.group("key")
        value = bytes(match.group("value"), "utf-8").decode("unicode_escape")
        os.environ[key] = value


def discover_latest_options_csv(
    scan_dir: Path,
    *,
    patterns: tuple[str, ...] | list[str] = DEFAULT_CSV_PATTERNS,
    recursive: bool = False,
) -> Path:
    if not scan_dir.exists():
        raise FileNotFoundError(f"Scan directory does not exist: {scan_dir}")

    candidates: dict[Path, float] = {}
    for pattern in patterns:
        iterator = scan_dir.rglob(pattern) if recursive else scan_dir.glob(pattern)
        for path in iterator:
            if not path.is_file() or path.suffix.lower() != ".csv":
                continue
            try:
                candidates[path.resolve()] = path.stat().st_mtime
            except OSError:
                continue

    if not candidates:
        raise FileNotFoundError(f"No CSV files matched under {scan_dir}")

    for candidate, _ in sorted(candidates.items(), key=lambda item: item[1], reverse=True):
        try:
            spot, _, rows = load_options_csv(candidate)
        except Exception:
            continue
        if spot is not None and rows:
            return candidate

    raise FileNotFoundError(f"No parseable SPX options CSV found under {scan_dir}")


def gex_per_1pct_move(gamma: float, open_interest: int, spot: float) -> float:
    return gamma * open_interest * CONTRACT_MULTIPLIER * (spot**2) * 0.01


def es_equivalent(strike: float, spot: float, es_price: float | None) -> float | None:
    if es_price is None:
        return None
    return strike + (es_price - spot)


def aggregate_by_strike(
    rows: list[OptionRow],
    *,
    quote_date: date | None,
    spot: float,
    max_dte: int,
    min_open_interest: int,
) -> tuple[list[StrikeMetrics], list[date]]:
    metrics_by_strike: dict[float, StrikeMetrics] = {}
    expirations_used: set[date] = set()

    for row in rows:
        dte = (row.expiration - quote_date).days if quote_date else 0
        if dte < 0 or dte > max_dte:
            continue

        item = metrics_by_strike.setdefault(row.strike, StrikeMetrics(strike=row.strike))
        call_proxy = row.call_gamma * row.call_open_interest if row.call_open_interest >= min_open_interest else 0.0
        put_proxy = row.put_gamma * row.put_open_interest if row.put_open_interest >= min_open_interest else 0.0
        call_gex = gex_per_1pct_move(row.call_gamma, row.call_open_interest, spot) if row.call_open_interest >= min_open_interest else 0.0
        put_gex = -gex_per_1pct_move(row.put_gamma, row.put_open_interest, spot) if row.put_open_interest >= min_open_interest else 0.0

        item.call_proxy += call_proxy
        item.put_proxy += put_proxy
        item.net_proxy += call_proxy - put_proxy
        item.call_gex_1pct += call_gex
        item.put_gex_1pct += put_gex
        item.net_gex_1pct += call_gex + put_gex
        item.call_volume += row.call_volume
        item.put_volume += row.put_volume
        item.call_open_interest += row.call_open_interest
        item.put_open_interest += row.put_open_interest
        item.expirations += 1
        expirations_used.add(row.expiration)

    metrics = sorted(metrics_by_strike.values(), key=lambda item: item.strike)
    return metrics, sorted(expirations_used)


def _select_call_row_by_delta(rows: list[OptionRow], target_delta: float) -> OptionRow | None:
    candidates = [row for row in rows if row.call_iv > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (abs(row.call_delta - target_delta), abs(row.strike)))


def _select_put_row_by_delta(rows: list[OptionRow], target_abs_delta: float) -> OptionRow | None:
    candidates = [row for row in rows if row.put_iv > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (abs(abs(row.put_delta) - target_abs_delta), abs(row.strike)))


def aggregate_by_expiration(
    rows: list[OptionRow],
    *,
    quote_date: date | None,
    spot: float,
    max_dte: int,
    min_open_interest: int,
) -> list[ExpirationMetrics]:
    rows_by_expiration: dict[date, list[OptionRow]] = {}

    for row in rows:
        dte = (row.expiration - quote_date).days if quote_date else 0
        if dte < 0 or dte > max_dte:
            continue
        rows_by_expiration.setdefault(row.expiration, []).append(row)

    expiration_metrics: list[ExpirationMetrics] = []
    for expiration in sorted(rows_by_expiration):
        expiry_rows = rows_by_expiration[expiration]
        dte = (expiration - quote_date).days if quote_date else 0
        call_gex = 0.0
        put_gex = 0.0

        for row in expiry_rows:
            if row.call_open_interest >= min_open_interest:
                call_gex += gex_per_1pct_move(row.call_gamma, row.call_open_interest, spot)
            if row.put_open_interest >= min_open_interest:
                put_gex += -gex_per_1pct_move(row.put_gamma, row.put_open_interest, spot)

        atm_row = min(expiry_rows, key=lambda row: (abs(row.strike - spot), abs(row.call_delta - 0.5)))
        call_25d_row = _select_call_row_by_delta(expiry_rows, 0.25)
        put_25d_row = _select_put_row_by_delta(expiry_rows, 0.25)
        dominant_call_row = max(
            expiry_rows,
            key=lambda row: (row.call_open_interest, row.call_gamma * row.call_open_interest, -abs(row.strike - spot)),
        )
        dominant_put_row = max(
            expiry_rows,
            key=lambda row: (row.put_open_interest, row.put_gamma * row.put_open_interest, -abs(row.strike - spot)),
        )

        atm_call_iv = atm_row.call_iv if atm_row.call_iv > 0 else None
        atm_put_iv = atm_row.put_iv if atm_row.put_iv > 0 else None
        atm_iv = None
        if atm_call_iv is not None and atm_put_iv is not None:
            atm_iv = (atm_call_iv + atm_put_iv) / 2.0
        elif atm_call_iv is not None:
            atm_iv = atm_call_iv
        elif atm_put_iv is not None:
            atm_iv = atm_put_iv

        call_25d_iv = call_25d_row.call_iv if call_25d_row and call_25d_row.call_iv > 0 else None
        put_25d_iv = put_25d_row.put_iv if put_25d_row and put_25d_row.put_iv > 0 else None
        put_call_ratio = None
        if call_25d_iv not in (None, 0) and put_25d_iv is not None:
            put_call_ratio = put_25d_iv / call_25d_iv
        risk_reversal = None
        if call_25d_iv is not None and put_25d_iv is not None:
            risk_reversal = call_25d_iv - put_25d_iv

        expiration_metrics.append(
            ExpirationMetrics(
                expiration=expiration.isoformat(),
                dte=dte,
                rows=len(expiry_rows),
                call_gex_1pct=call_gex,
                put_gex_1pct=put_gex,
                net_gex_1pct=call_gex + put_gex,
                atm_strike=atm_row.strike,
                atm_call_iv=atm_call_iv,
                atm_put_iv=atm_put_iv,
                atm_iv=atm_iv,
                call_25d_iv=call_25d_iv,
                put_25d_iv=put_25d_iv,
                put_call_iv_ratio_25d=put_call_ratio,
                risk_reversal_25d=risk_reversal,
                dominant_call_oi_strike=dominant_call_row.strike,
                dominant_put_oi_strike=dominant_put_row.strike,
            )
        )

    return expiration_metrics


def infer_strike_step(strike_metrics: list[StrikeMetrics]) -> float:
    if len(strike_metrics) < 2:
        return 5.0
    deltas = [
        round(strike_metrics[index + 1].strike - strike_metrics[index].strike, 4)
        for index in range(len(strike_metrics) - 1)
        if strike_metrics[index + 1].strike > strike_metrics[index].strike
    ]
    if not deltas:
        return 5.0
    positive = [delta for delta in deltas if delta > 0]
    return min(positive) if positive else 5.0


def compute_zero_gamma_proxy(strike_metrics: list[StrikeMetrics]) -> float | None:
    if not strike_metrics:
        return None

    cumulative = 0.0
    previous: tuple[float, float] | None = None
    best_strike = strike_metrics[0].strike
    best_abs = math.inf

    for item in strike_metrics:
        cumulative += item.net_gex_1pct
        if abs(cumulative) < best_abs:
            best_abs = abs(cumulative)
            best_strike = item.strike

        if previous is not None:
            previous_strike, previous_cumulative = previous
            crossed = (previous_cumulative <= 0 <= cumulative) or (previous_cumulative >= 0 >= cumulative)
            if crossed and cumulative != previous_cumulative:
                weight = abs(previous_cumulative) / (abs(previous_cumulative) + abs(cumulative))
                return previous_strike + (item.strike - previous_strike) * weight
        previous = (item.strike, cumulative)

    return best_strike


def build_levels(
    strike_metrics: list[StrikeMetrics],
    *,
    spot: float,
    es_price: float | None,
    top_n: int,
) -> tuple[list[Level], list[Level]]:
    above_spot = [item for item in strike_metrics if item.strike >= spot]
    below_spot = [item for item in strike_metrics if item.strike <= spot]

    resistance = sorted(above_spot, key=lambda item: item.call_gex_1pct, reverse=True)[:top_n]
    support = sorted(below_spot, key=lambda item: abs(item.put_gex_1pct), reverse=True)[:top_n]

    resistance_levels = [
        Level(
            strike=item.strike,
            es_equivalent=es_equivalent(item.strike, spot, es_price),
            score=item.call_gex_1pct,
            label="Resistance",
            call_open_interest=item.call_open_interest,
            put_open_interest=item.put_open_interest,
            call_volume=item.call_volume,
            put_volume=item.put_volume,
        )
        for item in resistance
    ]
    support_levels = [
        Level(
            strike=item.strike,
            es_equivalent=es_equivalent(item.strike, spot, es_price),
            score=abs(item.put_gex_1pct),
            label="Support",
            call_open_interest=item.call_open_interest,
            put_open_interest=item.put_open_interest,
            call_volume=item.call_volume,
            put_volume=item.put_volume,
        )
        for item in support
    ]
    return resistance_levels, support_levels


def dedupe_levels_by_strike(levels: list[Level]) -> list[Level]:
    seen: set[float] = set()
    deduped: list[Level] = []
    for level in levels:
        if level.strike in seen:
            continue
        seen.add(level.strike)
        deduped.append(level)
    return deduped


def build_acceleration_zones(
    *,
    support_levels: list[Level],
    resistance_levels: list[Level],
    spot: float,
    es_price: float | None,
) -> tuple[list[AccelerationZone], list[AccelerationZone]]:
    downside: list[AccelerationZone] = []
    upside: list[AccelerationZone] = []

    ordered_supports = sorted(dedupe_levels_by_strike(support_levels), key=lambda item: item.strike, reverse=True)
    ordered_resistances = sorted(dedupe_levels_by_strike(resistance_levels), key=lambda item: item.strike)

    def append_zone(
        target_list: list[AccelerationZone],
        *,
        direction: str,
        current: Level,
        target: Level,
    ) -> None:
        target_list.append(
            AccelerationZone(
                direction=direction,
                trigger_strike=current.strike,
                trigger_es=current.es_equivalent,
                target_strike=target.strike,
                target_es=target.es_equivalent,
                label=(
                    f"Below {format_price(current.strike)} can slide toward {format_price(target.strike)}"
                    if direction == "down"
                    else f"Above {format_price(current.strike)} can squeeze toward {format_price(target.strike)}"
                ),
                score=current.score + target.score,
            )
        )

    if len(ordered_supports) >= 3:
        append_zone(target_list=downside, direction="down", current=ordered_supports[1], target=ordered_supports[2])
        append_zone(target_list=downside, direction="down", current=ordered_supports[0], target=ordered_supports[1])
    else:
        for index, current in enumerate(ordered_supports):
            target = ordered_supports[index + 1] if index + 1 < len(ordered_supports) else None
            if target is None:
                continue
            append_zone(target_list=downside, direction="down", current=current, target=target)

    if len(ordered_resistances) >= 3:
        append_zone(target_list=upside, direction="up", current=ordered_resistances[1], target=ordered_resistances[2])
        append_zone(target_list=upside, direction="up", current=ordered_resistances[0], target=ordered_resistances[1])
    else:
        for index, current in enumerate(ordered_resistances):
            target = ordered_resistances[index + 1] if index + 1 < len(ordered_resistances) else None
            if target is None:
                continue
            append_zone(target_list=upside, direction="up", current=current, target=target)

    if not downside and ordered_supports:
        only = ordered_supports[0]
        downside.append(
            AccelerationZone(
                direction="down",
                trigger_strike=only.strike,
                trigger_es=only.es_equivalent,
                target_strike=min(spot, only.strike),
                target_es=es_equivalent(min(spot, only.strike), spot, es_price),
                label=f"Below {format_price(only.strike)} downside can speed up",
                score=only.score,
            )
        )

    if not upside and ordered_resistances:
        only = ordered_resistances[0]
        upside.append(
            AccelerationZone(
                direction="up",
                trigger_strike=only.strike,
                trigger_es=only.es_equivalent,
                target_strike=max(spot, only.strike),
                target_es=es_equivalent(max(spot, only.strike), spot, es_price),
                label=f"Above {format_price(only.strike)} upside can speed up",
                score=only.score,
            )
        )

    return upside[:2], downside[:2]


def build_wall_metrics(
    strike_metrics: list[StrikeMetrics],
    *,
    spot: float,
    es_price: float | None,
) -> tuple[WallMetrics | None, WallMetrics | None]:
    call_candidates = [item for item in strike_metrics if item.strike >= spot] or strike_metrics
    put_candidates = [item for item in strike_metrics if item.strike <= spot] or strike_metrics
    if not call_candidates or not put_candidates:
        return None, None

    dominant_call = max(
        call_candidates,
        key=lambda item: (item.call_open_interest, item.call_gex_1pct, -abs(item.strike - spot)),
    )
    dominant_put = max(
        put_candidates,
        key=lambda item: (item.put_open_interest, abs(item.put_gex_1pct), -abs(item.strike - spot)),
    )

    call_wall = WallMetrics(
        label="Call Wall",
        strike=dominant_call.strike,
        es_equivalent=es_equivalent(dominant_call.strike, spot, es_price),
        open_interest=dominant_call.call_open_interest,
        gex_1pct=dominant_call.call_gex_1pct,
        distance_from_spot=max(dominant_call.strike - spot, 0.0),
    )
    put_wall = WallMetrics(
        label="Put Wall",
        strike=dominant_put.strike,
        es_equivalent=es_equivalent(dominant_put.strike, spot, es_price),
        open_interest=dominant_put.put_open_interest,
        gex_1pct=abs(dominant_put.put_gex_1pct),
        distance_from_spot=max(spot - dominant_put.strike, 0.0),
    )
    return call_wall, put_wall


def _classify_term_structure(expiration_metrics: list[ExpirationMetrics]) -> tuple[str, ExpirationMetrics | None, ExpirationMetrics | None]:
    if len(expiration_metrics) < 2:
        return "仅纳入一个到期日，无法判断前端期限结构。", expiration_metrics[0] if expiration_metrics else None, None

    front = expiration_metrics[0]
    next_expiry = expiration_metrics[1]
    if front.atm_iv is None or next_expiry.atm_iv is None:
        return "到期日足够，但 ATM IV 不完整，无法判断期限结构。", front, next_expiry

    slope = front.atm_iv - next_expiry.atm_iv
    if slope >= 0.015:
        return "近端 ATM IV 高于次近月，前端保护更贵，事件/隔夜风险更集中。", front, next_expiry
    if slope <= -0.015:
        return "远端 ATM IV 高于近端，前端挤压没有明显强于后端。", front, next_expiry
    return "近端和次近月 ATM IV 接近，期限结构没有明显前端挤压。", front, next_expiry


def build_structural_regime(
    *,
    strike_metrics: list[StrikeMetrics],
    expiration_metrics: list[ExpirationMetrics],
    spot: float,
    es_price: float | None,
    strike_step: float,
    total_net_gex_1pct: float,
) -> StructuralRegime:
    local_half_width = max(strike_step * 2.0, spot * 0.004)
    local_low = spot - local_half_width
    local_high = spot + local_half_width
    local_net = sum(item.net_gex_1pct for item in strike_metrics if local_low <= item.strike <= local_high)

    macro_regime = "宏观负 Gamma / 更容易放大和延续" if total_net_gex_1pct < 0 else "宏观正 Gamma / 更偏均值回归"
    local_regime = "局部正 Gamma / 现价附近更容易钉住和来回" if local_net >= 0 else "局部负 Gamma / 现价附近更容易继续扩张"
    call_wall, put_wall = build_wall_metrics(strike_metrics, spot=spot, es_price=es_price)
    term_structure_label, front_expiry, next_expiry = _classify_term_structure(expiration_metrics)

    gap_chop_score = 0
    reasons: list[str] = []
    if total_net_gex_1pct < 0:
        gap_chop_score += 35
        reasons.append("总净 Gamma 仍偏负，墙位一旦被打穿，盘面更容易放大。")
    if local_net > 0:
        gap_chop_score += 30
        reasons.append("现价附近局部 Gamma 转正，更容易被钉在关键执行价之间来回。")

    if call_wall is not None and put_wall is not None:
        corridor_width = call_wall.distance_from_spot + put_wall.distance_from_spot
        tight_corridor = max(strike_step * 6.0, spot * 0.012)
        medium_corridor = max(strike_step * 10.0, spot * 0.018)
        if corridor_width <= tight_corridor:
            gap_chop_score += 20
            reasons.append("现价被 put wall 和 call wall 夹在较窄区间内，RTH 更容易反复 chop。")
        elif corridor_width <= medium_corridor:
            gap_chop_score += 10
            reasons.append("上下墙位仍在可交易距离内，方向单边前通常要先完成墙位切换。")

    if front_expiry is not None and front_expiry.put_call_iv_ratio_25d is not None:
        if front_expiry.put_call_iv_ratio_25d >= 1.15:
            gap_chop_score += 10
            reasons.append("前端 25Δ put/call IV ratio 偏高，put skew 仍在为尾部风险定高价。")
    elif front_expiry is not None and front_expiry.risk_reversal_25d is not None and front_expiry.risk_reversal_25d <= -0.03:
        gap_chop_score += 10
        reasons.append("前端 risk reversal 明显向 put 倾斜，保护性需求仍偏重。")

    if (
        front_expiry is not None
        and next_expiry is not None
        and front_expiry.atm_iv is not None
        and next_expiry.atm_iv is not None
        and front_expiry.atm_iv - next_expiry.atm_iv >= 0.015
    ):
        gap_chop_score += 10
        reasons.append("近端 IV 高于次近月，隔夜和事件风险更多被压在前端。")

    gap_chop_score = max(0, min(100, gap_chop_score))
    if total_net_gex_1pct < 0 and local_net > 0 and gap_chop_score >= 70:
        gap_chop_bias = "Gap-and-chop 倾向强"
    elif total_net_gex_1pct < 0 and local_net > 0:
        gap_chop_bias = "Gap-and-chop 倾向中等"
    elif total_net_gex_1pct < 0:
        gap_chop_bias = "更偏负 Gamma 趋势/破位日"
    else:
        gap_chop_bias = "更偏正 Gamma 均值回归日"

    if not reasons:
        reasons.append("当前结构没有形成明显的墙内反复条件，更多看净 Gamma 和破位方向。")

    return StructuralRegime(
        macro_gamma_regime=macro_regime,
        local_gamma_regime=local_regime,
        local_net_gex_1pct=local_net,
        local_strike_span_low=local_low,
        local_strike_span_high=local_high,
        dominant_call_wall=call_wall,
        dominant_put_wall=put_wall,
        term_structure_label=term_structure_label,
        front_expiry=front_expiry.expiration if front_expiry else None,
        front_atm_iv=front_expiry.atm_iv if front_expiry else None,
        next_expiry=next_expiry.expiration if next_expiry else None,
        next_atm_iv=next_expiry.atm_iv if next_expiry else None,
        front_put_call_iv_ratio_25d=front_expiry.put_call_iv_ratio_25d if front_expiry else None,
        front_risk_reversal_25d=front_expiry.risk_reversal_25d if front_expiry else None,
        gap_chop_score=gap_chop_score,
        gap_chop_bias=gap_chop_bias,
        gap_chop_reasons=reasons,
    )


def _nested_dict_value(payload: dict[str, object] | None, *keys: str) -> object | None:
    current: object | None = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def build_tracking_delta(summary: GammaMapSummary, previous_payload: dict[str, object] | None) -> TrackingDelta | None:
    if not previous_payload:
        return None

    previous_quote_time = _nested_dict_value(previous_payload, "quote_time")
    previous_source_file = _nested_dict_value(previous_payload, "source_file")
    previous_total_net = _nested_dict_value(previous_payload, "total_net_gex_1pct")
    previous_zero_gamma = _nested_dict_value(previous_payload, "zero_gamma_proxy")
    previous_local_net = _nested_dict_value(previous_payload, "structural_regime", "local_net_gex_1pct")
    previous_put_wall = _nested_dict_value(previous_payload, "structural_regime", "dominant_put_wall", "strike")
    previous_call_wall = _nested_dict_value(previous_payload, "structural_regime", "dominant_call_wall", "strike")
    previous_gap_chop_score = _nested_dict_value(previous_payload, "structural_regime", "gap_chop_score")
    previous_front_ratio = _nested_dict_value(previous_payload, "structural_regime", "front_put_call_iv_ratio_25d")

    current_structural = summary.structural_regime
    if current_structural is None:
        return None

    net_change = (
        summary.total_net_gex_1pct - float(previous_total_net)
        if isinstance(previous_total_net, (int, float))
        else None
    )
    zero_gamma_shift = (
        summary.zero_gamma_proxy - float(previous_zero_gamma)
        if summary.zero_gamma_proxy is not None and isinstance(previous_zero_gamma, (int, float))
        else None
    )
    local_net_change = (
        current_structural.local_net_gex_1pct - float(previous_local_net)
        if isinstance(previous_local_net, (int, float))
        else None
    )
    put_wall_shift = (
        current_structural.dominant_put_wall.strike - float(previous_put_wall)
        if current_structural.dominant_put_wall is not None and isinstance(previous_put_wall, (int, float))
        else None
    )
    call_wall_shift = (
        current_structural.dominant_call_wall.strike - float(previous_call_wall)
        if current_structural.dominant_call_wall is not None and isinstance(previous_call_wall, (int, float))
        else None
    )
    gap_chop_score_change = (
        current_structural.gap_chop_score - int(previous_gap_chop_score)
        if isinstance(previous_gap_chop_score, (int, float))
        else None
    )
    front_ratio_change = (
        current_structural.front_put_call_iv_ratio_25d - float(previous_front_ratio)
        if current_structural.front_put_call_iv_ratio_25d is not None and isinstance(previous_front_ratio, (int, float))
        else None
    )

    interpretation: list[str] = []
    if net_change is not None and abs(net_change) > max(abs(summary.total_net_gex_1pct) * 0.08, 1_000_000):
        direction = "回到更正" if net_change > 0 else "转向更负"
        interpretation.append(f"总净 Gamma 较上一份快照{direction}。")
    if zero_gamma_shift is not None and abs(zero_gamma_shift) >= max(summary.strike_step, 5.0):
        direction = "上移" if zero_gamma_shift > 0 else "下移"
        interpretation.append(f"Zero Gamma 参考位明显{direction}。")
    if put_wall_shift is not None and abs(put_wall_shift) >= max(summary.strike_step, 5.0):
        direction = "上移" if put_wall_shift > 0 else "下移"
        interpretation.append(f"Put wall {direction}，下方防守位置发生切换。")
    if call_wall_shift is not None and abs(call_wall_shift) >= max(summary.strike_step, 5.0):
        direction = "上移" if call_wall_shift > 0 else "下移"
        interpretation.append(f"Call wall {direction}，上方压制位置发生切换。")
    if gap_chop_score_change is not None and abs(gap_chop_score_change) >= 10:
        direction = "增强" if gap_chop_score_change > 0 else "减弱"
        interpretation.append(f"Gap-and-chop 结构分数{direction}。")
    if front_ratio_change is not None and abs(front_ratio_change) >= 0.05:
        direction = "更偏 put 侧" if front_ratio_change > 0 else "对 put 侧的定价压力缓和"
        interpretation.append(f"前端 skew {direction}。")
    if not interpretation:
        interpretation.append("和上一份快照相比，核心墙位和 regime 没有出现足够大的位移。")

    return TrackingDelta(
        previous_quote_time=str(previous_quote_time) if previous_quote_time is not None else None,
        previous_source_file=str(previous_source_file) if previous_source_file is not None else None,
        net_gex_change_1pct=net_change,
        zero_gamma_shift=zero_gamma_shift,
        local_net_gex_change_1pct=local_net_change,
        dominant_put_wall_shift=put_wall_shift,
        dominant_call_wall_shift=call_wall_shift,
        gap_chop_score_change=gap_chop_score_change,
        front_put_call_iv_ratio_25d_change=front_ratio_change,
        interpretation=interpretation,
    )


def analyze_spx_gamma_csv(
    csv_path: Path,
    *,
    es_price: float | None = None,
    max_dte: int = 7,
    top_n: int = 3,
    min_open_interest: int = 1,
) -> GammaMapSummary:
    spot, quote_dt, rows = load_options_csv(csv_path)
    if spot is None:
        raise ValueError(f"Could not parse SPX spot from {csv_path}.")
    if not rows:
        raise ValueError(f"No options rows found in {csv_path}.")

    strike_metrics, expirations_used = aggregate_by_strike(
        rows,
        quote_date=quote_dt.date() if quote_dt else None,
        spot=spot,
        max_dte=max_dte,
        min_open_interest=min_open_interest,
    )
    if not strike_metrics:
        raise ValueError("No rows matched the provided filters.")

    expiration_metrics = aggregate_by_expiration(
        rows,
        quote_date=quote_dt.date() if quote_dt else None,
        spot=spot,
        max_dte=max_dte,
        min_open_interest=min_open_interest,
    )
    zero_gamma = compute_zero_gamma_proxy(strike_metrics)
    total_call = sum(item.call_gex_1pct for item in strike_metrics)
    total_put = sum(item.put_gex_1pct for item in strike_metrics)
    total_net = sum(item.net_gex_1pct for item in strike_metrics)
    resistance_levels, support_levels = build_levels(
        strike_metrics,
        spot=spot,
        es_price=es_price,
        top_n=top_n,
    )
    upside_accel, downside_accel = build_acceleration_zones(
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        spot=spot,
        es_price=es_price,
    )

    regime = "正 Gamma / 更偏回归均值" if total_net > 0 else "负 Gamma / 更容易扩张和加速"
    structural_regime = build_structural_regime(
        strike_metrics=strike_metrics,
        expiration_metrics=expiration_metrics,
        spot=spot,
        es_price=es_price,
        strike_step=infer_strike_step(strike_metrics),
        total_net_gex_1pct=total_net,
    )
    return GammaMapSummary(
        source_file=str(csv_path),
        quote_time=quote_dt.isoformat(sep=" ") if quote_dt else None,
        spx_spot=spot,
        es_price=es_price,
        max_dte=max_dte,
        min_open_interest=min_open_interest,
        strike_step=infer_strike_step(strike_metrics),
        included_expirations=[item.isoformat() for item in expirations_used],
        regime=regime,
        zero_gamma_proxy=zero_gamma,
        zero_gamma_proxy_es=es_equivalent(zero_gamma, spot, es_price) if zero_gamma is not None else None,
        total_call_gex_1pct=total_call,
        total_put_gex_1pct=total_put,
        total_net_gex_1pct=total_net,
        resistance_levels=resistance_levels,
        support_levels=support_levels,
        upside_acceleration_zones=upside_accel,
        downside_acceleration_zones=downside_accel,
        strike_metrics=strike_metrics,
        expiration_metrics=expiration_metrics,
        structural_regime=structural_regime,
    )


def format_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def format_compact_dollars(value: float) -> str:
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{sign}${magnitude / 1_000_000_000:.2f}B"
    if magnitude >= 1_000_000:
        return f"{sign}${magnitude / 1_000_000:.2f}M"
    return f"{sign}${magnitude:,.0f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1%}"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}x"


def format_signed_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+,.2f}"


def format_level_line(prefix: str, level: Level) -> str:
    return (
        f"{prefix} SPX {format_price(level.strike)}"
        f" | ES {format_price(level.es_equivalent)}"
        f" | score {format_compact_dollars(level.score)}"
        f" | call OI {level.call_open_interest:,}"
        f" | put OI {level.put_open_interest:,}"
    )


def render_text_report(summary: GammaMapSummary) -> str:
    lines = [
        f"来源文件: {summary.source_file}",
        f"报价时间: {summary.quote_time or 'unknown'}",
        f"SPX 现价: {format_price(summary.spx_spot)}",
        f"ES 价格: {format_price(summary.es_price)}",
        f"Gamma 环境: {summary.regime}",
        f"Zero Gamma 参考位: SPX {format_price(summary.zero_gamma_proxy)} | ES {format_price(summary.zero_gamma_proxy_es)}",
        f"Call GEX 代理值 (1% move): {format_compact_dollars(summary.total_call_gex_1pct)}",
        f"Put GEX 代理值 (1% move): {format_compact_dollars(summary.total_put_gex_1pct)}",
        f"Net GEX 代理值 (1% move): {format_compact_dollars(summary.total_net_gex_1pct)}",
        f"纳入到期日: {', '.join(summary.included_expirations)}",
        "",
        "到达后容易减速的价位:",
    ]
    if summary.resistance_levels:
        lines.extend(
            f"  阻力 {index}: SPX {format_price(level.strike)} | ES {format_price(level.es_equivalent)} | 压力 {format_compact_dollars(level.score)}"
            for index, level in enumerate(summary.resistance_levels, start=1)
        )
    else:
        lines.append("  无")

    lines.append("")
    lines.append("到达后容易承接和减速的价位:")
    if summary.support_levels:
        lines.extend(
            f"  支撑 {index}: SPX {format_price(level.strike)} | ES {format_price(level.es_equivalent)} | 支撑 {format_compact_dollars(level.score)}"
            for index, level in enumerate(summary.support_levels, start=1)
        )
    else:
        lines.append("  无")

    lines.append("")
    lines.append("破位后容易加速的提醒:")
    if summary.upside_acceleration_zones:
        for zone in summary.upside_acceleration_zones:
            lines.append(
                f"  上破提醒: ES {format_price(zone.trigger_es)} 上方容易加速，目标先看 ES {format_price(zone.target_es)}"
            )
    if summary.downside_acceleration_zones:
        for zone in summary.downside_acceleration_zones:
            lines.append(
                f"  下破提醒: ES {format_price(zone.trigger_es)} 下方容易加速，目标先看 ES {format_price(zone.target_es)}"
            )
    if not summary.upside_acceleration_zones and not summary.downside_acceleration_zones:
        lines.append("  无")

    structural = summary.structural_regime
    if structural is not None:
        lines.append("")
        lines.append("结构状态:")
        lines.append(f"  宏观: {structural.macro_gamma_regime}")
        lines.append(
            f"  局部: {structural.local_gamma_regime}"
            f" | 区间 SPX {format_price(structural.local_strike_span_low)} - {format_price(structural.local_strike_span_high)}"
            f" | local net {format_compact_dollars(structural.local_net_gex_1pct)}"
        )
        if structural.dominant_put_wall is not None:
            lines.append(
                f"  Put Wall: SPX {format_price(structural.dominant_put_wall.strike)}"
                f" | ES {format_price(structural.dominant_put_wall.es_equivalent)}"
                f" | OI {structural.dominant_put_wall.open_interest:,}"
                f" | 距现价 {format_signed_number(-structural.dominant_put_wall.distance_from_spot)}"
            )
        if structural.dominant_call_wall is not None:
            lines.append(
                f"  Call Wall: SPX {format_price(structural.dominant_call_wall.strike)}"
                f" | ES {format_price(structural.dominant_call_wall.es_equivalent)}"
                f" | OI {structural.dominant_call_wall.open_interest:,}"
                f" | 距现价 {format_signed_number(structural.dominant_call_wall.distance_from_spot)}"
            )
        lines.append(f"  期限结构: {structural.term_structure_label}")
        lines.append(
            f"  前端 skew: 25Δ put/call {format_ratio(structural.front_put_call_iv_ratio_25d)}"
            f" | RR25Δ {format_percent(structural.front_risk_reversal_25d)}"
        )
        lines.append(f"  Gap&Chop 结构分数: {structural.gap_chop_score}/100 | {structural.gap_chop_bias}")
        for reason in structural.gap_chop_reasons:
            lines.append(f"  - {reason}")

    if summary.expiration_metrics:
        lines.append("")
        lines.append("按到期日观察:")
        for item in summary.expiration_metrics[:4]:
            lines.append(
                f"  {item.expiration} (DTE {item.dte}):"
                f" ATM IV {format_percent(item.atm_iv)}"
                f" | 25Δ put/call {format_ratio(item.put_call_iv_ratio_25d)}"
                f" | 净 GEX {format_compact_dollars(item.net_gex_1pct)}"
                f" | put wall {format_price(item.dominant_put_oi_strike)}"
                f" | call wall {format_price(item.dominant_call_oi_strike)}"
            )

    if summary.tracking_delta is not None:
        delta = summary.tracking_delta
        lines.append("")
        lines.append("和上一份快照相比:")
        lines.append(f"  上一份报价时间: {delta.previous_quote_time or 'unknown'}")
        lines.append(f"  Net GEX 变化: {format_compact_dollars(delta.net_gex_change_1pct or 0.0) if delta.net_gex_change_1pct is not None else '-'}")
        lines.append(f"  Zero Gamma 位移: {format_signed_number(delta.zero_gamma_shift)}")
        lines.append(f"  Local Net 变化: {format_compact_dollars(delta.local_net_gex_change_1pct or 0.0) if delta.local_net_gex_change_1pct is not None else '-'}")
        lines.append(f"  Put Wall 位移: {format_signed_number(delta.dominant_put_wall_shift)}")
        lines.append(f"  Call Wall 位移: {format_signed_number(delta.dominant_call_wall_shift)}")
        lines.append(
            f"  Gap&Chop 分数变化: {delta.gap_chop_score_change:+d}"
            if delta.gap_chop_score_change is not None
            else "  Gap&Chop 分数变化: -"
        )
        lines.append(
            f"  前端 skew 变化: {format_signed_number(delta.front_put_call_iv_ratio_25d_change)}"
        )
        for item in delta.interpretation:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def _build_ai_prompt_payload(summary: GammaMapSummary) -> dict[str, object]:
    return {
        "source_file": summary.source_file,
        "quote_time": summary.quote_time,
        "spx_spot": summary.spx_spot,
        "es_price": summary.es_price,
        "regime": summary.regime,
        "zero_gamma_proxy": summary.zero_gamma_proxy,
        "zero_gamma_proxy_es": summary.zero_gamma_proxy_es,
        "included_expirations": summary.included_expirations,
        "total_call_gex_1pct": summary.total_call_gex_1pct,
        "total_put_gex_1pct": summary.total_put_gex_1pct,
        "total_net_gex_1pct": summary.total_net_gex_1pct,
        "resistance_levels": [
            {
                "spx": level.strike,
                "es": level.es_equivalent,
                "score": level.score,
                "call_open_interest": level.call_open_interest,
                "put_open_interest": level.put_open_interest,
            }
            for level in summary.resistance_levels
        ],
        "support_levels": [
            {
                "spx": level.strike,
                "es": level.es_equivalent,
                "score": level.score,
                "call_open_interest": level.call_open_interest,
                "put_open_interest": level.put_open_interest,
            }
            for level in summary.support_levels
        ],
        "upside_acceleration_zones": [
            {
                "trigger_es": zone.trigger_es,
                "target_es": zone.target_es,
                "trigger_spx": zone.trigger_strike,
                "target_spx": zone.target_strike,
            }
            for zone in summary.upside_acceleration_zones
        ],
        "downside_acceleration_zones": [
            {
                "trigger_es": zone.trigger_es,
                "target_es": zone.target_es,
                "trigger_spx": zone.trigger_strike,
                "target_spx": zone.target_strike,
            }
            for zone in summary.downside_acceleration_zones
        ],
        "expiration_metrics": [asdict(item) for item in summary.expiration_metrics],
        "structural_regime": asdict(summary.structural_regime) if summary.structural_regime else None,
        "tracking_delta": asdict(summary.tracking_delta) if summary.tracking_delta else None,
    }


def _split_ai_lines(content: str) -> list[str]:
    lines = [line.strip(" -\t") for line in content.splitlines() if line.strip()]
    return lines


def _wrap_svg_text(text: str, max_chars: int = 26) -> list[str]:
    wrapped: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            if current:
                wrapped.append(current)
                current = ""
            continue
        current += char
        if len(current) >= max_chars:
            wrapped.append(current)
            current = ""
    if current:
        wrapped.append(current)
    return wrapped


def _append_svg_text_lines(
    svg: list[str],
    *,
    x: float,
    y: float,
    lines: list[str],
    font_size: int = 15,
    line_height: int = 22,
    fill: str = "#24334d",
    font_weight: str = "400",
    text_anchor: str = "start",
) -> float:
    current_y = y
    anchor_attr = f' text-anchor="{text_anchor}"' if text_anchor != "start" else ""
    for line in lines:
        svg.append(
            f'<text x="{x}" y="{current_y}" font-size="{font_size}" font-weight="{font_weight}" fill="{fill}"{anchor_attr}>{escape(line)}</text>'
        )
        current_y += line_height
    return current_y


def format_chart_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{round(value):,.0f}"


def _band_bounds_from_levels(
    levels: list[Level],
    *,
    y_for,
    row_height: float,
    limit: int = 2,
    padding: float = 10.0,
) -> tuple[float, float] | None:
    selected = levels[:limit]
    if not selected:
        return None
    ys = [y_for(level.strike) for level in selected]
    return (min(ys) - row_height / 2 - padding, max(ys) + row_height / 2 + padding)


def _band_bounds_from_zone(
    zone: AccelerationZone | None,
    *,
    y_for,
    row_height: float,
    padding: float = 10.0,
) -> tuple[float, float] | None:
    if zone is None:
        return None
    first_y = y_for(zone.trigger_strike)
    second_y = y_for(zone.target_strike)
    return (min(first_y, second_y) - row_height / 2 - padding, max(first_y, second_y) + row_height / 2 + padding)


def _format_es_range(values: list[float | None]) -> str:
    valid = sorted(value for value in values if value is not None)
    if not valid:
        return "ES -"
    if abs(valid[0] - valid[-1]) < 0.005:
        return f"ES {format_chart_price(valid[0])}"
    return f"ES {format_chart_price(valid[0])} - {format_chart_price(valid[-1])}"


def _layout_callouts(callouts: list[dict[str, object]], *, top: float, bottom: float, min_gap: float = 16.0) -> None:
    if not callouts:
        return

    ordered = sorted(callouts, key=lambda item: float(item["desired_center"]))
    cursor = top
    for item in ordered:
        box_height = float(item["box_height"])
        desired_top = float(item["desired_center"]) - box_height / 2
        box_top = max(top, desired_top, cursor)
        item["box_top"] = box_top
        cursor = box_top + box_height + min_gap

    overflow = cursor - min_gap - bottom
    if overflow > 0:
        for item in reversed(ordered):
            headroom = float(item["box_top"]) - top
            shift = min(headroom, overflow)
            item["box_top"] = float(item["box_top"]) - shift
            overflow -= shift
            if overflow <= 0:
                break

        cursor = top
        for item in ordered:
            item["box_top"] = max(float(item["box_top"]), cursor)
            cursor = float(item["box_top"]) + float(item["box_height"]) + min_gap


def _append_svg_callout(
    svg: list[str],
    *,
    side: str,
    box_left: float,
    box_width: float,
    bracket_x: float,
    band_top: float,
    band_bottom: float,
    box_top: float,
    lines: list[str],
    fill: str,
    stroke: str,
    text_fill: str,
) -> None:
    if not lines:
        return

    box_height = 22 + len(lines) * 17
    box_center_y = box_top + box_height / 2
    band_center_y = (band_top + band_bottom) / 2
    bracket_cap = 12
    connector_x = box_left if side == "right" else box_left + box_width
    cap_target_x = bracket_x - bracket_cap if side == "right" else bracket_x + bracket_cap

    svg.append(
        f'<line x1="{bracket_x}" y1="{band_top}" x2="{bracket_x}" y2="{band_bottom}" stroke="{stroke}" stroke-width="2.5" opacity="0.9"/>'
    )
    svg.append(
        f'<line x1="{bracket_x}" y1="{band_top}" x2="{cap_target_x}" y2="{band_top}" stroke="{stroke}" stroke-width="2.5" opacity="0.9"/>'
    )
    svg.append(
        f'<line x1="{bracket_x}" y1="{band_bottom}" x2="{cap_target_x}" y2="{band_bottom}" stroke="{stroke}" stroke-width="2.5" opacity="0.9"/>'
    )
    svg.append(
        f'<line x1="{bracket_x}" y1="{band_center_y}" x2="{connector_x}" y2="{box_center_y}" stroke="{stroke}" stroke-width="2" opacity="0.75"/>'
    )
    svg.append(f'<circle cx="{bracket_x}" cy="{band_center_y}" r="4.5" fill="{stroke}" opacity="0.88"/>')
    svg.append(
        f'<rect x="{box_left}" y="{box_top}" width="{box_width}" height="{box_height}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
    )
    _append_svg_text_lines(
        svg,
        x=box_left + box_width / 2,
        y=box_top + 24,
        lines=lines,
        font_size=13,
        line_height=17,
        fill=text_fill,
        font_weight="700",
        text_anchor="middle",
    )


def generate_ai_options_analysis(
    summary: GammaMapSummary,
    *,
    config: AppConfig,
    question: str | None = None,
) -> AiAnalysisResult:
    if not config.openai_api_key:
        raise ValueError("AI analysis is unavailable because OPENAI_API_KEY is not configured.")

    client = OpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url or None,
        timeout=config.ai_timeout_seconds,
    )
    user_question = question or "请结合这些 SPX 期权链推导出的 ES 关键位，给出今天的盘中交易解读。"
    payload = _build_ai_prompt_payload(summary)
    response = client.chat.completions.create(
        model=config.ai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是盘中期权结构解读员。"
                    "任务是把 SPX 期权链聚合结果翻成 ES 交易提醒。"
                    "只能根据给定数据说话，不允许补充新闻、订单流、成交量细节或主观猜测。"
                    "风格要求：直接、短句、像交易员口播，不要解释太多。"
                    "必须只输出 6 行，不要标题，不要 markdown，不要序号，不要空行。"
                    "每行必须严格使用这些前缀："
                    "环境: "
                    "阻力: "
                    "支撑: "
                    "上破: "
                    "下破: "
                    "执行: "
                    "写法要求："
                    "1. 阻力和支撑行必须先写最关键 ES 位，再写下一目标位；"
                    "2. 上破和下破行必须写成“过/破某个 ES 位，先看某个 ES 位”；"
                    "3. 每行尽量 14 到 28 个汉字，能短就短；"
                    "4. 不要说废话，不要用‘关注’‘留意’这种空词；"
                    "5. 环境行只说当前 gamma 环境对盘面节奏的含义；"
                    "6. 执行行必须明确说这些结论来自 proxy GEX / 期权链聚合，不是真实 dealer book。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": user_question,
                        "market_summary": payload,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.2,
        max_tokens=900,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("AI analysis returned an empty response.")
    return AiAnalysisResult(
        provider=config.ai_provider,
        model=config.ai_model,
        content=content,
    )


def _select_display_strike_metrics(summary: GammaMapSummary) -> list[StrikeMetrics]:
    if not summary.strike_metrics:
        return []

    metrics_by_strike = {item.strike: item for item in summary.strike_metrics}
    selected_strikes: set[float] = set()

    ordered_supports = sorted(dedupe_levels_by_strike(summary.support_levels), key=lambda item: item.strike, reverse=True)
    ordered_resistances = sorted(dedupe_levels_by_strike(summary.resistance_levels), key=lambda item: item.strike)

    for level in ordered_supports[:3]:
        selected_strikes.add(level.strike)
    for level in ordered_resistances[:3]:
        selected_strikes.add(level.strike)
    for zone in summary.upside_acceleration_zones[:2]:
        selected_strikes.add(zone.trigger_strike)
        selected_strikes.add(zone.target_strike)
    for zone in summary.downside_acceleration_zones[:2]:
        selected_strikes.add(zone.trigger_strike)
        selected_strikes.add(zone.target_strike)

    nearest_spot_item = min(summary.strike_metrics, key=lambda item: abs(item.strike - summary.spx_spot))
    selected_strikes.add(nearest_spot_item.strike)

    if summary.zero_gamma_proxy is not None:
        nearest_zero_item = min(summary.strike_metrics, key=lambda item: abs(item.strike - summary.zero_gamma_proxy))
        current_min = min(selected_strikes)
        current_max = max(selected_strikes)
        step = summary.strike_step or 5.0
        if current_min - step * 2 <= nearest_zero_item.strike <= current_max + step * 2:
            selected_strikes.add(nearest_zero_item.strike)

    selected = [metrics_by_strike[strike] for strike in sorted(selected_strikes) if strike in metrics_by_strike]
    return selected or summary.strike_metrics


def render_svg(summary: GammaMapSummary) -> str:
    return render_svg_with_ai(summary, ai_result=None)


def render_svg_with_ai(summary: GammaMapSummary, ai_result: AiAnalysisResult | None) -> str:
    display_metrics = _select_display_strike_metrics(summary)
    chart_support_levels = sorted(dedupe_levels_by_strike(summary.support_levels), key=lambda item: item.strike, reverse=True)
    chart_resistance_levels = sorted(dedupe_levels_by_strike(summary.resistance_levels), key=lambda item: item.strike)
    strikes = [item.strike for item in display_metrics]
    plot_min = min(strikes + [summary.spx_spot])
    plot_max = max(strikes + [summary.spx_spot])
    if plot_max == plot_min:
        plot_max += summary.strike_step
        plot_min -= summary.strike_step

    ai_lines = _split_ai_lines(ai_result.content) if ai_result else []
    ai_wrapped_lines: list[str] = []
    for line in ai_lines[:6]:
        ai_wrapped_lines.extend(_wrap_svg_text(line, max_chars=26))

    resistance_values = [format_chart_price(level.es_equivalent) for level in chart_resistance_levels if level.es_equivalent is not None]
    support_values = [format_chart_price(level.es_equivalent) for level in chart_support_levels if level.es_equivalent is not None]
    quick_lines_raw = [
        f"环境: {summary.regime}",
        f"上方减速: ES {' / '.join(resistance_values[:3])}" if resistance_values else "上方减速: 无",
        f"下方承接: ES {' / '.join(support_values[:3])}" if support_values else "下方承接: 无",
        (
            f"上破计划: ES {format_chart_price(summary.upside_acceleration_zones[0].trigger_es)} -> ES {format_chart_price(summary.upside_acceleration_zones[0].target_es)}"
            if summary.upside_acceleration_zones
            else "上破计划: 无"
        ),
        (
            f"下破计划: ES {format_chart_price(summary.downside_acceleration_zones[0].trigger_es)} -> ES {format_chart_price(summary.downside_acceleration_zones[0].target_es)}"
            if summary.downside_acceleration_zones
            else "下破计划: 无"
        ),
        f"Zero Gamma: ES {format_chart_price(summary.zero_gamma_proxy_es)}",
    ]
    quick_lines: list[str] = []
    for line in quick_lines_raw:
        quick_lines.extend(_wrap_svg_text(line, max_chars=28))

    side_rows = len(quick_lines) + len(ai_wrapped_lines) + 18

    width = 1760
    height = max(980, 260 + len(display_metrics) * 34, 280 + side_rows * 22)
    panel_top = 210
    panel_bottom = height - 60
    main_left = 60
    main_right = 1210
    main_width = main_right - main_left
    main_height = panel_bottom - panel_top
    side_left = 1240
    side_width = width - side_left - 40
    side_height = panel_bottom - panel_top

    plot_left = main_left + 20
    plot_right = main_right - 20
    plot_top = panel_top + 52
    plot_bottom = panel_bottom - 28
    plot_height = plot_bottom - plot_top

    left_callout_left = plot_left + 8
    left_callout_width = 150
    left_callout_right = left_callout_left + left_callout_width
    support_left = left_callout_right + 24
    support_right = support_left + 210
    ladder_left = support_right + 30
    ladder_right = ladder_left + 260
    resistance_left = ladder_right + 30
    resistance_right = resistance_left + 210
    right_callout_left = resistance_right + 24
    right_callout_right = plot_right - 8
    right_callout_width = right_callout_right - right_callout_left
    ladder_width = ladder_right - ladder_left

    max_support = max((abs(item.put_gex_1pct) for item in display_metrics), default=1.0)
    max_resistance = max((item.call_gex_1pct for item in display_metrics), default=1.0)
    max_net = max((abs(item.net_gex_1pct) for item in display_metrics), default=1.0)
    max_support = max(max_support, 1.0)
    max_resistance = max(max_resistance, 1.0)
    max_net = max(max_net, 1.0)

    def y_for(strike: float) -> float:
        return plot_top + ((plot_max - strike) / (plot_max - plot_min)) * plot_height

    def support_width(value: float) -> float:
        return (abs(value) / max_support) * (support_right - support_left)

    def resistance_width(value: float) -> float:
        return (abs(value) / max_resistance) * (resistance_right - resistance_left)

    def net_meter_width(value: float) -> float:
        return 12 + (abs(value) / max_net) * (ladder_width - 42)

    def clamp_band(bounds: tuple[float, float] | None) -> tuple[float, float] | None:
        if bounds is None:
            return None
        top, bottom = bounds
        return (max(plot_top + 6, top), min(plot_bottom - 6, bottom))

    def band_label(levels: list[Level]) -> str:
        selected = levels[:2]
        es_values = [level.es_equivalent for level in selected if level.es_equivalent is not None]
        if es_values:
            return _format_es_range(es_values)
        strikes = sorted(level.strike for level in selected)
        if not strikes:
            return "SPX -"
        if abs(strikes[0] - strikes[-1]) < 0.005:
            return f"SPX {format_chart_price(strikes[0])}"
        return f"SPX {format_chart_price(strikes[0])} - {format_chart_price(strikes[-1])}"

    def zone_level_line(prefix: str, es_value: float | None, strike: float) -> str:
        if es_value is not None:
            return f"{prefix} ES {format_chart_price(es_value)}"
        return f"{prefix} SPX {format_chart_price(strike)}"

    row_height = max(16.0, min(24.0, plot_height / max(len(display_metrics), 1) * 0.80))
    primary_resistance_band_levels = chart_resistance_levels[:2]
    primary_support_band_levels = chart_support_levels[:2]
    primary_resistance_band = clamp_band(
        _band_bounds_from_levels(primary_resistance_band_levels, y_for=y_for, row_height=row_height, limit=2)
    )
    primary_support_band = clamp_band(
        _band_bounds_from_levels(primary_support_band_levels, y_for=y_for, row_height=row_height, limit=2)
    )
    primary_upside_zone = summary.upside_acceleration_zones[0] if summary.upside_acceleration_zones else None
    primary_downside_zone = summary.downside_acceleration_zones[0] if summary.downside_acceleration_zones else None
    primary_upside_band = clamp_band(
        _band_bounds_from_zone(primary_upside_zone, y_for=y_for, row_height=row_height)
    )
    primary_downside_band = clamp_band(
        _band_bounds_from_zone(primary_downside_zone, y_for=y_for, row_height=row_height)
    )

    right_callouts: list[dict[str, object]] = []
    left_callouts: list[dict[str, object]] = []
    callout_box_height = 73.0
    if primary_resistance_band is not None:
        right_callouts.append(
            {
                "desired_center": sum(primary_resistance_band) / 2,
                "box_height": callout_box_height,
                "band_top": primary_resistance_band[0],
                "band_bottom": primary_resistance_band[1],
                "lines": ["上方阻力带", band_label(primary_resistance_band_levels), "到位易变慢"],
                "fill": "#fff1f2",
                "stroke": "#d9485f",
                "text_fill": "#8c1d2c",
            }
        )
    if primary_upside_zone is not None and primary_upside_band is not None:
        right_callouts.append(
            {
                "desired_center": sum(primary_upside_band) / 2,
                "box_height": callout_box_height,
                "band_top": primary_upside_band[0],
                "band_bottom": primary_upside_band[1],
                "lines": [
                    "上破加速区",
                    zone_level_line("过", primary_upside_zone.trigger_es, primary_upside_zone.trigger_strike),
                    zone_level_line("先看", primary_upside_zone.target_es, primary_upside_zone.target_strike),
                ],
                "fill": "#fff4e6",
                "stroke": "#f08c00",
                "text_fill": "#9c5b00",
            }
        )
    if primary_support_band is not None:
        left_callouts.append(
            {
                "desired_center": sum(primary_support_band) / 2,
                "box_height": callout_box_height,
                "band_top": primary_support_band[0],
                "band_bottom": primary_support_band[1],
                "lines": ["下方支撑带", band_label(primary_support_band_levels), "到位易承接"],
                "fill": "#ebfbee",
                "stroke": "#2b8a3e",
                "text_fill": "#1f6d31",
            }
        )
    if primary_downside_zone is not None and primary_downside_band is not None:
        left_callouts.append(
            {
                "desired_center": sum(primary_downside_band) / 2,
                "box_height": callout_box_height,
                "band_top": primary_downside_band[0],
                "band_bottom": primary_downside_band[1],
                "lines": [
                    "下破加速区",
                    zone_level_line("破", primary_downside_zone.trigger_es, primary_downside_zone.trigger_strike),
                    zone_level_line("先看", primary_downside_zone.target_es, primary_downside_zone.target_strike),
                ],
                "fill": "#fff5f5",
                "stroke": "#e03131",
                "text_fill": "#9d2121",
            }
        )

    _layout_callouts(left_callouts, top=plot_top + 4, bottom=plot_bottom - 4)
    _layout_callouts(right_callouts, top=plot_top + 4, bottom=plot_bottom - 4)

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="Microsoft YaHei, Segoe UI, Arial, sans-serif">',
        f'<defs><linearGradient id="bg" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#f8fafc"/><stop offset="100%" stop-color="#eef2f7"/></linearGradient></defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)"/>',
        '<text x="60" y="54" font-size="30" font-weight="700" fill="#172033">SPX Gamma 价位图</text>',
        f'<text x="60" y="86" font-size="16" fill="#50607d">{escape(f"SPX {format_price(summary.spx_spot)} | ES {format_price(summary.es_price)} | {summary.regime}")}</text>',
        f'<text x="60" y="112" font-size="14" fill="#6a7892">{escape(f"报价 {summary.quote_time or 'unknown'} | DTE <= {summary.max_dte} | 到期日 {', '.join(summary.included_expirations)}")}</text>',
        '<rect x="60" y="130" width="250" height="30" rx="15" fill="#dbeafe"/>',
        f'<text x="78" y="150" font-size="13" font-weight="700" fill="#1d4ed8">当前价: SPX {escape(format_price(summary.spx_spot))}</text>',
        '<rect x="330" y="130" width="260" height="30" rx="15" fill="#ffedd5"/>',
        f'<text x="348" y="150" font-size="13" font-weight="700" fill="#c2410c">Zero Gamma: ES {escape(format_price(summary.zero_gamma_proxy_es))}</text>',
        '<rect x="610" y="130" width="230" height="30" rx="15" fill="#ede9fe"/>',
        f'<text x="628" y="150" font-size="13" font-weight="700" fill="#6d28d9">净 GEX: {escape(format_compact_dollars(summary.total_net_gex_1pct))}</text>',
        f'<rect x="{main_left}" y="{panel_top}" width="{main_width}" height="{main_height}" rx="24" fill="#ffffff" stroke="#d6deeb"/>',
        f'<rect x="{side_left}" y="{panel_top}" width="{side_width}" height="{side_height}" rx="24" fill="#ffffff" stroke="#d6deeb"/>',
        f'<text x="{main_left + 24}" y="{panel_top + 30}" font-size="14" fill="#5b6780">减速带看反应，破位区看速度。</text>',
        f'<text x="{support_left + 36}" y="{plot_top - 18}" font-size="16" font-weight="700" fill="#18794e">支撑 GEX</text>',
        f'<text x="{ladder_left + 52}" y="{plot_top - 18}" font-size="16" font-weight="700" fill="#1f3b5c">价格梯子</text>',
        f'<text x="{resistance_left + 28}" y="{plot_top - 18}" font-size="16" font-weight="700" fill="#c92a2a">阻力 GEX</text>',
        f'<line x1="{left_callout_right + 12}" y1="{plot_top - 4}" x2="{left_callout_right + 12}" y2="{plot_bottom}" stroke="#eef2f7" stroke-width="1"/>',
        f'<line x1="{right_callout_left - 12}" y1="{plot_top - 4}" x2="{right_callout_left - 12}" y2="{plot_bottom}" stroke="#eef2f7" stroke-width="1"/>',
    ]

    if primary_support_band is not None:
        svg.append(
            f'<rect x="{plot_left}" y="{primary_support_band[0]}" width="{plot_right - plot_left}" height="{primary_support_band[1] - primary_support_band[0]}" fill="#ebfbee" opacity="0.82" rx="18"/>'
        )
        svg.append(
            f'<line x1="{plot_left}" y1="{primary_support_band[0]}" x2="{plot_right}" y2="{primary_support_band[0]}" stroke="#87d6a5" stroke-width="1.5" stroke-dasharray="8 6"/>'
        )
        svg.append(
            f'<line x1="{plot_left}" y1="{primary_support_band[1]}" x2="{plot_right}" y2="{primary_support_band[1]}" stroke="#87d6a5" stroke-width="1.5" stroke-dasharray="8 6"/>'
        )
    if primary_resistance_band is not None:
        svg.append(
            f'<rect x="{plot_left}" y="{primary_resistance_band[0]}" width="{plot_right - plot_left}" height="{primary_resistance_band[1] - primary_resistance_band[0]}" fill="#fff5f5" opacity="0.88" rx="18"/>'
        )
        svg.append(
            f'<line x1="{plot_left}" y1="{primary_resistance_band[0]}" x2="{plot_right}" y2="{primary_resistance_band[0]}" stroke="#ffb3b3" stroke-width="1.5" stroke-dasharray="8 6"/>'
        )
        svg.append(
            f'<line x1="{plot_left}" y1="{primary_resistance_band[1]}" x2="{plot_right}" y2="{primary_resistance_band[1]}" stroke="#ffb3b3" stroke-width="1.5" stroke-dasharray="8 6"/>'
        )
    if primary_upside_band is not None:
        svg.append(
            f'<rect x="{ladder_left - 20}" y="{primary_upside_band[0]}" width="{ladder_width + 40}" height="{primary_upside_band[1] - primary_upside_band[0]}" fill="#fff4e6" opacity="0.82" rx="16" stroke="#f08c00" stroke-width="1.2"/>'
        )
    if primary_downside_band is not None:
        svg.append(
            f'<rect x="{ladder_left - 20}" y="{primary_downside_band[0]}" width="{ladder_width + 40}" height="{primary_downside_band[1] - primary_downside_band[0]}" fill="#fff0f0" opacity="0.84" rx="16" stroke="#e03131" stroke-width="1.2"/>'
        )

    grid_step = max(summary.strike_step * 5, 25.0)
    grid_start = math.floor(plot_min / grid_step) * grid_step
    grid_end = math.ceil(plot_max / grid_step) * grid_step
    tick = grid_start
    while tick <= grid_end + 0.0001:
        y = y_for(tick)
        if plot_top <= y <= plot_bottom:
            es_tick = es_equivalent(tick, summary.spx_spot, summary.es_price)
            svg.append(f'<line x1="{plot_left}" y1="{y}" x2="{plot_right}" y2="{y}" stroke="#edf1f7" stroke-width="1"/>')
            svg.append(
                f'<text x="{support_left - 10}" y="{y + 5}" font-size="12" text-anchor="end" fill="#637188">{escape(format_chart_price(tick))}</text>'
            )
            svg.append(
                f'<text x="{resistance_right + 10}" y="{y + 5}" font-size="12" fill="#637188">{escape(format_chart_price(es_tick))}</text>'
            )
        tick += grid_step

    spot_y = y_for(summary.spx_spot)
    svg.append(f'<line x1="{plot_left}" y1="{spot_y}" x2="{plot_right}" y2="{spot_y}" stroke="#1971c2" stroke-width="3" opacity="0.75"/>')

    if summary.zero_gamma_proxy is not None and plot_min <= summary.zero_gamma_proxy <= plot_max:
        zero_y = y_for(summary.zero_gamma_proxy)
        svg.append(
            f'<line x1="{plot_left}" y1="{zero_y}" x2="{plot_right}" y2="{zero_y}" stroke="#f08c00" stroke-width="2.5" stroke-dasharray="10 8" opacity="0.85"/>'
        )

    svg.append(f'<rect x="{ladder_left}" y="{plot_top + 8}" width="{ladder_width}" height="{plot_height - 16}" rx="18" fill="#f3f7fc" stroke="#d7e0ed"/>')

    for item in display_metrics:
        y = y_for(item.strike)
        support_bar_width = support_width(item.put_gex_1pct)
        resistance_bar_width = resistance_width(item.call_gex_1pct)
        net_color = "#1f9d74" if item.net_gex_1pct > 0 else "#f08c00"
        net_bar_width = net_meter_width(item.net_gex_1pct)
        es_price = es_equivalent(item.strike, summary.spx_spot, summary.es_price)

        svg.append(f'<line x1="{plot_left}" y1="{y}" x2="{plot_right}" y2="{y}" stroke="#eef2f7" stroke-width="1"/>')
        svg.append(
            f'<rect x="{support_right - support_bar_width}" y="{y - row_height / 2}" width="{support_bar_width}" height="{row_height}" fill="#199d76" opacity="0.80" rx="8"/>'
        )
        svg.append(
            f'<rect x="{resistance_left}" y="{y - row_height / 2}" width="{resistance_bar_width}" height="{row_height}" fill="#e64946" opacity="0.80" rx="8"/>'
        )
        svg.append(
            f'<rect x="{ladder_left + 14}" y="{y - row_height / 2}" width="{ladder_width - 28}" height="{row_height}" rx="10" fill="#ffffff" stroke="#d3deea"/>'
        )
        if item.net_gex_1pct != 0:
            svg.append(
                f'<rect x="{ladder_left + 20}" y="{y - row_height / 2 + 4}" width="{net_bar_width}" height="{row_height - 8}" rx="7" fill="{net_color}" opacity="0.18"/>'
            )
        svg.append(
            f'<circle cx="{ladder_left + 30}" cy="{y}" r="4.5" fill="{net_color}" opacity="0.85"/>'
        )
        primary_ladder_value = (
            f"ES {format_chart_price(es_price)}"
            if es_price is not None
            else f"SPX {format_chart_price(item.strike)}"
        )
        secondary_ladder_value = (
            f"SPX {format_chart_price(item.strike)}"
            if es_price is not None
            else ""
        )
        svg.append(
            f'<text x="{ladder_left + ladder_width / 2}" y="{y - 1}" font-size="14" font-weight="700" text-anchor="middle" fill="#172033">{escape(primary_ladder_value)}</text>'
        )
        if secondary_ladder_value:
            svg.append(
                f'<text x="{ladder_left + ladder_width / 2}" y="{y + 13}" font-size="11" text-anchor="middle" fill="#66768f">{escape(secondary_ladder_value)}</text>'
            )

    for callout in left_callouts:
        _append_svg_callout(
            svg,
            side="left",
            box_left=left_callout_left,
            box_width=left_callout_width,
            bracket_x=left_callout_right + 10,
            band_top=float(callout["band_top"]),
            band_bottom=float(callout["band_bottom"]),
            box_top=float(callout["box_top"]),
            lines=list(callout["lines"]),
            fill=str(callout["fill"]),
            stroke=str(callout["stroke"]),
            text_fill=str(callout["text_fill"]),
        )

    for callout in right_callouts:
        _append_svg_callout(
            svg,
            side="right",
            box_left=right_callout_left,
            box_width=right_callout_width,
            bracket_x=right_callout_left - 10,
            band_top=float(callout["band_top"]),
            band_bottom=float(callout["band_bottom"]),
            box_top=float(callout["box_top"]),
            lines=list(callout["lines"]),
            fill=str(callout["fill"]),
            stroke=str(callout["stroke"]),
            text_fill=str(callout["text_fill"]),
        )

    side_y = panel_top + 36
    svg.append(f'<text x="{side_left + 28}" y="{side_y}" font-size="24" font-weight="700" fill="#172033">交易提醒</text>')
    side_y += 28
    svg.append(f'<text x="{side_left + 28}" y="{side_y}" font-size="14" fill="#5b6780">主图看结构，右侧看结论。</text>')
    side_y += 32

    svg.append(f'<text x="{side_left + 28}" y="{side_y}" font-size="18" font-weight="700" fill="#172033">核心结论</text>')
    side_y += 26
    side_y = _append_svg_text_lines(
        svg,
        x=side_left + 28,
        y=side_y,
        lines=quick_lines,
        font_size=15,
        line_height=22,
        fill="#24334d",
        font_weight="500",
    )

    side_y += 12
    svg.append(
        f'<rect x="{side_left + 20}" y="{side_y}" width="{side_width - 40}" height="1" fill="#e6ebf2"/>'
    )
    side_y += 28

    if ai_result and ai_wrapped_lines:
        svg.append(f'<text x="{side_left + 28}" y="{side_y}" font-size="18" font-weight="700" fill="#172033">AI 盘面解读</text>')
        svg.append(
            f'<text x="{side_left + side_width - 26}" y="{side_y}" font-size="12" text-anchor="end" fill="#7b8798">{escape(ai_result.provider)} / {escape(ai_result.model)}</text>'
        )
        side_y += 28
        ai_box_height = max(128, len(ai_wrapped_lines) * 22 + 22)
        svg.append(
            f'<rect x="{side_left + 20}" y="{side_y - 18}" width="{side_width - 40}" height="{ai_box_height}" rx="16" fill="#f8fafc" stroke="#d8e0ec"/>'
        )
        _append_svg_text_lines(
            svg,
            x=side_left + 36,
            y=side_y + 10,
            lines=ai_wrapped_lines,
            font_size=15,
            line_height=22,
            fill="#24334d",
            font_weight="400",
        )

    svg.append("</svg>")
    return "\n".join(svg)


def _sanitize_stem(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-") or "spx_gamma_map"


def _history_timestamp(summary: GammaMapSummary) -> str:
    if summary.quote_time:
        token = re.sub(r"[^0-9]", "", summary.quote_time)
        if token:
            return token[:14]
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _load_latest_history_summary(output_dir: Path, *, stem: str) -> dict[str, object] | None:
    history_dir = output_dir / "history"
    if not history_dir.exists():
        return None

    for candidate in sorted(history_dir.glob(f"{stem}_*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _write_history_snapshot(summary: GammaMapSummary, output_dir: Path, *, stem: str) -> Path:
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"{stem}_{_history_timestamp(summary)}.json"
    history_path.write_text(json.dumps(summary.to_jsonable(), indent=2), encoding="utf-8")
    return history_path


def write_artifacts(summary: GammaMapSummary, output_dir: Path, *, stem: str) -> GeneratedArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"{stem}_gamma_map.svg"
    json_path = output_dir / f"{stem}_gamma_map.json"
    report_path = output_dir / f"{stem}_gamma_map.txt"
    history_json_path = _write_history_snapshot(summary, output_dir, stem=stem)

    svg_path.write_text(render_svg(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary.to_jsonable(), indent=2), encoding="utf-8")
    report_path.write_text(render_text_report(summary), encoding="utf-8")
    return GeneratedArtifacts(
        summary=summary,
        svg_path=svg_path,
        json_path=json_path,
        report_path=report_path,
        history_json_path=history_json_path,
    )


def write_ai_analysis_artifact(artifacts: GeneratedArtifacts, ai_result: AiAnalysisResult) -> Path:
    ai_path = artifacts.report_path.with_name(artifacts.report_path.stem.replace("_gamma_map", "_gamma_map_ai") + ".md")
    ai_text = "\n".join(
        [
            f"# AI 期权解读",
            "",
            f"- Provider: `{ai_result.provider}`",
            f"- Model: `{ai_result.model}`",
            f"- Source: `{artifacts.summary.source_file}`",
            "",
            ai_result.content,
            "",
            "## 结构化文件",
            f"- SVG: `{artifacts.svg_path}`",
            f"- JSON: `{artifacts.json_path}`",
            f"- Report: `{artifacts.report_path}`",
            f"- History Snapshot: `{artifacts.history_json_path}`" if artifacts.history_json_path else "",
        ]
    )
    ai_path.write_text(ai_text, encoding="utf-8")
    artifacts.svg_path.write_text(render_svg_with_ai(artifacts.summary, ai_result), encoding="utf-8")
    artifacts.ai_report_path = ai_path
    return ai_path


def generate_gamma_map_artifacts(
    csv_path: Path,
    output_dir: Path,
    *,
    es_price: float | None = None,
    max_dte: int = 7,
    top_n: int = 3,
    min_open_interest: int = 1,
) -> GeneratedArtifacts:
    stem = _sanitize_stem(csv_path)
    previous_summary = _load_latest_history_summary(output_dir, stem=stem)
    summary = analyze_spx_gamma_csv(
        csv_path,
        es_price=es_price,
        max_dte=max_dte,
        top_n=top_n,
        min_open_interest=min_open_interest,
    )
    summary.tracking_delta = build_tracking_delta(summary, previous_summary)
    return write_artifacts(summary, output_dir, stem=stem)
