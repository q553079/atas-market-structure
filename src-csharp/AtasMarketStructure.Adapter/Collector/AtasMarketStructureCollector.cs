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
[Description("Streams compact continuous state and trigger bursts to the local ATAS market structure service.")]
[Category("Order Flow")]
internal sealed class AtasMarketStructureCollectorFull : Indicator
{
    private readonly object _sync = new();
    private readonly ValueDataSeries _collectorHeartbeat = new("CollectorHeartbeat") { VisualType = VisualMode.Hide };
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

    public AtasMarketStructureCollectorFull()
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
    public string SymbolOverride { get; set; } = "NQM6";

    [Display(Name = "Venue", GroupName = "2. Instrument", Order = 20)]
    public string Venue { get; set; } = "CME";

    [Display(Name = "Currency", GroupName = "2. Instrument", Order = 30)]
    public string Currency { get; set; } = "USD";

    [Display(Name = "Tick Size Override", GroupName = "2. Instrument", Order = 40)]
    public decimal TickSizeOverride { get; set; } = 0.25m;

    [Display(Name = "Continuous Cadence Ms", GroupName = "3. Performance", Order = 10)]
    public int ContinuousCadenceMilliseconds { get; set; } = 1000;

    [Display(Name = "Queue Limit", GroupName = "3. Performance", Order = 20)]
    public int QueueLimit { get; set; } = 256;

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
        }

        SubscribeToTimer(TimeSpan.FromMilliseconds(Math.Max(250, ContinuousCadenceMilliseconds)), OnTimerTick);
        if (EnableMarketByOrders)
        {
            _ = SubscribeMarketByOrderData();
        }
    }

    protected override void OnDispose()
    {
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
            var timeUtc = candle.Time.Kind == DateTimeKind.Utc ? candle.Time : candle.Time.ToUniversalTime();
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

        _gapReference = new GapReferencePayload
        {
            GapId = $"gap-{DetermineTradingDate(observedAtUtc)}",
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

        _transport.TryEnqueueContinuousState(new ContinuousStatePayload
        {
            MessageId = $"adapter-state-{nowUtc:yyyyMMddHHmmssfff}",
            EmittedAt = nowUtc,
            ObservedWindowStart = _tradeAccumulator.WindowStartedAtUtc,
            ObservedWindowEnd = nowUtc,
            Source = new SourceEnvelope { System = "ATAS", InstanceId = Environment.MachineName, AdapterVersion = "0.5.0-alpha" },
            Instrument = new InstrumentEnvelope { Symbol = SymbolOverride, Venue = Venue, TickSize = (double)EffectiveTickSize, Currency = Currency },
            SessionContext = new SessionContextPayload
            {
                SessionCode = DetermineSessionCode(nowUtc),
                TradingDate = DetermineTradingDate(nowUtc),
                IsRthOpen = IsRegularSession(nowUtc),
                PriorRthClose = (double)PriorRthClose,
                PriorRthHigh = (double)PriorRthHigh,
                PriorRthLow = (double)PriorRthLow,
                PriorValueAreaLow = NullIfZero(PriorValueAreaLow),
                PriorValueAreaHigh = NullIfZero(PriorValueAreaHigh),
                PriorPointOfControl = NullIfZero(PriorPointOfControl),
                OvernightHigh = NullIfZero(OvernightHigh),
                OvernightLow = NullIfZero(OvernightLow),
                OvernightMid = OvernightHigh > 0m && OvernightLow > 0m ? (double)((OvernightHigh + OvernightLow) / 2m) : null,
            },
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
        });

        _tradeAccumulator.Reset(nowUtc);
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
        _transport.TryEnqueueTriggerBurst(new TriggerBurstPayload
        {
            MessageId = $"adapter-burst-{triggeredAtUtc:yyyyMMddHHmmssfff}",
            EmittedAt = DateTime.UtcNow,
            ObservedWindowStart = triggeredAtUtc.AddSeconds(-Math.Max(1, BurstLookbackSeconds)),
            ObservedWindowEnd = DateTime.UtcNow,
            Source = new SourceEnvelope { System = "ATAS", InstanceId = Environment.MachineName, AdapterVersion = "0.5.0-alpha" },
            Instrument = new InstrumentEnvelope { Symbol = SymbolOverride, Venue = Venue, TickSize = (double)EffectiveTickSize, Currency = Currency },
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
        });
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

    private string DetermineSessionCode(DateTime nowUtc)
    {
        if (!string.IsNullOrWhiteSpace(SessionCodeOverride))
        {
            return SessionCodeOverride.Trim().ToLowerInvariant();
        }

        return nowUtc.Hour switch
        {
            < 7 => "asia",
            < 13 => "europe",
            < 14 => "us_premarket",
            < 21 => "us_regular",
            _ => "us_after_hours",
        };
    }

    private static bool IsRegularSession(DateTime nowUtc) => nowUtc.Hour >= 14 && nowUtc.Hour < 21;

    private static string DetermineTradingDate(DateTime nowUtc) => nowUtc.ToString("yyyy-MM-dd");

    private decimal EffectiveTickSize => TickSizeOverride > 0m ? TickSizeOverride : 0.25m;

    private static DateTime ToUtc(DateTime value) => value.Kind == DateTimeKind.Utc ? value : value.ToUniversalTime();

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
