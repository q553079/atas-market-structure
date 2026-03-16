using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.DataFeedsCore;
using ATAS.Indicators;
using AtasMarketStructure.Adapter.Contracts;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ATAS Market Structure Collector")]
[Description("Visible collector shell that streams a minimal continuous-state heartbeat to the local service.")]
[Category("Order Flow")]
public sealed class AtasMarketStructureCollector : Indicator
{
    private const string CollectorVersion = "0.10.0-shell";
    private static readonly string[][] SymbolCandidatePaths =
    {
        new[] { "Instrument" },
        new[] { "InstrumentInfo", "Instrument" },
        new[] { "DataProvider", "Instrument" },
        new[] { "InstrumentInfo", "Instrument", "Instrument" },
        new[] { "Security", "Name" },
        new[] { "Security", "Symbol" },
        new[] { "SourceDataSeries", "SourceName" },
        new[] { "SourceDataSeries", "FullName" },
        new[] { "DataProvider", "Instrument", "Name" },
        new[] { "DataProvider", "Instrument", "Symbol" },
    };
    private static readonly string[][] TickSizeCandidatePaths =
    {
        new[] { "TickSize" },
        new[] { "InstrumentInfo", "TickSize" },
        new[] { "InstrumentInfo", "Instrument", "TickSize" },
        new[] { "Instrument", "TickSize" },
        new[] { "Security", "TickSize" },
        new[] { "SourceDataSeries", "TickSize" },
        new[] { "DataProvider", "Instrument", "TickSize" },
    };
    private static readonly HashSet<string> InvalidSymbolCandidates = new(StringComparer.OrdinalIgnoreCase)
    {
        "BARS",
        "BARS(TRUE)",
        "BARS,FALSE",
        "CLOSE",
        "OPEN",
        "HIGH",
        "LOW",
        "BID",
        "ASK",
        "VOLUME",
        "DELTA",
        "DOM",
        "MBO",
        "CVD",
        "EMA",
        "VWAP",
        "TWAP",
        "PRICE",
        "VALUE",
        "SOURCE",
        "SERIES",
        "INDICATOR",
        "CLUSTER",
        "FOOTPRINT",
        "PROPERTIES",
        "CUSTOM",
        "TRUE",
        "FALSE",
    };
    private readonly object _sync = new();
    private readonly ValueDataSeries _heartbeat = new("CollectorShellHeartbeat") { VisualType = VisualMode.Hide };
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
    private decimal? _lastPrice;
    private decimal? _bestBid;
    private decimal? _bestAsk;
    private decimal? _sessionOpenPrice;
    private decimal? _ema20;
    private decimal _openingRangeHigh = decimal.MinValue;
    private decimal _openingRangeLow = decimal.MaxValue;
    private DateTime? _sessionStartUtc;
    private int _lastEmaBar = -1;
    private DateTime _lastHeartbeatUtc;
    private DateTime _lastHistorySyncUtc;
    private DateTime _lastHistoryFootprintSyncUtc;
    private DateTime _lastDepthSnapshotUtc;
    private DateTime? _lastDepthSnapshotSuccessUtc;
    private DateTime? _depthCoverageStartedUtc;
    private int _lastDepthSnapshotLevelCount;
    private int _latestObservedBarIndex = -1;
    private int _lastHistoryBarCount;
    private DateTime? _lastHistoryBarStartedAt;
    private int _localSequence;
    private string? _chartInstanceId;

    public AtasMarketStructureCollector()
        : base(true)
    {
        DataSeries.Add(_heartbeat);
    }

    [Display(Name = "Enabled", GroupName = "1. Collector", Order = 10)]
    public bool Enabled { get; set; } = true;

    [Display(Name = "Adapter Version", GroupName = "1. Collector", Order = 15)]
    [ReadOnly(true)]
    public string AdapterVersion => CollectorVersion;

    [Display(Name = "Chart Instance Id", GroupName = "1. Collector", Order = 17)]
    [ReadOnly(true)]
    public string ChartInstanceId => ResolveChartInstanceId();

    [Display(Name = "Tracked Liquidity Count", GroupName = "1. Collector", Order = 18)]
    [ReadOnly(true)]
    public int TrackedLiquidityCount
    {
        get
        {
            lock (_sync)
            {
                return _liquidityTracks.Count(track => track.Value.CurrentSize > 0 && track.Value.Status == "active");
            }
        }
    }

    [Display(Name = "Depth Snapshot Levels", GroupName = "1. Collector", Order = 19)]
    [ReadOnly(true)]
    public int DepthSnapshotLevelCount
    {
        get
        {
            lock (_sync)
            {
                return _lastDepthSnapshotLevelCount;
            }
        }
    }

    [Display(Name = "Depth Snapshot Last UTC", GroupName = "1. Collector", Order = 20)]
    [ReadOnly(true)]
    public string DepthSnapshotLastUtc
    {
        get
        {
            lock (_sync)
            {
                return _lastDepthSnapshotSuccessUtc?.ToString("yyyy-MM-dd HH:mm:ss'Z'") ?? string.Empty;
            }
        }
    }

    [Display(Name = "Best Bid", GroupName = "1. Collector", Order = 21)]
    [ReadOnly(true)]
    public decimal? BestBidDisplay
    {
        get
        {
            lock (_sync)
            {
                return _bestBid;
            }
        }
    }

    [Display(Name = "Best Ask", GroupName = "1. Collector", Order = 22)]
    [ReadOnly(true)]
    public decimal? BestAskDisplay
    {
        get
        {
            lock (_sync)
            {
                return _bestAsk;
            }
        }
    }

    [Display(Name = "Service Base URL", GroupName = "1. Collector", Order = 30)]
    public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8080";

    [Display(Name = "Continuous Endpoint", GroupName = "1. Collector", Order = 40)]
    public string ContinuousEndpoint { get; set; } = "/api/v1/adapter/continuous-state";

    [Display(Name = "History Bars Endpoint", GroupName = "1. Collector", Order = 45)]
    public string HistoryBarsEndpoint { get; set; } = "/api/v1/adapter/history-bars";

    [Display(Name = "History Footprint Endpoint", GroupName = "1. Collector", Order = 47)]
    public string HistoryFootprintEndpoint { get; set; } = "/api/v1/adapter/history-footprint";

    [Display(Name = "Trigger Endpoint", GroupName = "1. Collector", Order = 50)]
    public string TriggerEndpoint { get; set; } = "/api/v1/adapter/trigger-burst";

    [Display(Name = "Use Symbol Override", GroupName = "2. Instrument", Order = 10)]
    public bool UseSymbolOverride { get; set; }

    [Display(Name = "Detected Symbol", GroupName = "2. Instrument", Order = 15)]
    [ReadOnly(true)]
    public string DetectedSymbol => ResolveDetectedSymbol() ?? string.Empty;

    [Display(Name = "Effective Symbol", GroupName = "2. Instrument", Order = 18)]
    [ReadOnly(true)]
    public string EffectiveSymbol => ResolveEffectiveSymbol();

    [Display(Name = "Symbol Override", GroupName = "2. Instrument", Order = 20)]
    public string SymbolOverride { get; set; } = string.Empty;

    [Display(Name = "Use Tick Size Override", GroupName = "2. Instrument", Order = 30)]
    public bool UseTickSizeOverride { get; set; }

    [Display(Name = "Detected Tick Size", GroupName = "2. Instrument", Order = 35)]
    [ReadOnly(true)]
    public decimal DetectedTickSize => ResolveDetectedTickSize();

    [Display(Name = "Effective Tick Size", GroupName = "2. Instrument", Order = 38)]
    [ReadOnly(true)]
    public decimal EffectiveTickSizeDisplay => EffectiveTickSize;

    [Display(Name = "Tick Size Override", GroupName = "2. Instrument", Order = 40)]
    public decimal TickSizeOverride { get; set; } = 0.25m;

    [Display(Name = "Venue", GroupName = "2. Instrument", Order = 50)]
    public string Venue { get; set; } = "CME";

    [Display(Name = "Currency", GroupName = "2. Instrument", Order = 60)]
    public string Currency { get; set; } = "USD";

    [Display(Name = "Queue Limit", GroupName = "3. Performance", Order = 10)]
    public int QueueLimit { get; set; } = 64;

    [Display(Name = "Continuous Cadence Ms", GroupName = "3. Performance", Order = 20)]
    public int ContinuousCadenceMilliseconds { get; set; } = 1000;

    [Display(Name = "Burst Lookback Seconds", GroupName = "4. Trigger Burst", Order = 10)]
    public int BurstLookbackSeconds { get; set; } = 30;

    [Display(Name = "History Sync Cadence Seconds", GroupName = "4. Trigger Burst", Order = 20)]
    public int HistorySyncCadenceSeconds { get; set; } = 60;

    [Display(Name = "History Footprint Sync Minutes", GroupName = "4. Trigger Burst", Order = 25)]
    public int HistoryFootprintSyncMinutes { get; set; } = 15;

    [Display(Name = "History Max Bars", GroupName = "4. Trigger Burst", Order = 30)]
    public int HistoryMaxBars { get; set; } = 12000;

    [Display(Name = "History Footprint Chunk Bars", GroupName = "4. Trigger Burst", Order = 35)]
    public int HistoryFootprintChunkBars { get; set; } = 240;

    [Display(Name = "Significant Liquidity Min Size", GroupName = "5. Liquidity", Order = 10)]
    public int SignificantLiquidityMinSize { get; set; } = 80;

    [Display(Name = "Significant Liquidity Max Distance Ticks", GroupName = "5. Liquidity", Order = 20)]
    public int SignificantLiquidityMaxDistanceTicks { get; set; } = 64;

    [Display(Name = "Near Touch Distance Ticks", GroupName = "5. Liquidity", Order = 30)]
    public int NearTouchDistanceTicks { get; set; } = 2;

    [Display(Name = "Strong Replenishment Count", GroupName = "5. Liquidity", Order = 40)]
    public int StrongReplenishmentCount { get; set; } = 2;

    [Display(Name = "Drive Min Net Delta", GroupName = "6. Drive", Order = 10)]
    public int DriveMinNetDelta { get; set; } = 60;

    [Display(Name = "Drive Min Travel Ticks", GroupName = "6. Drive", Order = 20)]
    public int DriveMinTravelTicks { get; set; } = 8;

    [Display(Name = "Drive Merge Gap Seconds", GroupName = "6. Drive", Order = 30)]
    public int DriveMergeGapSeconds { get; set; } = 6;

    [Display(Name = "Measured Reference Ticks", GroupName = "7. Measured Move", Order = 10)]
    public int MeasuredReferenceTicks { get; set; } = 8;

    [Display(Name = "Opening Range Minutes", GroupName = "8. Structure", Order = 10)]
    public int OpeningRangeMinutes { get; set; } = 30;

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

    protected override void OnInitialize()
    {
        lock (_sync)
        {
            _transport?.Dispose();
            _transport = new BufferedHttpAdapterTransport(
                new Uri(ServiceBaseUrl, UriKind.Absolute),
                ContinuousEndpoint,
                HistoryBarsEndpoint,
                HistoryFootprintEndpoint,
                TriggerEndpoint,
                QueueLimit,
                _ => { },
                _ => { });
            _tradeAccumulator = new TradeAccumulatorState();
            _currentSecond = null;
            _driveState = null;
            _harvestState = null;
            _gapReference = null;
            _liquidityTracks.Clear();
            _lastTriggerByKey.Clear();
            _localSequence = 0;
            _sessionOpenPrice = null;
            _ema20 = null;
            _openingRangeHigh = decimal.MinValue;
            _openingRangeLow = decimal.MaxValue;
            _sessionStartUtc = null;
            _lastEmaBar = -1;
            _lastHeartbeatUtc = DateTime.UtcNow;
            _lastHistorySyncUtc = DateTime.MinValue;
            _lastHistoryFootprintSyncUtc = DateTime.MinValue;
            _lastDepthSnapshotUtc = DateTime.MinValue;
            _lastDepthSnapshotSuccessUtc = null;
            _depthCoverageStartedUtc = null;
            _lastDepthSnapshotLevelCount = 0;
            _latestObservedBarIndex = -1;
            _lastHistoryBarCount = 0;
            _lastHistoryBarStartedAt = null;
            _chartInstanceId = null;
        }

        SubscribeToTimer(TimeSpan.FromMilliseconds(Math.Max(250, ContinuousCadenceMilliseconds)), OnTimerTick);
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
        lock (_sync)
        {
            var candle = GetCandle(bar);
            var close = candle.Close;
            var high = candle.High;
            var low = candle.Low;
            var observedAtUtc = ToUtc(candle.Time);

            _heartbeat[bar] = Enabled ? close : 0m;
            _latestObservedBarIndex = Math.Max(_latestObservedBarIndex, bar);
            _lastPrice = close;
            _sessionStartUtc ??= observedAtUtc;
            _sessionOpenPrice ??= candle.Open;
            if ((observedAtUtc - _sessionStartUtc.Value).TotalMinutes <= Math.Max(1, OpeningRangeMinutes))
            {
                _openingRangeHigh = _openingRangeHigh == decimal.MinValue ? high : Math.Max(_openingRangeHigh, high);
                _openingRangeLow = _openingRangeLow == decimal.MaxValue ? low : Math.Min(_openingRangeLow, low);
            }

            UpdateEma(bar, close);
            UpdateGapReference(observedAtUtc, close);
            EnsureSecondAccumulator(observedAtUtc, close);
            if (_harvestState is not null)
            {
                _harvestState.HighestAfterCompletion = Math.Max(_harvestState.HighestAfterCompletion, high);
                _harvestState.LowestAfterCompletion = Math.Min(_harvestState.LowestAfterCompletion, low);
            }
        }
    }

    protected override void OnBestBidAskChanged(MarketDataArg marketData)
    {
        lock (_sync)
        {
            if (marketData.IsBid)
            {
                _bestBid = marketData.Price;
            }
            else if (marketData.IsAsk)
            {
                _bestAsk = marketData.Price;
            }

            EnsureSecondAccumulator(ToUtc(marketData.Time), marketData.Price);
            _currentSecond?.ObserveBestBid(_bestBid);
            _currentSecond?.ObserveBestAsk(_bestAsk);
        }
    }

    protected override void MarketDepthChanged(MarketDataArg marketData)
    {
        lock (_sync)
        {
            ProcessDisplayedLiquidity(
                ToUtc(marketData.Time),
                marketData.Price,
                DecimalToInt(marketData.Volume),
                AtasReflection.ReadSide(marketData),
                null);
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

    private void OnTimerTick()
    {
        lock (_sync)
        {
            if (!Enabled || _transport is null || _lastPrice is null)
            {
                return;
            }

            var nowUtc = DateTime.UtcNow;
            var chartInstanceId = ResolveChartInstanceId();
            PollDisplayedLiquiditySnapshot(nowUtc);
            FinalizeCurrentSecond(nowUtc);
            if ((nowUtc - _lastHeartbeatUtc).TotalMilliseconds < Math.Max(250, ContinuousCadenceMilliseconds) - 25)
            {
                return;
            }

            var lastPrice = _lastPrice.Value;
            var recentSeconds = _secondBuffer.Snapshot(nowUtc.AddSeconds(-Math.Max(2, BurstLookbackSeconds)), nowUtc);
            var activeLiquidityTracks = _liquidityTracks.Values
                .Where(item => item.CurrentSize > 0 && item.Status == "active")
                .OrderByDescending(item => item.HeatScore)
                .ToList();
            _transport.TryEnqueueContinuousState(new ContinuousStatePayload
            {
                MessageId = $"collector-shell-{nowUtc:yyyyMMddHHmmssfff}",
                EmittedAt = nowUtc,
                ObservedWindowStart = _lastHeartbeatUtc == default ? nowUtc.AddSeconds(-1) : _lastHeartbeatUtc,
                ObservedWindowEnd = nowUtc,
                Source = new SourceEnvelope
                {
                    System = "ATAS",
                    InstanceId = Environment.MachineName,
                    ChartInstanceId = chartInstanceId,
                    AdapterVersion = CollectorVersion,
                },
                Instrument = new InstrumentEnvelope
                {
                    Symbol = ResolveEffectiveSymbol(),
                    Venue = Venue,
                    TickSize = (double)EffectiveTickSize,
                    Currency = Currency,
                },
                SessionContext = new SessionContextPayload
                {
                    SessionCode = DetermineSessionCode(nowUtc),
                    TradingDate = DetermineTradingDate(nowUtc),
                    IsRthOpen = nowUtc.Hour >= 14 && nowUtc.Hour < 21,
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
                    BestBid = _bestBid is null ? null : (double)_bestBid.Value,
                    BestAsk = _bestAsk is null ? null : (double)_bestAsk.Value,
                    LocalRangeLow = recentSeconds.Count == 0 ? (double)lastPrice : recentSeconds.Min(item => item.Low),
                    LocalRangeHigh = recentSeconds.Count == 0 ? (double)lastPrice : recentSeconds.Max(item => item.High),
                    OpeningRangeLow = _openingRangeLow == decimal.MaxValue ? null : (double)_openingRangeLow,
                    OpeningRangeHigh = _openingRangeHigh == decimal.MinValue ? null : (double)_openingRangeHigh,
                    OpeningRangeSizeTicks = _openingRangeLow == decimal.MaxValue || _openingRangeHigh == decimal.MinValue
                        ? null
                        : PriceMath.ToTicks(_openingRangeHigh - _openingRangeLow, EffectiveTickSize),
                },
                TradeSummary = _tradeAccumulator.ToPayload(),
                DepthCoverage = BuildDepthCoveragePayload(),
                SignificantLiquidity = activeLiquidityTracks
                    .Take(8)
                    .Select(item => item.ToPayload(lastPrice, EffectiveTickSize))
                    .ToList(),
                SamePriceReplenishment = BuildSamePriceReplenishmentPayloads(lastPrice),
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
            _lastHeartbeatUtc = nowUtc;
            TrySyncHistoryBars(nowUtc, chartInstanceId);
            TrySyncHistoryFootprint(nowUtc, chartInstanceId);
        }
    }

    private void TrySyncHistoryBars(DateTime nowUtc, string chartInstanceId)
    {
        if (_latestObservedBarIndex < 0)
        {
            return;
        }

        var bars = BuildLoadedHistoryBars();
        if (bars.Count == 0)
        {
            return;
        }

        var latestBarStartedAt = bars[^1].StartedAt;
        var shouldSync = (nowUtc - _lastHistorySyncUtc).TotalSeconds >= Math.Max(15, HistorySyncCadenceSeconds)
            || bars.Count != _lastHistoryBarCount
            || _lastHistoryBarStartedAt != latestBarStartedAt;
        if (!shouldSync)
        {
            return;
        }

        var timeframe = DetermineHistoryBarTimeframe(bars);
        if (string.IsNullOrWhiteSpace(timeframe))
        {
            return;
        }

        if (_transport!.TryEnqueueHistoryBars(new HistoryBarsPayload
            {
                MessageId = $"collector-history-{nowUtc:yyyyMMddHHmmssfff}",
                EmittedAt = nowUtc,
                ObservedWindowStart = bars[0].StartedAt,
                ObservedWindowEnd = bars[^1].EndedAt,
                Source = new SourceEnvelope
                {
                    System = "ATAS",
                    InstanceId = Environment.MachineName,
                    ChartInstanceId = chartInstanceId,
                    AdapterVersion = CollectorVersion,
                },
                Instrument = new InstrumentEnvelope
                {
                    Symbol = ResolveEffectiveSymbol(),
                    Venue = Venue,
                    TickSize = (double)EffectiveTickSize,
                    Currency = Currency,
                },
                BarTimeframe = timeframe,
                Bars = bars,
            }))
        {
            _lastHistorySyncUtc = nowUtc;
            _lastHistoryBarCount = bars.Count;
            _lastHistoryBarStartedAt = latestBarStartedAt;
        }
    }

    private void TrySyncHistoryFootprint(DateTime nowUtc, string chartInstanceId)
    {
        if (_transport is null || _latestObservedBarIndex < 0)
        {
            return;
        }

        if (_lastHistoryFootprintSyncUtc != DateTime.MinValue
            && (nowUtc - _lastHistoryFootprintSyncUtc).TotalMinutes < Math.Max(1, HistoryFootprintSyncMinutes))
        {
            return;
        }

        var bars = BuildLoadedHistoryFootprintBars();
        if (bars.Count == 0)
        {
            return;
        }

        var chunkSize = Math.Max(50, HistoryFootprintChunkBars);
        var chunkCount = (int)Math.Ceiling((double)bars.Count / chunkSize);
        var batchId = $"history-footprint-{ResolveEffectiveSymbol().ToLowerInvariant()}-{nowUtc:yyyyMMddHHmmss}";
        var timeframe = DetermineHistoryFootprintTimeframe(bars);
        for (var chunkIndex = 0; chunkIndex < chunkCount; chunkIndex++)
        {
            var chunkBars = bars.Skip(chunkIndex * chunkSize).Take(chunkSize).ToList();
            if (chunkBars.Count == 0)
            {
                continue;
            }

            _transport.TryEnqueueHistoryFootprint(new HistoryFootprintPayload
            {
                MessageId = $"{batchId}-chunk-{chunkIndex:D3}",
                EmittedAt = nowUtc,
                ObservedWindowStart = chunkBars[0].StartedAt,
                ObservedWindowEnd = chunkBars[^1].EndedAt,
                Source = new SourceEnvelope
                {
                    System = "ATAS",
                    InstanceId = Environment.MachineName,
                    ChartInstanceId = chartInstanceId,
                    AdapterVersion = CollectorVersion,
                },
                Instrument = new InstrumentEnvelope
                {
                    Symbol = ResolveEffectiveSymbol(),
                    Venue = Venue,
                    TickSize = (double)EffectiveTickSize,
                    Currency = Currency,
                },
                BatchId = batchId,
                BarTimeframe = timeframe,
                ChunkIndex = chunkIndex,
                ChunkCount = chunkCount,
                Bars = chunkBars,
            });
        }

        _lastHistoryFootprintSyncUtc = nowUtc;
    }

    private void ProcessCumulativeTrade(CumulativeTrade trade, bool countVolume)
    {
        var eventTimeUtc = ToUtc(trade.Time);
        var price = trade.Lastprice != 0m ? trade.Lastprice : trade.FirstPrice;
        var size = DecimalToInt(trade.Volume);
        var side = AtasReflection.ReadSide(trade);

        _lastPrice = price;
        _bestBid = trade.NewBid?.Price ?? trade.PreviousBid?.Price ?? _bestBid;
        _bestAsk = trade.NewAsk?.Price ?? trade.PreviousAsk?.Price ?? _bestAsk;

        EnsureSecondAccumulator(eventTimeUtc, price);
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
            EventTime = eventTimeUtc,
            LocalSequence = ++_localSequence,
            Price = (double)price,
            Size = size,
            AggressorSide = side.ToPayloadString(),
            BestBidBefore = DecimalToDouble(trade.PreviousBid?.Price),
            BestAskBefore = DecimalToDouble(trade.PreviousAsk?.Price),
            BestBidAfter = DecimalToDouble(trade.NewBid?.Price),
            BestAskAfter = DecimalToDouble(trade.NewAsk?.Price),
        });

        UpdateDriveState(eventTimeUtc, price, side, size);
        UpdatePostHarvestState(eventTimeUtc, price, side, size);
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
            ScheduleTriggerBurst(
                "significant_liquidity_near_touch",
                eventTimeUtc,
                price.Value,
                new[] { "same_price_replenishment", side == CollectorSide.Buy ? "buyers_hitting_same_level" : "sellers_hitting_same_level" },
                $"repl:{track.TrackId}");
        }

        if (statusBefore != track.Status)
        {
            if (track.Status == "pulled")
            {
                ScheduleTriggerBurst(
                    "liquidity_pull",
                    eventTimeUtc,
                    price.Value,
                    new[] { "visible_liquidity_pulled", "watch_release" },
                    $"pull:{track.TrackId}");
            }
            else if (track.Status is "filled" or "partially_filled")
            {
                ScheduleTriggerBurst(
                    "liquidity_fill",
                    eventTimeUtc,
                    price.Value,
                    new[] { "visible_liquidity_consumed", "watch_post_harvest" },
                    $"fill:{track.TrackId}");
                TryStartHarvestState(track, eventTimeUtc);
            }
        }
    }

    private void PollDisplayedLiquiditySnapshot(DateTime nowUtc)
    {
        if ((nowUtc - _lastDepthSnapshotUtc).TotalMilliseconds < Math.Max(250, ContinuousCadenceMilliseconds))
        {
            return;
        }

        _lastDepthSnapshotUtc = nowUtc;

        MarketDataArg[]? snapshot;
        try
        {
            snapshot = GetMarketDepthSnapshot()?.ToArray();
        }
        catch
        {
            return;
        }

        if (snapshot is null || snapshot.Length == 0)
        {
            _lastDepthSnapshotLevelCount = 0;
            return;
        }

        _depthCoverageStartedUtc ??= nowUtc;
        _lastDepthSnapshotSuccessUtc = nowUtc;
        _lastDepthSnapshotLevelCount = snapshot.Length;

        var seenTrackIds = new HashSet<string>(StringComparer.Ordinal);
        decimal? snapshotBestBid = null;
        decimal? snapshotBestAsk = null;
        foreach (var level in snapshot)
        {
            var side = ResolveDisplayedLiquiditySide(level);
            if (side == CollectorSide.Neutral)
            {
                continue;
            }

            var price = level.Price;
            if (side == CollectorSide.Buy)
            {
                snapshotBestBid = snapshotBestBid is null ? price : Math.Max(snapshotBestBid.Value, price);
            }
            else if (side == CollectorSide.Sell)
            {
                snapshotBestAsk = snapshotBestAsk is null ? price : Math.Min(snapshotBestAsk.Value, price);
            }

            var trackId = BuildLiquidityTrackId(side, price);
            seenTrackIds.Add(trackId);
            ProcessDisplayedLiquidity(nowUtc, price, DecimalToInt(level.Volume), side, trackId);
        }

        _bestBid = snapshotBestBid ?? _bestBid;
        _bestAsk = snapshotBestAsk ?? _bestAsk;
        _currentSecond?.ObserveBestBid(_bestBid);
        _currentSecond?.ObserveBestAsk(_bestAsk);

        foreach (var staleTrack in _liquidityTracks.Values
                     .Where(track => track.CurrentSize > 0 && track.Status == "active" && !seenTrackIds.Contains(track.TrackId))
                     .ToList())
        {
            ProcessDisplayedLiquidity(nowUtc, staleTrack.Price, 0, staleTrack.Side, staleTrack.TrackId);
        }
    }

    private CollectorSide ResolveDisplayedLiquiditySide(MarketDataArg marketData)
    {
        var side = AtasReflection.ReadSide(marketData);
        if (side != CollectorSide.Neutral)
        {
            return side;
        }

        if (_bestBid is not null && marketData.Price <= _bestBid.Value)
        {
            return CollectorSide.Buy;
        }

        if (_bestAsk is not null && marketData.Price >= _bestAsk.Value)
        {
            return CollectorSide.Sell;
        }

        return CollectorSide.Neutral;
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

        var payload = BuildActiveDrivePayload();
        if (payload is not null)
        {
            ScheduleTriggerBurst("initiative_drive", eventTimeUtc, price, new[] { "drive_threshold_reached", side == CollectorSide.Buy ? "aggressive_buying" : "aggressive_selling" }, $"drive:{payload.DriveId}");
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

        ScheduleTriggerBurst(
            "harvest_completed",
            eventTimeUtc,
            track.Price,
            new[] { "liquidity_harvest_completed", "monitor_post_harvest_response" },
            _harvestState.ResponseId);
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

        if (_harvestState.FirstReversalAtUtc is null && reversalTicks >= 8)
        {
            _harvestState.FirstReversalAtUtc = eventTimeUtc;
            ScheduleTriggerBurst(
                "post_harvest_reversal",
                eventTimeUtc,
                price,
                new[] { "post_harvest_reversal", "watch_bigger_rotation" },
                $"post-rev:{_harvestState.ResponseId}");
        }
        else if (pullbackTicks >= 4)
        {
            ScheduleTriggerBurst(
                "post_harvest_pullback",
                eventTimeUtc,
                price,
                new[] { "post_harvest_pullback", "watch_retest_or_balance" },
                $"post-pb:{_harvestState.ResponseId}");
        }
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
            ReachedNextOpposingLiquidity = _harvestState.ReachedNextOpposingLiquidity,
            NextOpposingLiquidityPrice = DecimalToDouble(_harvestState.NextOpposingLiquidityPrice),
            PostHarvestDelta = _harvestState.PostHarvestDelta,
            Outcome = DeterminePostHarvestOutcome(continuationTicks, consolidationRangeTicks, pullbackTicks, reversalTicks),
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

    private DepthCoveragePayload BuildDepthCoveragePayload()
    {
        var activeCount = _liquidityTracks.Values.Count(item => item.CurrentSize > 0 && item.Status == "active");
        var coverageState = _lastDepthSnapshotSuccessUtc is null
            ? "depth_unavailable"
            : "depth_live";

        return new DepthCoveragePayload
        {
            CoverageState = coverageState,
            SnapshotLevelCount = _lastDepthSnapshotLevelCount,
            TrackedLiquidityCount = activeCount,
            LastSnapshotAt = _lastDepthSnapshotSuccessUtc,
            BestBidAvailable = _bestBid is not null,
            BestAskAvailable = _bestAsk is not null,
        };
    }

    private List<SamePriceReplenishmentPayload> BuildSamePriceReplenishmentPayloads(decimal currentPrice)
    {
        return _liquidityTracks.Values
            .Where(item => item.ReplenishmentCount >= StrongReplenishmentCount && item.TouchCount > 0 && item.CurrentSize > 0)
            .OrderByDescending(item => item.ReplenishmentCount)
            .ThenByDescending(item => item.HeatScore)
            .Take(6)
            .Select(item => new SamePriceReplenishmentPayload
            {
                TrackId = item.TrackId,
                Side = item.Side.ToPayloadString(),
                Price = (double)item.Price,
                CurrentSize = item.CurrentSize,
                DistanceFromPriceTicks = PriceMath.ToTicks(Math.Abs(currentPrice - item.Price), EffectiveTickSize),
                TouchCount = item.TouchCount,
                ReplenishmentCount = item.ReplenishmentCount,
                BuyersHittingSameLevelCount = item.Side == CollectorSide.Buy ? Math.Max(1, item.TouchCount) : 0,
                SellersHittingSameLevelCount = item.Side == CollectorSide.Sell ? Math.Max(1, item.TouchCount) : 0,
            })
            .ToList();
    }

    private List<ReferenceLevelPayload> BuildReferenceLevels()
    {
        return _liquidityTracks.Values
            .OrderByDescending(item => item.HeatScore)
            .Take(4)
            .Select(item => new ReferenceLevelPayload
            {
                Kind = item.Side == CollectorSide.Buy ? "significant_bid" : "significant_ask",
                Price = (double)item.Price,
                Notes = new List<string>
                {
                    $"replenishment={item.ReplenishmentCount}",
                    $"touches={item.TouchCount}",
                    $"status={item.Status}",
                },
            })
            .ToList();
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
        var chartInstanceId = ResolveChartInstanceId();
        _transport.TryEnqueueTriggerBurst(new TriggerBurstPayload
        {
            MessageId = $"collector-burst-{triggeredAtUtc:yyyyMMddHHmmssfff}",
            EmittedAt = DateTime.UtcNow,
            ObservedWindowStart = triggeredAtUtc.AddSeconds(-Math.Max(1, BurstLookbackSeconds)),
            ObservedWindowEnd = DateTime.UtcNow,
            Source = new SourceEnvelope
            {
                System = "ATAS",
                InstanceId = Environment.MachineName,
                ChartInstanceId = chartInstanceId,
                AdapterVersion = CollectorVersion,
            },
            Instrument = new InstrumentEnvelope
            {
                Symbol = ResolveEffectiveSymbol(),
                Venue = Venue,
                TickSize = (double)EffectiveTickSize,
                Currency = Currency,
            },
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
            PostWindow = BuildBurstWindow(triggeredAtUtc, DateTime.UtcNow),
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
            FirstTouchAt = insideGap ? observedAtUtc : _gapReference?.FirstTouchAt,
            MaxFillTicks = Math.Max(fillTicks, _gapReference?.MaxFillTicks ?? 0),
            FillRatio = Math.Max(fillRatio, _gapReference?.FillRatio ?? 0.0),
            FillAttemptCount = Math.Max(_gapReference?.FillAttemptCount ?? 0, insideGap ? 1 : 0),
            AcceptedInsideGap = insideGap && fillRatio > 0.2,
            RejectedFromGap = !insideGap,
            FullyFilledAt = fillRatio >= 1.0 ? observedAtUtc : _gapReference?.FullyFilledAt,
        };
    }

    private static string DetermineSessionCode(DateTime nowUtc) => nowUtc.Hour switch
    {
        < 7 => "asia",
        < 13 => "europe",
        < 14 => "us_premarket",
        < 21 => "us_regular",
        _ => "us_after_hours",
    };

    private static string DetermineTradingDate(DateTime nowUtc) => nowUtc.ToString("yyyy-MM-dd");

    private List<HistoryBarPayload> BuildLoadedHistoryBars()
    {
        var maxBars = Math.Max(100, HistoryMaxBars);
        var lastIndex = _latestObservedBarIndex;
        var firstIndex = Math.Max(0, lastIndex - maxBars + 1);
        var bars = new List<HistoryBarPayload>(lastIndex - firstIndex + 1);
        var barStarts = new List<DateTime>(lastIndex - firstIndex + 1);

        for (var index = firstIndex; index <= lastIndex; index++)
        {
            var candle = GetCandle(index);
            barStarts.Add(ToUtc(candle.Time));
        }

        if (barStarts.Count == 0)
        {
            return bars;
        }

        var barSpan = InferBarSpan(barStarts);
        for (var offset = 0; offset < barStarts.Count; offset++)
        {
            var index = firstIndex + offset;
            var candle = GetCandle(index);
            var startedAt = barStarts[offset];
            var endedAt = startedAt + barSpan - TimeSpan.FromSeconds(1);
            bars.Add(new HistoryBarPayload
            {
                StartedAt = startedAt,
                EndedAt = endedAt,
                Open = (double)candle.Open,
                High = (double)candle.High,
                Low = (double)candle.Low,
                Close = (double)candle.Close,
                Volume = AtasReflection.ReadInt(candle, "Volume"),
                Delta = AtasReflection.ReadInt(candle, "Delta"),
                BidVolume = AtasReflection.ReadInt(candle, "Bid"),
                AskVolume = AtasReflection.ReadInt(candle, "Ask"),
            });
        }

        return bars;
    }

    private List<HistoryFootprintBarPayload> BuildLoadedHistoryFootprintBars()
    {
        var maxBars = Math.Max(100, HistoryMaxBars);
        var lastIndex = _latestObservedBarIndex;
        var firstIndex = Math.Max(0, lastIndex - maxBars + 1);
        var bars = new List<HistoryFootprintBarPayload>(Math.Max(0, lastIndex - firstIndex + 1));
        var barStarts = new List<DateTime>(Math.Max(0, lastIndex - firstIndex + 1));

        for (var index = firstIndex; index <= lastIndex; index++)
        {
            var candle = GetCandle(index);
            barStarts.Add(ToUtc(candle.Time));
        }

        if (barStarts.Count == 0)
        {
            return bars;
        }

        var barSpan = InferBarSpan(barStarts);
        for (var offset = 0; offset < barStarts.Count; offset++)
        {
            var index = firstIndex + offset;
            var candle = GetCandle(index);
            var startedAt = barStarts[offset];
            var endedAt = startedAt + barSpan - TimeSpan.FromSeconds(1);
            bars.Add(new HistoryFootprintBarPayload
            {
                StartedAt = startedAt,
                EndedAt = endedAt,
                Open = (double)candle.Open,
                High = (double)candle.High,
                Low = (double)candle.Low,
                Close = (double)candle.Close,
                Volume = AtasReflection.ReadInt(candle, "Volume"),
                Delta = AtasReflection.ReadInt(candle, "Delta"),
                BidVolume = AtasReflection.ReadInt(candle, "Bid"),
                AskVolume = AtasReflection.ReadInt(candle, "Ask"),
                PriceLevels = ExtractHistoryFootprintLevels(candle),
            });
        }

        return bars;
    }

    private static TimeSpan InferBarSpan(IReadOnlyList<DateTime> barStarts)
    {
        if (barStarts.Count < 2)
        {
            return TimeSpan.FromMinutes(1);
        }

        for (var index = barStarts.Count - 1; index >= 1; index--)
        {
            var span = barStarts[index] - barStarts[index - 1];
            if (span > TimeSpan.Zero)
            {
                return span;
            }
        }

        return TimeSpan.FromMinutes(1);
    }

    private static string DetermineHistoryBarTimeframe(IReadOnlyList<HistoryBarPayload> bars)
    {
        var span = InferBarSpan(bars.Select(item => item.StartedAt).ToList());
        if (span.TotalMinutes <= 1.1)
        {
            return "1m";
        }

        if (span.TotalMinutes <= 5.1)
        {
            return "5m";
        }

        if (span.TotalMinutes <= 15.1)
        {
            return "15m";
        }

        if (span.TotalMinutes <= 30.1)
        {
            return "30m";
        }

        if (span.TotalMinutes <= 60.1)
        {
            return "1h";
        }

        if (span.TotalHours <= 24.1)
        {
            return "1d";
        }

        return string.Empty;
    }

    private static string DetermineHistoryFootprintTimeframe(IReadOnlyList<HistoryFootprintBarPayload> bars)
    {
        var span = InferBarSpan(bars.Select(item => item.StartedAt).ToList());
        if (span.TotalMinutes <= 1.1)
        {
            return "1m";
        }

        if (span.TotalMinutes <= 5.1)
        {
            return "5m";
        }

        if (span.TotalMinutes <= 15.1)
        {
            return "15m";
        }

        if (span.TotalMinutes <= 30.1)
        {
            return "30m";
        }

        if (span.TotalMinutes <= 60.1)
        {
            return "1h";
        }

        if (span.TotalHours <= 24.1)
        {
            return "1d";
        }

        return string.Empty;
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

    private decimal EffectiveTickSize => UseTickSizeOverride && TickSizeOverride > 0m
        ? TickSizeOverride
        : ResolveDetectedTickSize();

    private string ResolveEffectiveSymbol()
    {
        if (UseSymbolOverride)
        {
            var overrideSymbol = NormalizeSymbolCandidate(SymbolOverride);
            if (!string.IsNullOrWhiteSpace(overrideSymbol))
            {
                return overrideSymbol;
            }
        }

        return ResolveDetectedSymbol() ?? "UNKNOWN";
    }

    private string? ResolveDetectedSymbol()
    {
        foreach (var path in SymbolCandidatePaths)
        {
            var candidate = NormalizeSymbolCandidate(AtasReflection.ReadStringPath(this, path));
            if (!string.IsNullOrWhiteSpace(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private decimal ResolveDetectedTickSize()
    {
        if (TickSize > 0m)
        {
            return TickSize;
        }

        foreach (var path in TickSizeCandidatePaths)
        {
            var candidate = AtasReflection.ReadDecimalPath(this, path);
            if (candidate is > 0m)
            {
                return candidate.Value;
            }
        }

        return TickSizeOverride > 0m ? TickSizeOverride : 0.25m;
    }

    private string ResolveChartInstanceId()
    {
        _chartInstanceId ??= $"{ResolveEffectiveSymbol()}-{GetHashCode():x8}";
        return _chartInstanceId;
    }

    private static string BuildLiquidityTrackId(CollectorSide side, decimal price)
        => $"{side.ToPayloadString()}:{price:F8}";

    private static DateTime ToUtc(DateTime value) => value.Kind == DateTimeKind.Utc ? value : value.ToUniversalTime();

    private static int DecimalToInt(decimal value) => Math.Max(0, decimal.ToInt32(decimal.Round(value, MidpointRounding.AwayFromZero)));

    private static double? DecimalToDouble(decimal? value) => value is null ? null : (double)value.Value;

    private static double? NullIfZero(decimal value) => value == 0m ? null : (double)value;

    private static string? NormalizeSymbolCandidate(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var candidate = raw.Trim();
        var cutIndex = candidate.IndexOfAny(new[] { ' ', '\t', '\r', '\n', '(', '[', '{' });
        if (cutIndex > 0)
        {
            candidate = candidate[..cutIndex];
        }

        candidate = candidate.Trim().Trim('"', '\'');
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return null;
        }

        if (candidate.StartsWith("ATAS", StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith("ZZ", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        candidate = candidate.ToUpperInvariant();
        if (InvalidSymbolCandidates.Contains(candidate))
        {
            return null;
        }

        if (candidate.Length < 2)
        {
            return null;
        }

        var hasLetter = false;
        foreach (var ch in candidate)
        {
            if (char.IsLetter(ch))
            {
                hasLetter = true;
                break;
            }
        }

        if (!hasLetter)
        {
            return null;
        }

        return candidate;
    }

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
        if (reversalTicks >= 8)
        {
            return "reversal";
        }

        if (pullbackTicks >= 4)
        {
            return "pullback";
        }

        if (continuationTicks >= 4 && consolidationRangeTicks <= 6)
        {
            return "continuation";
        }

        return consolidationRangeTicks <= 8 ? "consolidation" : "mixed";
    }

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
            PriceTravelTicks = Side == CollectorSide.Buy
                ? PriceMath.ToTicks(Math.Max(0m, High - StartPrice), tickSize)
                : PriceMath.ToTicks(Math.Max(0m, StartPrice - Low), tickSize),
            MaxCounterMoveTicks = 0,
            ContinuationSeconds = Math.Max(1, (int)(LastObservedAtUtc - StartedAtUtc).TotalSeconds),
        };
    }
}
