using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static partial class KhanzaBridge
{
#if BRIDGE_X64
    private const string Dll = "windowsaccessbridge-64.dll";
    private const string BridgeArchitecture = "x64";
    private const int RequiredPointerSize = 8;
#else
    private const string Dll = "windowsaccessbridge-32.dll";
    private const string BridgeArchitecture = "x86";
    private const int RequiredPointerSize = 4;
#endif
    private const uint ProcessQueryLimitedInformation = 0x1000;
    private const ushort ImageFileMachineUnknown = 0x0000;
    private const ushort ImageFileMachineI386 = 0x014c;
    private const ushort ImageFileMachineAmd64 = 0x8664;
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    private static readonly object OutputLock = new object();
    private static int _dirty = 1;
    private static string _lastFingerprint = "";
    private static string _lastPrescription = "";
    private static string _lastInvalid = "";
    private static string _lastConnectionState = "";
    private static string _lastDiagnostic = "";
    private static string _pendingNoResep = "";
    private static string _pendingNoRawat = "";
    private static string _pendingPatientId = "";
    private static string _pendingPatientName = "";
    private static string _pendingPrescriberName = "";
    private static string _pendingCareSetting = "";
    private static DateTime _pendingIdentityAt = DateTime.MinValue;
    private static readonly Regex CareIdPattern = new Regex(
        @"\b\d{4}/\d{2}/\d{2}/\d{6}\b", RegexOptions.CultureInvariant);
    private static readonly Regex PrescriptionIdPattern = new Regex(
        @"(?<!\d)\d{12}(?!\d)", RegexOptions.CultureInvariant);
    // Khanza launchers legitimately use either `-jar <path>` or `-jar=<path>`.
    // Deployed Khanza launchers can use a product-prefixed basename ending in
    // khanza.jar. Reject separators that identify unrelated derived names
    // (for example reporting-khanza.jar) and any longer suffix.
    private static readonly Regex KhanzaJarPattern = new Regex(
        @"(?<![._-])khanza\.jar(?![A-Za-z0-9_.-])",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
    // Some Khanza launchers pass a full JAR path as the value for -jar.  Parse
    // that option independently of surrounding path characters, while still
    // requiring the canonical basename rather than a derived JAR filename.
    private static readonly Regex KhanzaJarLaunchArgumentPattern = new Regex(
        "(?:^|\\s)-jar(?:\\s+|=)\\s*(?:\"[^\"]*[\\\\/]khanza\\.jar\"|[^\\s\"]*[\\\\/]khanza\\.jar)(?=\\s|$)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool ReadProcessMemory(IntPtr process, IntPtr address,
        [Out] byte[] buffer, int size, out IntPtr bytesRead);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool IsWow64Process2(IntPtr process, out ushort processMachine,
        out ushort nativeMachine);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool IsWow64Process(IntPtr process, out bool wow64Process);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool QueryFullProcessImageName(IntPtr process, int flags,
        StringBuilder executableName, ref int size);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool ProcessIdToSessionId(uint processId, out uint sessionId);
    [DllImport("ntdll.dll")]
    private static extern int NtQueryInformationProcess(IntPtr process, int informationClass,
        out ProcessBasicInformation information, int informationLength, out int returnLength);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern void Windows_run();
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool isJavaWindow(IntPtr window);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool getAccessibleContextFromHWND(IntPtr window, out int vm, out long context);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool getAccessibleContextInfo(int vm, long context, out ContextInfo info);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern long getAccessibleChildFromContext(int vm, long context, int index);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern void releaseJavaObject(int vm, long context);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool getAccessibleTableInfo(int vm, long context, out TableInfo info);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool getAccessibleTableColumnHeader(int vm, long context, out TableInfo info);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool getAccessibleTableCellInfo(int vm, long table, int row, int column, out CellInfo info);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern int getAccessibleTableRowSelectionCount(int vm, long table);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] private static extern bool isAccessibleTableRowSelected(int vm, long table, int row);
    private delegate bool WindowCallback(IntPtr window, IntPtr state);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool EnumWindows(WindowCallback callback, IntPtr state);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessBasicInformation
    {
        public IntPtr Reserved1;
        public IntPtr PebBaseAddress;
        public IntPtr Reserved2a;
        public IntPtr Reserved2b;
        public IntPtr UniqueProcessId;
        public IntPtr Reserved3;
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void SimpleEvent(int vm, long evt, long source);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void TextEvent(int vm, long evt, long source, IntPtr oldValue, IntPtr newValue);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void ShutdownEvent(int vm);
    [DllImport(Dll, EntryPoint = "setFocusGainedFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetFocusGained(SimpleEvent callback);
    [DllImport(Dll, EntryPoint = "setPropertySelectionChangeFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetSelection(SimpleEvent callback);
    [DllImport(Dll, EntryPoint = "setPropertyVisibleDataChangeFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetVisibleData(SimpleEvent callback);
    [DllImport(Dll, EntryPoint = "setPropertyTableModelChangeFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetTableModel(TextEvent callback);
    [DllImport(Dll, EntryPoint = "setPropertyValueChangeFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetValue(TextEvent callback);
    [DllImport(Dll, EntryPoint = "setJavaShutdownFP", CallingConvention = CallingConvention.Cdecl)] private static extern void SetJavaShutdown(ShutdownEvent callback);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct ContextInfo
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 1024)] public string name;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 1024)] public string description;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string role;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string roleUS;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string states;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string statesUS;
        public int index, children, x, y, width, height, component, action, selection, text, interfaces;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TableInfo
    {
        public long caption, summary;
        public int rows, columns;
        public long context, table;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct CellInfo
    {
        public long context;
        public int index, row, column, rowExtent, columnExtent;
        public byte selected;
    }

    private sealed class Item
    {
        public string source_item_key = "";
        public string drug_code = "";
        public string drug_name = "";
        public string raw_quantity = "";
        public string raw_signa = "";
        public string compound_group = "";
    }

    private sealed class CommandLineEvidence
    {
        public string Value = "";
        public string Method = "NONE";
        public bool QuerySucceeded;
        public string FailureReason = "";
        public int Win32Error;
    }

    private sealed class UiSignatureEvidence
    {
        public bool AccessibleRootObtained;
        public bool RootFrameMatched;
        public bool MenuBarMatched;
        public bool DesktopPaneMatched;
        public bool SignatureMatched;
        public int RootChildCount;
        public int NodesScanned;
    }

    // This diagnostic contains only process/JAB structure state. It intentionally
    // excludes window titles, accessible names, patient identity, and prescription data.
    private sealed class DiscoveryProbe
    {
        public int ProcessId;
        public string ProcessName = "";
        public bool VisibleWindow;
        public bool JavaJabWindowMatched;
        public bool AccessibleRootObtained;
        public string CommandLineMethod = "NONE";
        public bool CommandLineQuerySucceeded;
        public bool KhanzaJarTextPresent;
        public bool KhanzaJarMatched;
        public string CommandLineFailureReason = "";
        public int CommandLineWin32Error;
        public bool RootFrameMatched;
        public bool MenuBarMatched;
        public bool DesktopPaneMatched;
        public bool SignatureMatched;
        public int RootChildCount;
        public int SignatureNodesScanned;
    }

    private sealed class Candidate
    {
        public string NoResep = "";
        public string NoRawat = "";
        public string PatientId = "";
        public string PatientName = "";
        public string PrescriberName = "";
        public readonly List<Item> Regular = new List<Item>();
        public readonly List<List<Item>> CompoundTables = new List<List<Item>>();
        public int CompoundGroups;
        public bool DetailFound;
        public bool Accessible;
        public bool KhanzaDetected;
        public bool JavaJabCandidateFound;
        public bool TargetKhanzaFound;
        public int TargetKhanzaProcessId;
        public string DetectionEvidence = "";
        public bool JabAttached;
        public readonly List<DiscoveryProbe> DiscoveryProbes = new List<DiscoveryProbe>();
        public DiscoveryProbe PrimaryDiscoveryProbe;
        public string IdentityState = "KHANZA_NOT_FOUND";
        public string PrescriptionState = "PRESCRIPTION_VIEW_NOT_FOUND";
        public string DetailNoRawat = "";
        public bool DetailIdentityAmbiguous;
        public string CareSetting = "";
        public bool CareSettingAmbiguous;
        public bool AmbiguousIdentity;
        public bool ReadError;
        public long ScanMilliseconds;
        public int NodesRead;
        public int VisibleJavaWindows;
        public int OverlayRawPositiveRows;
        public int OverlayClippedPositiveRows;
        public int OverlayDerivedRows;
        public readonly Dictionary<Item, OverlayRow> OverlayRows = new Dictionary<Item, OverlayRow>();
        public readonly List<OverlayProbeTable> OverlayProbeTables = new List<OverlayProbeTable>();
        public readonly Dictionary<long, int[]> OverlayProbeWindows = new Dictionary<long, int[]>();
        public DateTime ScanStarted = DateTime.UtcNow;

        public bool Complete
        {
            get
            {
                return !ReadError && !AmbiguousIdentity && !DetailIdentityAmbiguous &&
                    !CareSettingAmbiguous && CareSetting.Length > 0 &&
                    NoResep.Length > 0 && NoRawat.Length > 0 &&
                    DetailFound && Regular.Count + CompoundItemCount > 0 &&
                    (CompoundGroups == 0 ? CompoundTables.Count == 0 : CompoundTables.Count == CompoundGroups);
            }
        }

        public int CompoundItemCount
        {
            get
            {
                int count = 0;
                foreach (List<Item> rows in CompoundTables) count += rows.Count;
                return count;
            }
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        _overlayEnabled = Array.IndexOf(args, "--overlay-poc") >= 0;
        _overlayProbe = _overlayEnabled && Environment.GetEnvironmentVariable("EMAS_OVERLAY_UAT_DIAGNOSTICS") == "1";
        if (_overlayEnabled) ConfigureOverlayDpiAwareness();
        if (Array.IndexOf(args, "--probe-khanza-runtime") >= 0)
        {
            KhanzaRuntimeProbe runtime = FindKhanzaRuntime();
            Emit(new Dictionary<string, object> {
                { "type", "runtime_probe" },
                { "target_found", runtime.Found },
                { "target_pid", runtime.ProcessId },
                { "target_session_id", runtime.SessionId },
                { "java_architecture", runtime.Architecture },
                { "command_line_method", runtime.CommandLineMethod },
                { "command_line_query_succeeded", runtime.CommandLineQuerySucceeded },
                { "khanza_jar_matched", runtime.KhanzaJarMatched },
                { "probe_architecture", BridgeArchitecture }
            });
            return runtime.Found ? 0 : 7;
        }
        if (IntPtr.Size != RequiredPointerSize)
        {
            EmitStatus("ERROR", "BRIDGE_REQUIRES_" + BridgeArchitecture.ToUpperInvariant());
            return 2;
        }
        if (Array.IndexOf(args, "--self-test") >= 0)
        {
            bool passed = RunSelfTest();
            EmitStatus(passed ? "SELF_TEST_PASS" : "ERROR",
                passed ? BridgeArchitecture.ToUpperInvariant() + "_DISCOVERY_AND_QUANTITY_FILTER_READY" : "DISCOVERY_OR_QUANTITY_FILTER_FAILED");
            return passed ? 0 : 4;
        }
        foreach (string argument in args)
        {
            const string probePrefix = "--probe-command-line=";
            if (!argument.StartsWith(probePrefix, StringComparison.OrdinalIgnoreCase)) continue;
            int processId;
            if (!Int32.TryParse(argument.Substring(probePrefix.Length), out processId))
            {
                EmitStatus("ERROR", "PROBE_PID_INVALID");
                return 5;
            }
            CommandLineEvidence commandLine = ReadProcessCommandLine(processId);
            Emit(new Dictionary<string, object> {
                { "type", "probe" }, { "process_id", processId },
                { "command_line_available", commandLine.Value.Length > 0 },
                { "command_line_method", commandLine.Method },
                { "command_line_query_succeeded", commandLine.QuerySucceeded },
                { "command_line_failure_reason", commandLine.FailureReason },
                { "command_line_win32_error", commandLine.Win32Error },
                { "khanza_jar_text_present", ContainsKhanzaJarText(commandLine.Value) },
                { "khanza_jar_launch_argument", KhanzaJarLaunchArgumentPattern.IsMatch(commandLine.Value ?? "") },
                { "khanza_jar_boundary", DescribeKhanzaJarBoundary(commandLine.Value) },
                { "khanza_jar_detected", IsKhanzaJavaProcess("java", commandLine.Value) }
            });
            return commandLine.Value.Length > 0 ? 0 : 6;
        }
        try
        {
            string dll = FindBridgeDll();
            if (dll.Length == 0 || !SetDllDirectory(Path.GetDirectoryName(dll)))
            {
                EmitStatus("ERROR", "JAB_DLL_NOT_FOUND");
                return 3;
            }
            Windows_run();
            Stopwatch warmup = Stopwatch.StartNew();
            while (warmup.ElapsedMilliseconds < 2500) { Application.DoEvents(); Thread.Sleep(10); }

            SimpleEvent focus = OnFocusEvent;
            SimpleEvent selection = OnSelectionEvent;
            SimpleEvent visible = OnVisibleDataEvent;
            TextEvent table = OnTableModelEvent;
            TextEvent value = OnValueEvent;
            ShutdownEvent shutdown = OnShutdown;
            SetFocusGained(focus);
            SetSelection(selection);
            SetVisibleData(visible);
            SetTableModel(table);
            SetValue(value);
            SetJavaShutdown(shutdown);
            EmitStatus("READY", "JAB_ACTIVE");
            if (_overlayProbe) EmitProbeRuntime();

            Stopwatch fallback = Stopwatch.StartNew();
            while (true)
            {
                Application.DoEvents();
                FlushOverlayClear();
                bool shouldScan = Interlocked.Exchange(ref _dirty, 0) != 0 || fallback.ElapsedMilliseconds >= 1000;
                if (!shouldScan) { Thread.Sleep(10); continue; }
                fallback.Restart();
                // A short debounce lets the Swing detail finish the current event
                // burst. Two independent reads below remain the stability gate.
                Thread.Sleep(50);
                Candidate first = Scan();
                Thread.Sleep(50);
                Candidate second = Scan();
                BindStableQueueIdentity(first, second);
                InvalidateIfChanged(first);
                Interlocked.Exchange(ref _dirty, 0); // Ignore read-induced accessibility chatter.
                // The two complete reads above already prove the current JAB
                // state. Do not let callbacks caused by those reads clear the
                // geometry that is about to be published.
                Interlocked.Exchange(ref _overlayClearPending, 0);
                _overlayRevision = "";
                Publish(first, second);
                if (_overlayEnabled) { try { PublishOverlay(first, second); } catch { ClearOverlay(); } }
                if (_overlayProbe) { try { PublishOverlayProbe(first, second); } catch { EmitProbeFailure(); } }
                GC.KeepAlive(focus); GC.KeepAlive(selection); GC.KeepAlive(visible);
                GC.KeepAlive(table); GC.KeepAlive(value); GC.KeepAlive(shutdown);
            }
        }
        catch (Exception exc)
        {
            EmitStatus("ERROR", exc.GetType().Name);
            return 1;
        }
    }

    private static void MarkDirtyAndRelease(int vm, long evt, long source)
    {
        Interlocked.Exchange(ref _dirty, 1);
        if (evt != 0) releaseJavaObject(vm, evt);
        if (source != 0) releaseJavaObject(vm, source);
    }

    private static void OnFocusEvent(int vm, long evt, long source)
    {
        // Focus moves between Swing children during normal use and does not
        // change row geometry or prescription identity. It still requests a
        // fresh scan, but must not blank an already proven overlay.
        MarkDirtyAndRelease(vm, evt, source);
    }

    private static void OnSelectionEvent(int vm, long evt, long source)
    {
        if (_overlayEnabled) QueueOverlayClear("JAB_SELECTION_CHANGED");
        MarkDirtyAndRelease(vm, evt, source);
    }

    private static void OnVisibleDataEvent(int vm, long evt, long source)
    {
        if (_overlayEnabled) QueueOverlayClear("JAB_VISIBLE_DATA_CHANGED");
        MarkDirtyAndRelease(vm, evt, source);
    }

    private static void OnTableModelEvent(int vm, long evt, long source, IntPtr oldValue, IntPtr newValue)
    {
        if (_overlayEnabled) QueueOverlayClear("JAB_TABLE_MODEL_CHANGED");
        MarkDirtyAndRelease(vm, evt, source);
    }

    private static void OnValueEvent(int vm, long evt, long source, IntPtr oldValue, IntPtr newValue)
    {
        if (_overlayEnabled) QueueOverlayClear("JAB_VALUE_CHANGED");
        MarkDirtyAndRelease(vm, evt, source);
    }

    private static void OnShutdown(int vm)
    {
        _lastFingerprint = "";
        _lastPrescription = "";
        ClearPendingIdentity();
        Interlocked.Exchange(ref _dirty, 1);
        EmitStatus("DISCONNECTED", "JAVA_SHUTDOWN");
    }

    private static Candidate Scan()
    {
        Candidate result = new Candidate();
        HashSet<string> tables = new HashSet<string>(StringComparer.Ordinal);
        Stopwatch timer = Stopwatch.StartNew();
        int nodes = 0;
        int visibleJavaWindows = 0;
        WindowCallback callback = delegate(IntPtr window, IntPtr state)
        {
            // EnumWindows includes numerous hidden Swing helper/owner windows.
            // They cannot contain the operator-visible prescription and made
            // every stability pair traverse the same inaccessible UI repeatedly.
            if (!IsWindowVisible(window)) return true;
            uint pid;
            GetWindowThreadProcessId(window, out pid);
            string processName;
            try { using (Process process = Process.GetProcessById((int)pid)) processName = process.ProcessName; }
            catch { return true; }
            if ((!String.Equals(processName, "java", StringComparison.OrdinalIgnoreCase) &&
                !String.Equals(processName, "javaw", StringComparison.OrdinalIgnoreCase)) || !isJavaWindow(window)) return true;
            visibleJavaWindows++;
            result.JavaJabCandidateFound = true;
            DiscoveryProbe probe = new DiscoveryProbe {
                ProcessId = (int)pid, ProcessName = processName,
                VisibleWindow = true, JavaJabWindowMatched = true
            };
            result.DiscoveryProbes.Add(probe);
            SelectPrimaryDiscoveryProbe(result, probe);
            int vm; long context;
            if (!getAccessibleContextFromHWND(window, out vm, out context)) return true;
            result.Accessible = true;
            result.JabAttached = true;
            probe.AccessibleRootObtained = true;
            CommandLineEvidence commandLine = ReadProcessCommandLine((int)pid);
            probe.CommandLineMethod = commandLine.Method;
            probe.CommandLineQuerySucceeded = commandLine.QuerySucceeded;
            probe.CommandLineFailureReason = commandLine.FailureReason;
            probe.CommandLineWin32Error = commandLine.Win32Error;
            probe.KhanzaJarTextPresent = ContainsKhanzaJarText(commandLine.Value);
            bool jarEvidence = IsKhanzaJavaProcess(processName, commandLine.Value);
            probe.KhanzaJarMatched = jarEvidence;
            UiSignatureEvidence signature = jarEvidence ? new UiSignatureEvidence {
                AccessibleRootObtained = true
            } : InspectKhanzaUiSignature(vm, context);
            probe.RootFrameMatched = signature.RootFrameMatched;
            probe.MenuBarMatched = signature.MenuBarMatched;
            probe.DesktopPaneMatched = signature.DesktopPaneMatched;
            probe.SignatureMatched = signature.SignatureMatched;
            probe.RootChildCount = signature.RootChildCount;
            probe.SignatureNodesScanned = signature.NodesScanned;
            SelectPrimaryDiscoveryProbe(result, probe);
            bool signatureEvidence = signature.SignatureMatched;
            if (!jarEvidence && !signatureEvidence)
            {
                result.DetectionEvidence = "UNVERIFIED_JAVA";
                Release(vm, context);
                return true;
            }
            result.TargetKhanzaFound = true;
            if (result.TargetKhanzaProcessId == 0)
            {
                result.TargetKhanzaProcessId = (int)pid;
                result.DetectionEvidence = jarEvidence ? "KHANZA_JAR" : "JAB_UI_SIGNATURE";
            }
            result.KhanzaDetected = true;
            try { Walk(result, tables, vm, context, 0, timer, ref nodes, window, null, false, null); }
            finally { Release(vm, context); }
            // Once one complete detail subtree has been read, additional visible
            // Swing helper/owner windows cannot add clinical rows. Stop this
            // scan early; the second independent scan remains mandatory.
            if (HasCompleteDetailPayload(result)) return false;
            return timer.ElapsedMilliseconds < 1500 && nodes < 5000;
        };
        EnumWindows(callback, IntPtr.Zero);
        GC.KeepAlive(callback);
        result.ScanMilliseconds = timer.ElapsedMilliseconds;
        result.NodesRead = nodes;
        result.VisibleJavaWindows = visibleJavaWindows;
        if (timer.ElapsedMilliseconds >= 1500 || nodes >= 5000) result.ReadError = true;
        return result;
    }

    private static bool IsKhanzaJavaProcess(string processName, string commandLine)
    {
        bool javaRuntime = String.Equals(processName, "java", StringComparison.OrdinalIgnoreCase) ||
            String.Equals(processName, "javaw", StringComparison.OrdinalIgnoreCase);
        string value = commandLine ?? "";
        return javaRuntime && (KhanzaJarPattern.IsMatch(value) ||
            KhanzaJarLaunchArgumentPattern.IsMatch(value));
    }

    private sealed class KhanzaRuntimeProbe
    {
        public bool Found;
        public int ProcessId;
        public uint SessionId;
        public string Architecture = "unknown";
        public string ExecutablePath = "";
        public string CommandLineMethod = "NONE";
        public bool CommandLineQuerySucceeded;
        public bool KhanzaJarMatched;
    }

    private static bool ContainsKhanzaJarText(string commandLine)
    {
        return (commandLine ?? "").IndexOf("khanza.jar", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    // Diagnostic-only: describe the surrounding character classes without
    // emitting the command line or a filesystem path.
    private static string DescribeKhanzaJarBoundary(string commandLine)
    {
        string value = commandLine ?? "";
        int index = value.IndexOf("khanza.jar", StringComparison.OrdinalIgnoreCase);
        if (index < 0) return "TEXT_NOT_PRESENT";
        int after = index + "khanza.jar".Length;
        return "BEFORE_" + DescribeBoundaryCharacter(index > 0 ? value[index - 1] : '\0') +
            "_AFTER_" + DescribeBoundaryCharacter(after < value.Length ? value[after] : '\0');
    }

    private static string DescribeBoundaryCharacter(char value)
    {
        if (value == '\0') return "END";
        if (Char.IsLetterOrDigit(value)) return "ALNUM";
        if (Char.IsWhiteSpace(value)) return "SPACE";
        if (value == '.') return "DOT";
        if (value == '-') return "HYPHEN";
        if (value == '_') return "UNDERSCORE";
        if (value == '\\') return "BACKSLASH";
        if (value == '/') return "SLASH";
        if (value == '"') return "QUOTE";
        return "OTHER";
    }

    private static CommandLineEvidence ReadProcessCommandLine(int processId)
    {
        CommandLineEvidence evidence = new CommandLineEvidence { Method = "WMI" };
        // WMI is queried only for an already-visible Java/JAB window and its PID.
        // The command itself is never emitted or logged.
        try
        {
            using (ManagementObjectSearcher searcher = new ManagementObjectSearcher(
                "SELECT CommandLine FROM Win32_Process WHERE ProcessId=" + processId.ToString()))
            {
                foreach (ManagementObject row in searcher.Get())
                {
                    string commandLine = Convert.ToString(row["CommandLine"]) ?? "";
                    if (commandLine.Length > 0)
                    {
                        evidence.Value = commandLine;
                        evidence.QuerySucceeded = true;
                        return evidence;
                    }
                }
            }
            evidence.FailureReason = "WMI_EMPTY";
        }
        catch (Exception exc)
        {
            // Keep the type only; ManagementException details may include endpoint data.
            evidence.FailureReason = "WMI_" + exc.GetType().Name;
        }

        // Some endpoints deny WMI even for a visible Java process. The x86 PEB
        // fallback is read-only and is attempted only on this proven Java/JAB PID.
        CommandLineEvidence peb = ReadX86ProcessCommandLine(processId);
        if (peb.QuerySucceeded) return peb;
        evidence.Method = "WMI>PEB_X86";
        evidence.FailureReason = evidence.FailureReason + ";" + peb.FailureReason;
        evidence.Win32Error = peb.Win32Error;
        return evidence;
    }

    private static string ContextRole(ContextInfo info)
    {
        string role = Normalize(info.roleUS);
        return role.Length > 0 ? role : Normalize(info.role);
    }

    private static UiSignatureEvidence InspectKhanzaUiSignature(int vm, long root)
    {
        UiSignatureEvidence evidence = new UiSignatureEvidence();
        ContextInfo rootInfo;
        if (!getAccessibleContextInfo(vm, root, out rootInfo)) return evidence;
        evidence.AccessibleRootObtained = true;
        evidence.RootFrameMatched = Normalize(ContextRole(rootInfo)) == "frame";
        evidence.RootChildCount = Math.Max(rootInfo.children, 0);
        ScanKhanzaUiRoles(vm, root, 0, ref evidence.NodesScanned,
            ref evidence.MenuBarMatched, ref evidence.DesktopPaneMatched);
        // Structural JAB evidence only. No window title, hospital name, geometry,
        // theme/color, accessible name, patient identity, or prescription content.
        evidence.SignatureMatched = IsKhanzaStructuralSignature(
            evidence.RootFrameMatched ? "frame" : "", evidence.MenuBarMatched, evidence.DesktopPaneMatched);
        return evidence;
    }

    private static bool IsKhanzaStructuralSignature(string rootRole, bool menuBar, bool desktopPane)
    {
        return Normalize(rootRole) == "frame" && menuBar && desktopPane;
    }

    private static void ScanKhanzaUiRoles(int vm, long context, int depth, ref int nodes,
        ref bool menuBar, ref bool desktopPane)
    {
        if (depth > 6 || nodes >= 160 || (menuBar && desktopPane)) return;
        ContextInfo info;
        if (!getAccessibleContextInfo(vm, context, out info)) return;
        nodes++;
        string role = ContextRole(info);
        if (role == "menu bar") menuBar = true;
        if (role == "desktop pane") desktopPane = true;
        int children = Math.Min(Math.Max(info.children, 0), 48);
        for (int index = 0; index < children && nodes < 160 && !(menuBar && desktopPane); index++)
        {
            long child = getAccessibleChildFromContext(vm, context, index);
            if (child == 0) continue;
            try { ScanKhanzaUiRoles(vm, child, depth + 1, ref nodes, ref menuBar, ref desktopPane); }
            finally { Release(vm, child); }
        }
    }

    private static CommandLineEvidence ReadX86ProcessCommandLine(int processId)
    {
        CommandLineEvidence evidence = new CommandLineEvidence { Method = "PEB_X86" };
        const uint ProcessQueryInformation = 0x0400;
        const uint ProcessVmRead = 0x0010;
        const int PebProcessParametersOffset = 0x10;
        const int ProcessParametersCommandLineOffset = 0x40;
        if (IntPtr.Size != 4) { evidence.FailureReason = "PEB_REQUIRES_X86"; return evidence; }
        IntPtr process = OpenProcess(ProcessQueryInformation | ProcessVmRead, false, processId);
        if (process == IntPtr.Zero)
        {
            evidence.FailureReason = "OPEN_PROCESS_FAILED";
            evidence.Win32Error = Marshal.GetLastWin32Error();
            return evidence;
        }
        try
        {
            ProcessBasicInformation basic;
            int returned;
            int ntStatus = NtQueryInformationProcess(process, 0, out basic,
                Marshal.SizeOf(typeof(ProcessBasicInformation)), out returned);
            if (ntStatus != 0 || basic.PebBaseAddress == IntPtr.Zero)
            {
                evidence.FailureReason = "NT_QUERY_FAILED:" + ntStatus.ToString();
                return evidence;
            }
            byte[] pointerBytes = new byte[4];
            IntPtr read;
            if (!ReadProcessMemory(process, IntPtr.Add(basic.PebBaseAddress,
                PebProcessParametersOffset), pointerBytes, pointerBytes.Length, out read))
            {
                evidence.FailureReason = "READ_PEB_PARAMETERS_FAILED";
                evidence.Win32Error = Marshal.GetLastWin32Error();
                return evidence;
            }
            IntPtr parameters = new IntPtr(BitConverter.ToInt32(pointerBytes, 0));
            if (parameters == IntPtr.Zero) { evidence.FailureReason = "PEB_PARAMETERS_EMPTY"; return evidence; }
            byte[] unicodeString = new byte[8];
            if (!ReadProcessMemory(process, IntPtr.Add(parameters,
                ProcessParametersCommandLineOffset), unicodeString, unicodeString.Length, out read))
            {
                evidence.FailureReason = "READ_COMMAND_LINE_DESCRIPTOR_FAILED";
                evidence.Win32Error = Marshal.GetLastWin32Error();
                return evidence;
            }
            int length = BitConverter.ToUInt16(unicodeString, 0);
            if (length <= 0 || length > 32766) { evidence.FailureReason = "COMMAND_LINE_LENGTH_INVALID"; return evidence; }
            IntPtr buffer = new IntPtr(BitConverter.ToInt32(unicodeString, 4));
            if (buffer == IntPtr.Zero) { evidence.FailureReason = "COMMAND_LINE_BUFFER_EMPTY"; return evidence; }
            byte[] text = new byte[length];
            if (!ReadProcessMemory(process, buffer, text, text.Length, out read) ||
                read.ToInt32() != text.Length)
            {
                evidence.FailureReason = "READ_COMMAND_LINE_TEXT_FAILED";
                evidence.Win32Error = Marshal.GetLastWin32Error();
                return evidence;
            }
            evidence.Value = Encoding.Unicode.GetString(text);
            evidence.QuerySucceeded = evidence.Value.Length > 0;
            if (!evidence.QuerySucceeded) evidence.FailureReason = "COMMAND_LINE_EMPTY";
            return evidence;
        }
        catch (Exception exc) { evidence.FailureReason = "PEB_" + exc.GetType().Name; return evidence; }
        finally { CloseHandle(process); }
    }

    private static void SelectPrimaryDiscoveryProbe(Candidate candidate, DiscoveryProbe probe)
    {
        if (candidate.PrimaryDiscoveryProbe == null || DiscoveryProbeScore(probe) > DiscoveryProbeScore(candidate.PrimaryDiscoveryProbe))
            candidate.PrimaryDiscoveryProbe = probe;
    }

    private static int DiscoveryProbeScore(DiscoveryProbe probe)
    {
        return (probe.KhanzaJarMatched ? 16 : 0) + (probe.SignatureMatched ? 8 : 0) +
            (probe.AccessibleRootObtained ? 4 : 0) + (probe.JavaJabWindowMatched ? 2 : 0) +
            (probe.VisibleWindow ? 1 : 0);
    }

    private static Dictionary<string, object> DiscoveryProbePayload(DiscoveryProbe probe)
    {
        if (probe == null) return new Dictionary<string, object>();
        return new Dictionary<string, object> {
            { "pid", probe.ProcessId }, { "process_name", probe.ProcessName },
            { "visible_window", probe.VisibleWindow }, { "jab_window_matched", probe.JavaJabWindowMatched },
            { "accessible_root_obtained", probe.AccessibleRootObtained },
            { "command_line_method", probe.CommandLineMethod },
            { "command_line_query_succeeded", probe.CommandLineQuerySucceeded },
            { "khanza_jar_text_present", probe.KhanzaJarTextPresent },
            { "khanza_jar_matched", probe.KhanzaJarMatched },
            { "command_line_failure_reason", probe.CommandLineFailureReason },
            { "command_line_win32_error", probe.CommandLineWin32Error },
            { "root_frame_matched", probe.RootFrameMatched },
            { "menu_bar_matched", probe.MenuBarMatched },
            { "desktop_pane_matched", probe.DesktopPaneMatched },
            { "signature_final_matched", probe.SignatureMatched },
            { "root_child_count", probe.RootChildCount },
            { "signature_nodes_scanned", probe.SignatureNodesScanned }
        };
    }
    private static void Walk(Candidate result, HashSet<string> seenTables, int vm, long context,
        int depth, Stopwatch timer, ref int nodes, IntPtr window, int[] clip, bool viewport,
        int[] viewportRect,
        List<OverlayProbeNode> path = null)
    {
        if (depth > 30 || nodes >= 5000 || timer.ElapsedMilliseconds >= 1500) { result.ReadError = true; return; }
        ContextInfo info;
        if (!getAccessibleContextInfo(vm, context, out info)) { result.ReadError = true; return; }
        nodes++;
        if (_overlayProbe) {
            path = path == null ? new List<OverlayProbeNode>() : new List<OverlayProbeNode>(path);
            path.Add(new OverlayProbeNode { role = ProbeRole(info.roleUS), rect = RawBounds(info) });
        }
        ObserveCareSetting(result, info);
        if (_overlayEnabled) {
            clip = ClipAccessible(clip, info);
            viewport = viewport || info.roleUS == "viewport";
            if (info.roleUS == "viewport" && info.width > 0 && info.height > 0)
                viewportRect = Bounds(info);
        }
        if (info.roleUS == "table")
        {
            ReadTable(result, seenTables, vm, context, window, clip, viewport,
                Bounds(info), viewportRect, path);
            return;
        }
        if (info.roleUS == "text")
        {
            Match care = CareIdPattern.Match(info.name ?? "");
            if (care.Success)
            {
                if (result.DetailNoRawat.Length > 0 && result.DetailNoRawat != care.Value)
                    result.DetailIdentityAmbiguous = true;
                else
                    result.DetailNoRawat = care.Value;
            }
        }
        if (info.children < 0 || info.children > 2000) { result.ReadError = true; return; }
        for (int index = 0; index < info.children; index++)
        {
            long child = getAccessibleChildFromContext(vm, context, index);
            if (child == 0) continue;
            try { Walk(result, seenTables, vm, child, depth + 1, timer, ref nodes,
                window, clip, viewport, viewportRect, path); }
            finally { Release(vm, child); }
        }
    }

    private static void ReadTable(Candidate result, HashSet<string> seenTables, int vm, long context,
        IntPtr window, int[] clip, bool viewport, int[] tableRect, int[] viewportRect,
        List<OverlayProbeNode> path)
    {
        TableInfo table;
        if (!getAccessibleTableInfo(vm, context, out table)) { result.ReadError = true; return; }
        try
        {
            string tableKey = vm.ToString() + ":" + table.table.ToString();
            if (!seenTables.Add(tableKey) || table.rows < 0 || table.rows > 1000 || table.columns < 0 || table.columns > 80) return;
            List<string> headers = Headers(vm, context);
            int noResep = HeaderIndex(headers, "no.resep", "no. resep", "no resep");
            int noRawat = HeaderIndex(headers, "no.rawat", "no. rawat", "no rawat");
            if (noResep >= 0 && noRawat >= 0)
            {
                ObserveProbeWindow(result, window, path);
                result.KhanzaDetected = true;
                int selected = -1, count = 0;
                for (int row = 0; row < table.rows; row++) if (isAccessibleTableRowSelected(vm, table.table, row)) { selected = row; count++; }
                if (getAccessibleTableRowSelectionCount(vm, table.table) != count) { result.ReadError = true; return; }
                if (count == 1)
                {
                    // Some Khanza renderers expose a decorated accessibility
                    // value (for example HTML used for the red queue row) rather
                    // than only the visible cell text. Canonicalize the two
                    // identifiers by their strict Khanza formats. Ambiguous or
                    // missing values remain empty and therefore fail closed.
                    string prescription = ExtractSinglePrescriptionId(
                        Cell(vm, table.table, selected, noResep));
                    string care = ExtractSingleCareId(
                        Cell(vm, table.table, selected, noRawat));
                    int patientIdColumn = HeaderIndex(headers, "no.rm", "no. rm", "no rm");
                    int patientNameColumn = HeaderIndex(headers, "pasien", "nama pasien");
                    int prescriberColumn = HeaderIndex(headers, "dokter peresep", "dokter");
                    string patientId = DisplayCell(vm, table.table, selected, patientIdColumn, 40);
                    string patientName = DisplayCell(vm, table.table, selected, patientNameColumn, 160);
                    string prescriber = DisplayCell(vm, table.table, selected, prescriberColumn, 160);
                    if (result.NoResep.Length > 0 && (result.NoResep != prescription || result.NoRawat != care)) result.AmbiguousIdentity = true;
                    else {
                        result.NoResep = prescription;
                        result.NoRawat = care;
                        result.PatientId = patientId;
                        result.PatientName = patientName;
                        result.PrescriberName = prescriber;
                    }
                }
                return;
            }

            if (HeaderIndex(headers, "nama racikan") >= 0)
            {
                ObserveProbeWindow(result, window, path);
                result.KhanzaDetected = true;
                result.DetailFound = true;
                result.CompoundGroups += table.rows;
                return;
            }
            int code = HeaderIndex(headers, "kode barang", "kode obat", "kd barang");
            int name = HeaderIndex(headers, "nama barang", "nama obat", "obat");
            int quantity = HeaderIndex(headers, "jumlah", "jml");
            if (code < 0 || name < 0 || quantity < 0) return;
            ObserveProbeWindow(result, window, path);
            result.KhanzaDetected = true;
            result.DetailFound = true;
            bool compounded = HeaderIndex(headers, "jml") >= 0 && HeaderIndex(headers, "jumlah") < 0;
            OverlayProbeTable probe = null;
            if (_overlayProbe && result.OverlayProbeTables.Count < 8) {
                probe = new OverlayProbeTable { hwnd = window.ToInt64(), model_rows = table.rows,
                    columns = table.columns, name_column = name, hierarchy = path,
                    clip = Clip(viewportRect, tableRect) };
                result.OverlayProbeTables.Add(probe);
            }
            List<Item> rows = ReadItems(vm, table, headers, code, name, quantity, compounded,
                result, window, tableRect, viewportRect, probe);
            // Khanza keeps an empty compound-component JTable in the tree even
            // for a regular prescription. It is UI scaffolding, not a clinical
            // compound table. A declared compound group with no active component
            // still fails closed because CompoundGroups will exceed this count.
            AddItemRows(result, rows, compounded);
        }
        finally { ReleaseTable(vm, table); }
    }

    private static List<string> Headers(int vm, long context)
    {
        List<string> values = new List<string>();
        TableInfo headers;
        if (!getAccessibleTableColumnHeader(vm, context, out headers)) return values;
        try
        {
            if (headers.rows < 1 || headers.columns < 0 || headers.columns > 80) return values;
            for (int column = 0; column < headers.columns; column++)
                values.Add(Normalize(Cell(vm, headers.table, 0, column)));
        }
        finally { ReleaseTable(vm, headers); }
        return values;
    }

    private static List<Item> ReadItems(int vm, TableInfo table, List<string> headers,
        int code, int name, int quantity, bool compounded, Candidate candidate,
        IntPtr window, int[] tableRect, int[] viewportRect, OverlayProbeTable probe)
    {
        List<Item> values = new List<Item>();
        int signa = HeaderIndex(headers, "aturan pakai", "signa");
        for (int row = 0; row < table.rows; row++)
        {
            string drugCode = Cell(vm, table.table, row, code).Trim();
            ContextInfo nameInfo;
            string drugName = Cell(vm, table.table, row, name, out nameInfo).Trim();
            string rawQuantity = Cell(vm, table.table, row, quantity).Trim();
            if (drugCode.Length == 0 && drugName.Length == 0) continue;
            if (!PositiveQuantity(rawQuantity)) continue;
            if (drugCode.Length == 0 || drugName.Length == 0) throw new InvalidDataException("ITEM_IDENTITY_INCOMPLETE");
            Item item = new Item();
            item.source_item_key = (compounded ? "compound:" : "regular:") + (row + 1).ToString();
            item.drug_code = drugCode;
            item.drug_name = drugName;
            item.raw_quantity = rawQuantity;
            item.raw_signa = signa < 0 ? "" : Cell(vm, table.table, row, signa).Trim();
            values.Add(item);
            if (_overlayEnabled) {
                string group = compounded ? "racikan:" + (candidate.CompoundTables.Count + 1) : "";
                int[] rawRect = Bounds(nameInfo);
                int[] tableViewport = Clip(viewportRect, tableRect);
                int[] clippedRect = tableViewport == null ? null : Clip(tableViewport, rawRect);
                string geometrySource = "cell";
                if (!PositiveRect(clippedRect)) {
                    clippedRect = DeriveVisibleTableRow(tableRect, viewportRect, table.rows, row);
                    geometrySource = "uniform_table_row";
                    if (PositiveRect(clippedRect)) candidate.OverlayDerivedRows++;
                }
                if (rawRect[2] > 0 && rawRect[3] > 0) candidate.OverlayRawPositiveRows++;
                if (PositiveRect(clippedRect)) candidate.OverlayClippedPositiveRows++;
                if (probe != null) {
                    probe.captured++;
                    if (rawRect[2] > 0 && rawRect[3] > 0) probe.raw_positive++;
                    if (PositiveRect(clippedRect)) probe.clipped_positive++;
                    if (geometrySource == "uniform_table_row" && PositiveRect(clippedRect))
                        probe.derived_positive++;
                    if (probe.cells.Count < 3) {
                        OverlayProbeCell sample = new OverlayProbeCell {
                            row = row, raw = RawBounds(nameInfo), clipped = clippedRect,
                            component = nameInfo.component, role = ProbeRole(nameInfo.roleUS),
                            geometry_source = geometrySource };
                        probe.cells.Add(sample);
                    }
                }
                candidate.OverlayRows[item] = new OverlayRow {
                    source_item_key = (compounded ? group + ":" : "") + item.source_item_key,
                    drug_code = item.drug_code, compound_group = group,
                    hwnd = window.ToInt64(), rect = clippedRect, geometry_source = geometrySource
                };
            }
        }
        return values;
    }

    private static void AddItemRows(Candidate candidate, List<Item> rows, bool compounded)
    {
        if (compounded)
        {
            if (rows.Count > 0) candidate.CompoundTables.Add(rows);
        }
        else candidate.Regular.AddRange(rows);
    }

    private static bool HasCompleteDetailPayload(Candidate candidate)
    {
        return !candidate.ReadError && !candidate.DetailIdentityAmbiguous &&
            !candidate.CareSettingAmbiguous && candidate.DetailFound &&
            candidate.DetailNoRawat.Length > 0 && candidate.CareSetting.Length > 0 &&
            candidate.Regular.Count + candidate.CompoundItemCount > 0 &&
            (candidate.CompoundGroups == 0
                ? candidate.CompoundTables.Count == 0
                : candidate.CompoundTables.Count == candidate.CompoundGroups);
    }

    private static string Cell(int vm, long table, int row, int column)
    {
        ContextInfo ignored;
        return Cell(vm, table, row, column, out ignored);
    }

    private static string Cell(int vm, long table, int row, int column, out ContextInfo info)
    {
        info = new ContextInfo();
        if (column < 0) return "";
        CellInfo cell;
        if (!getAccessibleTableCellInfo(vm, table, row, column, out cell)) throw new InvalidDataException("CELL_READ_FAILED");
        try
        {
            if (!getAccessibleContextInfo(vm, cell.context, out info)) throw new InvalidDataException("CELL_CONTEXT_FAILED");
            return String.IsNullOrWhiteSpace(info.name) ? (info.description ?? "") : info.name;
        }
        finally { Release(vm, cell.context); }
    }

    private static string DisplayCell(int vm, long table, int row, int column, int maximum)
    {
        if (column < 0) return "";
        string raw = Cell(vm, table, row, column);
        string withoutMarkup = Regex.Replace(raw ?? "", "<[^>]*>", " ");
        string normalized = Regex.Replace(
            HttpUtility.HtmlDecode(withoutMarkup) ?? "", @"\s+", " ").Trim();
        return normalized.Length <= maximum ? normalized : "";
    }

    private static void AssignDiscoveryStates(Candidate candidate)
    {
        candidate.IdentityState = candidate.KhanzaDetected ? "KHANZA_CONNECTED" :
            (candidate.JavaJabCandidateFound ?
                (candidate.JabAttached ? "KHANZA_UNVERIFIED" : "JAB_ATTACH_FAILED") :
                "KHANZA_NOT_FOUND");
        candidate.PrescriptionState = candidate.KhanzaDetected && candidate.Complete ?
            "PRESCRIPTION_READY" : "PRESCRIPTION_VIEW_NOT_FOUND";
    }

    // Discovery is observed twice before a snapshot can be published. Preserve a
    // candidate seen by either read so a transient second scan never turns an
    // observed Java/JAB window into the misleading KHANZA_NOT_FOUND state.
    private static void PreserveCandidateEvidence(Candidate current, Candidate observed)
    {
        if (current.KhanzaDetected || !observed.JavaJabCandidateFound) return;
        current.JavaJabCandidateFound = true;
        current.JabAttached = current.JabAttached || observed.JabAttached;
        if (current.PrimaryDiscoveryProbe == null && observed.PrimaryDiscoveryProbe != null)
        {
            current.PrimaryDiscoveryProbe = observed.PrimaryDiscoveryProbe;
            current.DiscoveryProbes.Add(observed.PrimaryDiscoveryProbe);
        }
        if (current.DetectionEvidence.Length == 0)
            current.DetectionEvidence = observed.DetectionEvidence;
    }

    private static void Publish(Candidate first, Candidate second)
    {
        PreserveCandidateEvidence(second, first);
        AssignDiscoveryStates(second);
        string connectionState = second.KhanzaDetected ? "CONNECTED" : "DISCONNECTED";
        string connectionReason = second.IdentityState;
        string connectionSignature = connectionState + "|" + connectionReason + "|" + second.PrescriptionState;
        if (connectionSignature != _lastConnectionState)
        {
            EmitStatus(connectionState, connectionReason, second);
            _lastConnectionState = connectionSignature;
        }
        if (!second.KhanzaDetected)
        {
            _lastFingerprint = "";
            _lastPrescription = "";
            _lastInvalid = "";
            ClearPendingIdentity();
            return;
        }
        if (!first.Complete || !second.Complete)
        {
            string key = second.NoResep;
            string reason = DiagnosticReason(second);
            string invalid = key + "|" + reason;
            if (key.Length > 0 && invalid != _lastInvalid)
            {
                Emit(new Dictionary<string, object> { { "type", "invalidated" }, { "no_resep", key }, { "reason", reason } });
                _lastInvalid = invalid;
            }
            EmitDiagnostic(second, reason);
            return;
        }
        string firstFingerprint = Fingerprint(first);
        string secondFingerprint = Fingerprint(second);
        if (firstFingerprint != secondFingerprint) return;
        _overlayRevision = secondFingerprint;
        _lastInvalid = "";
        _lastDiagnostic = "";
        if (secondFingerprint == _lastFingerprint) return;
        _lastFingerprint = secondFingerprint;
        _lastPrescription = second.NoResep;
        List<Item> compounded = new List<Item>();
        for (int group = 0; group < second.CompoundTables.Count; group++)
        {
            foreach (Item item in second.CompoundTables[group])
            {
                item.compound_group = "racikan:" + (group + 1).ToString();
                item.source_item_key = item.compound_group + ":" + item.source_item_key;
                compounded.Add(item);
            }
        }
        Dictionary<string, object> header = new Dictionary<string, object>();
        header["no_resep"] = second.NoResep;
        header["no_rawat"] = second.NoRawat;
        header["patient_id"] = second.PatientId;
        header["patient_name"] = second.PatientName;
        header["prescriber_name"] = second.PrescriberName;
        header["status"] = "DRAFT";
        header["care_setting"] = second.CareSetting;
        Dictionary<string, object> message = new Dictionary<string, object>();
        message["type"] = "snapshot";
        message["schema"] = 1;
        message["stable"] = true;
        message["composition_complete"] = true;
        message["captured_at"] = DateTime.UtcNow.ToString("o");
        message["header"] = header;
        message["regular_items"] = second.Regular;
        message["compounded_items"] = compounded;
        message["revision"] = secondFingerprint;
        message["stability_pair_ms"] = first.ScanMilliseconds + second.ScanMilliseconds + 75;
        message["nodes_read"] = first.NodesRead + second.NodesRead;
        message["visible_java_windows"] = Math.Max(first.VisibleJavaWindows, second.VisibleJavaWindows);
        Emit(message);
    }

    private static void BindStableQueueIdentity(Candidate first, Candidate second)
    {
        bool firstHas = first.NoResep.Length > 0 && first.NoRawat.Length > 0;
        bool secondHas = second.NoResep.Length > 0 && second.NoRawat.Length > 0;
        if (firstHas && secondHas)
        {
            if (first.NoResep == second.NoResep && first.NoRawat == second.NoRawat &&
                first.PatientId == second.PatientId &&
                first.PatientName == second.PatientName &&
                first.PrescriberName == second.PrescriberName &&
                !first.AmbiguousIdentity && !second.AmbiguousIdentity)
            {
                _pendingNoResep = second.NoResep;
                _pendingNoRawat = second.NoRawat;
                _pendingPatientId = second.PatientId;
                _pendingPatientName = second.PatientName;
                _pendingPrescriberName = second.PrescriberName;
                _pendingCareSetting = second.CareSetting;
                _pendingIdentityAt = DateTime.UtcNow;
                if (first.CareSettingAmbiguous || second.CareSettingAmbiguous ||
                    first.CareSetting != second.CareSetting)
                    ClearPendingIdentity();
            }
            else
            {
                ClearPendingIdentity();
                first.AmbiguousIdentity = true;
                second.AmbiguousIdentity = true;
            }
            return;
        }
        if (firstHas != secondHas)
        {
            ClearPendingIdentity();
            first.AmbiguousIdentity = true;
            second.AmbiguousIdentity = true;
            return;
        }
        BindPendingIdentity(first);
        BindPendingIdentity(second);
    }

    private static void BindPendingIdentity(Candidate candidate)
    {
        if (!candidate.DetailFound || _pendingNoResep.Length == 0 ||
            DateTime.UtcNow - _pendingIdentityAt > TimeSpan.FromMinutes(5)) return;
        if (candidate.DetailNoRawat.Length == 0 || candidate.DetailIdentityAmbiguous ||
            candidate.DetailNoRawat != _pendingNoRawat)
        {
            candidate.AmbiguousIdentity = true;
            ClearPendingIdentity();
            return;
        }
        candidate.NoResep = _pendingNoResep;
        candidate.NoRawat = _pendingNoRawat;
        candidate.PatientId = _pendingPatientId;
        candidate.PatientName = _pendingPatientName;
        candidate.PrescriberName = _pendingPrescriberName;
        if (candidate.CareSetting.Length == 0)
            candidate.CareSetting = _pendingCareSetting;
        else if (_pendingCareSetting.Length > 0 && candidate.CareSetting != _pendingCareSetting)
            candidate.CareSettingAmbiguous = true;
    }

    private static void ClearPendingIdentity()
    {
        _pendingNoResep = "";
        _pendingNoRawat = "";
        _pendingPatientId = "";
        _pendingPatientName = "";
        _pendingPrescriberName = "";
        _pendingCareSetting = "";
        _pendingIdentityAt = DateTime.MinValue;
    }

    private static void ObserveCareSetting(Candidate candidate, ContextInfo info)
    {
        string name = Normalize(info.name);
        if (name != "rawat jalan" && name != "rawat inap") return;
        string states = (info.statesUS ?? "").ToLowerInvariant();
        bool selectedTab = Normalize(info.roleUS) == "page tab" &&
            Regex.IsMatch(states, @"(^|,\s*)selected(\s*,|$)", RegexOptions.CultureInvariant);
        // The prescription detail exposes the Tarif value as an accessible text
        // component.  Accept that exact value as a second independent source,
        // while deliberately excluding the Rawat Jalan/Rawat Inap menu buttons.
        bool detailText = Normalize(info.roleUS) == "text";
        if (!selectedTab && !detailText)
            return;
        string detected = name == "rawat jalan" ? "RALAN" : "RANAP";
        if (candidate.CareSetting.Length > 0 && candidate.CareSetting != detected)
            candidate.CareSettingAmbiguous = true;
        else
            candidate.CareSetting = detected;
    }

    private static bool RunSelfTest()
    {
        bool quantity = PositiveQuantity("1") && PositiveQuantity("0.5") &&
            !PositiveQuantity("") && !PositiveQuantity("0") && !PositiveQuantity("0,0");
        ClearPendingIdentity();
        ContextInfo selectedRalan = new ContextInfo {
            name = "Rawat Jalan", roleUS = "page tab", statesUS = "enabled,selected,visible"
        };
        Candidate careCandidate = new Candidate();
        ObserveCareSetting(careCandidate, selectedRalan);
        ContextInfo detailRalan = new ContextInfo {
            name = "Rawat Jalan", roleUS = "text", statesUS = "enabled,visible"
        };
        Candidate detailCareCandidate = new Candidate();
        ObserveCareSetting(detailCareCandidate, detailRalan);
        ContextInfo menuRanap = new ContextInfo {
            name = "Rawat Inap", roleUS = "push button", statesUS = "enabled,visible"
        };
        ObserveCareSetting(detailCareCandidate, menuRanap);
        Candidate ambiguousCareCandidate = new Candidate();
        ObserveCareSetting(ambiguousCareCandidate, detailRalan);
        ContextInfo detailRanap = new ContextInfo {
            name = "Rawat Inap", roleUS = "text", statesUS = "enabled,visible"
        };
        ObserveCareSetting(ambiguousCareCandidate, detailRanap);
        Candidate queueA = new Candidate { NoResep = "RX-SELF", NoRawat = "2026/09/05/000001",
            PatientId = "RM-SELF", PatientName = "Pasien Self Test",
            PrescriberName = "Dokter A", CareSetting = careCandidate.CareSetting };
        Candidate queueB = new Candidate { NoResep = "RX-SELF", NoRawat = "2026/09/05/000001",
            PatientId = "RM-SELF", PatientName = "Pasien Self Test",
            PrescriberName = "Dokter A", CareSetting = careCandidate.CareSetting };
        BindStableQueueIdentity(queueA, queueB);
        Candidate detailA = new Candidate { DetailFound = true, DetailNoRawat = "2026/09/05/000001" };
        Candidate detailB = new Candidate { DetailFound = true, DetailNoRawat = "2026/09/05/000001" };
        BindStableQueueIdentity(detailA, detailB);
        bool bound = detailA.NoResep == "RX-SELF" && detailB.NoResep == "RX-SELF" &&
            detailA.NoRawat == "2026/09/05/000001" && detailB.NoRawat == "2026/09/05/000001" &&
            detailA.PatientId == "RM-SELF" && detailB.PatientName == "Pasien Self Test" &&
            detailA.PrescriberName == "Dokter A" &&
            detailA.CareSetting == "RALAN" && detailB.CareSetting == "RALAN";
        Candidate wrong = new Candidate { DetailFound = true, DetailNoRawat = "2026/09/05/000002" };
        BindPendingIdentity(wrong);
        bool mismatchRejected = wrong.AmbiguousIdentity && _pendingNoResep.Length == 0;
        Candidate hiddenCompound = new Candidate();
        AddItemRows(hiddenCompound, new List<Item>(), true);
        Candidate activeCompound = new Candidate();
        AddItemRows(activeCompound, new List<Item> { new Item() }, true);
        bool hiddenCompoundIgnored = hiddenCompound.CompoundTables.Count == 0 &&
            activeCompound.CompoundTables.Count == 1;
        bool decoratedIdentity =
            ExtractSinglePrescriptionId("<html><font color='red'>202609050012</font></html>") == "202609050012" &&
            ExtractSingleCareId("row: 2026/09/05/000002") == "2026/09/05/000002" &&
            ExtractSinglePrescriptionId("202609050012 202609050013") == "";
        Candidate completePayload = new Candidate {
            DetailFound = true, DetailNoRawat = "2026/09/05/000001", CareSetting = "RALAN"
        };
        completePayload.Regular.Add(new Item {
            drug_code = "OBAT-1", drug_name = "Obat Uji", raw_quantity = "1"
        });
        bool earlyStopSafe = HasCompleteDetailPayload(completePayload);
        completePayload.CareSettingAmbiguous = true;
        bool ambiguousNotStopped = !HasCompleteDetailPayload(completePayload);
        Candidate orderA = new Candidate { NoResep = "RX-ORDER", NoRawat = "2026/09/05/000003", PatientId = "RM-ORDER" };
        orderA.Regular.Add(new Item { source_item_key = "row:1", drug_code = "OBAT-A", raw_quantity = "1" });
        orderA.Regular.Add(new Item { source_item_key = "row:2", drug_code = "OBAT-B", raw_quantity = "2" });
        Candidate orderB = new Candidate { NoResep = "RX-ORDER", NoRawat = "2026/09/05/000003", PatientId = "RM-ORDER" };
        orderB.Regular.Add(new Item { source_item_key = "row:2", drug_code = "OBAT-B", raw_quantity = "2" });
        orderB.Regular.Add(new Item { source_item_key = "row:1", drug_code = "OBAT-A", raw_quantity = "1" });
        Candidate changedOrder = new Candidate { NoResep = "RX-ORDER", NoRawat = "2026/09/05/000003", PatientId = "RM-ORDER" };
        changedOrder.Regular.Add(new Item { source_item_key = "row:1", drug_code = "OBAT-A", raw_quantity = "1" });
        changedOrder.Regular.Add(new Item { source_item_key = "row:2", drug_code = "OBAT-B", raw_quantity = "3" });
        bool rowOrderStable = Fingerprint(orderA) == Fingerprint(orderB) &&
            Fingerprint(orderA) != Fingerprint(changedOrder);
        bool khanzaJavaDetected = IsKhanzaJavaProcess("java",
            "java -jar C:\\SIMRS\\khanza.jar");
        bool khanzaJavawDetected = IsKhanzaJavaProcess("javaw",
            "javaw -jar \"C:\\SIMRS\\KHANZA.JAR\"");
        bool khanzaEqualsArgumentDetected = IsKhanzaJavaProcess("java",
            "java -jar=C:\\SIMRS\\khanza.jar");
        bool khanzaQuotedEqualsArgumentDetected = IsKhanzaJavaProcess("javaw",
            "javaw -jar=\"C:\\SIMRS\\khanza.jar\"");
        bool khanzaProductPrefixedDetected = IsKhanzaJavaProcess("java",
            "java -cp C:\\SIMRS\\SIMRSKhanza.jar");
        bool khanzaPathArgumentDetected = IsKhanzaJavaProcess("java",
            "java -jar C:\\SIMRS\\release-khanza.jar\\..\\khanza.jar");
        bool otherJavaRejected = !IsKhanzaJavaProcess("java",
            "java -jar C:\\Tools\\reporting.jar") &&
            !IsKhanzaJavaProcess("java", "java -jar C:\\Tools\\reporting-khanza.jar") &&
            !IsKhanzaJavaProcess("java", "java -jar C:\\SIMRS\\khanza.jar.bak");
        bool signatureAccepted = IsKhanzaStructuralSignature("frame", true, true);
        bool signatureRejected = !IsKhanzaStructuralSignature("frame", true, false) &&
            !IsKhanzaStructuralSignature("dialog", true, true);
        Candidate connectedWithoutPrescription = new Candidate { KhanzaDetected = true };
        AssignDiscoveryStates(connectedWithoutPrescription);
        Candidate prescriptionReady = new Candidate {
            KhanzaDetected = true, DetailFound = true, NoResep = "RX-READY",
            NoRawat = "2026/09/05/000004", CareSetting = "RALAN"
        };
        prescriptionReady.Regular.Add(new Item { drug_code = "OBAT-READY", raw_quantity = "1" });
        AssignDiscoveryStates(prescriptionReady);
        bool discoveryStates = connectedWithoutPrescription.IdentityState == "KHANZA_CONNECTED" &&
            connectedWithoutPrescription.PrescriptionState == "PRESCRIPTION_VIEW_NOT_FOUND" &&
            prescriptionReady.IdentityState == "KHANZA_CONNECTED" &&
            prescriptionReady.PrescriptionState == "PRESCRIPTION_READY";
        Candidate firstUnverified = new Candidate {
            JavaJabCandidateFound = true, JabAttached = true,
            DetectionEvidence = "UNVERIFIED_JAVA"
        };
        Candidate secondWithoutCandidate = new Candidate();
        PreserveCandidateEvidence(secondWithoutCandidate, firstUnverified);
        AssignDiscoveryStates(secondWithoutCandidate);
        bool candidateNeverMisreportedMissing =
            secondWithoutCandidate.IdentityState == "KHANZA_UNVERIFIED" &&
            secondWithoutCandidate.DetectionEvidence == "UNVERIFIED_JAVA";
        ClearPendingIdentity();
        return quantity && careCandidate.CareSetting == "RALAN" &&
            detailCareCandidate.CareSetting == "RALAN" && bound && mismatchRejected &&
            ambiguousCareCandidate.CareSettingAmbiguous && hiddenCompoundIgnored &&
            decoratedIdentity && earlyStopSafe && ambiguousNotStopped && rowOrderStable &&
            khanzaJavaDetected && khanzaJavawDetected && khanzaEqualsArgumentDetected &&
            khanzaQuotedEqualsArgumentDetected && khanzaProductPrefixedDetected && khanzaPathArgumentDetected && otherJavaRejected && signatureAccepted &&
            signatureRejected && discoveryStates && candidateNeverMisreportedMissing && OverlaySelfTest();
    }

    private static string ExtractSinglePrescriptionId(string value)
    {
        MatchCollection matches = PrescriptionIdPattern.Matches(value ?? "");
        return matches.Count == 1 ? matches[0].Value : "";
    }

    private static string ExtractSingleCareId(string value)
    {
        MatchCollection matches = CareIdPattern.Matches(value ?? "");
        return matches.Count == 1 ? matches[0].Value : "";
    }

    private static string DiagnosticReason(Candidate candidate)
    {
        if (candidate.ReadError) return "UI_READ_ERROR";
        if (candidate.AmbiguousIdentity || candidate.DetailIdentityAmbiguous)
            return "PATIENT_IDENTITY_AMBIGUOUS";
        if (candidate.CareSettingAmbiguous) return "CARE_SETTING_AMBIGUOUS";
        if (!candidate.DetailFound) return "DETAIL_NOT_DETECTED";
        if (candidate.NoResep.Length == 0 || candidate.NoRawat.Length == 0)
            return candidate.DetailNoRawat.Length == 0 ?
                "DETAIL_CARE_ID_NOT_READABLE" : "QUEUE_IDENTITY_NOT_BOUND";
        if (candidate.CareSetting.Length == 0) return "CARE_SETTING_NOT_DETECTED";
        if (candidate.Regular.Count + candidate.CompoundItemCount == 0)
            return "NO_COMMITTED_ITEMS";
        if (candidate.CompoundGroups != candidate.CompoundTables.Count)
            return "COMPOUND_INCOMPLETE";
        return "DATA_INCOMPLETE";
    }

    private static void EmitDiagnostic(Candidate candidate, string reason)
    {
        string signature = reason + "|" + candidate.DetailFound.ToString() + "|" +
            candidate.Regular.Count.ToString() + "|" + candidate.CompoundItemCount.ToString() + "|" +
            candidate.CompoundGroups.ToString() + "|" + candidate.CompoundTables.Count.ToString() + "|" +
            candidate.CareSetting;
        if (signature == _lastDiagnostic) return;
        _lastDiagnostic = signature;
        Emit(new Dictionary<string, object> {
            { "type", "diagnostic" }, { "reason", reason },
            { "detail_detected", candidate.DetailFound },
            { "identity_bound", candidate.NoResep.Length > 0 && candidate.NoRawat.Length > 0 },
            { "regular_count", candidate.Regular.Count },
            { "compound_count", candidate.CompoundItemCount },
            { "compound_group_count", candidate.CompoundGroups },
            { "compound_table_count", candidate.CompoundTables.Count },
            { "care_setting", candidate.CareSetting },
            { "scan_ms", candidate.ScanMilliseconds },
            { "nodes_read", candidate.NodesRead },
            { "visible_java_windows", candidate.VisibleJavaWindows },
            { "target_khanza_found", candidate.TargetKhanzaFound },
            { "target_khanza_pid", candidate.TargetKhanzaProcessId },
            { "detection_evidence", candidate.DetectionEvidence },
            { "jab_attached", candidate.JabAttached },
            { "identity_state", candidate.IdentityState },
            { "prescription_state", candidate.PrescriptionState },
            { "discovery_probe", DiscoveryProbePayload(candidate.PrimaryDiscoveryProbe) }
        });
    }

    private static void InvalidateIfChanged(Candidate first)
    {
        if (_lastFingerprint.Length == 0 || _lastPrescription.Length == 0) return;
        string current = first.Complete ? Fingerprint(first) : "";
        if (current == _lastFingerprint) return;
        Emit(new Dictionary<string, object> {
            { "type", "invalidated" },
            { "no_resep", _lastPrescription },
            { "reason", "UI_NOT_STABLE" }
        });
        _lastFingerprint = "";
        _lastPrescription = "";
    }

    private static string Fingerprint(Candidate candidate)
    {
        StringBuilder text = new StringBuilder();
        text.Append(candidate.NoResep).Append('\u001f').Append(candidate.NoRawat);
        text.Append('\u001f').Append(candidate.PatientId);
        // JAB may enumerate the same visible rows in a different order between
        // the two stability reads.  The prescription identity is a set of row
        // values, so canonicalize that set before comparing scans.  Keep each
        // compound group in its own namespace because group membership remains
        // clinically meaningful.
        List<string> rows = new List<string>();
        foreach (Item item in candidate.Regular)
            rows.Add("regular\u001f" + item.source_item_key + "\u001f" + item.drug_code + "\u001f" + item.raw_quantity);
        for (int group = 0; group < candidate.CompoundTables.Count; group++)
            foreach (Item item in candidate.CompoundTables[group])
                rows.Add("racikan:" + (group + 1).ToString() + "\u001f" + item.drug_code + "\u001f" + item.raw_quantity);
        rows.Sort(StringComparer.Ordinal);
        foreach (string row in rows)
            text.Append('\u001e').Append(row);
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text.ToString()))).Replace("-", "").ToLowerInvariant();
    }

    private static bool PositiveQuantity(string value)
    {
        bool digit = false, nonzero = false;
        foreach (char character in value)
            if (Char.IsDigit(character)) { digit = true; if (character != '0') nonzero = true; }
        return digit && nonzero;
    }

    private static int HeaderIndex(List<string> headers, params string[] names)
    {
        foreach (string name in names)
        {
            int index = headers.IndexOf(name);
            if (index >= 0) return index;
        }
        return -1;
    }

    private static string Normalize(string value)
    {
        return (value ?? "").Trim().ToLowerInvariant();
    }

    private static void Release(int vm, long value)
    {
        if (value != 0) releaseJavaObject(vm, value);
    }

    private static void ReleaseTable(int vm, TableInfo table)
    {
        Release(vm, table.caption); Release(vm, table.summary);
        Release(vm, table.context); Release(vm, table.table);
    }

    private static KhanzaRuntimeProbe FindKhanzaRuntime()
    {
        KhanzaRuntimeProbe result = new KhanzaRuntimeProbe();
        WindowCallback callback = delegate(IntPtr window, IntPtr state)
        {
            if (!IsWindowVisible(window)) return true;
            uint pid;
            GetWindowThreadProcessId(window, out pid);
            string processName;
            try
            {
                using (Process process = Process.GetProcessById((int)pid))
                    processName = process.ProcessName;
            }
            catch { return true; }
            if (!String.Equals(processName, "java", StringComparison.OrdinalIgnoreCase) &&
                !String.Equals(processName, "javaw", StringComparison.OrdinalIgnoreCase)) return true;
            CommandLineEvidence commandLine = ReadProcessCommandLine((int)pid);
            if (!IsKhanzaJavaProcess(processName, commandLine.Value)) return true;
            uint sessionId;
            ProcessIdToSessionId(pid, out sessionId);
            result.Found = true;
            result.ProcessId = (int)pid;
            result.SessionId = sessionId;
            result.Architecture = GetProcessArchitecture((int)pid);
            result.ExecutablePath = GetProcessExecutablePath((int)pid);
            result.CommandLineMethod = commandLine.Method;
            result.CommandLineQuerySucceeded = commandLine.QuerySucceeded;
            result.KhanzaJarMatched = true;
            return false;
        };
        EnumWindows(callback, IntPtr.Zero);
        GC.KeepAlive(callback);
        return result;
    }

    private static string GetProcessArchitecture(int processId)
    {
        IntPtr process = OpenProcess(ProcessQueryLimitedInformation, false, processId);
        if (process == IntPtr.Zero) return "unknown";
        try
        {
            try
            {
                ushort processMachine, nativeMachine;
                if (IsWow64Process2(process, out processMachine, out nativeMachine))
                {
                    if (processMachine == ImageFileMachineI386) return "x86";
                    if (processMachine == ImageFileMachineAmd64) return "x64";
                    if (processMachine == ImageFileMachineUnknown)
                        return nativeMachine == ImageFileMachineAmd64 ? "x64" : "x86";
                }
            }
            catch (EntryPointNotFoundException) { }
            bool wow64;
            if (IsWow64Process(process, out wow64))
                return wow64 ? "x86" : (Environment.Is64BitOperatingSystem ? "x64" : "x86");
            return "unknown";
        }
        finally { CloseHandle(process); }
    }

    private static string GetProcessExecutablePath(int processId)
    {
        IntPtr process = OpenProcess(ProcessQueryLimitedInformation, false, processId);
        if (process == IntPtr.Zero) return "";
        try
        {
            StringBuilder path = new StringBuilder(32768);
            int length = path.Capacity;
            return QueryFullProcessImageName(process, 0, path, ref length) ? path.ToString() : "";
        }
        finally { CloseHandle(process); }
    }

    private static string FindBridgeDll()
    {
        List<string> candidates = new List<string>();
        string configured = Environment.GetEnvironmentVariable("EMSS_KHANZA_JAB_DLL") ?? "";
        if (configured.Length > 0) candidates.Add(configured);
        KhanzaRuntimeProbe runtime = FindKhanzaRuntime();
        if (runtime.Found && runtime.ExecutablePath.Length > 0)
            candidates.Add(Path.Combine(Path.GetDirectoryName(runtime.ExecutablePath), Dll));
        string javaHome = Environment.GetEnvironmentVariable("JAVA_HOME") ?? "";
        if (javaHome.Length > 0) candidates.Add(Path.Combine(javaHome, "bin", Dll));
#if BRIDGE_X64
        string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string bell = Path.Combine(programFiles, "BellSoft");
#else
        string programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        string bell = Path.Combine(programFilesX86, "BellSoft");
#endif
        if (Directory.Exists(bell))
        {
            try
            {
                foreach (string directory in Directory.GetDirectories(bell, "*"))
                    candidates.Add(Path.Combine(directory, "bin", Dll));
            }
            catch (UnauthorizedAccessException) { }
        }
        foreach (string candidate in candidates) if (File.Exists(candidate)) return Path.GetFullPath(candidate);
        return "";
    }

    private static void EmitStatus(string state, string reason, Candidate candidate = null)
    {
        Dictionary<string, object> message = new Dictionary<string, object> {
            { "type", "status" }, { "state", state }, { "reason", reason }
        };
        if (candidate != null)
        {
            message["target_khanza_found"] = candidate.TargetKhanzaFound;
            message["target_khanza_pid"] = candidate.TargetKhanzaProcessId;
            message["detection_evidence"] = candidate.DetectionEvidence;
            message["jab_attached"] = candidate.JabAttached;
            message["identity_state"] = candidate.IdentityState;
            message["prescription_state"] = candidate.PrescriptionState;
            message["discovery_probe"] = DiscoveryProbePayload(candidate.PrimaryDiscoveryProbe);
        }
        Emit(message);
    }

    private static void Emit(object value)
    {
        lock (OutputLock)
        {
            Console.Out.WriteLine(Json.Serialize(value));
            Console.Out.Flush();
        }
    }
}
