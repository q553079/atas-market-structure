from __future__ import annotations

import re
from typing import TYPE_CHECKING

from atas_market_structure.models import (
    BuildPromptBlocksRequest,
    ChatHandoffRequest,
    ChatReplyRequest,
    CreateChatMessageRequest,
    CreateChatSessionRequest,
    ReplayAiChatRequest,
    ReplayAiReviewRequest,
    UpdateChatSessionRequest,
    UpdateMountedMessageRequest,
)

if TYPE_CHECKING:
    from urllib.parse import ParseResult

    from atas_market_structure.app import HttpResponse, MarketStructureApplication


_CHAT_SESSION_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)$")
_CHAT_ARCHIVE_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/archive$")
_CHAT_MESSAGES_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/messages$")
_PROMPT_BLOCKS_BUILD_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/prompt-blocks/build$")
_PROMPT_BLOCK_PATTERN = re.compile(r"^/api/v1/workbench/chat/prompt-blocks/(?P<block_id>[^/]+)$")
_REPLY_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/reply$")
_STREAM_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/stream$")
_REGENERATE_PATTERN = re.compile(
    r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/messages/(?P<message_id>[^/]+)/regenerate$"
)
_STOP_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/messages/(?P<message_id>[^/]+)/stop$")
_MEMORY_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/memory$")
_HANDOFF_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/handoff$")
_OBJECTS_PATTERN = re.compile(r"^/api/v1/workbench/chat/sessions/(?P<session_id>[^/]+)/messages/(?P<message_id>[^/]+)/objects$")
_MOUNT_PATTERN = re.compile(r"^/api/v1/workbench/chat/messages/(?P<message_id>[^/]+)/mount$")


def handle_chat_routes(
    app: MarketStructureApplication,
    method: str,
    route_path: str,
    query: dict[str, list[str]],
    body: bytes | None,
) -> HttpResponse | None:
    if method == "POST" and route_path == "/api/v1/workbench/replay-ai-review":
        if app._replay_ai_review_service is None:
            return app._json_response(
                503,
                {
                    "error": "ai_review_unavailable",
                    "detail": "Replay AI review service is not configured.",
                },
            )
        payload = ReplayAiReviewRequest.model_validate_json(body or b"{}")
        response = app._replay_ai_review_service.review_replay(payload)
        return app._json_model_response(200, response)

    if method == "POST" and route_path == "/api/v1/workbench/replay-ai-chat":
        if app._replay_ai_chat_service is None:
            return app._json_response(
                503,
                {
                    "error": "ai_chat_unavailable",
                    "detail": "Replay AI chat service is not configured.",
                },
            )
        payload = ReplayAiChatRequest.model_validate_json(body or b"{}")
        response = app._replay_ai_chat_service.chat(payload)
        return app._json_model_response(200, response)

    if route_path == "/api/v1/workbench/chat/sessions" and app._replay_workbench_chat_service is not None:
        if method == "POST":
            payload = CreateChatSessionRequest.model_validate_json(body or b"{}")
            response = app._replay_workbench_chat_service.create_session(payload)
            return app._json_model_response(201, response)
        if method == "GET":
            symbol = query.get("symbol", [None])[0]
            workspace_id = query.get("workspace_id", [None])[0]
            include_archived = query.get("include_archived", ["false"])[0].lower() == "true"
            response = app._replay_workbench_chat_service.list_sessions(
                workspace_id=workspace_id,
                symbol=symbol,
                include_archived=include_archived,
            )
            return app._json_model_response(200, response)

    chat_session_match = _CHAT_SESSION_PATTERN.match(route_path)
    if chat_session_match and app._replay_workbench_chat_service is not None:
        session_id = chat_session_match.group("session_id")
        if method == "GET":
            response = app._replay_workbench_chat_service.get_session(session_id)
            return app._json_model_response(200, response)
        if method == "PATCH":
            payload = UpdateChatSessionRequest.model_validate_json(body or b"{}")
            response = app._replay_workbench_chat_service.update_session(session_id, payload)
            return app._json_model_response(200, response)

    chat_archive_match = _CHAT_ARCHIVE_PATTERN.match(route_path)
    if chat_archive_match and app._replay_workbench_chat_service is not None and method == "POST":
        response = app._replay_workbench_chat_service.archive_session(chat_archive_match.group("session_id"))
        return app._json_model_response(200, response)

    chat_messages_match = _CHAT_MESSAGES_PATTERN.match(route_path)
    if chat_messages_match and app._replay_workbench_chat_service is not None:
        session_id = chat_messages_match.group("session_id")
        if method == "GET":
            limit_raw = query.get("limit", [None])[0]
            limit = int(limit_raw) if limit_raw is not None else 200
            response = app._replay_workbench_chat_service.list_messages(session_id, limit=limit)
            return app._json_model_response(200, response)
        if method == "POST":
            payload = CreateChatMessageRequest.model_validate_json(body or b"{}")
            response = app._replay_workbench_chat_service.create_message(session_id, payload)
            return app._json_model_response(201, response)

    prompt_blocks_build_match = _PROMPT_BLOCKS_BUILD_PATTERN.match(route_path)
    if prompt_blocks_build_match and app._replay_workbench_chat_service is not None and method == "POST":
        payload = BuildPromptBlocksRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_chat_service.build_prompt_blocks(prompt_blocks_build_match.group("session_id"), payload)
        return app._json_model_response(200, response)

    prompt_block_match = _PROMPT_BLOCK_PATTERN.match(route_path)
    if prompt_block_match and app._replay_workbench_chat_service is not None and method == "GET":
        response = app._replay_workbench_chat_service.get_prompt_block(prompt_block_match.group("block_id"))
        return app._json_model_response(200, response)

    reply_match = _REPLY_PATTERN.match(route_path)
    if reply_match and app._replay_workbench_chat_service is not None and method == "POST":
        payload = ChatReplyRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_chat_service.reply(reply_match.group("session_id"), payload)
        return app._json_model_response(200, response)

    stream_match = _STREAM_PATTERN.match(route_path)
    if stream_match and app._replay_workbench_chat_service is not None and method == "POST":
        payload = ChatReplyRequest.model_validate_json(body or b"{}")
        events = app._replay_workbench_chat_service.build_reply_event_preview(stream_match.group("session_id"), payload)
        return app._sse_response(events)

    regenerate_match = _REGENERATE_PATTERN.match(route_path)
    if regenerate_match and app._replay_workbench_chat_service is not None and method == "POST":
        response = app._replay_workbench_chat_service.regenerate_message(
            regenerate_match.group("session_id"),
            regenerate_match.group("message_id"),
        )
        return app._json_model_response(200, response)

    stop_match = _STOP_PATTERN.match(route_path)
    if stop_match and app._replay_workbench_chat_service is not None and method == "POST":
        response = app._replay_workbench_chat_service.stop_message(
            stop_match.group("session_id"),
            stop_match.group("message_id"),
        )
        return app._json_model_response(200, response)

    memory_match = _MEMORY_PATTERN.match(route_path)
    if memory_match and app._replay_workbench_chat_service is not None and method == "GET":
        response = app._replay_workbench_chat_service.get_memory(memory_match.group("session_id"))
        return app._json_model_response(200, response)

    handoff_match = _HANDOFF_PATTERN.match(route_path)
    if handoff_match and app._replay_workbench_chat_service is not None and method == "POST":
        payload = ChatHandoffRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_chat_service.build_handoff(handoff_match.group("session_id"), payload)
        return app._json_model_response(200, response)

    objects_match = _OBJECTS_PATTERN.match(route_path)
    if objects_match and app._replay_workbench_chat_service is not None and method == "GET":
        response = app._replay_workbench_chat_service.list_objects(
            objects_match.group("session_id"),
            objects_match.group("message_id"),
        )
        return app._json_model_response(200, response)

    mount_match = _MOUNT_PATTERN.match(route_path)
    if mount_match and app._replay_workbench_chat_service is not None and method == "PATCH":
        payload = UpdateMountedMessageRequest.model_validate_json(body or b"{}")
        response = app._replay_workbench_chat_service.update_mount_state(mount_match.group("message_id"), payload)
        return app._json_model_response(200, response)

    return None
