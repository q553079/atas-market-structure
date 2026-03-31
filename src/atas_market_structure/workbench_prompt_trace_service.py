from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Iterable
from uuid import uuid4

from atas_market_structure.ai_review_services import (
    OpenAiReplayReviewer,
    _compact_live_context_messages,
    _compact_replay_payload,
    _list_live_context_messages,
    _list_manual_regions,
    _list_operator_entries,
    _summarize_chat_attachment,
)
from atas_market_structure.models import (
    PromptTrace,
    PromptTraceBlockSummary,
    PromptTraceEnvelope,
    PromptTraceListEnvelope,
    ReplayAiChatContent,
    ReplayAiChatMessage,
    ReplayAiChatPreset,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.repository import AnalysisRepository, StoredChatSession, StoredPromptTrace
from atas_market_structure.strategy_library_services import StrategyLibraryService
from atas_market_structure.workbench_common import ReplayWorkbenchNotFoundError

_REPLAY_SYSTEM_PROMPT = (
    "You are the replay-workbench copilot for short-term futures review. "
    "Always reason in this order: strategy candidates first, then replay events/focus regions, "
    "then operator entries, then live depth context. "
    "If screenshot attachments are present, use them only as supplemental context and do not override structured replay facts. "
    "Be explicit about where the operator should not open. "
    "When evidence is missing, say so instead of inventing order-flow facts. "
    "Return only valid JSON matching the supplied schema."
)


class ReplayWorkbenchPromptTraceService:
    """Builds, persists, and queries user-readable Prompt Trace records for replay-workbench chat replies."""

    def __init__(
        self,
        repository: AnalysisRepository,
        *,
        replay_ai_chat_service=None,
        strategy_library_service: StrategyLibraryService | None = None,
    ) -> None:
        self._repository = repository
        self._replay_ai_chat_service = replay_ai_chat_service
        self._strategy_library_service = strategy_library_service or getattr(
            replay_ai_chat_service,
            "_strategy_library_service",
            None,
        ) or StrategyLibraryService()

    def create_prompt_trace(
        self,
        *,
        session: StoredChatSession,
        message_id: str,
        replay_ingestion_id: str | None,
        request,
        history: list[ReplayAiChatMessage],
        model_user_input: str,
    ) -> StoredPromptTrace:
        """Create and persist one prompt trace snapshot before model execution."""

        now = datetime.now(tz=UTC)
        snapshot, metadata = self._build_snapshot(
            session=session,
            replay_ingestion_id=replay_ingestion_id,
            request=request,
            history=history,
            model_user_input=model_user_input,
        )
        prompt_trace_id = f"trace-{uuid4().hex}"
        return self._repository.save_prompt_trace(
            prompt_trace_id=prompt_trace_id,
            session_id=session.session_id,
            message_id=message_id,
            symbol=session.symbol,
            timeframe=str(session.timeframe),
            analysis_type=request.analysis_type,
            analysis_range=request.analysis_range,
            analysis_style=request.analysis_style,
            selected_block_ids=list(request.selected_block_ids or []),
            pinned_block_ids=list(request.pinned_block_ids or []),
            attached_event_ids=[],
            prompt_block_summaries=snapshot["prompt_block_summaries"],
            bar_window_summary=snapshot["bar_window_summary"],
            manual_selection_summary=snapshot["manual_selection_summary"],
            memory_summary=snapshot["memory_summary"],
            final_system_prompt=snapshot["final_system_prompt"],
            final_user_prompt=snapshot["final_user_prompt"],
            model_name=snapshot["model_name"],
            model_input_hash=snapshot["model_input_hash"],
            snapshot=snapshot,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    def finalize_prompt_trace(
        self,
        prompt_trace_id: str,
        *,
        model_name: str | None,
        attached_event_ids: list[str] | None = None,
    ) -> StoredPromptTrace | None:
        """Patch one stored trace with the resolved model name and linked event ids."""

        current = self._repository.get_prompt_trace(prompt_trace_id)
        if current is None:
            return None
        metadata = dict(current.metadata)
        metadata["resolved_model_name"] = model_name
        if attached_event_ids is not None:
            metadata["attached_event_count"] = len(attached_event_ids)
        now = datetime.now(tz=UTC)
        return self._repository.update_prompt_trace(
            prompt_trace_id,
            model_name=model_name,
            attached_event_ids=attached_event_ids if attached_event_ids is not None else current.attached_event_ids,
            metadata=metadata,
            updated_at=now,
        )

    def get_prompt_trace(self, prompt_trace_id: str) -> PromptTraceEnvelope:
        stored = self._repository.get_prompt_trace(prompt_trace_id)
        if stored is None:
            raise ReplayWorkbenchNotFoundError(f"Prompt trace '{prompt_trace_id}' not found.")
        return PromptTraceEnvelope(trace=self._trace_model(stored))

    def get_prompt_trace_by_message(self, message_id: str) -> PromptTraceEnvelope:
        stored = self._repository.get_prompt_trace_by_message(message_id)
        if stored is None:
            raise ReplayWorkbenchNotFoundError(f"Prompt trace for message '{message_id}' not found.")
        return PromptTraceEnvelope(trace=self._trace_model(stored))

    def list_prompt_traces(self, *, session_id: str, limit: int = 200) -> PromptTraceListEnvelope:
        traces = self._repository.list_prompt_traces(session_id=session_id, limit=limit)
        return PromptTraceListEnvelope(traces=[self._trace_model(item) for item in traces])

    def _build_snapshot(
        self,
        *,
        session: StoredChatSession,
        replay_ingestion_id: str | None,
        request,
        history: list[ReplayAiChatMessage],
        model_user_input: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_block_summaries = self._collect_prompt_block_summaries(
            session=session,
            selected_block_ids=request.selected_block_ids,
            pinned_block_ids=request.pinned_block_ids,
        )
        context_blocks = self._build_context_blocks(prompt_block_summaries)
        attachment_summaries = [
            _summarize_chat_attachment(item, index)
            for index, item in enumerate(request.attachments[:3], start=1)
        ]
        replay_snapshot = self._load_replay_snapshot(replay_ingestion_id)
        bar_window_summary = self._build_bar_window_summary(replay_snapshot, prompt_block_summaries)
        manual_selection_summary = self._build_manual_selection_summary(
            prompt_block_summaries=prompt_block_summaries,
            extra_context=request.extra_context or {},
        )
        memory_summary = self._build_memory_summary(
            session_id=session.session_id,
            include_memory_summary=bool(request.include_memory_summary),
            include_recent_messages=bool(request.include_recent_messages),
            history=history,
        )
        final_system_prompt, final_user_prompt, request_snapshot = self._build_prompt_snapshot(
            replay_snapshot=replay_snapshot,
            replay_ingestion_id=replay_ingestion_id,
            session=session,
            request=request,
            history=history,
            model_user_input=model_user_input,
            attachment_summaries=attachment_summaries,
        )
        reply_window = self._resolve_reply_window(
            session=session,
            replay_snapshot=replay_snapshot,
            extra_context=request.extra_context or {},
        )
        reply_session_date = self._resolve_reply_session_date(
            reply_window=reply_window,
            extra_context=request.extra_context or {},
        )
        reply_window_anchor = self._build_reply_window_anchor(
            symbol=session.symbol,
            timeframe=str(session.timeframe),
            reply_window=reply_window,
            reply_session_date=reply_session_date,
        )
        context_version = self._build_context_version(
            selected_block_ids=request.selected_block_ids,
            pinned_block_ids=request.pinned_block_ids,
            context_blocks=context_blocks,
            include_memory_summary=bool(request.include_memory_summary),
            include_recent_messages=bool(request.include_recent_messages),
            preset=str(request.preset),
        )
        model_input_hash = self._hash_input(
            {
                "system": final_system_prompt,
                "user": final_user_prompt,
                "history": [item.model_dump(mode="json") if hasattr(item, "model_dump") else {"role": item.role, "content": item.content} for item in history],
                "session_id": session.session_id,
                "message_symbol": session.symbol,
            }
        )
        snapshot = {
            "mode": "replay_aware" if replay_snapshot is not None else "session_only",
            "preset": str(request.preset),
            "prompt_block_summaries": prompt_block_summaries,
            "context_blocks": context_blocks,
            "context_version": context_version,
            "bar_window_summary": bar_window_summary,
            "manual_selection_summary": manual_selection_summary,
            "memory_summary": memory_summary,
            "reply_window": reply_window,
            "reply_window_anchor": reply_window_anchor,
            "reply_session_date": reply_session_date,
            "final_system_prompt": final_system_prompt,
            "final_user_prompt": final_user_prompt,
            "model_name": request.model or session.active_model or None,
            "model_input_hash": model_input_hash,
            "request_snapshot": request_snapshot,
        }
        metadata = {
            "preset": str(request.preset),
            "include_memory_summary": bool(request.include_memory_summary),
            "include_recent_messages": bool(request.include_recent_messages),
            "attachment_summaries": attachment_summaries,
            "extra_context_keys": sorted((request.extra_context or {}).keys()),
            "session_only": replay_snapshot is None,
            "context_version": context_version,
            "block_version_refs": context_blocks,
            "reply_window": reply_window,
            "reply_window_anchor": reply_window_anchor,
            "reply_session_date": reply_session_date,
            "truncation": request_snapshot.get("truncation", {}),
        }
        return snapshot, metadata

    def _collect_prompt_block_summaries(
        self,
        *,
        session: StoredChatSession,
        selected_block_ids: Iterable[str],
        pinned_block_ids: Iterable[str],
    ) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys([*selected_block_ids, *pinned_block_ids]))
        selected_block_id_set = set(selected_block_ids)
        pinned_block_id_set = set(pinned_block_ids)
        summaries: list[dict[str, Any]] = []
        for block_id in ordered_ids:
            block = self._repository.get_prompt_block(block_id)
            if block is None:
                summaries.append(
                    PromptTraceBlockSummary(
                        block_id=block_id,
                        kind="missing",
                        title="missing",
                        preview_text="Prompt block was selected but is no longer available.",
                        payload_summary={},
                        block_version=1,
                        source_kind="system_policy",
                        scope="request",
                        editable=False,
                        selected=block_id in selected_block_id_set,
                        pinned=block_id in pinned_block_id_set,
                    ).model_dump(mode="json")
                )
                continue
            if block.session_id != session.session_id and block.symbol != session.symbol:
                continue
            block_meta = self._resolve_block_meta(block)
            summaries.append(
                PromptTraceBlockSummary(
                    block_id=block.block_id,
                    kind=block.kind,
                    title=block.title,
                    preview_text=block.preview_text,
                    payload_summary=self._summarize_prompt_block_payload(block.full_payload),
                    block_version=block_meta["block_version"],
                    source_kind=block_meta["source_kind"],
                    scope=block_meta["scope"],
                    editable=block_meta["editable"],
                    selected=block.block_id in selected_block_id_set,
                    pinned=block.block_id in pinned_block_id_set,
                ).model_dump(mode="json")
            )
        return summaries

    @staticmethod
    def _build_context_blocks(prompt_block_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        context_blocks: list[dict[str, Any]] = []
        for item in prompt_block_summaries:
            if not isinstance(item, dict):
                continue
            context_blocks.append(
                {
                    "block_id": item.get("block_id"),
                    "block_version": item.get("block_version", 1),
                    "source_kind": item.get("source_kind", "system_policy"),
                    "scope": item.get("scope", "request"),
                    "editable": bool(item.get("editable", False)),
                    "selected": bool(item.get("selected", False)),
                    "pinned": bool(item.get("pinned", False)),
                }
            )
        return context_blocks

    def _build_context_version(
        self,
        *,
        selected_block_ids: Iterable[str],
        pinned_block_ids: Iterable[str],
        context_blocks: list[dict[str, Any]],
        include_memory_summary: bool,
        include_recent_messages: bool,
        preset: str,
    ) -> str:
        payload = {
            "selected_block_ids": list(selected_block_ids),
            "pinned_block_ids": list(pinned_block_ids),
            "context_blocks": context_blocks,
            "include_memory_summary": include_memory_summary,
            "include_recent_messages": include_recent_messages,
            "preset": preset,
        }
        digest = self._hash_input(payload)[:16]
        return f"ctx_v1_{digest}"

    def _resolve_reply_window(
        self,
        *,
        session: StoredChatSession,
        replay_snapshot: ReplayWorkbenchSnapshotPayload | None,
        extra_context: dict[str, Any],
    ) -> dict[str, str]:
        ui_context = extra_context.get("ui_context") if isinstance(extra_context.get("ui_context"), dict) else {}
        chart_visible_window = ui_context.get("chart_visible_window") if isinstance(ui_context.get("chart_visible_window"), dict) else {}
        window_start = (
            chart_visible_window.get("window_start")
            or chart_visible_window.get("start")
            or extra_context.get("reply_window_start")
        )
        window_end = (
            chart_visible_window.get("window_end")
            or chart_visible_window.get("end")
            or extra_context.get("reply_window_end")
        )
        if not window_start and replay_snapshot is not None:
            window_start = replay_snapshot.window_start.astimezone(UTC).isoformat()
        if not window_end and replay_snapshot is not None:
            window_end = replay_snapshot.window_end.astimezone(UTC).isoformat()
        if not window_start:
            window_start = self._normalize_time_value(session.window_range.get("start") or session.window_range.get("window_start"))
        if not window_end:
            window_end = self._normalize_time_value(session.window_range.get("end") or session.window_range.get("window_end"))
        return {
            "window_start": self._normalize_time_value(window_start),
            "window_end": self._normalize_time_value(window_end),
        }

    def _resolve_reply_session_date(self, *, reply_window: dict[str, str], extra_context: dict[str, Any]) -> str | None:
        ui_context = extra_context.get("ui_context") if isinstance(extra_context.get("ui_context"), dict) else {}
        session_date = (
            ui_context.get("session_date")
            or extra_context.get("session_date")
            or extra_context.get("reply_session_date")
        )
        if isinstance(session_date, str) and session_date.strip():
            return session_date.strip()
        window_end = reply_window.get("window_end")
        parsed_window_end = self._parse_time_value(window_end)
        if parsed_window_end is None:
            return None
        return parsed_window_end.date().isoformat()

    @staticmethod
    def _build_reply_window_anchor(
        *,
        symbol: str,
        timeframe: str,
        reply_window: dict[str, str],
        reply_session_date: str | None,
    ) -> str | None:
        window_start = reply_window.get("window_start")
        window_end = reply_window.get("window_end")
        if not window_start or not window_end or not reply_session_date:
            return None
        return f"{symbol}|{timeframe}|{window_start}|{window_end}|{reply_session_date}"

    def _resolve_block_meta(self, block) -> dict[str, Any]:
        full_payload = block.full_payload if isinstance(block.full_payload, dict) else {}
        block_meta = full_payload.get("block_meta") if isinstance(full_payload.get("block_meta"), dict) else {}
        return {
            "block_version": self._coerce_block_version(block_meta.get("block_version")),
            "source_kind": str(block_meta.get("source_kind") or self._default_source_kind(block.kind)),
            "scope": str(block_meta.get("scope") or self._default_scope(ephemeral=block.ephemeral, pinned=block.pinned)),
            "editable": bool(block_meta.get("editable", False)),
            "author": block_meta.get("author"),
            "updated_at": self._normalize_time_value(block_meta.get("updated_at") or block.created_at),
        }

    @staticmethod
    def _coerce_block_version(value: Any) -> int:
        try:
            version = int(value)
        except (TypeError, ValueError):
            return 1
        return version if version >= 1 else 1

    @staticmethod
    def _default_source_kind(kind: str) -> str:
        return {
            "candles_20": "window_snapshot",
            "selected_bar": "window_snapshot",
            "manual_region": "window_snapshot",
            "event_summary": "nearby_event_summary",
            "recent_messages": "recent_messages",
            "session_summary": "memory_summary",
        }.get(kind, "system_policy")

    @staticmethod
    def _default_scope(*, ephemeral: bool, pinned: bool = False) -> str:
        return "session" if (not ephemeral or pinned) else "request"

    @staticmethod
    def _normalize_time_value(value: Any) -> str | None:
        parsed = ReplayWorkbenchPromptTraceService._parse_time_value(value)
        if parsed is None:
            return str(value).strip() if isinstance(value, str) and value.strip() else None
        return parsed.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_time_value(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    def _summarize_prompt_block_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            return {}
        summary: dict[str, Any] = {}
        bars = payload.get("bars")
        if isinstance(bars, list) and bars:
            summary["bar_count"] = len(bars)
            summary["time_start"] = bars[0].get("started_at") or bars[0].get("ended_at")
            summary["time_end"] = bars[-1].get("ended_at") or bars[-1].get("started_at")
            summary["close_range"] = {
                "first": bars[0].get("close"),
                "last": bars[-1].get("close"),
            }
        bar = payload.get("bar")
        if isinstance(bar, dict) and bar:
            summary["selected_bar"] = {
                "started_at": bar.get("started_at"),
                "ended_at": bar.get("ended_at"),
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": bar.get("close"),
            }
        events = payload.get("events")
        if isinstance(events, list):
            summary["event_count"] = len(events)
            if events:
                summary["event_types"] = list(
                    dict.fromkeys(str(item.get("event_type") or item.get("type") or item.get("label") or "").strip() for item in events if isinstance(item, dict))
                )[:6]
        regions = payload.get("regions")
        if isinstance(regions, list):
            summary["region_count"] = len(regions)
            if regions:
                lows = [item.get("price_low") for item in regions if isinstance(item, dict) and item.get("price_low") is not None]
                highs = [item.get("price_high") for item in regions if isinstance(item, dict) and item.get("price_high") is not None]
                if lows and highs:
                    summary["price_range"] = {"low": min(lows), "high": max(highs)}
        messages = payload.get("messages")
        if isinstance(messages, list):
            summary["message_count"] = len(messages)
        if "latest_question" in payload or "market_context_summary" in payload:
            summary["memory_excerpt"] = {
                "latest_question": payload.get("latest_question"),
                "market_context_summary": payload.get("market_context_summary"),
                "latest_answer_summary": payload.get("latest_answer_summary"),
            }
        return summary

    def _build_bar_window_summary(
        self,
        replay_snapshot: ReplayWorkbenchSnapshotPayload | None,
        prompt_block_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        if replay_snapshot is not None:
            summary.update(
                {
                    "window_start": replay_snapshot.window_start.isoformat(),
                    "window_end": replay_snapshot.window_end.isoformat(),
                    "display_timeframe": str(replay_snapshot.display_timeframe),
                    "total_candle_count": len(replay_snapshot.candles),
                }
            )
        for item in prompt_block_summaries:
            payload_summary = item.get("payload_summary") if isinstance(item, dict) else {}
            if not isinstance(payload_summary, dict):
                continue
            if "bar_count" in payload_summary:
                summary["selected_bar_count"] = payload_summary.get("bar_count")
                summary["selected_time_start"] = payload_summary.get("time_start")
                summary["selected_time_end"] = payload_summary.get("time_end")
            if "selected_bar" in payload_summary:
                summary["selected_bar"] = payload_summary.get("selected_bar")
        return summary

    def _build_manual_selection_summary(
        self,
        *,
        prompt_block_summaries: list[dict[str, Any]],
        extra_context: dict[str, Any],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "extra_context_keys": sorted(extra_context.keys()),
        }
        for item in prompt_block_summaries:
            payload_summary = item.get("payload_summary") if isinstance(item, dict) else {}
            if not isinstance(payload_summary, dict):
                continue
            if "region_count" in payload_summary:
                summary["region_count"] = payload_summary.get("region_count")
                if "price_range" in payload_summary:
                    summary["price_range"] = payload_summary.get("price_range")
            if "selected_bar" in payload_summary:
                summary["selected_bar"] = payload_summary.get("selected_bar")
        return summary

    def _build_memory_summary(
        self,
        *,
        session_id: str,
        include_memory_summary: bool,
        include_recent_messages: bool,
        history: list[ReplayAiChatMessage],
    ) -> dict[str, Any]:
        session_memory = self._repository.get_session_memory(session_id)
        summary: dict[str, Any] = {
            "include_memory_summary": include_memory_summary,
            "include_recent_messages": include_recent_messages,
            "history_message_count": len(history),
            "history_roles": [getattr(item, "role", None) for item in history],
        }
        if session_memory is not None:
            summary["session_memory"] = {
                "memory_summary_id": session_memory.memory_summary_id,
                "latest_question": session_memory.latest_question,
                "market_context_summary": session_memory.market_context_summary,
                "latest_answer_summary": session_memory.latest_answer_summary,
            }
        return summary

    def _build_prompt_snapshot(
        self,
        *,
        replay_snapshot: ReplayWorkbenchSnapshotPayload | None,
        replay_ingestion_id: str | None,
        session: StoredChatSession,
        request,
        history: list[ReplayAiChatMessage],
        model_user_input: str,
        attachment_summaries: list[str],
    ) -> tuple[str, str, dict[str, Any]]:
        history_payload = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else {"role": item.role, "content": item.content}
            for item in history[-10:]
        ]
        truncation: dict[str, Any] = {}
        preset = self._coerce_preset(request.preset)
        if replay_snapshot is not None:
            live_context_messages = _list_live_context_messages(self._repository, replay_snapshot)
            compact_payload = _compact_replay_payload(
                replay_snapshot,
                _list_operator_entries(self._repository, replay_ingestion_id or ""),
                _list_manual_regions(self._repository, replay_ingestion_id or ""),
                preset=preset,
            )
            compact_live_context = _compact_live_context_messages(live_context_messages)
            strategy_cards = self._strategy_library_service.resolve_relevant_cards(
                replay_snapshot,
                preset=preset,
            )
            request_payload = {
                "schema": ReplayAiChatContent.model_json_schema(),
                "preset": str(request.preset),
                "preset_instruction": self._replay_preset_instruction(str(request.preset)),
                "strategy_candidates_first": True,
                "strategy_library_cards": StrategyLibraryService.compact_cards(strategy_cards),
                "latest_user_request": model_user_input,
                "replay_packet": compact_payload,
                "live_context": compact_live_context,
                "image_attachments": attachment_summaries,
            }
            final_system_prompt = _REPLAY_SYSTEM_PROMPT
        else:
            request_payload = {
                "schema": ReplayAiChatContent.model_json_schema(),
                "mode": "session_only",
                "latest_user_request": model_user_input,
                "conversation_context": history_payload,
                "image_attachments": attachment_summaries,
                "output_expectations": {
                    "live_context_summary": [],
                    "referenced_strategy_ids": [],
                    "annotations": (
                        "When explicit prices/zones/invalidation cues are present, return structured annotations."
                        if self._should_enable_session_structured_output(request.analysis_type)
                        else []
                    ),
                    "plan_cards": (
                        "When a concrete execution plan is present, return at most one compact plan_card."
                        if self._should_enable_session_structured_output(request.analysis_type)
                        else []
                    ),
                },
            }
            final_system_prompt = getattr(
                getattr(self._replay_ai_chat_service, "_assistant", None),
                "_SESSION_ONLY_SYSTEM_PROMPT",
                OpenAiReplayReviewer._SESSION_ONLY_SYSTEM_PROMPT,
            )
        request_snapshot = {
            "assistant_history": self._truncate_value(history_payload, truncation=truncation, path="assistant_history"),
            "request_payload": self._truncate_value(request_payload, truncation=truncation, path="request_payload"),
            "attachment_summaries": attachment_summaries,
            "transport_mode": "text_plus_images" if attachment_summaries else "text_only",
            "truncation": truncation,
        }
        final_user_prompt = json.dumps(
            request_snapshot["request_payload"],
            ensure_ascii=False,
            default=self._json_default,
            sort_keys=True,
        )
        return final_system_prompt, final_user_prompt, request_snapshot

    @staticmethod
    def _replay_preset_instruction(preset: str) -> str:
        preset_map = {
            "general": (
                "Summarize the current market script, the most important no-trade areas, "
                "and the next context-sensitive questions the operator should answer."
            ),
            "recent_20_bars": (
                "Focus on the most recent 20 bars. Explain the local sequence, initiative quality, "
                "and where a scalp entry should not be opened."
            ),
            "recent_20_minutes": (
                "Focus on the most recent 20 minutes of bars. Explain short-term rotation, drive quality, "
                "and whether the local context supports continuation, pause, or reversal."
            ),
            "focus_regions": (
                "Rank the highest-priority focus regions from the replay packet. Explain which regions matter now, "
                "which are already consumed, and what reaction would confirm or reject each region."
            ),
            "trapped_large_orders": (
                "Evaluate whether any large order or defended price now looks trapped. Use strategy candidates first, "
                "then replay events, then live depth context. Be explicit about what evidence is still missing."
            ),
            "live_depth": (
                "Prioritize live resting-order and depth behavior. Explain whether the current depth supports attraction, "
                "absorption, spoof risk, or exhaustion, and where the operator should avoid opening."
            ),
        }
        return preset_map.get(preset, preset_map["general"])

    @staticmethod
    def _coerce_preset(value: str | ReplayAiChatPreset) -> ReplayAiChatPreset:
        try:
            return ReplayAiChatPreset(str(value))
        except ValueError:
            return ReplayAiChatPreset.GENERAL

    @staticmethod
    def _should_enable_session_structured_output(analysis_type: str | None) -> bool:
        normalized = str(analysis_type or "").strip().lower()
        return normalized in {"event_timeline", "event_extraction", "event_scribe", "event_summary"}

    def _load_replay_snapshot(self, replay_ingestion_id: str | None) -> ReplayWorkbenchSnapshotPayload | None:
        if not replay_ingestion_id:
            return None
        replay_ingestion = self._repository.get_ingestion(replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            return None
        return ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)

    @staticmethod
    def _hash_input(payload: dict[str, Any]) -> str:
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=ReplayWorkbenchPromptTraceService._json_default)
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()

    @staticmethod
    def _truncate_value(value: Any, *, truncation: dict[str, Any], path: str, max_chars: int = 2200, max_items: int = 24) -> Any:
        if isinstance(value, str):
            if len(value) <= max_chars:
                return value
            truncation[path] = {"original_chars": len(value), "max_chars": max_chars}
            return value[:max_chars] + "..."
        if isinstance(value, list):
            trimmed = value[:max_items]
            if len(value) > max_items:
                truncation[path] = {"original_items": len(value), "max_items": max_items}
            return [
                ReplayWorkbenchPromptTraceService._truncate_value(item, truncation=truncation, path=f"{path}[{index}]")
                for index, item in enumerate(trimmed)
            ]
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                result[key] = ReplayWorkbenchPromptTraceService._truncate_value(
                    item,
                    truncation=truncation,
                    path=f"{path}.{key}",
                    max_chars=max_chars,
                    max_items=max_items,
                )
            return result
        return value

    @staticmethod
    def _json_default(value: object) -> str:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")

    def _trace_model(self, stored: StoredPromptTrace) -> PromptTrace:
        snapshot = stored.snapshot if isinstance(stored.snapshot, dict) else {}
        metadata = stored.metadata if isinstance(stored.metadata, dict) else {}
        context_blocks = snapshot.get("context_blocks")
        if not isinstance(context_blocks, list):
            context_blocks = metadata.get("block_version_refs")
        if not isinstance(context_blocks, list):
            context_blocks = []
        block_version_refs = metadata.get("block_version_refs")
        if not isinstance(block_version_refs, list):
            block_version_refs = context_blocks
        return PromptTrace(
            prompt_trace_id=stored.prompt_trace_id,
            session_id=stored.session_id,
            message_id=stored.message_id,
            symbol=stored.symbol,
            timeframe=stored.timeframe,
            analysis_type=stored.analysis_type,
            analysis_range=stored.analysis_range,
            analysis_style=stored.analysis_style,
            selected_block_ids=stored.selected_block_ids,
            pinned_block_ids=stored.pinned_block_ids,
            attached_event_ids=stored.attached_event_ids,
            prompt_block_summaries=[PromptTraceBlockSummary.model_validate(item) for item in stored.prompt_block_summaries],
            bar_window_summary=stored.bar_window_summary,
            manual_selection_summary=stored.manual_selection_summary,
            memory_summary=stored.memory_summary,
            final_system_prompt=stored.final_system_prompt,
            final_user_prompt=stored.final_user_prompt,
            model_name=stored.model_name,
            model_input_hash=stored.model_input_hash,
            context_version=snapshot.get("context_version") or metadata.get("context_version"),
            context_blocks=context_blocks,
            reply_window=snapshot.get("reply_window") if isinstance(snapshot.get("reply_window"), dict) else (
                metadata.get("reply_window") if isinstance(metadata.get("reply_window"), dict) else {}
            ),
            reply_window_anchor=snapshot.get("reply_window_anchor") or metadata.get("reply_window_anchor"),
            block_version_refs=block_version_refs,
            snapshot=snapshot,
            metadata=metadata,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )
