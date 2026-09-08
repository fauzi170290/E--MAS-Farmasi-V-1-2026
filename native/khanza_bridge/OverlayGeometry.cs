using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;

// Optional presentation side channel. Never included in Item or Fingerprint.
internal static partial class KhanzaBridge
{
    private static bool _overlayEnabled;
    private static bool _overlayProbe;
    private static long _overlayProbeSequence;

    // UAT-only, strictly geometry/numeric metadata. No names, codes, identities or descriptions.
    private sealed class OverlayProbeNode { public string role; public int[] rect; }
    private sealed class OverlayProbeCell {
        public int row, component;
        public string role, geometry_source;
        public int[] raw, clipped;
    }
    private sealed class OverlayProbeTable {
        public long hwnd;
        public int model_rows, columns, name_column, captured, raw_positive, clipped_positive,
            derived_positive;
        public int[] clip;
        public List<OverlayProbeNode> hierarchy;
        public List<OverlayProbeCell> cells = new List<OverlayProbeCell>();
    }
    private static int[] RawBounds(ContextInfo info) { return new int[] { info.x, info.y, info.width, info.height }; }
    private static void ObserveProbeWindow(Candidate candidate, IntPtr hwnd, List<OverlayProbeNode> path) {
        if (_overlayProbe && path != null && path.Count > 0 && candidate.OverlayProbeWindows.Count < 8)
            candidate.OverlayProbeWindows[hwnd.ToInt64()] = path[0].rect;
    }
    private static string ProbeRole(string role) {
        switch (role) {
            case "frame": case "dialog": case "root pane": case "layered pane": case "panel":
            case "scroll pane": case "viewport": case "table": case "label": case "text": return role;
            default: return "other";
        }
    }
    private static void EmitProbeRuntime() {
        string path = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName;
        string hash;
        using (var stream = System.IO.File.OpenRead(path))
        using (var sha = System.Security.Cryptography.SHA256.Create())
            hash = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
        Emit(new Dictionary<string, object> { { "type", "overlay_probe_runtime" },
            { "pid", System.Diagnostics.Process.GetCurrentProcess().Id }, { "path", path },
            { "sha256", hash }, { "overlay_enabled", _overlayEnabled },
            { "pointer_bits", IntPtr.Size * 8 }, { "dpi_awareness_requested", _overlayDpiAware } });
    }
    private static void EmitProbeFailure() {
        Emit(new Dictionary<string, object> { { "type", "overlay_probe_error" }, { "reason", "PROBE_UNAVAILABLE" } });
    }
    private static bool SameProbeWindows(Candidate first, Candidate second) {
        if (first.OverlayProbeWindows.Count != second.OverlayProbeWindows.Count) return false;
        foreach (KeyValuePair<long, int[]> pair in first.OverlayProbeWindows) {
            int[] other;
            if (!second.OverlayProbeWindows.TryGetValue(pair.Key, out other)) return false;
            for (int edge = 0; edge < 4; edge++) if (pair.Value[edge] != other[edge]) return false;
        }
        return true;
    }
    private static List<Dictionary<string, object>> ProbeWindowSamples(Candidate candidate) {
        List<Dictionary<string, object>> windows = new List<Dictionary<string, object>>();
        foreach (KeyValuePair<long, int[]> pair in candidate.OverlayProbeWindows)
            windows.Add(new Dictionary<string, object> { { "hwnd", pair.Key }, { "root_raw", pair.Value } });
        return windows;
    }
    private static void PublishOverlayProbe(Candidate first, Candidate second) {
        bool stable = first.Complete && second.Complete && Fingerprint(first) == Fingerprint(second);
        bool tableStable = Json.Serialize(first.OverlayProbeTables) == Json.Serialize(second.OverlayProbeTables);
        List<Dictionary<string, object>> windows = ProbeWindowSamples(second);
        Emit(new Dictionary<string, object> { { "type", "overlay_probe" },
            { "sequence", ++_overlayProbeSequence }, { "scan_started", first.ScanStarted.ToString("o") },
            { "clinical_stable", stable }, { "table_sample_stable", tableStable },
            { "window_sample_stable", SameProbeWindows(first, second) },
            { "windows", windows },
            { "captured", second.OverlayRows.Count }, { "raw_positive", second.OverlayRawPositiveRows },
            { "clipped_positive", second.OverlayClippedPositiveRows },
            { "geometry_stable", StableRows(VisibleRows(first), VisibleRows(second), 0) },
            { "tables", second.OverlayProbeTables } });
    }
    private static string _overlayRevision = "";
    private static int _overlayCleared = 0;
    private static int _overlayClearPending = 0;
    private static string _overlayClearReason = "";
    private static string _pendingOverlayClearReason = "JAB_CONTEXT_CHANGED";
    private static bool _overlayDpiAware;
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowRect { public int left, top, right, bottom; }
    [StructLayout(LayoutKind.Sequential)]
    private struct MonitorInfo {
        public int size;
        public WindowRect monitor;
        public WindowRect work;
        public uint flags;
    }
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hwnd, out WindowRect rect);
    [DllImport("user32.dll")] private static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] private static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Auto)] private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);
    [DllImport("shcore.dll")] private static extern int GetDpiForMonitor(IntPtr monitor, int kind, out uint x, out uint y);

    private sealed class OverlayRow
    {
        public string source_item_key, drug_code, compound_group, geometry_source;
        public long hwnd;
        public int[] rect;
    }

    private static int[] Bounds(ContextInfo info)
    {
        return new int[] { info.x, info.y, Math.Max(0, info.width), Math.Max(0, info.height) };
    }

    private static int[] Clip(int[] a, int[] b)
    {
        if (b == null) return null;
        if (a == null) return b;
        int x = Math.Max(a[0], b[0]), y = Math.Max(a[1], b[1]);
        return new int[] { x, y, Math.Max(0, Math.Min(a[0] + a[2], b[0] + b[2]) - x),
            Math.Max(0, Math.Min(a[1] + a[3], b[1] + b[3]) - y) };
    }

    private static bool PositiveRect(int[] rect)
    {
        return rect != null && rect.Length == 4 && rect[2] > 0 && rect[3] > 0;
    }

    private static int[] DeriveVisibleTableRow(int[] table, int[] viewport, int rows, int row)
    {
        // Live Khanza proof: JTable itself and its viewport expose stable screen
        // bounds, while every virtual AccessibleJTableCell returns -1,-1,-1,-1.
        // JTable uses a uniform row grid in this view. Derive a full-row marker
        // only when the component height proves an exact, reasonable grid.
        if (!PositiveRect(table) || !PositiveRect(viewport) || rows <= 0 || rows > 1000 ||
                row < 0 || row >= rows || table[3] % rows != 0) return null;
        int height = table[3] / rows;
        if (height < 8 || height > 128) return null;
        int[] derived = new int[] { table[0], table[1] + row * height, table[2], height };
        int[] visible = Clip(Clip(viewport, table), derived);
        return PositiveRect(visible) ? visible : null;
    }

    private static int[] ClipAccessible(int[] current, ContextInfo info)
    {
        // Swing exposes structural accessibility nodes (root panes, layered
        // panes and table helpers) with zero/negative geometry. They do not
        // define a viewport and must not collapse every descendant rectangle.
        if (info.width <= 0 || info.height <= 0) return current;
        return Clip(current, Bounds(info));
    }

    private static void ConfigureOverlayDpiAwareness()
    {
        try {
            bool processAware = SetProcessDpiAwarenessContext(new IntPtr(-4));
            bool threadAware = SetThreadDpiAwarenessContext(new IntPtr(-4)) != IntPtr.Zero;
            _overlayDpiAware = processAware || threadAware;
        }
        catch { _overlayDpiAware = false; }
    }

    private static bool StableRows(List<OverlayRow> first, List<OverlayRow> second, int tolerance)
    {
        if (first.Count == 0 || first.Count != second.Count) return false;
        for (int index = 0; index < first.Count; index++) {
            OverlayRow a = first[index], b = second[index];
            if (a.source_item_key != b.source_item_key || a.drug_code != b.drug_code ||
                    a.compound_group != b.compound_group || a.geometry_source != b.geometry_source || a.hwnd != b.hwnd ||
                    a.rect == null || b.rect == null) return false;
            for (int edge = 0; edge < 4; edge++)
                if (Math.Abs(a.rect[edge] - b.rect[edge]) > tolerance) return false;
        }
        return true;
    }

    private static void ClearOverlay() { ClearOverlay("JAB_EVENT_OR_OVERLAY_ERROR"); }

    private static void QueueOverlayClear(string reason)
    {
        // JAB callbacks only flip atomics and release handles. JSON/pipe I/O runs
        // from the bridge message loop immediately after Application.DoEvents().
        _pendingOverlayClearReason = reason;
        Interlocked.Exchange(ref _overlayClearPending, 1);
    }

    private static void FlushOverlayClear()
    {
        if (_overlayEnabled && Interlocked.Exchange(ref _overlayClearPending, 0) != 0)
            ClearOverlay(_pendingOverlayClearReason);
    }

    private static void ClearOverlay(string reason)
    {
        if (Interlocked.Exchange(ref _overlayCleared, 1) != 0 && reason == _overlayClearReason) return;
        _overlayClearReason = reason;
        try { Emit(new Dictionary<string, object> { { "type", "overlay_clear" }, { "reason", reason } }); }
        catch { } // An optional presentation event must never break a JAB callback.
    }

    private static List<OverlayRow> VisibleRows(Candidate candidate)
    {
        List<OverlayRow> rows = new List<OverlayRow>();
        foreach (OverlayRow row in candidate.OverlayRows.Values)
            if (row.rect != null && row.rect[2] > 0 && row.rect[3] > 0) rows.Add(row);
        rows.Sort(delegate(OverlayRow a, OverlayRow b) {
            return String.CompareOrdinal(a.source_item_key, b.source_item_key);
        });
        return rows;
    }

    private static void PublishOverlay(Candidate first, Candidate second)
    {
        // Publish() already checked both independent clinical reads. Geometry also
        // has to match, including viewport clipping and owner HWND, without rereading JAB.
        if (_overlayRevision.Length == 0) { ClearOverlay("UNSTABLE_SOURCE"); return; }
        if (!_overlayDpiAware) { ClearOverlay("DPI_AWARENESS_UNAVAILABLE"); return; }
        List<OverlayRow> firstRows = VisibleRows(first);
        List<OverlayRow> rows = VisibleRows(second);
        if (rows.Count == 0) {
            ClearOverlay("NO_VISIBLE_ROWS_CAPTURED_" + second.OverlayRows.Count.ToString() +
                "_RAW_" + second.OverlayRawPositiveRows.ToString() +
                "_CLIPPED_" + second.OverlayClippedPositiveRows.ToString() +
                "_DERIVED_" + second.OverlayDerivedRows.ToString());
            return;
        }
        if (rows.Count > 200) { ClearOverlay("ROW_LIMIT"); return; }
        long owner = rows[0].hwnd;
        foreach (OverlayRow row in rows) if (row.hwnd != owner) { ClearOverlay("MULTIPLE_WINDOWS"); return; }
        IntPtr hwnd = new IntPtr(owner);
        IntPtr monitor = MonitorFromWindow(hwnd, 2);
        MonitorInfo monitorInfo = new MonitorInfo(); monitorInfo.size = Marshal.SizeOf(typeof(MonitorInfo));
        uint dpiX, dpiY;
        if (monitor == IntPtr.Zero || !GetMonitorInfo(monitor, ref monitorInfo) ||
                GetDpiForMonitor(monitor, 0, out dpiX, out dpiY) != 0 || dpiX != dpiY) {
            ClearOverlay("MONITOR_DPI_UNAVAILABLE"); return;
        }
        if (dpiX != 96 && dpiX != 120 && dpiX != 144) { ClearOverlay("UNSUPPORTED_MONITOR_DPI"); return; }
        int tolerance = Math.Max(2, (int)Math.Ceiling(2.0 * dpiX / 96.0));
        if (!StableRows(firstRows, rows, tolerance)) { ClearOverlay("GEOMETRY_PAIR_UNSTABLE"); return; }
        WindowRect window;
        if (!GetWindowRect(hwnd, out window)) { ClearOverlay("WINDOW_BOUNDS_UNAVAILABLE"); return; }
        uint pid; GetWindowThreadProcessId(hwnd, out pid);
        Emit(new Dictionary<string, object> {
            { "type", "overlay_geometry" }, { "schema", 2 },
            { "coordinate_space", "win32_physical_pixels" },
            { "no_resep", second.NoResep }, { "no_rawat", second.NoRawat },
            { "revision", _overlayRevision },
            { "clinical_fingerprint", ClinicalFingerprint(second) },
            { "hwnd", owner }, { "pid", pid },
            { "scan_started", first.ScanStarted.ToString("o") }, { "dpi", dpiX },
            { "monitor_rect", new int[] { monitorInfo.monitor.left, monitorInfo.monitor.top,
                monitorInfo.monitor.right-monitorInfo.monitor.left,
                monitorInfo.monitor.bottom-monitorInfo.monitor.top } },
            { "window_rect", new int[] { window.left, window.top, window.right-window.left, window.bottom-window.top } },
            { "rows", rows }
        });
        Interlocked.Exchange(ref _overlayCleared, 0);
    }

    private static bool OverlaySelfTest()
    {
        Candidate probeA = new Candidate(), probeB = new Candidate();
        probeA.OverlayProbeWindows[99] = new int[] { -1, -1, 0, 0 };
        probeB.OverlayProbeWindows[99] = new int[] { -1, -1, 0, 0 };
        bool probe = SameProbeWindows(probeA, probeB) &&
            Json.Serialize(ProbeWindowSamples(probeA)).Contains("\"root_raw\":[-1,-1,0,0]");
        probeB.OverlayProbeWindows[99][2] = 20;
        probe = probe && !SameProbeWindows(probeA, probeB);
        int[] clipped = Clip(new int[] { 10, 20, 100, 80 }, new int[] { 0, 30, 60, 90 });
        int[] hidden = Clip(new int[] { 10, 20, 100, 80 }, new int[] { 200, 30, 60, 10 });
        ContextInfo structural = new ContextInfo { x = -1, y = -1, width = 0, height = 0 };
        int[] preserved = ClipAccessible(new int[] { 10, 20, 100, 80 }, structural);
        int[] liveGrid = DeriveVisibleTableRow(new int[] { 19, 263, 1280, 154 },
            new int[] { 19, 263, 1881, 668 }, 7, 2);
        int[] scrolledGrid = DeriveVisibleTableRow(new int[] { 19, 241, 1280, 154 },
            new int[] { 19, 263, 1881, 668 }, 7, 0);
        bool gridFailsClosed = DeriveVisibleTableRow(new int[] { 19, 263, 1280, 155 },
            new int[] { 19, 263, 1881, 668 }, 7, 2) == null;
        Candidate candidate = new Candidate { NoResep = "TEST", NoRawat = "VISIT" };
        Item item = new Item { source_item_key = "regular:1", drug_code = "1", raw_quantity = "1" };
        candidate.Regular.Add(item);
        string before = Fingerprint(candidate);
        candidate.OverlayRows[item] = new OverlayRow { source_item_key = item.source_item_key,
            drug_code = item.drug_code, compound_group = "", hwnd = 5, rect = clipped };
        bool separate = before == Fingerprint(candidate) && !Json.Serialize(item).Contains("rect");
        bool clinicalIdentity = ClinicalFingerprint(candidate) ==
            "9a569952cf90af62cc8f84c57c79dbd94b6d1a911acc8e661951556e17a8a7bf";
        List<OverlayRow> stable = VisibleRows(candidate);
        return probe && separate && clinicalIdentity && liveGrid[0] == 19 && liveGrid[1] == 307 &&
            liveGrid[2] == 1280 && liveGrid[3] == 22 && scrolledGrid == null && gridFailsClosed &&
            clipped[0] == 10 && clipped[1] == 30 && clipped[2] == 50 &&
            clipped[3] == 70 && hidden[2] == 0 && preserved[0] == 10 && preserved[2] == 100 &&
            stable.Count == 1 && StableRows(stable, stable, 2);
    }

    private static string ClinicalFingerprint(Candidate candidate)
    {
        List<string[]> items = new List<string[]>();
        foreach (Item item in candidate.Regular)
            items.Add(new string[] { "regular", "", item.drug_code });
        for (int group = 0; group < candidate.CompoundTables.Count; group++)
            foreach (Item item in candidate.CompoundTables[group])
                items.Add(new string[] { "compound", "racikan:" + (group + 1).ToString(), item.drug_code });
        items.Sort(delegate(string[] left, string[] right) {
            for (int index = 0; index < 3; index++) {
                int compared = String.CompareOrdinal(left[index], right[index]);
                if (compared != 0) return compared;
            }
            return 0;
        });
        // Same canonical JSON produced by KhanzaDesktopAdapter._fingerprint_source.
        string source = "{\"items\":" + Json.Serialize(items) +
            ",\"no_resep\":" + Json.Serialize(candidate.NoResep) +
            ",\"schema\":\"desktop-ddi-v1\"}";
        using (System.Security.Cryptography.SHA256 sha = System.Security.Cryptography.SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(source)))
                .Replace("-", "").ToLowerInvariant();
    }
}
