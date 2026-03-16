using System.Reflection;

foreach (var path in new[]
{
    @"D:\docker\atas-market-structure\src-csharp\AtasMarketStructure.Adapter\bin\Debug\net10.0\AtasMarketStructure.Adapter.dll",
    @"D:\docker\atas-market-structure\src-csharp\AtasMarketStructure.Probe\bin\Debug\net10.0\AtasMarketStructure.Probe.dll",
    @"C:\Program Files (x86)\ATAS Platform\ATAS.Indicators.dll",
    @"C:\Program Files (x86)\ATAS Platform\ATAS.Types.dll",
    @"C:\Program Files (x86)\ATAS Platform\ATAS.DataFeedsCore.dll"
})
{
    Console.WriteLine($"=== {path} ===");
    try
    {
        var asm = Assembly.LoadFrom(path);
        foreach (var name in asm.GetReferencedAssemblies().OrderBy(x => x.Name))
        {
            Console.WriteLine($"{name.Name} {name.Version}");
        }
    }
    catch (Exception ex)
    {
        Console.WriteLine(ex);
    }
    Console.WriteLine();
}
