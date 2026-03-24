from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging

from atas_market_structure.ai_review_services import (
    OpenAiReplayChatAssistant,
    OpenAiReplayReviewer,
    ReplayAiChatService,
    ReplayAiReviewService,
)
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.config import AppConfig
from atas_market_structure.repository import AnalysisRepository, SQLiteAnalysisRepository
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository, HybridAnalysisRepository
from atas_market_structure.strategy_library_services import StrategyLibraryService


LOGGER = logging.getLogger(__name__)


class ApplicationRequestHandler(BaseHTTPRequestHandler):
    """HTTP bridge for the framework-free application."""

    application: MarketStructureApplication

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle_request()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PATCH, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        logging.getLogger("atas_market_structure.http").info("%s - %s", self.address_string(), format % args)

    def _handle_request(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length else b""
        response = self.application.dispatch(self.command, self.path, body)
        self.send_response(HTTPStatus(response.status_code))
        for header_name, header_value in response.headers.items():
            self.send_header(header_name, header_value)
        self.end_headers()
        if response.stream_chunks is not None:
            for chunk in response.stream_chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
            return
        self.wfile.write(response.body)


def build_repository(config: AppConfig) -> AnalysisRepository:
    sqlite_repository = SQLiteAnalysisRepository(database_path=config.database_path)
    storage_mode = config.storage_mode.strip().lower()
    if storage_mode in {"sqlite", "sqlite_authoritative", "sqlite-only", "sqlite_only"}:
        LOGGER.info(
            "build_repository: using SQLite authoritative storage mode (db=%s).",
            str(config.database_path.resolve()),
        )
        return sqlite_repository

    market_data_repository = ClickHouseChartCandleRepository(
        host=config.clickhouse_host,
        port=config.clickhouse_port,
        username=config.clickhouse_user,
        password=config.clickhouse_password,
        database=config.clickhouse_database,
        table=config.clickhouse_chart_candles_table,
        workspace_root=sqlite_repository.workspace_root,
        ingestions_table=config.clickhouse_ingestions_table,
        connect_retries=config.clickhouse_connect_retries,
        retry_delay_seconds=config.clickhouse_retry_delay_seconds,
    )
    LOGGER.info(
        "build_repository: using hybrid storage mode (sqlite=%s clickhouse=%s:%s db=%s).",
        str(config.database_path.resolve()),
        config.clickhouse_host,
        config.clickhouse_port,
        config.clickhouse_database,
    )
    return HybridAnalysisRepository(
        metadata_repository=sqlite_repository,
        chart_candle_repository=market_data_repository,
        ingestion_repository=market_data_repository,
    )


def build_application(config: AppConfig) -> MarketStructureApplication:
    repository = build_repository(config)
    repository.initialize()
    replay_ai_review_service = ReplayAiReviewService(
        repository=repository,
        reviewer=OpenAiReplayReviewer(
            provider_name=config.ai_provider,
            api_key=config.openai_api_key,
            model=config.ai_model,
            base_url=config.openai_base_url,
            timeout_seconds=config.ai_timeout_seconds,
        ),
    )
    strategy_library_service = StrategyLibraryService()
    replay_ai_chat_service = ReplayAiChatService(
        repository=repository,
        assistant=OpenAiReplayChatAssistant(
            provider_name=config.ai_provider,
            api_key=config.openai_api_key,
            model=config.ai_model,
            base_url=config.openai_base_url,
            timeout_seconds=config.ai_timeout_seconds,
        ),
        strategy_library_service=strategy_library_service,
    )
    return MarketStructureApplication(
        repository=repository,
        replay_ai_review_service=replay_ai_review_service,
        replay_ai_chat_service=replay_ai_chat_service,
        config=config,
    )


def main() -> None:
    config = AppConfig.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    application = build_application(config)
    ApplicationRequestHandler.application = application
    server = ThreadingHTTPServer((config.host, config.port), ApplicationRequestHandler)
    LOGGER.info(
        "ATAS market structure server listening on http://%s:%s (db=%s storage_mode=%s)",
        config.host,
        config.port,
        str(config.database_path.resolve()),
        config.storage_mode,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
