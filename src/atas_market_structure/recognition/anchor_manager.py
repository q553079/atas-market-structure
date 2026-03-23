from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any

from atas_market_structure.models import MemoryAnchorSnapshot
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.storage_models import (
    StoredAnchorInteraction,
    StoredMemoryAnchor,
    StoredMemoryAnchorVersion,
)
from atas_market_structure.recognition.types import RecognitionFeatureVector


class MemoryAnchorManager:
    """Versioned memory-anchor manager for deterministic recognition."""

    def __init__(self, repository: AnalysisRepository, *, schema_version: str) -> None:
        self._repository = repository
        self._schema_version = schema_version

    def refresh(
        self,
        *,
        feature: RecognitionFeatureVector,
        profile_version: str,
        engine_version: str,
        reference_time: datetime | None = None,
        run_key: str | None = None,
    ) -> list[MemoryAnchorSnapshot]:
        now = reference_time or datetime.now(tz=UTC)
        current_price = feature.current_price
        candidates = _candidate_anchors(feature)
        normalization = feature.context_payloads.get("latest_process_payload", {})
        _ = normalization
        for candidate in candidates:
            anchor_id = candidate["anchor_id"]
            version_id = _stable_id(
                "ancv",
                anchor_id,
                feature.market_time.isoformat(),
                feature.source_observation_table,
                feature.source_observation_id,
                run_key or "",
            )
            freshness = _freshness(candidate.get("reference_time"), now)
            payload = {
                "anchor_type": candidate["anchor_type"],
                "reference_price": candidate.get("reference_price"),
                "reference_time": candidate.get("reference_time").isoformat() if isinstance(candidate.get("reference_time"), datetime) else None,
                "source": candidate.get("source"),
                "role_profile": candidate.get("role_profile", {}),
                "notes": candidate.get("notes", []),
            }
            self._repository.save_memory_anchor_version(
                StoredMemoryAnchorVersion(
                    anchor_version_id=version_id,
                    anchor_id=anchor_id,
                    instrument_symbol=feature.instrument_symbol,
                    market_time=feature.market_time,
                    ingested_at=now,
                    schema_version=self._schema_version,
                    profile_version=profile_version,
                    engine_version=engine_version,
                    freshness=freshness,
                    anchor_payload=payload,
                ),
            )
            self._repository.upsert_memory_anchor(
                StoredMemoryAnchor(
                    anchor_id=anchor_id,
                    instrument_symbol=feature.instrument_symbol,
                    anchor_type=candidate["anchor_type"],
                    status="active",
                    freshness=freshness,
                    current_version_id=version_id,
                    reference_price=candidate.get("reference_price"),
                    reference_time=candidate.get("reference_time"),
                    schema_version=self._schema_version,
                    profile_version=profile_version,
                    engine_version=engine_version,
                    anchor_payload=payload,
                    updated_at=now,
                ),
            )

        anchors = self._repository.list_memory_anchors(instrument_symbol=feature.instrument_symbol, limit=24)
        snapshots: list[MemoryAnchorSnapshot] = []
        active_distance = max(8.0, float(feature.metrics.get("distance_to_balance_center_ticks") or 24.0) * 2.0)
        for anchor in anchors:
            if anchor.reference_price is None or current_price is None:
                distance = None
                influence = 0.25
            else:
                distance = round(abs(current_price - anchor.reference_price) / max(feature.tick_size, 1e-9), 4)
                influence = _clamp(1.0 - (distance / max(16.0, active_distance)))
                if distance <= 16.0:
                    self._repository.save_anchor_interaction(
                        StoredAnchorInteraction(
                            anchor_interaction_id=_stable_id(
                                "aint",
                                anchor.anchor_id,
                                feature.market_time.isoformat(),
                                feature.source_observation_table,
                                feature.source_observation_id,
                                run_key or "",
                                distance,
                            ),
                            anchor_id=anchor.anchor_id,
                            instrument_symbol=feature.instrument_symbol,
                            market_time=feature.market_time,
                            session_date=feature.session_date,
                            ingested_at=now,
                            schema_version=self._schema_version,
                            profile_version=profile_version,
                            engine_version=engine_version,
                            interaction_kind=("retest" if distance <= 6.0 else "approach") + f"_{anchor.anchor_type}",
                            source_observation_table=feature.source_observation_table,
                            source_observation_id=feature.source_observation_id,
                            interaction_payload={
                                "distance_ticks": distance,
                                "current_price": current_price,
                                "reference_price": anchor.reference_price,
                                "influence": influence,
                            },
                        ),
                    )
            payload = anchor.anchor_payload if isinstance(anchor.anchor_payload, dict) else {}
            snapshots.append(
                MemoryAnchorSnapshot(
                    anchor_id=anchor.anchor_id,
                    anchor_type=anchor.anchor_type,
                    reference_price=anchor.reference_price,
                    reference_time=anchor.reference_time,
                    freshness=anchor.freshness,
                    distance_ticks=distance,
                    influence=round(influence, 4) if influence is not None else None,
                    role_profile=payload.get("role_profile", {}) if isinstance(payload.get("role_profile"), dict) else {},
                    profile_version=profile_version,
                ),
            )
        snapshots.sort(key=lambda item: (item.influence or 0.0), reverse=True)
        return snapshots[:3]


def _candidate_anchors(feature: RecognitionFeatureVector) -> list[dict[str, Any]]:
    context = feature.context_payloads
    process_context = context.get("latest_process_context", {})
    market_payload = context.get("latest_market_structure", {})
    event_payload = context.get("latest_event_snapshot", {})
    candidates: list[dict[str, Any]] = []

    balance_center = feature.metrics.get("balance_center_price")
    if balance_center:
        candidates.append(
            {
                "anchor_id": _stable_id("anc", feature.instrument_symbol, "balance_center", round(balance_center, 2)),
                "anchor_type": "balance_center",
                "reference_price": float(balance_center),
                "reference_time": feature.market_time,
                "source": "feature.balance_center",
                "role_profile": {"magnet": 0.82, "take_profit_target": 0.64, "reversal_reference": 0.42},
                "notes": ["Derived from active balance center or session value-area midpoint."],
            },
        )

    if isinstance(process_context, dict):
        drives = process_context.get("initiative_drives") or []
        if drives:
            drive = drives[-1]
            side = str(drive.get("side") or "")
            price = drive.get("price_low") if side == "buy" else drive.get("price_high")
            if isinstance(price, (int, float)):
                candidates.append(
                    {
                        "anchor_id": _stable_id("anc", feature.instrument_symbol, "initiative_origin", round(float(price), 2)),
                        "anchor_type": "initiative_origin",
                        "reference_price": float(price),
                        "reference_time": _dt(drive.get("started_at")) or feature.market_time,
                        "source": "process_context.initiative_drives",
                        "role_profile": {"reversal_reference": 0.55, "support_from_above": 0.58, "resistance_from_below": 0.58},
                        "notes": ["Latest initiative drive origin retained as a path-dependency anchor."],
                    },
                )
        gaps = process_context.get("gap_references") or []
        if gaps:
            gap = gaps[-1]
            gap_price = gap.get("gap_high") if feature.current_price and feature.current_price >= float(gap.get("gap_high") or 0.0) else gap.get("gap_low")
            if isinstance(gap_price, (int, float)):
                candidates.append(
                    {
                        "anchor_id": _stable_id("anc", feature.instrument_symbol, "gap_edge", round(float(gap_price), 2)),
                        "anchor_type": "gap_edge",
                        "reference_price": float(gap_price),
                        "reference_time": _dt(gap.get("opened_at")) or feature.market_time,
                        "source": "process_context.gap_references",
                        "role_profile": {"magnet": 0.58, "reversal_reference": 0.63},
                        "notes": ["Gap edge preserved because it can act as repair target or rejection reference."],
                    },
                )
        zones = process_context.get("exertion_zones") or []
        for zone in zones[-2:]:
            if not isinstance(zone, dict):
                continue
            midpoint = _mid(zone.get("price_low"), zone.get("price_high"))
            if midpoint is None:
                continue
            anchor_type = "failed_breakout_reference" if int(zone.get("failed_reengagement_count") or 0) > 0 else "high_volume_acceptance_zone"
            candidates.append(
                {
                    "anchor_id": _stable_id("anc", feature.instrument_symbol, anchor_type, round(midpoint, 2)),
                    "anchor_type": anchor_type,
                    "reference_price": midpoint,
                    "reference_time": _dt(zone.get("established_at")) or feature.market_time,
                    "source": "process_context.exertion_zones",
                    "role_profile": {"magnet": 0.66, "reversal_reference": 0.72 if anchor_type == "failed_breakout_reference" else 0.41},
                    "notes": ["Historical exertion zone retained as versioned structure memory."],
                },
            )

    observed_events = market_payload.get("observed_events") if isinstance(market_payload.get("observed_events"), list) else []
    if not observed_events:
        observed_events = event_payload.get("trigger_event") and [event_payload.get("trigger_event")] or []
    for event in observed_events[:1]:
        if not isinstance(event, dict):
            continue
        price = event.get("price")
        if isinstance(price, (int, float)):
            candidates.append(
                {
                    "anchor_id": _stable_id("anc", feature.instrument_symbol, "failed_breakout_reference", round(float(price), 2)),
                    "anchor_type": "failed_breakout_reference",
                    "reference_price": float(price),
                    "reference_time": _dt(event.get("observed_at")) or feature.market_time,
                    "source": "observed_events",
                    "role_profile": {"reversal_reference": 0.75, "magnet": 0.48},
                    "notes": ["Recent event trigger preserved as breakout-failure or trap reference."],
                },
            )
    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        anchor_id = candidate["anchor_id"]
        if anchor_id in seen:
            continue
        seen.add(anchor_id)
        result.append(candidate)
    return result


def _stable_id(prefix: str, *parts: Any) -> str:
    material = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(material.encode('utf-8')).hexdigest()[:16]}"


def _freshness(reference_time: datetime | None, now: datetime) -> str:
    if reference_time is None:
        return "unknown"
    age_hours = max(0.0, (now - reference_time).total_seconds() / 3600.0)
    if age_hours <= 8:
        return "fresh"
    if age_hours <= 48:
        return "aging"
    return "stale"


def _mid(low: Any, high: Any) -> float | None:
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return None
    return float(low + ((high - low) / 2.0))


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
