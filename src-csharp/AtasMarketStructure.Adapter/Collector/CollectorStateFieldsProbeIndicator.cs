using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;
using AtasMarketStructure.Adapter.Contracts;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ZZ ATAS StateFields Probe")]
[Description("Probe indicator that mirrors the collector state fields without transport logic.")]
[Category("Order Flow")]
public sealed class CollectorStateFieldsProbeIndicator : Indicator
{
    private readonly object _sync = new();
    private readonly ValueDataSeries _series = new("CollectorStateFieldsProbe") { VisualType = VisualMode.Hide };
    private readonly TimedRingBuffer<TradeEventPayload> _tradeBuffer = new(TimeSpan.FromMinutes(5), item => item.EventTime);
    private readonly TimedRingBuffer<DepthEventPayload> _depthBuffer = new(TimeSpan.FromMinutes(5), item => item.EventTime);
    private readonly TimedRingBuffer<SecondFeaturePayload> _secondBuffer = new(TimeSpan.FromMinutes(5), item => item.SecondStartedAt);
    private readonly Dictionary<string, SignificantLiquidityTrackState> _liquidityTracks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, DateTime> _lastTriggerByKey = new(StringComparer.Ordinal);
    private TradeAccumulatorState _tradeAccumulator = new();
    private SecondAccumulatorState? _currentSecond;
    private HarvestState? _harvestState;
    private GapReferencePayload? _gapReference;
    private decimal? _bestBid;
    private decimal? _bestAsk;
    private decimal? _lastPrice;
    private decimal? _sessionOpenPrice;

    public CollectorStateFieldsProbeIndicator()
        : base(true)
    {
        DataSeries.Add(_series);
    }

    [Display(Name = "Enabled", GroupName = "1. Probe", Order = 10)]
    public bool Enabled { get; set; } = true;

    protected override void OnCalculate(int bar, decimal value)
    {
        lock (_sync)
        {
            _series[bar] = Enabled ? value : 0m;
            _lastPrice = value;
            _bestBid ??= value;
            _bestAsk ??= value;
            _sessionOpenPrice ??= value;
            _ = _tradeBuffer;
            _ = _depthBuffer;
            _ = _secondBuffer;
            _ = _liquidityTracks;
            _ = _lastTriggerByKey;
            _ = _tradeAccumulator;
            _ = _currentSecond;
            _ = _harvestState;
            _ = _gapReference;
        }
    }
}
