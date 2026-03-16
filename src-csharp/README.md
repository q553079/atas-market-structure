# ATAS C# Collector

This folder contains the first ATAS-side collector skeleton for the local market-structure service.

## Current Status

- `status`: `phase1_working_skeleton`
- builds successfully against the local ATAS installation on this machine
- the visible runtime indicator is currently a staged `shell` collector that is being expanded in-place
- emits:
  - `continuous_state`
  - `trigger_burst`
- keeps the collector lightweight:
  - compact state on a timer
  - trigger bursts only on meaningful liquidity events

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
- `tick size`
- `chart_instance_id`

Manual overrides are still available, but they are now explicit opt-in so multiple charts do not collapse into the same instrument symbol by default.

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
- keeping trigger bursts event-driven instead of always-on

This is the intended default for manual trading alongside collection.

## Important Limitations

- `trigger_burst` is currently emitted immediately, so the `post_window` is intentionally minimal.
- session references like prior RTH close or prior value area still rely on indicator settings for now.
- the collector uses a first-pass heuristic for:
  - initiative drives
  - same-price replenishment strength
  - post-harvest response

That is acceptable for phase 1 infrastructure.
Later iterations should improve fidelity, not add auto-trading.
