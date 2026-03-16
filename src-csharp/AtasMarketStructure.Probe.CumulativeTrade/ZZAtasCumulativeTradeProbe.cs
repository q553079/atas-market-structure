using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

[DisplayName("ZZ ATAS CumulativeTrade Probe")]
[Description("Probe indicator that only overrides cumulative trade callbacks.")]
[Category("Order Flow")]
public sealed class ZZAtasCumulativeTradeProbe : Indicator
{
    private readonly ValueDataSeries _series = new("CumulativeTradeProbe") { VisualType = VisualMode.Hide };

    public ZZAtasCumulativeTradeProbe()
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

    protected override void OnCumulativeTrade(CumulativeTrade trade)
    {
        var volume = trade.Volume;
        _ = volume;
    }

    protected override void OnUpdateCumulativeTrade(CumulativeTrade trade)
    {
        var volume = trade.Volume;
        _ = volume;
    }
}
