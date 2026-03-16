using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.DataFeedsCore;
using ATAS.Indicators;

[DisplayName("ZZ ATAS MarketDepth Probe")]
[Description("Probe indicator that only overrides MarketDepthChanged.")]
[Category("Order Flow")]
public sealed class ZZAtasMarketDepthProbe : Indicator
{
    private readonly ValueDataSeries _series = new("MarketDepthProbe") { VisualType = VisualMode.Hide };

    public ZZAtasMarketDepthProbe()
        : base(true)
    {
        DataSeries.Add(_series);
    }

    [Display(Name = "Enabled", GroupName = "1. Probe", Order = 10)]
    public bool Enabled { get; set; } = true;

    protected override void OnCalculate(int bar, decimal value)
    {
        _series[bar] = value;
    }

    protected override void MarketDepthChanged(MarketDataArg marketData)
    {
        var price = marketData.Price;
        _ = price;
    }
}
