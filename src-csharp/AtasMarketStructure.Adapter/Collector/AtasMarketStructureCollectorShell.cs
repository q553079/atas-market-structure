using System.ComponentModel;
using System.ComponentModel.DataAnnotations;

namespace AtasMarketStructure.Adapter.Collector;

[DisplayName("ATAS Market Structure Collector")]
[Description("Visible collector shell that reuses the full collector pipeline for mirror/history/backfill support.")]
[Category("Order Flow")]
public sealed class AtasMarketStructureCollector : AtasMarketStructureCollectorFull
{
}
