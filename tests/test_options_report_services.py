from __future__ import annotations

from pathlib import Path

from atas_market_structure.config import AppConfig
from atas_market_structure.options_context_services import (
    analyze_options_strategy_context,
    write_options_strategy_context_artifacts,
)
from atas_market_structure.options_report_services import (
    OptionsAiReportResult,
    build_options_report_prompt,
    generate_ai_options_markdown_report,
    write_options_markdown_report,
)
from atas_market_structure.spx_gamma_map import generate_gamma_map_artifacts
from tests.test_spx_gamma_map import _write_sample_csv


def test_write_options_markdown_report_contains_chart_prompt_and_context(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"
    _write_sample_csv(csv_path)

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5042.0,
        max_dte=7,
        top_n=3,
    )
    context = analyze_options_strategy_context(
        artifacts.summary,
        history_dir=output_dir / "history",
        exclude_history_path=artifacts.history_json_path,
    )
    context_artifacts = write_options_strategy_context_artifacts(context, output_dir, stem=csv_path.stem)

    prompt = build_options_report_prompt(artifacts.summary, context)
    assert "观测事实" in prompt
    assert "策略环境拟合" in prompt
    assert "样本不足" in prompt

    report_artifacts = write_options_markdown_report(
        artifacts.summary,
        context,
        artifacts,
        strategy_context_artifacts=context_artifacts,
    )

    report_text = report_artifacts.report_path.read_text(encoding="utf-8")
    assert report_artifacts.report_path.exists()
    assert f"![SPX Gamma Map](./{artifacts.svg_path.name})" in report_text
    assert "## 核心结论" in report_text
    assert "## 关键价位与结构解读" in report_text
    assert "## 策略环境拟合" in report_text
    assert "历史上下文不足" in report_text
    assert str(context_artifacts.json_path) in report_text


def test_generate_ai_options_markdown_report_uses_richer_prompt(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"
    _write_sample_csv(csv_path)

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5042.0,
        max_dte=7,
        top_n=3,
    )
    context = analyze_options_strategy_context(
        artifacts.summary,
        history_dir=output_dir / "history",
        exclude_history_path=artifacts.history_json_path,
    )

    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = type("Msg", (), {"content": "## 1. 核心结论\n\n- 这是测试输出。"})
            choice = type("Choice", (), {"message": message})
            return type("Resp", (), {"choices": [choice]})

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs
            self.chat = _FakeChat()

    monkeypatch.setattr("atas_market_structure.options_report_services.OpenAI", _FakeClient)

    result = generate_ai_options_markdown_report(
        artifacts.summary,
        context,
        config=AppConfig(openai_api_key="test-key", ai_model="test-model"),
    )

    assert result.content.startswith("## 1. 核心结论")
    assert result.model == "test-model"
    assert captured["client_kwargs"]["api_key"] == "test-key"
    assert captured["messages"][1]["content"].count("Markdown 报告") >= 1
    assert "观测事实" in captured["messages"][1]["content"]
    assert "样本不足" in captured["messages"][1]["content"]


def test_write_options_markdown_report_with_ai_content_writes_prompt_artifact(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"
    _write_sample_csv(csv_path)

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        output_dir,
        es_price=5042.0,
        max_dte=7,
        top_n=3,
    )
    context = analyze_options_strategy_context(
        artifacts.summary,
        history_dir=output_dir / "history",
        exclude_history_path=artifacts.history_json_path,
    )
    context_artifacts = write_options_strategy_context_artifacts(context, output_dir, stem=csv_path.stem)
    ai_report = OptionsAiReportResult(
        provider="openai_compatible",
        model="test-model",
        content="## 1. 核心结论\n\n- AI richer report test.",
        prompt="PROMPT-BODY",
    )

    report_artifacts = write_options_markdown_report(
        artifacts.summary,
        context,
        artifacts,
        strategy_context_artifacts=context_artifacts,
        ai_report=ai_report,
    )

    report_text = report_artifacts.report_path.read_text(encoding="utf-8")
    assert "## AI 报告元数据" in report_text
    assert "AI richer report test." in report_text
    assert report_artifacts.prompt_path is not None
    assert report_artifacts.prompt_path.read_text(encoding="utf-8") == "PROMPT-BODY"
