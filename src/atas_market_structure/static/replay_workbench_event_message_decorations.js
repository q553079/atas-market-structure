import { getEventPresentationState } from "./replay_workbench_event_overlay.js";
import { updateRegionMarkup } from "./replay_workbench_render_stability.js";

function normalizeId(value) {
  return String(value || "").trim();
}

export function createWorkbenchEventMessageDecorations({
  els,
  getEventState,
  getCandidateById,
  getActiveThread,
  sortCandidates,
  buildMessageEventChipMarkup,
  buildMessageEventRowSignature,
}) {
  function updateCardClassForEventId(eventId, eventState = getEventState(), pinnedSet = null) {
    const normalizedId = normalizeId(eventId);
    if (!normalizedId || !els.eventStreamList) {
      return;
    }
    const candidate = getCandidateById(normalizedId);
    if (!candidate) {
      return;
    }
    const nextPinnedSet = pinnedSet instanceof Set
      ? pinnedSet
      : new Set(Array.isArray(eventState.pinnedEventIds) ? eventState.pinnedEventIds : []);
    const presentationState = getEventPresentationState(candidate, eventState);
    const escapedId = CSS.escape(normalizedId);
    els.eventStreamList.querySelectorAll(`.event-candidate-card[data-event-id="${escapedId}"]`).forEach((node) => {
      node.classList.toggle("is-selected", eventState.selectedEventId === normalizedId);
      node.classList.toggle("is-hovered", eventState.hoverEventId === normalizedId);
      node.classList.toggle("is-pinned", nextPinnedSet.has(normalizedId));
      node.classList.toggle("is-mounted", presentationState === "mounted" || presentationState === "pinned");
      node.classList.toggle("is-presentation-pinned", presentationState === "pinned");
      node.dataset.presentationState = presentationState;
    });
  }

  function syncCardClasses({ eventIds = null } = {}) {
    const eventState = getEventState();
    const pinnedSet = new Set(Array.isArray(eventState.pinnedEventIds) ? eventState.pinnedEventIds : []);
    const targetIds = Array.isArray(eventIds) && eventIds.length
      ? Array.from(new Set(eventIds.map((eventId) => normalizeId(eventId)).filter(Boolean)))
      : Array.from(els.eventStreamList?.querySelectorAll?.(".event-candidate-card[data-event-id]") || [])
        .map((node) => normalizeId(node.dataset.eventId))
        .filter(Boolean);
    targetIds.forEach((eventId) => updateCardClassForEventId(eventId, eventState, pinnedSet));
  }

  function getMessageEventBubbleBody(messageId) {
    const normalizedId = normalizeId(messageId);
    if (!normalizedId || !els.aiChatThread) {
      return null;
    }
    const messageNode = els.aiChatThread.querySelector(`.chat-message[data-message-id="${CSS.escape(normalizedId)}"]`);
    return messageNode?.querySelector?.(".chat-bubble-body") || null;
  }

  function updateChatMessageDecoration(messageId, relatedCandidates = []) {
    const bubbleBody = getMessageEventBubbleBody(messageId);
    if (!bubbleBody) {
      return;
    }
    const existingRow = bubbleBody.querySelector("[data-message-event-row]");
    if (!relatedCandidates.length) {
      existingRow?.remove();
      return;
    }
    const row = existingRow instanceof HTMLElement
      ? existingRow
      : document.createElement("div");
    row.className = "message-event-chip-row";
    row.dataset.messageEventRow = "true";
    row.dataset.sourceMessageId = normalizeId(messageId);
    if (!row.parentElement) {
      bubbleBody.appendChild(row);
    }
    updateRegionMarkup(row, `
      <span class="message-event-chip-label">本轮事件</span>
      ${relatedCandidates.map((candidate) => buildMessageEventChipMarkup(candidate)).join("")}
    `, buildMessageEventRowSignature(relatedCandidates));
  }

  function decorateChatMessages({ messageIds = null } = {}) {
    if (!els.aiChatThread) {
      return;
    }
    const activeSession = typeof getActiveThread === "function" ? getActiveThread() : null;
    const candidates = (Array.isArray(getEventState().candidates) ? getEventState().candidates : [])
      .filter((candidate) => candidate.session_id === activeSession?.id && candidate.source_message_id);
    const byMessage = new Map();
    candidates.forEach((candidate) => {
      const messageId = normalizeId(candidate.source_message_id);
      if (!messageId) {
        return;
      }
      const bucket = byMessage.get(messageId) || [];
      bucket.push(candidate);
      byMessage.set(messageId, bucket);
    });
    const targetMessageIds = Array.isArray(messageIds) && messageIds.length
      ? Array.from(new Set(messageIds.map((messageId) => normalizeId(messageId)).filter(Boolean)))
      : Array.from(new Set([
        ...Array.from(byMessage.keys()),
        ...Array.from(els.aiChatThread.querySelectorAll("[data-message-event-row]"))
          .map((node) => normalizeId(node.dataset.sourceMessageId))
          .filter(Boolean),
      ]));
    targetMessageIds.forEach((messageId) => {
      const related = sortCandidates(byMessage.get(messageId) || [], getEventState()).slice(0, 4);
      updateChatMessageDecoration(messageId, related);
    });
  }

  function isHoverSurfaceTarget(target) {
    if (!target?.closest) {
      return false;
    }
    return Boolean(
      target.closest(".event-candidate-card[data-event-id]")
      || target.closest("[data-message-event-id]")
      || target.closest(".event-overlay-hit[data-event-id]"),
    );
  }

  return {
    syncCardClasses,
    decorateChatMessages,
    isHoverSurfaceTarget,
  };
}
