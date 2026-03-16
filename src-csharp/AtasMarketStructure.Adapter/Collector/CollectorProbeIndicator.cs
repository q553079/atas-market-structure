using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ZZ ATAS Collector Probe")]
[Description("Minimal probe indicator used to confirm that the adapter assembly is visible to ATAS.")]
[Category("Order Flow")]
public sealed class CollectorProbeIndicator : Indicator
{
    private readonly ValueDataSeries _probeSeries = new("CollectorProbe") { VisualType = VisualMode.Hide };

    public CollectorProbeIndicator()
        : base(true)
    {
        DataSeries.Add(_probeSeries);
    }

    [Display(Name = "Enabled", GroupName = "1. Probe", Order = 10)]
    public bool Enabled { get; set; } = true;

    protected override void OnCalculate(int bar, decimal value)
    {
        _probeSeries[bar] = Enabled ? value : 0m;
    }
}
