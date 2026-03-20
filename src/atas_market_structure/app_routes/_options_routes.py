from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atas_market_structure.spx_gamma_map import (
    analyze_spx_gamma_csv,
    discover_latest_options_csv,
    generate_ai_options_analysis,
    load_options_csv,
    render_svg,
    render_svg_with_ai,
    render_text_report,
    write_ai_analysis_artifact,
    write_artifacts,
)

if TYPE_CHECKING:
    from atas_market_structure.app import HttpResponse, MarketStructureApplication


def handle_options_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "GET" and route_path == "/api/v1/options/latest-csv":
        symbol = (query.get("symbol", ["SPX"])[0] or "SPX").strip().upper()
        scan_dir_raw = query.get("scan_dir", [None])[0]
        recursive = (query.get("recursive", ["false"])[0] or "false").lower() == "true"
        scan_dir = Path(scan_dir_raw).expanduser() if scan_dir_raw else Path.cwd()
        csv_path = discover_latest_options_csv(scan_dir, recursive=recursive)
        _, quote_dt, _ = load_options_csv(csv_path)
        return app._json_response(
            200,
            {
                "symbol": symbol,
                "csv_path": str(csv_path),
                "trade_date": quote_dt.date().isoformat() if quote_dt else None,
                "quote_time": quote_dt.isoformat(sep=" ") if quote_dt else None,
                "scan_dir": str(scan_dir),
                "recursive": recursive,
            },
        )

    if method == "POST" and route_path == "/api/v1/options/gamma-analysis":
        payload = json.loads(body or b"{}")
        symbol = str(payload.get("symbol") or "SPX").strip().upper()
        trade_date = payload.get("trade_date")
        csv_path_raw = payload.get("csv_path")
        auto_discover_latest = bool(payload.get("auto_discover_latest", not csv_path_raw))
        include_ai_analysis = bool(payload.get("include_ai_analysis", True))
        persist_artifacts = bool(payload.get("persist_artifacts", False))
        scan_dir_raw = payload.get("scan_dir")
        recursive = bool(payload.get("recursive", False))
        es_price = payload.get("es_price")
        max_dte = int(payload.get("max_dte", 7))
        top_n = int(payload.get("top_n", 3))
        min_open_interest = int(payload.get("min_open_interest", 1))
        artifact_output_dir_raw = payload.get("artifact_output_dir")

        if csv_path_raw:
            csv_path = Path(str(csv_path_raw)).expanduser()
        elif auto_discover_latest:
            scan_dir = Path(scan_dir_raw).expanduser() if scan_dir_raw else Path.cwd()
            csv_path = discover_latest_options_csv(scan_dir, recursive=recursive)
        else:
            return app._json_response(
                400,
                {"error": "missing_field", "detail": "csv_path is required when auto_discover_latest is false."},
            )

        summary = analyze_spx_gamma_csv(
            csv_path,
            es_price=float(es_price) if es_price is not None else None,
            max_dte=max_dte,
            top_n=top_n,
            min_open_interest=min_open_interest,
        )
        text_report = render_text_report(summary)
        ai_result = None
        ai_error = None
        if include_ai_analysis:
            try:
                ai_result = generate_ai_options_analysis(summary, config=app._config)
            except Exception as exc:
                app._logger.warning("Options AI analysis failed for %s: %s", csv_path, exc)
                ai_error = str(exc)

        artifacts_payload: dict[str, Any] = {
            "svg_content": render_svg_with_ai(summary, ai_result) if ai_result else render_svg(summary),
        }
        if persist_artifacts:
            output_dir = Path(artifact_output_dir_raw).expanduser() if artifact_output_dir_raw else (csv_path.parent / "gamma_artifacts")
            artifacts = write_artifacts(summary, output_dir, stem=csv_path.stem)
            artifacts_payload.update(
                {
                    "svg_path": str(artifacts.svg_path),
                    "json_path": str(artifacts.json_path),
                    "report_path": str(artifacts.report_path),
                    "history_json_path": str(artifacts.history_json_path) if artifacts.history_json_path else None,
                }
            )
            if ai_result is not None:
                ai_path = write_ai_analysis_artifact(artifacts, ai_result)
                artifacts_payload["ai_report_path"] = str(ai_path)

        return app._json_response(
            200,
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "summary": summary.to_jsonable(),
                "text_report": text_report,
                "ai_interpretation": ai_result.content if ai_result else None,
                "ai_analysis_error": ai_error,
                "artifacts": artifacts_payload,
                "source": {
                    "csv_path": str(csv_path),
                    "quote_time": summary.quote_time,
                    "trade_date": trade_date or (summary.quote_time.split(" ")[0] if summary.quote_time else None),
                },
                "generated_at": datetime.now(tz=UTC),
            },
        )

    return None
