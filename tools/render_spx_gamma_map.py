from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.spx_gamma_map import (
    DEFAULT_CSV_PATTERNS,
    discover_latest_options_csv,
    generate_ai_options_analysis,
    generate_gamma_map_artifacts,
    load_powershell_env_file,
    render_text_report,
    write_ai_analysis_artifact,
)
from atas_market_structure.config import AppConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render a gamma price map from a downloaded SPX options CSV. "
            "Outputs a text report, JSON summary, and SVG chart."
        )
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=None,
        help="Path to the ^SPX CSV downloaded from the options dashboard. If omitted, the tool scans for the latest file.",
    )
    parser.add_argument(
        "--scan-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory to scan for the latest SPX CSV when --csv is omitted.",
    )
    parser.add_argument(
        "--scan-pattern",
        action="append",
        default=None,
        help="Additional glob pattern used when scanning for the latest CSV. Can be passed multiple times.",
    )
    parser.add_argument(
        "--scan-recursive",
        action="store_true",
        help="Scan the directory recursively when auto-discovering the latest CSV.",
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
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "spx-gamma-map",
        help="Directory where the report, JSON, and SVG will be written.",
    )
    parser.add_argument(
        "--ai-analysis",
        action="store_true",
        help="Use the project's AI configuration to generate a Chinese market readout from the gamma map.",
    )
    parser.add_argument(
        "--ai-env-ps1",
        type=Path,
        default=REPO_ROOT / ".env.local.ps1",
        help="Optional PowerShell env file to load before building AppConfig for AI analysis.",
    )
    parser.add_argument(
        "--ai-question",
        type=str,
        default=None,
        help="Optional custom Chinese prompt for the AI analysis.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    patterns = tuple(args.scan_pattern) if args.scan_pattern else DEFAULT_CSV_PATTERNS
    if args.csv_path is not None:
        csv_path = args.csv_path.expanduser().resolve()
    else:
        csv_path = discover_latest_options_csv(
            args.scan_dir.expanduser().resolve(),
            patterns=patterns,
            recursive=args.scan_recursive,
        )

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        args.output_dir.expanduser().resolve(),
        es_price=args.es_price,
        max_dte=args.max_dte,
        top_n=args.top_n,
        min_open_interest=args.min_open_interest,
    )
    print(f"Using CSV: {csv_path}")
    print(render_text_report(artifacts.summary))
    if args.ai_analysis:
        load_powershell_env_file(args.ai_env_ps1.expanduser().resolve())
        config = AppConfig.from_env()
        ai_result = generate_ai_options_analysis(
            artifacts.summary,
            config=config,
            question=args.ai_question,
        )
        ai_path = write_ai_analysis_artifact(artifacts, ai_result)
        print()
        print("AI 解读:")
        print(ai_result.content)
        print()
        print(f"AI report: {ai_path}")
    print()
    print(f"SVG chart: {artifacts.svg_path}")
    print(f"JSON summary: {artifacts.json_path}")
    print(f"Text report: {artifacts.report_path}")
    if artifacts.history_json_path is not None:
        print(f"History snapshot: {artifacts.history_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
