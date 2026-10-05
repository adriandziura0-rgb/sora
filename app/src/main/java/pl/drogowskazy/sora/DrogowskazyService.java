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
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DrogowskazyService extends Service {
    static final String ACTION_STOP = "pl.drogowskazy.sora.STOP";
    static final int PORT = 5433;
    private static final String CHANNEL_ID = "drogowskazy_background";
    private static final int NOTIFICATION_ID = 4569;
    private final AtomicBoolean starting = new AtomicBoolean(false);
    private ScheduledExecutorService watchdog;
    private PowerManager.WakeLock wakeLock;

    public static void start(Context context) {
        Intent intent = new Intent(context, DrogowskazyService.class);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
    }

    public static void stop(Context context) {
        Intent intent = new Intent(context, DrogowskazyService.class).setAction(ACTION_STOP);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
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
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            startForegroundCompat(buildNotification("Zatrzymywanie…"));
            stopRuntime();
            stopSelf();
            return START_NOT_STICKY;
        }
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
        if (!ProjectStore.isInstalled(this)) {
            updateNotification("Wybierz ZIP programu w aplikacji");
            return;
        }
        if (isHealthy()) {
            updateNotification("Działa w tle • 127.0.0.1:" + PORT);
            return;
        }
        if (!starting.compareAndSet(false, true)) return;
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
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

    private void stopRuntime() {
        try {
            if (Python.isStarted()) Python.getInstance().getModule("android_bootstrap").callAttr("stop");
        } catch (Throwable ignored) {
        }
    }

    @Override
    public void onDestroy() {
        if (watchdog != null) watchdog.shutdownNow();
        stopRuntime();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
