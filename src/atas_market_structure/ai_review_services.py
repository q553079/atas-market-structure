from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Protocol
from uuid import uuid4

from openai import OpenAI

from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    MachineStrategyCard,
    ReplayAiChatContent,
    ReplayAiChatMessage,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiChatResponse,
    ReplayOperatorEntryRecord,
    ReplayManualRegionAnnotationRecord,
    ReplayAiReviewContent,
    ReplayAiReviewRequest,
    ReplayAiReviewResponse,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.strategy_library_services import StrategyLibraryService


class ReplayAiReviewUnavailableError(RuntimeError):
    """Raised when AI review cannot be executed because provider configuration is missing."""


class ReplayAiReviewNotFoundError(RuntimeError):
    """Raised when the requested replay packet does not exist."""


class ReplayAiReviewer(Protocol):
    def generate_review(
        self,
        payload: ReplayWorkbenchSnapshotPayload,
        *,
        operator_entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord],
        model_override: str | None = None,
    ) -> tuple[str, str, ReplayAiReviewContent]:
        ...


class ReplayAiChatAssistant(Protocol):
    def generate_reply(
        self,
        payload: ReplayWorkbenchSnapshotPayload,
        *,
        strategy_cards: list[MachineStrategyCard],
        operator_entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord],
        live_context_messages: list[AdapterContinuousStatePayload],
        preset: ReplayAiChatPreset,
        user_message: str,
        history: list[ReplayAiChatMessage],
        model_override: str | None = None,
    ) -> tuple[str, str, ReplayAiChatContent]:
        ...


class OpenAiReplayReviewer:
    """OpenAI-compatible replay reviewer using chat-completions JSON output."""

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        model: str,
        base_url: str | None,
        timeout_seconds: float,
    ) -> None:
        self._provider_name = provider_name
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    def generate_review(
        self,
        payload: ReplayWorkbenchSnapshotPayload,
        *,
        operator_entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord],
        model_override: str | None = None,
    ) -> tuple[str, str, ReplayAiReviewContent]:
        if not self._api_key:
            raise ReplayAiReviewUnavailableError(f"{self._provider_name} API key is not configured.")

        client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url or None,
            timeout=self._timeout_seconds,
        )
        chosen_model = model_override or self._model
        compact_payload = self._compact_payload(payload, operator_entries, manual_regions)
        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are reviewing a replay packet for short-term futures market structure. "
                        "Use only the supplied observed facts, event annotations, focus regions, strategy candidates, "
                        "and operator-recorded entries. Do not invent unobserved order-flow facts. "
                        "Return only valid JSON matching the supplied schema. "
                        "Review each operator entry against broad context and local trigger quality. "
                        "Identify where the operator should not open and what conditions should have been waited for."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "schema": ReplayAiReviewContent.model_json_schema(),
                            "replay_packet": compact_payload,
                        },
                        ensure_ascii=False,
                        default=_json_default,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1800,
        )
        raw_text = response.choices[0].message.content or ""
        if not raw_text.strip():
            raise ReplayAiReviewUnavailableError("AI review returned no text output.")
        parsed = ReplayAiReviewContent.model_validate_json(self._extract_json_text(raw_text))
        return self._provider_name, chosen_model, parsed

    @staticmethod
    def _compact_payload(
        payload: ReplayWorkbenchSnapshotPayload,
        operator_entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord],
    ) -> dict[str, object]:
        candles = payload.candles
        sampled_candles = candles[-150:] if len(candles) > 150 else candles
        candle_high = max((item.high for item in candles), default=None)
        candle_low = min((item.low for item in candles), default=None)
        return {
            "replay_snapshot_id": payload.replay_snapshot_id,
            "instrument": payload.instrument.model_dump(mode="json"),
            "display_timeframe": payload.display_timeframe,
            "window_start": payload.window_start.isoformat(),
            "window_end": payload.window_end.isoformat(),
            "candle_summary": {
                "count": len(candles),
                "high": candle_high,
                "low": candle_low,
                "first_close": candles[0].close if candles else None,
                "last_close": candles[-1].close if candles else None,
            },
            "sampled_candles": [item.model_dump(mode="json") for item in sampled_candles],
            "event_annotations": [item.model_dump(mode="json") for item in payload.event_annotations],
            "focus_regions": [item.model_dump(mode="json") for item in payload.focus_regions],
            "strategy_candidates": [item.model_dump(mode="json") for item in payload.strategy_candidates],
            "ai_briefing": payload.ai_briefing.model_dump(mode="json") if payload.ai_briefing else None,
            "operator_entries": [item.model_dump(mode="json") for item in operator_entries],
            "manual_regions": [item.model_dump(mode="json") for item in manual_regions],
            "raw_features": payload.raw_features,
        }

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```JSON").removeprefix("```").strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        return text


class OpenAiReplayChatAssistant:
    """OpenAI-compatible replay chat assistant with strategy-library-first prompts."""

    _PRESET_INSTRUCTIONS: dict[ReplayAiChatPreset, str] = {
        ReplayAiChatPreset.GENERAL: (
            "Summarize the current market script, the most important no-trade areas, "
            "and the next context-sensitive questions the operator should answer."
        ),
        ReplayAiChatPreset.RECENT_20_BARS: (
            "Focus on the most recent 20 bars. Explain the local sequence, initiative quality, "
            "and where a scalp entry should not be opened."
        ),
        ReplayAiChatPreset.RECENT_20_MINUTES: (
            "Focus on the most recent 20 minutes of bars. Explain short-term rotation, drive quality, "
            "and whether the local context supports continuation, pause, or reversal."
        ),
        ReplayAiChatPreset.FOCUS_REGIONS: (
            "Rank the highest-priority focus regions from the replay packet. Explain which regions matter now, "
            "which are already consumed, and what reaction would confirm or reject each region."
        ),
        ReplayAiChatPreset.TRAPPED_LARGE_ORDERS: (
            "Evaluate whether any large order or defended price now looks trapped. Use strategy candidates first, "
            "then replay events, then live depth context. Be explicit about what evidence is still missing."
        ),
        ReplayAiChatPreset.LIVE_DEPTH: (
            "Prioritize live resting-order and depth behavior. Explain whether the current depth supports attraction, "
            "absorption, spoof risk, or exhaustion, and where the operator should avoid opening."
        ),
    }

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        model: str,
        base_url: str | None,
        timeout_seconds: float,
    ) -> None:
        self._provider_name = provider_name
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    def generate_reply(
        self,
        payload: ReplayWorkbenchSnapshotPayload,
        *,
        strategy_cards: list[MachineStrategyCard],
        operator_entries: list[ReplayOperatorEntryRecord],
        manual_regions: list[ReplayManualRegionAnnotationRecord],
        live_context_messages: list[AdapterContinuousStatePayload],
        preset: ReplayAiChatPreset,
        user_message: str,
        history: list[ReplayAiChatMessage],
        model_override: str | None = None,
    ) -> tuple[str, str, ReplayAiChatContent]:
        if not self._api_key:
            raise ReplayAiReviewUnavailableError(f"{self._provider_name} API key is not configured.")

        client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url or None,
            timeout=self._timeout_seconds,
        )
        chosen_model = model_override or self._model
        compact_payload = _compact_replay_payload(payload, operator_entries, manual_regions, preset=preset)
        compact_live_context = _compact_live_context_messages(live_context_messages)
        compact_strategy_cards = StrategyLibraryService.compact_cards(strategy_cards)
        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the replay-workbench copilot for short-term futures review. "
                        "Always reason in this order: strategy candidates first, then replay events/focus regions, "
                        "then operator entries, then live depth context. "
                        "Be explicit about where the operator should not open. "
                        "When evidence is missing, say so instead of inventing order-flow facts. "
                        "Return only valid JSON matching the supplied schema."
                    ),
                },
                *[
                    {
                        "role": item.role,
                        "content": item.content,
                    }
                    for item in history[-10:]
                ],
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "schema": ReplayAiChatContent.model_json_schema(),
                            "preset": preset.value,
                            "preset_instruction": self._PRESET_INSTRUCTIONS[preset],
                            "strategy_candidates_first": True,
                            "strategy_library_cards": compact_strategy_cards,
                            "latest_user_request": user_message,
                            "replay_packet": compact_payload,
                            "live_context": compact_live_context,
                        },
                        ensure_ascii=False,
                        default=_json_default,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1500,
        )
        raw_text = response.choices[0].message.content or ""
        if not raw_text.strip():
            raise ReplayAiReviewUnavailableError("AI chat returned no text output.")
        parsed = ReplayAiChatContent.model_validate_json(OpenAiReplayReviewer._extract_json_text(raw_text))
        return self._provider_name, chosen_model, parsed


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


class ReplayAiReviewService:
    """Runs and stores structured AI review for replay-workbench packets."""

    def __init__(
        self,
        repository: AnalysisRepository,
        reviewer: ReplayAiReviewer,
    ) -> None:
        self._repository = repository
        self._reviewer = reviewer

    def review_replay(self, request: ReplayAiReviewRequest) -> ReplayAiReviewResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayAiReviewNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        if not request.force_refresh:
            existing = self._find_existing_review(request.replay_ingestion_id)
            if existing is not None:
                return ReplayAiReviewResponse.model_validate(existing.observed_payload)

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        operator_entries = self._list_operator_entries(request.replay_ingestion_id)
        manual_regions = _list_manual_regions(self._repository, request.replay_ingestion_id)
        provider, model, review = self._reviewer.generate_review(
            replay_payload,
            operator_entries=operator_entries,
            manual_regions=manual_regions,
            model_override=request.model_override,
        )
        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        response = ReplayAiReviewResponse(
            ingestion_id=ingestion_id,
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            stored_at=stored_at,
            provider=provider,
            model=model,
            review=review,
            raw_text=json.dumps(review.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="replay_ai_review",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=response.model_dump(mode="json"),
            stored_at=stored_at,
        )
        return response

    def _find_existing_review(self, replay_ingestion_id: str):
        for stored in self._repository.list_ingestions(ingestion_kind="replay_ai_review", limit=200):
            if stored.observed_payload.get("replay_ingestion_id") == replay_ingestion_id:
                return stored
        return None

    def _list_operator_entries(self, replay_ingestion_id: str) -> list[ReplayOperatorEntryRecord]:
        entries: list[ReplayOperatorEntryRecord] = []
        for stored in self._repository.list_ingestions(ingestion_kind="replay_operator_entry", limit=1000):
            if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
                continue
            entries.append(ReplayOperatorEntryRecord.model_validate(stored.observed_payload))
        entries.sort(key=lambda item: item.executed_at)
        return entries


class ReplayAiChatService:
    """Runs and stores contextual AI chat turns over one replay-workbench packet."""

    def __init__(
        self,
        repository: AnalysisRepository,
        assistant: ReplayAiChatAssistant,
        strategy_library_service: StrategyLibraryService | None = None,
    ) -> None:
        self._repository = repository
        self._assistant = assistant
        self._strategy_library_service = strategy_library_service or StrategyLibraryService()

    def chat(self, request: ReplayAiChatRequest) -> ReplayAiChatResponse:
        replay_ingestion = self._repository.get_ingestion(request.replay_ingestion_id)
        if replay_ingestion is None or replay_ingestion.ingestion_kind != "replay_workbench_snapshot":
            raise ReplayAiReviewNotFoundError(f"Replay ingestion '{request.replay_ingestion_id}' not found.")

        replay_payload = ReplayWorkbenchSnapshotPayload.model_validate(replay_ingestion.observed_payload)
        operator_entries = _list_operator_entries(self._repository, request.replay_ingestion_id)
        manual_regions = _list_manual_regions(self._repository, request.replay_ingestion_id)
        live_context_messages = (
            _list_live_context_messages(self._repository, replay_payload) if request.include_live_context else []
        )
        strategy_cards = self._strategy_library_service.resolve_relevant_cards(replay_payload, preset=request.preset)
        provider, model, content = self._assistant.generate_reply(
            replay_payload,
            strategy_cards=strategy_cards,
            operator_entries=operator_entries,
            manual_regions=manual_regions,
            live_context_messages=live_context_messages,
            preset=request.preset,
            user_message=request.user_message,
            history=request.history,
            model_override=request.model_override,
        )
        known_strategy_ids = {item.strategy_id for item in replay_payload.strategy_candidates}
        known_strategy_ids.update(item.strategy_id for item in strategy_cards)
        referenced_strategy_ids = [
            strategy_id for strategy_id in content.referenced_strategy_ids if strategy_id in known_strategy_ids
        ]
        generated_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        response = ReplayAiChatResponse(
            ingestion_id=ingestion_id,
            replay_ingestion_id=request.replay_ingestion_id,
            replay_snapshot_id=replay_payload.replay_snapshot_id,
            generated_at=generated_at,
            provider=provider,
            model=model,
            preset=request.preset,
            request_message=request.user_message,
            reply_text=content.reply_text,
            live_context_summary=content.live_context_summary,
            referenced_strategy_ids=referenced_strategy_ids,
            follow_up_suggestions=content.follow_up_suggestions,
            raw_text=json.dumps(content.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="replay_ai_chat",
            source_snapshot_id=replay_payload.replay_snapshot_id,
            instrument_symbol=replay_payload.instrument.symbol,
            observed_payload=response.model_dump(mode="json"),
            stored_at=generated_at,
        )
        return response


def _compact_replay_payload(
    payload: ReplayWorkbenchSnapshotPayload,
    operator_entries: list[ReplayOperatorEntryRecord],
    manual_regions: list[ReplayManualRegionAnnotationRecord],
    *,
    preset: ReplayAiChatPreset,
) -> dict[str, object]:
    candles = payload.candles
    if preset == ReplayAiChatPreset.RECENT_20_BARS:
        sampled_candles = candles[-20:]
    elif preset == ReplayAiChatPreset.RECENT_20_MINUTES and candles:
        cutoff = payload.window_end - _infer_minutes_delta(payload.display_timeframe, 20)
        sampled_candles = [item for item in candles if item.ended_at >= cutoff]
    else:
        sampled_candles = candles[-80:] if len(candles) > 80 else candles
    sampled_events = payload.event_annotations[-30:] if len(payload.event_annotations) > 30 else payload.event_annotations
    candle_high = max((item.high for item in candles), default=None)
    candle_low = min((item.low for item in candles), default=None)
    return {
        "replay_snapshot_id": payload.replay_snapshot_id,
        "instrument": payload.instrument.model_dump(mode="json"),
        "display_timeframe": payload.display_timeframe,
        "window_start": payload.window_start.isoformat(),
        "window_end": payload.window_end.isoformat(),
        "candle_summary": {
            "count": len(candles),
            "high": candle_high,
            "low": candle_low,
            "first_close": candles[0].close if candles else None,
            "last_close": candles[-1].close if candles else None,
        },
        "sampled_candles": [item.model_dump(mode="json") for item in sampled_candles],
        "event_annotations": [item.model_dump(mode="json") for item in sampled_events],
        "focus_regions": [item.model_dump(mode="json") for item in payload.focus_regions],
        "strategy_candidates": [item.model_dump(mode="json") for item in payload.strategy_candidates],
        "ai_briefing": payload.ai_briefing.model_dump(mode="json") if payload.ai_briefing else None,
        "operator_entries": [item.model_dump(mode="json") for item in operator_entries],
        "manual_regions": [item.model_dump(mode="json") for item in manual_regions],
        "raw_features": payload.raw_features,
    }


def _infer_minutes_delta(timeframe: object, minutes: int) -> timedelta:
    timeframe_value = str(timeframe)
    if timeframe_value.endswith("m"):
        base_minutes = max(1, int(timeframe_value[:-1]))
        return timedelta(minutes=max(minutes, base_minutes))
    if timeframe_value.endswith("h"):
        base_hours = max(1, int(timeframe_value[:-1]))
        return timedelta(minutes=max(minutes, base_hours * 60))
    return timedelta(minutes=minutes)


def _compact_live_context_messages(messages: list[AdapterContinuousStatePayload]) -> dict[str, object]:
    if not messages:
        return {
            "message_count": 0,
            "summary": [],
            "latest": None,
        }
    latest = messages[-1]
    summary = _summarize_live_context_messages(messages)
    depth_coverage = latest.depth_coverage.model_dump(mode="json") if latest.depth_coverage is not None else None
    trade_summary = latest.trade_summary.model_dump(mode="json") if latest.trade_summary is not None else None
    price_state = latest.price_state.model_dump(mode="json") if latest.price_state is not None else None
    return {
        "message_count": len(messages),
        "summary": summary,
        "latest": {
            "emitted_at": latest.emitted_at,
            "price_state": price_state,
            "depth_coverage": depth_coverage,
            "trade_summary": trade_summary,
            "same_price_replenishment": [item.model_dump(mode="json") for item in latest.same_price_replenishment],
            "significant_liquidity": [item.model_dump(mode="json") for item in latest.significant_liquidity],
            "active_initiative_drive": (
                latest.active_initiative_drive.model_dump(mode="json") if latest.active_initiative_drive else None
            ),
            "active_post_harvest_response": (
                latest.active_post_harvest_response.model_dump(mode="json")
                if latest.active_post_harvest_response
                else None
            ),
            "gap_reference": latest.gap_reference.model_dump(mode="json") if latest.gap_reference else None,
        },
    }


def _summarize_live_context_messages(messages: list[AdapterContinuousStatePayload]) -> list[str]:
    if not messages:
        return []
    latest = messages[-1]
    depth_coverage = latest.depth_coverage
    price_state = latest.price_state
    trade_summary = latest.trade_summary
    summary = []
    if depth_coverage is not None:
        summary.append(
            f"depth_coverage={depth_coverage.coverage_state.value} levels={depth_coverage.snapshot_level_count}"
        )
    else:
        summary.append("depth_coverage=unknown levels=unknown")
    if price_state is not None:
        summary.append(f"best_bid={price_state.best_bid} best_ask={price_state.best_ask}")
        summary.append(
            f"last_price={price_state.last_price} local_range={price_state.local_range_low}-{price_state.local_range_high}"
        )
    if trade_summary is not None:
        summary.append(
            f"net_delta={trade_summary.net_delta} aggressive_buy={trade_summary.aggressive_buy_volume} aggressive_sell={trade_summary.aggressive_sell_volume}"
        )
    else:
        summary.append("net_delta=unknown aggressive_buy=unknown aggressive_sell=unknown")
    summary.append(
        f"significant_liquidity={len(latest.significant_liquidity)} same_price_replenishment={len(latest.same_price_replenishment)}"
    )
    if latest.active_initiative_drive is not None:
        summary.append(
            f"active_drive side={latest.active_initiative_drive.side.value} travel_ticks={latest.active_initiative_drive.price_travel_ticks} net_delta={latest.active_initiative_drive.net_delta}"
        )
    if latest.active_post_harvest_response is not None:
        summary.append(
            f"post_harvest outcome={latest.active_post_harvest_response.outcome.value} reaction_ticks={latest.active_post_harvest_response.reaction_ticks}"
        )
    if latest.gap_reference is not None:
        summary.append(
            f"gap fill_ratio={latest.gap_reference.fill_ratio:.2f} attempts={latest.gap_reference.fill_attempt_count}"
        )
    if latest.same_price_replenishment:
        dominant = max(latest.same_price_replenishment, key=lambda item: item.replenishment_count)
        summary.append(
            f"dominant_replenishment price={dominant.price} count={dominant.replenishment_count} side={dominant.side.value}"
        )
    return summary


def _list_operator_entries(
    repository: AnalysisRepository,
    replay_ingestion_id: str,
) -> list[ReplayOperatorEntryRecord]:
    entries: list[ReplayOperatorEntryRecord] = []
    for stored in repository.list_ingestions(ingestion_kind="replay_operator_entry", limit=1000):
        if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
            continue
        entries.append(ReplayOperatorEntryRecord.model_validate(stored.observed_payload))
    entries.sort(key=lambda item: item.executed_at)
    return entries


def _list_manual_regions(
    repository: AnalysisRepository,
    replay_ingestion_id: str,
) -> list[ReplayManualRegionAnnotationRecord]:
    regions: list[ReplayManualRegionAnnotationRecord] = []
    for stored in repository.list_ingestions(ingestion_kind="replay_manual_region", limit=1000):
        if stored.observed_payload.get("replay_ingestion_id") != replay_ingestion_id:
            continue
        regions.append(ReplayManualRegionAnnotationRecord.model_validate(stored.observed_payload))
    regions.sort(key=lambda item: (item.started_at, item.price_low))
    return regions


def _list_live_context_messages(
    repository: AnalysisRepository,
    payload: ReplayWorkbenchSnapshotPayload,
) -> list[AdapterContinuousStatePayload]:
    ingestions = repository.list_ingestions(
        ingestion_kind="adapter_continuous_state",
        instrument_symbol=payload.instrument.symbol,
        limit=400,
    )
    messages: list[AdapterContinuousStatePayload] = []
    for stored in ingestions:
        observed = stored.observed_payload
        messages.append(AdapterContinuousStatePayload.model_validate(observed))
    messages.sort(key=lambda item: item.emitted_at)
    return messages[-60:]
