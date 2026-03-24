from __future__ import annotations

from pathlib import Path

from atas_market_structure.sample_validation import SampleValidationService


ROOT = Path(__file__).resolve().parents[1]


def test_repository_samples_and_golden_cases_validate_cleanly() -> None:
    report = SampleValidationService().validate(ROOT / "samples")

    assert report.failure_count == 0
    assert report.validated_file_count >= 41
    assert report.validated_case_count >= 50
