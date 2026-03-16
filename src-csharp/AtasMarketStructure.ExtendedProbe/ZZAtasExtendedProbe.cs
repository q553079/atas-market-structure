using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using ATAS.Indicators;

[DisplayName("ZZ ATAS Extended Probe")]
[Category("Order Flow")]
public class ZZAtasExtendedProbe : ExtendedIndicator
{
    private readonly ValueDataSeries _probe = new("ZZExtendedProbe")
    {
        VisualType = VisualMode.Hide,
    };

    public ZZAtasExtendedProbe()
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
