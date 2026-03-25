function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function createWorkbenchEventApi({ fetchJson }) {
  async function listEventStream({ sessionId, symbol = null, timeframe = null, sourceMessageId = null, limit = 200 }) {
    return fetchJson(`/api/v1/workbench/event-stream${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      source_message_id: sourceMessageId,
      limit,
    })}`);
  }

  async function extractEventStream({ sessionId, sourceMessageId = null, symbol = null, timeframe = null, limit = 200 }) {
    return fetchJson("/api/v1/workbench/event-stream/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        source_message_id: sourceMessageId,
        symbol,
        timeframe,
        limit,
      }),
    });
  }

  async function createCandidate(payload) {
    return fetchJson("/api/v1/workbench/event-candidates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function patchCandidate(eventId, payload) {
    return fetchJson(`/api/v1/workbench/event-candidates/${encodeURIComponent(eventId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function promoteCandidate(eventId, target) {
    return fetchJson(`/api/v1/workbench/event-candidates/${encodeURIComponent(eventId)}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
  }

  async function mountCandidate(eventId) {
    return fetchJson(`/api/v1/workbench/event-candidates/${encodeURIComponent(eventId)}/mount`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  }

  async function ignoreCandidate(eventId) {
    return fetchJson(`/api/v1/workbench/event-candidates/${encodeURIComponent(eventId)}/ignore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  }

  async function listEventOutcomes({
    sessionId,
    symbol = null,
    timeframe = null,
    eventId = null,
    eventKind = null,
    realizedOutcome = null,
    limit = 500,
  }) {
    return fetchJson(`/api/v1/workbench/event-outcomes${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      event_id: eventId,
      event_kind: eventKind,
      realized_outcome: realizedOutcome,
      limit,
    })}`);
  }

  async function getEventStatsSummary({ sessionId, symbol = null, timeframe = null, limit = 2000 }) {
    return fetchJson(`/api/v1/workbench/event-stats/summary${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      limit,
    })}`);
  }

  async function getEventStatsByKind({ sessionId, symbol = null, timeframe = null, limit = 2000 }) {
    return fetchJson(`/api/v1/workbench/event-stats/by-kind${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      limit,
    })}`);
  }

  async function getEventStatsByTimeWindow({ sessionId, symbol = null, timeframe = null, limit = 2000 }) {
    return fetchJson(`/api/v1/workbench/event-stats/by-time-window${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      limit,
    })}`);
  }

  async function getEventStatsByAnalysisPreset({ sessionId, symbol = null, timeframe = null, limit = 2000 }) {
    return fetchJson(`/api/v1/workbench/event-stats/by-analysis-preset${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      limit,
    })}`);
  }

  async function getEventStatsByModel({ sessionId, symbol = null, timeframe = null, limit = 2000 }) {
    return fetchJson(`/api/v1/workbench/event-stats/by-model${buildQuery({
      session_id: sessionId,
      symbol,
      timeframe,
      limit,
    })}`);
  }

  return {
    listEventStream,
    extractEventStream,
    createCandidate,
    patchCandidate,
    promoteCandidate,
    mountCandidate,
    ignoreCandidate,
    listEventOutcomes,
    getEventStatsSummary,
    getEventStatsByKind,
    getEventStatsByTimeWindow,
    getEventStatsByAnalysisPreset,
    getEventStatsByModel,
  };
}
