package pl.drogowskazy.sora;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.net.Uri;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class ProjectStore {
    static final String BUNDLED_VERSION = "4.5.12-inapp-1";
    private static final String BUNDLE_PREFS = "drogowskazy_bundle";
    private static final long MAX_UNPACKED_BYTES = 700L * 1024L * 1024L;
    private static final int MAX_ENTRIES = 20_000;
    private static final long MAX_DATABASE_BYTES = 512L * 1024L * 1024L;

    private ProjectStore() {}

    static File projectDir(Context context) {
        return new File(new File(context.getFilesDir(), "drogowskazy"), "current");
    }

    static boolean isInstalled(Context context) {
        File root = projectDir(context);
        return new File(root, "app.py").isFile()
                && new File(root, "templates/index.html").isFile()
                && new File(root, "static/app.js").isFile();
    }

    static boolean needsBundledInstall(Context context) {
        return !isInstalled(context) || !BUNDLED_VERSION.equals(context
                .getSharedPreferences(BUNDLE_PREFS, Context.MODE_PRIVATE)
                .getString("installed_version", ""));
    }

    static synchronized String installBundled(Context context) throws Exception {
        if (!needsBundledInstall(context)) return "Program jest gotowy.";
        try (InputStream input = context.getAssets().open("drogowskazy-runtime.zip")) {
            installProject(context, input);
        }
        markBundleInstalled(context);
        return "Program jest gotowy. Dotychczasowa baza została zachowana.";
    }

    static synchronized String importZip(Context context, Uri uri) throws Exception {
        try (InputStream input = context.getContentResolver().openInputStream(uri)) {
            if (input == null) throw new IOException("Nie można otworzyć wskazanego ZIP-a");
            installProject(context, input);
        }
        // Ręczna aktualizacja pozostaje aktywna do następnej wersji APK.
        markBundleInstalled(context);
        return "Program zaktualizowany. Dotychczasowa baza została zachowana.";
    }

    private static void markBundleInstalled(Context context) throws IOException {
        if (!context.getSharedPreferences(BUNDLE_PREFS, Context.MODE_PRIVATE).edit()
                .putString("installed_version", BUNDLED_VERSION).commit()) {
            throw new IOException("Nie można zapisać wersji zainstalowanego programu.");
        }
    }

    private static void installProject(Context context, InputStream input) throws Exception {
        File base = new File(context.getFilesDir(), "drogowskazy");
        File current = new File(base, "current");
        File staging = new File(base, "staging");
        File previous = new File(base, "previous");

        if (!base.exists() && !base.mkdirs()) {
            throw new IOException("Nie można utworzyć katalogu aplikacji");
        }
        // Odzyskaj bazę także po przerwaniu aktywacji przez system.
        if (!current.exists() && previous.exists() && !previous.renameTo(current)) {
            throw new IOException("Nie można odzyskać poprzedniej instalacji.");
        }
        if (current.exists() && previous.exists()) {
            verify(current);
            deleteRecursively(previous);
        }
        deleteRecursively(staging);
        File normalized = new File(base, "normalized");
        deleteRecursively(normalized);
        if (!staging.mkdirs()) throw new IOException("Nie można utworzyć katalogu tymczasowego");
        boolean movedOld = false;
        boolean activated = false;
        try {
            unzip(input, staging);
            File root = locateProjectRoot(staging);
            if (root == null) throw new IOException("ZIP nie zawiera programu Drogowskazy.");
            verify(root);
            if (!root.equals(staging)) {
                if (!normalized.mkdirs()) throw new IOException("Nie można przygotować katalogu projektu");
                moveChildren(root, normalized);
                deleteRecursively(staging);
                if (!normalized.renameTo(staging)) throw new IOException("Nie można przygotować programu.");
            }

            // Zachowaj całe data, w tym WAL i pozostałe pliki użytkownika.
            // Wywołujący zatrzymuje serwer i worker przed podmianą.
            File userData = new File(current, "data");
            if (userData.isDirectory()) {
                File nextData = new File(staging, "data");
                deleteRecursively(nextData);
                copyDirectory(userData, nextData);
            }
            verify(staging);
            if (current.exists()) {
                if (!current.renameTo(previous)) throw new IOException("Nie można bezpiecznie zachować poprzedniego programu.");
                movedOld = true;
            }
            if (!staging.renameTo(current)) throw new IOException("Nie można uruchomić nowego programu.");
            activated = true;
            verify(current);
            deleteRecursively(previous);
        } catch (Exception activationError) {
            if (activated) deleteRecursively(current);
            if (movedOld && previous.exists() && !previous.renameTo(current)) {
                activationError.addSuppressed(new IOException("Poprzednia instalacja jest zachowana w katalogu previous."));
            }
            throw activationError;
        } finally {
            deleteRecursively(staging);
            deleteRecursively(normalized);
        }
    }

    static String restoreDatabase(Context context, Uri uri) throws Exception {
        File root = projectDir(context);
        if (!isInstalled(context)) throw new IOException("Poczekaj na przygotowanie programu.");

        File incoming = new File(context.getCacheDir(), "drogowskazy-restore.sqlite3");
        File target = new File(root, "data/drogowskazy.sqlite3");
        File backup = new File(root, "data/drogowskazy.sqlite3.before_restore");
        incoming.delete();

        try (InputStream in = context.getContentResolver().openInputStream(uri)) {
            if (in == null) throw new IOException("Nie można otworzyć wybranej kopii bazy.");
            copyStreamWithLimit(in, incoming, MAX_DATABASE_BYTES);
        }
        validateDatabase(incoming);

        if (target.isFile()) copyFile(target, backup);
        new File(target.getAbsolutePath() + "-wal").delete();
        new File(target.getAbsolutePath() + "-shm").delete();
        try {
            copyFile(incoming, target);
            validateDatabase(target);
            backup.delete();
        } catch (Exception error) {
            if (backup.isFile()) copyFile(backup, target);
            throw error;
        } finally {
            incoming.delete();
        }
        return "Baza SQLite przywrócona bez ponownego liczenia zakończonych rekordów.";
    }

    private static void validateDatabase(File file) throws IOException {
        if (!file.isFile() || file.length() < 100) throw new IOException("Wybrany plik nie jest prawidłową bazą SQLite.");
        SQLiteDatabase db = null;
        try {
            db = SQLiteDatabase.openDatabase(file.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
            try (Cursor integrity = db.rawQuery("PRAGMA integrity_check", null)) {
                if (!integrity.moveToFirst() || !"ok".equalsIgnoreCase(integrity.getString(0))) {
                    throw new IOException("Kontrola integralności SQLite nie zwróciła OK.");
                }
            }
            try (Cursor schema = db.rawQuery("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1", null)) {
                if (!schema.moveToFirst()) throw new IOException("To nie jest baza Drogowskazów: brak tabeli documents.");
            }
        } catch (IOException error) {
            throw error;
        } catch (Exception error) {
            throw new IOException("Nie można otworzyć kopii SQLite: " + error.getMessage(), error);
        } finally {
            if (db != null) db.close();
        }
    }

    private static void copyStreamWithLimit(InputStream in, File dst, long maxBytes) throws IOException {
        File parent = dst.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("Nie można utworzyć katalogu.");
        byte[] buffer = new byte[64 * 1024];
        long total = 0L;
        try (OutputStream out = new BufferedOutputStream(new FileOutputStream(dst))) {
            int n;
            while ((n = in.read(buffer)) > 0) {
                total += n;
                if (total > maxBytes) throw new IOException("Kopia bazy jest zbyt duża.");
                out.write(buffer, 0, n);
            }
        }
    }

    private static void verify(File root) throws IOException {
        List<String> missing = new ArrayList<>();
        String[] required = {"app.py", "templates/index.html", "static/app.js", "clean_core"};
        for (String relative : required) {
            if (!new File(root, relative).exists()) missing.add(relative);
        }
        if (!missing.isEmpty()) {
            throw new IOException("Niepełny projekt. Brak: " + String.join(", ", missing));
        }
    }

    private static File locateProjectRoot(File base) {
        if (new File(base, "app.py").isFile()) return base;
        File[] first = base.listFiles(File::isDirectory);
        if (first == null) return null;
        for (File dir : first) {
            if (new File(dir, "app.py").isFile()) return dir;
            File[] second = dir.listFiles(File::isDirectory);
            if (second != null) {
                for (File nested : second) {
                    if (new File(nested, "app.py").isFile()) return nested;
                }
            }
        }
        return null;
    }

    private static void unzip(InputStream raw, File target) throws IOException {
        String rootPath = target.getCanonicalPath() + File.separator;
        long total = 0L;
        int entries = 0;
        byte[] buffer = new byte[64 * 1024];
        try (ZipInputStream zis = new ZipInputStream(new BufferedInputStream(raw))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ENTRIES) throw new IOException("ZIP ma zbyt wiele plików");
                File out = new File(target, entry.getName());
                String canonical = out.getCanonicalPath();
                if (!canonical.startsWith(rootPath)) throw new IOException("Niebezpieczna ścieżka ZIP");
                if (entry.isDirectory()) {
                    if (!out.exists() && !out.mkdirs()) throw new IOException("Nie można utworzyć: " + out);
                } else {
                    File parent = out.getParentFile();
                    if (parent != null && !parent.exists() && !parent.mkdirs()) {
                        throw new IOException("Nie można utworzyć katalogu: " + parent);
                    }
                    try (OutputStream os = new BufferedOutputStream(new FileOutputStream(out))) {
                        int n;
                        while ((n = zis.read(buffer)) > 0) {
                            total += n;
                            if (total > MAX_UNPACKED_BYTES) throw new IOException("ZIP po rozpakowaniu jest zbyt duży");
                            os.write(buffer, 0, n);
                        }
                    }
                }
                zis.closeEntry();
            }
        }
    }

    private static void moveChildren(File from, File to) throws IOException {
        File[] files = from.listFiles();
        if (files == null) return;
        for (File child : files) {
            File dest = new File(to, child.getName());
            if (!child.renameTo(dest)) {
                if (child.isDirectory()) copyDirectory(child, dest); else copyFile(child, dest);
            }
        }
    }

    private static void copyDirectory(File src, File dst) throws IOException {
        if (src.isDirectory()) {
            if (!dst.exists() && !dst.mkdirs()) throw new IOException("Nie można utworzyć: " + dst);
            File[] files = src.listFiles();
            if (files != null) for (File file : files) copyDirectory(file, new File(dst, file.getName()));
        } else {
            copyFile(src, dst);
        }
    }

    private static void copyFile(File src, File dst) throws IOException {
        File parent = dst.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("Nie można utworzyć katalogu");
        byte[] buffer = new byte[64 * 1024];
        try (InputStream in = new BufferedInputStream(new FileInputStream(src));
             OutputStream out = new BufferedOutputStream(new FileOutputStream(dst))) {
            int n;
            while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
        }
    }

    private static void deleteRecursively(File file) {
        if (file == null || !file.exists()) return;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) for (File child : children) deleteRecursively(child);
        }
        file.delete();
    }
}
