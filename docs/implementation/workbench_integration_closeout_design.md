# Replay Workbench Integration Closeout Design

## What This Closeout Covers
This pass does not redesign the replay workbench. It closes the integration seams between the new object layers already added in the four implementation threads:

- `EventCandidate` / `EventStreamEntry` / `EventMemoryEntry`
- Prompt Trace
- Event overlay projection and event-card interactions
- Event Outcome Ledger and summary panels

The intent is to make these layers operate as one coherent workbench loop:

1. Assistant reply is stored and linked to `prompt_trace_id`.
2. Structured event extraction persists `EventCandidate` objects.
3. Frontend event column reads the `event-stream` API as the main path.
4. Hover and selection state project events onto the chart overlay.
5. Outcome data decorates event cards and plan cards without replacing the source object.

## Integrated Object Flow

### Source Of Truth
`EventCandidate` is the only object that should drive:
- event cards
- overlay projection state
- assistant-message event chips
- event-to-outcome linking
- candidate-to-prompt-trace lookup

### Derived Views
The following remain supported, but are treated as projections or compatibility views:
- chat annotations
- chat plan cards
- legacy text-derived plan cards

Structured plan cards still render when returned by the backend, but the UI should not infer them from free text unless explicit debug fallback is enabled.

## Frontend State Flow

### Event Presentation State
The event overlay flow is split into presentation state and lifecycle state:

- lifecycle state comes from persisted candidate data, for example `candidate`, `mounted`, `ignored`, `promoted_plan`
- presentation state is resolved in the UI, for example `hidden`, `hover_spotlight`, `mounted`, `pinned`

The chart overlay reads the current presentation state and renders:
- `hover_spotlight` as temporary ghost projection
- `mounted` as committed overlay
- `pinned` as persistent committed overlay with stronger styling

### Event Panel Rendering
`renderSnapshot()` can run frequently from unrelated workbench updates. The event panel therefore must not rebuild `#eventStreamList` on every call.

The closeout adds a render signature guard so the card list is only replaced when the candidate list or relevant candidate fields actually change. State-only changes such as hover and selection continue to update through `syncCardClasses()`.

This keeps:
- hover stable
- overlay click stable
- mounted and pinned classes stable across refresh
- Playwright and user interactions from losing DOM nodes mid-hover

## Prompt Trace Integration
Prompt Trace remains a message-linked audit object. Closeout work preserves:

- `assistant_message.prompt_trace_id`
- message-level lookup
- session-level lookup
- trace viewer entry points from assistant messages and event cards

The only route change in this pass is defensive: prompt-trace list queries now return a normal `400` JSON response when `session_id` is missing.

## Outcome Ledger Integration
Outcome data remains additive to the event flow:

- event cards are decorated by matching `outcome.event_id`
- plan cards are decorated by resolving an originating event id from plan metadata
- summary buckets stay in the event column as a lightweight dashboard

This pass keeps the outcome panel visible but constrains its height so it does not crowd or interfere with the event card interaction area.

## Compatibility Strategy

### Legacy Event Stream UI
The old compatibility renderer in `replay_workbench.html` is kept, but it yields to the modular event panel through `app.renderEventPanel()`.

### Legacy Plan Card Fallback
`parsePlanCardsFromReply()` still exists, but it is no longer the default path.

It should only run when explicitly enabled for debugging, for example via:
- query flag
- explicit global debug switch

This prevents text parsing from silently replacing missing structured payloads in normal operation.

## Known Limits After This Pass
- The compatibility facade in `replay_workbench.html` is still large and should stay facade-only.
- Pinned state is still frontend-persisted even though mounted lifecycle is server-backed.
- Outcome summary is lightweight and not a full analytics dashboard.
- Legacy fallback remains present for rollback and debugging, so it still needs eventual removal once all environments reliably emit structured plan payloads.
