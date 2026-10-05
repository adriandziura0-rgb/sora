package pl.drogowskazy.sora;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int REQUEST_ZIP = 1001;
    private static final int REQUEST_NOTIFICATIONS = 1002;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button openButton;
    private Button startButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        requestNotificationPermission();
        refreshStatus();
        if (ProjectStore.isInstalled(this)) {
            DrogowskazyService.start(this);
            waitForServer(false);
        }
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
        subtitle.setText("APK bez Termuxa • lokalny serwer • praca w tle");
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

        Button select = makeButton("1. Wybierz ZIP Drogowskazów");
        select.setOnClickListener(v -> chooseZip());
        root.addView(select, buttonParams());

        startButton = makeButton("2. Uruchom w tle");
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

        openButton = makeButton("3. Otwórz Drogowskazy");
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
        note.setText("Pierwsze uruchomienie: wybierz ZIP PHONE/ANDROID z Drogowskazami. APK skopiuje projekt do swojej prywatnej pamięci. Przy kolejnej aktualizacji ZIP-a zachowa obecną bazę SQLite, żeby nie stracić danych. Interfejs otwiera się w zwykłej przeglądarce, dzięki czemu wybór folderów działa tak jak wcześniej.\n\nPo uruchomieniu możesz wygasić ekran lub przejść do innej aplikacji. Android nadal może zatrzymać aplikację po ręcznym „Wymuś zatrzymanie”, dlatego ustaw baterię na „Bez ograniczeń”.");
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

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_ZIP || resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) {
        }
        status.setText("Importowanie ZIP-a… nie zamykaj tej aplikacji.");
        startButton.setEnabled(false);
        openButton.setEnabled(false);
        DrogowskazyService.stop(this);
        executor.execute(() -> {
            try {
                String message = ProjectStore.importZip(this, uri);
                handler.post(() -> {
                    status.setText(message + "\nUruchamianie serwera…");
                    startButton.setEnabled(true);
                    openButton.setEnabled(true);
                    DrogowskazyService.start(this);
                    waitForServer(false);
                });
            } catch (Exception error) {
                handler.post(() -> {
                    status.setText("Błąd importu: " + error.getMessage());
                    startButton.setEnabled(true);
                    openButton.setEnabled(true);
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
                    status.setText("Serwer działa w tle.\nhttp://127.0.0.1:" + DrogowskazyService.PORT);
                    if (openBrowserWhenReady) openBrowser();
                } else {
                    status.setText("Serwer jeszcze nie odpowiada. Sprawdź ponownie za chwilę lub wybierz poprawny ZIP.");
                }
            });
        });
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
        Uri uri = Uri.parse("http://127.0.0.1:" + DrogowskazyService.PORT + "/");
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException error) {
            toast("Brak przeglądarki do otwarcia " + uri);
        }
    }

    private void refreshStatus() {
        File root = ProjectStore.projectDir(this);
        if (ProjectStore.isInstalled(this)) {
            status.setText("Projekt jest zainstalowany.\n" + root.getAbsolutePath() + "\nUruchamiam usługę w tle…");
        } else {
            status.setText("Brak zaimportowanego projektu.\nWybierz ZIP PHONE/ANDROID z Drogowskazami.");
        }
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
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
