using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ZZ ATAS PropertyTypes Probe")]
[Description("Probe indicator that mirrors the collector property mix.")]
[Category("Order Flow")]
public sealed class CollectorPropertyTypesProbeIndicator : Indicator
{
    private readonly ValueDataSeries _series = new("CollectorPropertyTypesProbe") { VisualType = VisualMode.Hide };

    public CollectorPropertyTypesProbeIndicator()
        : base(true)
    {
        DataSeries.Add(_series);
    }

    [Display(Name = "Service Base URL", GroupName = "1. Adapter", Order = 10)]
    public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8080";

    [Display(Name = "Continuous Endpoint", GroupName = "1. Adapter", Order = 20)]
    public string ContinuousEndpoint { get; set; } = "/api/v1/adapter/continuous-state";

    [Display(Name = "Tick Size Override", GroupName = "2. Instrument", Order = 10)]
    public decimal TickSizeOverride { get; set; } = 0.25m;

    [Display(Name = "Queue Limit", GroupName = "3. Performance", Order = 10)]
    public int QueueLimit { get; set; } = 256;

    [Display(Name = "Prior RTH Close", GroupName = "4. Session References", Order = 10)]
    public decimal PriorRthClose { get; set; }

    [Display(Name = "Enable Market By Orders", GroupName = "5. DOM / MBO", Order = 10)]
    public bool EnableMarketByOrders { get; set; }

    protected override void OnCalculate(int bar, decimal value)
    {
        _series[bar] = value;
    }
}
