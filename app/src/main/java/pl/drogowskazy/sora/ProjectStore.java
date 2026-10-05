package pl.drogowskazy.sora;

import android.content.Context;
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
    private static final long MAX_UNPACKED_BYTES = 700L * 1024L * 1024L;
    private static final int MAX_ENTRIES = 20_000;

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

    static String importZip(Context context, Uri uri) throws Exception {
        File base = new File(context.getFilesDir(), "drogowskazy");
        File current = new File(base, "current");
        File staging = new File(base, "staging");
        File previous = new File(base, "previous");
        File preservedDb = new File(context.getCacheDir(), "drogowskazy-preserved.sqlite3");

        if (!base.exists() && !base.mkdirs()) {
            throw new IOException("Nie można utworzyć katalogu aplikacji");
        }
        deleteRecursively(staging);
        deleteRecursively(previous);
        if (!staging.mkdirs()) {
            throw new IOException("Nie można utworzyć katalogu tymczasowego");
        }

        File oldDb = new File(current, "data/drogowskazy.sqlite3");
        boolean hadOldDb = oldDb.isFile();
        if (hadOldDb) {
            copyFile(oldDb, preservedDb);
        } else if (preservedDb.exists()) {
            preservedDb.delete();
        }

        try (InputStream raw = context.getContentResolver().openInputStream(uri)) {
            if (raw == null) throw new IOException("Nie można otworzyć wskazanego ZIP-a");
            unzip(raw, staging);
        }

        File root = locateProjectRoot(staging);
        if (root == null) {
            throw new IOException("ZIP nie zawiera projektu Drogowskazy (brak app.py/templates/static)");
        }
        if (!root.equals(staging)) {
            File normalized = new File(base, "normalized");
            deleteRecursively(normalized);
            if (!normalized.mkdirs()) throw new IOException("Nie można przygotować katalogu projektu");
            moveChildren(root, normalized);
            deleteRecursively(staging);
            if (!normalized.renameTo(staging)) {
                copyDirectory(normalized, staging);
                deleteRecursively(normalized);
            }
        }

        if (current.exists() && !current.renameTo(previous)) {
            copyDirectory(current, previous);
            deleteRecursively(current);
        }
        if (!staging.renameTo(current)) {
            copyDirectory(staging, current);
            deleteRecursively(staging);
        }

        try {
            if (hadOldDb && preservedDb.isFile()) {
                File newDb = new File(current, "data/drogowskazy.sqlite3");
                File parent = newDb.getParentFile();
                if (parent != null && !parent.exists() && !parent.mkdirs()) {
                    throw new IOException("Nie można utworzyć katalogu data");
                }
                copyFile(preservedDb, newDb);
            }
            verify(current);
            deleteRecursively(previous);
            preservedDb.delete();
        } catch (Exception activationError) {
            deleteRecursively(current);
            if (previous.exists() && !previous.renameTo(current)) {
                copyDirectory(previous, current);
            }
            throw activationError;
        }

        return "Projekt zaimportowany: " + current.getAbsolutePath();
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
