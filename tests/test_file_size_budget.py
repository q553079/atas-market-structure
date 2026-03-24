from __future__ import annotations

from pathlib import Path

from scripts.check_file_size_budget import format_report, iter_budget_entries


def test_python_file_size_budget_has_no_hard_violations() -> None:
    root = Path(__file__).resolve().parents[1]
    entries = iter_budget_entries(root)
    hard_violations = [entry for entry in entries if entry.status == "hard_violation"]
    assert not hard_violations, format_report(hard_violations)
