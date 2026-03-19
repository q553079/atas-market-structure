from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from atas_market_structure.spx_gamma_map import (
    discover_latest_options_csv,
    generate_gamma_map_artifacts,
    load_powershell_env_file,
)


def _write_sample_csv(path: Path) -> None:
    def row(
        expiration: str,
        call_symbol: str,
        call_last: float,
        call_bid: float,
        call_ask: float,
        call_volume: int,
        call_iv: float,
        call_delta: float,
        call_gamma: float,
        call_oi: int,
        strike: float,
        put_symbol: str,
        put_last: float,
        put_bid: float,
        put_ask: float,
        put_volume: int,
        put_iv: float,
        put_delta: float,
        put_gamma: float,
        put_oi: int,
    ) -> str:
        return ",".join(
            [
                expiration,
                call_symbol,
                f"{call_last:.1f}",
                "1.0",
                f"{call_bid:.1f}",
                f"{call_ask:.1f}",
                str(call_volume),
                f"{call_iv:.2f}",
                f"{call_delta:.2f}",
                f"{call_gamma:.4f}",
                str(call_oi),
                f"{strike:.2f}",
                put_symbol,
                f"{put_last:.1f}",
                "1.0",
                f"{put_bid:.1f}",
                f"{put_ask:.1f}",
                str(put_volume),
                f"{put_iv:.2f}",
                f"{put_delta:.2f}",
                f"{put_gamma:.4f}",
                str(put_oi),
            ]
        )

    path.write_text(
        "\n".join(
            [
                "",
                "S&P 500 INDEX,Last: 5000.00,Change:  0.00",
                "Date: 2026年3月19日 GMT-4 10:30,Bid: 4999.50,Ask: 5000.50,Size: 1*1,Volume: 0",
                "Expiration Date,Calls,Last Sale,Net,Bid,Ask,Volume,IV,Delta,Gamma,Open Interest,Strike,Puts,Last Sale,Net,Bid,Ask,Volume,IV,Delta,Gamma,Open Interest",
                row("Thu Mar 19 2026", "SPXW260319C04950000", 34.0, 33.8, 34.2, 80, 0.16, 0.95, 0.0008, 40, 4950.00, "SPXW260319P04950000", 3.0, 2.9, 3.1, 3200, 0.31, -0.05, 0.0008, 15000),
                row("Thu Mar 19 2026", "SPXW260319C04960000", 30.0, 29.8, 30.2, 90, 0.16, 0.90, 0.0010, 50, 4960.00, "SPXW260319P04960000", 4.0, 3.9, 4.1, 3000, 0.30, -0.08, 0.0010, 12000),
                row("Thu Mar 19 2026", "SPXW260319C04970000", 27.0, 26.8, 27.2, 100, 0.17, 0.86, 0.0012, 80, 4970.00, "SPXW260319P04970000", 5.0, 4.9, 5.1, 2800, 0.30, -0.12, 0.0012, 10000),
                row("Thu Mar 19 2026", "SPXW260319C04980000", 25.0, 24.8, 25.2, 120, 0.17, 0.80, 0.0020, 120, 4980.00, "SPXW260319P04980000", 7.0, 6.9, 7.1, 2200, 0.29, -0.20, 0.0020, 7000),
                row("Thu Mar 19 2026", "SPXW260319C04990000", 18.0, 17.8, 18.2, 140, 0.18, 0.68, 0.0040, 180, 4990.00, "SPXW260319P04990000", 8.0, 7.9, 8.1, 2000, 0.28, -0.32, 0.0040, 5000),
                row("Thu Mar 19 2026", "SPXW260319C05000000", 12.0, 11.8, 12.2, 220, 0.22, 0.52, 0.0100, 2400, 5000.00, "SPXW260319P05000000", 12.0, 11.8, 12.2, 1200, 0.23, -0.48, 0.0100, 1400),
                row("Thu Mar 19 2026", "SPXW260319C05010000", 8.0, 7.9, 8.1, 1800, 0.18, 0.36, 0.0110, 3400, 5010.00, "SPXW260319P05010000", 18.0, 17.8, 18.2, 800, 0.24, -0.64, 0.0110, 900),
                row("Thu Mar 19 2026", "SPXW260319C05020000", 5.0, 4.9, 5.1, 1600, 0.17, 0.22, 0.0090, 3000, 5020.00, "SPXW260319P05020000", 25.0, 24.8, 25.2, 500, 0.26, -0.78, 0.0090, 500),
                row("Thu Apr 16 2026", "SPXW260416C04950000", 52.0, 51.8, 52.2, 70, 0.15, 0.90, 0.0010, 100, 4950.00, "SPXW260416P04950000", 17.0, 16.8, 17.2, 1200, 0.25, -0.10, 0.0010, 6000),
                row("Thu Apr 16 2026", "SPXW260416C04980000", 35.0, 34.8, 35.2, 90, 0.16, 0.75, 0.0025, 200, 4980.00, "SPXW260416P04980000", 22.0, 21.8, 22.2, 1500, 0.24, -0.24, 0.0025, 4800),
                row("Thu Apr 16 2026", "SPXW260416C05000000", 26.0, 25.8, 26.2, 110, 0.18, 0.51, 0.0060, 1200, 5000.00, "SPXW260416P05000000", 26.0, 25.8, 26.2, 900, 0.18, -0.49, 0.0060, 1500),
                row("Thu Apr 16 2026", "SPXW260416C05010000", 20.0, 19.8, 20.2, 140, 0.17, 0.38, 0.0070, 2000, 5010.00, "SPXW260416P05010000", 30.0, 29.8, 30.2, 700, 0.19, -0.61, 0.0070, 900),
                row("Thu Apr 16 2026", "SPXW260416C05020000", 15.0, 14.8, 15.2, 150, 0.16, 0.25, 0.0065, 2200, 5020.00, "SPXW260416P05020000", 35.0, 34.8, 35.2, 500, 0.21, -0.75, 0.0065, 800),
            ]
        ),
        encoding="utf-8",
    )


def _write_shifted_sample_csv(path: Path) -> None:
    def row(
        expiration: str,
        call_symbol: str,
        call_last: float,
        call_bid: float,
        call_ask: float,
        call_volume: int,
        call_iv: float,
        call_delta: float,
        call_gamma: float,
        call_oi: int,
        strike: float,
        put_symbol: str,
        put_last: float,
        put_bid: float,
        put_ask: float,
        put_volume: int,
        put_iv: float,
        put_delta: float,
        put_gamma: float,
        put_oi: int,
    ) -> str:
        return ",".join(
            [
                expiration,
                call_symbol,
                f"{call_last:.1f}",
                "1.0",
                f"{call_bid:.1f}",
                f"{call_ask:.1f}",
                str(call_volume),
                f"{call_iv:.2f}",
                f"{call_delta:.2f}",
                f"{call_gamma:.4f}",
                str(call_oi),
                f"{strike:.2f}",
                put_symbol,
                f"{put_last:.1f}",
                "1.0",
                f"{put_bid:.1f}",
                f"{put_ask:.1f}",
                str(put_volume),
                f"{put_iv:.2f}",
                f"{put_delta:.2f}",
                f"{put_gamma:.4f}",
                str(put_oi),
            ]
        )

    path.write_text(
        "\n".join(
            [
                "",
                "S&P 500 INDEX,Last: 5010.00,Change:  0.00",
                "Date: 2026年3月19日 GMT-4 11:00,Bid: 5009.50,Ask: 5010.50,Size: 1*1,Volume: 0",
                "Expiration Date,Calls,Last Sale,Net,Bid,Ask,Volume,IV,Delta,Gamma,Open Interest,Strike,Puts,Last Sale,Net,Bid,Ask,Volume,IV,Delta,Gamma,Open Interest",
                row("Thu Mar 19 2026", "SPXW260319C04970000", 33.0, 32.8, 33.2, 90, 0.15, 0.93, 0.0010, 60, 4970.00, "SPXW260319P04970000", 4.0, 3.9, 4.1, 2000, 0.28, -0.08, 0.0010, 9000),
                row("Thu Mar 19 2026", "SPXW260319C04980000", 29.0, 28.8, 29.2, 100, 0.16, 0.86, 0.0012, 80, 4980.00, "SPXW260319P04980000", 5.0, 4.9, 5.1, 2200, 0.27, -0.12, 0.0012, 8200),
                row("Thu Mar 19 2026", "SPXW260319C04990000", 24.0, 23.8, 24.2, 120, 0.17, 0.76, 0.0022, 200, 4990.00, "SPXW260319P04990000", 7.0, 6.9, 7.1, 1900, 0.25, -0.23, 0.0022, 6400),
                row("Thu Mar 19 2026", "SPXW260319C05000000", 18.0, 17.8, 18.2, 150, 0.18, 0.64, 0.0040, 320, 5000.00, "SPXW260319P05000000", 10.0, 9.9, 10.1, 1500, 0.24, -0.35, 0.0040, 7000),
                row("Thu Mar 19 2026", "SPXW260319C05010000", 12.0, 11.8, 12.2, 250, 0.20, 0.52, 0.0100, 2600, 5010.00, "SPXW260319P05010000", 12.0, 11.8, 12.2, 1200, 0.21, -0.48, 0.0100, 1800),
                row("Thu Mar 19 2026", "SPXW260319C05020000", 8.0, 7.9, 8.1, 1700, 0.17, 0.38, 0.0110, 3600, 5020.00, "SPXW260319P05020000", 18.0, 17.8, 18.2, 900, 0.22, -0.62, 0.0110, 900),
                row("Thu Mar 19 2026", "SPXW260319C05030000", 5.0, 4.9, 5.1, 1900, 0.16, 0.24, 0.0090, 4200, 5030.00, "SPXW260319P05030000", 26.0, 25.8, 26.2, 600, 0.24, -0.76, 0.0090, 500),
                row("Thu Apr 16 2026", "SPXW260416C04990000", 38.0, 37.8, 38.2, 80, 0.15, 0.72, 0.0025, 180, 4990.00, "SPXW260416P04990000", 23.0, 22.8, 23.2, 1200, 0.22, -0.23, 0.0025, 5200),
                row("Thu Apr 16 2026", "SPXW260416C05010000", 28.0, 27.8, 28.2, 100, 0.17, 0.50, 0.0060, 1500, 5010.00, "SPXW260416P05010000", 28.0, 27.8, 28.2, 950, 0.17, -0.50, 0.0060, 1600),
                row("Thu Apr 16 2026", "SPXW260416C05030000", 16.0, 15.8, 16.2, 130, 0.15, 0.26, 0.0065, 2600, 5030.00, "SPXW260416P05030000", 36.0, 35.8, 36.2, 600, 0.19, -0.74, 0.0065, 900),
            ]
        ),
        encoding="utf-8",
    )


def test_generate_gamma_map_artifacts_writes_outputs(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    _write_sample_csv(csv_path)

    artifacts = generate_gamma_map_artifacts(
        csv_path,
        tmp_path / "out",
        es_price=5042.0,
        max_dte=1,
        top_n=2,
    )

    assert artifacts.summary.spx_spot == 5000.0
    assert artifacts.summary.zero_gamma_proxy is not None
    assert artifacts.summary.zero_gamma_proxy_es is not None
    assert len(artifacts.summary.resistance_levels) == 2
    assert len(artifacts.summary.support_levels) == 2
    assert artifacts.summary.structural_regime is not None
    assert artifacts.summary.structural_regime.gap_chop_score >= 50
    assert artifacts.svg_path.exists()
    assert artifacts.json_path.exists()
    assert artifacts.report_path.exists()
    assert artifacts.history_json_path is not None
    assert artifacts.history_json_path.exists()

    svg_text = artifacts.svg_path.read_text(encoding="utf-8")
    report_text = artifacts.report_path.read_text(encoding="utf-8")

    assert "SPX Gamma 价位图" in svg_text
    assert "上方阻力带" in svg_text
    assert "下方支撑带" in svg_text
    assert "上破加速区" in svg_text
    assert "下破加速区" in svg_text
    assert "到达后容易减速的价位:" in report_text
    assert "到达后容易承接和减速的价位:" in report_text
    assert "Gap&Chop 结构分数:" in report_text
    assert "结构状态:" in report_text


def test_generate_gamma_map_artifacts_tracks_structural_shift_between_snapshots(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_spx.csv"
    output_dir = tmp_path / "out"

    _write_sample_csv(csv_path)
    first = generate_gamma_map_artifacts(
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

    assert first.summary.expiration_metrics
    assert len(first.summary.expiration_metrics) == 2
    assert second.summary.tracking_delta is not None
    assert second.summary.tracking_delta.previous_quote_time == "2026-03-19 10:30:00"
    assert second.summary.tracking_delta.dominant_put_wall_shift is not None
    assert second.summary.tracking_delta.dominant_call_wall_shift is not None
    assert second.summary.tracking_delta.gap_chop_score_change is not None
    assert second.summary.structural_regime is not None
    assert second.summary.structural_regime.dominant_put_wall is not None
    assert second.summary.structural_regime.dominant_call_wall is not None
    assert second.history_json_path is not None
    assert len(list((output_dir / "history").glob("sample_spx_*.json"))) == 2


def test_discover_latest_options_csv_prefers_latest_parseable_file(tmp_path: Path) -> None:
    older_csv = tmp_path / "^spx_quotedata_older.csv"
    invalid_csv = tmp_path / "^spx_quotedata_invalid.csv"
    newer_csv = tmp_path / "^spx_quotedata_newer.csv"

    _write_sample_csv(older_csv)
    invalid_csv.write_text("not,a,valid,options,csv\n", encoding="utf-8")
    _write_sample_csv(newer_csv)

    os.utime(older_csv, (1_000, 1_000))
    os.utime(invalid_csv, (2_000, 2_000))
    os.utime(newer_csv, (3_000, 3_000))

    selected = discover_latest_options_csv(tmp_path)
    assert selected == newer_csv.resolve()


def test_load_powershell_env_file_sets_environment_variables(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local.ps1"
    env_path.write_text(
        '\n'.join(
            [
                '$env:ATAS_MS_AI_PROVIDER = "deepseek"',
                '$env:OPENAI_API_KEY = "test-key"',
                '$env:ATAS_MS_AI_MODEL = "deepseek-chat"',
            ]
        ),
        encoding="utf-8",
    )

    load_powershell_env_file(env_path)

    assert os.environ["ATAS_MS_AI_PROVIDER"] == "deepseek"
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    assert os.environ["ATAS_MS_AI_MODEL"] == "deepseek-chat"
