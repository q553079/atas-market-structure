using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

[DisplayName("ZZ ATAS Collector Probe")]
[Category("Order Flow")]
public class ZZAtasCollectorProbe : Indicator
{
    private readonly ValueDataSeries _probe = new("ZZProbe")
    {
        VisualType = VisualMode.Hide,
    };

    public ZZAtasCollectorProbe()
        : base(true)
    {
        DataSeries.Add(_probe);
    }

    [Display(Name = "Enabled", GroupName = "1. Probe", Order = 10)]
    public bool Enabled { get; set; } = true;

    protected override void OnCalculate(int bar, decimal value)
    {
        _probe[bar] = Enabled ? value : 0m;
    }
}
