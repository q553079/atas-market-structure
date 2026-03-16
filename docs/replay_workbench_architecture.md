# Replay Workbench Architecture

## Goal

Build a standalone review UI that can:

- load a 3-7 day historical window from ATAS-oriented data,
- rebuild an independent candle chart without relying on the ATAS viewport,
- render event annotations and focus regions on top of that chart,
- attach strategy-library candidates,
- assemble a structured AI briefing from the event set,
- surface key support and resistance zones without interfering with live ATAS usage.

This workbench is a **review and context-compression tool**, not an execution terminal.

## Design Constraints

- Do not depend on screen scraping or ATAS chart pixels.
- Do not depend on the operator manually setting many per-chart parameters.
- Preserve the existing rule: separate observed facts from derived interpretation.
- Treat the UI as a consumer of structured replay packets, not as the source of market logic.
- Keep the UI isolated from the live ATAS workspace so replay and annotation do not affect trading screens.
- Only fetch from ATAS when the requested historical replay packet is missing locally.
- Limit replay verification to once per day.
- After 3 successful verification passes, keep the replay packet as durable cache until the operator manually invalidates it.

## Core Flow

```mermaid
flowchart LR
    A["ATAS Collector"] --> B["Raw Adapter Messages"]
    B --> C["Replay Packet Builder"]
    C --> D["Replay Workbench Snapshot"]
    D --> E["Standalone UI Chart"]
    D --> F["Strategy Library Matcher"]
    F --> G["AI Briefing Packet"]
    G --> H["AI Zone Review"]
    H --> E
```

## Recommended Split

### 1. Historical Window Acquisition

The replay UI should not read the current ATAS screen.

Historical acquisition should be cache-first:

- if the local replay packet already exists, reuse it,
- only fetch from ATAS when the packet is missing,
- verify stored packets at most once per day,
- after 3 successful verification passes, stop reacquiring automatically,
- require manual invalidation before any later reimport.

It should consume a structured historical window containing:

- reconstructed candles,
- event annotations,
- focus regions,
- strategy-library candidates,
- optional AI briefing instructions.

This packet is now represented by:

- [ReplayWorkbenchSnapshotPayload](D:/docker/atas-market-structure/src/atas_market_structure/models.py)

The packet now carries explicit cache policy and verification state so the UI and later AI review can distinguish:

- fresh ATAS acquisition,
- local cache reuse,
- unverified cache,
- verified cache,
- durable locked cache,
- manually invalidated cache.

### 2. Standalone Chart Reconstruction

The workbench chart should be rebuilt locally from the replay packet.

Minimum render layers:

- candle layer,
- event marker layer,
- focus region layer,
- optional reference levels,
- optional summary sidebar.

This gives two benefits:

- ATAS remains dedicated to live order-flow work,
- the workbench can annotate aggressively without cluttering the trading chart.

### 3. Event Layer

Events should remain structured and explicit.

Minimum event classes for the workbench:

- collector events,
- strategy-library matched events,
- manual review events,
- AI review events.

Examples:

- same-price replenishment,
- initiative drive,
- gap first touch,
- upper-liquidity harvest,
- post-harvest reversal watch,
- Europe defended bid,
- failed overhead capping.

### 4. Focus Region Layer

Focus regions are not the same as raw events.

They are operator-facing highlighted zones derived from multiple events and context.

A focus region should answer:

- where the operator should look first,
- why that price zone matters,
- which events justify the region,
- whether the current script is continuation, reversal, or unresolved.

### 5. Strategy Library Attachment

The workbench should not send raw events directly to AI without context.

It should first attach strategy-library candidates that explain:

- which stored pattern(s) are relevant,
- which observed events matched them,
- why those patterns matter now.

This reduces AI ambiguity and keeps the prompt tied to the local doctrine library.

### 6. AI Briefing Packet

The AI should receive a compact structured packet, not an unbounded chart dump.

Minimum sections:

- replay window,
- event annotations,
- focus regions,
- strategy-library candidates,
- explicit operator objective,
- required output sections.

Expected AI output:

- key zones,
- support and resistance ranking,
- continuation vs reversal scripts,
- invalidations,
- unresolved conflicts.

## Why This Is Better Than Reusing ATAS UI

- The ATAS chart stays optimized for live reading and execution.
- The replay UI can add dense labels and region overlays without harming the trading workspace.
- The workbench can mix multiple days of context, strategy-library notes, and AI results in one view.
- The same replay packet can be reused for review, journaling, and later model training.

## Current Infrastructure Added

The backend now has a dedicated storage contract and endpoint for replay packets:

- `POST /api/v1/workbench/replay-snapshots`
- `POST /api/v1/workbench/replay-builder/build`
- `GET /api/v1/workbench/replay-cache?cache_key=...`
- `POST /api/v1/workbench/replay-cache/invalidate`

Relevant files:

- [workbench_services.py](D:/docker/atas-market-structure/src/atas_market_structure/workbench_services.py)
- [models.py](D:/docker/atas-market-structure/src/atas_market_structure/models.py)
- [replay_workbench.snapshot.sample.json](D:/docker/atas-market-structure/samples/replay_workbench.snapshot.sample.json)

## Next Implementation Steps

1. Build a replay-packet builder from adapter history and strategy-library matches.
2. Add a minimal browser UI that renders candles plus event and focus overlays.
3. Add an AI review action that consumes one stored replay packet and writes back focus-zone commentary.
4. Add saved operator annotations so the workbench becomes a reusable review surface, not a one-shot prompt tool.
