package pl.drogowskazy.sora;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DrogowskazyService extends Service {
    static final String ACTION_STOP = "pl.drogowskazy.sora.STOP";
    static final String ACTION_STOP_FOR_UPDATE = "pl.drogowskazy.sora.STOP_FOR_UPDATE";
    private static final String PREFS = "drogowskazy_service";
    private static final String KEY_AUTO_RUN = "auto_run";
    static final int PORT = 5433;
    private static final String CHANNEL_ID = "drogowskazy_background";
    private static final int NOTIFICATION_ID = 4569;
    private static final AtomicBoolean RUNTIME_STOPPED = new AtomicBoolean(true);
    private final AtomicBoolean starting = new AtomicBoolean(false);
    private final ExecutorService runtimeExecutor = Executors.newSingleThreadExecutor();
    private volatile boolean stopRequested;
    private ScheduledExecutorService watchdog;
    private PowerManager.WakeLock wakeLock;

    private static void startInternal(Context context, Intent intent) {
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
    }

    public static void start(Context context) {
        context.getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(KEY_AUTO_RUN, true).apply();
        startInternal(context, new Intent(context, DrogowskazyService.class));
    }

    public static void startIfEnabled(Context context) {
        boolean enabled = context.getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean(KEY_AUTO_RUN, true);
        if (enabled && ProjectStore.isInstalled(context)) {
            startInternal(context, new Intent(context, DrogowskazyService.class));
        }
    }

    public static void stop(Context context) {
        context.getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(KEY_AUTO_RUN, false).apply();
        startInternal(context, new Intent(context, DrogowskazyService.class).setAction(ACTION_STOP));
    }

    public static void stopForUpdate(Context context) {
        startInternal(context, new Intent(context, DrogowskazyService.class).setAction(ACTION_STOP_FOR_UPDATE));
    }

    public static boolean isRuntimeStopped() {
        return RUNTIME_STOPPED.get();
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        acquireWakeLock();
        startWatchdog();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && (ACTION_STOP.equals(intent.getAction()) || ACTION_STOP_FOR_UPDATE.equals(intent.getAction()))) {
            stopRequested = true;
            if (ACTION_STOP.equals(intent.getAction())) {
                getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(KEY_AUTO_RUN, false).apply();
            }
            if (watchdog != null) watchdog.shutdownNow();
            startForegroundCompat(buildNotification("Bezpieczne zatrzymywanie…"));
            runtimeExecutor.execute(() -> {
                if (stopRuntime()) stopSelfResult(startId);
                else updateNotification("Nie udało się zatrzymać kolejki — otwórz aplikację");
            });
            return START_NOT_STICKY;
        }
        stopRequested = false;
        if (watchdog == null || watchdog.isShutdown()) startWatchdog();
        RUNTIME_STOPPED.set(false);
        startForegroundCompat(buildNotification("Uruchamianie lokalnego serwera…"));
        ensureRuntime();
        return START_STICKY;
    }

    private void startForegroundCompat(Notification notification) {
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Drogowskazy — praca w tle",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Lokalny serwer analizy i kolejka importu");
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent openPi = PendingIntent.getActivity(
                this, 1, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, DrogowskazyService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(
                this, 2, stop, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle("Drogowskazy Sora")
                .setContentText(text)
                .setOngoing(true)
                .setContentIntent(openPi)
                .addAction(new Notification.Action.Builder(
                        android.R.drawable.ic_media_pause, "Zatrzymaj", stopPi).build())
                .build();
    }

    private void updateNotification(String text) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(text));
    }

    private void acquireWakeLock() {
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "DrogowskazySora:server");
        wakeLock.setReferenceCounted(false);
        wakeLock.acquire();
    }

    private void startWatchdog() {
        watchdog = Executors.newSingleThreadScheduledExecutor();
        watchdog.scheduleWithFixedDelay(() -> {
            if (!ProjectStore.isInstalled(this)) return;
            if (!isHealthy()) ensureRuntime();
        }, 20, 20, TimeUnit.SECONDS);
    }

    private void ensureRuntime() {
        if (stopRequested) return;
        if (!ProjectStore.isInstalled(this)) {
            RUNTIME_STOPPED.set(true);
            updateNotification("Wybierz ZIP programu w aplikacji");
            return;
        }
        if (isHealthy()) {
            updateNotification("Działa w tle • 127.0.0.1:" + PORT);
            return;
        }
        if (!starting.compareAndSet(false, true)) return;
        runtimeExecutor.execute(() -> {
            try {
                if (stopRequested) return;
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                PyObject bootstrap = Python.getInstance().getModule("android_bootstrap");
                bootstrap.callAttr("start", ProjectStore.projectDir(this).getAbsolutePath(), PORT);
                for (int i = 0; i < 30 && !isHealthy(); i++) Thread.sleep(500);
                if (isHealthy()) updateNotification("Działa w tle • 127.0.0.1:" + PORT);
                else updateNotification("Serwer startuje — sprawdź aplikację");
            } catch (Throwable error) {
                updateNotification("Błąd uruchomienia — otwórz aplikację");
            } finally {
                starting.set(false);
            }
        });
    }

    private boolean isHealthy() {
        HttpURLConnection connection = null;
        try {
            URL url = new URL("http://127.0.0.1:" + PORT + "/api/health");
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(1200);
            connection.setReadTimeout(1200);
            connection.setRequestMethod("GET");
            int code = connection.getResponseCode();
            if (code != 200) return false;
            try (InputStream in = connection.getInputStream()) {
                byte[] bytes = new byte[512];
                int n = in.read(bytes);
                String body = n > 0 ? new String(bytes, 0, n, StandardCharsets.UTF_8) : "";
                return body.contains("ok") || body.contains("status");
            }
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private boolean stopRuntime() {
        try {
            if (Python.isStarted()) Python.getInstance().getModule("android_bootstrap").callAttr("stop");
            RUNTIME_STOPPED.set(true);
            return true;
        } catch (Throwable error) {
            RUNTIME_STOPPED.set(false);
            return false;
        }
    }

    @Override
    public void onDestroy() {
        if (watchdog != null) watchdog.shutdownNow();
        stopRequested = true;
        runtimeExecutor.execute(() -> {
            if (!RUNTIME_STOPPED.get()) stopRuntime();
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        });
        runtimeExecutor.shutdown();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
