"""Backfill the continuous_state_events table from existing ingestions."""
import clickhouse_connect

client = clickhouse_connect.get_client(host="127.0.0.1", port=8123)

# Replenishment events
query = """
INSERT INTO market_data.continuous_state_events
SELECT
    instrument_symbol AS symbol,
    toStartOfInterval(toDateTime64(observed_window_end, 3, 'UTC'), INTERVAL 1 minute) AS bucket_start,
    JSONExtractString(observed_payload_json, 'same_price_replenishment', '0', 'track_id') AS track_id,
    'same_price_replenishment' AS event_kind,
    JSONExtractFloat(observed_payload_json, 'same_price_replenishment', '0', 'price') AS price,
    JSONExtractString(observed_payload_json, 'same_price_replenishment', '0', 'side') AS side,
    JSONExtractUInt(observed_payload_json, 'same_price_replenishment', '0', 'replenishment_count') AS replenishment_count,
    toDateTime64(observed_window_end, 3, 'UTC') AS observed_at,
    now64(3) AS stored_at
FROM market_data.ingestions
WHERE ingestion_kind = 'adapter_continuous_state'
  AND JSONLength(observed_payload_json, 'same_price_replenishment') > 0
"""
client.command(query)
print("Replenishment events backfilled.")

# Significant liquidity events
query2 = """
INSERT INTO market_data.continuous_state_events
SELECT
    instrument_symbol AS symbol,
    toStartOfInterval(toDateTime64(observed_window_end, 3, 'UTC'), INTERVAL 1 minute) AS bucket_start,
    JSONExtractString(observed_payload_json, 'significant_liquidity', '0', 'track_id') AS track_id,
    'significant_liquidity' AS event_kind,
    JSONExtractFloat(observed_payload_json, 'significant_liquidity', '0', 'price') AS price,
    JSONExtractString(observed_payload_json, 'significant_liquidity', '0', 'side') AS side,
    0 AS replenishment_count,
    toDateTime64(observed_window_end, 3, 'UTC') AS observed_at,
    now64(3) AS stored_at
FROM market_data.ingestions
WHERE ingestion_kind = 'adapter_continuous_state'
  AND JSONLength(observed_payload_json, 'significant_liquidity') > 0
"""
client.command(query2)
print("Liquidity events backfilled.")

# Verify
result = client.query("SELECT count() FROM market_data.continuous_state_events")
print(f"Total events in table: {result.first_row[0]}")
