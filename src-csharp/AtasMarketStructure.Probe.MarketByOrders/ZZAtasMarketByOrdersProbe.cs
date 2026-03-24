using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Diagnostics;
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
        ObserveBackgroundTask(SubscribeMarketByOrderData(), "ZZAtasMarketByOrdersProbe.SubscribeMarketByOrderData");
    }

    protected override void OnMarketByOrdersChanged(IEnumerable<MarketByOrder> marketByOrders)
    {
        foreach (var marketByOrder in marketByOrders)
        {
            _ = marketByOrder;
            break;
        }
    }

    private static void ObserveBackgroundTask(Task? task, string operationName)
    {
        if (task is null)
        {
            return;
        }

        task.ContinueWith(
            continuation =>
            {
                var exception = continuation.Exception?.GetBaseException();
                Debug.WriteLine(
                    exception is null
                        ? $"[ATAS-MBO-Probe][WARN] {operationName} faulted without an exception payload."
                        : $"[ATAS-MBO-Probe][WARN] {operationName} faulted: {exception.GetType().Name}: {exception.Message}");
            },
            CancellationToken.None,
            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
            TaskScheduler.Default);
    }
}
