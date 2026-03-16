using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.DataFeedsCore;
using ATAS.Indicators;

[DisplayName("ZZ ATAS BestBidAsk Probe")]
[Description("Probe indicator that only overrides OnBestBidAskChanged.")]
[Category("Order Flow")]
public sealed class ZZAtasBestBidAskProbe : Indicator
{
    private readonly ValueDataSeries _series = new("BestBidAskProbe") { VisualType = VisualMode.Hide };

    public ZZAtasBestBidAskProbe()
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

    protected override void OnBestBidAskChanged(MarketDataArg marketData)
    {
        var price = marketData.Price;
        _ = price;
    }
}
