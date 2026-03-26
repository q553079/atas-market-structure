using System.ComponentModel;
using System.ComponentModel.DataAnnotations;

namespace AtasMarketStructure.Adapter.Collector;

// Workspace-facing compatibility shell.
// Keep legacy serialized properties here so older ATAS workspaces can reopen
// after collector internals evolve.
[DisplayName("ATAS Market Structure Collector")]
[Description("Visible collector shell that reuses the full collector pipeline for mirror/history/backfill support.")]
[Category("Order Flow")]
public sealed class AtasMarketStructureCollector : AtasMarketStructureCollectorFull
{
    private string _adapterVersion = "0.10.5-compat";
    private string _chartInstanceId = string.Empty;
    private string _detectedSymbol = string.Empty;
    private string _effectiveSymbol = string.Empty;
    private string _historyBarsEndpoint = "/api/v1/adapter/history-bars";
    private string _historyFootprintEndpoint = "/api/v1/adapter/history-footprint";
    private string _lastCollectorInternalErrorUtc = string.Empty;
    private string _lastTransportAttemptUtc = string.Empty;
    private string _lastTransportError = string.Empty;
    private string _lastTransportFailureUtc = string.Empty;
    private string _lastTransportSuccessUtc = string.Empty;

    [Browsable(false)]
    public string AdapterVersion
    {
        get => _adapterVersion;
        set => _adapterVersion = string.IsNullOrWhiteSpace(value) ? "0.10.5-compat" : value;
    }

    [Browsable(false)]
    public string ChartInstanceId
    {
        get => _chartInstanceId;
        set => _chartInstanceId = value ?? string.Empty;
    }

    [Browsable(false)]
    public int TrackedLiquidityCount { get; set; }

    [Browsable(false)]
    public int DepthSnapshotLevelCount { get; set; }

    [Browsable(false)]
    public string DepthSnapshotLastUtc { get; set; } = string.Empty;

    [Browsable(false)]
    public decimal BestBidDisplay { get; set; }

    [Browsable(false)]
    public decimal BestAskDisplay { get; set; }

    [Browsable(false)]
    public int TransportQueueDepth { get; set; }

    [Browsable(false)]
    public int DroppedMessageCount { get; set; }

    [Browsable(false)]
    public int ConsecutiveSendFailures { get; set; }

    [Browsable(false)]
    public string LastTransportAttemptUtc
    {
        get => _lastTransportAttemptUtc;
        set => _lastTransportAttemptUtc = value ?? string.Empty;
    }

    [Browsable(false)]
    public string LastTransportSuccessUtc
    {
        get => _lastTransportSuccessUtc;
        set => _lastTransportSuccessUtc = value ?? string.Empty;
    }

    [Browsable(false)]
    public string LastTransportFailureUtc
    {
        get => _lastTransportFailureUtc;
        set => _lastTransportFailureUtc = value ?? string.Empty;
    }

    [Browsable(false)]
    public string LastTransportError
    {
        get => _lastTransportError;
        set => _lastTransportError = value ?? string.Empty;
    }

    [Browsable(false)]
    public string LastCollectorInternalErrorUtc
    {
        get => _lastCollectorInternalErrorUtc;
        set => _lastCollectorInternalErrorUtc = value ?? string.Empty;
    }

    [Browsable(false)]
    public string LastCollectorInternalError { get; set; } = string.Empty;

    [Browsable(false)]
    public string HistoryBarsEndpoint
    {
        get => _historyBarsEndpoint;
        set => _historyBarsEndpoint = string.IsNullOrWhiteSpace(value) ? "/api/v1/adapter/history-bars" : value;
    }

    [Browsable(false)]
    public string HistoryFootprintEndpoint
    {
        get => _historyFootprintEndpoint;
        set => _historyFootprintEndpoint = string.IsNullOrWhiteSpace(value) ? "/api/v1/adapter/history-footprint" : value;
    }

    [Browsable(false)]
    public bool UseSymbolOverride { get; set; }

    [Browsable(false)]
    public string DetectedSymbol
    {
        get => _detectedSymbol;
        set => _detectedSymbol = value ?? string.Empty;
    }

    [Browsable(false)]
    public string EffectiveSymbol
    {
        get => _effectiveSymbol;
        set => _effectiveSymbol = value ?? string.Empty;
    }

    [Browsable(false)]
    public bool UseTickSizeOverride { get; set; }

    [Browsable(false)]
    public decimal DetectedTickSize { get; set; }

    [Browsable(false)]
    public decimal EffectiveTickSizeDisplay { get; set; }

    [Browsable(false)]
    public int HistorySyncCadenceSeconds { get; set; } = 15;

    [Browsable(false)]
    public int HistoryFootprintSyncMinutes { get; set; } = 15;

    [Browsable(false)]
    public int HistoryMaxBars { get; set; } = 12000;

    [Browsable(false)]
    public int HistoryFootprintChunkBars { get; set; } = 240;
}
