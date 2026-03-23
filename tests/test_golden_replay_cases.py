from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from atas_market_structure.golden_cases import iter_cases, load_case_sets
from atas_market_structure.rebuild_runner import ReplayRebuildRunner


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "samples" / "golden_cases"
CASE_SETS = load_case_sets(GOLDEN_ROOT)
CASES = iter_cases(GOLDEN_ROOT)


def test_golden_case_inventory_covers_required_event_and_degraded_scenarios() -> None:
    counts = Counter(case.scenario for case in CASES)

    assert counts["momentum_continuation"] >= 3
    assert counts["balance_mean_reversion"] >= 3
    assert counts["absorption_to_reversal_preparation"] >= 3
    assert sum(
        counts[name]
        for name in counts
        if name not in {
            "momentum_continuation",
            "balance_mean_reversion",
            "absorption_to_reversal_preparation",
        }
    ) >= 3
    assert sum(len(case_set.cases) for case_set in CASE_SETS) >= 12


@pytest.mark.parametrize("case", CASES, ids=[case.case_id for case in CASES])
def test_golden_case_replay_matches_declared_expectations(case, tmp_path: Path) -> None:
    runner = ReplayRebuildRunner()
    output_database = tmp_path / "rebuild" / f"{case.case_id}.db"

    report = runner.run_case(case=case, output_database_path=output_database)
    errors = runner.validate_case_report(case=case, report=report)

    assert errors == []
    assert report.ai_in_critical_path is False
    if report.evaluation_count:
        assert report.evaluation_schema_versions == ["episode_evaluation_v1"]
