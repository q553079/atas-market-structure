"""Focus region review: structured sedimentation of high-value analysis results.

Stores deep region analysis results as structured records that can feed back into:
- strategy_candidates selection
- focus_regions prioritization
- ai_briefing enrichment
- position health reminders
- strategy library refinement
- behavior library corrections

Also handles screenshot/box-select analysis input normalization.

Consumers: app.py (new endpoints), workbench UI, AI review prompts
Does NOT modify: models.py, existing replay/workbench routes, ATAS collector
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from atas_market_structure.analysis_orchestration_services import DeepRegionAnalysisResult
from atas_market_structure.repository import AnalysisRepository


# ---------------------------------------------------------------------------
# Focus Region Review Record (structured sedimentation)
# ---------------------------------------------------------------------------

@dataclass
class FocusRegionReviewRecord:
    """Structured record for a reviewed focus region — the core sedimentation unit."""
    review_id: str
    analysis_id: str
    region_id: str
    replay_ingestion_id: str
    instrument_symbol: str
    timeframe: str
    session: str | None
    time_range_start: datetime
    time_range_end: datetime
    price_range_low: float
    price_range_high: float
    selection_source: str  # "manual_marked" | "ai_suggested" | "web_box_select" | "atas_screenshot"
    # Market context at time of review
    market_context: dict[str, Any]
    # Observed features
    observed_features: list[str]
    # Derived mappings
    derived_event_kinds: list[str]
    derived_reason_codes: list[str]
    strategy_candidates: list[dict[str, Any]]
    # Analysis outputs
    focus_questions: list[str]
    required_evidence_seen: list[str]
    invalidation_seen: list[str]
    no_trade_flags: list[str]
    position_health_flags: list[str]
    region_verdict: str
    ai_summary_short: str
    confidence: float
    provenance: list[str]
    # Review lifecycle
    review_status: str  # "pending" | "confirmed" | "rejected" | "revised"
    reviewer_notes: str
    reviewed_at: datetime | None
    stored_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "analysis_id": self.analysis_id,
            "region_id": self.region_id,
            "replay_ingestion_id": self.replay_ingestion_id,
            "instrument_symbol": self.instrument_symbol,
            "timeframe": self.timeframe,
            "session": self.session,
            "time_range_start": self.time_range_start.isoformat(),
            "time_range_end": self.time_range_end.isoformat(),
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "selection_source": self.selection_source,
            "market_context": self.market_context,
            "observed_features": self.observed_features,
            "derived_event_kinds": self.derived_event_kinds,
            "derived_reason_codes": self.derived_reason_codes,
            "strategy_candidates": self.strategy_candidates,
            "focus_questions": self.focus_questions,
            "required_evidence_seen": self.required_evidence_seen,
            "invalidation_seen": self.invalidation_seen,
            "no_trade_flags": self.no_trade_flags,
            "position_health_flags": self.position_health_flags,
            "region_verdict": self.region_verdict,
            "ai_summary_short": self.ai_summary_short,
            "confidence": round(self.confidence, 2),
            "provenance": self.provenance,
            "review_status": self.review_status,
            "reviewer_notes": self.reviewer_notes,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "stored_at": self.stored_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Screenshot / Box-Select Analysis Input
# ---------------------------------------------------------------------------

@dataclass
class ScreenshotAnalysisInput:
    """Normalized input for screenshot or box-select region analysis."""
    input_id: str
    source_type: str  # "atas_screenshot" | "web_box_select"
    instrument_symbol: str | None
    timeframe: str | None
    session: str | None
    time_range_start: datetime | None
    time_range_end: datetime | None
    price_range_low: float | None
    price_range_high: float | None
    # For screenshots
    image_url: str | None
    observed_visual_cues: list[str]
    # For web box-select
    chart_id: str | None
    snapshot_id: str | None
    pane_type: str | None
    # Metadata
    selected_at: datetime
    selected_by: str
    linked_replay_ingestion_id: str | None
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "source_type": self.source_type,
            "instrument_symbol": self.instrument_symbol,
            "timeframe": self.timeframe,
            "session": self.session,
            "time_range_start": self.time_range_start.isoformat() if self.time_range_start else None,
            "time_range_end": self.time_range_end.isoformat() if self.time_range_end else None,
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "image_url": self.image_url,
            "observed_visual_cues": self.observed_visual_cues,
            "chart_id": self.chart_id,
            "snapshot_id": self.snapshot_id,
            "pane_type": self.pane_type,
            "selected_at": self.selected_at.isoformat(),
            "selected_by": self.selected_by,
            "linked_replay_ingestion_id": self.linked_replay_ingestion_id,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Focus Region Review Service (store, query, feedback loop)
# ---------------------------------------------------------------------------

class FocusRegionReviewService:
    """Stores and queries focus region reviews. Provides feedback loop for AI enrichment.

    Storage: uses existing AnalysisRepository ingestion table with kind='focus_region_review'.
    This avoids schema changes while keeping reviews queryable and structured.

    Feedback loop:
    - list_confirmed_reviews() returns confirmed reviews for a given instrument/timeframe
    - These can be injected into AI briefing as historical precedent
    - strategy_candidates can be boosted if a confirmed review matched the same strategy
    """

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def store_review(
        self,
        deep_result: DeepRegionAnalysisResult,
        *,
        replay_ingestion_id: str,
        market_context: dict[str, Any] | None = None,
        reviewer_notes: str = "",
    ) -> FocusRegionReviewRecord:
        now = datetime.now(tz=UTC)
        review_id = f"frr-{uuid4().hex[:12]}"

        record = FocusRegionReviewRecord(
            review_id=review_id,
            analysis_id=deep_result.analysis_id,
            region_id=deep_result.region_id,
            replay_ingestion_id=replay_ingestion_id,
            instrument_symbol=deep_result.instrument_symbol,
            timeframe=deep_result.timeframe,
            session=deep_result.session,
            time_range_start=deep_result.time_range_start,
            time_range_end=deep_result.time_range_end,
            price_range_low=deep_result.price_range_low,
            price_range_high=deep_result.price_range_high,
            selection_source=deep_result.source_type,
            market_context=market_context or {},
            observed_features=[f"events={len(deep_result.event_chain)}"],
            derived_event_kinds=deep_result.derived_event_kinds,
            derived_reason_codes=deep_result.derived_reason_codes,
            strategy_candidates=deep_result.strategy_candidates,
            focus_questions=[],
            required_evidence_seen=deep_result.required_evidence_seen,
            invalidation_seen=deep_result.invalidation_seen,
            no_trade_flags=deep_result.no_trade_flags,
            position_health_flags=deep_result.position_health_flags,
            region_verdict=deep_result.region_verdict,
            ai_summary_short=deep_result.ai_summary_short,
            confidence=deep_result.confidence,
            provenance=deep_result.provenance,
            review_status="pending",
            reviewer_notes=reviewer_notes,
            reviewed_at=None,
            stored_at=now,
        )

        self._repository.save_ingestion(
            ingestion_id=f"ing-{uuid4().hex}",
            ingestion_kind="focus_region_review",
            source_snapshot_id=replay_ingestion_id,
            instrument_symbol=deep_result.instrument_symbol,
            observed_payload=record.to_dict(),
            stored_at=now,
        )
        return record

    def confirm_review(self, review_id: str, *, reviewer_notes: str = "") -> FocusRegionReviewRecord | None:
        return self._update_status(review_id, "confirmed", reviewer_notes)

    def reject_review(self, review_id: str, *, reviewer_notes: str = "") -> FocusRegionReviewRecord | None:
        return self._update_status(review_id, "rejected", reviewer_notes)

    def list_reviews(
        self,
        *,
        instrument_symbol: str | None = None,
        status_filter: str | None = None,
        limit: int = 200,
    ) -> list[FocusRegionReviewRecord]:
        stored_list = self._repository.list_ingestions(
            ingestion_kind="focus_region_review",
            instrument_symbol=instrument_symbol,
            limit=limit,
        )
        results: list[FocusRegionReviewRecord] = []
        for stored in stored_list:
            record = self._parse_record(stored.observed_payload)
            if record is None:
                continue
            if status_filter and record.review_status != status_filter:
                continue
            results.append(record)
        return results

    def list_confirmed_reviews(
        self,
        *,
        instrument_symbol: str | None = None,
        limit: int = 100,
    ) -> list[FocusRegionReviewRecord]:
        """Returns confirmed reviews — primary feedback loop for AI enrichment."""
        return self.list_reviews(
            instrument_symbol=instrument_symbol,
            status_filter="confirmed",
            limit=limit,
        )

    def get_feedback_for_briefing(
        self,
        instrument_symbol: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Returns compact confirmed reviews suitable for injection into AI briefing prompts.

        This is the main feedback mechanism:
        - Confirmed reviews boost matching strategy_candidates
        - Confirmed verdicts inform AI about historical precedent at similar price levels
        - Confirmed no-trade flags reinforce suppressor conditions
        """
        confirmed = self.list_confirmed_reviews(instrument_symbol=instrument_symbol, limit=limit)
        feedback: list[dict[str, Any]] = []
        for r in confirmed:
            feedback.append({
                "review_id": r.review_id,
                "price_range": f"{r.price_range_low}-{r.price_range_high}",
                "verdict": r.region_verdict,
                "strategy_ids": [s.get("strategy_id", "") for s in r.strategy_candidates[:3]],
                "evidence_seen": r.required_evidence_seen[:3],
                "no_trade_flags": r.no_trade_flags[:2],
                "confidence": r.confidence,
                "ai_summary": r.ai_summary_short[:120],
            })
        return feedback

    def store_screenshot_input(self, input_data: ScreenshotAnalysisInput) -> str:
        """Stores a screenshot/box-select analysis input for later processing."""
        now = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind="screenshot_analysis_input",
            source_snapshot_id=input_data.linked_replay_ingestion_id or "",
            instrument_symbol=input_data.instrument_symbol or "",
            observed_payload=input_data.to_dict(),
            stored_at=now,
        )
        return ingestion_id

    def _update_status(self, review_id: str, new_status: str, notes: str) -> FocusRegionReviewRecord | None:
        now = datetime.now(tz=UTC)
        for stored in self._repository.list_ingestions(ingestion_kind="focus_region_review", limit=500):
            payload = stored.observed_payload
            if payload.get("review_id") != review_id:
                continue
            payload["review_status"] = new_status
            payload["reviewer_notes"] = notes
            payload["reviewed_at"] = now.isoformat()
            self._repository.update_ingestion_observed_payload(
                ingestion_id=stored.ingestion_id,
                observed_payload=payload,
            )
            return self._parse_record(payload)
        return None

    @staticmethod
    def _parse_record(payload: dict[str, Any]) -> FocusRegionReviewRecord | None:
        try:
            return FocusRegionReviewRecord(
                review_id=payload["review_id"],
                analysis_id=payload["analysis_id"],
                region_id=payload["region_id"],
                replay_ingestion_id=payload["replay_ingestion_id"],
                instrument_symbol=payload["instrument_symbol"],
                timeframe=payload["timeframe"],
                session=payload.get("session"),
                time_range_start=datetime.fromisoformat(payload["time_range_start"]),
                time_range_end=datetime.fromisoformat(payload["time_range_end"]),
                price_range_low=payload["price_range_low"],
                price_range_high=payload["price_range_high"],
                selection_source=payload["selection_source"],
                market_context=payload.get("market_context", {}),
                observed_features=payload.get("observed_features", []),
                derived_event_kinds=payload.get("derived_event_kinds", []),
                derived_reason_codes=payload.get("derived_reason_codes", []),
                strategy_candidates=payload.get("strategy_candidates", []),
                focus_questions=payload.get("focus_questions", []),
                required_evidence_seen=payload.get("required_evidence_seen", []),
                invalidation_seen=payload.get("invalidation_seen", []),
                no_trade_flags=payload.get("no_trade_flags", []),
                position_health_flags=payload.get("position_health_flags", []),
                region_verdict=payload.get("region_verdict", "ambiguous"),
                ai_summary_short=payload.get("ai_summary_short", ""),
                confidence=payload.get("confidence", 0.0),
                provenance=payload.get("provenance", []),
                review_status=payload.get("review_status", "pending"),
                reviewer_notes=payload.get("reviewer_notes", ""),
                reviewed_at=(
                    datetime.fromisoformat(payload["reviewed_at"])
                    if payload.get("reviewed_at")
                    else None
                ),
                stored_at=datetime.fromisoformat(payload["stored_at"]),
            )
        except (KeyError, ValueError):
            return None
