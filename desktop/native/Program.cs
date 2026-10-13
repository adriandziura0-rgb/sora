using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Windows.Forms;

namespace Sora.Native;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        // Tylko jeden host dla danej bazy SQLite. Drugie uruchomienie
        // odsłania istniejące okno z zasobnika, bez drugiego SoraSilnik.exe.
        var homeIndex = Array.IndexOf(args, "--data-dir");
        var home = homeIndex >= 0 && homeIndex + 1 < args.Length
            ? Path.GetFullPath(args[homeIndex + 1])
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "DrogowskazySoraPC");
        var fingerprint = Convert.ToHexString(SHA256.HashData(
            Encoding.UTF8.GetBytes(home.TrimEnd('\\', '/').ToUpperInvariant())))[..28];
        using var single = new Mutex(true, "Local\\Sora_PC_" + fingerprint, out var created);
        using var activate = new EventWaitHandle(false, EventResetMode.AutoReset,
            "Local\\Sora_PC_Show_" + fingerprint);
        if (!created)
        {
            activate.Set();
            return;
        }
        try { Application.Run(new SoraWindow(args, activate)); }
        finally { single.ReleaseMutex(); }
    }
}

internal sealed class SoraWindow : Form
{
    private readonly WebView2 _browser = new() { Dock = DockStyle.Fill, Visible = false };
    private readonly Label _notice = new() {
        Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
        Text = "Uruchamianie Sory z telefonu…", Font = new Font("Segoe UI", 12f)
    };
    private readonly Dictionary<string, string> _folders = new(StringComparer.Ordinal);
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromMinutes(4) };
    private readonly string _home;
    private readonly bool _testUi;
    private readonly bool _testBackground;
    private readonly EventWaitHandle _activate;
    private readonly NotifyIcon _tray;
    private readonly System.Windows.Forms.Timer _watchdog = new() { Interval = 8000 };
    private readonly HttpClient _healthHttp = new() { Timeout = TimeSpan.FromSeconds(4) };
    private readonly Label _connection = new() {
        Dock = DockStyle.Top, Height = 40, Visible = false, AutoEllipsis = true,
        BackColor = Color.FromArgb(255, 234, 204), ForeColor = Color.FromArgb(95, 53, 0),
        TextAlign = ContentAlignment.MiddleCenter,
        Text = "Brak połączenia z silnikiem. Sora próbuje je odzyskać…"
    };
    private bool _allowExit;
    private bool _checkingBackend;
    private bool _restartingBackend;
    private bool _wasDisconnected;
    private bool _showedTrayTip;
    private int _badHealth;
    private Process? _engineProcess;
    private string _url = "";
    private string _secret = "";
    private int _port;
    private bool _tested;

    private static readonly string BridgeScript = """
(() => {
    const pending = new Map();
    let next = 0;
    window.pywebview = {
        api: new Proxy({}, {
            get(_target, method) {
                return (...args) => new Promise((resolve, reject) => {
                    const id = String(++next);
                    pending.set(id, {resolve, reject});
                    window.chrome.webview.postMessage({id, method: String(method), args});
                });
            }
        })
    };
    window.chrome.webview.addEventListener('message', event => {
        const message = event.data || {};
        const promise = pending.get(String(message.id));
        if (!promise) return;
        pending.delete(String(message.id));
        if (message.ok) promise.resolve(message.result);
        else promise.reject(new Error(message.error || 'Błąd Windows'));
    });
    window.dispatchEvent(new Event('pywebviewready'));
})();
""";

    public SoraWindow(string[] args, EventWaitHandle activate)
    {
        _activate = activate;
        Text = "Drogowskazy Sora — interfejs PHONE na Windows";
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(640, 820);
        MinimumSize = new Size(430, 560);
        Controls.Add(_notice);
        Controls.Add(_browser);
        Controls.Add(_connection);
        _testUi = args.Contains("--test-ui");
        _testBackground = args.Contains("--test-background");
        var menu = new ContextMenuStrip();
        menu.Items.Add("Otwórz Sorę", null, (_, _) => RestoreWindow());
        menu.Items.Add("Stan silnika: sprawdź połączenie", null,
            async (_, _) => await CheckBackendAsync());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Zakończ Sorę i zatrzymaj analizę", null, (_, _) => ExitFully());
        _tray = new NotifyIcon {
            Icon = SystemIcons.Application, Visible = !_testUi,
            Text = "Sora PC — analiza w tle", ContextMenuStrip = menu
        };
        _tray.DoubleClick += (_, _) => RestoreWindow();
        int homeIndex = Array.IndexOf(args, "--data-dir");
        _home = homeIndex >= 0 && homeIndex + 1 < args.Length
            ? Path.GetFullPath(args[homeIndex + 1])
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DrogowskazySoraPC");
        Directory.CreateDirectory(_home);
        Shown += async (_, _) => await StartAsync();
        FormClosing += OnClosing;
        FormClosed += (_, _) => {
            _watchdog.Stop();
            _watchdog.Dispose();
            _tray.Visible = false;
            _tray.Dispose();
            _healthHttp.Dispose();
            StopBackend();
        };
        _watchdog.Tick += async (_, _) => {
            if (_activate.WaitOne(0)) RestoreWindow();
            await CheckBackendAsync();
        };
        _watchdog.Start();
    }

    private async Task StartAsync()
    {
        try
        {
            await StartBackendAsync();
            _notice.Text = "Ładowanie oryginalnego panelu PHONE…";
            var webRoot = Path.Combine(_home, "webview-native");
            Directory.CreateDirectory(webRoot);
            var environment = await CoreWebView2Environment.CreateAsync(null, webRoot);
            await _browser.EnsureCoreWebView2Async(environment);
            _browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            _browser.CoreWebView2.Settings.AreHostObjectsAllowed = false;
            _browser.CoreWebView2.Settings.IsWebMessageEnabled = true;
            _browser.CoreWebView2.WebMessageReceived += ReceivedMessage;
            _browser.CoreWebView2.NavigationStarting += (_, e) =>
            {
                if (!IsLocalUrl(e.Uri)) e.Cancel = true;
            };
            _browser.CoreWebView2.NewWindowRequested += (_, e) =>
            {
                e.Handled = true;
                if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri) &&
                    uri.Scheme is "https" or "http")
                    try { Process.Start(new ProcessStartInfo(uri.ToString()) { UseShellExecute = true }); }
                    catch { /* Zewnętrzny link nie jest wymagany do analizy. */ }
            };
            var appFolder = AppContext.BaseDirectory;
            string adapter = await File.ReadAllTextAsync(Path.Combine(appFolder, "windows_adapter.js"), Encoding.UTF8);
            await _browser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(BridgeScript);
            await _browser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(adapter);
            _browser.NavigationCompleted += NavigationFinished;
            _browser.Visible = true;
            _notice.Visible = false;
            _browser.Source = new Uri(_url);
        }
        catch (Exception ex)
        {
            Fail(ex);
        }
    }

    private void RestoreWindow()
    {
        if (IsDisposed || Disposing) return;
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
        BringToFront();
    }

    private void ExitFully()
    {
        _allowExit = true;
        Close();
    }

    private void OnClosing(object? sender, FormClosingEventArgs e)
    {
        // X/Alt+F4 zachowują proces analizy w zasobniku.
        // Testy, restart systemu i wyraźne zakończenie pozwalają zamknąć proces.
        if ((!_testUi || _testBackground) && !_allowExit &&
            e.CloseReason == CloseReason.UserClosing)
        {
            e.Cancel = true;
            Hide();
            if (!_testUi && !_showedTrayTip)
            {
                _showedTrayTip = true;
                _tray.ShowBalloonTip(4500, "Sora analizuje w tle",
                    "Zamknięto okno, ale silnik nadal działa. Dwuklik ikony Sora przy zegarze ponownie otworzy program.",
                    ToolTipIcon.Info);
            }
        }
    }

    private async Task<bool> HealthAsync()
    {
        if (_engineProcess is null || _engineProcess.HasExited || _port <= 0) return false;
        using var request = new HttpRequestMessage(HttpMethod.Get,
            $"http://127.0.0.1:{_port}/api/sora-pc/health");
        request.Headers.TryAddWithoutValidation("Cookie", "sora_native_session=" + _secret);
        using var response = await _healthHttp.SendAsync(request,
            HttpCompletionOption.ResponseHeadersRead);
        return response.IsSuccessStatusCode;
    }

    private async Task CheckBackendAsync()
    {
        if (_checkingBackend || _restartingBackend || IsDisposed || Disposing || _allowExit)
            return;
        _checkingBackend = true;
        try
        {
            bool alive;
            try { alive = await HealthAsync(); }
            catch (Exception) { alive = false; }
            if (alive)
            {
                if (_wasDisconnected && _browser.CoreWebView2 is not null)
                    _browser.Reload();
                _wasDisconnected = false;
                _badHealth = 0;
                _connection.Visible = false;
                _tray.Text = "Sora PC — analiza w tle";
                return;
            }
            _badHealth++;
            if (_badHealth < 2) return; // krótkie przerwy nie przerywają pracy
            _wasDisconnected = true;
            _connection.Visible = Visible;
            _tray.Text = "Sora PC — sprawdzanie silnika";
            // Backend zajęty długą analizą NIE jest zabijany. Uruchamiamy
            // nowy proces wyłącznie, gdy poprzedni naprawdę się zakończył.
            if (_engineProcess is not null && !_engineProcess.HasExited) return;
            _restartingBackend = true;
            try
            {
                _engineProcess?.Dispose();
                _engineProcess = null;
                await StartBackendAsync();
                _badHealth = 0;
                _connection.Visible = false;
                _tray.Text = "Sora PC — analiza w tle";
                _wasDisconnected = false;
                if (_browser.CoreWebView2 is not null)
                    _browser.CoreWebView2.Navigate(_url);
                if (!_testUi && !Visible)
                    _tray.ShowBalloonTip(2500, "Sora — połączenie przywrócone",
                        "Silnik został ponownie uruchomiony. Wcześniej zapisane analizy pozostały w SQLite.",
                        ToolTipIcon.Info);
            }
            catch (Exception ex)
            {
                try { File.AppendAllText(Path.Combine(_home, "diagnostyka_polaczenia.txt"),
                    DateTimeOffset.Now + " " + ex + Environment.NewLine); }
                catch { }
                _connection.Text = "Silnik nie odpowiada. Ponowna próba połączenia za chwilę.";
            }
            finally { _restartingBackend = false; }
        }
        finally { _checkingBackend = false; }
    }

    private async Task StartBackendAsync()
    {
        var exe = Path.Combine(AppContext.BaseDirectory, "_engine", "SoraSilnik", "SoraSilnik.exe");
        if (!File.Exists(exe)) throw new FileNotFoundException("Brak spakowanego silnika Sory z telefonu.", exe);
        var start = new ProcessStartInfo(exe) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
            RedirectStandardError = true, RedirectStandardInput = true,
            WorkingDirectory = Path.GetDirectoryName(exe)!
        };
        start.ArgumentList.Add("--data-dir");
        start.ArgumentList.Add(_home);
        _engineProcess = Process.Start(start) ?? throw new InvalidOperationException("Nie udało się uruchomić silnika.");
        // Stderr drenujemy na bieżąco; brak buforowania może zablokować backend.
        var running = _engineProcess;
        _ = Task.Run(async () =>
        {
            try
            {
                var errors = await running.StandardError.ReadToEndAsync();
                if (!string.IsNullOrWhiteSpace(errors))
                    await File.WriteAllTextAsync(Path.Combine(_home, "diagnostyka_silnika.txt"), errors);
            }
            catch { }
        });
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        while (!timeout.IsCancellationRequested)
        {
            var line = await _engineProcess.StandardOutput.ReadLineAsync(timeout.Token);
            if (line is null) break;
            if (!line.StartsWith("SORA_READY:", StringComparison.Ordinal)) continue;
            using var doc = JsonDocument.Parse(line["SORA_READY:".Length..]);
            var info = doc.RootElement;
            _url = info.GetProperty("url").GetString()!;
            _port = info.GetProperty("port").GetInt32();
            _secret = info.GetProperty("session").GetString()!;
            if (!IsLocalUrl(_url) || _secret.Length < 30) throw new InvalidOperationException("Nieprawidłowa odpowiedź silnika.");
            return;
        }
        throw new InvalidOperationException("Silnik Sory nie zgłosił gotowości w 90 sekund.");
    }

    private bool IsLocalUrl(string? url)
    {
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) &&
               uri.Scheme == Uri.UriSchemeHttp && uri.Host == "127.0.0.1" &&
               uri.Port == _port;
    }

    private async void NavigationFinished(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (!e.IsSuccess) { Fail(new InvalidOperationException("WebView2 nie wczytał panelu PHONE: " + e.WebErrorStatus)); return; }
        if (!_testUi || _tested || _browser.Source.Query.Length > 0) return;
        _tested = true;
        try
        {
            // Test realnego okna: WebView2 musi wykonać JS i odnaleźć ekrany PHONE.
            await Task.Delay(1000);
            var js = await _browser.ExecuteScriptAsync("""
                JSON.stringify({
                  baza: !!document.getElementById('databasePanel'),
                  porownania: !!document.getElementById('databaseComparePanel'),
                  tematy: !!document.getElementById('sameStoryComparePanel'),
                  wspolne: !!document.getElementById('sharedContentPanel'),
                  przycisk: !!document.getElementById('findSharedContentBtn'),
                  bridge: !!window.pywebview?.api?.select_folder,
                  native: document.body.dataset.soraDesktopWindow === 'true',
                  recovery: !!document.getElementById('soraImportClose')
                })
                """);
            var inner = JsonSerializer.Deserialize<string>(js) ?? throw new Exception("Brak JSON z WebView2.");
            using var check = JsonDocument.Parse(inner);
            foreach (var property in check.RootElement.EnumerateObject())
                if (property.Value.ValueKind != JsonValueKind.True)
                    throw new InvalidOperationException("Panel PHONE nie działa w WebView2: " + property.Name);
            // Test funkcjonalny prawdziwej przeglądarki, nie tylko obecności
            // elementów HTML: odczyt statusu SQLite oraz wiadomości JS -> C# -> JS.
            await _browser.ExecuteScriptAsync("""
                window.__soraFunctionalProbe = {done:false};
                (async () => {
                    try {
                        const response = await fetch('/api/baza/status');
                        const data = await response.json();
                        if (!response.ok || !data.stats)
                            throw new Error('Nie działa API bazy.');
                        let rejected = false;
                        try {
                            await window.pywebview.api.list_directory(
                                'nieznany-token-testowy', '', 0, 1);
                        } catch (e) {
                            rejected = true;
                        }
                        window.__soraFunctionalProbe = {
                            done:true, ok:rejected, api:response.status,
                            hasStats:!!data.stats, bridgeErrorHandled:rejected
                        };
                    } catch (e) {
                        window.__soraFunctionalProbe = {
                            done:true, ok:false, error:String(e)
                        };
                    }
                })();
                """);
            bool functional = false;
            for (int attempt = 0; attempt < 55; attempt++)
            {
                await Task.Delay(180);
                var json = await _browser.ExecuteScriptAsync(
                    "JSON.stringify(window.__soraFunctionalProbe || {})");
                var dataString = JsonSerializer.Deserialize<string>(json) ?? "{}";
                using var probe = JsonDocument.Parse(dataString);
                if (!probe.RootElement.TryGetProperty("done", out var done) ||
                    done.ValueKind != JsonValueKind.True) continue;
                if (!probe.RootElement.TryGetProperty("ok", out var ok) ||
                    ok.ValueKind != JsonValueKind.True)
                    throw new InvalidOperationException(
                        "Test połączenia JavaScript–WebView2–SQLite: " + dataString);
                functional = true;
                break;
            }
            if (!functional)
                throw new TimeoutException(
                    "Panel PHONE nie otrzymał odpowiedzi z natywnego mostu Windows.");
            // Próba odczytu API spoza okna, bez sesji, MUSI być odrzucona.
            using (var unauthorized = await _http.GetAsync(
                $"http://127.0.0.1:{_port}/api/baza/status"))
            {
                if ((int)unauthorized.StatusCode != 403)
                    throw new InvalidOperationException(
                        "Prywatna baza PC jest dostępna bez sesji WebView2.");
            }

            // Regresja użytkownika: 40 MB nie może zablokować panelu ani
            // wywołać żądania analizy większego niż 2 MB.
            await _browser.ExecuteScriptAsync("""
                window.__soraRecoveryProbe = {done:false};
                (async () => {
                  try {
                    const mock = Array.from({length:22}, (_, i) => ({
                      name:'duzy-test-'+i+'.txt', size:1900*1024,
                      webkitRelativePath:'Proba/duzy-test-'+i+'.txt'
                    }));
                    await dodajPlikiZFileList(mock, true);
                    const box=document.getElementById('operationProgress');
                    const close=document.getElementById('soraImportClose');
                    const toDatabase=document.getElementById('soraImportDatabase');
                    const shown=!!box && !box.hidden && !!close && !close.hidden &&
                      !!toDatabase && !toDatabase.hidden;
                    if(close) close.click();
                    window.__soraRecoveryProbe = {done:true,shown,closed:!!box?.hidden};
                  } catch(e) {
                    window.__soraRecoveryProbe = {done:true,shown:false,error:String(e)};
                  }
                })();
                """);
            var recoveryPassed = false;
            for(int attempt=0; attempt<40; attempt++)
            {
                await Task.Delay(150);
                var response = await _browser.ExecuteScriptAsync(
                    "JSON.stringify(window.__soraRecoveryProbe || {})");
                var recoveryJson = JsonSerializer.Deserialize<string>(response) ?? "{}";
                using var checkedRecovery=JsonDocument.Parse(recoveryJson);
                if (!checkedRecovery.RootElement.TryGetProperty("done", out var done) ||
                    done.ValueKind != JsonValueKind.True) continue;
                if (!checkedRecovery.RootElement.TryGetProperty("shown", out var shown) ||
                    shown.ValueKind != JsonValueKind.True ||
                    !checkedRecovery.RootElement.GetProperty("closed").GetBoolean())
                    throw new InvalidOperationException(
                        "Komunikat 40 MB nie ma działającego Zamknij: " + recoveryJson);
                recoveryPassed=true;
                break;
            }
            if (!recoveryPassed) throw new TimeoutException("Test zamykania komunikatu 40 MB nie zakończył się.");
            bool passedBackground = false;
            bool passedRestart = false;
            if (_testBackground)
            {
                // To jest test PRAWDZIWEGO obsłużenia kliknięcia X.
                var requestClose = new FormClosingEventArgs(CloseReason.UserClosing, false);
                var originalPid = _engineProcess?.Id;
                OnClosing(this, requestClose);
                if (!requestClose.Cancel || Visible || !await HealthAsync() ||
                    _engineProcess?.Id != originalPid)
                    throw new InvalidOperationException(
                        "Zamknięcie X zatrzymało analizę albo nie ukryło okna.");
                passedBackground = true;
                RestoreWindow();
                if (!Visible || !await HealthAsync())
                    throw new InvalidOperationException(
                        "Nie udało się przywrócić Sory z zasobnika.");

                // Test awarii backendu wyłącznie na pustej bazie CI.
                var crashed = _engineProcess!;
                crashed.Kill(entireProcessTree: true);
                await crashed.WaitForExitAsync();
                await CheckBackendAsync();
                await CheckBackendAsync();
                for (var i = 0; i < 20 && !await HealthAsync(); i++)
                {
                    await Task.Delay(250);
                    await CheckBackendAsync();
                }
                passedRestart = await HealthAsync() &&
                    _engineProcess is not null && _engineProcess.Id != originalPid;
                if (!passedRestart)
                    throw new InvalidOperationException(
                        "Watchdog nie przywrócił silnika po jego awarii.");
                await Task.Delay(500);
            }
            string screenshot = Path.Combine(_home, "PODGLAD_PRAWDZIWEGO_OKNA.png");
            await using (var stream = File.Create(screenshot))
                await _browser.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
            if (new FileInfo(screenshot).Length < 1000) throw new Exception("Pusty zrzut okna WebView2.");
            await File.WriteAllTextAsync(Path.Combine(_home, "OK_PRAWDZIWE_OKNO.json"),
                JsonSerializer.Serialize(new { window = "WebView2 native", phone = true,
                    dataPreserved = true, backgroundVerified = passedBackground,
                    watchdogRestartVerified = passedRestart, controls = inner },
                    new JsonSerializerOptions { WriteIndented = true }));
            Environment.ExitCode = 0;
        }
        catch (Exception ex) { Fail(ex); return; }
        _allowExit = true;
        Close();
    }

    private void ReceivedMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (!IsLocalUrl(e.Source)) return;
        _ = ProcessMessageAsync(e.WebMessageAsJson);
    }

    private async Task ProcessMessageAsync(string raw)
    {
        string id = "";
        try
        {
            using var doc = JsonDocument.Parse(raw);
            var data = doc.RootElement;
            id = data.GetProperty("id").GetString() ?? "";
            var method = data.GetProperty("method").GetString() ?? "";
            var args = data.GetProperty("args");
            object? result = method switch
            {
                "select_folder" => SelectFolder(),
                "list_directory" => ListDirectory(Arg(args, 0), Arg(args, 1),
                                    ArgInt(args, 2, 0), ArgInt(args, 3, 300)),
                "read_file" => ReadFile(Arg(args, 0), Arg(args, 1)),
                "backup_database" => await TransferAsync("backup"),
                "restore_database" => await TransferAsync("restore"),
                "export_transfer" => await TransferAsync("export"),
                "import_transfer" => await TransferAsync("import"),
                _ => throw new InvalidOperationException("Nieznana funkcja panelu PC.")
            };
            Reply(new { id, ok = true, result });
        }
        catch (Exception ex)
        {
            Reply(new { id, ok = false, error = ex.Message });
        }
    }

    private void Reply(object message)
    {
        if (IsDisposed || _browser.CoreWebView2 is null) return;
        _browser.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(message));
    }

    private static string Arg(JsonElement a, int n) =>
        a.ValueKind == JsonValueKind.Array && a.GetArrayLength() > n ? a[n].ToString() : "";

    private static int ArgInt(JsonElement a, int n, int otherwise) =>
        int.TryParse(Arg(a, n), out var value) ? value : otherwise;

    private object? SelectFolder()
    {
        using var dialog = new FolderBrowserDialog { Description = "Wybierz folder artykułów Sory" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return null;
        var folder = Path.GetFullPath(dialog.SelectedPath);
        if (!Directory.Exists(folder)) throw new DirectoryNotFoundException(folder);
        var token = Guid.NewGuid().ToString("N");
        _folders[token] = folder;
        return new { root = token, name = Path.GetFileName(folder.TrimEnd('\\', '/')),
                     path = "", kind = "directory" };
    }

    private string Resolve(string token, string relative)
    {
        if (!_folders.TryGetValue(token, out var basePath)) throw new InvalidOperationException("Wybierz ponownie folder.");
        if (Path.IsPathRooted(relative)) throw new UnauthorizedAccessException("Ścieżka spoza folderu.");
        var full = Path.GetFullPath(Path.Combine(basePath, relative.Replace('/', Path.DirectorySeparatorChar)));
        var allowed = Path.GetFullPath(basePath).TrimEnd('\\') + Path.DirectorySeparatorChar;
        if (!full.StartsWith(allowed, StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(full, basePath, StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException("Plik znajduje się poza wybranym folderem.");
        // Nie pozwalamy wejść przez dowiązania (reparse point) do innego katalogu.
        var current = basePath;
        var tail = Path.GetRelativePath(basePath, full);
        foreach (var part in tail.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            if (part == ".") continue;
            current = Path.Combine(current, part);
            if (File.GetAttributes(current).HasFlag(FileAttributes.ReparsePoint))
                throw new UnauthorizedAccessException("Dowiązanie katalogu jest niedozwolone.");
        }
        return full;
    }

    private object ListDirectory(string token, string relative, int offset, int limit)
    {
        var directory = Resolve(token, relative);
        if (!Directory.Exists(directory)) throw new DirectoryNotFoundException(directory);
        offset = Math.Max(0, offset);
        limit = Math.Clamp(limit, 1, 500);
        var files = Directory.EnumerateFileSystemEntries(directory).Where(path =>
        {
            try
            {
                var attributes = File.GetAttributes(path);
                return !attributes.HasFlag(FileAttributes.ReparsePoint) &&
                       !Path.GetFileName(path).StartsWith(".") &&
                       (attributes.HasFlag(FileAttributes.Directory) ||
                        new[] { ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".htm", ".html" }
                            .Contains(Path.GetExtension(path).ToLowerInvariant()));
            }
            catch { return false; }
        }).OrderBy(path => Directory.Exists(path) ? 0 : 1)
          .ThenBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase).ToArray();
        var page = files.Skip(offset).Take(limit).Select(path => new
        {
            root = token,
            name = Path.GetFileName(path),
            kind = Directory.Exists(path) ? "directory" : "file",
            path = Path.GetRelativePath(_folders[token], path).Replace('\\', '/'),
            size = Directory.Exists(path) ? 0L : new FileInfo(path).Length
        }).ToArray();
        return new { items = page, has_more = offset + page.Length < files.Length };
    }

    private object ReadFile(string token, string relative)
    {
        var path = Resolve(token, relative);
        if (!File.Exists(path)) throw new FileNotFoundException("Brak dokumentu.", path);
        if (new FileInfo(path).Length > 2 * 1024 * 1024)
            throw new InvalidOperationException("Plik jest większy niż 2 MB.");
        return new { base64 = Convert.ToBase64String(File.ReadAllBytes(path)) };
    }

    private async Task<object?> TransferAsync(string method)
    {
        string? file = null;
        if (method is "backup" or "export")
        {
            using var dialog = new SaveFileDialog {
                Filter = method == "backup" ? "Baza SQLite (*.sqlite3)|*.sqlite3" : "TRANSFER (*.zip)|*.zip",
                FileName = method == "backup" ? "Sora_kopia.sqlite3" : "Sora_TRANSFER_PC.zip"
            };
            if (dialog.ShowDialog(this) == DialogResult.OK) file = dialog.FileName;
        }
        else
        {
            using var dialog = new OpenFileDialog {
                Filter = method == "restore" ? "Baza SQLite (*.sqlite3)|*.sqlite3" : "TRANSFER (*.zip)|*.zip",
                CheckFileExists = true
            };
            if (dialog.ShowDialog(this) == DialogResult.OK) file = dialog.FileName;
            if (file is not null && MessageBox.Show(this,
                method == "restore"
                  ? "Baza PC zostanie zastąpiona po wykonaniu kopii. Kontynuować?"
                  : "Pakiet TRANSFER zostanie zweryfikowany i scalony. Kontynuować?",
                "Potwierdzenie Sora", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
                file = null;
        }
        if (file is null) return new { cancelled = true };
        using var request = new HttpRequestMessage(HttpMethod.Post,
            $"http://127.0.0.1:{_port}/api/sora-pc/{method}");
        request.Headers.Add("Cookie", "sora_native_session=" + _secret);
        request.Headers.Add("Origin", $"http://127.0.0.1:{_port}");
        request.Content = JsonContent.Create(new { path = file });
        using var response = await _http.SendAsync(request);
        var payload = await response.Content.ReadAsStringAsync();
        using var data = JsonDocument.Parse(payload);
        if (!response.IsSuccessStatusCode || !data.RootElement.GetProperty("ok").GetBoolean())
            throw new InvalidOperationException(data.RootElement.TryGetProperty("szczegoly", out var err) ?
                err.GetString() : "Błąd transferu lub kopii bazy.");
        return new {
            message = data.RootElement.GetProperty("message").GetString(),
            reload = data.RootElement.GetProperty("reload").GetBoolean()
        };
    }

    private void Fail(Exception ex)
    {
        var path = Path.Combine(_home, "blad_okna_webview2.txt");
        try { File.WriteAllText(path, ex.ToString(), Encoding.UTF8); } catch { }
        if (!_testUi)
            MessageBox.Show(this, ex.Message + "\n\nSzczegóły: " + path +
                "\nWymagany Microsoft Edge WebView2 Runtime.", "Sora — błąd uruchomienia",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        Environment.ExitCode = 1;
        Close();
    }

    private void StopBackend()
    {
        if (_engineProcess is null) return;
        try
        {
            if (!_engineProcess.HasExited)
            {
                _engineProcess.StandardInput.WriteLine("STOP");
                _engineProcess.StandardInput.Flush();
                if (!_engineProcess.WaitForExit(3500)) _engineProcess.Kill(entireProcessTree: true);
            }
        }
        catch { }
        finally { _engineProcess.Dispose(); _engineProcess = null; }
    }
}
