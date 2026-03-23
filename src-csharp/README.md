# ATAS C# Collector

This folder contains the ATAS-side collector used by the local market-structure service.

## Current Status

- `status`: `minimal_runnable_mirror_dual_layer`
- builds successfully against the local ATAS installation on this machine
- the visible runtime indicator `AtasMarketStructureCollector` is now a thin shell over the full collector pipeline
- emits:
  - `continuous_state`
  - `trigger_burst`
  - `history_bars`
  - `history_footprint`
- polls:
  - `GET /api/v1/adapter/backfill-command`
- acknowledges:
  - `POST /api/v1/adapter/backfill-ack`
- keeps the collector lightweight:
  - compact state on a timer
  - trigger bursts only on meaningful liquidity events
  - history export on dedicated transports

## Main Files

- `AtasMarketStructure.Adapter/AtasMarketStructure.Adapter.csproj`
- `AtasMarketStructure.Adapter/Contracts/AdapterPayloads.cs`
- `AtasMarketStructure.Adapter/Collector/CollectorInfrastructure.cs`
- `AtasMarketStructure.Adapter/Collector/AtasMarketStructureCollector.cs`

## Build

From the repo root:

```powershell
cd D:\docker\atas-market-structure
dotnet build .\src-csharp\AtasMarketStructure.Adapter\AtasMarketStructure.Adapter.csproj
```

If ATAS is installed in a different path, override it:

```powershell
dotnet build .\src-csharp\AtasMarketStructure.Adapter\AtasMarketStructure.Adapter.csproj `
  -p:AtasInstallDir="C:\Path\To\ATAS Platform"
```

## Runtime Intent

The collector currently focuses on these observed facts:

- best bid and ask state
- cumulative trade pressure
- significant displayed liquidity
- same-price replenishment
- initiative drive context
- measured move context
- gap reference context
- post-harvest pullback or reversal context

The collector now prefers ATAS chart metadata for:

- `symbol`
- `root_symbol`
- `contract_symbol`
- `tick size`
- `chart_instance_id`
- chart display timezone fields
- instrument timezone fields

Manual overrides are still available, but they are now explicit opt-in so multiple charts do not collapse into the same instrument symbol by default.

## Transport Split

The collector now uses separate transport paths:

- realtime queue
  - `continuous_state`
  - `trigger_burst`
  - timeout `5s`
- history bars queue
  - timeout `20s`
- history footprint queue
  - timeout `45s`
- backfill command client
  - timeout `3s`
- backfill ack client
  - timeout `10s`

History export is no longer forced through the realtime queue, so slow historical posts do not silently block or drop realtime traffic.

## Time And Identity Semantics

The collector now emits:

- `source.chart_instance_id`
- `instrument.root_symbol`
- `instrument.contract_symbol`
- chart display timezone metadata
- collector local timezone metadata
- `timestamp_basis`
- `timezone_capture_confidence`

All persisted timestamps sent to the Python service are normalized to UTC.
If the chart display timezone cannot be read directly, the collector marks the export as derived or fallback instead of pretending it was direct metadata.

## Loading Notes

- the visible indicator name inside ATAS is `ATAS Market Structure Collector`
- probe indicators prefixed with `ZZ ATAS` are only for compatibility diagnostics
- after replacing `AtasMarketStructure.Adapter.dll`, ATAS may continue running the old in-memory collector until the platform is fully restarted
- if the backend still shows an older `source.adapter_version`, restart ATAS and reload the indicator

It does **not** place orders.

## Live-Safety Notes

The current collector is designed to reduce ATAS-side pressure by:

- buffering outbound HTTP
- dropping low-priority continuous-state payloads if the queue is full
- preserving history on dedicated queues instead of mixing it with realtime
- keeping trigger bursts event-driven instead of always-on

This is the intended default for manual trading alongside collection.

## Important Limitations

- `trigger_burst` is currently emitted immediately, so the `post_window` is intentionally minimal.
- session references like prior RTH close or prior value area still rely on indicator settings for now.
- continuous and raw mirror are now separated, but the current continuous layer only supports:
  - `roll_mode=none`
  - `roll_mode=by_contract_start`
  - `roll_mode=manual_sequence`
- `roll_mode=by_volume_proxy` is still intentionally unsupported.
- `adjustment_mode=gap_shift` is only a simple additive gap removal, not a full back-adjusted main contract.
- the collector uses a first-pass heuristic for:
  - initiative drives
  - same-price replenishment strength
  - post-harvest response

That is acceptable for phase 1 infrastructure.
Later iterations should improve fidelity, not add auto-trading.

## Manual Verification

After the Python service is running, the shortest operator validation path is:

```powershell
python .\tools\verify_mirror_vs_continuous.py `
  --contract-symbol NQM6 `
  --root-symbol NQ `
  --timeframe 1m `
  --window-start-utc 2026-03-22T09:30:00Z `
  --window-end-utc 2026-03-22T10:00:00Z
```

```powershell
python .\tools\verify_backfill_ack_flow.py `
  --instrument-symbol NQH6 `
  --contract-symbol NQH6 `
  --root-symbol NQ `
  --chart-instance-id chart-abc `
  --window-start-utc 2026-03-22T09:30:00Z `
  --window-end-utc 2026-03-22T10:00:00Z
```

```powershell
python .\tools\verify_timezone_fields.py .\samples\atas_adapter.history_bars.sample.json
```
