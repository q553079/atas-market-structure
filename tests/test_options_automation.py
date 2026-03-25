from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from atas_market_structure.options_report_services import OptionsAiReportResult
from atas_market_structure.options_automation_services import (
    archive_and_analyze_options,
    archive_latest_options_csv,
    parse_archive_date,
)
from tests.test_spx_gamma_map import _write_sample_csv


def test_archive_latest_options_csv_moves_latest_symbol_match_to_dated_destination(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    older = source_dir / "^spx_quotedata_older.csv"
    newer = source_dir / "^spx_quotedata_newer.csv"
    ignored = source_dir / "^qqq_quotedata_newer.csv"
    _write_sample_csv(older)
    _write_sample_csv(newer)
    ignored.write_text("ignored", encoding="utf-8")
    os.utime(older, (1_000, 1_000))
    os.utime(newer, (2_000, 2_000))
    os.utime(ignored, (3_000, 3_000))

    result = archive_latest_options_csv(
        source_dir=source_dir,
        data_root=data_root,
        market="s&p500_options",
        symbol="spx",
        archive_day=date(2026, 3, 25),
        pattern="*quotedata*.csv",
    )

    expected_destination = (
        data_root / "s&p500_options" / "2026" / "2026-03-25" / "^spx_quotedata_20260325_1400Z.csv"
    ).resolve()
    assert result.source == newer.resolve()
    assert result.destination == expected_destination
    assert result.moved is True
    assert not newer.exists()
    assert "S&P 500 INDEX" in result.destination.read_text(encoding="utf-8")


def test_archive_and_analyze_options_writes_gamma_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    result = archive_and_analyze_options(
        source_dir=source_dir,
        data_root=data_root,
        archive_day=date(2026, 3, 19),
        copy_only=True,
        es_price=5042.0,
        max_dte=1,
        top_n=2,
    )

    assert result.dry_run is False
    assert result.archive.moved is False
    assert result.archive.destination.exists()
    assert result.archive.destination.name == "^spx_quotedata_20260319_1400Z.csv"
    assert csv_path.exists()
    assert result.artifacts is not None
    assert result.strategy_context is not None
    assert result.strategy_context_artifacts is not None
    assert result.artifacts.svg_path.exists()
    assert result.artifacts.json_path.exists()
    assert result.artifacts.report_path.exists()
    assert result.artifacts.history_json_path is not None
    assert result.artifacts.history_json_path.exists()
    assert result.strategy_context_artifacts.json_path.exists()
    assert result.strategy_context_artifacts.report_path.exists()
    assert result.markdown_report_artifacts is not None
    assert result.markdown_report_artifacts.report_path.exists()
    assert result.text_report is not None
    assert "Gap&Chop 结构分数:" in result.text_report
    assert result.strategy_context.strategy_candidates


def test_archive_and_analyze_options_dry_run_skips_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    result = archive_and_analyze_options(
        source_dir=source_dir,
        data_root=data_root,
        archive_day=date(2026, 3, 19),
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.artifacts is None
    assert result.text_report is None
    assert not result.archive.destination.exists()
    assert csv_path.exists()


def test_parse_archive_date_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="Expected YYYY-MM-DD"):
        parse_archive_date("2026/03/19")


def test_archive_and_analyze_options_uses_richer_ai_report_and_writes_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    def _fake_generate_ai_options_markdown_report(*args, **kwargs):
        return OptionsAiReportResult(
            provider="openai_compatible",
            model="test-model",
            content="## 1. 核心结论\n\n- richer ai output",
            prompt="RICHER-PROMPT",
        )

    monkeypatch.setattr(
        "atas_market_structure.options_automation_services.generate_ai_options_markdown_report",
        _fake_generate_ai_options_markdown_report,
    )

    result = archive_and_analyze_options(
        source_dir=source_dir,
        data_root=data_root,
        archive_day=date(2026, 3, 19),
        copy_only=True,
        include_ai_analysis=True,
    )

    assert result.ai_analysis_error is None
    assert result.ai_interpretation is not None
    assert "richer ai output" in result.ai_interpretation
    assert result.markdown_report_artifacts is not None
    assert result.markdown_report_artifacts.report_path.exists()
    assert result.markdown_report_artifacts.prompt_path is not None
    assert result.markdown_report_artifacts.prompt_path.read_text(encoding="utf-8") == "RICHER-PROMPT"
    assert result.artifacts is not None
    assert result.artifacts.ai_report_path == result.markdown_report_artifacts.report_path
