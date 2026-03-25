from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atas_market_structure.options_context_services import (
    analyze_options_strategy_context,
    write_options_strategy_context_artifacts,
)
from atas_market_structure.options_automation_services import (
    archive_and_analyze_options,
    parse_archive_date,
)
from atas_market_structure.options_report_services import (
    generate_ai_options_markdown_report,
    write_options_markdown_report,
)
from atas_market_structure.spx_gamma_map import (
    analyze_spx_gamma_csv,
    discover_latest_options_csv,
    load_options_csv,
    render_svg,
    render_text_report,
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
        try:
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
        except FileNotFoundError as exc:
            return app._json_response(404, {"error": "not_found", "detail": str(exc)})

    if method == "POST" and route_path == "/api/v1/options/gamma-analysis":
        try:
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
            output_dir = (
                Path(artifact_output_dir_raw).expanduser()
                if artifact_output_dir_raw
                else (csv_path.parent / "gamma_artifacts")
            )
            strategy_context = analyze_options_strategy_context(
                summary,
                history_dir=output_dir / "history",
            )
            ai_report = None
            ai_error = None
            if include_ai_analysis:
                try:
                    ai_report = generate_ai_options_markdown_report(
                        summary,
                        strategy_context,
                        config=app._config,
                        question=(str(payload["ai_question"]) if payload.get("ai_question") is not None else None),
                    )
                except Exception as exc:
                    app._logger.warning("Options AI analysis failed for %s: %s", csv_path, exc)
                    ai_error = str(exc)

            artifacts_payload: dict[str, Any] = {
                "svg_content": render_svg(summary),
            }
            if persist_artifacts:
                artifacts = write_artifacts(summary, output_dir, stem=csv_path.stem)
                strategy_context_artifacts = write_options_strategy_context_artifacts(
                    strategy_context,
                    output_dir,
                    stem=csv_path.stem,
                )
                markdown_report_artifacts = write_options_markdown_report(
                    summary,
                    strategy_context,
                    artifacts,
                    strategy_context_artifacts=strategy_context_artifacts,
                    ai_report=ai_report,
                )
                if ai_report is not None:
                    artifacts.ai_report_path = markdown_report_artifacts.report_path
                artifacts_payload.update(
                    {
                        "svg_path": str(artifacts.svg_path),
                        "json_path": str(artifacts.json_path),
                        "report_path": str(artifacts.report_path),
                        "strategy_context_json_path": str(strategy_context_artifacts.json_path),
                        "strategy_context_report_path": str(strategy_context_artifacts.report_path),
                        "markdown_report_path": str(markdown_report_artifacts.report_path),
                        "markdown_prompt_path": (
                            str(markdown_report_artifacts.prompt_path)
                            if markdown_report_artifacts.prompt_path is not None
                            else None
                        ),
                        "history_json_path": str(artifacts.history_json_path) if artifacts.history_json_path else None,
                    }
                )
                if artifacts.ai_report_path is not None:
                    artifacts_payload["ai_report_path"] = str(artifacts.ai_report_path)

            return app._json_response(
                200,
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "summary": summary.to_jsonable(),
                    "text_report": text_report,
                    "strategy_context": strategy_context.to_jsonable(),
                    "ai_interpretation": ai_report.content if ai_report else None,
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
        except FileNotFoundError as exc:
            return app._json_response(404, {"error": "not_found", "detail": str(exc)})

    if method == "POST" and route_path == "/api/v1/options/archive-and-analyze":
        try:
            payload = json.loads(body or b"{}")
            archive_day = parse_archive_date(str(payload.get("date") or datetime.now(tz=UTC).date().isoformat()))
            symbol = str(payload.get("symbol") or "spx").strip().lower()
            result = archive_and_analyze_options(
                source_dir=Path(str(payload.get("source_dir") or Path.home() / "Downloads")).expanduser(),
                data_root=Path(str(payload.get("data_root") or app._config.database_path.parent)).expanduser(),
                market=str(payload.get("market") or "s&p500_options"),
                symbol=symbol,
                archive_day=archive_day,
                pattern=str(payload.get("glob") or "*quotedata*.csv"),
                copy_only=bool(payload.get("copy", False)),
                dry_run=bool(payload.get("dry_run", False)),
                artifact_output_dir=(
                    Path(str(payload.get("artifact_output_dir"))).expanduser()
                    if payload.get("artifact_output_dir")
                    else None
                ),
                es_price=float(payload["es_price"]) if payload.get("es_price") is not None else None,
                max_dte=int(payload.get("max_dte", 7)),
                top_n=int(payload.get("top_n", 3)),
                min_open_interest=int(payload.get("min_open_interest", 1)),
                include_ai_analysis=bool(payload.get("include_ai_analysis", False)),
                config=app._config,
                ai_question=(str(payload["ai_question"]) if payload.get("ai_question") is not None else None),
            )
            return app._json_response(
                200,
                {
                    "archive": {
                        "source": str(result.archive.source),
                        "destination": str(result.archive.destination),
                        "action": result.archive.action,
                        "moved": result.archive.moved,
                        "archive_day": result.archive_day.isoformat(),
                        "dry_run": result.dry_run,
                    },
                    "analysis": (
                        {
                            "summary": result.artifacts.summary.to_jsonable(),
                            "text_report": result.text_report,
                            "strategy_context": (
                                result.strategy_context.to_jsonable() if result.strategy_context is not None else None
                            ),
                            "ai_interpretation": result.ai_interpretation,
                            "ai_analysis_error": result.ai_analysis_error,
                            "artifacts": {
                                "svg_path": str(result.artifacts.svg_path),
                                "json_path": str(result.artifacts.json_path),
                                "report_path": str(result.artifacts.report_path),
                                "strategy_context_json_path": (
                                    str(result.strategy_context_artifacts.json_path)
                                    if result.strategy_context_artifacts is not None
                                    else None
                                ),
                                "strategy_context_report_path": (
                                    str(result.strategy_context_artifacts.report_path)
                                    if result.strategy_context_artifacts is not None
                                    else None
                                ),
                                "markdown_report_path": (
                                    str(result.markdown_report_artifacts.report_path)
                                    if result.markdown_report_artifacts is not None
                                    else None
                                ),
                                "markdown_prompt_path": (
                                    str(result.markdown_report_artifacts.prompt_path)
                                    if result.markdown_report_artifacts is not None
                                    and result.markdown_report_artifacts.prompt_path is not None
                                    else None
                                ),
                                "history_json_path": (
                                    str(result.artifacts.history_json_path) if result.artifacts.history_json_path else None
                                ),
                                "ai_report_path": (
                                    str(result.artifacts.ai_report_path) if result.artifacts.ai_report_path else None
                                ),
                            },
                        }
                        if result.artifacts is not None
                        else None
                    ),
                    "generated_at": datetime.now(tz=UTC),
                },
            )
        except FileNotFoundError as exc:
            return app._json_response(404, {"error": "not_found", "detail": str(exc)})

    return None
