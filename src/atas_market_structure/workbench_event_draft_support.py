from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any, Iterable
from uuid import uuid4

from atas_market_structure.models import (
    EventCandidateKind,
    EventCandidateLifecycleState,
    EventCandidateSourceType,
)
from atas_market_structure.repository import (
    StoredChatAnnotation,
    StoredChatPlanCard,
    StoredChatSession,
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventStreamEntry,
)


_RANGE_PATTERN = re.compile(r"(?P<low>\d{4,5}(?:\.\d{1,2})?)\s*[-~到至]\s*(?P<high>\d{4,5}(?:\.\d{1,2})?)")
_SINGLE_PATTERN = re.compile(r"\d{4,5}(?:\.\d{1,2})?")
_RISK_PATTERN = re.compile(r"风险|失效|谨慎|放弃|不要追|不能追|止损|跌破|站不上", re.IGNORECASE)
_SUPPORT_PATTERN = re.compile(r"支撑|需求|回踩|多头|防守", re.IGNORECASE)
_RESISTANCE_PATTERN = re.compile(r"阻力|压力|供给|反抽|空头", re.IGNORECASE)
_ENTRY_PATTERN = re.compile(r"入场|回踩|关注|突破|关键价位|盯住", re.IGNORECASE)
_TARGET_PATTERN = re.compile(r"止盈|目标|TP", re.IGNORECASE)
_PLAN_PATTERN = re.compile(r"计划|入场|止损|止盈|TP|做多|做空", re.IGNORECASE)
_MARKET_EVENT_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"延续|continuation", re.IGNORECASE), "延续结构"),
    (re.compile(r"均值回归|mean reversion|balance", re.IGNORECASE), "均值回归"),
    (re.compile(r"吸收|absorption", re.IGNORECASE), "吸收结构"),
    (re.compile(r"反转|reversal", re.IGNORECASE), "反转准备"),
)


@dataclass
class ReplyEventBackboneResult:
    """Internal result of reply-time extraction and derived projection."""

    candidates: list[StoredEventCandidate]
    stream_entries: list[StoredEventStreamEntry]
    memory_entries: list[StoredEventMemoryEntry]
    annotations: list[StoredChatAnnotation]
    plan_cards: list[StoredChatPlanCard]


@dataclass
class _EventDraft:
    candidate_kind: EventCandidateKind
    title: str
    summary: str
    symbol: str
    timeframe: str
    source_type: EventCandidateSourceType
    source_message_id: str | None
    source_prompt_trace_id: str | None
    anchor_start_ts: datetime | None = None
    anchor_end_ts: datetime | None = None
    price_lower: float | None = None
    price_upper: float | None = None
    price_ref: float | None = None
    side_hint: str | None = None
    confidence: float | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    invalidation_rule: dict[str, Any] | None = None
    evaluation_window: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    dedup_key: str | None = None


class ReplayWorkbenchEventDraftSupport:
    def _extract_candidate_drafts(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        reply_text: str,
        response_payload: dict[str, Any],
    ) -> list[_EventDraft]:
        drafts: list[_EventDraft] = []
        evidence_refs = [{"type": "assistant_message", "message_id": source_message_id}]
        for item in response_payload.get("annotations", []) or []:
            if not isinstance(item, dict):
                continue
            draft = self._draft_from_structured_annotation(
                session=session,
                source_message_id=source_message_id,
                candidate=item,
                evidence_refs=evidence_refs,
            )
            if draft is not None:
                drafts.append(draft)
        for item in response_payload.get("plan_cards", []) or []:
            if not isinstance(item, dict):
                continue
            drafts.append(
                self._draft_from_structured_plan(
                    session=session,
                    source_message_id=source_message_id,
                    candidate=item,
                    evidence_refs=evidence_refs,
                )
            )
        drafts.extend(
            self._drafts_from_reply_text(
                session=session,
                source_message_id=source_message_id,
                reply_text=reply_text,
                evidence_refs=evidence_refs,
                skip_plan=bool(response_payload.get("plan_cards")),
                skip_annotation=bool(response_payload.get("annotations")),
            )
        )
        return self._dedupe_drafts(drafts)

    def _draft_from_structured_annotation(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        candidate: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
    ) -> _EventDraft | None:
        raw_type = str(candidate.get("type") or "").strip().lower()
        if not raw_type:
            return None
        label = str(candidate.get("label") or "").strip()
        reason = str(candidate.get("reason") or "").strip()
        side_hint = self._normalize_side(candidate.get("side"))
        price_lower = self._coerce_float(candidate.get("price_low"))
        price_upper = self._coerce_float(candidate.get("price_high"))
        entry_price = self._coerce_float(candidate.get("entry_price"))
        stop_price = self._coerce_float(candidate.get("stop_price"))
        target_price = self._coerce_float(candidate.get("target_price"))
        start_time = self._coerce_datetime(candidate.get("start_time"))
        end_time = self._coerce_datetime(candidate.get("end_time"))
        expires_at = self._coerce_datetime(candidate.get("expires_at"))
        confidence = self._coerce_float(candidate.get("confidence"))
        title = label or {
            "plan": "计划意图",
            "plan_intent": "计划意图",
            "price_zone": "价格区域",
            "risk_note": "风险提示",
            "market_event": "市场事件",
        }.get(raw_type, "关键价位")
        annotation_type = self._normalize_annotation_projection_type(
            raw_type=raw_type,
            label=label,
            reason=reason,
            side_hint=side_hint,
            price_lower=price_lower,
            price_upper=price_upper,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )
        payload_metadata = {
            "raw_annotation_type": raw_type,
            "raw_payload": dict(candidate),
            "source_kind": candidate.get("source_kind"),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "tp_level": self._coerce_int(candidate.get("tp_level")),
            "path_points": list(candidate.get("path_points") or []) if isinstance(candidate.get("path_points"), list) else [],
            "compat_annotation_type": annotation_type,
            "compat_annotation_event_kind": self._derive_annotation_event_kind(annotation_type, plan_like=raw_type in {"plan", "plan_intent"}),
            "compat_emit_annotation": True,
            "priority": self._coerce_int(candidate.get("priority")),
            "visible": bool(candidate.get("visible", True)),
            "pinned": bool(candidate.get("pinned", False)),
        }
        if raw_type in {"plan", "plan_intent"}:
            return _EventDraft(
                candidate_kind=EventCandidateKind.PLAN_INTENT,
                title=title,
                summary=reason or title,
                symbol=session.symbol,
                timeframe=session.timeframe,
                source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
                source_message_id=source_message_id,
                source_prompt_trace_id=None,
                anchor_start_ts=start_time,
                anchor_end_ts=end_time or expires_at,
                price_lower=price_lower,
                price_upper=price_upper,
                price_ref=entry_price or self._midpoint(price_lower, price_upper) or target_price or stop_price,
                side_hint=side_hint,
                confidence=confidence,
                evidence_refs=[*evidence_refs, {"type": "structured_annotation", "annotation_type": raw_type}],
                invalidation_rule={"stop_price": stop_price} if stop_price is not None else {},
                evaluation_window={"expires_at": expires_at.isoformat()} if expires_at is not None else {},
                metadata=payload_metadata,
            )
        if raw_type in {"risk", "risk_note", "no_trade_zone", "stop_loss"}:
            return _EventDraft(
                candidate_kind=EventCandidateKind.RISK_NOTE,
                title=title,
                summary=reason or title,
                symbol=session.symbol,
                timeframe=session.timeframe,
                source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
                source_message_id=source_message_id,
                source_prompt_trace_id=None,
                anchor_start_ts=start_time,
                anchor_end_ts=end_time or expires_at,
                price_lower=price_lower,
                price_upper=price_upper,
                price_ref=stop_price or self._midpoint(price_lower, price_upper) or entry_price,
                side_hint=side_hint,
                confidence=confidence,
                evidence_refs=[*evidence_refs, {"type": "structured_annotation", "annotation_type": raw_type}],
                invalidation_rule={"stop_price": stop_price} if stop_price is not None else {},
                evaluation_window={"expires_at": expires_at.isoformat()} if expires_at is not None else {},
                metadata=payload_metadata,
            )
        if raw_type in {"market_event", "event_marker", "event"}:
            return _EventDraft(
                candidate_kind=EventCandidateKind.MARKET_EVENT,
                title=title,
                summary=reason or title,
                symbol=session.symbol,
                timeframe=session.timeframe,
                source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
                source_message_id=source_message_id,
                source_prompt_trace_id=None,
                anchor_start_ts=start_time,
                anchor_end_ts=end_time or expires_at,
                price_lower=price_lower,
                price_upper=price_upper,
                price_ref=entry_price or self._midpoint(price_lower, price_upper) or target_price,
                side_hint=side_hint,
                confidence=confidence,
                evidence_refs=[*evidence_refs, {"type": "structured_annotation", "annotation_type": raw_type}],
                evaluation_window={"expires_at": expires_at.isoformat()} if expires_at is not None else {},
                metadata=payload_metadata,
            )
        if raw_type in {"zone", "price_zone", "support_zone", "resistance_zone"} or price_lower is not None or price_upper is not None:
            return _EventDraft(
                candidate_kind=EventCandidateKind.PRICE_ZONE,
                title=title,
                summary=reason or title,
                symbol=session.symbol,
                timeframe=session.timeframe,
                source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
                source_message_id=source_message_id,
                source_prompt_trace_id=None,
                anchor_start_ts=start_time,
                anchor_end_ts=end_time or expires_at,
                price_lower=price_lower,
                price_upper=price_upper,
                price_ref=self._midpoint(price_lower, price_upper) or entry_price,
                side_hint=side_hint,
                confidence=confidence,
                evidence_refs=[*evidence_refs, {"type": "structured_annotation", "annotation_type": raw_type}],
                evaluation_window={"expires_at": expires_at.isoformat()} if expires_at is not None else {},
                metadata=payload_metadata,
            )
        return _EventDraft(
            candidate_kind=EventCandidateKind.KEY_LEVEL,
            title=title,
            summary=reason or title,
            symbol=session.symbol,
            timeframe=session.timeframe,
            source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
            source_message_id=source_message_id,
            source_prompt_trace_id=None,
            anchor_start_ts=start_time,
            anchor_end_ts=end_time or expires_at,
            price_lower=price_lower,
            price_upper=price_upper,
            price_ref=entry_price or stop_price or target_price or self._midpoint(price_lower, price_upper),
            side_hint=side_hint,
            confidence=confidence,
            evidence_refs=[*evidence_refs, {"type": "structured_annotation", "annotation_type": raw_type}],
            invalidation_rule={"stop_price": stop_price} if stop_price is not None else {},
            evaluation_window={"expires_at": expires_at.isoformat()} if expires_at is not None else {},
            metadata=payload_metadata,
        )

    def _draft_from_structured_plan(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        candidate: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
    ) -> _EventDraft:
        title = str(candidate.get("title") or "").strip() or "AI计划卡"
        summary = str(candidate.get("summary") or "").strip() or str(candidate.get("notes") or "").strip() or title
        side_hint = self._normalize_side(candidate.get("side")) or "buy"
        entry_price = self._coerce_float(candidate.get("entry_price"))
        price_lower = self._coerce_float(candidate.get("entry_price_low"))
        price_upper = self._coerce_float(candidate.get("entry_price_high"))
        stop_price = self._coerce_float(candidate.get("stop_price"))
        take_profits = list(candidate.get("take_profits") or []) if isinstance(candidate.get("take_profits"), list) else []
        invalidations = list(candidate.get("invalidations") or []) if isinstance(candidate.get("invalidations"), list) else []
        return _EventDraft(
            candidate_kind=EventCandidateKind.PLAN_INTENT,
            title=title,
            summary=summary,
            symbol=session.symbol,
            timeframe=session.timeframe,
            source_type=EventCandidateSourceType.AI_REPLY_STRUCTURED,
            source_message_id=source_message_id,
            source_prompt_trace_id=None,
            price_lower=price_lower,
            price_upper=price_upper,
            price_ref=entry_price or self._midpoint(price_lower, price_upper),
            side_hint=side_hint,
            confidence=self._coerce_float(candidate.get("confidence")),
            evidence_refs=[*evidence_refs, {"type": "structured_plan"}],
            invalidation_rule={"stop_price": stop_price} if stop_price is not None else {},
            metadata={
                "raw_payload": dict(candidate),
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profits": take_profits,
                "invalidations": invalidations,
                "priority": self._coerce_int(candidate.get("priority")),
                "notes": str(candidate.get("notes") or "").strip(),
                "compat_emit_annotation": False,
            },
        )

    def _drafts_from_reply_text(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        reply_text: str,
        evidence_refs: list[dict[str, Any]],
        skip_plan: bool,
        skip_annotation: bool,
    ) -> list[_EventDraft]:
        text = str(reply_text or "").strip()
        if not text:
            return []
        drafts: list[_EventDraft] = []
        if not skip_annotation:
            drafts.extend(
                self._zone_and_price_drafts_from_text(
                    session=session,
                    source_message_id=source_message_id,
                    reply_text=text,
                    evidence_refs=evidence_refs,
                )
            )
        market_event = self._market_event_draft_from_text(
            session=session,
            source_message_id=source_message_id,
            reply_text=text,
            evidence_refs=evidence_refs,
        )
        if market_event is not None:
            drafts.append(market_event)
        if not skip_plan:
            plan_draft = self._plan_draft_from_text(
                session=session,
                source_message_id=source_message_id,
                reply_text=text,
                evidence_refs=evidence_refs,
            )
            if plan_draft is not None:
                drafts.append(plan_draft)
        return drafts

    def _zone_and_price_drafts_from_text(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        reply_text: str,
        evidence_refs: list[dict[str, Any]],
    ) -> list[_EventDraft]:
        drafts: list[_EventDraft] = []
        range_spans: list[tuple[int, int]] = []
        for match in _RANGE_PATTERN.finditer(reply_text):
            low = self._coerce_float(match.group("low"))
            high = self._coerce_float(match.group("high"))
            if low is None or high is None:
                continue
            price_lower, price_upper = sorted((low, high))
            range_spans.append(match.span())
            sentence = self._extract_sentence(reply_text, match.start(), match.end())
            side_hint = self._normalize_side(
                "sell" if _RESISTANCE_PATTERN.search(sentence) else ("buy" if _SUPPORT_PATTERN.search(sentence) else None)
            )
            is_risk = bool(_RISK_PATTERN.search(sentence))
            annotation_type = "no_trade_zone" if is_risk else self._infer_zone_annotation_type(sentence, side_hint=side_hint)
            drafts.append(
                _EventDraft(
                    candidate_kind=EventCandidateKind.RISK_NOTE if is_risk else EventCandidateKind.PRICE_ZONE,
                    title=("风险区域" if is_risk else {"support_zone": "支撑区域", "resistance_zone": "阻力区域"}.get(annotation_type, "价格区域")),
                    summary=sentence,
                    symbol=session.symbol,
                    timeframe=session.timeframe,
                    source_type=EventCandidateSourceType.AI_REPLY_TEXT,
                    source_message_id=source_message_id,
                    source_prompt_trace_id=None,
                    price_lower=price_lower,
                    price_upper=price_upper,
                    price_ref=self._midpoint(price_lower, price_upper),
                    side_hint=side_hint,
                    evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": sentence}],
                    metadata={
                        "excerpt": sentence,
                        "compat_annotation_type": annotation_type,
                        "compat_annotation_event_kind": "risk" if is_risk else "zone",
                    },
                )
            )
        for match in _SINGLE_PATTERN.finditer(reply_text):
            if any(start <= match.start() and match.end() <= end for start, end in range_spans):
                continue
            value = self._coerce_float(match.group(0))
            if value is None:
                continue
            sentence = self._extract_sentence(reply_text, match.start(), match.end())
            if not any(pattern.search(sentence) for pattern in (_RISK_PATTERN, _ENTRY_PATTERN, _TARGET_PATTERN, _SUPPORT_PATTERN, _RESISTANCE_PATTERN)):
                continue
            if _RISK_PATTERN.search(sentence):
                drafts.append(
                    _EventDraft(
                        candidate_kind=EventCandidateKind.RISK_NOTE,
                        title="风险位",
                        summary=sentence,
                        symbol=session.symbol,
                        timeframe=session.timeframe,
                        source_type=EventCandidateSourceType.AI_REPLY_TEXT,
                        source_message_id=source_message_id,
                        source_prompt_trace_id=None,
                        price_ref=value,
                        side_hint=self._normalize_side(
                            "sell" if _RESISTANCE_PATTERN.search(sentence) else ("buy" if _SUPPORT_PATTERN.search(sentence) else None)
                        ),
                        evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": sentence}],
                        invalidation_rule={"stop_price": value},
                        metadata={
                            "excerpt": sentence,
                            "stop_price": value,
                            "compat_annotation_type": "stop_loss",
                            "compat_annotation_event_kind": "risk",
                        },
                    )
                )
                continue
            if _TARGET_PATTERN.search(sentence):
                drafts.append(
                    _EventDraft(
                        candidate_kind=EventCandidateKind.KEY_LEVEL,
                        title="目标位",
                        summary=sentence,
                        symbol=session.symbol,
                        timeframe=session.timeframe,
                        source_type=EventCandidateSourceType.AI_REPLY_TEXT,
                        source_message_id=source_message_id,
                        source_prompt_trace_id=None,
                        price_ref=value,
                        side_hint=self._normalize_side(
                            "sell" if _RESISTANCE_PATTERN.search(sentence) else ("buy" if _SUPPORT_PATTERN.search(sentence) else None)
                        ),
                        evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": sentence}],
                        metadata={
                            "excerpt": sentence,
                            "target_price": value,
                            "compat_annotation_type": "take_profit",
                            "compat_annotation_event_kind": "price",
                        },
                    )
                )
                continue
            side_hint = self._normalize_side(
                "sell" if _RESISTANCE_PATTERN.search(sentence) else ("buy" if _SUPPORT_PATTERN.search(sentence) else None)
            )
            drafts.append(
                _EventDraft(
                    candidate_kind=EventCandidateKind.KEY_LEVEL,
                    title="关键价位",
                    summary=sentence,
                    symbol=session.symbol,
                    timeframe=session.timeframe,
                    source_type=EventCandidateSourceType.AI_REPLY_TEXT,
                    source_message_id=source_message_id,
                    source_prompt_trace_id=None,
                    price_ref=value,
                    side_hint=side_hint,
                    evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": sentence}],
                    metadata={
                        "excerpt": sentence,
                        "entry_price": value,
                        "compat_annotation_type": "entry_line",
                        "compat_annotation_event_kind": "price",
                    },
                )
            )
        return drafts

    def _market_event_draft_from_text(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        reply_text: str,
        evidence_refs: list[dict[str, Any]],
    ) -> _EventDraft | None:
        for pattern, title in _MARKET_EVENT_KEYWORDS:
            match = pattern.search(reply_text)
            if match is None:
                continue
            sentence = self._extract_sentence(reply_text, match.start(), match.end())
            return _EventDraft(
                candidate_kind=EventCandidateKind.MARKET_EVENT,
                title=title,
                summary=sentence,
                symbol=session.symbol,
                timeframe=session.timeframe,
                source_type=EventCandidateSourceType.AI_REPLY_TEXT,
                source_message_id=source_message_id,
                source_prompt_trace_id=None,
                evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": sentence}],
                metadata={
                    "excerpt": sentence,
                    "keyword": title,
                    "compat_annotation_type": "event_marker",
                    "compat_annotation_event_kind": "event",
                },
            )
        return None

    def _plan_draft_from_text(
        self,
        *,
        session: StoredChatSession,
        source_message_id: str,
        reply_text: str,
        evidence_refs: list[dict[str, Any]],
    ) -> _EventDraft | None:
        if not _PLAN_PATTERN.search(reply_text):
            return None
        prices = [self._coerce_float(item.group(0)) for item in _SINGLE_PATTERN.finditer(reply_text)]
        values = [item for item in prices if item is not None]
        if len(values) < 2:
            return None
        side_hint = self._normalize_side(
            "sell"
            if re.search(r"做空|空头|sell|short", reply_text, re.IGNORECASE) and not re.search(r"做多|buy|long", reply_text, re.IGNORECASE)
            else "buy"
        )
        entry_price = values[0]
        stop_price = values[1] if len(values) > 1 else None
        target_prices = values[2:]
        summary = self._extract_sentence(reply_text, 0, min(len(reply_text), 64))
        take_profits = [{"price": price, "label": f"TP{index + 1}"} for index, price in enumerate(target_prices)]
        invalidations = [f"{'上破' if side_hint == 'sell' else '跌破'} {stop_price} 失效"] if stop_price is not None else []
        return _EventDraft(
            candidate_kind=EventCandidateKind.PLAN_INTENT,
            title="文本计划意图",
            summary=summary,
            symbol=session.symbol,
            timeframe=session.timeframe,
            source_type=EventCandidateSourceType.AI_REPLY_TEXT,
            source_message_id=source_message_id,
            source_prompt_trace_id=None,
            price_ref=entry_price,
            side_hint=side_hint,
            evidence_refs=[*evidence_refs, {"type": "text_excerpt", "excerpt": summary}],
            invalidation_rule={"stop_price": stop_price} if stop_price is not None else {},
            metadata={
                "excerpt": summary,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profits": take_profits,
                "invalidations": invalidations,
                "compat_emit_annotation": False,
            },
        )

    def _save_candidate_from_draft(self, session: StoredChatSession, draft: _EventDraft) -> StoredEventCandidate:
        now = datetime.now(tz=UTC)
        return self._repository.save_event_candidate(
            event_id=f"evt-{uuid4().hex}",
            session_id=session.session_id,
            candidate_kind=draft.candidate_kind.value,
            title=draft.title,
            summary=draft.summary,
            symbol=draft.symbol,
            timeframe=draft.timeframe,
            anchor_start_ts=draft.anchor_start_ts,
            anchor_end_ts=draft.anchor_end_ts,
            price_lower=draft.price_lower,
            price_upper=draft.price_upper,
            price_ref=draft.price_ref,
            side_hint=draft.side_hint,
            confidence=draft.confidence,
            evidence_refs=draft.evidence_refs or [],
            source_type=draft.source_type.value,
            source_message_id=draft.source_message_id,
            source_prompt_trace_id=draft.source_prompt_trace_id,
            lifecycle_state=EventCandidateLifecycleState.CANDIDATE.value,
            invalidation_rule=draft.invalidation_rule or {},
            evaluation_window=draft.evaluation_window or {},
            metadata=draft.metadata or {},
            dedup_key=draft.dedup_key or self._build_dedup_key(draft),
            promoted_projection_type=None,
            promoted_projection_id=None,
            created_at=now,
            updated_at=now,
        )

    def _dedupe_drafts(self, drafts: Iterable[_EventDraft]) -> list[_EventDraft]:
        seen: set[str] = set()
        deduped: list[_EventDraft] = []
        for draft in drafts:
            key = draft.dedup_key or self._build_dedup_key(draft)
            if key in seen:
                continue
            draft.dedup_key = key
            seen.add(key)
            deduped.append(draft)
        return deduped

    def _build_dedup_key(self, draft: _EventDraft) -> str:
        return json.dumps(
            {
                "candidate_kind": draft.candidate_kind.value,
                "title": draft.title,
                "summary": draft.summary,
                "symbol": draft.symbol,
                "timeframe": draft.timeframe,
                "price_lower": round(draft.price_lower, 6) if draft.price_lower is not None else None,
                "price_upper": round(draft.price_upper, 6) if draft.price_upper is not None else None,
                "price_ref": round(draft.price_ref, 6) if draft.price_ref is not None else None,
                "side_hint": draft.side_hint,
                "source_message_id": draft.source_message_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _midpoint(price_lower: float | None, price_upper: float | None) -> float | None:
        if price_lower is None or price_upper is None:
            return None
        return round((price_lower + price_upper) / 2.0, 6)

    @staticmethod
    def _normalize_side(value: Any) -> str | None:
        raw = str(value or "").strip().lower()
        if raw in {"buy", "long", "bull", "bullish", "多", "做多"}:
            return "buy"
        if raw in {"sell", "short", "bear", "bearish", "空", "做空"}:
            return "sell"
        return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _extract_sentence(text: str, start: int, end: int) -> str:
        separators = ("\n", "。", "！", "?", "？", "，", ",", "；", ";", "：", ":")
        left = max(text.rfind(token, 0, start) for token in separators)
        right_candidates = [index for token in separators if (index := text.find(token, end)) != -1]
        right = min(right_candidates) if right_candidates else len(text)
        snippet = text[(left + 1 if left != -1 else 0):right].strip()
        return snippet or text[max(0, start - 32):min(len(text), end + 32)].strip()

    @staticmethod
    def _infer_zone_annotation_type(hint_text: str, *, side_hint: str | None = None) -> str:
        if _RISK_PATTERN.search(hint_text):
            return "no_trade_zone"
        if _RESISTANCE_PATTERN.search(hint_text) or side_hint == "sell":
            return "resistance_zone"
        if _SUPPORT_PATTERN.search(hint_text) or side_hint == "buy":
            return "support_zone"
        return "zone"

    @classmethod
    def _normalize_annotation_projection_type(
        cls,
        *,
        raw_type: str,
        label: str,
        reason: str,
        side_hint: str | None,
        price_lower: float | None,
        price_upper: float | None,
        entry_price: float | None,
        stop_price: float | None,
        target_price: float | None,
    ) -> str:
        hint_text = f"{label} {reason}".strip()
        has_zone = price_lower is not None or price_upper is not None
        if raw_type in {"support_zone", "resistance_zone", "no_trade_zone", "entry_line", "stop_loss", "take_profit", "event_marker"}:
            return raw_type
        if raw_type in {"plan", "plan_intent"}:
            if has_zone:
                return cls._infer_zone_annotation_type(hint_text, side_hint=side_hint)
            if stop_price is not None and entry_price is None and target_price is None:
                return "stop_loss"
            if target_price is not None:
                return "take_profit"
            return "entry_line"
        if raw_type in {"risk", "risk_note"}:
            return "no_trade_zone" if has_zone else "stop_loss"
        if raw_type in {"zone", "price_zone"}:
            return cls._infer_zone_annotation_type(hint_text, side_hint=side_hint)
        if raw_type in {"market_event", "event", "event_marker"}:
            return "event_marker"
        if has_zone:
            return cls._infer_zone_annotation_type(hint_text, side_hint=side_hint)
        if stop_price is not None and entry_price is None and target_price is None:
            return "stop_loss"
        if target_price is not None:
            return "take_profit"
        return "entry_line"

    @staticmethod
    def _derive_annotation_event_kind(annotation_type: str, *, plan_like: bool = False) -> str:
        if plan_like:
            return "plan"
        normalized = str(annotation_type or "").strip().lower()
        if normalized in {"support_zone", "resistance_zone", "zone", "price_zone"}:
            return "zone"
        if normalized in {"no_trade_zone", "stop_loss", "risk", "risk_note"}:
            return "risk"
        if normalized in {"event_marker", "market_event"}:
            return "event"
        return "price"

    @staticmethod
    def _default_annotation_label(annotation_type: str) -> str:
        return {
            "entry_line": "关键价位",
            "stop_loss": "风险位",
            "take_profit": "目标位",
            "support_zone": "支撑区域",
            "resistance_zone": "阻力区域",
            "no_trade_zone": "风险区域",
            "zone": "候选区域",
            "event_marker": "市场事件",
        }.get(annotation_type, "AI标记")
