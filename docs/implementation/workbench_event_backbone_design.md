# Replay Workbench Event Backbone Design

## Scope

This change promotes replay-workbench events into first-class persisted objects without changing the deterministic recognition pipeline. The new backbone lives strictly on the chat/workbench side and keeps AI outside the online recognition critical path.

## Object Model

- `EventCandidate`
  - session-scoped source-of-truth candidate.
  - persists normalized kind, anchors, price references, source linkage, lifecycle state, invalidation/evaluation hints, and additive metadata.
- `EventStreamEntry`
  - append-only mutation log for extracted, patched, transitioned, and promoted candidates.
  - preserves rebuildability and auditability.
- `EventMemoryEntry`
  - current memory/read model for active, watchlist, projected, and inactive candidates.
  - can be rebuilt from candidate + stream history.

## Lifecycle

Supported lifecycle states:

- `candidate`
- `confirmed`
- `mounted`
- `ignored`
- `promoted_plan`
- `expired`
- `archived`

Transitions are validated in `ReplayWorkbenchEventService` and persisted through repository transition APIs. The frontend no longer owns state assembly.

## Repository And Persistence

SQLite persistence was added in `src/atas_market_structure/repository_workbench_events_sqlite.py` with three tables:

- `chat_event_candidates`
- `chat_event_stream_entries`
- `chat_event_memory_entries`

`repository_sqlite.py` stays a thin shell and delegates event persistence to the focused workbench-event repository module.

## API

New HTTP contracts:

- `GET /api/v1/workbench/event-stream`
- `POST /api/v1/workbench/event-stream/extract`
- `PATCH /api/v1/workbench/event-candidates/{event_id}`
- `POST /api/v1/workbench/event-candidates/{event_id}/promote`
- `POST /api/v1/workbench/event-candidates/{event_id}/mount`
- `POST /api/v1/workbench/event-candidates/{event_id}/ignore`

All responses are schema-versioned Pydantic envelopes and support `session_id` with optional `symbol`, `timeframe`, and `source_message_id` filtering where relevant.

## Compatibility Strategy

- Existing `annotation` and `plan_card` persistence remains intact.
- Reply finalization now extracts and persists `EventCandidate` first.
- Legacy `annotation` and `plan_card` objects are generated as derived projections from candidates.
- Structured `plan` annotations still emit compatibility annotations such as `entry_line`, so the current replay workbench UI and tests keep working while the event backbone becomes the new source of truth.

## Current Candidate Coverage

The minimum closed loop implemented in this change covers:

- `key_level`
- `price_zone`
- `market_event`
- `risk_note`
- `plan_intent` as the projection bridge for plan cards

`thesis_fragment` remains in the model surface for future phases but is not part of the initial extraction path.
