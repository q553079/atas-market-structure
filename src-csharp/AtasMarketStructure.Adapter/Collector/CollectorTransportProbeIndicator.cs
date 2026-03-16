using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ZZ ATAS Transport Probe")]
[Description("Probe indicator that exercises the collector transport and timer initialization path.")]
[Category("Order Flow")]
public sealed class CollectorTransportProbeIndicator : Indicator
{
    private readonly ValueDataSeries _series = new("CollectorTransportProbe") { VisualType = VisualMode.Hide };
    private IAdapterTransport? _transport;

    public CollectorTransportProbeIndicator()
        : base(true)
    {
        DataSeries.Add(_series);
    }

    [Display(Name = "Service Base URL", GroupName = "1. Adapter", Order = 10)]
    public string ServiceBaseUrl { get; set; } = "http://127.0.0.1:8080";

    [Display(Name = "Continuous Endpoint", GroupName = "1. Adapter", Order = 20)]
    public string ContinuousEndpoint { get; set; } = "/api/v1/adapter/continuous-state";

    [Display(Name = "Trigger Endpoint", GroupName = "1. Adapter", Order = 30)]
    public string TriggerEndpoint { get; set; } = "/api/v1/adapter/trigger-burst";

    [Display(Name = "History Bars Endpoint", GroupName = "1. Adapter", Order = 25)]
    public string HistoryBarsEndpoint { get; set; } = "/api/v1/adapter/history-bars";

    [Display(Name = "History Footprint Endpoint", GroupName = "1. Adapter", Order = 27)]
    public string HistoryFootprintEndpoint { get; set; } = "/api/v1/adapter/history-footprint";

    [Display(Name = "Queue Limit", GroupName = "2. Performance", Order = 10)]
    public int QueueLimit { get; set; } = 64;

    protected override void OnInitialize()
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
        SubscribeToTimer(TimeSpan.FromSeconds(1), () => { });
    }

    protected override void OnDispose()
    {
        _transport?.Dispose();
        _transport = null;
    }

    protected override void OnCalculate(int bar, decimal value)
    {
        _series[bar] = value;
    }
}
