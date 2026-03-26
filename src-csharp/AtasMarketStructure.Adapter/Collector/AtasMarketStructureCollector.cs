using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Diagnostics;
using ATAS.DataFeedsCore;
using ATAS.Indicators;
using AtasMarketStructure.Adapter.Contracts;

namespace AtasMarketStructure.Adapter.Collector;

internal static class TriggerKinds
{
    public const string SignificantLiquidityNearTouch = "significant_liquidity_near_touch";
    public const string LiquidityPull = "liquidity_pull";
    public const string LiquidityFill = "liquidity_fill";
    public const string HarvestCompleted = "harvest_completed";
    public const string PostHarvestReversal = "post_harvest_reversal";
    public const string PostHarvestPullback = "post_harvest_pullback";
}

[DisplayName("ZZ ATAS Collector Full Internal")]
[Description("Streams compact continuous state, mirror history, and backfill control to the local ATAS market structure service.")]
[Category("Order Flow")]
public abstract class AtasMarketStructureCollectorFull : Indicator
{
    private const string CollectorVersion = "0.5.1-alpha";
    private const int DefaultHistoryBarsChunkBars = 512;
    private const int DirectBackfillHistoryBarsChunkBars = 180;
    private const int DefaultHistoryFootprintChunkBars = 50;
    private readonly object _sync = new();
    private readonly ValueDataSeries _collectorHeartbeat = new("CollectorShellHeartbeat") { VisualType = VisualMode.Hide };
    private readonly TimedRingBuffer<TradeEventPayload> _tradeBuffer = new(TimeSpan.FromMinutes(5), item => item.EventTime);
    private readonly TimedRingBuffer<DepthEventPayload> _depthBuffer = new(TimeSpan.FromMinutes(5), item => item.EventTime);
    private readonly TimedRingBuffer<SecondFeaturePayload> _secondBuffer = new(TimeSpan.FromMinutes(5), item => item.SecondStartedAt);
    private readonly Dictionary<string, SignificantLiquidityTrackState> _liquidityTracks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, DateTime> _lastTriggerByKey = new(StringComparer.Ordinal);

    private IAdapterTransport? _transport;
    private TradeAccumulatorState _tradeAccumulator = new();
    private SecondAccumulatorState? _currentSecond;
    private DriveState? _driveState;
    private HarvestState? _harvestState;
    private GapReferencePayload? _gapReference;

    private decimal? _bestBid;
    private decimal? _bestAsk;
    private decimal? _lastPrice;
    private decimal? _sessionOpenPrice;
    private decimal? _ema20;
    private decimal _openingRangeHigh = decimal.MinValue;
    private decimal _openingRangeLow = decimal.MaxValue;
    private DateTime? _sessionStartUtc;
    private int _lastEmaBar = -1;
    private int _localSequence;
    private ChartIdentity? _chartIdentityCache;
    private DateTime _chartIdentityResolvedAtUtc;
    private ResolvedTimeContext? _timeContextCache;
    private DateTime _timeContextResolvedAtUtc;
    private DateTime? _lastObservedBarStartedAtUtc;
    private string _lastLoggedContextSignature = string.Empty;

    private CancellationTokenSource? _backfillCts;
    private Task? _backfillPollerTask;
    private readonly HashSet<string> _inProgressBackfills = new(StringComparer.Ordinal);
    private int _latestObservedBarCount;
    private int _latestObservedBarIndex = -1;
    private int _lastHistoryBarsExportedBarIndex = -1;
    private int _lastHistoryBarsExportedCount;
    private DateTime? _lastHistoryBarsExportedFirstStartedAtUtc;
    private DateTime? _lastHistoryBarsExportedLatestStartedAtUtc;
    private DateTime _lastHistoryBarsMutationObservedUtc = DateTime.MinValue;
    private DateTime _lastHistoryBarsFullSnapshotExportedAtUtc = DateTime.MinValue;
    private bool _historyBarsInitialSnapshotPending = true;
    private DateTime _lastHistoryInventoryPublishedAtUtc = DateTime.MinValue;
    private string _lastHistoryInventorySignature = string.Empty;
    private int _historyInventorySendInFlight;

    protected AtasMarketStructureCollectorFull()
        : base(true)
    {
        DataSeries.Add(_collectorHeartbeat);
    }

    [Display(Name = "Service Base URL", GroupName = "1. Adapter", Order = 10)]
    public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8080";

    [Display(Name = "Continuous Endpoint", GroupName = "1. Adapter", Order = 20)]
    public string ContinuousEndpoint { get; set; } = "/api/v1/adapter/continuous-state";

    [Display(Name = "Trigger Endpoint", GroupName = "1. Adapter", Order = 30)]
    public string TriggerEndpoint { get; set; } = "/api/v1/adapter/trigger-burst";

    [Display(Name = "Symbol Override", GroupName = "2. Instrument", Order = 10)]
    public string SymbolOverride { get; set; } = string.Empty;

    [Display(Name = "Venue", GroupName = "2. Instrument", Order = 20)]
    public string Venue { get; set; } = "CME";

    [Display(Name = "Currency", GroupName = "2. Instrument", Order = 30)]
    public string Currency { get; set; } = "USD";

    [Display(Name = "Tick Size Override", GroupName = "2. Instrument", Order = 40)]
    public decimal TickSizeOverride { get; set; }

    [Display(Name = "Continuous Cadence Ms", GroupName = "3. Performance", Order = 10)]
    public int ContinuousCadenceMilliseconds { get; set; } = 1000;

    [Display(Name = "Queue Limit", GroupName = "3. Performance", Order = 20)]
    public int QueueLimit { get; set; } = 256;

    [Display(Name = "Enable Backfill Poller", GroupName = "3. Performance", Order = 25)]
    public bool EnableBackfillPoller { get; set; } = true;

    [Display(Name = "Backfill Poll Interval Seconds", GroupName = "3. Performance", Order = 26)]
    [Range(1, 30)]
    public int BackfillPollIntervalSeconds { get; set; } = 5;

    [Display(Name = "Force UTC Timestamps", GroupName = "3. Performance", Order = 27)]
    public bool ForceUtcTimestamps { get; set; } = true;

    [Display(Name = "Burst Lookback Seconds", GroupName = "4. Trigger Burst", Order = 10)]
    public int BurstLookbackSeconds { get; set; } = 45;

    [Display(Name = "Significant Liquidity Min Size", GroupName = "5. Liquidity", Order = 10)]
    public int SignificantLiquidityMinSize { get; set; } = 80;

    [Display(Name = "Significant Liquidity Max Distance Ticks", GroupName = "5. Liquidity", Order = 20)]
    public int SignificantLiquidityMaxDistanceTicks { get; set; } = 64;

    [Display(Name = "Near Touch Distance Ticks", GroupName = "5. Liquidity", Order = 30)]
    public int NearTouchDistanceTicks { get; set; } = 2;

    [Display(Name = "Strong Replenishment Count", GroupName = "5. Liquidity", Order = 40)]
    public int StrongReplenishmentCount { get; set; } = 2;

    [Display(Name = "Drive Min Net Delta", GroupName = "6. Drive", Order = 10)]
    public int DriveMinNetDelta { get; set; } = 20;

    [Display(Name = "Drive Min Travel Ticks", GroupName = "6. Drive", Order = 20)]
    public int DriveMinTravelTicks { get; set; } = 6;

    [Display(Name = "Drive Merge Gap Seconds", GroupName = "6. Drive", Order = 30)]
    public int DriveMergeGapSeconds { get; set; } = 6;

    [Display(Name = "Opening Range Minutes", GroupName = "7. Structure", Order = 10)]
    public int OpeningRangeMinutes { get; set; } = 30;

    [Display(Name = "Measured Reference Ticks", GroupName = "8. Measured Move", Order = 10)]
    public int MeasuredReferenceTicks { get; set; } = 8;

    [Display(Name = "Prior RTH Close", GroupName = "9. Session References", Order = 10)]
    public decimal PriorRthClose { get; set; }

    [Display(Name = "Prior RTH High", GroupName = "9. Session References", Order = 20)]
    public decimal PriorRthHigh { get; set; }

    [Display(Name = "Prior RTH Low", GroupName = "9. Session References", Order = 30)]
    public decimal PriorRthLow { get; set; }

    [Display(Name = "Prior Value Area Low", GroupName = "9. Session References", Order = 40)]
    public decimal PriorValueAreaLow { get; set; }

    [Display(Name = "Prior Value Area High", GroupName = "9. Session References", Order = 50)]
    public decimal PriorValueAreaHigh { get; set; }

    [Display(Name = "Prior Point Of Control", GroupName = "9. Session References", Order = 60)]
    public decimal PriorPointOfControl { get; set; }

    [Display(Name = "Overnight High", GroupName = "9. Session References", Order = 70)]
    public decimal OvernightHigh { get; set; }

    [Display(Name = "Overnight Low", GroupName = "9. Session References", Order = 80)]
    public decimal OvernightLow { get; set; }

    [Display(Name = "Session Code Override", GroupName = "9. Session References", Order = 90)]
    public string SessionCodeOverride { get; set; } = string.Empty;

    [Display(Name = "Enable Market By Orders", GroupName = "10. DOM / MBO", Order = 10)]
    public bool EnableMarketByOrders { get; set; }

    protected override void OnInitialize()
    {
        lock (_sync)
        {
            _transport?.Dispose();
            _transport = new BufferedHttpAdapterTransport(
                new Uri(ServiceBaseUrl, UriKind.Absolute),
                ContinuousEndpoint,
                "/api/v1/adapter/history-bars",
                "/api/v1/adapter/history-footprint",
                "/api/v1/adapter/history-inventory",
                TriggerEndpoint,
                QueueLimit,
                LogInfoLocal,
                LogWarnLocal);
            _tradeAccumulator = new TradeAccumulatorState();
            _currentSecond = null;
            _driveState = null;
            _harvestState = null;
            _gapReference = null;
            _liquidityTracks.Clear();
            _lastTriggerByKey.Clear();
            _localSequence = 0;
            _chartIdentityCache = null;
            _chartIdentityResolvedAtUtc = DateTime.MinValue;
            _timeContextCache = null;
            _timeContextResolvedAtUtc = DateTime.MinValue;
            _lastObservedBarStartedAtUtc = null;
            _lastLoggedContextSignature = string.Empty;
            _latestObservedBarCount = 0;
            _latestObservedBarIndex = -1;
            _lastHistoryBarsExportedBarIndex = -1;
            _lastHistoryBarsExportedCount = 0;
            _lastHistoryBarsExportedFirstStartedAtUtc = null;
            _lastHistoryBarsExportedLatestStartedAtUtc = null;
            _lastHistoryBarsMutationObservedUtc = DateTime.MinValue;
            _lastHistoryBarsFullSnapshotExportedAtUtc = DateTime.MinValue;
            _historyBarsInitialSnapshotPending = true;
            _lastHistoryInventoryPublishedAtUtc = DateTime.MinValue;
            _lastHistoryInventorySignature = string.Empty;
            _historyInventorySendInFlight = 0;
        }

        SubscribeToTimer(TimeSpan.FromMilliseconds(Math.Max(250, ContinuousCadenceMilliseconds)), OnTimerTick);
        if (EnableMarketByOrders)
        {
            ObserveBackgroundTask(
                SubscribeMarketByOrderData(),
                "SubscribeMarketByOrderData",
                onFault: () => EnableMarketByOrders = false);
        }

        if (EnableBackfillPoller)
        {
            StartBackfillPoller();
        }
    }

    protected override void OnDispose()
    {
        StopBackfillPoller();

        lock (_sync)
        {
            FinalizeCurrentSecond(DateTime.UtcNow);
            _transport?.Dispose();
            _transport = null;
        }
    }

    protected override void OnCalculate(int bar, decimal value)
    {
        var candle = GetCandle(bar);
        if (candle is null)
        {
            return;
        }

        lock (_sync)
        {
            _collectorHeartbeat[bar] = candle.Close;
            var timeUtc = ToUtc(candle.Time);
            var observedBarCount = Math.Max(CurrentBar, bar + 1);
            if (observedBarCount > _latestObservedBarCount)
            {
                _latestObservedBarCount = observedBarCount;
                _lastHistoryBarsMutationObservedUtc = DateTime.UtcNow;
            }

            if (bar > _latestObservedBarIndex)
            {
                _latestObservedBarIndex = bar;
                _lastHistoryBarsMutationObservedUtc = DateTime.UtcNow;
            }
            _lastObservedBarStartedAtUtc = timeUtc;
            _sessionStartUtc ??= timeUtc;
            _sessionOpenPrice ??= candle.Open;
            if (timeUtc <= _sessionStartUtc.Value.AddMinutes(Math.Max(1, OpeningRangeMinutes)))
            {
                _openingRangeHigh = _openingRangeHigh == decimal.MinValue ? candle.High : Math.Max(_openingRangeHigh, candle.High);
                _openingRangeLow = _openingRangeLow == decimal.MaxValue ? candle.Low : Math.Min(_openingRangeLow, candle.Low);
            }

            _lastPrice ??= candle.Close;
            UpdateEma(bar, candle.Close);
            UpdateGapReference(timeUtc, candle.Close);
        }
    }

    protected override void OnBestBidAskChanged(MarketDataArg marketData)
    {
        lock (_sync)
        {
            var price = marketData.Price;
            if (marketData.IsBid)
            {
                _bestBid = price;
            }
            else if (marketData.IsAsk)
            {
                _bestAsk = price;
            }

            EnsureSecondAccumulator(ToUtc(marketData.Time), price);
            _currentSecond?.ObserveBestBid(_bestBid);
            _currentSecond?.ObserveBestAsk(_bestAsk);
        }
    }

    protected override void MarketDepthChanged(MarketDataArg marketData)
    {
        lock (_sync)
        {
            ProcessDisplayedLiquidity(ToUtc(marketData.Time), marketData.Price, DecimalToInt(marketData.Volume), AtasReflection.ReadSide(marketData), null);
        }
    }

    protected override void OnCumulativeTrade(CumulativeTrade trade)
    {
        lock (_sync)
        {
            ProcessCumulativeTrade(trade, countVolume: true);
        }
    }

    protected override void OnUpdateCumulativeTrade(CumulativeTrade trade)
    {
        lock (_sync)
        {
            ProcessCumulativeTrade(trade, countVolume: false);
        }
    }

    protected override void OnMarketByOrdersChanged(IEnumerable<MarketByOrder> marketByOrders)
    {
        if (!EnableMarketByOrders)
        {
            return;
        }

        lock (_sync)
        {
            foreach (var marketByOrder in marketByOrders)
            {
                ProcessDisplayedLiquidity(
                    DateTime.UtcNow,
                    AtasReflection.ReadDecimal(marketByOrder, "Price"),
                    DecimalToInt(AtasReflection.ReadDecimal(marketByOrder, "Volume", "Size") ?? 0m),
                    AtasReflection.ReadSide(marketByOrder),
                    AtasReflection.ReadString(marketByOrder, "ExchangeOrderId", "OrderId"));
            }
        }
    }

    private void OnTimerTick()
    {
        lock (_sync)
        {
            var nowUtc = DateTime.UtcNow;
            FinalizeCurrentSecond(nowUtc);
            MaybeEmitContinuousState(nowUtc);
            MaybeExportLoadedHistoryBars(nowUtc);
            MaybePublishHistoryInventory(nowUtc);
        }
    }

    private void ProcessCumulativeTrade(CumulativeTrade trade, bool countVolume)
    {
        var timeUtc = ToUtc(trade.Time);
        var price = trade.Lastprice != 0m ? trade.Lastprice : trade.FirstPrice;
        var size = DecimalToInt(trade.Volume);
        var side = AtasReflection.ReadSide(trade);

        _lastPrice = price;
        _bestBid = trade.NewBid?.Price ?? trade.PreviousBid?.Price ?? _bestBid;
        _bestAsk = trade.NewAsk?.Price ?? trade.PreviousAsk?.Price ?? _bestAsk;

        EnsureSecondAccumulator(timeUtc, price);
        _currentSecond?.ObserveBestBid(_bestBid);
        _currentSecond?.ObserveBestAsk(_bestAsk);

        if (!countVolume || size <= 0)
        {
            return;
        }

        _tradeAccumulator.Observe(side, size);
        _currentSecond?.ObserveTrade(side, size, price);
        _tradeBuffer.Add(new TradeEventPayload
        {
            EventTime = timeUtc,
            LocalSequence = ++_localSequence,
            Price = (double)price,
            Size = size,
            AggressorSide = side.ToPayloadString(),
            BestBidBefore = DecimalToDouble(trade.PreviousBid?.Price),
            BestAskBefore = DecimalToDouble(trade.PreviousAsk?.Price),
            BestBidAfter = DecimalToDouble(trade.NewBid?.Price),
            BestAskAfter = DecimalToDouble(trade.NewAsk?.Price),
        });

        UpdateDriveState(timeUtc, price, side, size);
        UpdatePostHarvestState(timeUtc, price, side, size);
    }

    private void ProcessDisplayedLiquidity(DateTime eventTimeUtc, decimal? price, int size, CollectorSide side, string? externalTrackId)
    {
        if (price is null || side == CollectorSide.Neutral)
        {
            return;
        }

        var currentPrice = _lastPrice ?? price.Value;
        var distanceTicks = PriceMath.ToTicks(Math.Abs(currentPrice - price.Value), EffectiveTickSize);
        var key = externalTrackId ?? $"{side.ToPayloadString()}:{price.Value:F2}";

        if (!_liquidityTracks.TryGetValue(key, out var track))
        {
            if (size < SignificantLiquidityMinSize || distanceTicks > SignificantLiquidityMaxDistanceTicks)
            {
                return;
            }

            track = new SignificantLiquidityTrackState
            {
                TrackId = key,
                Side = side,
                Price = price.Value,
                FirstObservedAtUtc = eventTimeUtc,
                LastObservedAtUtc = eventTimeUtc,
                CurrentSize = size,
                MaxSeenSize = size,
                Status = "active",
            };
            _liquidityTracks[key] = track;
        }

        var sizeBefore = track.CurrentSize;
        var statusBefore = track.Status;
        var nearTouch = distanceTicks <= NearTouchDistanceTicks;

        track.LastObservedAtUtc = eventTimeUtc;
        if (nearTouch && !track.WasNearPrice)
        {
            track.TouchCount += 1;
        }

        if (size > sizeBefore && nearTouch)
        {
            track.ReplenishmentCount += 1;
        }
        else if (size < sizeBefore)
        {
            if (nearTouch)
            {
                track.ExecutedVolumeEstimate += Math.Max(0, sizeBefore - size);
                track.Status = size == 0 ? "filled" : "partially_filled";
            }
            else
            {
                track.PullCount += 1;
                track.Status = size == 0 ? "pulled" : "moved";
            }
        }
        else
        {
            track.Status = "active";
        }

        track.WasNearPrice = nearTouch;
        track.CurrentSize = Math.Max(0, size);
        track.MaxSeenSize = Math.Max(track.MaxSeenSize, size);
        track.PriceReactionTicks = ComputeReactionTicks(track.Side, track.Price, currentPrice, EffectiveTickSize);
        track.HeatScore = ComputeHeatScore(track, distanceTicks);

        _depthBuffer.Add(new DepthEventPayload
        {
            EventTime = eventTimeUtc,
            TrackId = track.TrackId,
            Side = track.Side.ToPayloadString(),
            Price = (double)track.Price,
            SizeBefore = sizeBefore,
            SizeAfter = track.CurrentSize,
            StatusBefore = statusBefore,
            StatusAfter = track.Status,
            DistanceFromPriceTicks = distanceTicks,
        });

        if (track.ReplenishmentCount >= StrongReplenishmentCount && nearTouch)
        {
            ScheduleTriggerBurst(TriggerKinds.SignificantLiquidityNearTouch, eventTimeUtc, price.Value, new[] { "same_price_replenishment", side == CollectorSide.Buy ? "buyers_hitting_same_level" : "sellers_hitting_same_level" }, $"repl:{track.TrackId}");
        }

        if (statusBefore != track.Status)
        {
            if (track.Status == "pulled")
            {
                ScheduleTriggerBurst(TriggerKinds.LiquidityPull, eventTimeUtc, price.Value, new[] { "visible_liquidity_pulled", "watch_release" }, $"pull:{track.TrackId}");
            }
            else if (track.Status is "filled" or "partially_filled")
            {
                ScheduleTriggerBurst(TriggerKinds.LiquidityFill, eventTimeUtc, price.Value, new[] { "visible_liquidity_consumed", "watch_post_harvest" }, $"fill:{track.TrackId}");
                TryStartHarvestState(track, eventTimeUtc);
            }
        }
    }

    private void UpdateDriveState(DateTime eventTimeUtc, decimal price, CollectorSide side, int size)
    {
        if (side == CollectorSide.Neutral)
        {
            return;
        }

        if (_driveState is null)
        {
            _driveState = DriveState.Start(eventTimeUtc, price, side, size);
        }
        else if (_driveState.Side == side && (eventTimeUtc - _driveState.LastObservedAtUtc).TotalSeconds <= DriveMergeGapSeconds)
        {
            _driveState.Observe(eventTimeUtc, price, size);
        }
        else
        {
            _driveState = DriveState.Start(eventTimeUtc, price, side, size);
        }
    }

    private void TryStartHarvestState(SignificantLiquidityTrackState track, DateTime eventTimeUtc)
    {
        if (_driveState is null)
        {
            return;
        }

        if ((_driveState.Side == CollectorSide.Buy && track.Side != CollectorSide.Sell)
            || (_driveState.Side == CollectorSide.Sell && track.Side != CollectorSide.Buy))
        {
            return;
        }

        _harvestState = new HarvestState
        {
            ResponseId = $"harvest-{_driveState.DriveId}",
            HarvestSubjectId = _driveState.DriveId,
            HarvestSubjectKind = "initiative_drive",
            HarvestSide = _driveState.Side,
            HarvestCompletedAtUtc = eventTimeUtc,
            HarvestedPriceLow = track.Price - EffectiveTickSize,
            HarvestedPriceHigh = track.Price + EffectiveTickSize,
            HighestAfterCompletion = _lastPrice ?? track.Price,
            LowestAfterCompletion = _lastPrice ?? track.Price,
        };

        ScheduleTriggerBurst(TriggerKinds.HarvestCompleted, eventTimeUtc, track.Price, new[] { "liquidity_harvest_completed", "monitor_post_harvest_response" }, _harvestState.ResponseId);
    }

    private void UpdatePostHarvestState(DateTime eventTimeUtc, decimal price, CollectorSide tradeSide, int size)
    {
        if (_harvestState is null)
        {
            return;
        }

        _harvestState.PostHarvestDelta += tradeSide == CollectorSide.Buy ? size : tradeSide == CollectorSide.Sell ? -size : 0;
        _harvestState.HighestAfterCompletion = Math.Max(_harvestState.HighestAfterCompletion, price);
        _harvestState.LowestAfterCompletion = Math.Min(_harvestState.LowestAfterCompletion, price);

        var pullbackTicks = ComputePullbackTicks(_harvestState, price);
        var reversalTicks = ComputeReversalTicks(_harvestState, price);
        if (_harvestState.FirstPullbackAtUtc is null && pullbackTicks > 0)
        {
            _harvestState.FirstPullbackAtUtc = eventTimeUtc;
        }

        if (_harvestState.FirstReversalAtUtc is null && reversalTicks >= 6)
        {
            _harvestState.FirstReversalAtUtc = eventTimeUtc;
            ScheduleTriggerBurst(TriggerKinds.PostHarvestReversal, eventTimeUtc, price, new[] { "post_harvest_reversal", "watch_bigger_rotation" }, $"post-rev:{_harvestState.ResponseId}");
        }
        else if (pullbackTicks >= 2)
        {
            ScheduleTriggerBurst(TriggerKinds.PostHarvestPullback, eventTimeUtc, price, new[] { "post_harvest_pullback", "watch_retest_or_balance" }, $"post-pb:{_harvestState.ResponseId}");
        }
    }

    private void UpdateGapReference(DateTime observedAtUtc, decimal currentPrice)
    {
        if (_sessionOpenPrice is null || PriorRthClose <= 0m)
        {
            return;
        }

        var gapLow = Math.Min(PriorRthClose, _sessionOpenPrice.Value);
        var gapHigh = Math.Max(PriorRthClose, _sessionOpenPrice.Value);
        var gapSizeTicks = PriceMath.ToTicks(gapHigh - gapLow, EffectiveTickSize);
        if (gapSizeTicks <= 0)
        {
            return;
        }

        var insideGap = currentPrice >= gapLow && currentPrice <= gapHigh;
        var fillTicks = insideGap ? PriceMath.ToTicks(Math.Abs(_sessionOpenPrice.Value - currentPrice), EffectiveTickSize) : currentPrice > gapHigh ? gapSizeTicks : 0;
        var fillRatio = Math.Round((double)fillTicks / gapSizeTicks, 4);
        var chartIdentity = ResolveChartIdentity();
        var timeContext = ResolveTimeContext();

        _gapReference = new GapReferencePayload
        {
            GapId = $"gap-{DetermineTradingDate(observedAtUtc, chartIdentity, timeContext)}",
            Direction = _sessionOpenPrice.Value >= PriorRthClose ? "up" : "down",
            OpenedAt = _sessionStartUtc ?? observedAtUtc,
            GapLow = (double)gapLow,
            GapHigh = (double)gapHigh,
            GapSizeTicks = gapSizeTicks,
            FirstTouchAt = insideGap ? observedAtUtc : null,
            MaxFillTicks = Math.Max(fillTicks, _gapReference?.MaxFillTicks ?? 0),
            FillRatio = Math.Max(fillRatio, _gapReference?.FillRatio ?? 0.0),
            FillAttemptCount = Math.Max(_gapReference?.FillAttemptCount ?? 0, insideGap ? 1 : 0),
            AcceptedInsideGap = insideGap && fillRatio > 0.2,
            RejectedFromGap = !insideGap,
            FullyFilledAt = fillRatio >= 1.0 ? observedAtUtc : null,
        };
    }

    private void MaybeEmitContinuousState(DateTime nowUtc)
    {
        if (_transport is null)
        {
            return;
        }

        if ((nowUtc - _tradeAccumulator.WindowStartedAtUtc).TotalMilliseconds < Math.Max(250, ContinuousCadenceMilliseconds))
        {
            return;
        }

        var recentSeconds = _secondBuffer.Snapshot(nowUtc.AddSeconds(-60), nowUtc);
        var lastPrice = _lastPrice ?? _sessionOpenPrice ?? 0m;
        var chartIdentity = ResolveChartIdentity();
        var timeContext = ResolveTimeContext();
        var barTimestampUtc = _lastObservedBarStartedAtUtc ?? nowUtc;
        var sessionContext = BuildSessionContext(chartIdentity, timeContext, nowUtc);
        LogResolvedContext(chartIdentity, timeContext);

        var payload = new ContinuousStatePayload
        {
            MessageId = CollectorMetadataResolver.BuildMessageId(
                "continuous_state",
                chartIdentity,
                barTimestampUtc,
                ComputeContinuousSequence(barTimestampUtc, nowUtc)),
            EmittedAt = nowUtc,
            ObservedWindowStart = _tradeAccumulator.WindowStartedAtUtc,
            ObservedWindowEnd = nowUtc,
            Source = BuildSourceEnvelope(chartIdentity, timeContext),
            Instrument = BuildInstrumentEnvelope(chartIdentity),
            DisplayTimeframe = chartIdentity.DisplayTimeframe,
            TimeContext = timeContext.ToPayload(),
            SessionContext = sessionContext,
            PriceState = new PriceStatePayload
            {
                LastPrice = (double)lastPrice,
                BestBid = DecimalToDouble(_bestBid),
                BestAsk = DecimalToDouble(_bestAsk),
                LocalRangeLow = recentSeconds.Count == 0 ? (double)lastPrice : recentSeconds.Min(item => item.Low),
                LocalRangeHigh = recentSeconds.Count == 0 ? (double)lastPrice : recentSeconds.Max(item => item.High),
                OpeningRangeLow = _openingRangeLow == decimal.MaxValue ? null : (double)_openingRangeLow,
                OpeningRangeHigh = _openingRangeHigh == decimal.MinValue ? null : (double)_openingRangeHigh,
                OpeningRangeSizeTicks = _openingRangeLow == decimal.MaxValue || _openingRangeHigh == decimal.MinValue ? null : PriceMath.ToTicks(_openingRangeHigh - _openingRangeLow, EffectiveTickSize),
            },
            TradeSummary = _tradeAccumulator.ToPayload(),
            SignificantLiquidity = _liquidityTracks.Values.OrderByDescending(item => item.HeatScore).Take(8).Select(item => item.ToPayload(lastPrice, EffectiveTickSize)).ToList(),
            GapReference = _gapReference,
            ActiveInitiativeDrive = BuildActiveDrivePayload(),
            ActiveManipulationLeg = BuildManipulationLegPayload(),
            ActiveMeasuredMove = BuildMeasuredMovePayload(),
            ActivePostHarvestResponse = BuildPostHarvestPayload(),
            ActiveZoneInteraction = BuildZoneInteractionPayload(),
            EmaContext = BuildEmaContextPayload(lastPrice),
            ReferenceLevels = BuildReferenceLevels(),
        };
        if (!_transport.TryEnqueueContinuousState(payload))
        {
            LogWarnLocal($"MaybeEmitContinuousState: realtime queue rejected {payload.MessageId}.");
        }

        _tradeAccumulator.Reset(nowUtc);
    }

    private void MaybeExportLoadedHistoryBars(DateTime nowUtc)
    {
        SyncLoadedHistoryIndex(nowUtc);
        if (_transport is null || _latestObservedBarIndex < 0)
        {
            return;
        }

        if (!TryGetLoadedHistoryWindow(
                nowUtc,
                out var loadedLatestBarIndex,
                out var loadedBarCount,
                out var loadedFirstStartedAtUtc,
                out var loadedLatestStartedAtUtc))
        {
            return;
        }

        var stabilizationWindow = TimeSpan.FromMilliseconds(Math.Max(500, ContinuousCadenceMilliseconds));
        if (_historyBarsInitialSnapshotPending)
        {
            if (_lastHistoryBarsMutationObservedUtc != DateTime.MinValue
                && nowUtc - _lastHistoryBarsMutationObservedUtc < stabilizationWindow)
            {
                return;
            }

            var snapshotBars = ExportLoadedHistoryBarsSnapshot(0, loadedLatestBarIndex);
            if (snapshotBars.Count == 0)
            {
                return;
            }

            var chartIdentity = ResolveChartIdentity();
            var timeContext = ResolveTimeContext();
            if (TrySendHistoryBarsChunks(snapshotBars, nowUtc, chartIdentity, timeContext))
            {
                _historyBarsInitialSnapshotPending = false;
                RecordHistoryBarsExport(snapshotBars, loadedBarCount, loadedLatestBarIndex, fullSnapshot: true, exportedAtUtc: nowUtc);
                LogInfoLocal(
                    $"MaybeExportLoadedHistoryBars: exported initial snapshot bars={snapshotBars.Count} loaded_count={loadedBarCount} first_started_at_utc={snapshotBars[0].StartedAt:O} latest_started_at_utc={snapshotBars[^1].StartedAt:O}.");
            }

            return;
        }

        if (ShouldReexportExpandedHistory(
                nowUtc,
                loadedBarCount,
                loadedFirstStartedAtUtc,
                loadedLatestStartedAtUtc,
                stabilizationWindow))
        {
            var expandedSnapshotBars = ExportLoadedHistoryBarsSnapshot(0, loadedLatestBarIndex);
            if (expandedSnapshotBars.Count == 0)
            {
                return;
            }

            LogInfoLocal(
                $"MaybeExportLoadedHistoryBars: detected earlier loaded history expansion loaded_count={loadedBarCount} exported_count={_lastHistoryBarsExportedCount} loaded_first_started_at_utc={loadedFirstStartedAtUtc:O} exported_first_started_at_utc={_lastHistoryBarsExportedFirstStartedAtUtc:O}; re-exporting full snapshot.");
            var expandedChartIdentity = ResolveChartIdentity();
            var expandedTimeContext = ResolveTimeContext();
            if (TrySendHistoryBarsChunks(expandedSnapshotBars, nowUtc, expandedChartIdentity, expandedTimeContext))
            {
                RecordHistoryBarsExport(expandedSnapshotBars, loadedBarCount, loadedLatestBarIndex, fullSnapshot: true, exportedAtUtc: nowUtc);
                LogInfoLocal(
                    $"MaybeExportLoadedHistoryBars: re-exported expanded snapshot bars={expandedSnapshotBars.Count} loaded_count={loadedBarCount} first_started_at_utc={expandedSnapshotBars[0].StartedAt:O} latest_started_at_utc={expandedSnapshotBars[^1].StartedAt:O}.");
            }

            return;
        }

        if (loadedLatestBarIndex <= _lastHistoryBarsExportedBarIndex)
        {
            return;
        }

        var incrementalStartIndex = Math.Max(0, _lastHistoryBarsExportedBarIndex + 1);
        var incrementalBars = ExportLoadedHistoryBarsSnapshot(incrementalStartIndex, loadedLatestBarIndex);
        if (incrementalBars.Count == 0)
        {
            return;
        }

        var incrementalChartIdentity = ResolveChartIdentity();
        var incrementalTimeContext = ResolveTimeContext();
        if (TrySendHistoryBarsChunks(incrementalBars, nowUtc, incrementalChartIdentity, incrementalTimeContext))
        {
            RecordHistoryBarsExport(incrementalBars, loadedBarCount, loadedLatestBarIndex, fullSnapshot: false, exportedAtUtc: nowUtc);
            LogInfoLocal(
                $"MaybeExportLoadedHistoryBars: exported incremental bars={incrementalBars.Count} loaded_count={loadedBarCount} latest_started_at_utc={incrementalBars[^1].StartedAt:O}.");
        }
    }

    private void MaybePublishHistoryInventory(DateTime nowUtc)
    {
        if (_transport is null || _latestObservedBarIndex < 0)
        {
            return;
        }

        if (!TryGetLoadedHistoryWindow(
                nowUtc,
                out var loadedLatestBarIndex,
                out var loadedBarCount,
                out var loadedFirstStartedAtUtc,
                out var loadedLatestStartedAtUtc))
        {
            return;
        }

        var currentBarCount = Math.Max(loadedBarCount, Math.Max(_latestObservedBarCount, CurrentBar));
        var signature = string.Create(
            System.Globalization.CultureInfo.InvariantCulture,
            $"{loadedBarCount}:{currentBarCount}:{loadedLatestBarIndex}:{loadedFirstStartedAtUtc:O}:{loadedLatestStartedAtUtc:O}");
        var heartbeatDue = _lastHistoryInventoryPublishedAtUtc == DateTime.MinValue
            || nowUtc - _lastHistoryInventoryPublishedAtUtc >= TimeSpan.FromSeconds(15);
        if (!heartbeatDue && string.Equals(signature, _lastHistoryInventorySignature, StringComparison.Ordinal))
        {
            return;
        }

        if (Interlocked.CompareExchange(ref _historyInventorySendInFlight, 1, 0) != 0)
        {
            return;
        }

        var chartIdentity = ResolveChartIdentity();
        var timeContext = ResolveTimeContext();
        LogResolvedContext(chartIdentity, timeContext);

        var payload = BuildHistoryInventoryPayload(
            emittedAtUtc: nowUtc,
            chartIdentity: chartIdentity,
            timeContext: timeContext,
            loadedBarCount: loadedBarCount,
            currentBarCount: currentBarCount,
            latestLoadedBarIndex: loadedLatestBarIndex,
            firstLoadedBarStartedAtUtc: loadedFirstStartedAtUtc,
            latestLoadedBarStartedAtUtc: loadedLatestStartedAtUtc);

        _lastHistoryInventorySignature = signature;
        _lastHistoryInventoryPublishedAtUtc = nowUtc;
        LogInfoLocal(
            $"MaybePublishHistoryInventory: scheduling inventory publish message_id={payload.MessageId} loaded_bar_count={loadedBarCount} current_bar_count={currentBarCount} first_started_at_utc={loadedFirstStartedAtUtc:O} latest_started_at_utc={loadedLatestStartedAtUtc:O} heartbeat_due={heartbeatDue}.");
        ObserveBackgroundTask(
            PublishHistoryInventoryAsync(payload),
            $"PublishHistoryInventoryAsync:{payload.MessageId}");
    }

    private void SyncLoadedHistoryIndex(DateTime nowUtc)
    {
        var currentBarCount = Math.Max(0, CurrentBar);
        if (currentBarCount > _latestObservedBarCount)
        {
            _latestObservedBarCount = currentBarCount;
            _lastHistoryBarsMutationObservedUtc = nowUtc;
            LogInfoLocal(
                $"history_bars_window count_updated loaded_bar_count={_latestObservedBarCount} latest_index={Math.Max(_latestObservedBarCount - 1, _latestObservedBarIndex)}.");
        }

        var currentLatestBarIndex = currentBarCount - 1;
        if (currentLatestBarIndex > _latestObservedBarIndex)
        {
            _latestObservedBarIndex = currentLatestBarIndex;
            _lastHistoryBarsMutationObservedUtc = nowUtc;
            LogInfoLocal(
                $"history_bars_window latest_index_updated loaded_bar_count={_latestObservedBarCount} latest_index={_latestObservedBarIndex}.");
        }
    }

    private int GetLatestCompletedHistoryBarIndex(DateTime nowUtc)
    {
        var lastIndex = GetLatestLoadedHistoryBarIndex();
        if (lastIndex < 0)
        {
            return -1;
        }

        if (!TryGetCandleSafe(lastIndex, out var lastCandle))
        {
            LogWarnLocal($"GetLatestCompletedHistoryBarIndex: unable to read last loaded candle at index={lastIndex}.");
            return -1;
        }

        var barSpan = EstimateLoadedBarSpan();
        var lastStartedAtUtc = ToUtc(lastCandle.Time);
        var lastEndedAtUtc = lastStartedAtUtc + barSpan - TimeSpan.FromSeconds(1);
        return lastEndedAtUtc < nowUtc ? lastIndex : lastIndex - 1;
    }

    private bool TryGetLatestCompletedBarStartedAtUtc(DateTime nowUtc, out DateTime latestCompletedBarStartedAtUtc)
    {
        latestCompletedBarStartedAtUtc = DateTime.MinValue;
        var completedLastIndex = GetLatestCompletedHistoryBarIndex(nowUtc);
        if (completedLastIndex < 0)
        {
            return false;
        }

        if (!TryGetCandleSafe(completedLastIndex, out var completedCandle))
        {
            return false;
        }

        latestCompletedBarStartedAtUtc = ToUtc(completedCandle.Time);
        return true;
    }

    private bool TryGetLoadedHistoryWindow(
        DateTime nowUtc,
        out int loadedLatestBarIndex,
        out int loadedBarCount,
        out DateTime loadedFirstStartedAtUtc,
        out DateTime loadedLatestStartedAtUtc)
    {
        loadedLatestBarIndex = -1;
        loadedBarCount = 0;
        loadedFirstStartedAtUtc = DateTime.MinValue;
        loadedLatestStartedAtUtc = DateTime.MinValue;

        var completedLastIndex = GetLatestCompletedHistoryBarIndex(nowUtc);
        if (completedLastIndex < 0)
        {
            return false;
        }

        if (!TryGetCandleSafe(0, out var firstCandle) || !TryGetCandleSafe(completedLastIndex, out var lastCandle))
        {
            return false;
        }

        loadedLatestBarIndex = completedLastIndex;
        loadedBarCount = completedLastIndex + 1;
        loadedFirstStartedAtUtc = ToUtc(firstCandle.Time);
        loadedLatestStartedAtUtc = ToUtc(lastCandle.Time);
        return true;
    }

    private bool ShouldReexportExpandedHistory(
        DateTime nowUtc,
        int loadedBarCount,
        DateTime loadedFirstStartedAtUtc,
        DateTime loadedLatestStartedAtUtc,
        TimeSpan stabilizationWindow)
    {
        if (_lastHistoryBarsExportedFirstStartedAtUtc is null || _lastHistoryBarsExportedCount <= 0)
        {
            return false;
        }

        if (loadedBarCount <= _lastHistoryBarsExportedCount || loadedLatestStartedAtUtc < _lastHistoryBarsExportedLatestStartedAtUtc)
        {
            return false;
        }

        var barSpan = EstimateLoadedBarSpan();
        var expandedEarlier = loadedFirstStartedAtUtc + barSpan <= _lastHistoryBarsExportedFirstStartedAtUtc.Value;
        if (!expandedEarlier)
        {
            return false;
        }

        if (_lastHistoryBarsMutationObservedUtc != DateTime.MinValue
            && nowUtc - _lastHistoryBarsMutationObservedUtc < stabilizationWindow)
        {
            return false;
        }

        return _lastHistoryBarsFullSnapshotExportedAtUtc == DateTime.MinValue
            || nowUtc - _lastHistoryBarsFullSnapshotExportedAtUtc >= TimeSpan.FromSeconds(10);
    }

    private void RecordHistoryBarsExport(
        IReadOnlyList<HistoryBarPayload> exportedBars,
        int loadedBarCount,
        int latestExportedBarIndex,
        bool fullSnapshot,
        DateTime exportedAtUtc)
    {
        _lastHistoryBarsExportedBarIndex = latestExportedBarIndex;
        _lastHistoryBarsExportedCount = Math.Max(loadedBarCount, exportedBars.Count);
        _lastHistoryBarsExportedFirstStartedAtUtc = exportedBars[0].StartedAt;
        _lastHistoryBarsExportedLatestStartedAtUtc = exportedBars[^1].StartedAt;
        if (fullSnapshot)
        {
            _lastHistoryBarsFullSnapshotExportedAtUtc = exportedAtUtc;
        }
    }

    private List<HistoryBarPayload> ExportLoadedHistoryBarsSnapshot(int startIndex = 0, int? endIndexInclusive = null)
    {
        var lastIndex = endIndexInclusive ?? GetLatestCompletedHistoryBarIndex(DateTime.UtcNow);
        if (lastIndex < 0)
        {
            return new List<HistoryBarPayload>();
        }

        var firstIndex = Math.Max(0, Math.Min(startIndex, lastIndex));
        if (firstIndex > lastIndex)
        {
            return new List<HistoryBarPayload>();
        }

        var barCount = lastIndex - firstIndex + 1;
        var bars = new List<HistoryBarPayload>(barCount);
        var barSpan = EstimateLoadedBarSpan();
        for (var index = firstIndex; index <= lastIndex; index++)
        {
            if (!TryGetCandleSafe(index, out var candle))
            {
                LogWarnLocal($"ExportLoadedHistoryBarsSnapshot: skipped unreadable candle at index={index}.");
                continue;
            }

            var originalBarTime = candle.Time;
            var startedAtUtc = ToUtc(candle.Time);
            bars.Add(new HistoryBarPayload
            {
                StartedAt = startedAtUtc,
                EndedAt = startedAtUtc + barSpan - TimeSpan.FromSeconds(1),
                Open = (double)candle.Open,
                High = (double)candle.High,
                Low = (double)candle.Low,
                Close = (double)candle.Close,
                Volume = AtasReflection.ReadInt(candle, "Volume"),
                Delta = AtasReflection.ReadInt(candle, "Delta"),
                BidVolume = AtasReflection.ReadInt(candle, "Bid"),
                AskVolume = AtasReflection.ReadInt(candle, "Ask"),
                BarTimestampUtc = startedAtUtc,
                OriginalBarTimeText = originalBarTime.ToString("O"),
            });
        }

        return bars;
    }

    private HistoryBarsPayload BuildHistoryBarsPayload(
        IReadOnlyList<HistoryBarPayload> bars,
        DateTime emittedAtUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext,
        int sequence)
    {
        var barTimeframe = ResolveNativeBarTimeframe(chartIdentity, bars.Select(item => item.StartedAt).ToList());
        return new HistoryBarsPayload
        {
            MessageId = CollectorMetadataResolver.BuildMessageId("history_bars", chartIdentity, bars[^1].StartedAt, sequence),
            EmittedAt = emittedAtUtc,
            ObservedWindowStart = bars[0].StartedAt,
            ObservedWindowEnd = bars[^1].EndedAt,
            Source = BuildSourceEnvelope(chartIdentity, timeContext),
            Instrument = BuildInstrumentEnvelope(chartIdentity),
            DisplayTimeframe = chartIdentity.DisplayTimeframe,
            TimeContext = timeContext.ToPayload(),
            BarTimeframe = barTimeframe,
            Bars = bars.ToList(),
        };
    }

    private HistoryInventoryPayload BuildHistoryInventoryPayload(
        DateTime emittedAtUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext,
        int loadedBarCount,
        int currentBarCount,
        int latestLoadedBarIndex,
        DateTime firstLoadedBarStartedAtUtc,
        DateTime latestLoadedBarStartedAtUtc)
    {
        var barSpan = EstimateLoadedBarSpan();
        var barTimeframe = ResolveNativeBarTimeframe(
            chartIdentity,
            new List<DateTime> { firstLoadedBarStartedAtUtc, latestLoadedBarStartedAtUtc });
        return new HistoryInventoryPayload
        {
            MessageId = CollectorMetadataResolver.BuildMessageId(
                "history_inventory",
                chartIdentity,
                latestLoadedBarStartedAtUtc,
                Math.Max(0, loadedBarCount)),
            EmittedAt = emittedAtUtc,
            ObservedWindowStart = firstLoadedBarStartedAtUtc,
            ObservedWindowEnd = latestLoadedBarStartedAtUtc + barSpan - TimeSpan.FromSeconds(1),
            Source = BuildSourceEnvelope(chartIdentity, timeContext),
            Instrument = BuildInstrumentEnvelope(chartIdentity),
            DisplayTimeframe = chartIdentity.DisplayTimeframe,
            TimeContext = timeContext.ToPayload(),
            BarTimeframe = barTimeframe,
            LoadedBarCount = Math.Max(0, loadedBarCount),
            CurrentBarCount = Math.Max(0, currentBarCount),
            LatestLoadedBarIndex = latestLoadedBarIndex >= 0 ? latestLoadedBarIndex : null,
            FirstLoadedBarStartedAtUtc = firstLoadedBarStartedAtUtc,
            LatestLoadedBarStartedAtUtc = latestLoadedBarStartedAtUtc,
            LatestCompletedBarStartedAtUtc = latestLoadedBarStartedAtUtc,
        };
    }

    private bool TrySendHistoryBarsChunks(
        IReadOnlyList<HistoryBarPayload> bars,
        DateTime emittedAtUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext)
    {
        if (_transport is null || bars.Count == 0)
        {
            return false;
        }

        LogResolvedContext(chartIdentity, timeContext);
        var payloads = BuildHistoryBarsChunks(bars, emittedAtUtc, chartIdentity, timeContext);
        var enqueuedAny = false;
        foreach (var payload in payloads)
        {
            if (!_transport.TryEnqueueHistoryBars(payload))
            {
                LogWarnLocal($"TrySendHistoryBarsChunks: history queue rejected {payload.MessageId}.");
                return false;
            }

            enqueuedAny = true;
        }

        return enqueuedAny;
    }

    private List<HistoryBarsPayload> BuildHistoryBarsChunks(
        IReadOnlyList<HistoryBarPayload> bars,
        DateTime emittedAtUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext,
        int maxChunkBars = DefaultHistoryBarsChunkBars)
    {
        var payloads = new List<HistoryBarsPayload>();
        if (bars.Count == 0)
        {
            return payloads;
        }

        var chunkSize = Math.Max(32, maxChunkBars);
        var sequence = 0;
        for (var offset = 0; offset < bars.Count; offset += chunkSize)
        {
            var chunkBars = bars.Skip(offset).Take(chunkSize).ToList();
            if (chunkBars.Count == 0)
            {
                continue;
            }

            payloads.Add(BuildHistoryBarsPayload(chunkBars, emittedAtUtc, chartIdentity, timeContext, sequence++));
        }

        return payloads;
    }

    private async Task PublishHistoryInventoryAsync(HistoryInventoryPayload payload)
    {
        try
        {
            var transport = _transport;
            if (transport is null)
            {
                return;
            }

            var sent = await transport.SendHistoryInventoryAsync(payload, CancellationToken.None).ConfigureAwait(false);
            if (sent)
            {
                LogInfoLocal(
                    $"PublishHistoryInventoryAsync: published inventory message_id={payload.MessageId} loaded_bar_count={payload.LoadedBarCount}.");
            }
            else
            {
                lock (_sync)
                {
                    _lastHistoryInventoryPublishedAtUtc = DateTime.MinValue;
                }
                LogWarnLocal($"PublishHistoryInventoryAsync: failed to publish inventory message_id={payload.MessageId}.");
            }
        }
        catch (Exception ex)
        {
            lock (_sync)
            {
                _lastHistoryInventoryPublishedAtUtc = DateTime.MinValue;
                _lastHistoryInventorySignature = string.Empty;
            }
            LogWarnLocal(
                $"PublishHistoryInventoryAsync unexpected error message_id={payload.MessageId}: {ex.GetType().Name}: {ex.Message}");
        }
        finally
        {
            Interlocked.Exchange(ref _historyInventorySendInFlight, 0);
        }
    }

    private List<HistoryFootprintBarPayload> ExportLoadedHistoryFootprintSnapshot(int startIndex = 0, int? endIndexInclusive = null)
    {
        var lastIndex = endIndexInclusive ?? GetLatestCompletedHistoryBarIndex(DateTime.UtcNow);
        if (lastIndex < 0)
        {
            return new List<HistoryFootprintBarPayload>();
        }

        var firstIndex = Math.Max(0, Math.Min(startIndex, lastIndex));
        if (firstIndex > lastIndex)
        {
            return new List<HistoryFootprintBarPayload>();
        }

        var barCount = lastIndex - firstIndex + 1;
        var bars = new List<HistoryFootprintBarPayload>(barCount);
        var barSpan = EstimateLoadedBarSpan();
        for (var index = firstIndex; index <= lastIndex; index++)
        {
            if (!TryGetCandleSafe(index, out var candle))
            {
                LogWarnLocal($"ExportLoadedHistoryFootprintSnapshot: skipped unreadable candle at index={index}.");
                continue;
            }

            var originalBarTime = candle.Time;
            var startedAtUtc = ToUtc(candle.Time);
            bars.Add(new HistoryFootprintBarPayload
            {
                StartedAt = startedAtUtc,
                EndedAt = startedAtUtc + barSpan - TimeSpan.FromSeconds(1),
                Open = (double)candle.Open,
                High = (double)candle.High,
                Low = (double)candle.Low,
                Close = (double)candle.Close,
                Volume = AtasReflection.ReadInt(candle, "Volume"),
                Delta = AtasReflection.ReadInt(candle, "Delta"),
                BidVolume = AtasReflection.ReadInt(candle, "Bid"),
                AskVolume = AtasReflection.ReadInt(candle, "Ask"),
                BarTimestampUtc = startedAtUtc,
                OriginalBarTimeText = originalBarTime.ToString("O"),
                PriceLevels = ExtractHistoryFootprintLevels(candle),
            });
        }

        return bars;
    }

    private List<HistoryFootprintPayload> BuildHistoryFootprintChunks(
        IReadOnlyList<HistoryFootprintBarPayload> bars,
        DateTime emittedAtUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext)
    {
        var payloads = new List<HistoryFootprintPayload>();
        if (bars.Count == 0)
        {
            return payloads;
        }

        var chunkSize = Math.Max(10, DefaultHistoryFootprintChunkBars);
        var chunkCount = (int)Math.Ceiling((double)bars.Count / chunkSize);
        var barTimeframe = ResolveNativeBarTimeframe(chartIdentity, bars.Select(item => item.StartedAt).ToList());
        var batchId = $"history-footprint-{chartIdentity.ContractSymbol.ToLowerInvariant()}-{bars[0].StartedAt:yyyyMMddHHmmss}";
        for (var chunkIndex = 0; chunkIndex < chunkCount; chunkIndex++)
        {
            var chunkBars = bars.Skip(chunkIndex * chunkSize).Take(chunkSize).ToList();
            if (chunkBars.Count == 0)
            {
                continue;
            }

            payloads.Add(new HistoryFootprintPayload
            {
                MessageId = CollectorMetadataResolver.BuildMessageId("history_footprint", chartIdentity, chunkBars[^1].StartedAt, chunkIndex),
                EmittedAt = emittedAtUtc,
                ObservedWindowStart = chunkBars[0].StartedAt,
                ObservedWindowEnd = chunkBars[^1].EndedAt,
                Source = BuildSourceEnvelope(chartIdentity, timeContext),
                Instrument = BuildInstrumentEnvelope(chartIdentity),
                DisplayTimeframe = chartIdentity.DisplayTimeframe,
                TimeContext = timeContext.ToPayload(),
                BatchId = batchId,
                BarTimeframe = barTimeframe,
                ChunkIndex = chunkIndex,
                ChunkCount = chunkCount,
                Bars = chunkBars,
            });
        }

        return payloads;
    }

    private InitiativeDrivePayload? BuildActiveDrivePayload()
    {
        if (_driveState is null)
        {
            return null;
        }

        var payload = _driveState.ToPayload(EffectiveTickSize);
        return Math.Abs(payload.NetDelta) >= DriveMinNetDelta && payload.PriceTravelTicks >= DriveMinTravelTicks ? payload : null;
    }

    private ManipulationLegPayload? BuildManipulationLegPayload()
    {
        var drive = BuildActiveDrivePayload();
        if (drive is null || drive.PriceTravelTicks < Math.Max(MeasuredReferenceTicks, DriveMinTravelTicks))
        {
            return null;
        }

        var displacementTicks = Math.Max(DriveMinTravelTicks, drive.PriceTravelTicks);
        return new ManipulationLegPayload
        {
            LegId = $"leg-{drive.DriveId}",
            Side = drive.Side,
            StartedAt = drive.StartedAt,
            EndedAt = DateTime.UtcNow,
            PriceLow = drive.PriceLow,
            PriceHigh = drive.PriceHigh,
            DisplacementTicks = displacementTicks,
            PrimaryObjectiveTicks = displacementTicks,
            SecondaryObjectiveTicks = displacementTicks * 2,
            PrimaryObjectiveReached = true,
            SecondaryObjectiveReached = drive.PriceTravelTicks >= displacementTicks * 2,
        };
    }

    private MeasuredMovePayload? BuildMeasuredMovePayload()
    {
        var drive = BuildActiveDrivePayload();
        if (drive is null)
        {
            return null;
        }

        var referenceTicks = Math.Max(1, MeasuredReferenceTicks);
        var achievedMultiple = Math.Round((double)drive.PriceTravelTicks / referenceTicks, 2);
        return new MeasuredMovePayload
        {
            MeasurementId = $"measure-{drive.DriveId}",
            MeasuredSubjectId = drive.DriveId,
            MeasuredSubjectKind = "initiative_drive",
            Side = drive.Side,
            AnchorPrice = drive.Side == "buy" ? drive.PriceLow : drive.PriceHigh,
            LatestPrice = drive.Side == "buy" ? drive.PriceHigh : drive.PriceLow,
            AchievedDistanceTicks = drive.PriceTravelTicks,
            ReferenceKind = "range_amplitude",
            ReferenceDistanceTicks = referenceTicks,
            AchievedMultiple = achievedMultiple,
            BodyConfirmedThresholdMultiple = achievedMultiple >= 1.0 ? Math.Floor(achievedMultiple * 2.0) / 2.0 : null,
            NextTargetMultiple = Math.Ceiling(Math.Max(1.0, achievedMultiple + 0.01)),
            Invalidated = false,
        };
    }

    private PostHarvestResponsePayload? BuildPostHarvestPayload()
    {
        if (_harvestState is null)
        {
            return null;
        }

        var lastPrice = _lastPrice ?? _harvestState.HarvestedPriceLow;
        var continuationTicks = ComputeContinuationTicks(_harvestState);
        var consolidationRangeTicks = PriceMath.ToTicks(_harvestState.HighestAfterCompletion - _harvestState.LowestAfterCompletion, EffectiveTickSize);
        var pullbackTicks = ComputePullbackTicks(_harvestState, lastPrice);
        var reversalTicks = ComputeReversalTicks(_harvestState, lastPrice);

        return new PostHarvestResponsePayload
        {
            ResponseId = _harvestState.ResponseId,
            HarvestSubjectId = _harvestState.HarvestSubjectId,
            HarvestSubjectKind = _harvestState.HarvestSubjectKind,
            HarvestSide = _harvestState.HarvestSide.ToPayloadString(),
            HarvestCompletedAt = _harvestState.HarvestCompletedAtUtc,
            HarvestedPriceLow = (double)_harvestState.HarvestedPriceLow,
            HarvestedPriceHigh = (double)_harvestState.HarvestedPriceHigh,
            CompletionRatio = 1.0,
            ContinuationTicksAfterCompletion = continuationTicks,
            ConsolidationRangeTicks = consolidationRangeTicks,
            PullbackTicks = pullbackTicks,
            ReversalTicks = reversalTicks,
            SecondsToFirstPullback = _harvestState.FirstPullbackAtUtc is null ? null : (int)(_harvestState.FirstPullbackAtUtc.Value - _harvestState.HarvestCompletedAtUtc).TotalSeconds,
            SecondsToReversal = _harvestState.FirstReversalAtUtc is null ? null : (int)(_harvestState.FirstReversalAtUtc.Value - _harvestState.HarvestCompletedAtUtc).TotalSeconds,
            ReachedNextOpposingLiquidity = false,
            NextOpposingLiquidityPrice = null,
            PostHarvestDelta = _harvestState.PostHarvestDelta,
            Outcome = DeterminePostHarvestOutcome(continuationTicks, consolidationRangeTicks, pullbackTicks, reversalTicks),
        };
    }

    private ZoneInteractionPayload? BuildZoneInteractionPayload()
    {
        var bestTrack = _liquidityTracks.Values
            .Where(item => item.ReplenishmentCount >= StrongReplenishmentCount && item.TouchCount > 0)
            .OrderByDescending(item => item.HeatScore)
            .FirstOrDefault();
        if (bestTrack is null)
        {
            return null;
        }

        return new ZoneInteractionPayload
        {
            ZoneId = $"zone-{bestTrack.TrackId}",
            ZoneLow = (double)(bestTrack.Side == CollectorSide.Buy ? bestTrack.Price - EffectiveTickSize : bestTrack.Price),
            ZoneHigh = (double)(bestTrack.Side == CollectorSide.Sell ? bestTrack.Price + EffectiveTickSize : bestTrack.Price),
            StartedAt = bestTrack.FirstObservedAtUtc,
            ExecutedVolumeAgainst = bestTrack.ExecutedVolumeEstimate,
            ReplenishmentCount = bestTrack.ReplenishmentCount,
            BuyersHittingSameLevelCount = bestTrack.Side == CollectorSide.Buy ? Math.Max(1, bestTrack.TouchCount) : 0,
            SellersHittingSameLevelCount = bestTrack.Side == CollectorSide.Sell ? Math.Max(1, bestTrack.TouchCount) : 0,
            PullCount = bestTrack.PullCount,
            PriceRejectionTicks = bestTrack.PriceReactionTicks,
            SecondsHeld = Math.Max(0, (int)(bestTrack.LastObservedAtUtc - bestTrack.FirstObservedAtUtc).TotalSeconds),
        };
    }

    private EmaContextPayload? BuildEmaContextPayload(decimal lastPrice)
    {
        if (_ema20 is null)
        {
            return null;
        }

        return new EmaContextPayload
        {
            Ema20 = (double)_ema20.Value,
            Ema20DistanceTicks = PriceMath.ToTicks(Math.Abs(lastPrice - _ema20.Value), EffectiveTickSize),
            Ema20Slope = 0.0,
            Ema20ReclaimConfirmed = lastPrice >= _ema20.Value,
            BarsAboveEma20AfterReclaim = lastPrice >= _ema20.Value ? 1 : 0,
        };
    }

    private List<ReferenceLevelPayload> BuildReferenceLevels()
    {
        var levels = _liquidityTracks.Values
            .OrderByDescending(item => item.HeatScore)
            .Take(4)
            .Select(item => new ReferenceLevelPayload
            {
                Kind = item.Side == CollectorSide.Buy ? "significant_bid" : "significant_ask",
                Price = (double)item.Price,
                Notes = new List<string> { $"replenishment={item.ReplenishmentCount}", $"touches={item.TouchCount}" },
            })
            .ToList();

        if (_gapReference is not null)
        {
            levels.Add(new ReferenceLevelPayload { Kind = "gap_high", Price = _gapReference.GapHigh, Notes = new List<string> { $"fill_ratio={_gapReference.FillRatio:F2}" } });
            levels.Add(new ReferenceLevelPayload { Kind = "gap_low", Price = _gapReference.GapLow, Notes = new List<string> { $"fill_ratio={_gapReference.FillRatio:F2}" } });
        }

        return levels;
    }

    private void ScheduleTriggerBurst(string triggerType, DateTime triggeredAtUtc, decimal triggerPrice, IEnumerable<string> reasonCodes, string uniquenessKey)
    {
        if (_transport is null)
        {
            return;
        }

        if (_lastTriggerByKey.TryGetValue(uniquenessKey, out var lastTriggeredAtUtc) && (triggeredAtUtc - lastTriggeredAtUtc).TotalSeconds < 10)
        {
            return;
        }

        _lastTriggerByKey[uniquenessKey] = triggeredAtUtc;
        var chartIdentity = ResolveChartIdentity();
        var timeContext = ResolveTimeContext();
        LogResolvedContext(chartIdentity, timeContext);
        var payload = new TriggerBurstPayload
        {
            MessageId = CollectorMetadataResolver.BuildMessageId("trigger_burst", chartIdentity, triggeredAtUtc, 0),
            EmittedAt = DateTime.UtcNow,
            ObservedWindowStart = triggeredAtUtc.AddSeconds(-Math.Max(1, BurstLookbackSeconds)),
            ObservedWindowEnd = DateTime.UtcNow,
            Source = BuildSourceEnvelope(chartIdentity, timeContext),
            Instrument = BuildInstrumentEnvelope(chartIdentity),
            DisplayTimeframe = chartIdentity.DisplayTimeframe,
            TimeContext = timeContext.ToPayload(),
            Trigger = new TriggerInfoPayload
            {
                TriggerId = $"{triggerType}-{triggeredAtUtc:yyyyMMddHHmmssfff}",
                TriggerType = triggerType,
                TriggeredAt = triggeredAtUtc,
                Price = (double)triggerPrice,
                ReasonCodes = reasonCodes.ToList(),
            },
            PreWindow = BuildBurstWindow(triggeredAtUtc.AddSeconds(-Math.Max(1, BurstLookbackSeconds)), triggeredAtUtc.AddTicks(-1)),
            EventWindow = BuildBurstWindow(triggeredAtUtc.AddSeconds(-1), triggeredAtUtc.AddSeconds(1)),
            PostWindow = new BurstWindowPayload(),
        };
        if (!_transport.TryEnqueueTriggerBurst(payload))
        {
            LogWarnLocal($"TryEmitTriggerBurst: realtime queue rejected {payload.MessageId}.");
        }
    }

    private BurstWindowPayload BuildBurstWindow(DateTime startUtc, DateTime endUtc) => new()
    {
        TradeEvents = _tradeBuffer.Snapshot(startUtc, endUtc),
        DepthEvents = _depthBuffer.Snapshot(startUtc, endUtc),
        SecondFeatures = _secondBuffer.Snapshot(startUtc, endUtc),
        PriceLevels = new List<Dictionary<string, object?>>(),
        Bookmarks = new List<BookmarkPayload>(),
    };

    private void EnsureSecondAccumulator(DateTime eventTimeUtc, decimal price)
    {
        var secondStart = new DateTime(eventTimeUtc.Year, eventTimeUtc.Month, eventTimeUtc.Day, eventTimeUtc.Hour, eventTimeUtc.Minute, eventTimeUtc.Second, DateTimeKind.Utc);
        if (_currentSecond is null)
        {
            _currentSecond = new SecondAccumulatorState(secondStart, price);
            return;
        }

        if (_currentSecond.SecondStartedAtUtc != secondStart)
        {
            FinalizeCurrentSecond(eventTimeUtc);
            _currentSecond = new SecondAccumulatorState(secondStart, price);
        }
        else
        {
            _currentSecond.ObservePrice(price);
        }
    }

    private void FinalizeCurrentSecond(DateTime nowUtc)
    {
        if (_currentSecond is null || nowUtc < _currentSecond.SecondStartedAtUtc.AddSeconds(1))
        {
            return;
        }

        if (_bestBid is not null)
        {
            _currentSecond.ObserveBestBid(_bestBid);
        }

        if (_bestAsk is not null)
        {
            _currentSecond.ObserveBestAsk(_bestAsk);
        }

        var bidDepth = _liquidityTracks.Values.Where(item => item.Side == CollectorSide.Buy && item.CurrentSize > 0).Sum(item => item.CurrentSize);
        var askDepth = _liquidityTracks.Values.Where(item => item.Side == CollectorSide.Sell && item.CurrentSize > 0).Sum(item => item.CurrentSize);
        if (bidDepth + askDepth > 0)
        {
            _currentSecond.DepthImbalance = Math.Round((double)(bidDepth - askDepth) / (bidDepth + askDepth), 4);
        }

        _secondBuffer.Add(_currentSecond.ToPayload());
        _currentSecond = null;
    }

    private void UpdateEma(int bar, decimal close)
    {
        if (bar == _lastEmaBar)
        {
            return;
        }

        const decimal alpha = 2m / 21m;
        _ema20 = _ema20 is null ? close : _ema20.Value + (alpha * (close - _ema20.Value));
        _lastEmaBar = bar;
    }

    private string DetermineSessionCode(DateTime observedAtUtc, ChartIdentity chartIdentity, ResolvedTimeContext timeContext)
    {
        if (!string.IsNullOrWhiteSpace(SessionCodeOverride))
        {
            return SessionCodeOverride.Trim().ToLowerInvariant();
        }

        var marketNow = CollectorMetadataResolver.ToReferenceTime(observedAtUtc, timeContext);
        var profile = ResolveSessionProfile(chartIdentity, timeContext, observedAtUtc);
        var minutes = marketNow.Hour * 60 + marketNow.Minute;
        if (minutes < 7 * 60)
        {
            return "asia";
        }

        if (minutes < Math.Max(7 * 60, profile.RegularSessionOpenLocalMinutes - 60))
        {
            return "europe";
        }

        if (minutes < profile.RegularSessionOpenLocalMinutes)
        {
            return "us_premarket";
        }

        return minutes < profile.RegularSessionCloseLocalMinutes ? "us_regular" : "us_after_hours";
    }

    private static bool IsRegularSession(DateTime observedAtUtc, ChartIdentity chartIdentity, ResolvedTimeContext timeContext)
    {
        var marketNow = CollectorMetadataResolver.ToReferenceTime(observedAtUtc, timeContext);
        var minutes = marketNow.Hour * 60 + marketNow.Minute;
        var profile = ResolveSessionProfile(chartIdentity, timeContext, observedAtUtc);
        return minutes >= profile.RegularSessionOpenLocalMinutes && minutes < profile.RegularSessionCloseLocalMinutes;
    }

    private static string DetermineTradingDate(DateTime observedAtUtc, ChartIdentity chartIdentity, ResolvedTimeContext timeContext)
    {
        var marketNow = CollectorMetadataResolver.ToReferenceTime(observedAtUtc, timeContext);
        var profile = ResolveSessionProfile(chartIdentity, timeContext, observedAtUtc);
        var minutes = marketNow.Hour * 60 + marketNow.Minute;
        var tradingDate = minutes >= profile.TradingDayRollLocalMinutes
            ? marketNow.Date.AddDays(1)
            : marketNow.Date;
        return tradingDate.ToString("yyyy-MM-dd");
    }

    private decimal EffectiveTickSize => ResolveChartIdentity().TickSize;

    private ChartIdentity ResolveChartIdentity()
    {
        var nowUtc = DateTime.UtcNow;
        if (_chartIdentityCache is not null && (nowUtc - _chartIdentityResolvedAtUtc).TotalSeconds < 2)
        {
            return _chartIdentityCache;
        }

        _chartIdentityCache = CollectorMetadataResolver.ResolveChartIdentity(
            this,
            SymbolOverride,
            TickSizeOverride,
            Venue,
            Currency,
            EstimateLoadedBarSpan);
        _chartIdentityResolvedAtUtc = nowUtc;
        return _chartIdentityCache;
    }

    private ResolvedTimeContext ResolveTimeContext()
    {
        var nowUtc = DateTime.UtcNow;
        if (_timeContextCache is not null && (nowUtc - _timeContextResolvedAtUtc).TotalSeconds < 2)
        {
            return _timeContextCache;
        }

        _timeContextCache = CollectorMetadataResolver.ResolveTimeContext(this, nowUtc, ForceUtcTimestamps);
        _timeContextResolvedAtUtc = nowUtc;
        return _timeContextCache;
    }

    private SourceEnvelope BuildSourceEnvelope(ChartIdentity chartIdentity, ResolvedTimeContext timeContext) => new()
    {
        System = "ATAS",
        InstanceId = Environment.MachineName,
        ChartInstanceId = chartIdentity.ChartInstanceId,
        AdapterVersion = CollectorVersion,
        ChartDisplayTimezoneMode = timeContext.ChartDisplayTimezoneMode,
        ChartDisplayTimezoneName = timeContext.ChartDisplayTimezoneName,
        ChartDisplayUtcOffsetMinutes = timeContext.ChartDisplayUtcOffsetMinutes,
        InstrumentTimezoneValue = timeContext.InstrumentTimezoneValue,
        InstrumentTimezoneSource = timeContext.InstrumentTimezoneSource,
        CollectorLocalTimezoneName = timeContext.CollectorLocalTimezoneName,
        CollectorLocalUtcOffsetMinutes = timeContext.CollectorLocalUtcOffsetMinutes,
        TimestampBasis = timeContext.TimestampBasis,
        TimezoneCaptureConfidence = timeContext.TimezoneCaptureConfidence,
    };

    private SessionContextPayload BuildSessionContext(ChartIdentity chartIdentity, ResolvedTimeContext timeContext, DateTime observedAtUtc)
    {
        return new SessionContextPayload
        {
            SessionCode = DetermineSessionCode(observedAtUtc, chartIdentity, timeContext),
            TradingDate = DetermineTradingDate(observedAtUtc, chartIdentity, timeContext),
            IsRthOpen = IsRegularSession(observedAtUtc, chartIdentity, timeContext),
            PriorRthClose = (double)PriorRthClose,
            PriorRthHigh = (double)PriorRthHigh,
            PriorRthLow = (double)PriorRthLow,
            PriorValueAreaLow = NullIfZero(PriorValueAreaLow),
            PriorValueAreaHigh = NullIfZero(PriorValueAreaHigh),
            PriorPointOfControl = NullIfZero(PriorPointOfControl),
            OvernightHigh = NullIfZero(OvernightHigh),
            OvernightLow = NullIfZero(OvernightLow),
            OvernightMid = OvernightHigh > 0m && OvernightLow > 0m ? (double)((OvernightHigh + OvernightLow) / 2m) : null,
        };
    }

    private InstrumentEnvelope BuildInstrumentEnvelope(ChartIdentity chartIdentity) => new()
    {
        Symbol = chartIdentity.DisplaySymbol,
        RootSymbol = chartIdentity.RootSymbol,
        ContractSymbol = chartIdentity.ContractSymbol,
        Venue = chartIdentity.Venue,
        TickSize = (double)chartIdentity.TickSize,
        Currency = chartIdentity.Currency,
    };

    private static SessionProfile ResolveSessionProfile(ChartIdentity chartIdentity, ResolvedTimeContext timeContext, DateTime observedAtUtc)
    {
        var venue = chartIdentity.Venue ?? string.Empty;
        var referenceName = (timeContext.ChartDisplayTimezoneName
            ?? timeContext.InstrumentTimezoneValue
            ?? timeContext.CollectorLocalTimezoneName
            ?? string.Empty).ToLowerInvariant();

        var looksEastern = referenceName.Contains("new_york", StringComparison.Ordinal)
            || referenceName.Contains("eastern", StringComparison.Ordinal);
        var looksCentral = referenceName.Contains("chicago", StringComparison.Ordinal)
            || referenceName.Contains("central", StringComparison.Ordinal);

        if (venue.Contains("CME", StringComparison.OrdinalIgnoreCase))
        {
            if (looksEastern)
            {
                return new SessionProfile(9 * 60 + 30, 16 * 60, 18 * 60, "cme_equity_index_eastern");
            }

            if (looksCentral || timeContext.ChartDisplayTimezoneSource.Contains("instrument", StringComparison.OrdinalIgnoreCase))
            {
                return new SessionProfile(8 * 60 + 30, 15 * 60, 17 * 60, "cme_equity_index_central");
            }
        }

        var marketNow = CollectorMetadataResolver.ToReferenceTime(observedAtUtc, timeContext);
        var inferredRegularOpen = marketNow.Offset == TimeSpan.Zero ? 8 * 60 + 30 : 9 * 60 + 30;
        return new SessionProfile(inferredRegularOpen, inferredRegularOpen + (6 * 60 + 30), 17 * 60, "generic_fallback");
    }

    private int ComputeContinuousSequence(DateTime barTimestampUtc, DateTime observedAtUtc)
    {
        var cadenceMs = Math.Max(250, ContinuousCadenceMilliseconds);
        var elapsedMs = Math.Max(0.0, (observedAtUtc - barTimestampUtc).TotalMilliseconds);
        return (int)Math.Floor(elapsedMs / cadenceMs);
    }

    private void LogResolvedContext(ChartIdentity chartIdentity, ResolvedTimeContext timeContext)
    {
        var signature = CollectorMetadataResolver.Describe(chartIdentity, timeContext);
        if (string.Equals(signature, _lastLoggedContextSignature, StringComparison.Ordinal))
        {
            return;
        }

        _lastLoggedContextSignature = signature;
        LogInfoLocal($"collector_context {signature}");
    }

    private TimeSpan EstimateLoadedBarSpan()
    {
        var lastIndex = GetLatestLoadedHistoryBarIndex();
        if (lastIndex < 1)
        {
            return TimeSpan.FromMinutes(1);
        }

        for (var index = lastIndex; index >= 1; index--)
        {
            if (!TryGetCandleSafe(index, out var currentCandle)
                || !TryGetCandleSafe(index - 1, out var previousCandle))
            {
                continue;
            }

            var currentStart = currentCandle.Time;
            var previousStart = previousCandle.Time;
            var span = currentStart - previousStart;
            if (span > TimeSpan.Zero)
            {
                return span;
            }
        }

        return TimeSpan.FromMinutes(1);
    }

    private int GetLatestLoadedHistoryBarIndex()
    {
        var observedBarCount = Math.Max(_latestObservedBarCount, Math.Max(CurrentBar, _latestObservedBarIndex + 1));
        return observedBarCount - 1;
    }

    private bool TryGetCandleSafe(int index, out IndicatorCandle candle)
    {
        candle = null!;
        var latestLoadedBarIndex = GetLatestLoadedHistoryBarIndex();
        if (index < 0 || index > latestLoadedBarIndex)
        {
            return false;
        }

        try
        {
            var loadedCandle = GetCandle(index);
            if (loadedCandle is null)
            {
                return false;
            }

            candle = loadedCandle;
            return true;
        }
        catch (Exception ex)
        {
            LogWarnLocal(
                $"TryGetCandleSafe: failed to read candle index={index} latest_loaded_index={latestLoadedBarIndex} current_bar_count={CurrentBar} error={ex.Message}");
            return false;
        }
    }

    private string ResolveNativeBarTimeframe(ChartIdentity chartIdentity, IReadOnlyList<DateTime> barStartsUtc)
    {
        if (!string.IsNullOrWhiteSpace(chartIdentity.DisplayTimeframe) && !string.Equals(chartIdentity.DisplayTimeframe, "unknown", StringComparison.OrdinalIgnoreCase))
        {
            return chartIdentity.DisplayTimeframe;
        }

        return CollectorMetadataResolver.FormatTimeframe(InferBarSpan(barStartsUtc));
    }

    private static TimeSpan InferBarSpan(IReadOnlyList<DateTime> barStartsUtc)
    {
        if (barStartsUtc.Count < 2)
        {
            return TimeSpan.FromMinutes(1);
        }

        TimeSpan? bestSpan = null;
        for (var index = 1; index < barStartsUtc.Count; index++)
        {
            var span = barStartsUtc[index] - barStartsUtc[index - 1];
            if (span > TimeSpan.Zero && (bestSpan is null || span < bestSpan.Value))
            {
                bestSpan = span;
            }
        }

        return bestSpan ?? TimeSpan.FromMinutes(1);
    }

    private static List<HistoryFootprintLevelPayload> ExtractHistoryFootprintLevels(object candle)
    {
        var levels = new List<HistoryFootprintLevelPayload>();
        foreach (var level in AtasReflection.ReadSequence(candle, "GetAllPriceLevels", "PriceLevels"))
        {
            var price = AtasReflection.ReadDecimal(level, "Price");
            if (price is null)
            {
                continue;
            }

            var bidVolume = AtasReflection.ReadInt(level, "Bid");
            var askVolume = AtasReflection.ReadInt(level, "Ask");
            var totalVolume = AtasReflection.ReadInt(level, "Volume", "TotalVolume");
            var delta = AtasReflection.ReadInt(level, "Delta");
            if (totalVolume is null && bidVolume is not null && askVolume is not null)
            {
                totalVolume = bidVolume + askVolume;
            }

            if (delta is null && bidVolume is not null && askVolume is not null)
            {
                delta = askVolume - bidVolume;
            }

            levels.Add(new HistoryFootprintLevelPayload
            {
                Price = (double)price.Value,
                BidVolume = bidVolume,
                AskVolume = askVolume,
                TotalVolume = totalVolume,
                Delta = delta,
                TradeCount = AtasReflection.ReadInt(level, "Ticks", "TradeCount"),
            });
        }

        return levels;
    }

    private static DateTime EnsureUtc(DateTime value) => value.Kind switch
    {
        DateTimeKind.Utc => value,
        DateTimeKind.Unspecified => DateTime.SpecifyKind(value, DateTimeKind.Utc),
        _ => value.ToUniversalTime(),
    };

    private static List<(DateTime StartUtc, DateTime EndUtc)> ResolveBackfillRanges(AdapterBackfillCommandPayload command)
    {
        var windowStartUtc = EnsureUtc(command.WindowStart);
        var windowEndUtc = EnsureUtc(command.WindowEnd);
        if (windowEndUtc < windowStartUtc)
        {
            (windowStartUtc, windowEndUtc) = (windowEndUtc, windowStartUtc);
        }

        var rawRanges = new List<(DateTime StartUtc, DateTime EndUtc)>();
        if (command.RequestedRanges.Count > 0)
        {
            rawRanges.AddRange(command.RequestedRanges.Select(item =>
            {
                var rangeStartUtc = EnsureUtc(item.RangeStart);
                var rangeEndUtc = EnsureUtc(item.RangeEnd);
                return rangeEndUtc < rangeStartUtc
                    ? (rangeEndUtc, rangeStartUtc)
                    : (rangeStartUtc, rangeEndUtc);
            }));
        }
        else if (command.MissingSegments.Count > 0)
        {
            rawRanges.AddRange(command.MissingSegments.Select(segment =>
            {
                var rangeStartUtc = EnsureUtc(segment.PrevEndedAt?.AddSeconds(1) ?? command.WindowStart);
                var rangeEndUtc = EnsureUtc(segment.NextStartedAt).AddSeconds(-1);
                return rangeEndUtc < rangeStartUtc
                    ? (rangeEndUtc, rangeStartUtc)
                    : (rangeStartUtc, rangeEndUtc);
            }));
        }

        if (rawRanges.Count == 0)
        {
            rawRanges.Add((windowStartUtc, windowEndUtc));
        }

        var clampedRanges = new List<(DateTime StartUtc, DateTime EndUtc)>(rawRanges.Count);
        foreach (var (rangeStartUtc, rangeEndUtc) in rawRanges)
        {
            var clampedStartUtc = rangeStartUtc < windowStartUtc ? windowStartUtc : rangeStartUtc;
            var clampedEndUtc = rangeEndUtc > windowEndUtc ? windowEndUtc : rangeEndUtc;
            if (clampedEndUtc < clampedStartUtc)
            {
                continue;
            }

            clampedRanges.Add((clampedStartUtc, clampedEndUtc));
        }

        if (clampedRanges.Count == 0)
        {
            return clampedRanges;
        }

        clampedRanges.Sort((left, right) =>
        {
            var startCompare = left.StartUtc.CompareTo(right.StartUtc);
            return startCompare != 0 ? startCompare : left.EndUtc.CompareTo(right.EndUtc);
        });

        var mergedRanges = new List<(DateTime StartUtc, DateTime EndUtc)> { clampedRanges[0] };
        for (var index = 1; index < clampedRanges.Count; index++)
        {
            var current = mergedRanges[^1];
            var next = clampedRanges[index];
            if (next.StartUtc <= current.EndUtc + TimeSpan.FromSeconds(1))
            {
                mergedRanges[^1] = (
                    current.StartUtc,
                    next.EndUtc > current.EndUtc ? next.EndUtc : current.EndUtc);
                continue;
            }

            mergedRanges.Add(next);
        }

        return mergedRanges;
    }

    private static bool OverlapsAnyRange(
        DateTime itemStartUtc,
        DateTime itemEndUtc,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> rangesUtc)
    {
        foreach (var (rangeStartUtc, rangeEndUtc) in rangesUtc)
        {
            if (itemEndUtc < rangeStartUtc)
            {
                return false;
            }

            if (itemStartUtc <= rangeEndUtc && itemEndUtc >= rangeStartUtc)
            {
                return true;
            }
        }

        return false;
    }

    private static List<HistoryBarPayload> FilterHistoryBarsByRanges(
        IReadOnlyList<HistoryBarPayload> loadedBars,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> rangesUtc)
    {
        if (loadedBars.Count == 0 || rangesUtc.Count == 0)
        {
            return new List<HistoryBarPayload>();
        }

        var filteredBars = new List<HistoryBarPayload>(loadedBars.Count);
        foreach (var bar in loadedBars)
        {
            if (OverlapsAnyRange(bar.StartedAt, bar.EndedAt, rangesUtc))
            {
                filteredBars.Add(bar);
            }
        }

        return filteredBars;
    }

    private static List<HistoryFootprintBarPayload> FilterHistoryFootprintBarsByRanges(
        IReadOnlyList<HistoryFootprintBarPayload> loadedBars,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> rangesUtc)
    {
        if (loadedBars.Count == 0 || rangesUtc.Count == 0)
        {
            return new List<HistoryFootprintBarPayload>();
        }

        var filteredBars = new List<HistoryFootprintBarPayload>(loadedBars.Count);
        foreach (var bar in loadedBars)
        {
            if (OverlapsAnyRange(bar.StartedAt, bar.EndedAt, rangesUtc))
            {
                filteredBars.Add(bar);
            }
        }

        return filteredBars;
    }

    private static bool CoversRequestedRanges(
        IReadOnlyList<HistoryBarPayload> filteredBars,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> targetRangesUtc,
        out string coverageDetail)
    {
        coverageDetail = "empty";
        if (filteredBars.Count == 0 || targetRangesUtc.Count == 0)
        {
            return false;
        }

        var tolerance = TimeSpan.FromSeconds(1);
        foreach (var (rangeStartUtc, rangeEndUtc) in targetRangesUtc)
        {
            var matchedAny = false;
            var coveredUntilUtc = DateTime.MinValue;
            foreach (var bar in filteredBars)
            {
                if (bar.EndedAt < rangeStartUtc || bar.StartedAt > rangeEndUtc)
                {
                    continue;
                }

                var overlapStartUtc = bar.StartedAt > rangeStartUtc ? bar.StartedAt : rangeStartUtc;
                var overlapEndUtc = bar.EndedAt < rangeEndUtc ? bar.EndedAt : rangeEndUtc;
                if (!matchedAny)
                {
                    if (overlapStartUtc > rangeStartUtc + tolerance)
                    {
                        coverageDetail = $"gap_at_start:{rangeStartUtc:O}";
                        return false;
                    }

                    matchedAny = true;
                    coveredUntilUtc = overlapEndUtc;
                }
                else
                {
                    if (overlapStartUtc > coveredUntilUtc.AddSeconds(1))
                    {
                        coverageDetail = $"gap_after:{coveredUntilUtc:O}";
                        return false;
                    }

                    if (overlapEndUtc > coveredUntilUtc)
                    {
                        coveredUntilUtc = overlapEndUtc;
                    }
                }

                if (coveredUntilUtc >= rangeEndUtc - tolerance)
                {
                    break;
                }
            }

            if (!matchedAny)
            {
                coverageDetail = $"missing:{rangeStartUtc:O}";
                return false;
            }

            if (coveredUntilUtc < rangeEndUtc - tolerance)
            {
                coverageDetail = $"truncated:{coveredUntilUtc:O}->{rangeEndUtc:O}";
                return false;
            }
        }

        coverageDetail = "complete";
        return true;
    }

    private static string FormatBackfillRanges(IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> rangesUtc)
    {
        if (rangesUtc.Count == 0)
        {
            return "none";
        }

        return string.Join(",", rangesUtc.Select(range => $"{range.StartUtc:O}..{range.EndUtc:O}"));
    }

    private static string BuildBackfillAckNote(string status, string? historyBarsDiagnostic)
    {
        if (string.IsNullOrWhiteSpace(historyBarsDiagnostic))
        {
            return status;
        }

        var note = $"{status}; {historyBarsDiagnostic}";
        return note.Length <= 480 ? note : note[..480];
    }

    private DateTime ToUtc(DateTime value) => CollectorMetadataResolver.ToUtc(value, ResolveTimeContext());

    private static int DecimalToInt(decimal value) => Math.Max(0, decimal.ToInt32(decimal.Round(value, MidpointRounding.AwayFromZero)));

    private static double? DecimalToDouble(decimal? value) => value is null ? null : (double)value.Value;

    private static double? NullIfZero(decimal value) => value == 0m ? null : (double)value;

    private static int ComputeReactionTicks(CollectorSide side, decimal trackPrice, decimal currentPrice, decimal tickSize) => side switch
    {
        CollectorSide.Buy when currentPrice > trackPrice => PriceMath.ToTicks(currentPrice - trackPrice, tickSize),
        CollectorSide.Sell when currentPrice < trackPrice => PriceMath.ToTicks(trackPrice - currentPrice, tickSize),
        _ => 0,
    };

    private static double ComputeHeatScore(SignificantLiquidityTrackState track, int distanceTicks)
    {
        var sizeScore = Math.Min(0.5, track.MaxSeenSize / 500.0);
        var behaviorScore = Math.Min(0.35, (track.ReplenishmentCount * 0.08) + (track.TouchCount * 0.05));
        var proximityScore = Math.Max(0.0, 0.15 - (distanceTicks * 0.01));
        return Math.Round(Math.Min(1.0, sizeScore + behaviorScore + proximityScore), 3);
    }

    private int ComputeContinuationTicks(HarvestState harvestState) => harvestState.HarvestSide == CollectorSide.Buy
        ? PriceMath.ToTicks(Math.Max(0m, harvestState.HighestAfterCompletion - harvestState.HarvestedPriceHigh), EffectiveTickSize)
        : PriceMath.ToTicks(Math.Max(0m, harvestState.HarvestedPriceLow - harvestState.LowestAfterCompletion), EffectiveTickSize);

    private int ComputePullbackTicks(HarvestState harvestState, decimal currentPrice) => harvestState.HarvestSide == CollectorSide.Buy
        ? PriceMath.ToTicks(Math.Max(0m, harvestState.HarvestedPriceHigh - currentPrice), EffectiveTickSize)
        : PriceMath.ToTicks(Math.Max(0m, currentPrice - harvestState.HarvestedPriceLow), EffectiveTickSize);

    private int ComputeReversalTicks(HarvestState harvestState, decimal currentPrice) => harvestState.HarvestSide == CollectorSide.Buy
        ? PriceMath.ToTicks(Math.Max(0m, harvestState.HarvestedPriceLow - currentPrice), EffectiveTickSize)
        : PriceMath.ToTicks(Math.Max(0m, currentPrice - harvestState.HarvestedPriceHigh), EffectiveTickSize);

    private static string DeterminePostHarvestOutcome(int continuationTicks, int consolidationRangeTicks, int pullbackTicks, int reversalTicks)
    {
        if (reversalTicks >= 6)
        {
            return "reversal";
        }

        if (pullbackTicks >= 2)
        {
            return "pullback";
        }

        if (continuationTicks >= 3 && consolidationRangeTicks <= 8)
        {
            return "continuation";
        }

        return consolidationRangeTicks <= 8 ? "consolidation" : "mixed";
    }

    private static void LogInfoLocal(string message) => Debug.WriteLine($"[ATAS-Collector][INFO] {message}");

    private static void LogWarnLocal(string message) => Debug.WriteLine($"[ATAS-Collector][WARN] {message}");

    private static void ObserveBackgroundTask(Task? task, string operationName, Action? onFault = null)
    {
        if (task is null)
        {
            return;
        }

        task.ContinueWith(
            continuation =>
            {
                try
                {
                    onFault?.Invoke();
                }
                catch (Exception callbackEx)
                {
                    LogWarnLocal($"{operationName} fault callback failed: {callbackEx.Message}");
                }

                var exception = continuation.Exception?.GetBaseException();
                if (exception is null)
                {
                    LogWarnLocal($"{operationName} faulted without an exception payload.");
                    return;
                }

                LogWarnLocal($"{operationName} faulted: {exception.GetType().Name}: {exception.Message}");
            },
            CancellationToken.None,
            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
            TaskScheduler.Default);
    }

    private void StartBackfillPoller()
    {
        StopBackfillPoller();
        _backfillCts = new CancellationTokenSource();
        _backfillPollerTask = Task.Run(() => BackfillPollerLoopAsync(_backfillCts.Token));
        ObserveBackgroundTask(_backfillPollerTask, "BackfillPollerLoopAsync");
        LogInfoLocal("Backfill poller started.");
    }

    private void StopBackfillPoller()
    {
        if (_backfillCts is not null)
        {
            _backfillCts.Cancel();
            try
            {
                _backfillPollerTask?.Wait(TimeSpan.FromSeconds(3));
            }
            catch (AggregateException)
            {
            }
            _backfillCts.Dispose();
            _backfillCts = null;
            _backfillPollerTask = null;
        }
    }

    private async Task BackfillPollerLoopAsync(CancellationToken ct)
    {
        var pollInterval = TimeSpan.FromSeconds(Math.Max(1, Math.Min(30, BackfillPollIntervalSeconds)));
        while (!ct.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(pollInterval, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            try
            {
                await PollBackfillCommandAsync(ct).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                LogWarnLocal($"BackfillPollerLoopAsync error: {ex.Message}");
            }
        }
    }

    private async Task PollBackfillCommandAsync(CancellationToken ct)
    {
        if (_transport is null)
        {
            return;
        }

        var chartIdentity = ResolveChartIdentity();
        var instrumentSymbol = chartIdentity.DisplaySymbol;

        var dispatchResponse = await _transport.PollBackfillCommandAsync(
            instrumentSymbol,
            chartIdentity.ChartInstanceId,
            chartIdentity.ContractSymbol,
            chartIdentity.RootSymbol,
            ct).ConfigureAwait(false);

        if (dispatchResponse?.Request is null)
        {
            return;
        }

        await HandleBackfillCommandAsync(dispatchResponse.Request, chartIdentity, ct).ConfigureAwait(false);
    }

    private async Task HandleBackfillCommandAsync(
        AdapterBackfillCommandPayload command,
        ChartIdentity chartIdentity,
        CancellationToken ct)
    {
        lock (_inProgressBackfills)
        {
            if (_inProgressBackfills.Contains(command.RequestId))
            {
                LogWarnLocal($"Backfill {command.RequestId} already in progress, skipping.");
                return;
            }
            _inProgressBackfills.Add(command.RequestId);
        }

        LogInfoLocal($"Processing backfill {command.RequestId}: {command.RequestedRanges.Count} ranges, bars={command.RequestHistoryBars}, footprint={command.RequestHistoryFootprint}.");

        var (historyBarsSucceeded, historyFootprintSucceeded, historyBarsDiagnostic) = await ExecuteBackfillRangesAsync(command, chartIdentity, ct).ConfigureAwait(false);

        lock (_inProgressBackfills)
        {
            _inProgressBackfills.Remove(command.RequestId);
        }

        await AcknowledgeBackfillAsync(
            command,
            chartIdentity,
            historyBarsSucceeded,
            historyFootprintSucceeded,
            historyBarsDiagnostic,
            ct).ConfigureAwait(false);
    }

    private async Task<(bool HistoryBarsSucceeded, bool HistoryFootprintSucceeded, string? HistoryBarsDiagnostic)> ExecuteBackfillRangesAsync(
        AdapterBackfillCommandPayload command,
        ChartIdentity chartIdentity,
        CancellationToken ct)
    {
        if (_transport is null)
        {
            return (!command.RequestHistoryBars, !command.RequestHistoryFootprint, null);
        }

        ct.ThrowIfCancellationRequested();
        var timeContext = ResolveTimeContext();
        var resolvedRangesUtc = ResolveBackfillRanges(command);
        if (resolvedRangesUtc.Count == 0)
        {
            LogWarnLocal($"ExecuteBackfillRangesAsync: no usable ranges resolved for {command.RequestId}.");
            return (!command.RequestHistoryBars, !command.RequestHistoryFootprint, "history_bars=no_usable_ranges");
        }

        var historyBarsSucceeded = !command.RequestHistoryBars;
        string? historyBarsDiagnostic = null;
        if (command.RequestHistoryBars)
        {
            var historyBarsResult = await ExportHistoryBarsChunkAsync(command, resolvedRangesUtc, chartIdentity, timeContext, ct).ConfigureAwait(false);
            historyBarsSucceeded = historyBarsResult.Succeeded;
            historyBarsDiagnostic = historyBarsResult.Diagnostic;
        }

        var historyFootprintSucceeded = !command.RequestHistoryFootprint;
        if (command.RequestHistoryFootprint)
        {
            historyFootprintSucceeded = await ExportHistoryFootprintChunkAsync(command, resolvedRangesUtc, chartIdentity, timeContext, ct).ConfigureAwait(false);
        }

        return (historyBarsSucceeded, historyFootprintSucceeded, historyBarsDiagnostic);
    }

    private async Task<HistoryBarsBackfillExportResult> ExportHistoryBarsChunkAsync(
        AdapterBackfillCommandPayload command,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> targetRangesUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext,
        CancellationToken ct)
    {
        if (_transport is null)
        {
            return new HistoryBarsBackfillExportResult(false, "history_bars=transport_unavailable");
        }

        ct.ThrowIfCancellationRequested();
        List<HistoryBarPayload> loadedBars;
        lock (_sync)
        {
            loadedBars = ExportLoadedHistoryBarsSnapshot();
        }

        var loadedWindow = loadedBars.Count == 0
            ? "none"
            : $"{loadedBars[0].StartedAt:O}..{loadedBars[^1].StartedAt:O}";
        var filteredBars = FilterHistoryBarsByRanges(loadedBars, targetRangesUtc);
        if (filteredBars.Count == 0)
        {
            var noMatchDiagnostic = $"history_bars=no_match loaded={loadedBars.Count} loaded_window={loadedWindow} requested={FormatBackfillRanges(targetRangesUtc)}";
            LogWarnLocal($"ExportHistoryBarsChunkAsync: {noMatchDiagnostic} request_id={command.RequestId}.");
            return new HistoryBarsBackfillExportResult(false, noMatchDiagnostic);
        }

        var emittedAtUtc = DateTime.UtcNow;
        var payloads = BuildHistoryBarsChunks(
            filteredBars,
            emittedAtUtc,
            chartIdentity,
            timeContext,
            Math.Min(DefaultHistoryBarsChunkBars, DirectBackfillHistoryBarsChunkBars));
        var delivered = await _transport.SendHistoryBarsDirectAsync(payloads, ct).ConfigureAwait(false);
        var coverageComplete = CoversRequestedRanges(filteredBars, targetRangesUtc, out var coverageDetail);
        var diagnosticStatus = delivered
            ? (coverageComplete ? "complete" : "partial")
            : "delivery_failed";
        var diagnostic =
            $"history_bars={diagnosticStatus} matched={filteredBars.Count} chunks={payloads.Count} coverage={coverageDetail} filtered_window={filteredBars[0].StartedAt:O}..{filteredBars[^1].StartedAt:O} requested={FormatBackfillRanges(targetRangesUtc)}";

        if (!delivered)
        {
            LogWarnLocal($"ExportHistoryBarsChunkAsync: {diagnostic} request_id={command.RequestId}.");
            return new HistoryBarsBackfillExportResult(false, diagnostic);
        }

        if (!coverageComplete)
        {
            LogWarnLocal($"ExportHistoryBarsChunkAsync: {diagnostic} request_id={command.RequestId}.");
            return new HistoryBarsBackfillExportResult(false, diagnostic);
        }

        LogInfoLocal(
            $"ExportHistoryBarsChunkAsync: {diagnostic} request_id={command.RequestId}.");
        return new HistoryBarsBackfillExportResult(true, diagnostic);
    }

    private Task<bool> ExportHistoryFootprintChunkAsync(
        AdapterBackfillCommandPayload command,
        IReadOnlyList<(DateTime StartUtc, DateTime EndUtc)> targetRangesUtc,
        ChartIdentity chartIdentity,
        ResolvedTimeContext timeContext,
        CancellationToken ct)
    {
        if (_transport is null)
        {
            return Task.FromResult(false);
        }

        ct.ThrowIfCancellationRequested();
        List<HistoryFootprintBarPayload> loadedBars;
        lock (_sync)
        {
            loadedBars = ExportLoadedHistoryFootprintSnapshot();
        }

        var filteredBars = FilterHistoryFootprintBarsByRanges(loadedBars, targetRangesUtc);
        if (filteredBars.Count == 0)
        {
            LogWarnLocal($"ExportHistoryFootprintChunkAsync: no loaded footprint bars matched backfill {command.RequestId}.");
            return Task.FromResult(false);
        }

        LogResolvedContext(chartIdentity, timeContext);
        var emittedAtUtc = DateTime.UtcNow;
        var payloads = BuildHistoryFootprintChunks(filteredBars, emittedAtUtc, chartIdentity, timeContext);
        var enqueuedAny = false;
        foreach (var payload in payloads)
        {
            ct.ThrowIfCancellationRequested();
            if (!_transport.TryEnqueueHistoryFootprint(payload))
            {
                LogWarnLocal($"ExportHistoryFootprintChunkAsync: history footprint queue rejected {payload.MessageId}.");
                return Task.FromResult(false);
            }

            enqueuedAny = true;
        }

        LogInfoLocal(
            $"ExportHistoryFootprintChunkAsync: matched {filteredBars.Count} footprint bars across {targetRangesUtc.Count} ranges for {command.RequestId}; observed_window_start_utc={filteredBars[0].StartedAt:O} observed_window_end_utc={filteredBars[^1].EndedAt:O}.");
        return Task.FromResult(enqueuedAny);
    }

    private async Task AcknowledgeBackfillAsync(
        AdapterBackfillCommandPayload command,
        ChartIdentity chartIdentity,
        bool historyBarsSucceeded,
        bool historyFootprintSucceeded,
        string? historyBarsDiagnostic,
        CancellationToken ct)
    {
        if (_transport is null)
        {
            return;
        }

        var timeContext = ResolveTimeContext();
        DateTime? latestLoadedBarStartedAtUtc = null;
        lock (_sync)
        {
            if (TryGetLatestCompletedBarStartedAtUtc(DateTime.UtcNow, out var completedBarStartedAtUtc))
            {
                latestLoadedBarStartedAtUtc = completedBarStartedAtUtc;
            }
        }

        var ack = new AdapterBackfillAcknowledgeRequestPayload
        {
            RequestId = command.RequestId,
            CacheKey = command.CacheKey,
            ChartInstanceId = chartIdentity.ChartInstanceId,
            InstrumentSymbol = command.InstrumentSymbol,
            AcknowledgedAt = DateTime.UtcNow,
            AcknowledgedHistoryBars = historyBarsSucceeded,
            AcknowledgedHistoryFootprint = historyFootprintSucceeded,
            LatestLoadedBarStartedAt = latestLoadedBarStartedAtUtc.HasValue
                ? CollectorMetadataResolver.ToReferenceTime(latestLoadedBarStartedAtUtc.Value, timeContext).DateTime
                : (DateTime?)null,
            LatestLoadedBarStartedAtUtc = latestLoadedBarStartedAtUtc,
            InstrumentTimezoneValue = timeContext.InstrumentTimezoneValue,
            InstrumentTimezoneSource = timeContext.InstrumentTimezoneSource,
            ChartDisplayTimezoneMode = timeContext.ChartDisplayTimezoneMode,
            ChartDisplayTimezoneSource = timeContext.ChartDisplayTimezoneSource,
            ChartDisplayTimezoneName = timeContext.ChartDisplayTimezoneName,
            ChartDisplayUtcOffsetMinutes = timeContext.ChartDisplayUtcOffsetMinutes,
            CollectorLocalTimezoneName = timeContext.CollectorLocalTimezoneName,
            CollectorLocalUtcOffsetMinutes = timeContext.CollectorLocalUtcOffsetMinutes,
            TimestampBasis = timeContext.TimestampBasis,
            TimezoneCaptureConfidence = timeContext.TimezoneCaptureConfidence,
            Note = BuildBackfillAckNote((!command.RequestHistoryBars || historyBarsSucceeded)
                && (!command.RequestHistoryFootprint || historyFootprintSucceeded)
                ? "backfill_complete"
                : "backfill_partial_failure", historyBarsDiagnostic),
        };

        var sent = await _transport.SendBackfillAckAsync(ack, ct).ConfigureAwait(false);
        if (sent)
        {
            LogInfoLocal(
                $"AcknowledgeBackfillAsync: acknowledged {command.RequestId} cache_key={command.CacheKey} (history_bars={historyBarsSucceeded}, history_footprint={historyFootprintSucceeded}).");
        }
        else
        {
            LogWarnLocal($"AcknowledgeBackfillAsync: failed to acknowledge {command.RequestId}.");
        }
    }

    private sealed record SessionProfile(
        int RegularSessionOpenLocalMinutes,
        int RegularSessionCloseLocalMinutes,
        int TradingDayRollLocalMinutes,
        string Source);

    private sealed record HistoryBarsBackfillExportResult(bool Succeeded, string Diagnostic);

    private sealed class DriveState
    {
        private DriveState()
        {
        }

        public string DriveId { get; private init; } = string.Empty;
        public CollectorSide Side { get; private init; }
        public DateTime StartedAtUtc { get; private init; }
        public DateTime LastObservedAtUtc { get; private set; }
        public decimal StartPrice { get; private init; }
        public decimal High { get; private set; }
        public decimal Low { get; private set; }
        public int AggressiveVolume { get; private set; }
        public int NetDelta { get; private set; }
        public int TradeCount { get; private set; }

        public static DriveState Start(DateTime eventTimeUtc, decimal price, CollectorSide side, int size)
        {
            var drive = new DriveState
            {
                DriveId = $"drive-{eventTimeUtc:yyyyMMddHHmmssfff}",
                Side = side,
                StartedAtUtc = eventTimeUtc,
                LastObservedAtUtc = eventTimeUtc,
                StartPrice = price,
                High = price,
                Low = price,
            };
            drive.Observe(eventTimeUtc, price, size);
            return drive;
        }

        public void Observe(DateTime eventTimeUtc, decimal price, int size)
        {
            LastObservedAtUtc = eventTimeUtc;
            High = Math.Max(High, price);
            Low = Math.Min(Low, price);
            AggressiveVolume += size;
            TradeCount += 1;
            NetDelta += Side == CollectorSide.Buy ? size : -size;
        }

        public InitiativeDrivePayload ToPayload(decimal tickSize) => new()
        {
            DriveId = DriveId,
            Side = Side.ToPayloadString(),
            StartedAt = StartedAtUtc,
            PriceLow = (double)Low,
            PriceHigh = (double)High,
            AggressiveVolume = AggressiveVolume,
            NetDelta = NetDelta,
            TradeCount = TradeCount,
            ConsumedPriceLevels = Math.Max(1, PriceMath.ToTicks(Math.Abs(High - Low), tickSize)),
            PriceTravelTicks = Side == CollectorSide.Buy ? PriceMath.ToTicks(Math.Max(0m, High - StartPrice), tickSize) : PriceMath.ToTicks(Math.Max(0m, StartPrice - Low), tickSize),
            MaxCounterMoveTicks = 0,
            ContinuationSeconds = Math.Max(1, (int)(LastObservedAtUtc - StartedAtUtc).TotalSeconds),
        };
    }
}
