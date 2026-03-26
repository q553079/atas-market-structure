using System.Reflection;
using System.Runtime.Loader;

var repoRoot = @"D:\docker\atas-market-structure";
var atasInstallDir = @"C:\Program Files (x86)\ATAS Platform";
var indicatorsDir = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
    "ATAS",
    "Indicators");

var adapterPath = Path.Combine(indicatorsDir, "AtasMarketStructure.Adapter.dll");
var probePath = Path.Combine(repoRoot, "src-csharp", "AtasMarketStructure.Probe", "bin", "Debug", "net10.0", "AtasMarketStructure.Probe.dll");

InspectAssembly(
    assemblyPath: probePath,
    targetTypeName: "ZZAtasCollectorProbe",
    atasInstallDir: atasInstallDir,
    indicatorsDir: indicatorsDir);

InspectAssembly(
    assemblyPath: adapterPath,
    targetTypeName: "AtasMarketStructure.Adapter.Collector.AtasMarketStructureCollector",
    atasInstallDir: atasInstallDir,
    indicatorsDir: indicatorsDir);

static void InspectAssembly(
    string assemblyPath,
    string targetTypeName,
    string atasInstallDir,
    string indicatorsDir)
{
    Console.WriteLine($"=== {assemblyPath} ===");
    if (!File.Exists(assemblyPath))
    {
        Console.WriteLine("Missing assembly.");
        Console.WriteLine();
        return;
    }

    var loadContext = new PluginLoadContext(assemblyPath, atasInstallDir, indicatorsDir);
    Assembly assembly;
    try
    {
        assembly = loadContext.LoadFromAssemblyPath(assemblyPath);
        Console.WriteLine($"Loaded assembly: {assembly.FullName}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Load failure: {ex}");
        Console.WriteLine();
        return;
    }

    Type[] types;
    try
    {
        types = assembly.GetTypes();
        Console.WriteLine($"Type count: {types.Length}");
        foreach (var type in types.OrderBy(item => item.FullName))
        {
            Console.WriteLine(
                $"TYPE {type.FullName} public={type.IsPublic} abstract={type.IsAbstract} base={type.BaseType?.FullName}");
        }
    }
    catch (ReflectionTypeLoadException ex)
    {
        Console.WriteLine("ReflectionTypeLoadException while enumerating types.");
        foreach (var loaderException in ex.LoaderExceptions.Where(item => item is not null))
        {
            Console.WriteLine($"LOADER {loaderException!.GetType().FullName}: {loaderException.Message}");
        }
        Console.WriteLine();
        return;
    }

    var targetType = assembly.GetType(targetTypeName, throwOnError: false);
    Console.WriteLine($"Target type: {targetType?.FullName ?? "<null>"}");

    if (targetType is not null)
    {
        try
        {
            var instance = Activator.CreateInstance(targetType);
            Console.WriteLine($"Created instance: {instance?.GetType().FullName ?? "<null>"}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Instantiation failure: {ex}");
        }
    }

    Console.WriteLine();
}

internal sealed class PluginLoadContext : AssemblyLoadContext
{
    private readonly AssemblyDependencyResolver _resolver;
    private readonly string _atasInstallDir;
    private readonly string _indicatorsDir;

    public PluginLoadContext(string assemblyPath, string atasInstallDir, string indicatorsDir)
        : base(isCollectible: true)
    {
        _resolver = new AssemblyDependencyResolver(assemblyPath);
        _atasInstallDir = atasInstallDir;
        _indicatorsDir = indicatorsDir;
    }

    protected override Assembly? Load(AssemblyName assemblyName)
    {
        var resolvedPath = _resolver.ResolveAssemblyToPath(assemblyName);
        if (resolvedPath is not null)
        {
            return LoadFromAssemblyPath(resolvedPath);
        }

        foreach (var baseDir in new[] { _indicatorsDir, _atasInstallDir })
        {
            var candidatePath = Path.Combine(baseDir, $"{assemblyName.Name}.dll");
            if (File.Exists(candidatePath))
            {
                return LoadFromAssemblyPath(candidatePath);
            }
        }

        return null;
    }
}
