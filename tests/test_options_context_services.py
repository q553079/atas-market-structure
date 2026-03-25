from __future__ import annotations

from pathlib import Path

from atas_market_structure.options_context_services import (
    analyze_options_strategy_context,
    render_options_strategy_context_report,
    write_options_strategy_context_artifacts,
)
from atas_market_structure.spx_gamma_map import generate_gamma_map_artifacts
from tests.test_spx_gamma_map import _write_sample_csv, _write_shifted_sample_csv


def test_options_strategy_context_produces_scores_candidates_and_artifacts(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"
    _write_sample_csv(csv_path)

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5042.0,
        max_dte=30,
        top_n=2,
    )
    context = analyze_options_strategy_context(
        artifacts.summary,
        history_dir=output_dir / "history",
        exclude_history_path=artifacts.history_json_path,
    )

    assert context.environment_label in {
        "range_harvest",
        "breakout_pressure",
        "downside_hedge_demand",
        "upside_chase",
    }
    assert 0 <= context.range_harvest_score <= 100
    assert 0 <= context.short_vol_friendliness <= 100
    assert context.strategy_candidates
    report = render_options_strategy_context_report(context)
    assert "环境标签:" in report
    assert "更匹配的策略环境:" in report

    written = write_options_strategy_context_artifacts(context, output_dir, stem=csv_path.stem)
    assert written.json_path.exists()
    assert written.report_path.exists()


def test_options_strategy_context_reads_previous_history_for_context(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"
    _write_sample_csv(csv_path)
    generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5042.0,
        max_dte=30,
        top_n=2,
    )

    _write_shifted_sample_csv(csv_path)
    second = generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5051.0,
        max_dte=30,
        top_n=2,
    )

    context = analyze_options_strategy_context(
        second.summary,
        history_dir=output_dir / "history",
        exclude_history_path=second.history_json_path,
    )

    assert context.context_window_count >= 1
    assert context.recent_history
    assert context.recent_history[0].quote_time == "2026-03-19 10:30:00"
    assert context.context_signals
