package pl.drogowskazy.sora;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int REQUEST_ZIP = 1001;
    private static final int REQUEST_NOTIFICATIONS = 1002;
    private static final int REQUEST_DB_RESTORE = 1003;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button openButton;
    private Button startButton;
    private Button selectButton;
    private Button restoreButton;
    private Button stopButton;
    private FrameLayout container;
    private ScrollView settingsView;
    private NativePanel panel;
    private boolean panelNeedsReload;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        container = new FrameLayout(this);
        container.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
        settingsView = buildUi();
        container.addView(settingsView);
        setContentView(container);
        requestNotificationPermission();
        refreshStatus();
        prepareAndStart();
    }

    private void prepareAndStart() {
        if (!ProjectStore.needsBundledInstall(this)) {
            status.setText("Uruchamianie Drogowskazów…");
            DrogowskazyService.start(this);
            waitForServer(true);
            return;
        }
        status.setText("Przygotowywanie programu…");
        setBusy(true);
        if (ProjectStore.isInstalled(this)) DrogowskazyService.stopForUpdate(this);
        executor.execute(() -> {
            try {
                if (!waitForRuntimeStopped(65_000L)) {
                    throw new IllegalStateException("Nie udało się bezpiecznie zatrzymać poprzedniej wersji.");
                }
                ProjectStore.installBundled(this);
                handler.post(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    setBusy(false);
                    DrogowskazyService.start(this);
                    waitForServer(true);
                });
            } catch (Exception error) {
                handler.post(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    status.setText("Nie udało się przygotować programu: " + error.getMessage());
                    setBusy(false);
                });
            }
        });
    }

    private ScrollView buildUi() {
        int pad = dp(18);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);
        root.setBackgroundColor(Color.rgb(248, 250, 252));

        TextView title = new TextView(this);
        title.setText("Drogowskazy Sora");
        title.setTextSize(28);
        title.setTextColor(Color.rgb(17, 24, 39));
        title.setPadding(0, 0, 0, dp(8));
        root.addView(title, matchWrap());

        TextView subtitle = new TextView(this);
        subtitle.setText("Program gotowy po instalacji • praca w tle");
        subtitle.setTextSize(16);
        subtitle.setTextColor(Color.rgb(75, 85, 99));
        subtitle.setPadding(0, 0, 0, dp(18));
        root.addView(subtitle, matchWrap());

        status = new TextView(this);
        status.setTextSize(16);
        status.setTextColor(Color.rgb(17, 24, 39));
        status.setBackgroundColor(Color.WHITE);
        status.setPadding(dp(14), dp(14), dp(14), dp(14));
        root.addView(status, matchWrap());

        Button select = makeButton("Wybierz / zaktualizuj ZIP Drogowskazów");
        selectButton = select;
        select.setOnClickListener(v -> chooseZip());
        root.addView(select, buttonParams());

        Button restoreDb = makeButton("Przywróć kopię bazy SQLite");
        restoreButton = restoreDb;
        restoreDb.setOnClickListener(v -> chooseDatabaseBackup());
        root.addView(restoreDb, buttonParams());

        startButton = makeButton("Uruchom ponownie usługę");
        startButton.setOnClickListener(v -> {
            if (!ProjectStore.isInstalled(this)) {
                toast("Najpierw wybierz ZIP programu");
                return;
            }
            DrogowskazyService.start(this);
            status.setText("Uruchamianie serwera…");
            waitForServer(false);
        });
        root.addView(startButton, buttonParams());

        openButton = makeButton("Otwórz panel Drogowskazów");
        openButton.setOnClickListener(v -> {
            if (!ProjectStore.isInstalled(this)) {
                toast("Najpierw wybierz ZIP programu");
                return;
            }
            DrogowskazyService.start(this);
            waitForServer(true);
        });
        root.addView(openButton, buttonParams());

        Button stop = makeButton("Zatrzymaj pracę w tle");
        stopButton = stop;
        stop.setOnClickListener(v -> {
            DrogowskazyService.stop(this);
            status.setText("Zatrzymywanie…");
            handler.postDelayed(this::refreshStatus, 1200);
        });
        root.addView(stop, buttonParams());

        Button battery = makeButton("Ustawienia baterii — ustaw Bez ograniczeń");
        battery.setOnClickListener(v -> openBatterySettings());
        root.addView(battery, buttonParams());

        TextView note = new TextView(this);
        note.setText("Program przygotuje się i otworzy sam. Przy aktualizacji zachowa obecną bazę SQLite. Panel, wybór plików i folderów oraz zapis wyników działają w aplikacji. Przycisk Wstecz w panelu otwiera ten ekran ustawień.\n\nMożesz wygasić ekran lub przejść do innej aplikacji. Dla pracy w tle ustaw baterię na „Bez ograniczeń”.");
        note.setTextSize(14);
        note.setTextColor(Color.rgb(75, 85, 99));
        note.setPadding(0, dp(18), 0, 0);
        root.addView(note, matchWrap());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        return scroll;
    }

    private Button makeButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(16);
        button.setGravity(Gravity.CENTER);
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(12);
        return params;
    }

    private void chooseZip() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "application/zip", "application/x-zip-compressed", "application/octet-stream"
        });
        startActivityForResult(intent, REQUEST_ZIP);
    }

    private void chooseDatabaseBackup() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "application/vnd.sqlite3", "application/x-sqlite3", "application/octet-stream"
        });
        startActivityForResult(intent, REQUEST_DB_RESTORE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (panel != null && panel.handleActivityResult(requestCode, resultCode, data)) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (requestCode == REQUEST_DB_RESTORE) {
            restoreDatabaseBackup(uri);
            return;
        }
        if (requestCode != REQUEST_ZIP) return;
        panelNeedsReload = true;
        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) {
        }
        status.setText("Bezpieczne zatrzymywanie serwera i kolejki…");
        setBusy(true);
        DrogowskazyService.stopForUpdate(this);
        executor.execute(() -> {
            try {
                if (!waitForRuntimeStopped(65_000L)) {
                    throw new IllegalStateException("Nie udało się bezpiecznie zatrzymać pracy w tle. Spróbuj ponownie.");
                }
                handler.post(() -> status.setText("Importowanie ZIP-a… nie zamykaj tej aplikacji."));
                String message = ProjectStore.importZip(this, uri);
                handler.post(() -> {
                    status.setText(message + "\nUruchamianie serwera…");
                    setBusy(false);
                    DrogowskazyService.start(this);
                    waitForServer(true);
                });
            } catch (Exception error) {
                handler.post(() -> {
                    status.setText("Błąd importu: " + error.getMessage());
                    setBusy(false);
                });
            }
        });
    }

    private void restoreDatabaseBackup(Uri uri) {
        panelNeedsReload = true;
        status.setText("Bezpieczne zatrzymywanie przed przywróceniem bazy…");
        setBusy(true);
        DrogowskazyService.stopForUpdate(this);
        executor.execute(() -> {
            try {
                if (!waitForRuntimeStopped(65_000L)) {
                    throw new IllegalStateException("Nie udało się bezpiecznie zatrzymać pracy w tle.");
                }
                handler.post(() -> status.setText("Sprawdzanie i przywracanie bazy SQLite…"));
                String message = ProjectStore.restoreDatabase(this, uri);
                handler.post(() -> {
                    status.setText(message + "\nUruchamianie serwera…");
                    setBusy(false);
                    DrogowskazyService.start(this);
                    waitForServer(true);
                });
            } catch (Exception error) {
                handler.post(() -> {
                    status.setText("Błąd przywracania bazy: " + error.getMessage());
                    setBusy(false);
                });
            }
        });
    }

    private void waitForServer(boolean openBrowserWhenReady) {
        executor.execute(() -> {
            boolean ready = false;
            for (int i = 0; i < 60 && !ready; i++) {
                ready = serverHealthy();
                if (!ready) {
                    try { Thread.sleep(500); } catch (InterruptedException ignored) { break; }
                }
            }
            boolean finalReady = ready;
            handler.post(() -> {
                if (finalReady) {
                    status.setText("Program działa w tle.");
                    if (openBrowserWhenReady) openBrowser();
                } else {
                    status.setText("Serwer jeszcze nie odpowiada. Sprawdź ponownie za chwilę lub wybierz poprawny ZIP.");
                }
            });
        });
    }

    private boolean waitForRuntimeStopped(long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (DrogowskazyService.isRuntimeStopped() && !serverHealthy()) return true;
            try {
                Thread.sleep(250);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return DrogowskazyService.isRuntimeStopped() && !serverHealthy();
    }

    private boolean serverHealthy() {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL("http://127.0.0.1:" + DrogowskazyService.PORT + "/api/health").openConnection();
            c.setConnectTimeout(900);
            c.setReadTimeout(900);
            return c.getResponseCode() == 200;
        } catch (Exception ignored) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void openBrowser() {
        if (isFinishing() || isDestroyed()) return;
        if (panel == null) {
            panel = new NativePanel(this);
            container.addView(panel, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            panel.loadUrl("http://127.0.0.1:" + DrogowskazyService.PORT + "/");
        } else if (panelNeedsReload) {
            panel.reload();
        }
        panelNeedsReload = false;
        settingsView.setVisibility(View.GONE);
        panel.setVisibility(View.VISIBLE);
    }

    private void refreshStatus() {
        if (ProjectStore.isInstalled(this)) {
            status.setText("Program jest zainstalowany. Ustawienia pracy i kopii bazy.");
        } else {
            status.setText("Przygotowywanie programu przy pierwszym uruchomieniu…");
        }
    }

    private void setBusy(boolean busy) {
        startButton.setEnabled(!busy);
        openButton.setEnabled(!busy);
        selectButton.setEnabled(!busy);
        restoreButton.setEnabled(!busy);
        stopButton.setEnabled(!busy);
    }

    private void openBatterySettings() {
        try {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + getPackageName()));
            startActivity(intent);
            toast("Wejdź w Bateria i wybierz Bez ograniczeń");
        } catch (Exception error) {
            startActivity(new Intent(Settings.ACTION_SETTINGS));
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
        }
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onBackPressed() {
        if (panel != null && panel.getVisibility() == View.VISIBLE) {
            panel.setVisibility(View.GONE);
            settingsView.setVisibility(View.VISIBLE);
            refreshStatus();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (panel != null) panel.onResume();
    }

    @Override
    protected void onPause() {
        if (panel != null) panel.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (panel != null) {
            container.removeView(panel);
            panel.close();
        }
        executor.shutdownNow();
        super.onDestroy();
    }
}
