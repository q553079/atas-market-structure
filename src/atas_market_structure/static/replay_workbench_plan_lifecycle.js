export function createPlanLifecycleEngine({ state }) {
  function getLatestCandleTime(candles = []) {
    const latest = candles[candles.length - 1];
    return latest ? (latest.ended_at || latest.started_at || null) : null;
  }

  function markAnnotationChanged(changedSessionIds, item, patch = {}) {
    if (!item) {
      return false;
    }
    let changed = false;
    Object.entries(patch).forEach(([key, value]) => {
      if (item[key] !== value) {
        item[key] = value;
        changed = true;
      }
    });
    if (changed && item.session_id) {
      changedSessionIds.add(item.session_id);
    }
    return changed;
  }

  function updatePlanStatuses(candles = [], changedSessionIds = new Set()) {
    const plans = new Map();
    (state.aiAnnotations || []).forEach((item) => {
      if (!item.plan_id) return;
      const current = plans.get(item.plan_id) || [];
      current.push(item);
      plans.set(item.plan_id, current);
    });

    plans.forEach((items) => {
      const entry = items.find((item) => item.type === "entry_line");
      const stop = items.find((item) => item.type === "stop_loss");
      const tps = items.filter((item) => item.type === "take_profit").sort((a, b) => (a.tp_level || 0) - (b.tp_level || 0));
      const startTs = new Date(entry?.start_time || items[0]?.start_time || state.snapshot?.window_start).getTime();

      for (const candle of candles) {
        const ts = new Date(candle.started_at).getTime();
        if (!Number.isFinite(ts) || ts < startTs) continue;

        if (entry && ["active", "draft"].includes(entry.status)) {
          const price = Number(entry.entry_price);
          if (Number.isFinite(price) && Number(candle.low) <= price && Number(candle.high) >= price) {
            markAnnotationChanged(changedSessionIds, entry, {
              status: "triggered",
              end_time: candle.ended_at || candle.started_at,
            });
            if (stop && stop.status === "inactive_waiting_entry") {
              markAnnotationChanged(changedSessionIds, stop, { status: "active" });
            }
            tps.forEach((tp) => {
              if (tp.status === "inactive_waiting_entry") {
                markAnnotationChanged(changedSessionIds, tp, { status: "active" });
              }
            });
          }
        }

        if (entry?.status === "triggered") {
          if (stop && ["active", "inactive_waiting_entry"].includes(stop.status)) {
            const stopPrice = Number(stop.stop_price);
            if (Number.isFinite(stopPrice) && Number(candle.low) <= stopPrice && Number(candle.high) >= stopPrice) {
              markAnnotationChanged(changedSessionIds, stop, {
                status: "sl_hit",
                end_time: candle.ended_at || candle.started_at,
              });
              markAnnotationChanged(changedSessionIds, entry, { status: "completed" });
              tps.forEach((tp) => {
                if (tp.status === "active") {
                  markAnnotationChanged(changedSessionIds, tp, { status: "invalidated" });
                }
              });
              break;
            }
          }

          for (const tp of tps) {
            if (!["active", "inactive_waiting_entry"].includes(tp.status)) continue;
            const target = Number(tp.target_price);
            if (Number.isFinite(target) && Number(candle.low) <= target && Number(candle.high) >= target) {
              markAnnotationChanged(changedSessionIds, tp, {
                status: "tp_hit",
                end_time: candle.ended_at || candle.started_at,
              });
            }
          }
        }
      }

      const allTpHit = tps.length && tps.every((tp) => tp.status === "tp_hit");
      if (entry && allTpHit) {
        markAnnotationChanged(changedSessionIds, entry, { status: "completed" });
        if (stop && ["active", "inactive_waiting_entry"].includes(stop.status)) {
          markAnnotationChanged(changedSessionIds, stop, { status: "completed" });
        }
      }

      if (entry?.expires_at && ["active", "draft"].includes(entry.status)) {
        const expiryTs = new Date(entry.expires_at).getTime();
        const latestTsValue = getLatestCandleTime(candles);
        const latestTs = latestTsValue ? new Date(latestTsValue).getTime() : NaN;
        if (Number.isFinite(expiryTs) && Number.isFinite(latestTs) && latestTs > expiryTs) {
          markAnnotationChanged(changedSessionIds, entry, {
            status: "expired",
            end_time: latestTsValue,
          });
          if (stop && ["active", "inactive_waiting_entry"].includes(stop.status)) {
            markAnnotationChanged(changedSessionIds, stop, { status: "invalidated" });
          }
          tps.forEach((tp) => {
            if (["active", "inactive_waiting_entry"].includes(tp.status)) {
              markAnnotationChanged(changedSessionIds, tp, { status: "invalidated" });
            }
          });
        }
      }
    });
  }

  function updateZoneStatuses(candles = [], changedSessionIds = new Set()) {
    const zones = (state.aiAnnotations || []).filter((item) => ["support_zone", "resistance_zone", "no_trade_zone"].includes(item.type));
    zones.forEach((zone) => {
      const startTs = new Date(zone.start_time || state.snapshot?.window_start).getTime();
      let touched = false;
      for (const candle of candles) {
        const ts = new Date(candle.started_at).getTime();
        if (!Number.isFinite(ts) || ts < startTs) continue;
        const low = Number(zone.price_low);
        const high = Number(zone.price_high);
        if (!Number.isFinite(low) || !Number.isFinite(high)) continue;
        const overlaps = Number(candle.high) >= low && Number(candle.low) <= high;
        if (overlaps && zone.status === "active") {
          markAnnotationChanged(changedSessionIds, zone, {
            status: "triggered",
            end_time: candle.ended_at || candle.started_at,
          });
          touched = true;
        }
        if (zone.type === "support_zone" && Number(candle.close) < low) {
          markAnnotationChanged(changedSessionIds, zone, {
            status: "invalidated",
            end_time: candle.ended_at || candle.started_at,
          });
        }
        if (zone.type === "resistance_zone" && Number(candle.close) > high) {
          markAnnotationChanged(changedSessionIds, zone, {
            status: "invalidated",
            end_time: candle.ended_at || candle.started_at,
          });
        }
        if (zone.type === "no_trade_zone" && touched) {
          markAnnotationChanged(changedSessionIds, zone, {
            status: "completed",
            end_time: candle.ended_at || candle.started_at,
          });
        }
      }

      if (zone.expires_at && ["active", "triggered"].includes(zone.status)) {
        const expiryTs = new Date(zone.expires_at).getTime();
        const latestTsValue = getLatestCandleTime(candles);
        const latestTs = latestTsValue ? new Date(latestTsValue).getTime() : NaN;
        if (Number.isFinite(expiryTs) && Number.isFinite(latestTs) && latestTs > expiryTs) {
          markAnnotationChanged(changedSessionIds, zone, {
            status: "expired",
            end_time: latestTsValue,
          });
        }
      }
    });
  }

  function syncSessionPlanSummaries(changedSessionIds = new Set()) {
    (state.aiThreads || []).forEach((session) => {
      const sessionItems = (state.aiAnnotations || []).filter((item) => item.session_id === session.id);
      const activePlans = new Set();
      const invalidatedPlans = new Set();
      sessionItems.forEach((item) => {
        if (!item.plan_id) return;
        const title = item.label || item.plan_id;
        if (["active", "triggered", "tp_hit"].includes(item.status)) activePlans.add(title);
        if (["sl_hit", "invalidated", "expired", "archived"].includes(item.status)) invalidatedPlans.add(title);
      });
      session.memory = session.memory || {};
      const nextActivePlans = Array.from(activePlans).slice(-8);
      const nextInvalidatedPlans = Array.from(invalidatedPlans).slice(-8);
      const nextSelectedAnnotations = sessionItems
        .filter((item) => item.status !== "archived")
        .map((item) => item.id)
        .slice(-12);
      const activeChanged = JSON.stringify(session.memory.active_plans_summary || []) !== JSON.stringify(nextActivePlans);
      const invalidatedChanged = JSON.stringify(session.memory.invalidated_plans_summary || []) !== JSON.stringify(nextInvalidatedPlans);
      const selectedChanged = JSON.stringify(session.memory.selected_annotations || []) !== JSON.stringify(nextSelectedAnnotations);
      if (activeChanged || invalidatedChanged || selectedChanged) {
        changedSessionIds.add(session.id);
      }
      session.memory.active_plans_summary = nextActivePlans;
      session.memory.invalidated_plans_summary = nextInvalidatedPlans;
      session.memory.selected_annotations = nextSelectedAnnotations;
      session.memory.last_updated_at = new Date().toISOString();
    });
  }

  function updateAnnotationLifecycle() {
    const candles = state.snapshot?.candles || [];
    const changedSessionIds = new Set();
    if (!candles.length || !state.aiAnnotations?.length) {
      return [];
    }
    updatePlanStatuses(candles, changedSessionIds);
    updateZoneStatuses(candles, changedSessionIds);
    syncSessionPlanSummaries(changedSessionIds);
    return Array.from(changedSessionIds);
  }

  return {
    updateAnnotationLifecycle,
    syncSessionPlanSummaries,
  };
}
