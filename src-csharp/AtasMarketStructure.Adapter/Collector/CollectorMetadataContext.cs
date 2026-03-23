using System.Globalization;
using ATAS.Indicators;
using AtasMarketStructure.Adapter.Contracts;

namespace AtasMarketStructure.Adapter.Collector;

internal sealed class ChartIdentity
{
    public string RootSymbol { get; init; } = string.Empty;

    public string ContractSymbol { get; init; } = string.Empty;

    public string DisplaySymbol { get; init; } = string.Empty;

    public string Venue { get; init; } = string.Empty;

    public string Currency { get; init; } = string.Empty;

    public decimal TickSize { get; init; }

    public string ChartInstanceId { get; init; } = string.Empty;

    public string DisplayTimeframe { get; init; } = string.Empty;
}

internal sealed class ResolvedTimeContext
{
    public string? InstrumentTimezoneValue { get; init; }

    public string InstrumentTimezoneSource { get; init; } = "unavailable";

    public TimeZoneInfo? InstrumentTimeZone { get; init; }

    public int? InstrumentUtcOffsetMinutes { get; init; }

    public string ChartDisplayTimezoneMode { get; init; } = "unknown";

    public string ChartDisplayTimezoneSource { get; init; } = "unavailable";

    public string? ChartDisplayTimezoneName { get; init; }

    public TimeZoneInfo? ChartDisplayTimeZone { get; init; }

    public int? ChartDisplayUtcOffsetMinutes { get; init; }

    public string CollectorLocalTimezoneName { get; init; } = TimeZoneInfo.Local.Id;

    public int CollectorLocalUtcOffsetMinutes { get; init; }

    public string TimestampBasis { get; init; } = "collector_local_timezone";

    public string StartedAtTimeSource { get; init; } = "collector_local_timezone";

    public string TimezoneCaptureConfidence { get; init; } = "unknown";

    public TimeContextPayload ToPayload() => new()
    {
        InstrumentTimezoneValue = InstrumentTimezoneValue,
        InstrumentTimezoneSource = InstrumentTimezoneSource,
        ChartDisplayTimezoneMode = ChartDisplayTimezoneMode,
        ChartDisplayTimezoneSource = ChartDisplayTimezoneSource,
        ChartDisplayTimezoneName = ChartDisplayTimezoneName,
        ChartDisplayUtcOffsetMinutes = ChartDisplayUtcOffsetMinutes,
        CollectorLocalTimezoneName = CollectorLocalTimezoneName,
        CollectorLocalUtcOffsetMinutes = CollectorLocalUtcOffsetMinutes,
        TimestampBasis = TimestampBasis,
        StartedAtOutputTimezone = "UTC",
        StartedAtTimeSource = StartedAtTimeSource,
        TimezoneCaptureConfidence = TimezoneCaptureConfidence,
    };
}

internal static class CollectorMetadataResolver
{
    private static readonly string[][] ContractSymbolCandidatePaths =
    {
        new[] { "Instrument" },
        new[] { "InstrumentInfo", "Instrument" },
        new[] { "DataProvider", "Instrument" },
        new[] { "InstrumentInfo", "Instrument", "Instrument" },
        new[] { "Security", "Name" },
        new[] { "Security", "Symbol" },
        new[] { "SourceDataSeries", "SourceName" },
        new[] { "SourceDataSeries", "FullName" },
        new[] { "DataProvider", "Instrument", "Name" },
        new[] { "DataProvider", "Instrument", "Symbol" },
    };

    private static readonly string[][] DisplaySymbolCandidatePaths =
    {
        new[] { "ChartInfo", "Symbol" },
        new[] { "ChartInfo", "Instrument" },
        new[] { "Chart", "Symbol" },
        new[] { "Chart", "Instrument" },
        new[] { "SourceDataSeries", "SourceName" },
        new[] { "SourceDataSeries", "FullName" },
        new[] { "Security", "Name" },
        new[] { "Security", "Symbol" },
        new[] { "InstrumentInfo", "Instrument" },
        new[] { "Instrument" },
    };

    private static readonly string[][] RootSymbolCandidatePaths =
    {
        new[] { "InstrumentInfo", "RootSymbol" },
        new[] { "Instrument", "RootSymbol" },
        new[] { "Security", "RootSymbol" },
        new[] { "DataProvider", "Instrument", "RootSymbol" },
    };

    private static readonly string[][] TickSizeCandidatePaths =
    {
        new[] { "TickSize" },
        new[] { "InstrumentInfo", "TickSize" },
        new[] { "InstrumentInfo", "Instrument", "TickSize" },
        new[] { "Instrument", "TickSize" },
        new[] { "Security", "TickSize" },
        new[] { "SourceDataSeries", "TickSize" },
        new[] { "DataProvider", "Instrument", "TickSize" },
    };

    private static readonly string[][] VenueCandidatePaths =
    {
        new[] { "InstrumentInfo", "Exchange" },
        new[] { "InstrumentInfo", "Instrument", "Exchange" },
        new[] { "Instrument", "Exchange" },
        new[] { "Security", "Exchange" },
        new[] { "Security", "Market" },
        new[] { "DataProvider", "Instrument", "Exchange" },
        new[] { "DataProvider", "Instrument", "Market" },
    };

    private static readonly string[][] CurrencyCandidatePaths =
    {
        new[] { "InstrumentInfo", "Currency" },
        new[] { "InstrumentInfo", "Instrument", "Currency" },
        new[] { "Instrument", "Currency" },
        new[] { "Security", "Currency" },
        new[] { "DataProvider", "Instrument", "Currency" },
    };

    private static readonly string[][] ChartInstanceIdCandidatePaths =
    {
        new[] { "ChartInfo", "Id" },
        new[] { "ChartInfo", "ChartId" },
        new[] { "Chart", "Id" },
        new[] { "Chart", "ChartId" },
        new[] { "Container", "Id" },
        new[] { "Container", "ChartId" },
        new[] { "Panel", "Id" },
        new[] { "Panel", "ChartId" },
    };

    private static readonly string[][] DisplayTimeframeCandidatePaths =
    {
        new[] { "ChartInfo", "TimeFrame" },
        new[] { "ChartInfo", "Timeframe" },
        new[] { "TimeFrame" },
        new[] { "Timeframe" },
        new[] { "SourceDataSeries", "TimeFrame" },
        new[] { "SourceDataSeries", "Interval" },
        new[] { "DataProvider", "TimeFrame" },
        new[] { "DataProvider", "Interval" },
        new[] { "Security", "TimeFrame" },
    };

    private static readonly string[][] InstrumentTimezoneCandidatePaths =
    {
        new[] { "InstrumentInfo", "TimeZone" },
        new[] { "InstrumentInfo", "Timezone" },
        new[] { "InstrumentInfo", "Instrument", "TimeZone" },
        new[] { "InstrumentInfo", "Instrument", "Timezone" },
        new[] { "Instrument", "TimeZone" },
        new[] { "Instrument", "Timezone" },
        new[] { "Security", "TimeZone" },
        new[] { "Security", "Timezone" },
        new[] { "DataProvider", "Instrument", "TimeZone" },
        new[] { "DataProvider", "Instrument", "Timezone" },
    };

    private static readonly string[][] ChartDisplayTimezoneModeCandidatePaths =
    {
        new[] { "ChartInfo", "DisplayTimeZoneMode" },
        new[] { "ChartInfo", "TimeZoneMode" },
        new[] { "Chart", "DisplayTimeZoneMode" },
        new[] { "Chart", "TimeZoneMode" },
        new[] { "Container", "DisplayTimeZoneMode" },
        new[] { "Container", "TimeZoneMode" },
        new[] { "TimeZoneMode" },
    };

    private static readonly string[][] ChartDisplayTimezoneNameCandidatePaths =
    {
        new[] { "ChartInfo", "DisplayTimeZone" },
        new[] { "ChartInfo", "TimeZone" },
        new[] { "ChartInfo", "Timezone" },
        new[] { "Chart", "DisplayTimeZone" },
        new[] { "Chart", "TimeZone" },
        new[] { "Chart", "Timezone" },
        new[] { "Container", "DisplayTimeZone" },
        new[] { "Container", "TimeZone" },
        new[] { "Container", "Timezone" },
        new[] { "DisplayTimeZone" },
    };

    private static readonly string[][] ChartDisplayUtcOffsetCandidatePaths =
    {
        new[] { "ChartInfo", "DisplayUtcOffsetMinutes" },
        new[] { "ChartInfo", "UtcOffsetMinutes" },
        new[] { "Chart", "DisplayUtcOffsetMinutes" },
        new[] { "Chart", "UtcOffsetMinutes" },
        new[] { "Container", "DisplayUtcOffsetMinutes" },
        new[] { "Container", "UtcOffsetMinutes" },
        new[] { "UtcOffsetMinutes" },
        new[] { "TimeZoneOffsetMinutes" },
        new[] { "TimeZoneOffset" },
    };

    private static readonly HashSet<string> InvalidSymbolCandidates = new(StringComparer.OrdinalIgnoreCase)
    {
        "BARS",
        "BARS(TRUE)",
        "BARS,FALSE",
        "CLOSE",
        "OPEN",
        "HIGH",
        "LOW",
        "BID",
        "ASK",
        "VOLUME",
        "DELTA",
        "DOM",
        "MBO",
        "CVD",
        "EMA",
        "VWAP",
        "TWAP",
        "PRICE",
        "VALUE",
        "SOURCE",
        "SERIES",
        "INDICATOR",
        "CLUSTER",
        "FOOTPRINT",
        "PROPERTIES",
        "CUSTOM",
        "TRUE",
        "FALSE",
    };

    private static readonly char[] IdentifierUnsafeChars = { ' ', ':', '/', '\\', '\t', '\r', '\n' };

    public static ChartIdentity ResolveChartIdentity(
        Indicator indicator,
        string? symbolOverride,
        decimal tickSizeOverride,
        string? fallbackVenue,
        string? fallbackCurrency,
        Func<TimeSpan> inferBarSpan)
    {
        var overrideSymbol = NormalizeSymbolCandidate(symbolOverride);
        var contractSymbol = ResolveFirstString(indicator, ContractSymbolCandidatePaths, NormalizeSymbolCandidate);
        var displaySymbol = overrideSymbol
            ?? ResolveFirstString(indicator, DisplaySymbolCandidatePaths, NormalizeSymbolCandidate)
            ?? contractSymbol;
        contractSymbol ??= overrideSymbol ?? displaySymbol ?? "UNKNOWN";
        displaySymbol ??= contractSymbol;

        var rootSymbol = ResolveFirstString(indicator, RootSymbolCandidatePaths, NormalizeSymbolCandidate)
            ?? ParseRootSymbol(displaySymbol)
            ?? ParseRootSymbol(contractSymbol)
            ?? displaySymbol
            ?? contractSymbol;
        var venue = ResolveFirstString(indicator, VenueCandidatePaths, NormalizeFreeText)
            ?? NormalizeFreeText(fallbackVenue)
            ?? string.Empty;
        var currency = ResolveFirstString(indicator, CurrencyCandidatePaths, NormalizeFreeText)
            ?? NormalizeFreeText(fallbackCurrency)
            ?? string.Empty;
        var tickSize = tickSizeOverride > 0m
            ? tickSizeOverride
            : ResolveFirstDecimal(indicator, TickSizeCandidatePaths);
        var displayTimeframe = ResolveFirstString(indicator, DisplayTimeframeCandidatePaths, NormalizeDisplayTimeframe)
            ?? NormalizeDisplayTimeframe(FormatTimeframe(inferBarSpan()))
            ?? "unknown";
        var detectedChartInstanceId = ResolveFirstString(indicator, ChartInstanceIdCandidatePaths, NormalizeIdentifier);
        var chartInstanceId = !string.IsNullOrWhiteSpace(detectedChartInstanceId)
            ? detectedChartInstanceId
            : BuildFallbackChartInstanceId(contractSymbol, displayTimeframe, venue, currency);

        return new ChartIdentity
        {
            RootSymbol = rootSymbol,
            ContractSymbol = contractSymbol,
            DisplaySymbol = displaySymbol,
            Venue = venue,
            Currency = currency,
            TickSize = tickSize,
            ChartInstanceId = chartInstanceId,
            DisplayTimeframe = displayTimeframe,
        };
    }

    public static ResolvedTimeContext ResolveTimeContext(Indicator indicator, DateTime observedAtUtc)
    {
        var localZone = TimeZoneInfo.Local;
        var localOffsetMinutes = (int)Math.Round(localZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero);

        var instrumentTimezoneRaw = ResolveFirstObject(indicator, InstrumentTimezoneCandidatePaths);
        var instrumentTimezoneValue = NormalizeFreeText(DescribeTimeZoneValue(instrumentTimezoneRaw));
        var instrumentTimezoneSource = instrumentTimezoneRaw is null ? "unavailable" : "metadata";
        var instrumentTimeZone = TryResolveTimeZoneInfo(instrumentTimezoneRaw, out var instrumentUtcOffsetMinutes)
            ?? TryResolveTimeZoneInfo(instrumentTimezoneValue, out instrumentUtcOffsetMinutes);

        var rawChartMode = ResolveFirstObject(indicator, ChartDisplayTimezoneModeCandidatePaths);
        var chartMode = NormalizeTimeZoneMode(rawChartMode);
        var rawChartTimezone = ResolveFirstObject(indicator, ChartDisplayTimezoneNameCandidatePaths);
        var rawChartTimezoneName = NormalizeFreeText(DescribeTimeZoneValue(rawChartTimezone));
        var chartDisplayTimeZone = TryResolveTimeZoneInfo(rawChartTimezone, out var chartDisplayFixedOffsetMinutes)
            ?? TryResolveTimeZoneInfo(rawChartTimezoneName, out chartDisplayFixedOffsetMinutes);
        var directChartOffsetMinutes = ResolveFirstUtcOffsetMinutes(indicator, ChartDisplayUtcOffsetCandidatePaths);

        string chartDisplayTimezoneSource;
        string timestampBasis;
        string startedAtTimeSource;
        string timezoneCaptureConfidence;
        string? chartDisplayTimezoneName;
        int? chartDisplayUtcOffsetMinutes;

        if (chartDisplayTimeZone is not null || !string.IsNullOrWhiteSpace(rawChartTimezoneName) || directChartOffsetMinutes is not null)
        {
            chartMode ??= chartDisplayTimeZone is not null || !string.IsNullOrWhiteSpace(rawChartTimezoneName)
                ? "named_zone"
                : "custom_offset";
            chartDisplayUtcOffsetMinutes = directChartOffsetMinutes
                ?? chartDisplayFixedOffsetMinutes
                ?? (chartDisplayTimeZone is not null
                    ? (int)Math.Round(chartDisplayTimeZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero)
                    : null);
            chartDisplayTimezoneName = rawChartTimezoneName
                ?? chartDisplayTimeZone?.Id
                ?? FormatUtcOffsetName(chartDisplayUtcOffsetMinutes);
            chartDisplayTimezoneSource = "direct_metadata";
            timestampBasis = "chart_display_timezone_direct";
            startedAtTimeSource = "chart_display_timezone_direct";
            timezoneCaptureConfidence = "high";
        }
        else if (string.Equals(chartMode, "utc", StringComparison.Ordinal))
        {
            chartDisplayTimezoneName = "UTC";
            chartDisplayUtcOffsetMinutes = 0;
            chartDisplayTimezoneSource = rawChartMode is null ? "derived_utc" : "direct_metadata";
            timestampBasis = rawChartMode is null ? "chart_display_timezone_derived_utc" : "chart_display_timezone_direct";
            startedAtTimeSource = timestampBasis;
            timezoneCaptureConfidence = rawChartMode is null ? "medium" : "high";
        }
        else if (string.Equals(chartMode, "instrument", StringComparison.Ordinal)
            && (instrumentTimeZone is not null || instrumentUtcOffsetMinutes is not null || !string.IsNullOrWhiteSpace(instrumentTimezoneValue)))
        {
            chartDisplayTimezoneName = instrumentTimeZone?.Id
                ?? instrumentTimezoneValue
                ?? FormatUtcOffsetName(instrumentUtcOffsetMinutes);
            chartDisplayUtcOffsetMinutes = instrumentUtcOffsetMinutes
                ?? (instrumentTimeZone is not null
                    ? (int)Math.Round(instrumentTimeZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero)
                    : null);
            chartDisplayTimezoneSource = "derived_from_instrument";
            timestampBasis = "chart_display_timezone_derived_from_instrument";
            startedAtTimeSource = "chart_display_timezone_derived_from_instrument";
            timezoneCaptureConfidence = instrumentTimeZone is not null || instrumentUtcOffsetMinutes is not null ? "medium" : "low";
        }
        else if (string.Equals(chartMode, "local", StringComparison.Ordinal))
        {
            chartDisplayTimezoneName = localZone.Id;
            chartDisplayUtcOffsetMinutes = localOffsetMinutes;
            chartDisplayTimezoneSource = rawChartMode is null ? "collector_local_fallback" : "derived_from_local_mode";
            timestampBasis = rawChartMode is null ? "collector_local_timezone_fallback" : "chart_display_timezone_derived_from_local";
            startedAtTimeSource = timestampBasis;
            timezoneCaptureConfidence = rawChartMode is null ? "low" : "medium";
        }
        else if (instrumentTimeZone is not null || instrumentUtcOffsetMinutes is not null || !string.IsNullOrWhiteSpace(instrumentTimezoneValue))
        {
            chartMode ??= "instrument";
            chartDisplayTimezoneName = instrumentTimeZone?.Id
                ?? instrumentTimezoneValue
                ?? FormatUtcOffsetName(instrumentUtcOffsetMinutes);
            chartDisplayUtcOffsetMinutes = instrumentUtcOffsetMinutes
                ?? (instrumentTimeZone is not null
                    ? (int)Math.Round(instrumentTimeZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero)
                    : null);
            chartDisplayTimezoneSource = "derived_from_instrument";
            timestampBasis = "instrument_timezone_direct";
            startedAtTimeSource = "instrument_timezone_direct";
            timezoneCaptureConfidence = "medium";
        }
        else
        {
            chartMode ??= "local";
            chartDisplayTimezoneName = localZone.Id;
            chartDisplayUtcOffsetMinutes = localOffsetMinutes;
            chartDisplayTimezoneSource = "collector_local_fallback";
            timestampBasis = "collector_local_timezone_fallback";
            startedAtTimeSource = "collector_local_timezone_fallback";
            timezoneCaptureConfidence = "low";
        }

        return new ResolvedTimeContext
        {
            InstrumentTimezoneValue = instrumentTimezoneValue,
            InstrumentTimezoneSource = instrumentTimezoneSource,
            InstrumentTimeZone = instrumentTimeZone,
            InstrumentUtcOffsetMinutes = instrumentUtcOffsetMinutes,
            ChartDisplayTimezoneMode = chartMode ?? "unknown",
            ChartDisplayTimezoneSource = chartDisplayTimezoneSource,
            ChartDisplayTimezoneName = chartDisplayTimezoneName,
            ChartDisplayTimeZone = chartDisplayTimeZone,
            ChartDisplayUtcOffsetMinutes = chartDisplayUtcOffsetMinutes,
            CollectorLocalTimezoneName = localZone.Id,
            CollectorLocalUtcOffsetMinutes = localOffsetMinutes,
            TimestampBasis = timestampBasis,
            StartedAtTimeSource = startedAtTimeSource,
            TimezoneCaptureConfidence = timezoneCaptureConfidence,
        };
    }

    public static DateTime ToUtc(DateTime value, ResolvedTimeContext context)
    {
        return value.Kind switch
        {
            DateTimeKind.Utc => value,
            DateTimeKind.Local => value.ToUniversalTime(),
            _ => ConvertUnspecifiedToUtc(value, context),
        };
    }

    public static string BuildMessageId(string messageType, ChartIdentity chartIdentity, DateTime barTimestampUtc, int sequence)
    {
        var normalizedType = NormalizeIdentifier(messageType) ?? "unknown";
        var normalizedChartId = NormalizeIdentifier(chartIdentity.ChartInstanceId) ?? "unknown_chart";
        var normalizedSymbol = NormalizeIdentifier(chartIdentity.DisplaySymbol) ?? NormalizeIdentifier(chartIdentity.ContractSymbol) ?? "unknown_symbol";
        var normalizedTimeframe = NormalizeIdentifier(chartIdentity.DisplayTimeframe) ?? "unknown_tf";
        return string.Create(
            CultureInfo.InvariantCulture,
            $"{normalizedType}:{normalizedChartId}:{normalizedSymbol}:{normalizedTimeframe}:{barTimestampUtc:O}:{Math.Max(0, sequence)}");
    }

    public static string Describe(ChartIdentity chartIdentity, ResolvedTimeContext timeContext)
        => string.Create(
            CultureInfo.InvariantCulture,
            $"display_symbol={SafeLogValue(chartIdentity.DisplaySymbol)} root_symbol={SafeLogValue(chartIdentity.RootSymbol)} contract_symbol={SafeLogValue(chartIdentity.ContractSymbol)} chart_instance_id={SafeLogValue(chartIdentity.ChartInstanceId)} display_timeframe={SafeLogValue(chartIdentity.DisplayTimeframe)} instrument_timezone_value={SafeLogValue(timeContext.InstrumentTimezoneValue)} chart_display_timezone_mode={SafeLogValue(timeContext.ChartDisplayTimezoneMode)} chart_display_timezone_name={SafeLogValue(timeContext.ChartDisplayTimezoneName)} chart_display_utc_offset_minutes={SafeLogValue(timeContext.ChartDisplayUtcOffsetMinutes)} collector_local_timezone_name={SafeLogValue(timeContext.CollectorLocalTimezoneName)} timestamp_basis={SafeLogValue(timeContext.TimestampBasis)} timezone_capture_confidence={SafeLogValue(timeContext.TimezoneCaptureConfidence)}");

    public static DateTimeOffset ToReferenceTime(DateTime utcValue, ResolvedTimeContext context)
    {
        var normalizedUtc = utcValue.Kind == DateTimeKind.Utc ? utcValue : utcValue.ToUniversalTime();
        var utcOffsetValue = new DateTimeOffset(normalizedUtc, TimeSpan.Zero);
        if (context.ChartDisplayTimeZone is not null)
        {
            return TimeZoneInfo.ConvertTime(utcOffsetValue, context.ChartDisplayTimeZone);
        }

        if (context.ChartDisplayUtcOffsetMinutes is int chartOffsetMinutes)
        {
            return utcOffsetValue.ToOffset(TimeSpan.FromMinutes(chartOffsetMinutes));
        }

        if (context.InstrumentTimeZone is not null)
        {
            return TimeZoneInfo.ConvertTime(utcOffsetValue, context.InstrumentTimeZone);
        }

        if (context.InstrumentUtcOffsetMinutes is int instrumentOffsetMinutes)
        {
            return utcOffsetValue.ToOffset(TimeSpan.FromMinutes(instrumentOffsetMinutes));
        }

        return utcOffsetValue.ToOffset(TimeSpan.FromMinutes(context.CollectorLocalUtcOffsetMinutes));
    }

    public static string FormatTimeframe(TimeSpan span)
    {
        if (span <= TimeSpan.Zero)
        {
            return "unknown";
        }

        if (span.TotalSeconds < 60)
        {
            return $"{Math.Max(1, (int)Math.Round(span.TotalSeconds, MidpointRounding.AwayFromZero))}s";
        }

        if (span.TotalMinutes <= 1.1)
        {
            return "1m";
        }

        if (span.TotalMinutes <= 5.1)
        {
            return "5m";
        }

        if (span.TotalMinutes <= 15.1)
        {
            return "15m";
        }

        if (span.TotalMinutes <= 30.1)
        {
            return "30m";
        }

        if (span.TotalMinutes <= 60.1)
        {
            return "1h";
        }

        if (span.TotalHours <= 24.1)
        {
            return "1d";
        }

        return $"{Math.Max(1, (int)Math.Round(span.TotalMinutes, MidpointRounding.AwayFromZero))}m";
    }

    private static DateTime ConvertUnspecifiedToUtc(DateTime value, ResolvedTimeContext context)
    {
        var unspecified = DateTime.SpecifyKind(value, DateTimeKind.Unspecified);
        if (context.ChartDisplayTimeZone is not null)
        {
            return new DateTimeOffset(unspecified, context.ChartDisplayTimeZone.GetUtcOffset(unspecified)).UtcDateTime;
        }

        if (context.ChartDisplayUtcOffsetMinutes is int chartOffsetMinutes)
        {
            return new DateTimeOffset(unspecified, TimeSpan.FromMinutes(chartOffsetMinutes)).UtcDateTime;
        }

        if (context.InstrumentTimeZone is not null)
        {
            return new DateTimeOffset(unspecified, context.InstrumentTimeZone.GetUtcOffset(unspecified)).UtcDateTime;
        }

        if (context.InstrumentUtcOffsetMinutes is int instrumentOffsetMinutes)
        {
            return new DateTimeOffset(unspecified, TimeSpan.FromMinutes(instrumentOffsetMinutes)).UtcDateTime;
        }

        return new DateTimeOffset(unspecified, TimeZoneInfo.Local.GetUtcOffset(unspecified)).UtcDateTime;
    }

    private static string? ResolveFirstString(object source, IEnumerable<string[]> paths, Func<string?, string?> normalizer)
    {
        foreach (var path in paths)
        {
            var normalized = normalizer(AtasReflection.ReadStringPath(source, path));
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                return normalized;
            }
        }

        return null;
    }

    private static decimal ResolveFirstDecimal(object source, IEnumerable<string[]> paths)
    {
        foreach (var path in paths)
        {
            var candidate = AtasReflection.ReadDecimalPath(source, path);
            if (candidate is > 0m)
            {
                return candidate.Value;
            }
        }

        return 0m;
    }

    private static object? ResolveFirstObject(object source, IEnumerable<string[]> paths)
    {
        foreach (var path in paths)
        {
            var candidate = AtasReflection.ReadObjectPath(source, path);
            if (candidate is not null)
            {
                return candidate;
            }
        }

        return null;
    }

    private static int? ResolveFirstUtcOffsetMinutes(object source, IEnumerable<string[]> paths)
    {
        foreach (var path in paths)
        {
            if (TryParseUtcOffsetMinutes(AtasReflection.ReadObjectPath(source, path), out var offsetMinutes))
            {
                return offsetMinutes;
            }
        }

        return null;
    }

    private static TimeZoneInfo? TryResolveTimeZoneInfo(object? raw, out int? fixedOffsetMinutes)
    {
        fixedOffsetMinutes = null;
        if (raw is null)
        {
            return null;
        }

        if (raw is TimeZoneInfo zoneInfo)
        {
            return zoneInfo;
        }

        if (raw is TimeSpan timeSpan)
        {
            fixedOffsetMinutes = (int)Math.Round(timeSpan.TotalMinutes, MidpointRounding.AwayFromZero);
            return null;
        }

        if (raw is int intValue)
        {
            fixedOffsetMinutes = intValue;
            return null;
        }

        if (raw is long longValue)
        {
            fixedOffsetMinutes = checked((int)longValue);
            return null;
        }

        if (raw is decimal decimalValue)
        {
            fixedOffsetMinutes = decimal.ToInt32(decimal.Round(decimalValue, MidpointRounding.AwayFromZero));
            return null;
        }

        if (raw is double doubleValue)
        {
            fixedOffsetMinutes = Convert.ToInt32(doubleValue);
            return null;
        }

        if (raw is float floatValue)
        {
            fixedOffsetMinutes = Convert.ToInt32(floatValue);
            return null;
        }

        var candidate = raw.ToString()?.Trim();
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return null;
        }

        try
        {
            return TimeZoneInfo.FindSystemTimeZoneById(candidate);
        }
        catch (TimeZoneNotFoundException)
        {
        }
        catch (InvalidTimeZoneException)
        {
        }

        var matchedZone = TimeZoneInfo.GetSystemTimeZones()
            .FirstOrDefault(item =>
                string.Equals(item.Id, candidate, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.StandardName, candidate, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.DisplayName, candidate, StringComparison.OrdinalIgnoreCase));
        if (matchedZone is not null)
        {
            return matchedZone;
        }

        if (TryParseUtcOffsetMinutes(candidate, out var parsedOffset))
        {
            fixedOffsetMinutes = parsedOffset;
        }

        return null;
    }

    private static bool TryParseUtcOffsetMinutes(object? raw, out int offsetMinutes)
    {
        offsetMinutes = 0;
        if (raw is null)
        {
            return false;
        }

        if (raw is TimeSpan timeSpan)
        {
            offsetMinutes = (int)Math.Round(timeSpan.TotalMinutes, MidpointRounding.AwayFromZero);
            return true;
        }

        if (raw is int intValue)
        {
            offsetMinutes = intValue;
            return true;
        }

        if (raw is long longValue)
        {
            offsetMinutes = checked((int)longValue);
            return true;
        }

        if (raw is decimal decimalValue)
        {
            offsetMinutes = decimal.ToInt32(decimal.Round(decimalValue, MidpointRounding.AwayFromZero));
            return true;
        }

        if (raw is double doubleValue)
        {
            offsetMinutes = Convert.ToInt32(doubleValue);
            return true;
        }

        var candidate = raw.ToString()?.Trim();
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return false;
        }

        if (candidate.Equals("UTC", StringComparison.OrdinalIgnoreCase)
            || candidate.Equals("GMT", StringComparison.OrdinalIgnoreCase)
            || candidate.Equals("Z", StringComparison.OrdinalIgnoreCase))
        {
            offsetMinutes = 0;
            return true;
        }

        candidate = candidate
            .Replace("UTC", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("GMT", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Trim();
        if (TimeSpan.TryParse(candidate, CultureInfo.InvariantCulture, out var parsedTimeSpan))
        {
            offsetMinutes = (int)Math.Round(parsedTimeSpan.TotalMinutes, MidpointRounding.AwayFromZero);
            return true;
        }

        if ((candidate.StartsWith('+') || candidate.StartsWith('-')) && candidate.Length >= 2)
        {
            var sign = candidate[0] == '-' ? -1 : 1;
            var magnitude = candidate[1..];
            var parts = magnitude.Split(':', StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length >= 1 && int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var hours))
            {
                var minutes = 0;
                if (parts.Length >= 2)
                {
                    _ = int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out minutes);
                }

                offsetMinutes = sign * ((Math.Abs(hours) * 60) + Math.Abs(minutes));
                return true;
            }
        }

        return int.TryParse(candidate, NumberStyles.Integer, CultureInfo.InvariantCulture, out offsetMinutes);
    }

    private static string? NormalizeDisplayTimeframe(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var candidate = raw.Trim().ToLowerInvariant().Replace(" ", string.Empty);
        return candidate switch
        {
            "m1" or "1min" or "1minute" => "1m",
            "m5" or "5min" or "5minute" => "5m",
            "m15" or "15min" or "15minute" => "15m",
            "m30" or "30min" or "30minute" => "30m",
            "h1" or "60m" or "60min" or "1hour" => "1h",
            "d1" or "1day" => "1d",
            _ => candidate,
        };
    }

    private static string? NormalizeFreeText(string? raw)
        => string.IsNullOrWhiteSpace(raw) ? null : raw.Trim();

    private static string? NormalizeIdentifier(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var candidate = raw.Trim();
        foreach (var unsafeChar in IdentifierUnsafeChars)
        {
            candidate = candidate.Replace(unsafeChar, '_');
        }

        return candidate;
    }

    private static string? NormalizeTimeZoneMode(object? raw)
    {
        var candidate = raw?.ToString()?.Trim();
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return null;
        }

        var normalized = candidate.ToLowerInvariant().Replace(" ", "_").Replace("-", "_");
        if (normalized.Contains("utc"))
        {
            return "utc";
        }

        if (normalized.Contains("local"))
        {
            return "local";
        }

        if (normalized.Contains("exchange") || normalized.Contains("instrument") || normalized.Contains("symbol"))
        {
            return "instrument";
        }

        if (normalized.Contains("custom"))
        {
            return "custom_offset";
        }

        if (TryParseUtcOffsetMinutes(candidate, out _))
        {
            return "custom_offset";
        }

        return normalized;
    }

    private static int? InferUtcOffsetMinutes(
        string? chartMode,
        TimeZoneInfo? instrumentTimeZone,
        int? instrumentUtcOffsetMinutes,
        TimeZoneInfo localZone,
        DateTime observedAtUtc)
    {
        return chartMode switch
        {
            "utc" => 0,
            "local" => (int)Math.Round(localZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero),
            "instrument" when instrumentTimeZone is not null => (int)Math.Round(instrumentTimeZone.GetUtcOffset(observedAtUtc).TotalMinutes, MidpointRounding.AwayFromZero),
            "instrument" when instrumentUtcOffsetMinutes is not null => instrumentUtcOffsetMinutes,
            _ => null,
        };
    }

    private static string? FormatUtcOffsetName(int? offsetMinutes)
    {
        if (offsetMinutes is null)
        {
            return null;
        }

        var offset = TimeSpan.FromMinutes(offsetMinutes.Value);
        var sign = offset < TimeSpan.Zero ? "-" : "+";
        var absolute = offset.Duration();
        return $"UTC{sign}{absolute:hh\\:mm}";
    }

    private static string BuildFallbackChartInstanceId(string contractSymbol, string displayTimeframe, string venue, string currency)
    {
        var parts = new[]
        {
            NormalizeIdentifier(contractSymbol) ?? "unknown_symbol",
            NormalizeIdentifier(displayTimeframe) ?? "unknown_tf",
            NormalizeIdentifier(venue) ?? "unknown_venue",
            NormalizeIdentifier(currency) ?? "unknown_ccy",
        };
        return $"chart-{string.Join("-", parts)}";
    }

    private static string? NormalizeSymbolCandidate(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var candidate = raw.Trim();
        var cutIndex = candidate.IndexOfAny(new[] { ' ', '\t', '\r', '\n', '(', '[', '{' });
        if (cutIndex > 0)
        {
            candidate = candidate[..cutIndex];
        }

        candidate = candidate.Trim().Trim('"', '\'');
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return null;
        }

        if (candidate.StartsWith("ATAS", StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith("ZZ", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        candidate = candidate.ToUpperInvariant();
        if (InvalidSymbolCandidates.Contains(candidate) || candidate.Length < 2 || !candidate.Any(char.IsLetter))
        {
            return null;
        }

        return candidate;
    }

    private static string? ParseRootSymbol(string? contractSymbol)
    {
        var symbol = NormalizeSymbolCandidate(contractSymbol);
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return null;
        }

        var monthCodeIndex = symbol.Length - 1;
        while (monthCodeIndex >= 0 && char.IsDigit(symbol[monthCodeIndex]))
        {
            monthCodeIndex--;
        }

        if (monthCodeIndex > 0 && "FGHJKMNQUVXZ".IndexOf(symbol[monthCodeIndex]) >= 0)
        {
            var root = symbol[..monthCodeIndex];
            if (!string.IsNullOrWhiteSpace(root))
            {
                return root;
            }
        }

        return symbol;
    }

    private static string? DescribeTimeZoneValue(object? raw)
    {
        if (raw is TimeZoneInfo timeZoneInfo)
        {
            return timeZoneInfo.Id;
        }

        if (raw is TimeSpan timeSpan)
        {
            return timeSpan.ToString("c", CultureInfo.InvariantCulture);
        }

        return raw?.ToString();
    }

    private static string SafeLogValue(object? value)
        => value switch
        {
            null => "null",
            string text when string.IsNullOrWhiteSpace(text) => "empty",
            _ => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "null",
        };
}
