using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.DataFeedsCore;
using ATAS.Indicators;

[DisplayName("ZZ ATAS MarketByOrders Probe")]
[Description("Probe indicator that only overrides OnMarketByOrdersChanged.")]
[Category("Order Flow")]
public sealed class ZZAtasMarketByOrdersProbe : Indicator
{
    private readonly ValueDataSeries _series = new("MarketByOrdersProbe") { VisualType = VisualMode.Hide };

    public ZZAtasMarketByOrdersProbe()
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

    protected override void OnInitialize()
    {
        _ = SubscribeMarketByOrderData();
    }

    protected override void OnMarketByOrdersChanged(IEnumerable<MarketByOrder> marketByOrders)
    {
        foreach (var marketByOrder in marketByOrders)
        {
            _ = marketByOrder;
            break;
        }
    }
}
