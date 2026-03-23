from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atas_market_structure.sample_validation import SampleValidationService


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repository sample payloads and golden replay case specs.")
    parser.add_argument(
        "--samples-root",
        default=str(ROOT / "samples"),
        help="Sample root directory to validate. Defaults to ./samples.",
    )
    parser.add_argument("--output-json", help="Optional file path for the JSON validation report.")
    args = parser.parse_args()

    report = SampleValidationService().validate(Path(args.samples_root))
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
