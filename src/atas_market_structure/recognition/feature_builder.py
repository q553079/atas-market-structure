from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from atas_market_structure.models import BeliefDataStatus
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.storage_models import ObservationTable
from atas_market_structure.recognition.types import EvidenceBucket, RecognitionFeatureVector


class FeatureBuilder:
    """Build deterministic V1 feature slices from append-only observations."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def build(
        self,
        *,
        instrument_symbol: str,
        profile_payload: dict[str, Any],
        data_status: BeliefDataStatus,
    ) -> RecognitionFeatureVector | None:
        observations = {
            table.value: list(
                reversed(
                    self._repository.list_observation_records(
                        table_name=table,
                        instrument_symbol=instrument_symbol,
                        limit=48,
                    ),
                ),
            )
            for table in (
                ObservationTable.BAR,
                ObservationTable.ADAPTER_PAYLOAD,
                ObservationTable.TRADE_CLUSTER,
                ObservationTable.DEPTH_EVENT,
                ObservationTable.GAP_EVENT,
                ObservationTable.SWING_EVENT,
                ObservationTable.ABSORPTION_EVENT,
            )
        }
        ingestions = {
            kind: list(
                reversed(
                    self._repository.list_ingestions(
                        ingestion_kind=kind,
                        instrument_symbol=instrument_symbol,
                        limit=8 if kind in {"market_structure", "event_snapshot"} else 1,
                    ),
                ),
            )
            for kind in ("market_structure", "event_snapshot", "process_context")
        }
        anchors = self._repository.list_memory_anchors(instrument_symbol=instrument_symbol, limit=24)

        tick_size = _resolve_tick_size(profile_payload, observations["observation_adapter_payload"], ingestions)
        candles = _collect_candles(observations, ingestions)
        if not candles and not ingestions["market_structure"] and not ingestions["event_snapshot"]:
            return None

        market_time = _latest_market_time(candles, observations, ingestions)
        current_price = _current_price(candles, observations["observation_adapter_payload"], ingestions)
        balance_center = _balance_center(candles, ingestions)
        distance_to_center = _distance_ticks(current_price, balance_center, tick_size)

        trend_efficiency = _trend_efficiency(candles, tick_size)
        range_expansion = _range_expansion(candles, tick_size)
        compression = _compression(candles, tick_size)
        overlap_ratio = _overlap_ratio(candles, tick_size)
        initiative_buy, initiative_sell, initiative_signals = _initiative_scores(observations, ingestions)
        absorption_score, absorption_signals = _absorption_scores(observations, ingestions)
        balance_score = _clamp(
            (overlap_ratio * 0.35)
            + (compression * 0.25)
            + ((1.0 - trend_efficiency) * 0.20)
            + (_clamp(1.0 - ((distance_to_center or 24.0) / 24.0)) * 0.20),
        )
        depth_score, depth_signals = _depth_scores(data_status, observations["observation_depth_event"])
        anchor_score, anchor_signals = _anchor_scores(current_price, tick_size, anchors, profile_payload)
        path_score, path_signals = _path_scores(observations, ingestions)
        signed_move = _signed_move(candles, tick_size)
        current_direction = _clamp((signed_move * 0.55) + ((initiative_buy - initiative_sell) * 0.45), -1.0, 1.0)

        weights = profile_payload.get("weights") if isinstance(profile_payload.get("weights"), dict) else {}
        metrics = {
            "tick_size": tick_size,
            "current_direction": round(current_direction, 6),
            "trend_efficiency": round(trend_efficiency, 6),
            "range_expansion_score": round(range_expansion, 6),
            "compression_score": round(compression, 6),
            "overlap_ratio": round(overlap_ratio, 6),
            "initiative_buy_score": round(initiative_buy, 6),
            "initiative_sell_score": round(initiative_sell, 6),
            "balance_score": round(balance_score, 6),
            "absorption_score": round(absorption_score, 6),
            "depth_dom_score": round(depth_score, 6),
            "anchor_interaction_score": round(anchor_score, 6),
            "path_dependency_score": round(path_score, 6),
            "balance_center_price": float(balance_center) if balance_center is not None else 0.0,
            "distance_to_balance_center_ticks": float(distance_to_center or 0.0),
        }
        buckets = {
            "bar_structure": EvidenceBucket(
                name="bar_structure",
                score=_clamp((abs(current_direction) * 0.65) + (trend_efficiency * 0.35)),
                available=bool(candles or ingestions["market_structure"] or ingestions["event_snapshot"]),
                weight=float(weights.get("bar_structure", 1.0)),
                signals=_bar_signals(candles, observations["observation_swing_event"]),
                metrics={"bar_count": len(candles), "current_direction": round(current_direction, 4)},
            ),
            "volatility_range": EvidenceBucket(
                name="volatility_range",
                score=range_expansion,
                available=bool(candles),
                weight=float(weights.get("volatility_range", 0.8)),
                signals=[f"range_expansion={range_expansion:.2f}"],
                metrics={"range_expansion_score": round(range_expansion, 4)},
            ),
            "trend_efficiency": EvidenceBucket(
                name="trend_efficiency",
                score=trend_efficiency,
                available=bool(candles),
                weight=float(weights.get("trend_efficiency", 1.0)),
                signals=[f"trend_efficiency={trend_efficiency:.2f}"],
                metrics={"trend_efficiency": round(trend_efficiency, 4)},
            ),
            "initiative": EvidenceBucket(
                name="initiative",
                score=max(initiative_buy, initiative_sell),
                available=bool(initiative_signals),
                weight=float(weights.get("initiative", 1.0)),
                signals=initiative_signals,
                metrics={"buy": round(initiative_buy, 4), "sell": round(initiative_sell, 4)},
            ),
            "balance": EvidenceBucket(
                name="balance",
                score=balance_score,
                available=balance_center is not None,
                weight=float(weights.get("balance", 0.95)),
                signals=["near_balance_center"] if (distance_to_center or 999.0) <= 10 else ["balance_center_defined"],
                metrics={"balance_center_price": balance_center, "distance_ticks": distance_to_center},
            ),
            "absorption": EvidenceBucket(
                name="absorption",
                score=absorption_score,
                available=bool(absorption_signals),
                weight=float(weights.get("absorption", 1.0)),
                signals=absorption_signals,
                metrics={"absorption_score": round(absorption_score, 4)},
            ),
            "depth_dom": EvidenceBucket(
                name="depth_dom",
                score=depth_score,
                available=data_status.depth_available and data_status.dom_available,
                weight=float(weights.get("depth_dom", 0.9)),
                signals=depth_signals,
                metrics={"depth_dom_score": round(depth_score, 4)},
            ),
            "anchor_interaction": EvidenceBucket(
                name="anchor_interaction",
                score=anchor_score,
                available=bool(anchors),
                weight=float(weights.get("anchor_interaction", 0.85)),
                signals=anchor_signals,
                metrics={"anchor_interaction_score": round(anchor_score, 4)},
            ),
            "path_dependency": EvidenceBucket(
                name="path_dependency",
                score=path_score,
                available=bool(path_signals),
                weight=float(weights.get("path_dependency", 0.8)),
                signals=path_signals,
                metrics={"path_dependency_score": round(path_score, 4)},
            ),
        }
        table_name, source_id = _primary_source(observations, ingestions)
        latest_process = ingestions["process_context"][-1].observed_payload if ingestions["process_context"] else {}
        return RecognitionFeatureVector(
            instrument_symbol=instrument_symbol,
            market_time=market_time,
            session_date=market_time.date().isoformat(),
            window_start=candles[0]["market_time"] if candles else market_time,
            window_end=candles[-1]["market_time"] if candles else market_time,
            tick_size=tick_size,
            current_price=current_price,
            source_observation_table=table_name,
            source_observation_id=source_id,
            metrics=metrics,
            evidence_buckets=buckets,
            context_payloads={
                "latest_process_context": latest_process.get("process_context", {}),
                "latest_process_payload": latest_process,
                "latest_market_structure": ingestions["market_structure"][-1].observed_payload if ingestions["market_structure"] else {},
                "latest_event_snapshot": ingestions["event_snapshot"][-1].observed_payload if ingestions["event_snapshot"] else {},
                "latest_adapter_payload": observations["observation_adapter_payload"][-1].observation_payload if observations["observation_adapter_payload"] else {},
                "data_status": data_status.model_dump(mode="json"),
            },
            notes=_feature_notes(data_status, len(candles)),
        )


def _resolve_tick_size(profile_payload: dict[str, Any], adapter_payloads: list[Any], ingestions: dict[str, list[Any]]) -> float:
    normalization = profile_payload.get("normalization")
    if isinstance(normalization, dict) and isinstance(normalization.get("tick_size"), (int, float)):
        return float(normalization["tick_size"])
    for payload in [*(item.observation_payload for item in adapter_payloads), *(stored.observed_payload for items in ingestions.values() for stored in items)]:
        instrument = payload.get("instrument")
        if isinstance(instrument, dict) and isinstance(instrument.get("tick_size"), (int, float)):
            return float(instrument["tick_size"])
    return 0.25


def _collect_candles(observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> list[dict[str, Any]]:
    candles = [
        {
            "open": float(p.get("open") or p.get("low") or 0.0),
            "high": float(p.get("high") or p.get("close") or 0.0),
            "low": float(p.get("low") or p.get("open") or 0.0),
            "close": float(p.get("close") or p.get("high") or 0.0),
            "market_time": row.market_time,
        }
        for row in observations["observation_bar"]
        for p in [row.observation_payload]
    ]
    if len(candles) >= 3:
        return candles[-20:]
    for row in observations["observation_adapter_payload"]:
        payload = row.observation_payload
        if payload.get("message_type") != "continuous_state":
            continue
        price_state = payload.get("price_state")
        if isinstance(price_state, dict):
            last_price = float(price_state.get("last_price") or 0.0)
            low = float(price_state.get("local_range_low") or last_price)
            high = float(price_state.get("local_range_high") or last_price)
            candles.append({"open": low, "high": high, "low": low, "close": last_price, "market_time": row.market_time})
    for key in ("market_structure", "event_snapshot"):
        for stored in ingestions[key]:
            observed_at = _parse_dt(stored.observed_payload.get("observed_at")) or stored.stored_at
            decision_layers = stored.observed_payload.get("decision_layers")
            if not isinstance(decision_layers, dict):
                continue
            for layer_name in ("execution_context", "setup_context", "intraday_bias"):
                for item in decision_layers.get(layer_name) or []:
                    latest_range = item.get("latest_range") if isinstance(item, dict) else None
                    if not isinstance(latest_range, dict):
                        continue
                    candles.append(
                        {
                            "open": float(latest_range.get("open") or latest_range.get("low") or 0.0),
                            "high": float(latest_range.get("high") or latest_range.get("close") or 0.0),
                            "low": float(latest_range.get("low") or latest_range.get("open") or 0.0),
                            "close": float(latest_range.get("close") or latest_range.get("high") or 0.0),
                            "market_time": observed_at,
                        },
                    )
    candles.sort(key=lambda item: item["market_time"])
    return candles[-20:]


def _current_price(candles: list[dict[str, Any]], adapter_payloads: list[Any], ingestions: dict[str, list[Any]]) -> float | None:
    if candles:
        return float(candles[-1]["close"])
    for row in reversed(adapter_payloads):
        price_state = row.observation_payload.get("price_state")
        if isinstance(price_state, dict) and isinstance(price_state.get("last_price"), (int, float)):
            return float(price_state["last_price"])
    for key in ("event_snapshot", "market_structure"):
        for stored in reversed(ingestions[key]):
            decision_layers = stored.observed_payload.get("decision_layers")
            if not isinstance(decision_layers, dict):
                continue
            for layer_items in decision_layers.values():
                for item in layer_items or []:
                    latest_range = item.get("latest_range") if isinstance(item, dict) else None
                    if isinstance(latest_range, dict) and isinstance(latest_range.get("close"), (int, float)):
                        return float(latest_range["close"])
    return None


def _balance_center(candles: list[dict[str, Any]], ingestions: dict[str, list[Any]]) -> float | None:
    process = ingestions["process_context"][-1].observed_payload.get("process_context") if ingestions["process_context"] else {}
    if isinstance(process, dict):
        for item in reversed(process.get("session_windows") or []):
            if not isinstance(item, dict):
                continue
            value_area = item.get("value_area")
            if isinstance(value_area, dict) and isinstance(value_area.get("point_of_control"), (int, float)):
                return float(value_area["point_of_control"])
    for stored in reversed(ingestions["market_structure"]):
        decision_layers = stored.observed_payload.get("decision_layers")
        if not isinstance(decision_layers, dict):
            continue
        for item in decision_layers.get("macro_context") or []:
            value_area = item.get("value_area") if isinstance(item, dict) else None
            if isinstance(value_area, dict) and isinstance(value_area.get("point_of_control"), (int, float)):
                return float(value_area["point_of_control"])
    if candles:
        low = min(c["low"] for c in candles)
        high = max(c["high"] for c in candles)
        return float(low + ((high - low) / 2.0))
    return None


def _latest_market_time(candles: list[dict[str, Any]], observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> datetime:
    candidates = [item["market_time"] for item in candles]
    for rows in observations.values():
        candidates.extend(item.market_time for item in rows)
    for items in ingestions.values():
        for stored in items:
            observed_at = _parse_dt(stored.observed_payload.get("observed_at"))
            if observed_at is not None:
                candidates.append(observed_at)
    return max(candidates) if candidates else datetime.now(tz=UTC)


def _initiative_scores(observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> tuple[float, float, list[str]]:
    buy = sell = 0.0
    signals: list[str] = []
    for row in observations["observation_adapter_payload"]:
        payload = row.observation_payload
        trade_summary = payload.get("trade_summary")
        if isinstance(trade_summary, dict):
            delta = float(trade_summary.get("net_delta") or 0.0)
            volume = max(1.0, float(trade_summary.get("volume") or 0.0))
            if delta > 0:
                buy = max(buy, _clamp(abs(delta) / volume))
                signals.append("adapter_positive_delta")
            elif delta < 0:
                sell = max(sell, _clamp(abs(delta) / volume))
                signals.append("adapter_negative_delta")
        drive = payload.get("active_initiative_drive")
        if isinstance(drive, dict):
            score = _clamp(float(drive.get("price_travel_ticks") or 0.0) / max(1.0, float(drive.get("price_travel_ticks") or 0.0) + float(drive.get("max_counter_move_ticks") or 0.0)))
            if str(drive.get("side") or "") == "buy":
                buy = max(buy, score)
                signals.append("active_buy_drive")
            elif str(drive.get("side") or "") == "sell":
                sell = max(sell, score)
                signals.append("active_sell_drive")
    for stored in [*ingestions["market_structure"], *ingestions["event_snapshot"]]:
        decision_layers = stored.observed_payload.get("decision_layers")
        if not isinstance(decision_layers, dict):
            continue
        for layer_items in decision_layers.values():
            for item in layer_items or []:
                for signal in (item.get("orderflow_signals") if isinstance(item, dict) else []) or []:
                    if not isinstance(signal, dict):
                        continue
                    side = str(signal.get("side") or "")
                    signal_type = str(signal.get("signal_type") or "")
                    magnitude = _clamp(float(signal.get("magnitude") or 0.5))
                    if side == "buy" and signal_type in {"initiative_buying", "stacked_imbalance"}:
                        buy = max(buy, magnitude)
                        signals.append(f"{signal_type}_buy")
                    if side == "sell" and signal_type in {"initiative_selling", "stacked_imbalance"}:
                        sell = max(sell, magnitude)
                        signals.append(f"{signal_type}_sell")
    process = ingestions["process_context"][-1].observed_payload.get("process_context") if ingestions["process_context"] else {}
    if isinstance(process, dict):
        for drive in process.get("initiative_drives") or []:
            score = _clamp(float(drive.get("price_travel_ticks") or 0.0) / max(1.0, float(drive.get("price_travel_ticks") or 0.0) + float(drive.get("max_counter_move_ticks") or 0.0)))
            if str(drive.get("side") or "") == "buy":
                buy = max(buy, score)
                signals.append("process_buy_drive")
            elif str(drive.get("side") or "") == "sell":
                sell = max(sell, score)
                signals.append("process_sell_drive")
    return _clamp(buy), _clamp(sell), _unique(signals)


def _absorption_scores(observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> tuple[float, list[str]]:
    score = _clamp(len(observations["observation_absorption_event"]) / 4.0) if observations["observation_absorption_event"] else 0.0
    signals = ["mirrored_absorption_event"] if observations["observation_absorption_event"] else []
    process = ingestions["process_context"][-1].observed_payload.get("process_context") if ingestions["process_context"] else {}
    if isinstance(process, dict):
        for episode in process.get("liquidity_episodes") or []:
            replenishment = float(episode.get("replenishment_count") or 0.0)
            pulls = float(episode.get("pull_count") or 0.0)
            reaction = float(episode.get("price_rejection_ticks") or 0.0)
            score = max(score, _clamp((replenishment + min(4.0, reaction / 8.0)) / max(1.0, replenishment + pulls + 2.0)))
            signals.append("liquidity_episode_absorption")
    for stored in [*ingestions["market_structure"], *ingestions["event_snapshot"]]:
        decision_layers = stored.observed_payload.get("decision_layers")
        if not isinstance(decision_layers, dict):
            continue
        for layer_items in decision_layers.values():
            for item in layer_items or []:
                for signal in (item.get("orderflow_signals") if isinstance(item, dict) else []) or []:
                    if isinstance(signal, dict) and str(signal.get("signal_type") or "") == "absorption":
                        score = max(score, _clamp(float(signal.get("magnitude") or 0.6)))
                        signals.append("decision_layer_absorption")
    return _clamp(score), _unique(signals)


def _depth_scores(data_status: BeliefDataStatus, depth_events: list[Any]) -> tuple[float, list[str]]:
    if not data_status.depth_available and not data_status.dom_available:
        return 0.0, ["depth_dom_unavailable"]
    heat = max((float(item.observation_payload.get("heat_score") or 0.0) for item in depth_events), default=0.0)
    signals = [f"depth_status_{item.observation_payload.get('status')}" for item in depth_events if item.observation_payload.get("status")]
    if data_status.depth_available:
        signals.append("depth_available")
    if data_status.dom_available:
        signals.append("dom_available")
    return _clamp(max(heat, 0.55 if data_status.depth_available and data_status.dom_available else 0.35)), _unique(signals)


def _anchor_scores(current_price: float | None, tick_size: float, anchors: list[Any], profile_payload: dict[str, Any]) -> tuple[float, list[str]]:
    if current_price is None or not anchors:
        return 0.0, []
    normalization = profile_payload.get("normalization") if isinstance(profile_payload.get("normalization"), dict) else {}
    active_distance = float(normalization.get("anchor_active_distance_ticks") or 48.0)
    closest = 1.0
    signals: list[str] = []
    for anchor in anchors:
        if anchor.reference_price is None:
            continue
        distance = _distance_ticks(current_price, anchor.reference_price, tick_size)
        if distance is None:
            continue
        closest = min(closest, distance / max(1.0, active_distance))
        if distance <= 6:
            signals.append(f"anchor_retest_{anchor.anchor_type}")
        elif distance <= 16:
            signals.append(f"anchor_approach_{anchor.anchor_type}")
    return _clamp(1.0 - closest), _unique(signals)


def _path_scores(observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []
    process = ingestions["process_context"][-1].observed_payload.get("process_context") if ingestions["process_context"] else {}
    if isinstance(process, dict):
        score = max(score, _clamp((len(process.get("cross_session_sequences") or []) * 0.2) + (len(process.get("measured_moves") or []) * 0.15) + (len(process.get("post_harvest_responses") or []) * 0.1)))
        if process.get("cross_session_sequences"):
            signals.append("cross_session_sequence_present")
        if process.get("measured_moves"):
            signals.append("measured_move_present")
        if process.get("post_harvest_responses"):
            signals.append("post_harvest_present")
    if observations["observation_gap_event"]:
        score = max(score, _clamp(len(observations["observation_gap_event"]) / 3.0))
        signals.append("gap_reference_present")
    if observations["observation_swing_event"]:
        score = max(score, _clamp(len(observations["observation_swing_event"]) / 6.0))
        signals.append("swing_sequence_present")
    if observations["observation_trade_cluster"]:
        score = max(score, _clamp(len(observations["observation_trade_cluster"]) / 3.0))
        signals.append("trade_cluster_present")
    return _clamp(score), _unique(signals)


def _trend_efficiency(candles: list[dict[str, Any]], tick_size: float) -> float:
    if not candles:
        return 0.0
    if len(candles) == 1:
        return _clamp(abs(candles[0]["close"] - candles[0]["open"]) / max(tick_size, candles[0]["high"] - candles[0]["low"]))
    directional = abs(candles[-1]["close"] - candles[0]["open"])
    total_travel = max(sum(abs(candles[i]["close"] - candles[i - 1]["close"]) for i in range(1, len(candles))), abs(candles[-1]["high"] - candles[0]["low"]), tick_size)
    return _clamp(directional / total_travel)


def _range_expansion(candles: list[dict[str, Any]], tick_size: float) -> float:
    if len(candles) < 2:
        return 0.0
    last_range = max(tick_size, candles[-1]["high"] - candles[-1]["low"])
    baseline = sum(max(tick_size, c["high"] - c["low"]) for c in candles[:-1]) / max(1, len(candles) - 1)
    return _clamp((last_range / max(tick_size, baseline) - 0.8) / 1.2)


def _compression(candles: list[dict[str, Any]], tick_size: float) -> float:
    if not candles:
        return 0.0
    ranges = [max(tick_size, c["high"] - c["low"]) for c in candles]
    return _clamp(1.0 - ((sum(ranges) / len(ranges)) / max(ranges)))


def _overlap_ratio(candles: list[dict[str, Any]], tick_size: float) -> float:
    if len(candles) < 2:
        return 0.0
    overlaps = []
    for left, right in zip(candles[:-1], candles[1:]):
        overlap = max(0.0, min(left["high"], right["high"]) - max(left["low"], right["low"]))
        width = max(tick_size, max(left["high"] - left["low"], right["high"] - right["low"]))
        overlaps.append(overlap / width)
    return _clamp(sum(overlaps) / len(overlaps)) if overlaps else 0.0


def _signed_move(candles: list[dict[str, Any]], tick_size: float) -> float:
    if not candles:
        return 0.0
    return _clamp((candles[-1]["close"] - candles[0]["open"]) / max(tick_size * 12.0, 1e-9), -1.0, 1.0)


def _distance_ticks(current_price: float | None, reference_price: float | None, tick_size: float) -> float | None:
    if current_price is None or reference_price is None or tick_size <= 0:
        return None
    return round(abs(current_price - reference_price) / tick_size, 4)


def _bar_signals(candles: list[dict[str, Any]], swing_events: list[Any]) -> list[str]:
    signals = []
    if len(candles) >= 2:
        signals.append("higher_close_sequence" if candles[-1]["close"] >= candles[0]["open"] else "lower_close_sequence")
    if swing_events:
        kind = str(swing_events[-1].observation_payload.get("kind") or "")
        if kind:
            signals.append(f"last_swing_{kind}")
    return _unique(signals)


def _primary_source(observations: dict[str, list[Any]], ingestions: dict[str, list[Any]]) -> tuple[str | None, str | None]:
    for key in ("observation_bar", "observation_trade_cluster", "observation_adapter_payload"):
        if observations[key]:
            return key, observations[key][-1].observation_id
    if ingestions["market_structure"]:
        return "ingestion.market_structure", ingestions["market_structure"][-1].ingestion_id
    if ingestions["event_snapshot"]:
        return "ingestion.event_snapshot", ingestions["event_snapshot"][-1].ingestion_id
    return None, None


def _feature_notes(data_status: BeliefDataStatus, bar_count: int) -> list[str]:
    notes = [f"feature_bar_count={bar_count}"]
    if not data_status.depth_available:
        notes.append("depth evidence unavailable; related weights were reduced.")
    if not data_status.dom_available:
        notes.append("DOM evidence unavailable; hard confirms were suppressed.")
    if any(mode.value == "stale_macro" for mode in data_status.degraded_modes):
        notes.append("macro/process context stale; regime confidence will be flattened.")
    return notes


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered
