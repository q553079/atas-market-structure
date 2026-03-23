# Mirror vs Continuous

## What Is Raw Mirror

`raw mirror` means the bar exactly as one ATAS chart instance exported it.

Properties:

- source table: `atas_chart_bars_raw`
- primary key: `chart_instance_id + contract_symbol + timeframe + started_at_utc`
- scope: one concrete contract on one concrete chart instance
- keeps timezone audit metadata
- keeps `bar_timestamp_utc`, `source_started_at`, and `original_bar_time_text`

This is the contract-faithful view. It is the right answer when the operator asks:

- what did chart `chart-abc` actually load?
- what did `NQH6` look like before rollover?
- which timezone basis did the collector use?

## What Is Continuous

`continuous` means a derived series built from raw mirror rows for a `root_symbol`.

Properties:

- runtime source: `ContinuousContractService`
- input data: `atas_chart_bars_raw`
- output data: derived `candles` plus `contract_segments`
- never writes back into `atas_chart_bars_raw`
- never pretends to be the original contract tape

This is the analysis view. It is the right answer when the operator asks:

- show me `NQ` across a rollover window
- which contract segments contributed to this root-symbol view?
- did the system apply any gap shift?

## Why Mirror Cannot Replace Continuous

Mirror and continuous answer different questions.

- mirror is exact but contract-specific
- continuous is comparable across contracts but derived
- mirror may contain overlapping contracts from multiple charts
- continuous must resolve one contract sequence and make that choice explicit

Using mirror as if it were continuous causes two failures:

- rollover windows become broken or duplicated
- timezone and chart identity facts get mixed into a root-symbol analysis result

## Currently Supported roll_mode Values

- `none`
  - returns only one contract segment
  - does not stitch across contracts
  - if multiple contracts exist in the window, the response includes a warning
- `by_contract_start`
  - switches contracts when the next contract first appears in raw mirror data
  - emits multiple `contract_segments` when the window spans rollover
- `manual_sequence`
  - requires explicit `contract_sequence=...`
  - rejects ambiguous windows instead of guessing

Current explicit non-support:

- `by_volume_proxy`
  - returns a clear error
  - real volume/open-interest roll logic is not implemented yet

## Currently Supported adjustment_mode Values

- `none`
  - no price adjustment
  - gaps remain visible at roll boundaries
- `gap_shift`
  - additive gap removal only
  - not a full back-adjusted continuous contract

## UTC and Timezone Semantics

Primary storage times are UTC:

- `started_at_utc`
- `ended_at_utc`
- `bar_timestamp_utc`

Audit/display fields are preserved separately:

- `source_started_at`
- `original_bar_time_text`
- chart display timezone fields
- instrument timezone fields
- `timestamp_basis`
- `timezone_capture_confidence`

If chart display timezone was not captured directly, the payload must say so. Fallback values are not allowed to masquerade as `direct`.

## Manual Verification

Use these helpers after starting the local service:

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
