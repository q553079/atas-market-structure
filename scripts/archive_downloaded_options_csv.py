from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.config import AppConfig
from atas_market_structure.options_automation_services import (
    DEFAULT_OPTIONS_DATA_ROOT,
    DEFAULT_OPTIONS_DOWNLOADS_DIR,
    archive_and_analyze_options,
    archive_latest_options_csv,
    parse_archive_date,
)
from atas_market_structure.spx_gamma_map import load_powershell_env_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive the latest downloaded options quote CSV and optionally run automated gamma analysis.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_OPTIONS_DOWNLOADS_DIR,
        help=f"Directory containing downloaded CSV files (default: {DEFAULT_OPTIONS_DOWNLOADS_DIR})",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_OPTIONS_DATA_ROOT,
        help=f"Project data root directory (default: {DEFAULT_OPTIONS_DATA_ROOT})",
    )
    parser.add_argument(
        "--market",
        default="s&p500_options",
        help="Market subdirectory under data root (default: s&p500_options)",
    )
    parser.add_argument(
        "--symbol",
        default="spx",
        help="Symbol stem used for archive filename matching/output naming (default: spx)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Archive date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--glob",
        default="*quotedata*.csv",
        help="Glob pattern used to find candidate CSV files (default: *quotedata*.csv)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy the file instead of moving it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without moving/copying the file.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run automated SPX gamma analysis after archiving the latest file.",
    )
    parser.add_argument(
        "--artifact-output-dir",
        type=Path,
        default=None,
        help="Optional output directory for gamma analysis artifacts. Defaults to <archive day dir>/gamma_artifacts.",
    )
    parser.add_argument(
        "--es-price",
        type=float,
        default=None,
        help="Current ES futures price used to map SPX strikes into ES levels.",
    )
    parser.add_argument(
        "--max-dte",
        type=int,
        default=7,
        help="Only include expirations up to this many days to expiry.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Number of support and resistance levels to surface.",
    )
    parser.add_argument(
        "--min-open-interest",
        type=int,
        default=1,
        help="Ignore options below this open-interest threshold.",
    )
    parser.add_argument(
        "--ai-analysis",
        action="store_true",
        help="Generate optional AI market readout after gamma analysis.",
    )
    parser.add_argument(
        "--ai-env-ps1",
        type=Path,
        default=ROOT_DIR / ".env.local.ps1",
        help="Optional PowerShell env file to load before AI analysis.",
    )
    parser.add_argument(
        "--ai-question",
        type=str,
        default=None,
        help="Optional custom Chinese prompt for the AI analysis.",
    )
    return parser.parse_args()


def _print_archive_result(*, source: Path, destination: Path, action: str, dry_run: bool) -> None:
    print(f"source={source}")
    print(f"destination={destination}")
    print(f"action={action}")
    print(f"dry_run={dry_run}")
    print(f"destination_exists={destination.exists()}")
    if destination.exists():
        print(f"destination_size={destination.stat().st_size}")


def main() -> int:
    try:
        args = parse_args()
        archive_day: date = parse_archive_date(args.date)

        if args.analyze:
            if args.ai_analysis:
                load_powershell_env_file(args.ai_env_ps1.expanduser().resolve())
            result = archive_and_analyze_options(
                source_dir=args.source_dir,
                data_root=args.data_root,
                market=args.market,
                symbol=args.symbol,
                archive_day=archive_day,
                pattern=args.glob,
                copy_only=args.copy,
                dry_run=args.dry_run,
                artifact_output_dir=args.artifact_output_dir,
                es_price=args.es_price,
                max_dte=args.max_dte,
                top_n=args.top_n,
                min_open_interest=args.min_open_interest,
                include_ai_analysis=args.ai_analysis,
                config=AppConfig.from_env() if args.ai_analysis else None,
                ai_question=args.ai_question,
            )
            _print_archive_result(
                source=result.archive.source,
                destination=result.archive.destination,
                action=result.archive.action,
                dry_run=result.dry_run,
            )
            if result.dry_run:
                return 0

            if result.text_report:
                print()
                print(result.text_report)
            if result.strategy_context is not None:
                print()
                print("策略环境:")
                print(f"environment_label={result.strategy_context.environment_label}")
                print(f"range_harvest_score={result.strategy_context.range_harvest_score}")
                print(f"breakout_pressure_score={result.strategy_context.breakout_pressure_score}")
                print(f"downside_hedge_demand_score={result.strategy_context.downside_hedge_demand_score}")
                print(f"upside_chase_score={result.strategy_context.upside_chase_score}")
                if result.strategy_context.strategy_candidates:
                    print(
                        "top_strategy_environment="
                        f"{result.strategy_context.strategy_candidates[0].strategy_id}"
                    )
            if result.ai_analysis_error:
                print()
                print(f"ai_analysis_error={result.ai_analysis_error}")
            if result.artifacts is not None:
                print()
                print(f"svg_path={result.artifacts.svg_path}")
                print(f"json_path={result.artifacts.json_path}")
                print(f"report_path={result.artifacts.report_path}")
                if result.strategy_context_artifacts is not None:
                    print(f"strategy_context_json_path={result.strategy_context_artifacts.json_path}")
                    print(f"strategy_context_report_path={result.strategy_context_artifacts.report_path}")
                if result.artifacts.history_json_path is not None:
                    print(f"history_json_path={result.artifacts.history_json_path}")
                if result.artifacts.ai_report_path is not None:
                    print(f"ai_report_path={result.artifacts.ai_report_path}")
                if result.markdown_report_artifacts is not None:
                    print(f"markdown_report_path={result.markdown_report_artifacts.report_path}")
                    if result.markdown_report_artifacts.prompt_path is not None:
                        print(f"markdown_prompt_path={result.markdown_report_artifacts.prompt_path}")
            return 0

        result = archive_latest_options_csv(
            source_dir=args.source_dir,
            data_root=args.data_root,
            market=args.market,
            symbol=args.symbol,
            archive_day=archive_day,
            pattern=args.glob,
            copy_only=args.copy,
            dry_run=args.dry_run,
        )
        _print_archive_result(
            source=result.source,
            destination=result.destination,
            action=result.action,
            dry_run=args.dry_run,
        )
        return 0
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
