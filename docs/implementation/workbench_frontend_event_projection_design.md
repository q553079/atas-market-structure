## Summary

This change makes `EventCandidate` the frontend source of truth for workbench event interaction.

## UI state flow

- Backend `event-stream` returns `candidates`, `items`, and `memory_entries`.
- Frontend stores candidates by `event_id` and tracks one presentation state per event:
  - `hidden`
  - `hover_spotlight`
  - `mounted`
  - `pinned`
- `hover_spotlight` is purely transient and never persisted.
- `mounted` is created by backend `mount` or `promote(annotation)` responses and persists through candidate lifecycle state.
- `pinned` is a frontend visibility preference layered on top of a mounted candidate.

## Main interaction loop

- Event card hover: show lightweight chart spotlight only.
- Event card leave: remove spotlight unless the same event is mounted or pinned.
- Event card click: mount and center chart on the event anchor.
- Pin action: keep the mounted overlay in the pinned visual state.
- Overlay click: select event card and scroll the source event into view.
- Source action: jump from event card to its source AI message by `source_message_id`.

## Overlay strategy

- Overlays stay lightweight and are rendered from event candidates rather than reply text.
- Kinds:
  - `key_level`: thin price line with compact label
  - `price_zone`: transparent band
  - `market_event`: time band / anchor marker
  - `risk_note`: warning tag or warning line
- Visual emphasis:
  - `hover_spotlight`: brighter, temporary
  - `mounted`: stable line/band
  - `pinned`: stronger chip/border treatment than mounted

## Legacy fallback

- Existing `parsePlanCardsFromReply()` and related text extraction remain in place only for compatibility.
- New middle event panel reads backend `event-stream` first.
- If backend event data is missing, UI can surface a small legacy note rather than silently mixing both paths as equals.

## Manual creation

- Manual tools create `EventCandidate` records, not annotations directly.
- Manual objects use backend event persistence first, then join the same panel and overlay lifecycle as extracted events.
- Frontend passes the latest assistant `source_message_id` when available so manual candidates can still mount through the same derived-projection path.

## Compatibility

- Existing annotation and plan-card rendering remains intact.
- Event-driven overlays are additive and do not replace annotation projections until explicitly promoted or mounted.
