from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atas_market_structure.golden_cases import iter_cases
from atas_market_structure.config import AppConfig
from atas_market_structure.rebuild_runner import ReplayRebuildRunner
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository, HybridAnalysisRepository


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    runner = ReplayRebuildRunner()
    reports: list[dict[str, object]] = []
    if args.golden_cases:
        case_path = Path(args.golden_cases)
        cases = iter_cases(case_path)
        if args.case_id:
            cases = [case for case in cases if case.case_id == args.case_id]
        if not cases:
            raise SystemExit("no golden replay cases matched the requested selector")
        output_dir = Path(args.output_db).parent if args.output_db else ROOT / "data" / "rebuild"
        output_dir.mkdir(parents=True, exist_ok=True)
        for case in cases:
            output_db = Path(args.output_db) if args.output_db and len(cases) == 1 else output_dir / f"{case.case_id}.db"
            _prepare_output(output_db, overwrite=args.overwrite)
            report = runner.run_case(case=case, output_database_path=output_db)
            reports.append(report.model_dump(mode="json"))
    else:
        if not args.instrument:
            raise SystemExit("--instrument is required for repository replay mode")
        if args.source_clickhouse and args.source_db:
            raise SystemExit("use either --source-db or --source-clickhouse, not both")
        if not args.source_clickhouse and not args.source_db:
            raise SystemExit("repository replay mode requires --source-db or --source-clickhouse")
        output_db = Path(args.output_db) if args.output_db else ROOT / "data" / "rebuild" / _default_output_name(args.instrument)
        _prepare_output(output_db, overwrite=args.overwrite)
        if args.source_clickhouse:
            source_repository, source_label = _build_clickhouse_source_repository(args)
            report = runner.run_repository_rebuild(
                source_repository=source_repository,
                source_label=source_label,
                output_database_path=output_db,
                instrument_symbol=args.instrument,
                ai_available=args.ai_available,
                session_date=args.session_date,
                window_start=_parse_optional_datetime(args.window_start),
                window_end=_parse_optional_datetime(args.window_end),
                page_size=args.page_size,
            )
        else:
            assert args.source_db is not None
            report = runner.run_repository_rebuild(
                source_database_path=Path(args.source_db),
                output_database_path=output_db,
                instrument_symbol=args.instrument,
                ai_available=args.ai_available,
                session_date=args.session_date,
                window_start=_parse_optional_datetime(args.window_start),
                window_end=_parse_optional_datetime(args.window_end),
                page_size=args.page_size,
            )
        reports.append(report.model_dump(mode="json"))

    payload: object = reports[0] if len(reports) == 1 else reports
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay append-only raw ingestions into a fresh SQLite analysis database.")
    parser.add_argument("--golden-cases", help="Golden case file or directory to replay.")
    parser.add_argument("--case-id", help="Optional single case selector when --golden-cases targets a file or directory.")
    parser.add_argument("--source-db", help="Existing SQLite database to replay from.")
    parser.add_argument("--source-clickhouse", action="store_true", help="Read raw ingestions from ClickHouse using the configured hybrid source.")
    parser.add_argument("--metadata-db", help="SQLite metadata database used with --source-clickhouse for active profile/build lookup.")
    parser.add_argument("--instrument", help="Instrument symbol for repository replay mode.")
    parser.add_argument("--session-date", help="Optional YYYY-MM-DD filter for repository replay mode.")
    parser.add_argument("--window-start", help="Optional ISO timestamp lower bound for repository replay mode.")
    parser.add_argument("--window-end", help="Optional ISO timestamp upper bound for repository replay mode.")
    parser.add_argument("--page-size", type=int, default=5000, help="Source page size for repository replay scans.")
    parser.add_argument("--ai-available", action="store_true", help="Mark AI as available during repository replay.")
    parser.add_argument("--output-db", help="Target SQLite database path.")
    parser.add_argument("--output-json", help="Optional JSON report file.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing target database or report file.")
    return parser


def _default_output_name(instrument: str) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{instrument.lower()}-{timestamp}.db"


def _prepare_output(path: Path, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return
    if not overwrite:
        raise SystemExit(f"target already exists: {path}; rerun with --overwrite to replace it")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        candidate.unlink(missing_ok=True)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _build_clickhouse_source_repository(args: argparse.Namespace) -> tuple[HybridAnalysisRepository, str]:
    config = AppConfig.from_env()
    metadata_database_path = Path(args.metadata_db) if args.metadata_db else config.database_path
    metadata_repository = SQLiteAnalysisRepository(database_path=metadata_database_path)
    clickhouse_repository = ClickHouseChartCandleRepository(
        host=config.clickhouse_host,
        port=config.clickhouse_port,
        username=config.clickhouse_user,
        password=config.clickhouse_password,
        database=config.clickhouse_database,
        table=config.clickhouse_chart_candles_table,
        workspace_root=metadata_repository.workspace_root,
        ingestions_table=config.clickhouse_ingestions_table,
        connect_retries=config.clickhouse_connect_retries,
        retry_delay_seconds=config.clickhouse_retry_delay_seconds,
    )
    return (
        HybridAnalysisRepository(
            metadata_repository=metadata_repository,
            chart_candle_repository=clickhouse_repository,
            ingestion_repository=clickhouse_repository,
        ),
        (
            f"clickhouse://{config.clickhouse_host}:{config.clickhouse_port}/"
            f"{config.clickhouse_database}.{config.clickhouse_ingestions_table}"
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
