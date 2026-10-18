using FactorioMCP.Services;

int checks = 0;
void Check(bool expected, (double x, double y)[] points, double x = 4, double y = 0)
{
    if (NavigationPathPolicy.Valid(points, 0, 0, x, y, .75) != expected)
        throw new Exception($"Path validation case {checks + 1} failed");
    checks++;
}
Check(true, [(0, 0), (2, 0), (4, 0)]);
Check(true, [(0, 0), (2, 1), (4, 0)]);
Check(false, []);
Check(false, [(0, 0), (2, 3), (4, 0)]); // Endpoint is short, route exceeds five.
Check(false, [(0, 0), (6, 0), (4, 0)]);
Check(false, [(0, 0), (double.NaN, 0), (4, 0)]);
Check(false, [(0, 0), (double.PositiveInfinity, 0)]);
Check(false, [(0, 0), (1, 0)]); // Does not reach requested endpoint.
Check(false, [(0, 0), (6, 0)], 6, 0);
Check(false, Enumerable.Repeat((0.0, 0.0), 129).ToArray());
Console.WriteLine($"{checks} backend route-validation cases passed.");
