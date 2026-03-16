using System.Collections.Concurrent;
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

internal interface IAdapterTransport : IDisposable
{
    bool TryEnqueueContinuousState(ContinuousStatePayload payload);

    bool TryEnqueueHistoryBars(HistoryBarsPayload payload);

    bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload);

    bool TryEnqueueTriggerBurst(TriggerBurstPayload payload);
}

internal sealed class BufferedHttpAdapterTransport : IAdapterTransport
{
    private readonly HttpClient _httpClient;
    private readonly string _continuousEndpoint;
    private readonly string _historyBarsEndpoint;
    private readonly string _historyFootprintEndpoint;
    private readonly string _triggerEndpoint;
    private readonly int _maxQueueLength;
    private readonly Action<string> _infoLogger;
    private readonly Action<string> _warnLogger;
    private readonly ConcurrentQueue<OutboundMessage> _queue = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _pumpTask;
    private readonly SemaphoreSlim _signal = new(0);
    private int _queueLength;

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
        _continuousEndpoint = continuousEndpoint;
        _historyBarsEndpoint = historyBarsEndpoint;
        _historyFootprintEndpoint = historyFootprintEndpoint;
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
    }

    public bool TryEnqueueContinuousState(ContinuousStatePayload payload)
        => TryEnqueue(new OutboundMessage(_continuousEndpoint, payload, false));

    public bool TryEnqueueHistoryBars(HistoryBarsPayload payload)
        => TryEnqueue(new OutboundMessage(_historyBarsEndpoint, payload, false));

    public bool TryEnqueueHistoryFootprint(HistoryFootprintPayload payload)
        => TryEnqueue(new OutboundMessage(_historyFootprintEndpoint, payload, false));

    public bool TryEnqueueTriggerBurst(TriggerBurstPayload payload)
        => TryEnqueue(new OutboundMessage(_triggerEndpoint, payload, true));

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
            // Best-effort shutdown only.
        }
        finally
        {
            _signal.Dispose();
            _cts.Dispose();
            _httpClient.Dispose();
        }
    }

    private bool TryEnqueue(OutboundMessage message)
    {
        if (!message.HighPriority && Volatile.Read(ref _queueLength) >= _maxQueueLength)
        {
            _warnLogger($"Adapter queue full ({_maxQueueLength}). Dropping low-priority continuous_state payload.");
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
                    _warnLogger($"Adapter send failed for '{message.Endpoint}': {ex.Message}");
                }
            }
        }
    }

    private async Task PostAsync(OutboundMessage message, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(message.Payload, PayloadJson.Options);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var response = await _httpClient.PostAsync(message.Endpoint, content, cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            var responseBody = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
            throw new InvalidOperationException(
                $"HTTP {(int)response.StatusCode} for {message.Endpoint}: {responseBody}");
        }

        _infoLogger($"Adapter payload delivered to {message.Endpoint}.");
    }

    private sealed record OutboundMessage(string Endpoint, object Payload, bool HighPriority);
}

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
            DateTime dateTime => dateTime.Kind == DateTimeKind.Utc ? dateTime : dateTime.ToUniversalTime(),
            DateTimeOffset offset => offset.UtcDateTime,
            _ when DateTime.TryParse(value.ToString(), out var parsed) => parsed.Kind == DateTimeKind.Utc ? parsed : parsed.ToUniversalTime(),
            _ => null,
        };
    }

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
