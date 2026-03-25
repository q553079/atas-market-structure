from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
import re

from atas_market_structure.config import AppConfig, PROJECT_ROOT
from atas_market_structure.options_context_services import (
    OptionsStrategyContext,
    OptionsStrategyContextArtifacts,
    analyze_options_strategy_context,
    write_options_strategy_context_artifacts,
)
from atas_market_structure.options_report_services import (
    OptionsMarkdownReportArtifacts,
    generate_ai_options_markdown_report,
    write_options_markdown_report,
)
from atas_market_structure.spx_gamma_map import (
    GeneratedArtifacts,
    generate_gamma_map_artifacts,
    load_options_csv,
    render_text_report,
)


DEFAULT_OPTIONS_DOWNLOADS_DIR = Path.home() / "Downloads"
DEFAULT_OPTIONS_DATA_ROOT = PROJECT_ROOT / "data"
DEFAULT_OPTIONS_MARKET = "s&p500_options"
DEFAULT_OPTIONS_SYMBOL = "spx"
DEFAULT_OPTIONS_GLOB = "*quotedata*.csv"
QUOTE_TIMESTAMP_PATTERN = re.compile(
    r"Date:\s*(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s+"
    r"GMT(?P<offset_sign>[+-])(?P<offset_hour>\d{1,2})(?::?(?P<offset_minute>\d{2}))?\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    source: Path
    destination: Path
    moved: bool

    @property
    def action(self) -> str:
        return "move" if self.moved else "copy"


@dataclass(slots=True)
class AutomatedOptionsAnalysisResult:
    archive: ArchiveResult
    archive_day: date
    dry_run: bool
    text_report: str | None = None
    artifacts: GeneratedArtifacts | None = None
    strategy_context: OptionsStrategyContext | None = None
    strategy_context_artifacts: OptionsStrategyContextArtifacts | None = None
    markdown_report_artifacts: OptionsMarkdownReportArtifacts | None = None
    ai_interpretation: str | None = None
    ai_analysis_error: str | None = None


def parse_archive_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid archive date '{raw}'. Expected YYYY-MM-DD.") from exc


def pick_latest_candidate(
    source_dir: Path,
    pattern: str,
    symbol: str,
    *,
    require_parseable: bool = False,
) -> Path:
    resolved_source_dir = source_dir.expanduser().resolve()
    if not resolved_source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {resolved_source_dir}")

    candidates = sorted(
        [
            path.resolve()
            for path in resolved_source_dir.glob(pattern)
            if path.is_file() and symbol.lower() in path.name.lower()
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            f"No CSV candidates found in {resolved_source_dir} matching pattern '{pattern}' and symbol '{symbol}'."
        )

    if not require_parseable:
        return candidates[0]

    for candidate in candidates:
        try:
            spot, _, rows = load_options_csv(candidate)
        except Exception:
            continue
        if spot is not None and rows:
            return candidate

    raise FileNotFoundError(
        f"No parseable options CSV found in {resolved_source_dir} matching pattern '{pattern}' and symbol '{symbol}'."
    )


def _resolve_archive_bucket_start_utc(source: Path) -> datetime:
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            for _ in range(3):
                line = handle.readline()
                if not line:
                    break
                match = QUOTE_TIMESTAMP_PATTERN.search(line)
                if match is None:
                    continue
                offset = timedelta(
                    hours=int(match.group("offset_hour")),
                    minutes=int(match.group("offset_minute") or "0"),
                )
                if match.group("offset_sign") == "-":
                    offset = -offset
                quote_dt = datetime(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                    int(match.group("hour")),
                    int(match.group("minute")),
                    tzinfo=timezone(offset),
                )
                return quote_dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    except OSError:
        pass

    fallback = datetime.fromtimestamp(source.stat().st_mtime, tz=UTC)
    return fallback.replace(minute=0, second=0, microsecond=0)


def build_destination(data_root: Path, market: str, archive_day: date, symbol: str, *, source: Path) -> Path:
    year_dir = archive_day.strftime("%Y")
    date_dir = archive_day.isoformat()
    bucket_start_utc = _resolve_archive_bucket_start_utc(source)
    hour_token = bucket_start_utc.strftime("%H00Z")
    filename = f"^{symbol.lower()}_quotedata_{archive_day.strftime('%Y%m%d')}_{hour_token}.csv"
    return data_root.expanduser().resolve() / market / year_dir / date_dir / filename


def archive_file(source: Path, destination: Path, *, copy_only: bool, dry_run: bool) -> ArchiveResult:
    resolved_source = source.expanduser().resolve()
    resolved_destination = destination.expanduser().resolve()

    if dry_run:
        return ArchiveResult(source=resolved_source, destination=resolved_destination, moved=not copy_only)

    if resolved_source == resolved_destination:
        return ArchiveResult(source=resolved_source, destination=resolved_destination, moved=False)

    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    if resolved_destination.exists():
        resolved_destination.unlink()

    if copy_only:
        shutil.copy2(resolved_source, resolved_destination)
        moved = False
    else:
        shutil.move(str(resolved_source), str(resolved_destination))
        moved = True

    return ArchiveResult(source=resolved_source, destination=resolved_destination, moved=moved)


def archive_latest_options_csv(
    *,
    source_dir: Path = DEFAULT_OPTIONS_DOWNLOADS_DIR,
    data_root: Path = DEFAULT_OPTIONS_DATA_ROOT,
    market: str = DEFAULT_OPTIONS_MARKET,
    symbol: str = DEFAULT_OPTIONS_SYMBOL,
    archive_day: date,
    pattern: str = DEFAULT_OPTIONS_GLOB,
    copy_only: bool = False,
    dry_run: bool = False,
    require_parseable: bool = False,
) -> ArchiveResult:
    source = pick_latest_candidate(source_dir, pattern, symbol, require_parseable=require_parseable)
    destination = build_destination(data_root, market, archive_day, symbol, source=source)
    return archive_file(source, destination, copy_only=copy_only, dry_run=dry_run)


def archive_and_analyze_options(
    *,
    source_dir: Path = DEFAULT_OPTIONS_DOWNLOADS_DIR,
    data_root: Path = DEFAULT_OPTIONS_DATA_ROOT,
    market: str = DEFAULT_OPTIONS_MARKET,
    symbol: str = DEFAULT_OPTIONS_SYMBOL,
    archive_day: date,
    pattern: str = DEFAULT_OPTIONS_GLOB,
    copy_only: bool = False,
    dry_run: bool = False,
    artifact_output_dir: Path | None = None,
    es_price: float | None = None,
    max_dte: int = 7,
    top_n: int = 3,
    min_open_interest: int = 1,
    include_ai_analysis: bool = False,
    config: AppConfig | None = None,
    ai_question: str | None = None,
) -> AutomatedOptionsAnalysisResult:
    archive = archive_latest_options_csv(
        source_dir=source_dir,
        data_root=data_root,
        market=market,
        symbol=symbol,
        archive_day=archive_day,
        pattern=pattern,
        copy_only=copy_only,
        dry_run=dry_run,
        require_parseable=True,
    )
    if dry_run:
        return AutomatedOptionsAnalysisResult(
            archive=archive,
            archive_day=archive_day,
            dry_run=True,
        )

    output_dir = (
        artifact_output_dir.expanduser().resolve()
        if artifact_output_dir is not None
        else archive.destination.parent / "gamma_artifacts"
    )
    artifacts = generate_gamma_map_artifacts(
        archive.destination,
        output_dir,
        es_price=es_price,
        max_dte=max_dte,
        top_n=top_n,
        min_open_interest=min_open_interest,
    )
    text_report = render_text_report(artifacts.summary)
    strategy_context = analyze_options_strategy_context(
        artifacts.summary,
        history_dir=output_dir / "history",
        exclude_history_path=artifacts.history_json_path,
    )
    strategy_context_artifacts = write_options_strategy_context_artifacts(
        strategy_context,
        output_dir,
        stem=archive.destination.stem,
    )

    ai_interpretation: str | None = None
    ai_analysis_error: str | None = None
    ai_report = None
    if include_ai_analysis:
        runtime_config = config or AppConfig.from_env()
        try:
            ai_report = generate_ai_options_markdown_report(
                artifacts.summary,
                strategy_context,
                config=runtime_config,
                question=ai_question,
            )
        except Exception as exc:
            ai_analysis_error = str(exc)
        else:
            ai_interpretation = ai_report.content

    markdown_report_artifacts = write_options_markdown_report(
        artifacts.summary,
        strategy_context,
        artifacts,
        strategy_context_artifacts=strategy_context_artifacts,
        ai_report=ai_report,
    )
    if ai_report is not None:
        artifacts.ai_report_path = markdown_report_artifacts.report_path

    return AutomatedOptionsAnalysisResult(
        archive=archive,
        archive_day=archive_day,
        dry_run=False,
        text_report=text_report,
        artifacts=artifacts,
        strategy_context=strategy_context,
        strategy_context_artifacts=strategy_context_artifacts,
        markdown_report_artifacts=markdown_report_artifacts,
        ai_interpretation=ai_interpretation,
        ai_analysis_error=ai_analysis_error,
    )
