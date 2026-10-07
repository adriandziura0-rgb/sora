package pl.drogowskazy.sora;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.print.PrintManager;
import android.provider.DocumentsContract;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Panel lokalnego programu z systemowym wyborem plików, folderów i zapisu. */
final class NativePanel extends WebView {
    private static final int REQUEST_FILES = 4101;
    private static final int REQUEST_FOLDER = 4102;
    private static final int REQUEST_SAVE = 4103;
    private static final int MAX_TEXT_BYTES = 2 * 1024 * 1024;
    private final Activity activity;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final AtomicBoolean exporting = new AtomicBoolean(false);
    private final Set<String> allowedTrees = new HashSet<>();
    private ValueCallback<Uri[]> fileCallback;
    private String folderRequest;
    private File exportFile;
    private volatile boolean closed;
    private String adapterScript = "";

    NativePanel(Activity activity) {
        super(activity);
        this.activity = activity;
        if ((activity.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
        getSettings().setJavaScriptEnabled(true);
        getSettings().setDomStorageEnabled(true);
        getSettings().setAllowFileAccess(false);
        getSettings().setAllowContentAccess(true);
        getSettings().setSupportMultipleWindows(false);
        getSettings().setTextZoom(100);
        addJavascriptInterface(new Bridge(), "DrogowskazyAndroid");
        try (InputStream in = activity.getAssets().open("native-panel.js")) {
            adapterScript = new String(readLimited(in, 64 * 1024), StandardCharsets.UTF_8);
        } catch (IOException error) {
            message("Nie udało się przygotować wyboru folderów: " + error.getMessage());
        }
        setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView view, String url) {
                if (isLocal(url) && !closed) evaluateJavascript(adapterScript, null);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleNavigation(request.getUrl().toString());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleNavigation(url);
            }
        });
        setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                                       FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,
                        params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                startInDownloads(intent);
                try {
                    activity.startActivityForResult(intent, REQUEST_FILES);
                } catch (Exception error) {
                    fileCallback.onReceiveValue(null);
                    fileCallback = null;
                    message("Nie udało się otworzyć wyboru plików.");
                }
                return true;
            }
            @Override public boolean onJsAlert(WebView view, String url, String text, JsResult result) {
                new AlertDialog.Builder(activity).setMessage(text)
                        .setPositiveButton("OK", (dialog, which) -> result.confirm())
                        .setOnCancelListener(dialog -> result.cancel()).show();
                return true;
            }
            @Override public boolean onJsConfirm(WebView view, String url, String text, JsResult result) {
                new AlertDialog.Builder(activity).setMessage(text)
                        .setPositiveButton("OK", (dialog, which) -> result.confirm())
                        .setNegativeButton("Anuluj", (dialog, which) -> result.cancel())
                        .setOnCancelListener(dialog -> result.cancel()).show();
                return true;
            }
        });
        setDownloadListener((url, userAgent, disposition, mime, length) ->
                download(url, URLUtil.guessFileName(url, disposition, mime), mime));
    }

    private static boolean isLocal(String value) {
        Uri uri = Uri.parse(value);
        return "http".equals(uri.getScheme()) && "127.0.0.1".equals(uri.getHost())
                && uri.getPort() == DrogowskazyService.PORT;
    }

    private boolean handleNavigation(String url) {
        if (isLocal(url)) {
            if ("/api/baza/pobierz".equals(Uri.parse(url).getPath())) {
                download(url, "drogowskazy_baza.sqlite3", "application/vnd.sqlite3");
                return true;
            }
            return false;
        }
        Uri uri = Uri.parse(url);
        if ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())
                || "mailto".equals(uri.getScheme())) {
            try { activity.startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
            catch (Exception error) { message("Nie można otworzyć tego odnośnika."); }
        }
        return true;
    }

    boolean handleActivityResult(int request, int result, Intent data) {
        if (request == REQUEST_FILES) {
            if (fileCallback != null) {
                ArrayList<Uri> files = new ArrayList<>();
                if (result == Activity.RESULT_OK && data != null) {
                    ClipData clips = data.getClipData();
                    if (clips != null) {
                        for (int i = 0; i < clips.getItemCount(); i++) files.add(clips.getItemAt(i).getUri());
                    } else if (data.getData() != null) files.add(data.getData());
                }
                fileCallback.onReceiveValue(files.isEmpty() ? null : files.toArray(new Uri[0]));
                fileCallback = null;
            }
            return true;
        }
        if (request == REQUEST_FOLDER) {
            String id = folderRequest;
            folderRequest = null;
            JSONObject folder = null;
            if (result == Activity.RESULT_OK && data != null && data.getData() != null) {
                try {
                    Uri tree = data.getData();
                    int flags = data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION;
                    // Nie każdy dostawca udostępnia trwałe uprawnienie. Do bieżącego
                    // importu wystarcza odczyt przyznany przez systemowy picker.
                    if ((data.getFlags() & Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION) != 0 && flags != 0) {
                        try { activity.getContentResolver().takePersistableUriPermission(tree, flags); }
                        catch (SecurityException ignored) { }
                    }
                    synchronized (allowedTrees) { allowedTrees.add(treeKey(tree)); }
                    Uri document = DocumentsContract.buildDocumentUriUsingTree(tree,
                            DocumentsContract.getTreeDocumentId(tree));
                    String name = "Folder";
                    try (Cursor c = activity.getContentResolver().query(document,
                            new String[]{DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null)) {
                        if (c != null && c.moveToFirst()) name = c.getString(0);
                    }
                    folder = new JSONObject().put("uri", document.toString()).put("name", name);
                } catch (Exception error) {
                    try { folder = new JSONObject().put("error", "Nie można odczytać wybranego folderu: " + error.getMessage()); }
                    catch (Exception ignored) { }
                }
            }
            if (id != null) evaluateJavascript("window.__drogowskazyFolderResult(" + JSONObject.quote(id)
                    + "," + (folder == null ? "null" : folder.toString()) + ");", null);
            return true;
        }
        if (request == REQUEST_SAVE) {
            File ready = exportFile;
            exportFile = null;
            if (result == Activity.RESULT_OK && data != null && data.getData() != null && ready != null) {
                Uri destination = data.getData();
                io.execute(() -> {
                    try (InputStream in = new FileInputStream(ready);
                         OutputStream out = activity.getContentResolver().openOutputStream(destination, "wt")) {
                        if (out == null) throw new IOException("Nie można otworzyć pliku zapisu.");
                        copyLimited(in, out, 512L * 1024 * 1024);
                        message("Plik zapisany.");
                    } catch (Exception error) { message("Nie udało się zapisać: " + error.getMessage()); }
                    finally { ready.delete(); exporting.set(false); }
                });
            } else {
                if (ready != null) ready.delete();
                exporting.set(false);
            }
            return true;
        }
        return false;
    }

    private static String treeKey(Uri uri) {
        return uri.getAuthority() + "/" + DocumentsContract.getTreeDocumentId(uri);
    }

    static void startInDownloads(Intent intent) {
        if (Build.VERSION.SDK_INT >= 26) {
            // Dostawca Downloads bywa oparty tylko na indeksie MediaStore.
            // Pliki skopiowane lub rozpakowane muszą być widoczne również
            // zanim Android dopisze je do tego indeksu.
            intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI,
                    DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:Download"));
        }
    }

    private Uri permittedTreeDocument(String value) {
        Uri uri = Uri.parse(value);
        if (!"content".equals(uri.getScheme()) || !DocumentsContract.isTreeUri(uri)) {
            throw new SecurityException("Nieprawidłowy folder.");
        }
        synchronized (allowedTrees) {
            if (!allowedTrees.contains(treeKey(uri))) throw new SecurityException("Najpierw wybierz folder.");
        }
        return uri;
    }

    private final class Bridge {
        @JavascriptInterface public void openSettings() {
            activity.runOnUiThread(() -> ((MainActivity) activity).showSettings());
        }

        @JavascriptInterface public void restoreDatabaseBackup() {
            activity.runOnUiThread(() -> {
                if (closed) return;
                ((MainActivity) activity).showSettings();
                ((MainActivity) activity).chooseDatabaseBackup();
            });
        }

        @JavascriptInterface public void copyText(String text) {
            activity.runOnUiThread(() -> {
                ClipboardManager clipboard = (ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("Raport Drogowskazy", text));
            });
        }

        @JavascriptInterface public void pickFolder(String requestId) {
            activity.runOnUiThread(() -> {
                if (closed) return;
                if (folderRequest != null) {
                    evaluateJavascript("window.__drogowskazyFolderResult(" + JSONObject.quote(requestId) + ",null);", null);
                    return;
                }
                folderRequest = requestId;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
                startInDownloads(intent);
                try { activity.startActivityForResult(intent, REQUEST_FOLDER); }
                catch (Exception error) {
                    folderRequest = null;
                    evaluateJavascript("window.__drogowskazyFolderResult(" + JSONObject.quote(requestId)
                            + ",{error:'Nie udało się otworzyć wyboru folderu. Użyj przycisku Dodaj pliki do bazy.'});", null);
                }
            });
        }

        @JavascriptInterface public String listChildren(String value) {
            try {
                Uri parent = permittedTreeDocument(value);
                Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(parent,
                        DocumentsContract.getDocumentId(parent));
                JSONArray rows = new JSONArray();
                String[] columns = {DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                        DocumentsContract.Document.COLUMN_MIME_TYPE, DocumentsContract.Document.COLUMN_SIZE};
                try (Cursor c = activity.getContentResolver().query(children, columns, null, null, null)) {
                    if (c == null) throw new IOException("Nie można odczytać katalogu.");
                    while (c.moveToNext()) {
                        if (rows.length() >= 20000) throw new IOException("Folder zawiera zbyt wiele plików.");
                        rows.put(new JSONObject().put("uri", DocumentsContract.buildDocumentUriUsingTree(parent,
                                c.getString(0)).toString()).put("name", c.getString(1))
                                .put("kind", DocumentsContract.Document.MIME_TYPE_DIR.equals(c.getString(2))
                                        ? "directory" : "file").put("size", c.isNull(3) ? 0L : c.getLong(3)));
                    }
                }
                return new JSONObject().put("entries", rows).toString();
            } catch (Exception error) {
                return errorJson(error);
            }
        }

        @JavascriptInterface public String readFile(String value) {
            try (InputStream in = activity.getContentResolver().openInputStream(permittedTreeDocument(value))) {
                if (in == null) throw new IOException("Nie można odczytać pliku.");
                return new JSONObject().put("base64", Base64.encodeToString(readLimited(in, MAX_TEXT_BYTES), Base64.NO_WRAP)).toString();
            } catch (Exception error) { return errorJson(error); }
        }

        @JavascriptInterface public void saveText(String filename, String text, String mime) {
            if (closed || !exporting.compareAndSet(false, true)) { message("Poczekaj na poprzedni zapis."); return; }
            io.execute(() -> {
                File file = null;
                try {
                    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
                    if (bytes.length > 32 * 1024 * 1024) throw new IOException("Wynik jest zbyt duży do zapisu.");
                    file = File.createTempFile("drogowskazy-export-", ".tmp", activity.getCacheDir());
                    try (OutputStream out = new FileOutputStream(file)) { out.write(bytes); }
                    offerSave(file, filename, mime);
                } catch (Exception error) {
                    if (file != null) file.delete();
                    exporting.set(false);
                    message("Nie udało się przygotować zapisu: " + error.getMessage());
                }
            });
        }

        @JavascriptInterface public void downloadDatabase() {
            download("http://127.0.0.1:" + DrogowskazyService.PORT + "/api/baza/pobierz",
                    "drogowskazy_baza.sqlite3", "application/vnd.sqlite3");
        }

        @JavascriptInterface public void printPanel() {
            activity.runOnUiThread(() -> {
                if (closed) return;
                PrintManager manager = (PrintManager) activity.getSystemService(Activity.PRINT_SERVICE);
                if (manager != null) manager.print("Drogowskazy", createPrintDocumentAdapter("Drogowskazy"), null);
            });
        }
    }

    private static String errorJson(Exception error) {
        try { return new JSONObject().put("error", error.getMessage()).toString(); }
        catch (Exception ignored) { return "{\"error\":\"Błąd odczytu\"}"; }
    }

    private void download(String url, String filename, String mime) {
        if (!isLocal(url) || closed) { message("Nieprawidłowy adres pobierania."); return; }
        if (!exporting.compareAndSet(false, true)) { message("Poczekaj na poprzedni zapis."); return; }
        io.execute(() -> {
            File file = null;
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setInstanceFollowRedirects(false);
                c.setConnectTimeout(5000);
                c.setReadTimeout(60000);
                if (c.getResponseCode() != 200) throw new IOException("Program nie udostępnił pliku.");
                file = File.createTempFile("drogowskazy-download-", ".tmp", activity.getCacheDir());
                try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(file)) {
                    copyLimited(in, out, 512L * 1024 * 1024);
                }
                String disposition = c.getHeaderField("Content-Disposition");
                String type = c.getContentType();
                offerSave(file, disposition == null ? filename : URLUtil.guessFileName(url, disposition, type),
                        type == null ? mime : type);
            } catch (Exception error) {
                if (file != null) file.delete();
                exporting.set(false);
                message("Nie udało się pobrać: " + error.getMessage());
            } finally { if (c != null) c.disconnect(); }
        });
    }

    private void offerSave(File file, String name, String mime) {
        activity.runOnUiThread(() -> {
            if (closed || activity.isFinishing() || activity.isDestroyed()) {
                file.delete(); exporting.set(false); return;
            }
            exportFile = file;
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            String type = mime == null ? "application/octet-stream" : mime.split(";", 2)[0];
            intent.setType(type.isEmpty() ? "application/octet-stream" : type);
            String cleanName = name == null ? "Drogowskazy.txt" : name.replaceAll("[\\\\/\\r\\n]", "_");
            intent.putExtra(Intent.EXTRA_TITLE, cleanName);
            startInDownloads(intent);
            try { activity.startActivityForResult(intent, REQUEST_SAVE); }
            catch (Exception error) {
                file.delete(); exportFile = null; exporting.set(false);
                message("Nie udało się otworzyć wyboru miejsca zapisu.");
            }
        });
    }

    private static byte[] readLimited(InputStream in, int max) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        copyLimited(in, out, max);
        return out.toByteArray();
    }

    private static void copyLimited(InputStream in, OutputStream out, long max) throws IOException {
        byte[] buffer = new byte[64 * 1024];
        long total = 0;
        int n;
        while ((n = in.read(buffer)) != -1) {
            total += n;
            if (total > max) throw new IOException("Plik przekracza dopuszczalny rozmiar.");
            out.write(buffer, 0, n);
        }
    }

    private void message(String text) {
        activity.runOnUiThread(() -> { if (!closed) Toast.makeText(activity, text, Toast.LENGTH_LONG).show(); });
    }

    void close() {
        closed = true;
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        fileCallback = null;
        if (exportFile != null) exportFile.delete();
        io.shutdownNow();
        removeJavascriptInterface("DrogowskazyAndroid");
        stopLoading();
        destroy();
    }
}
