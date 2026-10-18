namespace FactorioMCP.Services;

// Pure validation; makes no RCON calls and cannot initiate movement.
internal static class NavigationPathPolicy
{
    public static bool Valid(IReadOnlyList<(double x, double y)> path,
        double startX, double startY, double targetX, double targetY, double tolerance)
    {
        static bool Finite(double x, double y) => double.IsFinite(x) && double.IsFinite(y);
        static double Dist(double ax, double ay, double bx, double by) => Math.Sqrt((ax-bx)*(ax-bx)+(ay-by)*(ay-by));
        if (!Finite(startX, startY) || !Finite(targetX, targetY) ||
            !double.IsFinite(tolerance) || tolerance <= 0 || tolerance > .75 ||
            path.Count == 0 || path.Count > 128) return false;
        var direct = Dist(startX, startY, targetX, targetY);
        if (direct < .5 || direct > 5) return false;
        double length = 0, lastX = startX, lastY = startY;
        foreach (var (x, y) in path)
        {
            if (!Finite(x, y) || Dist(startX, startY, x, y) > 5) return false;
            length += Dist(lastX, lastY, x, y);
            if (!double.IsFinite(length) || length > 5) return false;
            lastX = x; lastY = y;
        }
        return Dist(lastX, lastY, targetX, targetY) <= tolerance;
    }
}
