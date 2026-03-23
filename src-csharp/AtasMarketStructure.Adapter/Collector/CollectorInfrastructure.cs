using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Collections;
using AtasMarketStructure.Adapter.Contracts;

namespace AtasMarketStructure.Adapter.Collector;

internal enum CollectorSide
{
    Neutral,
    Buy,
    Sell,
}

#region Transport Interfaces

internal interface IAdapterTransport : IDisposable
{
    bool TryEnqueueContinuousState(ContinuousStatePayload payload);

    bool TryEnqueueHistoryBars(HistoryBarsPayload payload);

    bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload);

    bool TryEnqueueTriggerBurst(TriggerBurstPayload payload);

    Task<AdapterBackfillDispatchResponsePayload?> PollBackfillCommandAsync(
        string instrumentSymbol,
        string? chartInstanceId,
        string? contractSymbol,
        string? rootSymbol,
        CancellationToken ct);

    Task<bool> SendBackfillAckAsync(AdapterBackfillAcknowledgeRequestPayload ack, CancellationToken ct);

    int QueueLength { get; }

    int DroppedMessageCount { get; }

    int ConsecutiveSendFailures { get; }

    DateTime? LastAttemptUtc { get; }

    DateTime? LastSuccessfulPostUtc { get; }

    DateTime? LastFailureUtc { get; }

    string LastTransportError { get; }

    TransportStatus GetStatus();
}

internal interface IRealtimeTransport : IDisposable
{
    bool TryEnqueueContinuousState(ContinuousStatePayload payload);

    bool TryEnqueueTriggerBurst(TriggerBurstPayload payload);

    int QueueLength { get; }

    int DroppedMessageCount { get; }

    int ConsecutiveSendFailures { get; }

    DateTime? LastAttemptUtc { get; }

    DateTime? LastSuccessfulPostUtc { get; }

    DateTime? LastFailureUtc { get; }

    string LastTransportError { get; }

    RealtimeTransportStatus GetStatus();
}

internal interface IHistoryTransport : IDisposable
{
    bool TryEnqueueHistoryBars(HistoryBarsPayload payload);

    bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload);

    Task<AdapterBackfillDispatchResponsePayload?> PollBackfillCommandAsync(
        string instrumentSymbol,
        string? chartInstanceId,
        string? contractSymbol,
        string? rootSymbol,
        CancellationToken ct);

    Task<bool> SendBackfillAckAsync(AdapterBackfillAcknowledgeRequestPayload ack, CancellationToken ct);

    int HistoryBarsQueueLength { get; }

    int HistoryFootprintQueueLength { get; }

    int HistoryBarsDroppedCount { get; }

    int HistoryFootprintDroppedCount { get; }

    int HistoryBarsSentCount { get; }

    int HistoryBarsFailedCount { get; }

    int HistoryFootprintSentCount { get; }

    int HistoryFootprintFailedCount { get; }

    int BackfillCommandPolledCount { get; }

    int BackfillAckPostedCount { get; }

    int BackfillAckFailedCount { get; }

    DateTime? LastAttemptUtc { get; }

    DateTime? LastSuccessfulPostUtc { get; }

    DateTime? LastFailureUtc { get; }

    string LastTransportError { get; }

    HistoryTransportStatus GetStatus();
}

#endregion

#region Transport Status Models

internal class TransportStatus
{
    public int TotalQueueLength { get; init; }
    public int TotalDroppedCount { get; init; }
    public int ConsecutiveSendFailures { get; init; }
    public DateTime? LastAttemptUtc { get; init; }
    public DateTime? LastSuccessfulPostUtc { get; init; }
    public DateTime? LastFailureUtc { get; init; }
    public string LastTransportError { get; init; } = string.Empty;
    public string Summary { get; init; } = string.Empty;
}

internal sealed class RealtimeTransportStatus : TransportStatus
{
    public int ContinuousStateQueueLength { get; init; }
    public int TriggerBurstQueueLength { get; init; }
}

internal sealed class HistoryTransportStatus : TransportStatus
{
    public int HistoryBarsQueueLength { get; init; }
    public int HistoryFootprintQueueLength { get; init; }
    public int HistoryBarsDroppedCount { get; init; }
    public int HistoryFootprintDroppedCount { get; init; }
    public int HistoryBarsSentCount { get; init; }
    public int HistoryBarsFailedCount { get; init; }
    public int HistoryFootprintSentCount { get; init; }
    public int HistoryFootprintFailedCount { get; init; }
    public int BackfillCommandPolledCount { get; init; }
    public int BackfillAckPostedCount { get; init; }
    public int BackfillAckFailedCount { get; init; }
}

#endregion

#region Realtime Transport Implementation

internal sealed class BufferedRealtimeTransport : IRealtimeTransport
{
    private readonly HttpClient _httpClient;
    private readonly string _continuousEndpoint;
    private readonly string _triggerEndpoint;
    private readonly Action<string> _infoLogger;
    private readonly Action<string> _warnLogger;

    private readonly ConcurrentQueue<RealtimeOutboundMessage> _queue = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _pumpTask;
    private readonly SemaphoreSlim _signal = new(0);
    private readonly int _maxQueueLength;

    private int _queueLength;
    private int _droppedMessageCount;
    private int _consecutiveSendFailures;
    private DateTime? _lastAttemptUtc;
    private DateTime? _lastSuccessfulPostUtc;
    private DateTime? _lastFailureUtc;
    private string _lastTransportError = string.Empty;

    public BufferedRealtimeTransport(
        Uri baseUri,
        string continuousEndpoint,
        string triggerEndpoint,
        int maxQueueLength,
        Action<string> infoLogger,
        Action<string> warnLogger)
    {
        _continuousEndpoint = continuousEndpoint;
        _triggerEndpoint = triggerEndpoint;
        _maxQueueLength = Math.Max(16, maxQueueLength);
        _infoLogger = infoLogger;
        _warnLogger = warnLogger;

        _httpClient = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(5),
        };
        _httpClient.DefaultRequestHeaders.Accept.Clear();
        _httpClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        _pumpTask = Task.Run(PumpAsync);
        _infoLogger("BufferedRealtimeTransport initialized with 5s timeout.");
    }

    public bool TryEnqueueContinuousState(ContinuousStatePayload payload)
        => TryEnqueue(new RealtimeOutboundMessage(_continuousEndpoint, payload, MessagePriority.High));

    public bool TryEnqueueTriggerBurst(TriggerBurstPayload payload)
        => TryEnqueue(new RealtimeOutboundMessage(_triggerEndpoint, payload, MessagePriority.High));

    public int QueueLength => Volatile.Read(ref _queueLength);

    public int DroppedMessageCount => Volatile.Read(ref _droppedMessageCount);

    public int ConsecutiveSendFailures => Volatile.Read(ref _consecutiveSendFailures);

    public DateTime? LastAttemptUtc => _lastAttemptUtc;

    public DateTime? LastSuccessfulPostUtc => _lastSuccessfulPostUtc;

    public DateTime? LastFailureUtc => _lastFailureUtc;

    public string LastTransportError => _lastTransportError;

    public RealtimeTransportStatus GetStatus()
    {
        return new RealtimeTransportStatus
        {
            TotalQueueLength = QueueLength,
            TotalDroppedCount = DroppedMessageCount,
            ConsecutiveSendFailures = ConsecutiveSendFailures,
            LastAttemptUtc = LastAttemptUtc,
            LastSuccessfulPostUtc = LastSuccessfulPostUtc,
            LastFailureUtc = LastFailureUtc,
            LastTransportError = LastTransportError,
            ContinuousStateQueueLength = QueueLength,
            TriggerBurstQueueLength = 0,
            Summary = $"RealtimeTransport: queue={QueueLength}, dropped={DroppedMessageCount}, failures={ConsecutiveSendFailures}",
        };
    }

    public void Dispose()
    {
        _cts.Cancel();
        _signal.Release();
        try
        {
            _pumpTask.Wait(TimeSpan.FromSeconds(2));
        }
        catch (AggregateException)
        {
        }
        finally
        {
            _signal.Dispose();
            _cts.Dispose();
            _httpClient.Dispose();
        }
    }

    private bool TryEnqueue(RealtimeOutboundMessage message)
    {
        if (Volatile.Read(ref _queueLength) >= _maxQueueLength)
        {
            Interlocked.Increment(ref _droppedMessageCount);
            _lastFailureUtc = DateTime.UtcNow;
            _lastTransportError = $"Realtime queue full ({_maxQueueLength}); dropped payload for {message.Endpoint}.";
            _warnLogger(_lastTransportError);
            return false;
        }

        _queue.Enqueue(message);
        Interlocked.Increment(ref _queueLength);
        _signal.Release();
        return true;
    }

    private async Task PumpAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            try
            {
                await _signal.WaitAsync(_cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            while (_queue.TryDequeue(out var message))
            {
                Interlocked.Decrement(ref _queueLength);

                try
                {
                    await PostAsync(message, _cts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
                catch (Exception ex)
                {
                    _warnLogger($"Realtime send failed for '{message.Endpoint}': {ex.Message}");
                }
            }
        }
    }

    private async Task PostAsync(RealtimeOutboundMessage message, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(message.Payload, PayloadJson.Options);
        Exception? lastException = null;
        const int maxAttempts = 3;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            _lastAttemptUtc = DateTime.UtcNow;
            try
            {
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                using var response = await _httpClient.PostAsync(message.Endpoint, content, cancellationToken).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                {
                    var responseBody = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                    throw new InvalidOperationException(
                        $"HTTP {(int)response.StatusCode} for {message.Endpoint}: {responseBody}");
                }

                Interlocked.Exchange(ref _consecutiveSendFailures, 0);
                _lastSuccessfulPostUtc = DateTime.UtcNow;
                _lastTransportError = string.Empty;
                _infoLogger($"Realtime payload delivered to {message.Endpoint}.");
                return;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                lastException = ex;
                if (attempt < maxAttempts)
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(250 * attempt), cancellationToken).ConfigureAwait(false);
                    continue;
                }
            }
        }

        Interlocked.Increment(ref _consecutiveSendFailures);
        _lastFailureUtc = DateTime.UtcNow;
        _lastTransportError = lastException?.Message ?? $"Unknown transport error for {message.Endpoint}.";
        throw lastException ?? new InvalidOperationException(_lastTransportError);
    }

    private sealed record RealtimeOutboundMessage(string Endpoint, object Payload, MessagePriority Priority);

    private enum MessagePriority { Low, High }
}

#endregion

#region History Transport Implementation

internal sealed class BufferedHistoryTransport : IHistoryTransport
{
    private readonly HttpClient _barsClient;
    private readonly HttpClient _footprintClient;
    private readonly HttpClient _backfillCommandClient;
    private readonly HttpClient _backfillAckClient;
    private readonly string _historyBarsEndpoint;
    private readonly string _historyFootprintEndpoint;
    private readonly Action<string> _infoLogger;
    private readonly Action<string> _warnLogger;

    private readonly ConcurrentQueue<HistoryBarsMessage> _barsQueue = new();
    private readonly ConcurrentQueue<HistoryFootprintMessage> _footprintQueue = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _barsPumpTask;
    private readonly Task _footprintPumpTask;
    private readonly SemaphoreSlim _barsSignal = new(0);
    private readonly SemaphoreSlim _footprintSignal = new(0);
    private readonly int _maxBarsQueueLength;
    private readonly int _maxFootprintQueueLength;
    private readonly int _rateLimitBarsPerSecond;
    private readonly int _rateLimitFootprintPerSecond;
    private readonly SemaphoreSlim _barsRateLimit = new(1, 1);
    private readonly SemaphoreSlim _footprintRateLimit = new(1, 1);

    private int _barsQueueLength;
    private int _footprintQueueLength;
    private int _historyBarsDroppedCount;
    private int _historyFootprintDroppedCount;
    private int _historyBarsSentCount;
    private int _historyBarsFailedCount;
    private int _historyFootprintSentCount;
    private int _historyFootprintFailedCount;
    private int _backfillCommandPolledCount;
    private int _backfillAckPostedCount;
    private int _backfillAckFailedCount;
    private DateTime? _lastAttemptUtc;
    private DateTime? _lastSuccessfulPostUtc;
    private DateTime? _lastFailureUtc;
    private string _lastTransportError = string.Empty;
    private DateTime _lastBarsSentTime = DateTime.MinValue;
    private DateTime _lastFootprintSentTime = DateTime.MinValue;

    public BufferedHistoryTransport(
        Uri baseUri,
        string historyBarsEndpoint,
        string historyFootprintEndpoint,
        int maxBarsQueueLength,
        int maxFootprintQueueLength,
        int rateLimitBarsPerSecond,
        int rateLimitFootprintPerSecond,
        Action<string> infoLogger,
        Action<string> warnLogger)
    {
        _historyBarsEndpoint = historyBarsEndpoint;
        _historyFootprintEndpoint = historyFootprintEndpoint;
        _maxBarsQueueLength = Math.Max(16, maxBarsQueueLength);
        _maxFootprintQueueLength = Math.Max(16, maxFootprintQueueLength);
        _rateLimitBarsPerSecond = rateLimitBarsPerSecond > 0 ? rateLimitBarsPerSecond : 100;
        _rateLimitFootprintPerSecond = rateLimitFootprintPerSecond > 0 ? rateLimitFootprintPerSecond : 50;
        _infoLogger = infoLogger;
        _warnLogger = warnLogger;

        _barsClient = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(20),
        };
        _barsClient.DefaultRequestHeaders.Accept.Clear();
        _barsClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        _footprintClient = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(45),
        };
        _footprintClient.DefaultRequestHeaders.Accept.Clear();
        _footprintClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        _backfillCommandClient = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(3),
        };
        _backfillCommandClient.DefaultRequestHeaders.Accept.Clear();
        _backfillCommandClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        _backfillAckClient = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(10),
        };
        _backfillAckClient.DefaultRequestHeaders.Accept.Clear();
        _backfillAckClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        _barsPumpTask = Task.Run(BarsPumpAsync);
        _footprintPumpTask = Task.Run(FootprintPumpAsync);
        _infoLogger("BufferedHistoryTransport initialized: bars=20s, footprint=45s, backfill-GET=3s, backfill-POST=10s.");
    }

    public bool TryEnqueueHistoryBars(HistoryBarsPayload payload)
    {
        if (Volatile.Read(ref _barsQueueLength) >= _maxBarsQueueLength)
        {
            Interlocked.Increment(ref _historyBarsDroppedCount);
            _lastFailureUtc = DateTime.UtcNow;
            _lastTransportError = $"HistoryBars queue full ({_maxBarsQueueLength}); dropped payload.";
            _warnLogger(_lastTransportError);
            return false;
        }

        var message = new HistoryBarsMessage(payload, DateTime.UtcNow);
        _barsQueue.Enqueue(message);
        Interlocked.Increment(ref _barsQueueLength);
        _barsSignal.Release();
        return true;
    }

    public bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload)
    {
        if (Volatile.Read(ref _footprintQueueLength) >= _maxFootprintQueueLength)
        {
            Interlocked.Increment(ref _historyFootprintDroppedCount);
            _lastFailureUtc = DateTime.UtcNow;
            _lastTransportError = $"HistoryFootprint queue full ({_maxFootprintQueueLength}); dropped payload.";
            _warnLogger(_lastTransportError);
            return false;
        }

        var message = new HistoryFootprintMessage(payload, DateTime.UtcNow);
        _footprintQueue.Enqueue(message);
        Interlocked.Increment(ref _footprintQueueLength);
        _footprintSignal.Release();
        return true;
    }

    public async Task<AdapterBackfillDispatchResponsePayload?> PollBackfillCommandAsync(
        string instrumentSymbol,
        string? chartInstanceId,
        string? contractSymbol,
        string? rootSymbol,
        CancellationToken ct)
    {
        Interlocked.Increment(ref _backfillCommandPolledCount);

        var endpoint = $"/api/v1/adapter/backfill-command?instrument_symbol={Uri.EscapeDataString(instrumentSymbol)}";
        if (!string.IsNullOrEmpty(chartInstanceId))
        {
            endpoint += $"&chart_instance_id={Uri.EscapeDataString(chartInstanceId)}";
        }
        if (!string.IsNullOrWhiteSpace(contractSymbol))
        {
            endpoint += $"&contract_symbol={Uri.EscapeDataString(contractSymbol)}";
        }
        if (!string.IsNullOrWhiteSpace(rootSymbol))
        {
            endpoint += $"&root_symbol={Uri.EscapeDataString(rootSymbol)}";
        }

        try
        {
            _lastAttemptUtc = DateTime.UtcNow;
            using var request = new HttpRequestMessage(HttpMethod.Get, endpoint);
            using var response = await _backfillCommandClient.SendAsync(request, ct).ConfigureAwait(false);

            if (response.StatusCode == System.Net.HttpStatusCode.NoContent)
            {
                _infoLogger("PollBackfillCommandAsync: no pending backfill command.");
                return null;
            }

            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                _warnLogger($"PollBackfillCommandAsync: HTTP {(int)response.StatusCode} - {body}");
                return null;
            }

            var json = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            var result = JsonSerializer.Deserialize<AdapterBackfillDispatchResponsePayload>(json, PayloadJson.Options);
            _infoLogger($"PollBackfillCommandAsync: received command {result?.Request?.RequestId ?? "null"}.");
            _lastSuccessfulPostUtc = DateTime.UtcNow;
            return result;
        }
        catch (OperationCanceledException)
        {
            return null;
        }
        catch (Exception ex)
        {
            _warnLogger($"PollBackfillCommandAsync failed: {ex.Message}");
            _lastFailureUtc = DateTime.UtcNow;
            _lastTransportError = ex.Message;
            return null;
        }
    }

    public async Task<bool> SendBackfillAckAsync(
        AdapterBackfillAcknowledgeRequestPayload ack,
        CancellationToken ct)
    {
        try
        {
            var json = JsonSerializer.Serialize(ack, PayloadJson.Options);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            _lastAttemptUtc = DateTime.UtcNow;

            using var response = await _backfillAckClient.PostAsync("/api/v1/adapter/backfill-ack", content, ct).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                _warnLogger($"SendBackfillAckAsync: HTTP {(int)response.StatusCode} - {body}");
                Interlocked.Increment(ref _backfillAckFailedCount);
                _lastFailureUtc = DateTime.UtcNow;
                return false;
            }

            Interlocked.Increment(ref _backfillAckPostedCount);
            _lastSuccessfulPostUtc = DateTime.UtcNow;
            _infoLogger($"SendBackfillAckAsync: acknowledged request {ack.RequestId}.");
            return true;
        }
        catch (OperationCanceledException)
        {
            return false;
        }
        catch (Exception ex)
        {
            _warnLogger($"SendBackfillAckAsync failed: {ex.Message}");
            Interlocked.Increment(ref _backfillAckFailedCount);
            _lastFailureUtc = DateTime.UtcNow;
            _lastTransportError = ex.Message;
            return false;
        }
    }

    public int HistoryBarsQueueLength => Volatile.Read(ref _barsQueueLength);

    public int HistoryFootprintQueueLength => Volatile.Read(ref _footprintQueueLength);

    public int HistoryBarsDroppedCount => Volatile.Read(ref _historyBarsDroppedCount);

    public int HistoryFootprintDroppedCount => Volatile.Read(ref _historyFootprintDroppedCount);

    public int HistoryBarsSentCount => Volatile.Read(ref _historyBarsSentCount);

    public int HistoryBarsFailedCount => Volatile.Read(ref _historyBarsFailedCount);

    public int HistoryFootprintSentCount => Volatile.Read(ref _historyFootprintSentCount);

    public int HistoryFootprintFailedCount => Volatile.Read(ref _historyFootprintFailedCount);

    public int BackfillCommandPolledCount => Volatile.Read(ref _backfillCommandPolledCount);

    public int BackfillAckPostedCount => Volatile.Read(ref _backfillAckPostedCount);

    public int BackfillAckFailedCount => Volatile.Read(ref _backfillAckFailedCount);

    public DateTime? LastAttemptUtc => _lastAttemptUtc;

    public DateTime? LastSuccessfulPostUtc => _lastSuccessfulPostUtc;

    public DateTime? LastFailureUtc => _lastFailureUtc;

    public string LastTransportError => _lastTransportError;

    public HistoryTransportStatus GetStatus()
    {
        return new HistoryTransportStatus
        {
            TotalQueueLength = HistoryBarsQueueLength + HistoryFootprintQueueLength,
            TotalDroppedCount = HistoryBarsDroppedCount + HistoryFootprintDroppedCount,
            ConsecutiveSendFailures = 0,
            LastAttemptUtc = LastAttemptUtc,
            LastSuccessfulPostUtc = LastSuccessfulPostUtc,
            LastFailureUtc = LastFailureUtc,
            LastTransportError = LastTransportError,
            HistoryBarsQueueLength = HistoryBarsQueueLength,
            HistoryFootprintQueueLength = HistoryFootprintQueueLength,
            HistoryBarsDroppedCount = HistoryBarsDroppedCount,
            HistoryFootprintDroppedCount = HistoryFootprintDroppedCount,
            HistoryBarsSentCount = HistoryBarsSentCount,
            HistoryBarsFailedCount = HistoryBarsFailedCount,
            HistoryFootprintSentCount = HistoryFootprintSentCount,
            HistoryFootprintFailedCount = HistoryFootprintFailedCount,
            BackfillCommandPolledCount = BackfillCommandPolledCount,
            BackfillAckPostedCount = BackfillAckPostedCount,
            BackfillAckFailedCount = BackfillAckFailedCount,
            Summary = $"HistoryTransport: bars_q={HistoryBarsQueueLength}, fp_q={HistoryFootprintQueueLength}, " +
                      $"bars_sent={HistoryBarsSentCount}, bars_failed={HistoryBarsFailedCount}, " +
                      $"bars_dropped={HistoryBarsDroppedCount}, fp_sent={HistoryFootprintSentCount}, " +
                      $"fp_failed={HistoryFootprintFailedCount}, fp_dropped={HistoryFootprintDroppedCount}, " +
                      $"poll={BackfillCommandPolledCount}, ack_ok={BackfillAckPostedCount}, ack_fail={BackfillAckFailedCount}",
        };
    }

    public void Dispose()
    {
        _cts.Cancel();
        _barsSignal.Release();
        _footprintSignal.Release();
        try
        {
            Task.WaitAll(_barsPumpTask, _footprintPumpTask);
        }
        catch (AggregateException)
        {
        }
        finally
        {
            _barsSignal.Dispose();
            _footprintSignal.Dispose();
            _barsRateLimit.Dispose();
            _footprintRateLimit.Dispose();
            _cts.Dispose();
            _barsClient.Dispose();
            _footprintClient.Dispose();
            _backfillCommandClient.Dispose();
            _backfillAckClient.Dispose();
        }
    }

    private async Task BarsPumpAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            try
            {
                await _barsSignal.WaitAsync(_cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            while (_barsQueue.TryDequeue(out var message))
            {
                Interlocked.Decrement(ref _barsQueueLength);

                _lastBarsSentTime = await ApplyRateLimitAsync(_barsRateLimit, _rateLimitBarsPerSecond, _lastBarsSentTime).ConfigureAwait(false);

                try
                {
                    await PostBarsAsync(message, _cts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
                catch (Exception ex)
                {
                    _warnLogger($"HistoryBars send failed: {ex.Message}");
                }
            }
        }
    }

    private async Task FootprintPumpAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            try
            {
                await _footprintSignal.WaitAsync(_cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            while (_footprintQueue.TryDequeue(out var message))
            {
                Interlocked.Decrement(ref _footprintQueueLength);

                _lastFootprintSentTime = await ApplyRateLimitAsync(_footprintRateLimit, _rateLimitFootprintPerSecond, _lastFootprintSentTime).ConfigureAwait(false);

                try
                {
                    await PostFootprintAsync(message, _cts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
                catch (Exception ex)
                {
                    _warnLogger($"HistoryFootprint send failed: {ex.Message}");
                }
            }
        }
    }

    private async Task<DateTime> ApplyRateLimitAsync(SemaphoreSlim rateLimit, int itemsPerSecond, DateTime lastSentTime)
    {
        if (itemsPerSecond <= 0)
        {
            return lastSentTime;
        }

        var minInterval = TimeSpan.FromSeconds(1.0 / itemsPerSecond);
        var now = DateTime.UtcNow;
        var elapsed = now - lastSentTime;

        if (elapsed < minInterval)
        {
            await Task.Delay(minInterval - elapsed, _cts.Token).ConfigureAwait(false);
        }

        return DateTime.UtcNow;
    }

    private async Task PostBarsAsync(HistoryBarsMessage message, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(message.Payload, PayloadJson.Options);
        Exception? lastException = null;
        const int maxAttempts = 3;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            _lastAttemptUtc = DateTime.UtcNow;
            try
            {
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                using var response = await _barsClient.PostAsync(_historyBarsEndpoint, content, cancellationToken).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                {
                    var responseBody = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                    throw new InvalidOperationException($"HTTP {(int)response.StatusCode}: {responseBody}");
                }

                Interlocked.Increment(ref _historyBarsSentCount);
                _lastSuccessfulPostUtc = DateTime.UtcNow;
                _lastTransportError = string.Empty;
                _infoLogger($"HistoryBars delivered (attempt {attempt}).");
                return;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                lastException = ex;
                if (attempt < maxAttempts)
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
                    continue;
                }
            }
        }

        Interlocked.Increment(ref _historyBarsFailedCount);
        _lastFailureUtc = DateTime.UtcNow;
        _lastTransportError = lastException?.Message ?? "Unknown HistoryBars transport error.";
        throw lastException ?? new InvalidOperationException(_lastTransportError);
    }

    private async Task PostFootprintAsync(HistoryFootprintMessage message, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(message.Payload, PayloadJson.Options);
        Exception? lastException = null;
        const int maxAttempts = 3;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            _lastAttemptUtc = DateTime.UtcNow;
            try
            {
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                using var response = await _footprintClient.PostAsync(_historyFootprintEndpoint, content, cancellationToken).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                {
                    var responseBody = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                    throw new InvalidOperationException($"HTTP {(int)response.StatusCode}: {responseBody}");
                }

                Interlocked.Increment(ref _historyFootprintSentCount);
                _lastSuccessfulPostUtc = DateTime.UtcNow;
                _lastTransportError = string.Empty;
                _infoLogger($"HistoryFootprint delivered (attempt {attempt}).");
                return;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                lastException = ex;
                if (attempt < maxAttempts)
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
                    continue;
                }
            }
        }

        Interlocked.Increment(ref _historyFootprintFailedCount);
        _lastFailureUtc = DateTime.UtcNow;
        _lastTransportError = lastException?.Message ?? "Unknown HistoryFootprint transport error.";
        throw lastException ?? new InvalidOperationException(_lastTransportError);
    }

    private sealed record HistoryBarsMessage(HistoryBarsPayload Payload, DateTime EnqueuedAtUtc);
    private sealed record HistoryFootprintMessage(HistoryFootprintPayload Payload, DateTime EnqueuedAtUtc);
}

#endregion

#region Unified Adapter Transport (Delegates to Separate Transports)

internal sealed class BufferedHttpAdapterTransport : IAdapterTransport
{
    private readonly IRealtimeTransport _realtimeTransport;
    private readonly IHistoryTransport _historyTransport;
    private readonly Action<string> _infoLogger;
    private readonly Action<string> _warnLogger;

    public BufferedHttpAdapterTransport(
        Uri baseUri,
        string continuousEndpoint,
        string historyBarsEndpoint,
        string historyFootprintEndpoint,
        string triggerEndpoint,
        int maxQueueLength,
        Action<string> infoLogger,
        Action<string> warnLogger)
    {
        _infoLogger = infoLogger;
        _warnLogger = warnLogger;

        _realtimeTransport = new BufferedRealtimeTransport(
            baseUri, continuousEndpoint, triggerEndpoint, maxQueueLength, infoLogger, warnLogger);

        _historyTransport = new BufferedHistoryTransport(
            baseUri, historyBarsEndpoint, historyFootprintEndpoint,
            maxQueueLength, maxQueueLength, 100, 50,
            infoLogger, warnLogger);

        _infoLogger("BufferedHttpAdapterTransport initialized with separated realtime/history transports.");
    }

    public bool TryEnqueueContinuousState(ContinuousStatePayload payload)
        => _realtimeTransport.TryEnqueueContinuousState(payload);

    public bool TryEnqueueHistoryBars(HistoryBarsPayload payload)
        => _historyTransport.TryEnqueueHistoryBars(payload);

    public bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload)
        => _historyTransport.TryEnqueueHistoryFootprint(payload);

    public bool TryEnqueueTriggerBurst(TriggerBurstPayload payload)
        => _realtimeTransport.TryEnqueueTriggerBurst(payload);

    public async Task<AdapterBackfillDispatchResponsePayload?> PollBackfillCommandAsync(
        string instrumentSymbol,
        string? chartInstanceId,
        string? contractSymbol,
        string? rootSymbol,
        CancellationToken ct)
        => await _historyTransport.PollBackfillCommandAsync(
            instrumentSymbol,
            chartInstanceId,
            contractSymbol,
            rootSymbol,
            ct).ConfigureAwait(false);

    public async Task<bool> SendBackfillAckAsync(
        AdapterBackfillAcknowledgeRequestPayload ack,
        CancellationToken ct)
        => await _historyTransport.SendBackfillAckAsync(ack, ct).ConfigureAwait(false);

    public int QueueLength => _realtimeTransport.QueueLength + _historyTransport.HistoryBarsQueueLength + _historyTransport.HistoryFootprintQueueLength;

    public int DroppedMessageCount => _realtimeTransport.DroppedMessageCount + _historyTransport.HistoryBarsDroppedCount + _historyTransport.HistoryFootprintDroppedCount;

    public int ConsecutiveSendFailures => _realtimeTransport.ConsecutiveSendFailures;

    public DateTime? LastAttemptUtc => _realtimeTransport.LastAttemptUtc ?? _historyTransport.LastAttemptUtc;

    public DateTime? LastSuccessfulPostUtc => _realtimeTransport.LastSuccessfulPostUtc ?? _historyTransport.LastSuccessfulPostUtc;

    public DateTime? LastFailureUtc => _realtimeTransport.LastFailureUtc ?? _historyTransport.LastFailureUtc;

    public string LastTransportError
    {
        get
        {
            var rt = _realtimeTransport.LastTransportError;
            var ht = _historyTransport.LastTransportError;
            if (!string.IsNullOrEmpty(rt)) return $"Realtime: {rt}";
            if (!string.IsNullOrEmpty(ht)) return $"History: {ht}";
            return string.Empty;
        }
    }

    public TransportStatus GetStatus()
    {
        var rtStatus = _realtimeTransport.GetStatus();
        var htStatus = _historyTransport.GetStatus();
        return new TransportStatus
        {
            TotalQueueLength = QueueLength,
            TotalDroppedCount = DroppedMessageCount,
            ConsecutiveSendFailures = ConsecutiveSendFailures,
            LastAttemptUtc = LastAttemptUtc,
            LastSuccessfulPostUtc = LastSuccessfulPostUtc,
            LastFailureUtc = LastFailureUtc,
            LastTransportError = LastTransportError,
            Summary = $"AdapterTransport: realtime[{rtStatus.Summary}] | history[{htStatus.Summary}]",
        };
    }

    public void Dispose()
    {
        _realtimeTransport.Dispose();
        _historyTransport.Dispose();
    }
}

#endregion

internal static class PayloadJson
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };
}

internal sealed class TimedRingBuffer<T>
{
    private readonly object _sync = new();
    private readonly Func<T, DateTime> _timestampSelector;
    private readonly TimeSpan _retention;
    private readonly List<T> _items = new();

    public TimedRingBuffer(TimeSpan retention, Func<T, DateTime> timestampSelector)
    {
        _retention = retention;
        _timestampSelector = timestampSelector;
    }

    public void Add(T item)
    {
        lock (_sync)
        {
            _items.Add(item);
            PruneLocked(DateTime.UtcNow - _retention);
        }
    }

    public List<T> Snapshot(DateTime startInclusive, DateTime endInclusive)
    {
        lock (_sync)
        {
            PruneLocked(DateTime.UtcNow - _retention);
            return _items
                .Where(item =>
                {
                    var timestamp = _timestampSelector(item);
                    return timestamp >= startInclusive && timestamp <= endInclusive;
                })
                .ToList();
        }
    }

    private void PruneLocked(DateTime cutoff)
    {
        _items.RemoveAll(item => _timestampSelector(item) < cutoff);
    }
}

internal static class AtasReflection
{
    private static readonly ConcurrentDictionary<string, PropertyInfo?> PropertyCache = new(StringComparer.Ordinal);

    public static decimal? ReadDecimal(object? source, params string[] propertyNames)
    {
        var value = ReadValue(source, propertyNames);
        return value switch
        {
            null => null,
            decimal decimalValue => decimalValue,
            double doubleValue => Convert.ToDecimal(doubleValue),
            float floatValue => Convert.ToDecimal(floatValue),
            int intValue => intValue,
            long longValue => longValue,
            _ when decimal.TryParse(value.ToString(), out var parsed) => parsed,
            _ => null,
        };
    }

    public static int? ReadInt(object? source, params string[] propertyNames)
    {
        var value = ReadValue(source, propertyNames);
        return value switch
        {
            null => null,
            int intValue => intValue,
            long longValue => checked((int)longValue),
            decimal decimalValue => decimal.ToInt32(decimalValue),
            double doubleValue => Convert.ToInt32(doubleValue),
            _ when int.TryParse(value.ToString(), out var parsed) => parsed,
            _ => null,
        };
    }

    public static DateTime? ReadDateTime(object? source, params string[] propertyNames)
    {
        var value = ReadValue(source, propertyNames);
        return value switch
        {
            null => null,
            DateTime dateTime => NormalizeUtc(dateTime),
            DateTimeOffset offset => offset.UtcDateTime,
            _ when DateTime.TryParse(value.ToString(), out var parsed) => NormalizeUtc(parsed),
            _ => null,
        };
    }

    private static DateTime NormalizeUtc(DateTime value) => value.Kind switch
    {
        DateTimeKind.Utc => value,
        DateTimeKind.Unspecified => DateTime.SpecifyKind(value, DateTimeKind.Utc),
        _ => value.ToUniversalTime(),
    };

    public static string? ReadString(object? source, params string[] propertyNames)
    {
        var value = ReadValue(source, propertyNames);
        return value?.ToString();
    }

    public static bool? ReadBool(object? source, params string[] propertyNames)
    {
        var value = ReadValue(source, propertyNames);
        return value switch
        {
            null => null,
            bool boolValue => boolValue,
            _ when bool.TryParse(value.ToString(), out var parsed) => parsed,
            _ => null,
        };
    }

    public static CollectorSide ReadSide(object? source)
    {
        var isBid = ReadBool(source, "IsBid");
        if (isBid == true)
        {
            return CollectorSide.Buy;
        }

        var isAsk = ReadBool(source, "IsAsk");
        if (isAsk == true)
        {
            return CollectorSide.Sell;
        }

        var text = ReadString(source, "AggressorSide", "Direction", "Side", "Type")?.ToLowerInvariant() ?? string.Empty;
        if (text.Contains("buy") || text.Contains("bid"))
        {
            return CollectorSide.Buy;
        }

        if (text.Contains("sell") || text.Contains("ask"))
        {
            return CollectorSide.Sell;
        }

        return CollectorSide.Neutral;
    }

    public static decimal? ReadDecimalPath(object? source, params string[] propertyPath)
    {
        var value = ReadValuePath(source, propertyPath);
        return value switch
        {
            null => null,
            decimal decimalValue => decimalValue,
            double doubleValue => Convert.ToDecimal(doubleValue),
            float floatValue => Convert.ToDecimal(floatValue),
            int intValue => intValue,
            long longValue => longValue,
            _ when decimal.TryParse(value.ToString(), out var parsed) => parsed,
            _ => null,
        };
    }

    public static int? ReadIntPath(object? source, params string[] propertyPath)
    {
        var value = ReadValuePath(source, propertyPath);
        return value switch
        {
            null => null,
            int intValue => intValue,
            long longValue => checked((int)longValue),
            decimal decimalValue => decimal.ToInt32(decimal.Round(decimalValue, MidpointRounding.AwayFromZero)),
            double doubleValue => Convert.ToInt32(doubleValue),
            float floatValue => Convert.ToInt32(floatValue),
            _ when int.TryParse(value.ToString(), out var parsed) => parsed,
            _ => null,
        };
    }

    public static object? ReadObjectPath(object? source, params string[] propertyPath)
        => ReadValuePath(source, propertyPath);

    public static string? ReadStringPath(object? source, params string[] propertyPath)
    {
        var value = ReadValuePath(source, propertyPath);
        return value?.ToString();
    }

    public static IEnumerable<object> ReadSequence(object? source, params string[] memberNames)
    {
        if (source is null)
        {
            yield break;
        }

        var type = source.GetType();
        foreach (var memberName in memberNames)
        {
            var property = type.GetProperty(memberName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase);
            var propertyValue = property?.GetValue(source);
            if (propertyValue is IEnumerable enumerable and not string)
            {
                foreach (var item in enumerable)
                {
                    if (item is not null)
                    {
                        yield return item;
                    }
                }
                yield break;
            }

            var method = type.GetMethod(memberName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase, Type.DefaultBinder, Type.EmptyTypes, null);
            var methodValue = method?.Invoke(source, null);
            if (methodValue is IEnumerable methodEnumerable and not string)
            {
                foreach (var item in methodEnumerable)
                {
                    if (item is not null)
                    {
                        yield return item;
                    }
                }
                yield break;
            }
        }
    }

    private static object? ReadValue(object? source, params string[] propertyNames)
    {
        if (source is null)
        {
            return null;
        }

        var type = source.GetType();
        foreach (var propertyName in propertyNames)
        {
            var cacheKey = $"{type.FullName}:{propertyName}";
            var property = PropertyCache.GetOrAdd(
                cacheKey,
                _ => type.GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase));
            if (property is null)
            {
                continue;
            }

            return property.GetValue(source);
        }

        return null;
    }

    private static object? ReadValuePath(object? source, params string[] propertyPath)
    {
        if (source is null || propertyPath.Length == 0)
        {
            return null;
        }

        var current = source;
        foreach (var propertyName in propertyPath)
        {
            if (current is null)
            {
                return null;
            }

            var type = current.GetType();
            var cacheKey = $"{type.FullName}:{string.Join(".", propertyPath)}:{propertyName}";
            var property = PropertyCache.GetOrAdd(
                cacheKey,
                _ => type.GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase));
            if (property is null)
            {
                return null;
            }

            current = property.GetValue(current);
        }

        return current;
    }
}

internal sealed class TradeAccumulatorState
{
    public DateTime WindowStartedAtUtc { get; private set; } = DateTime.UtcNow;

    public int TradeCount { get; private set; }

    public int Volume { get; private set; }

    public int AggressiveBuyVolume { get; private set; }

    public int AggressiveSellVolume { get; private set; }

    public int NetDelta { get; private set; }

    public void Observe(CollectorSide side, int size)
    {
        TradeCount += 1;
        Volume += size;

        if (side == CollectorSide.Buy)
        {
            AggressiveBuyVolume += size;
            NetDelta += size;
        }
        else if (side == CollectorSide.Sell)
        {
            AggressiveSellVolume += size;
            NetDelta -= size;
        }
    }

    public TradeSummaryPayload ToPayload() => new()
    {
        TradeCount = TradeCount,
        Volume = Volume,
        AggressiveBuyVolume = AggressiveBuyVolume,
        AggressiveSellVolume = AggressiveSellVolume,
        NetDelta = NetDelta,
    };

    public void Reset(DateTime windowStartedAtUtc)
    {
        WindowStartedAtUtc = windowStartedAtUtc;
        TradeCount = 0;
        Volume = 0;
        AggressiveBuyVolume = 0;
        AggressiveSellVolume = 0;
        NetDelta = 0;
    }
}

internal sealed class SecondAccumulatorState
{
    public DateTime SecondStartedAtUtc { get; }

    public decimal Open { get; private set; }

    public decimal High { get; private set; }

    public decimal Low { get; private set; }

    public decimal Close { get; private set; }

    public int TradeCount { get; private set; }

    public int Volume { get; private set; }

    public int Delta { get; private set; }

    public decimal? BestBid { get; private set; }

    public decimal? BestAsk { get; private set; }

    public double? DepthImbalance { get; set; }

    public SecondAccumulatorState(DateTime secondStartedAtUtc, decimal initialPrice)
    {
        SecondStartedAtUtc = secondStartedAtUtc;
        Open = initialPrice;
        High = initialPrice;
        Low = initialPrice;
        Close = initialPrice;
    }

    public void ObservePrice(decimal price)
    {
        if (TradeCount == 0 && Volume == 0 && Open == 0m)
        {
            Open = price;
            High = price;
            Low = price;
        }

        if (price > High)
        {
            High = price;
        }

        if (price < Low)
        {
            Low = price;
        }

        Close = price;
    }

    public void ObserveTrade(CollectorSide side, int size, decimal price)
    {
        ObservePrice(price);
        TradeCount += 1;
        Volume += size;
        if (side == CollectorSide.Buy)
        {
            Delta += size;
        }
        else if (side == CollectorSide.Sell)
        {
            Delta -= size;
        }
    }

    public void ObserveBestBid(decimal? bestBid)
    {
        BestBid = bestBid;
    }

    public void ObserveBestAsk(decimal? bestAsk)
    {
        BestAsk = bestAsk;
    }

    public SecondFeaturePayload ToPayload() => new()
    {
        SecondStartedAt = SecondStartedAtUtc,
        SecondEndedAt = SecondStartedAtUtc.AddSeconds(1).AddTicks(-1),
        Open = (double)Open,
        High = (double)High,
        Low = (double)Low,
        Close = (double)Close,
        TradeCount = TradeCount,
        Volume = Volume,
        Delta = Delta,
        BestBid = BestBid is null ? null : (double)BestBid.Value,
        BestAsk = BestAsk is null ? null : (double)BestAsk.Value,
        DepthImbalance = DepthImbalance,
    };
}

internal sealed class SignificantLiquidityTrackState
{
    public required string TrackId { get; init; }

    public required CollectorSide Side { get; init; }

    public required decimal Price { get; init; }

    public required DateTime FirstObservedAtUtc { get; init; }

    public DateTime LastObservedAtUtc { get; set; }

    public int CurrentSize { get; set; }

    public int MaxSeenSize { get; set; }

    public string Status { get; set; } = "active";

    public int TouchCount { get; set; }

    public int ExecutedVolumeEstimate { get; set; }

    public int ReplenishmentCount { get; set; }

    public int PullCount { get; set; }

    public int MoveCount { get; set; }

    public int PriceReactionTicks { get; set; }

    public double HeatScore { get; set; }

    public bool WasNearPrice { get; set; }

    public SignificantLiquidityPayload ToPayload(decimal currentPrice, decimal tickSize) => new()
    {
        TrackId = TrackId,
        Side = Side.ToPayloadString(),
        Price = (double)Price,
        CurrentSize = CurrentSize,
        MaxSeenSize = MaxSeenSize,
        DistanceFromPriceTicks = PriceMath.ToTicks(Math.Abs(currentPrice - Price), tickSize),
        FirstObservedAt = FirstObservedAtUtc,
        LastObservedAt = LastObservedAtUtc,
        Status = Status,
        TouchCount = TouchCount,
        ExecutedVolumeEstimate = ExecutedVolumeEstimate,
        ReplenishmentCount = ReplenishmentCount,
        PullCount = PullCount,
        MoveCount = MoveCount,
        PriceReactionTicks = PriceReactionTicks,
        HeatScore = HeatScore,
    };
}

internal sealed class HarvestState
{
    public required string ResponseId { get; init; }

    public required string HarvestSubjectId { get; init; }

    public required string HarvestSubjectKind { get; init; }

    public required CollectorSide HarvestSide { get; init; }

    public required DateTime HarvestCompletedAtUtc { get; init; }

    public required decimal HarvestedPriceLow { get; init; }

    public required decimal HarvestedPriceHigh { get; init; }

    public double CompletionRatio { get; set; } = 1.0;

    public decimal HighestAfterCompletion { get; set; }

    public decimal LowestAfterCompletion { get; set; }

    public int PostHarvestDelta { get; set; }

    public DateTime? FirstPullbackAtUtc { get; set; }

    public DateTime? FirstReversalAtUtc { get; set; }

    public bool ReachedNextOpposingLiquidity { get; set; }

    public decimal? NextOpposingLiquidityPrice { get; set; }
}

internal static class PriceMath
{
    public static int ToTicks(decimal distance, decimal tickSize)
    {
        if (tickSize <= 0m)
        {
            return 0;
        }

        return (int)Math.Round(distance / tickSize, MidpointRounding.AwayFromZero);
    }

    public static decimal RoundToTick(decimal value, decimal tickSize)
    {
        if (tickSize <= 0m)
        {
            return value;
        }

        return Math.Round(value / tickSize, MidpointRounding.AwayFromZero) * tickSize;
    }
}

internal static class CollectorSideExtensions
{
    public static string ToPayloadString(this CollectorSide side) => side switch
    {
        CollectorSide.Buy => "buy",
        CollectorSide.Sell => "sell",
        _ => "neutral",
    };
}
