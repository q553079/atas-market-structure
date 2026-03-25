from __future__ import annotations

import json
from pathlib import Path

import pytest

from atas_market_structure.options_report_services import OptionsAiReportResult
from tests.test_app_support import build_application
from tests.test_spx_gamma_map import _write_sample_csv


def test_options_archive_and_analyze_route_returns_archive_and_artifacts(tmp_path: Path) -> None:
    application = build_application()
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    response = application.dispatch(
        "POST",
        "/api/v1/options/archive-and-analyze",
        json.dumps(
            {
                "source_dir": str(source_dir),
                "data_root": str(data_root),
                "date": "2026-03-19",
                "symbol": "spx",
                "copy": True,
                "es_price": 5042.0,
                "max_dte": 1,
                "top_n": 2,
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["archive"]["action"] == "copy"
    assert payload["archive"]["dry_run"] is False
    assert Path(payload["archive"]["destination"]).name == "^spx_quotedata_20260319_1400Z.csv"
    assert payload["analysis"]["summary"]["spx_spot"] == 5000.0
    assert "Gap&Chop 结构分数:" in payload["analysis"]["text_report"]
    assert payload["analysis"]["strategy_context"] is not None
    assert payload["analysis"]["strategy_context"]["strategy_candidates"]
    assert Path(payload["analysis"]["artifacts"]["svg_path"]).exists()
    assert Path(payload["analysis"]["artifacts"]["json_path"]).exists()
    assert Path(payload["analysis"]["artifacts"]["report_path"]).exists()
    assert Path(payload["analysis"]["artifacts"]["strategy_context_json_path"]).exists()
    assert Path(payload["analysis"]["artifacts"]["strategy_context_report_path"]).exists()
    assert Path(payload["analysis"]["artifacts"]["markdown_report_path"]).exists()


def test_options_archive_and_analyze_route_supports_dry_run_preview(tmp_path: Path) -> None:
    application = build_application()
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    response = application.dispatch(
        "POST",
        "/api/v1/options/archive-and-analyze",
        json.dumps(
            {
                "source_dir": str(source_dir),
                "data_root": str(data_root),
                "date": "2026-03-19",
                "symbol": "spx",
                "dry_run": True,
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["archive"]["dry_run"] is True
    assert payload["analysis"] is None


def test_options_archive_and_analyze_route_rejects_invalid_date(tmp_path: Path) -> None:
    application = build_application()
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    data_root = tmp_path / "data"
    csv_path = source_dir / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)

    response = application.dispatch(
        "POST",
        "/api/v1/options/archive-and-analyze",
        json.dumps(
            {
                "source_dir": str(source_dir),
                "data_root": str(data_root),
                "date": "2026/03/19",
                "symbol": "spx",
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["error"] == "invalid_parameter"
    assert "YYYY-MM-DD" in payload["detail"]


def test_options_gamma_analysis_route_returns_richer_ai_markdown_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = build_application()
    csv_path = tmp_path / "^spx_quotedata_20260319.csv"
    _write_sample_csv(csv_path)
    artifact_output_dir = tmp_path / "artifacts"

    def _fake_generate_ai_options_markdown_report(*args, **kwargs):
        return OptionsAiReportResult(
            provider="openai_compatible",
            model="test-model",
            content="## 1. 核心结论\n\n- route richer ai output",
            prompt="ROUTE-RICHER-PROMPT",
        )

    monkeypatch.setattr(
        "atas_market_structure.app_routes._options_routes.generate_ai_options_markdown_report",
        _fake_generate_ai_options_markdown_report,
    )

    response = application.dispatch(
        "POST",
        "/api/v1/options/gamma-analysis",
        json.dumps(
            {
                "csv_path": str(csv_path),
                "include_ai_analysis": True,
                "persist_artifacts": True,
                "artifact_output_dir": str(artifact_output_dir),
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["strategy_context"] is not None
    assert "route richer ai output" in payload["ai_interpretation"]
    assert Path(payload["artifacts"]["markdown_report_path"]).exists()
    assert Path(payload["artifacts"]["markdown_prompt_path"]).exists()
    assert Path(payload["artifacts"]["ai_report_path"]).exists()
