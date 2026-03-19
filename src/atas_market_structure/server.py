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
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.strategy_library_services import StrategyLibraryService


class ApplicationRequestHandler(BaseHTTPRequestHandler):
    """HTTP bridge for the framework-free application."""

    application: MarketStructureApplication

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

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
        self.wfile.write(response.body)


def build_application(config: AppConfig) -> MarketStructureApplication:
    repository = SQLiteAnalysisRepository(database_path=config.database_path)
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
    )


def main() -> None:
    config = AppConfig.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    application = build_application(config)
    ApplicationRequestHandler.application = application
    server = ThreadingHTTPServer((config.host, config.port), ApplicationRequestHandler)
    logging.getLogger(__name__).info(
        "ATAS market structure server listening on http://%s:%s (db=%s)",
        config.host,
        config.port,
        str(config.database_path.resolve()),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
