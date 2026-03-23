# Mirror / Continuous Field Matrix

This matrix is the current field contract for the ATAS mirror + continuous dual-layer path.

Legend:

- `C# payload`: field emitted by `src-csharp/AtasMarketStructure.Adapter/Contracts/AdapterPayloads.cs`
- `Python model`: field accepted by the Python pydantic models
- `Repository`: SQLite column or runtime state
- `API response`: field returned by `mirror-bars`, `continuous-bars`, or backfill control APIs

## Identity Fields

| Semantic | C# payload | Python model | Repository | API response | Required | Default / degrade | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| display symbol | `instrument.symbol` | `InstrumentRef.symbol` | `atas_chart_bars_raw.symbol` | `mirror-bars.bars[].symbol` | yes | none | Raw mirror keeps the concrete display symbol from ATAS. |
| root symbol | `instrument.root_symbol` | `InstrumentRef.root_symbol` | `atas_chart_bars_raw.root_symbol` | `mirror-bars.bars[].root_symbol`, `continuous-bars.root_symbol` | strongly preferred | `null` in mirror rows; continuous query requires caller input | Continuous is keyed by root symbol. |
| contract symbol | `instrument.contract_symbol` | `InstrumentRef.contract_symbol` | `atas_chart_bars_raw.contract_symbol` | `mirror-bars.contract_symbol`, `mirror-bars.bars[].contract_symbol`, `continuous-bars.contract_segments[].contract_symbol`, `continuous-bars.candles[].source_contract_symbol` | strongly preferred for mirror | falls back to `instrument.symbol` during ingestion | Raw mirror never collapses multiple contracts into one row key. |
| chart identity | `source.chart_instance_id` | `SourceRef.chart_instance_id` | `atas_chart_bars_raw.chart_instance_id` | `mirror-bars.chart_instance_id`, `mirror-bars.bars[].chart_instance_id`, backfill request/ack fields | strongly preferred | `null` | Continuous derivation dedupes duplicate contract bars across chart instances and does not expose chart_instance_id as a root-layer key. |

## Time Fields

| Semantic | C# payload | Python model | Repository | API response | Required | Default / degrade | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| raw ATAS UTC timestamp | `bars[].bar_timestamp_utc` | `AdapterHistoryBar.bar_timestamp_utc` | `atas_chart_bars_raw.bar_timestamp_utc` | `mirror-bars.bars[].bar_timestamp_utc` | optional but preferred | if missing, ingestion falls back to `bars[].started_at` | Preserved separately from `source_started_at` for audit clarity. |
| primary UTC start | `bars[].bar_timestamp_utc` or normalized `bars[].started_at` | derived in `AdapterIngestionService` | `atas_chart_bars_raw.started_at_utc` | `mirror-bars.bars[].started_at_utc`, `continuous-bars.candles[].started_at_utc`, `continuous-bars.contract_segments[].segment_start_utc` | yes | falls back to normalized `started_at` | Primary raw mirror key. |
| primary UTC end | normalized `bars[].ended_at` | `AdapterHistoryBar.ended_at` | `atas_chart_bars_raw.ended_at_utc` | `mirror-bars.bars[].ended_at_utc`, `continuous-bars.candles[].ended_at_utc`, `continuous-bars.contract_segments[].segment_end_utc` | yes | none | All stored end times remain UTC. |
| source bar start | `bars[].started_at` | `AdapterHistoryBar.started_at` | `atas_chart_bars_raw.source_started_at` | `mirror-bars.bars[].source_started_at`, `continuous-bars.candles[].source_started_at_utc` | yes | none | Audit field, not the raw mirror primary key. |
| original bar text | `bars[].original_bar_time_text` | `AdapterHistoryBar.original_bar_time_text` | `atas_chart_bars_raw.original_bar_time_text` | `mirror-bars.bars[].original_bar_time_text` | optional | `null` | Preserves the pre-normalized ATAS display string. |

## Timezone Audit Fields

| Semantic | C# payload | Python model | Repository | API response | Required | Default / degrade | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| chart display timezone mode | `source.chart_display_timezone_mode` | `SourceRef.chart_display_timezone_mode` | `atas_chart_bars_raw.chart_display_timezone_mode` | `mirror-bars.bars[].chart_display_timezone_mode` | optional | `null` | Must reflect direct vs fallback semantics honestly. |
| chart display timezone name | `source.chart_display_timezone_name` | `SourceRef.chart_display_timezone_name` | `atas_chart_bars_raw.chart_display_timezone_name` | `mirror-bars.bars[].chart_display_timezone_name` | optional | `null` | If missing, fallback remains explicit through other audit fields. |
| chart display UTC offset | `source.chart_display_utc_offset_minutes` | `SourceRef.chart_display_utc_offset_minutes` | `atas_chart_bars_raw.chart_display_utc_offset_minutes` | `mirror-bars.bars[].chart_display_utc_offset_minutes` | optional | `null` | Audit only; primary storage remains UTC. |
| instrument timezone value | `source.instrument_timezone_value` | `SourceRef.instrument_timezone_value` | `atas_chart_bars_raw.instrument_timezone_value` | `mirror-bars.bars[].instrument_timezone_value` | optional | `null` | Used when chart display timezone cannot be read directly. |
| instrument timezone source | `source.instrument_timezone_source` | `SourceRef.instrument_timezone_source` | `atas_chart_bars_raw.instrument_timezone_source` | `mirror-bars.bars[].instrument_timezone_source` | optional | `null` | Expected values include `exchange_metadata` or `unavailable`. |
| collector local timezone name | `source.collector_local_timezone_name` | `SourceRef.collector_local_timezone_name` | `atas_chart_bars_raw.collector_local_timezone_name` | `mirror-bars.bars[].collector_local_timezone_name` | optional | `null` | Audit field only. |
| collector local UTC offset | `source.collector_local_utc_offset_minutes` | `SourceRef.collector_local_utc_offset_minutes` | `atas_chart_bars_raw.collector_local_utc_offset_minutes` | `mirror-bars.bars[].collector_local_utc_offset_minutes` | optional | `null` | Audit field only. |
| timestamp basis | `source.timestamp_basis` | `SourceRef.timestamp_basis` | `atas_chart_bars_raw.timestamp_basis` | `mirror-bars.bars[].timestamp_basis` | optional but recommended | `null` | Must say when timestamps came from fallback or derived metadata. |
| timezone capture confidence | `source.timezone_capture_confidence` | `SourceRef.timezone_capture_confidence` | `atas_chart_bars_raw.timezone_capture_confidence` | `mirror-bars.bars[].timezone_capture_confidence` | optional but recommended | `null` | Must never claim `high` for guessed values. |

## Continuous Derived Fields

| Semantic | Source | Python model | Repository | API response | Required | Default / degrade | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| roll mode | query param | `RollMode` | not persisted | `continuous-bars.roll_mode` | yes | legacy values map to `by_contract_start` with warning | `by_volume_proxy` currently returns an explicit error. |
| adjustment mode | query param | `ContinuousAdjustmentMode` | not persisted | `continuous-bars.adjustment_mode`, `continuous-bars.candles[].adjustment_mode` | yes | defaults to `none` | `gap_shift` is additive gap removal only, not full back-adjustment. |
| contract segments | derived from raw mirror rows | `ContinuousContractSegment` | not persisted | `continuous-bars.contract_segments[]` | yes | empty when no raw mirror rows matched | Explains which contract supplied each slice of the derived series. |
| derived candle contract source | derived from raw mirror rows | `ContinuousDerivedBar.source_contract_symbol` | not persisted | `continuous-bars.candles[].source_contract_symbol` | yes | none | Continuous response must always say which contract produced each candle. |
| adjustment offset | derived from segment stitching | `ContinuousDerivedBar.adjustment_offset` | not persisted | `continuous-bars.candles[].adjustment_offset`, `continuous-bars.contract_segments[].adjustment_offset` | yes | `0.0` | Keeps derived behavior explainable. |

## Backfill Control Fields

| Semantic | C# payload | Python model | Repository | API response | Required | Default / degrade | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| request id | `request_id` | `ReplayWorkbenchAtasBackfillRequest / AdapterBackfillAcknowledgeRequest` | server memory only (`ReplayWorkbenchAtasBackfillRecord`) | `backfill-command.request.request_id`, `backfill-ack.request.request_id` | yes | none | Control-plane state is currently in memory, not SQLite. |
| cache key | `cache_key` | same | server memory only | `backfill-command.request.cache_key`, `backfill-ack.request.cache_key` | yes on command, optional on ack | ack may omit and reuse existing request cache key | Used to rebuild or verify replay snapshots. |
| acknowledged history bars | `acknowledged_history_bars` | `AdapterBackfillAcknowledgeRequest.acknowledged_history_bars` | server memory only | `backfill-ack.request.acknowledged_history_bars` | yes | `false` | Indicates whether the collector actually resent bars. |
| acknowledged history footprint | `acknowledged_history_footprint` | `AdapterBackfillAcknowledgeRequest.acknowledged_history_footprint` | server memory only | `backfill-ack.request.acknowledged_history_footprint` | yes | `false` | Separate from history bars. |
| latest loaded bar started at | `latest_loaded_bar_started_at` | `AdapterBackfillAcknowledgeRequest.latest_loaded_bar_started_at` | server memory only | `backfill-ack.request.latest_loaded_bar_started_at` | optional | `null` | Audit field from collector, not used as raw mirror storage time. |
| target root symbol | `target_root_symbol` | `ReplayWorkbenchAtasBackfillRequest.target_root_symbol` | server memory only | `backfill-command.request.target_root_symbol`, `backfill-ack.request.target_root_symbol` | optional | `null` | Explicit adapter-facing root target when different from `instrument_symbol`. |
| target contract symbol | `target_contract_symbol` | `ReplayWorkbenchAtasBackfillRequest.target_contract_symbol` | server memory only | `backfill-command.request.target_contract_symbol`, `backfill-ack.request.target_contract_symbol` | optional | `null` | Explicit adapter-facing contract target when different from `instrument_symbol`. |

## Explicit Non-Mappings

- `continuous-bars` does not write back into `atas_chart_bars_raw`
- `continuous-bars` does not read from `chart_candles`
- backfill request/ack state is not yet persisted in SQLite
- `mirror-bars` exposes raw mirror rows directly instead of translating them into a continuous-style candle schema
