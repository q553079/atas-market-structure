using System.Text.Json.Serialization;

namespace AtasMarketStructure.Adapter.Contracts;

internal sealed class SourceEnvelope
{
    [JsonPropertyName("system")]
    public string System { get; init; } = "ATAS";

    [JsonPropertyName("instance_id")]
    public string InstanceId { get; init; } = string.Empty;

    [JsonPropertyName("chart_instance_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartInstanceId { get; init; }

    [JsonPropertyName("adapter_version")]
    public string AdapterVersion { get; init; } = string.Empty;

    [JsonPropertyName("chart_display_timezone_mode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartDisplayTimezoneMode { get; init; }

    [JsonPropertyName("chart_display_timezone_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartDisplayTimezoneName { get; init; }

    [JsonPropertyName("chart_display_utc_offset_minutes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ChartDisplayUtcOffsetMinutes { get; init; }

    [JsonPropertyName("instrument_timezone_value")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InstrumentTimezoneValue { get; init; }

    [JsonPropertyName("instrument_timezone_source")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InstrumentTimezoneSource { get; init; }

    [JsonPropertyName("collector_local_timezone_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? CollectorLocalTimezoneName { get; init; }

    [JsonPropertyName("collector_local_utc_offset_minutes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? CollectorLocalUtcOffsetMinutes { get; init; }

    [JsonPropertyName("timestamp_basis")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimestampBasis { get; init; }

    [JsonPropertyName("timezone_capture_confidence")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimezoneCaptureConfidence { get; init; }
}

internal sealed class InstrumentEnvelope
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; init; } = string.Empty;

    [JsonPropertyName("root_symbol")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RootSymbol { get; init; }

    [JsonPropertyName("contract_symbol")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ContractSymbol { get; init; }

    [JsonPropertyName("venue")]
    public string Venue { get; init; } = string.Empty;

    [JsonPropertyName("tick_size")]
    public double TickSize { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "USD";
}

internal sealed class TimeContextPayload
{
    [JsonPropertyName("instrument_timezone_value")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InstrumentTimezoneValue { get; init; }

    [JsonPropertyName("instrument_timezone_source")]
    public string InstrumentTimezoneSource { get; init; } = "unavailable";

    [JsonPropertyName("chart_display_timezone_mode")]
    public string ChartDisplayTimezoneMode { get; init; } = "unknown";

    [JsonPropertyName("chart_display_timezone_source")]
    public string ChartDisplayTimezoneSource { get; init; } = "unavailable";

    [JsonPropertyName("chart_display_timezone_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartDisplayTimezoneName { get; init; }

    [JsonPropertyName("chart_display_utc_offset_minutes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ChartDisplayUtcOffsetMinutes { get; init; }

    [JsonPropertyName("collector_local_timezone_name")]
    public string CollectorLocalTimezoneName { get; init; } = string.Empty;

    [JsonPropertyName("collector_local_utc_offset_minutes")]
    public int CollectorLocalUtcOffsetMinutes { get; init; }

    [JsonPropertyName("timestamp_basis")]
    public string TimestampBasis { get; init; } = "collector_local_timezone";

    [JsonPropertyName("started_at_output_timezone")]
    public string StartedAtOutputTimezone { get; init; } = "UTC";

    [JsonPropertyName("started_at_time_source")]
    public string StartedAtTimeSource { get; init; } = "collector_local_timezone";

    [JsonPropertyName("timezone_capture_confidence")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimezoneCaptureConfidence { get; init; }
}

internal sealed class SessionContextPayload
{
    [JsonPropertyName("session_code")]
    public string SessionCode { get; init; } = string.Empty;

    [JsonPropertyName("trading_date")]
    public string TradingDate { get; init; } = string.Empty;

    [JsonPropertyName("is_rth_open")]
    public bool IsRthOpen { get; init; }

    [JsonPropertyName("prior_rth_close")]
    public double PriorRthClose { get; init; }

    [JsonPropertyName("prior_rth_high")]
    public double PriorRthHigh { get; init; }

    [JsonPropertyName("prior_rth_low")]
    public double PriorRthLow { get; init; }

    [JsonPropertyName("prior_value_area_low")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? PriorValueAreaLow { get; init; }

    [JsonPropertyName("prior_value_area_high")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? PriorValueAreaHigh { get; init; }

    [JsonPropertyName("prior_point_of_control")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? PriorPointOfControl { get; init; }

    [JsonPropertyName("overnight_high")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? OvernightHigh { get; init; }

    [JsonPropertyName("overnight_low")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? OvernightLow { get; init; }

    [JsonPropertyName("overnight_mid")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? OvernightMid { get; init; }
}

internal sealed class PriceStatePayload
{
    [JsonPropertyName("last_price")]
    public double LastPrice { get; init; }

    [JsonPropertyName("best_bid")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestBid { get; init; }

    [JsonPropertyName("best_ask")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestAsk { get; init; }

    [JsonPropertyName("local_range_low")]
    public double LocalRangeLow { get; init; }

    [JsonPropertyName("local_range_high")]
    public double LocalRangeHigh { get; init; }

    [JsonPropertyName("opening_range_low")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? OpeningRangeLow { get; init; }

    [JsonPropertyName("opening_range_high")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? OpeningRangeHigh { get; init; }

    [JsonPropertyName("opening_range_size_ticks")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? OpeningRangeSizeTicks { get; init; }
}

internal sealed class DepthCoveragePayload
{
    [JsonPropertyName("coverage_state")]
    public string CoverageState { get; init; } = "depth_unavailable";

    [JsonPropertyName("snapshot_level_count")]
    public int SnapshotLevelCount { get; init; }

    [JsonPropertyName("tracked_liquidity_count")]
    public int TrackedLiquidityCount { get; init; }

    [JsonPropertyName("last_snapshot_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? LastSnapshotAt { get; init; }

    [JsonPropertyName("best_bid_available")]
    public bool BestBidAvailable { get; init; }

    [JsonPropertyName("best_ask_available")]
    public bool BestAskAvailable { get; init; }
}

internal sealed class TradeSummaryPayload
{
    [JsonPropertyName("trade_count")]
    public int TradeCount { get; init; }

    [JsonPropertyName("volume")]
    public int Volume { get; init; }

    [JsonPropertyName("aggressive_buy_volume")]
    public int AggressiveBuyVolume { get; init; }

    [JsonPropertyName("aggressive_sell_volume")]
    public int AggressiveSellVolume { get; init; }

    [JsonPropertyName("net_delta")]
    public int NetDelta { get; init; }
}

internal sealed class SignificantLiquidityPayload
{
    [JsonPropertyName("track_id")]
    public string TrackId { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("current_size")]
    public int CurrentSize { get; init; }

    [JsonPropertyName("max_seen_size")]
    public int MaxSeenSize { get; init; }

    [JsonPropertyName("distance_from_price_ticks")]
    public int DistanceFromPriceTicks { get; init; }

    [JsonPropertyName("first_observed_at")]
    public DateTime FirstObservedAt { get; init; }

    [JsonPropertyName("last_observed_at")]
    public DateTime LastObservedAt { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "active";

    [JsonPropertyName("touch_count")]
    public int TouchCount { get; init; }

    [JsonPropertyName("executed_volume_estimate")]
    public int ExecutedVolumeEstimate { get; init; }

    [JsonPropertyName("replenishment_count")]
    public int ReplenishmentCount { get; init; }

    [JsonPropertyName("buyers_hitting_same_level_count")]
    public int BuyersHittingSameLevelCount { get; init; }

    [JsonPropertyName("sellers_hitting_same_level_count")]
    public int SellersHittingSameLevelCount { get; init; }

    [JsonPropertyName("pull_count")]
    public int PullCount { get; init; }

    [JsonPropertyName("move_count")]
    public int MoveCount { get; init; }

    [JsonPropertyName("price_reaction_ticks")]
    public int? PriceReactionTicks { get; init; }

    [JsonPropertyName("heat_score")]
    public double HeatScore { get; init; }
}

internal sealed class SamePriceReplenishmentPayload
{
    [JsonPropertyName("track_id")]
    public string TrackId { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("current_size")]
    public int CurrentSize { get; init; }

    [JsonPropertyName("distance_from_price_ticks")]
    public int DistanceFromPriceTicks { get; init; }

    [JsonPropertyName("touch_count")]
    public int TouchCount { get; init; }

    [JsonPropertyName("replenishment_count")]
    public int ReplenishmentCount { get; init; }

    [JsonPropertyName("buyers_hitting_same_level_count")]
    public int BuyersHittingSameLevelCount { get; init; }

    [JsonPropertyName("sellers_hitting_same_level_count")]
    public int SellersHittingSameLevelCount { get; init; }
}

internal sealed class GapReferencePayload
{
    [JsonPropertyName("gap_id")]
    public string GapId { get; init; } = string.Empty;

    [JsonPropertyName("direction")]
    public string Direction { get; init; } = string.Empty;

    [JsonPropertyName("opened_at")]
    public DateTime OpenedAt { get; init; }

    [JsonPropertyName("gap_low")]
    public double GapLow { get; init; }

    [JsonPropertyName("gap_high")]
    public double GapHigh { get; init; }

    [JsonPropertyName("gap_size_ticks")]
    public int GapSizeTicks { get; init; }

    [JsonPropertyName("first_touch_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? FirstTouchAt { get; init; }

    [JsonPropertyName("max_fill_ticks")]
    public int MaxFillTicks { get; init; }

    [JsonPropertyName("fill_ratio")]
    public double FillRatio { get; init; }

    [JsonPropertyName("fill_attempt_count")]
    public int FillAttemptCount { get; init; }

    [JsonPropertyName("accepted_inside_gap")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? AcceptedInsideGap { get; init; }

    [JsonPropertyName("rejected_from_gap")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? RejectedFromGap { get; init; }

    [JsonPropertyName("fully_filled_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? FullyFilledAt { get; init; }
}

internal sealed class InitiativeDrivePayload
{
    [JsonPropertyName("drive_id")]
    public string DriveId { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("started_at")]
    public DateTime StartedAt { get; init; }

    [JsonPropertyName("price_low")]
    public double PriceLow { get; init; }

    [JsonPropertyName("price_high")]
    public double PriceHigh { get; init; }

    [JsonPropertyName("aggressive_volume")]
    public int AggressiveVolume { get; init; }

    [JsonPropertyName("net_delta")]
    public int NetDelta { get; init; }

    [JsonPropertyName("trade_count")]
    public int TradeCount { get; init; }

    [JsonPropertyName("consumed_price_levels")]
    public int ConsumedPriceLevels { get; init; }

    [JsonPropertyName("price_travel_ticks")]
    public int PriceTravelTicks { get; init; }

    [JsonPropertyName("max_counter_move_ticks")]
    public int MaxCounterMoveTicks { get; init; }

    [JsonPropertyName("continuation_seconds")]
    public int ContinuationSeconds { get; init; }
}

internal sealed class ManipulationLegPayload
{
    [JsonPropertyName("leg_id")]
    public string LegId { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("started_at")]
    public DateTime StartedAt { get; init; }

    [JsonPropertyName("ended_at")]
    public DateTime EndedAt { get; init; }

    [JsonPropertyName("price_low")]
    public double PriceLow { get; init; }

    [JsonPropertyName("price_high")]
    public double PriceHigh { get; init; }

    [JsonPropertyName("displacement_ticks")]
    public int DisplacementTicks { get; init; }

    [JsonPropertyName("primary_objective_ticks")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? PrimaryObjectiveTicks { get; init; }

    [JsonPropertyName("secondary_objective_ticks")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? SecondaryObjectiveTicks { get; init; }

    [JsonPropertyName("primary_objective_reached")]
    public bool PrimaryObjectiveReached { get; init; }

    [JsonPropertyName("secondary_objective_reached")]
    public bool SecondaryObjectiveReached { get; init; }
}

internal sealed class MeasuredMovePayload
{
    [JsonPropertyName("measurement_id")]
    public string MeasurementId { get; init; } = string.Empty;

    [JsonPropertyName("measured_subject_id")]
    public string MeasuredSubjectId { get; init; } = string.Empty;

    [JsonPropertyName("measured_subject_kind")]
    public string MeasuredSubjectKind { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("anchor_price")]
    public double AnchorPrice { get; init; }

    [JsonPropertyName("latest_price")]
    public double LatestPrice { get; init; }

    [JsonPropertyName("achieved_distance_ticks")]
    public int AchievedDistanceTicks { get; init; }

    [JsonPropertyName("reference_kind")]
    public string ReferenceKind { get; init; } = string.Empty;

    [JsonPropertyName("reference_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ReferenceId { get; init; }

    [JsonPropertyName("reference_distance_ticks")]
    public int ReferenceDistanceTicks { get; init; }

    [JsonPropertyName("achieved_multiple")]
    public double AchievedMultiple { get; init; }

    [JsonPropertyName("body_confirmed_threshold_multiple")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BodyConfirmedThresholdMultiple { get; init; }

    [JsonPropertyName("next_target_multiple")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? NextTargetMultiple { get; init; }

    [JsonPropertyName("invalidated")]
    public bool Invalidated { get; init; }
}

internal sealed class PostHarvestResponsePayload
{
    [JsonPropertyName("response_id")]
    public string ResponseId { get; init; } = string.Empty;

    [JsonPropertyName("harvest_subject_id")]
    public string HarvestSubjectId { get; init; } = string.Empty;

    [JsonPropertyName("harvest_subject_kind")]
    public string HarvestSubjectKind { get; init; } = string.Empty;

    [JsonPropertyName("harvest_side")]
    public string HarvestSide { get; init; } = string.Empty;

    [JsonPropertyName("harvest_completed_at")]
    public DateTime HarvestCompletedAt { get; init; }

    [JsonPropertyName("harvested_price_low")]
    public double HarvestedPriceLow { get; init; }

    [JsonPropertyName("harvested_price_high")]
    public double HarvestedPriceHigh { get; init; }

    [JsonPropertyName("completion_ratio")]
    public double CompletionRatio { get; init; }

    [JsonPropertyName("continuation_ticks_after_completion")]
    public int ContinuationTicksAfterCompletion { get; init; }

    [JsonPropertyName("consolidation_range_ticks")]
    public int ConsolidationRangeTicks { get; init; }

    [JsonPropertyName("pullback_ticks")]
    public int PullbackTicks { get; init; }

    [JsonPropertyName("reversal_ticks")]
    public int ReversalTicks { get; init; }

    [JsonPropertyName("seconds_to_first_pullback")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? SecondsToFirstPullback { get; init; }

    [JsonPropertyName("seconds_to_reversal")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? SecondsToReversal { get; init; }

    [JsonPropertyName("reached_next_opposing_liquidity")]
    public bool ReachedNextOpposingLiquidity { get; init; }

    [JsonPropertyName("next_opposing_liquidity_price")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? NextOpposingLiquidityPrice { get; init; }

    [JsonPropertyName("post_harvest_delta")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? PostHarvestDelta { get; init; }

    [JsonPropertyName("outcome")]
    public string Outcome { get; init; } = string.Empty;
}

internal sealed class ZoneInteractionPayload
{
    [JsonPropertyName("zone_id")]
    public string ZoneId { get; init; } = string.Empty;

    [JsonPropertyName("zone_low")]
    public double ZoneLow { get; init; }

    [JsonPropertyName("zone_high")]
    public double ZoneHigh { get; init; }

    [JsonPropertyName("started_at")]
    public DateTime StartedAt { get; init; }

    [JsonPropertyName("executed_volume_against")]
    public int ExecutedVolumeAgainst { get; init; }

    [JsonPropertyName("replenishment_count")]
    public int ReplenishmentCount { get; init; }

    [JsonPropertyName("buyers_hitting_same_level_count")]
    public int BuyersHittingSameLevelCount { get; init; }

    [JsonPropertyName("sellers_hitting_same_level_count")]
    public int SellersHittingSameLevelCount { get; init; }

    [JsonPropertyName("pull_count")]
    public int PullCount { get; init; }

    [JsonPropertyName("price_rejection_ticks")]
    public int PriceRejectionTicks { get; init; }

    [JsonPropertyName("seconds_held")]
    public int SecondsHeld { get; init; }
}

internal sealed class EmaContextPayload
{
    [JsonPropertyName("ema20")]
    public double Ema20 { get; init; }

    [JsonPropertyName("ema20_distance_ticks")]
    public int Ema20DistanceTicks { get; init; }

    [JsonPropertyName("ema20_slope")]
    public double Ema20Slope { get; init; }

    [JsonPropertyName("ema20_reclaim_confirmed")]
    public bool Ema20ReclaimConfirmed { get; init; }

    [JsonPropertyName("bars_above_ema20_after_reclaim")]
    public int BarsAboveEma20AfterReclaim { get; init; }
}

internal sealed class ReferenceLevelPayload
{
    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("notes")]
    public List<string> Notes { get; init; } = new();
}

internal sealed class ContinuousStatePayload
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "1.0.0";

    [JsonPropertyName("message_id")]
    public string MessageId { get; init; } = string.Empty;

    [JsonPropertyName("message_type")]
    public string MessageType { get; init; } = "continuous_state";

    [JsonPropertyName("emitted_at")]
    public DateTime EmittedAt { get; init; }

    [JsonPropertyName("observed_window_start")]
    public DateTime ObservedWindowStart { get; init; }

    [JsonPropertyName("observed_window_end")]
    public DateTime ObservedWindowEnd { get; init; }

    [JsonPropertyName("source")]
    public SourceEnvelope Source { get; init; } = new();

    [JsonPropertyName("instrument")]
    public InstrumentEnvelope Instrument { get; init; } = new();

    [JsonPropertyName("display_timeframe")]
    public string DisplayTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("time_context")]
    public TimeContextPayload TimeContext { get; init; } = new();

    [JsonPropertyName("session_context")]
    public SessionContextPayload SessionContext { get; init; } = new();

    [JsonPropertyName("price_state")]
    public PriceStatePayload PriceState { get; init; } = new();

    [JsonPropertyName("trade_summary")]
    public TradeSummaryPayload TradeSummary { get; init; } = new();

    [JsonPropertyName("depth_coverage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DepthCoveragePayload? DepthCoverage { get; init; }

    [JsonPropertyName("significant_liquidity")]
    public List<SignificantLiquidityPayload> SignificantLiquidity { get; init; } = new();

    [JsonPropertyName("same_price_replenishment")]
    public List<SamePriceReplenishmentPayload> SamePriceReplenishment { get; init; } = new();

    [JsonPropertyName("gap_reference")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public GapReferencePayload? GapReference { get; init; }

    [JsonPropertyName("active_initiative_drive")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public InitiativeDrivePayload? ActiveInitiativeDrive { get; init; }

    [JsonPropertyName("active_manipulation_leg")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ManipulationLegPayload? ActiveManipulationLeg { get; init; }

    [JsonPropertyName("active_measured_move")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public MeasuredMovePayload? ActiveMeasuredMove { get; init; }

    [JsonPropertyName("active_post_harvest_response")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PostHarvestResponsePayload? ActivePostHarvestResponse { get; init; }

    [JsonPropertyName("active_zone_interaction")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ZoneInteractionPayload? ActiveZoneInteraction { get; init; }

    [JsonPropertyName("ema_context")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public EmaContextPayload? EmaContext { get; init; }

    [JsonPropertyName("reference_levels")]
    public List<ReferenceLevelPayload> ReferenceLevels { get; init; } = new();
}

internal class HistoryBarPayload
{
    [JsonPropertyName("started_at")]
    public DateTime StartedAt { get; init; }

    [JsonPropertyName("ended_at")]
    public DateTime EndedAt { get; init; }

    [JsonPropertyName("open")]
    public double Open { get; init; }

    [JsonPropertyName("high")]
    public double High { get; init; }

    [JsonPropertyName("low")]
    public double Low { get; init; }

    [JsonPropertyName("close")]
    public double Close { get; init; }

    [JsonPropertyName("volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Volume { get; init; }

    [JsonPropertyName("delta")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Delta { get; init; }

    [JsonPropertyName("bid_volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? BidVolume { get; init; }

    [JsonPropertyName("ask_volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? AskVolume { get; init; }

    [JsonPropertyName("bar_timestamp_utc")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? BarTimestampUtc { get; init; }

    [JsonPropertyName("original_bar_time_text")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? OriginalBarTimeText { get; init; }
}

internal sealed class HistoryFootprintLevelPayload
{
    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("bid_volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? BidVolume { get; init; }

    [JsonPropertyName("ask_volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? AskVolume { get; init; }

    [JsonPropertyName("total_volume")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? TotalVolume { get; init; }

    [JsonPropertyName("delta")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Delta { get; init; }

    [JsonPropertyName("trade_count")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? TradeCount { get; init; }
}

internal sealed class HistoryFootprintBarPayload : HistoryBarPayload
{
    [JsonPropertyName("price_levels")]
    public List<HistoryFootprintLevelPayload> PriceLevels { get; init; } = new();
}

internal sealed class HistoryBarsPayload
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "1.0.0";

    [JsonPropertyName("message_id")]
    public string MessageId { get; init; } = string.Empty;

    [JsonPropertyName("message_type")]
    public string MessageType { get; init; } = "history_bars";

    [JsonPropertyName("emitted_at")]
    public DateTime EmittedAt { get; init; }

    [JsonPropertyName("observed_window_start")]
    public DateTime ObservedWindowStart { get; init; }

    [JsonPropertyName("observed_window_end")]
    public DateTime ObservedWindowEnd { get; init; }

    [JsonPropertyName("source")]
    public SourceEnvelope Source { get; init; } = new();

    [JsonPropertyName("instrument")]
    public InstrumentEnvelope Instrument { get; init; } = new();

    [JsonPropertyName("display_timeframe")]
    public string DisplayTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("time_context")]
    public TimeContextPayload TimeContext { get; init; } = new();

    [JsonPropertyName("bar_timeframe")]
    public string BarTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("bars")]
    public List<HistoryBarPayload> Bars { get; init; } = new();
}

internal sealed class HistoryFootprintPayload
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "1.0.0";

    [JsonPropertyName("message_id")]
    public string MessageId { get; init; } = string.Empty;

    [JsonPropertyName("message_type")]
    public string MessageType { get; init; } = "history_footprint";

    [JsonPropertyName("emitted_at")]
    public DateTime EmittedAt { get; init; }

    [JsonPropertyName("observed_window_start")]
    public DateTime ObservedWindowStart { get; init; }

    [JsonPropertyName("observed_window_end")]
    public DateTime ObservedWindowEnd { get; init; }

    [JsonPropertyName("source")]
    public SourceEnvelope Source { get; init; } = new();

    [JsonPropertyName("instrument")]
    public InstrumentEnvelope Instrument { get; init; } = new();

    [JsonPropertyName("display_timeframe")]
    public string DisplayTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("time_context")]
    public TimeContextPayload TimeContext { get; init; } = new();

    [JsonPropertyName("batch_id")]
    public string BatchId { get; init; } = string.Empty;

    [JsonPropertyName("bar_timeframe")]
    public string BarTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("chunk_index")]
    public int ChunkIndex { get; init; }

    [JsonPropertyName("chunk_count")]
    public int ChunkCount { get; init; }

    [JsonPropertyName("bars")]
    public List<HistoryFootprintBarPayload> Bars { get; init; } = new();
}

internal sealed class TriggerInfoPayload
{
    [JsonPropertyName("trigger_id")]
    public string TriggerId { get; init; } = string.Empty;

    [JsonPropertyName("trigger_type")]
    public string TriggerType { get; init; } = string.Empty;

    [JsonPropertyName("triggered_at")]
    public DateTime TriggeredAt { get; init; }

    [JsonPropertyName("price")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? Price { get; init; }

    [JsonPropertyName("reason_codes")]
    public List<string> ReasonCodes { get; init; } = new();
}

internal sealed class TradeEventPayload
{
    [JsonPropertyName("event_time")]
    public DateTime EventTime { get; init; }

    [JsonPropertyName("local_sequence")]
    public int LocalSequence { get; init; }

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("size")]
    public int Size { get; init; }

    [JsonPropertyName("aggressor_side")]
    public string AggressorSide { get; init; } = "neutral";

    [JsonPropertyName("best_bid_before")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestBidBefore { get; init; }

    [JsonPropertyName("best_ask_before")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestAskBefore { get; init; }

    [JsonPropertyName("best_bid_after")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestBidAfter { get; init; }

    [JsonPropertyName("best_ask_after")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestAskAfter { get; init; }
}

internal sealed class DepthEventPayload
{
    [JsonPropertyName("event_time")]
    public DateTime EventTime { get; init; }

    [JsonPropertyName("track_id")]
    public string TrackId { get; init; } = string.Empty;

    [JsonPropertyName("side")]
    public string Side { get; init; } = string.Empty;

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("size_before")]
    public int SizeBefore { get; init; }

    [JsonPropertyName("size_after")]
    public int SizeAfter { get; init; }

    [JsonPropertyName("status_before")]
    public string StatusBefore { get; init; } = string.Empty;

    [JsonPropertyName("status_after")]
    public string StatusAfter { get; init; } = string.Empty;

    [JsonPropertyName("distance_from_price_ticks")]
    public int DistanceFromPriceTicks { get; init; }
}

internal sealed class SecondFeaturePayload
{
    [JsonPropertyName("second_started_at")]
    public DateTime SecondStartedAt { get; init; }

    [JsonPropertyName("second_ended_at")]
    public DateTime SecondEndedAt { get; init; }

    [JsonPropertyName("open")]
    public double Open { get; init; }

    [JsonPropertyName("high")]
    public double High { get; init; }

    [JsonPropertyName("low")]
    public double Low { get; init; }

    [JsonPropertyName("close")]
    public double Close { get; init; }

    [JsonPropertyName("trade_count")]
    public int TradeCount { get; init; }

    [JsonPropertyName("volume")]
    public int Volume { get; init; }

    [JsonPropertyName("delta")]
    public int Delta { get; init; }

    [JsonPropertyName("best_bid")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestBid { get; init; }

    [JsonPropertyName("best_ask")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? BestAsk { get; init; }

    [JsonPropertyName("depth_imbalance")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? DepthImbalance { get; init; }
}

internal sealed class BookmarkPayload
{
    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("event_time")]
    public DateTime EventTime { get; init; }

    [JsonPropertyName("price")]
    public double Price { get; init; }

    [JsonPropertyName("notes")]
    public List<string> Notes { get; init; } = new();
}

internal sealed class BurstWindowPayload
{
    [JsonPropertyName("trade_events")]
    public List<TradeEventPayload> TradeEvents { get; init; } = new();

    [JsonPropertyName("depth_events")]
    public List<DepthEventPayload> DepthEvents { get; init; } = new();

    [JsonPropertyName("second_features")]
    public List<SecondFeaturePayload> SecondFeatures { get; init; } = new();

    [JsonPropertyName("price_levels")]
    public List<Dictionary<string, object?>> PriceLevels { get; init; } = new();

    [JsonPropertyName("bookmarks")]
    public List<BookmarkPayload> Bookmarks { get; init; } = new();
}

internal sealed class TriggerBurstPayload
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "1.0.0";

    [JsonPropertyName("message_id")]
    public string MessageId { get; init; } = string.Empty;

    [JsonPropertyName("message_type")]
    public string MessageType { get; init; } = "trigger_burst";

    [JsonPropertyName("emitted_at")]
    public DateTime EmittedAt { get; init; }

    [JsonPropertyName("observed_window_start")]
    public DateTime ObservedWindowStart { get; init; }

    [JsonPropertyName("observed_window_end")]
    public DateTime ObservedWindowEnd { get; init; }

    [JsonPropertyName("source")]
    public SourceEnvelope Source { get; init; } = new();

    [JsonPropertyName("instrument")]
    public InstrumentEnvelope Instrument { get; init; } = new();

    [JsonPropertyName("display_timeframe")]
    public string DisplayTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("time_context")]
    public TimeContextPayload TimeContext { get; init; } = new();

    [JsonPropertyName("trigger")]
    public TriggerInfoPayload Trigger { get; init; } = new();

    [JsonPropertyName("pre_window")]
    public BurstWindowPayload PreWindow { get; init; } = new();

    [JsonPropertyName("event_window")]
    public BurstWindowPayload EventWindow { get; init; } = new();

    [JsonPropertyName("post_window")]
    public BurstWindowPayload PostWindow { get; init; } = new();
}

internal sealed class BackfillGapSegmentPayload
{
    [JsonPropertyName("prev_ended_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? PrevEndedAt { get; init; }

    [JsonPropertyName("next_started_at")]
    public DateTime NextStartedAt { get; init; }

    [JsonPropertyName("missing_bar_count")]
    public int MissingBarCount { get; init; }
}

internal sealed class BackfillRangePayload
{
    [JsonPropertyName("range_start")]
    public DateTime RangeStart { get; init; }

    [JsonPropertyName("range_end")]
    public DateTime RangeEnd { get; init; }
}

internal sealed class AdapterBackfillCommandPayload
{
    [JsonPropertyName("request_id")]
    public string RequestId { get; init; } = string.Empty;

    [JsonPropertyName("cache_key")]
    public string CacheKey { get; init; } = string.Empty;

    [JsonPropertyName("instrument_symbol")]
    public string InstrumentSymbol { get; init; } = string.Empty;

    [JsonPropertyName("display_timeframe")]
    public string DisplayTimeframe { get; init; } = string.Empty;

    [JsonPropertyName("window_start")]
    public DateTime WindowStart { get; init; }

    [JsonPropertyName("window_end")]
    public DateTime WindowEnd { get; init; }

    [JsonPropertyName("chart_instance_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartInstanceId { get; init; }

    [JsonPropertyName("contract_symbol")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ContractSymbol { get; init; }

    [JsonPropertyName("root_symbol")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RootSymbol { get; init; }

    [JsonPropertyName("missing_segments")]
    public List<BackfillGapSegmentPayload> MissingSegments { get; init; } = new();

    [JsonPropertyName("requested_ranges")]
    public List<BackfillRangePayload> RequestedRanges { get; init; } = new();

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = string.Empty;

    [JsonPropertyName("request_history_bars")]
    public bool RequestHistoryBars { get; init; }

    [JsonPropertyName("request_history_footprint")]
    public bool RequestHistoryFootprint { get; init; }

    [JsonPropertyName("dispatch_count")]
    public int DispatchCount { get; init; }

    [JsonPropertyName("requested_at")]
    public DateTime RequestedAt { get; init; }

    [JsonPropertyName("dispatched_at")]
    public DateTime DispatchedAt { get; init; }
}

internal sealed class AdapterBackfillDispatchResponsePayload
{
    [JsonPropertyName("instrument_symbol")]
    public string InstrumentSymbol { get; init; } = string.Empty;

    [JsonPropertyName("chart_instance_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartInstanceId { get; init; }

    [JsonPropertyName("polled_at")]
    public DateTime PolledAt { get; init; }

    [JsonPropertyName("request")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public AdapterBackfillCommandPayload? Request { get; init; }
}

internal sealed class AdapterBackfillAcknowledgeRequestPayload
{
    [JsonPropertyName("request_id")]
    public string RequestId { get; init; } = string.Empty;

    [JsonPropertyName("cache_key")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? CacheKey { get; init; }

    [JsonPropertyName("chart_instance_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartInstanceId { get; init; }

    [JsonPropertyName("instrument_symbol")]
    public string InstrumentSymbol { get; init; } = string.Empty;

    [JsonPropertyName("acknowledged_at")]
    public DateTime AcknowledgedAt { get; init; }

    [JsonPropertyName("acknowledged_history_bars")]
    public bool AcknowledgedHistoryBars { get; init; }

    [JsonPropertyName("acknowledged_history_footprint")]
    public bool AcknowledgedHistoryFootprint { get; init; }

    [JsonPropertyName("latest_loaded_bar_started_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? LatestLoadedBarStartedAt { get; init; }

    [JsonPropertyName("latest_loaded_bar_started_at_utc")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTime? LatestLoadedBarStartedAtUtc { get; init; }

    [JsonPropertyName("instrument_timezone_value")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InstrumentTimezoneValue { get; init; }

    [JsonPropertyName("instrument_timezone_source")]
    public string InstrumentTimezoneSource { get; init; } = "collector";

    [JsonPropertyName("chart_display_timezone_mode")]
    public string ChartDisplayTimezoneMode { get; init; } = "unknown";

    [JsonPropertyName("chart_display_timezone_source")]
    public string ChartDisplayTimezoneSource { get; init; } = "collector";

    [JsonPropertyName("chart_display_timezone_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChartDisplayTimezoneName { get; init; }

    [JsonPropertyName("chart_display_utc_offset_minutes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ChartDisplayUtcOffsetMinutes { get; init; }

    [JsonPropertyName("collector_local_timezone_name")]
    public string CollectorLocalTimezoneName { get; init; } = string.Empty;

    [JsonPropertyName("collector_local_utc_offset_minutes")]
    public int CollectorLocalUtcOffsetMinutes { get; init; }

    [JsonPropertyName("timestamp_basis")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimestampBasis { get; init; }

    [JsonPropertyName("timezone_capture_confidence")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimezoneCaptureConfidence { get; init; }

    [JsonPropertyName("note")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Note { get; init; }
}
