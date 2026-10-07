"""Exercise the real ProjectStore filesystem installer on the JVM.

Android stubs supply only paths, streams and preferences; SQLite restore is not
mock-tested here. Runtime SQLite behavior is checked by test_runtime.py.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
"android/net/Uri.java": r'''package android.net;
public final class Uri {
  private final String value;
  private Uri(String value){this.value=value;}
  public static Uri parse(String value){return new Uri(value);}
  public String toString(){return value;}
}''',
"android/content/SharedPreferences.java": r'''package android.content;
import java.util.HashMap;
public final class SharedPreferences {
  private final HashMap<String,String> data=new HashMap<>();
  public String getString(String key,String fallback){return data.getOrDefault(key,fallback);}
  public Editor edit(){return new Editor();}
  public final class Editor {
    private String key,value;
    public Editor putString(String key,String value){this.key=key;this.value=value;return this;}
    public boolean commit(){data.put(key,value);return true;}
  }
}''',
"android/content/res/AssetManager.java": r'''package android.content.res;
import java.io.*;
public final class AssetManager {
  private final File root;
  public AssetManager(File root){this.root=root;}
  public InputStream open(String name)throws IOException{return new FileInputStream(new File(root,name));}
}''',
"android/content/ContentResolver.java": r'''package android.content;
import android.net.Uri;
import java.io.*;
public final class ContentResolver {
  public InputStream openInputStream(Uri uri)throws IOException{return new FileInputStream(uri.toString());}
}''',
"android/content/Context.java": r'''package android.content;
import java.io.File;
import android.content.res.AssetManager;
public final class Context {
  public static final int MODE_PRIVATE=0;
  private final File root,assets;
  private final SharedPreferences prefs=new SharedPreferences();
  public Context(File root,File assets){this.root=root;this.assets=assets;getFilesDir().mkdirs();getCacheDir().mkdirs();}
  public File getFilesDir(){return new File(root,"files");}
  public File getCacheDir(){return new File(root,"cache");}
  public AssetManager getAssets(){return new AssetManager(assets);}
  public ContentResolver getContentResolver(){return new ContentResolver();}
  public SharedPreferences getSharedPreferences(String name,int mode){return prefs;}
}''',
"android/database/Cursor.java": r'''package android.database;
public interface Cursor extends AutoCloseable {
  boolean moveToFirst();
  String getString(int i);
  int getColumnCount();
  void close();
}''',
"android/database/sqlite/SQLiteDatabase.java": r'''package android.database.sqlite;
import android.database.Cursor;
public final class SQLiteDatabase {
  public static final int OPEN_READONLY=1;
  public static SQLiteDatabase openDatabase(String path,Object factory,int flags){throw new UnsupportedOperationException();}
  public Cursor rawQuery(String sql,String[] args){throw new UnsupportedOperationException();}
  public void close(){}
}''',
"pl/drogowskazy/sora/ProjectStoreTest.java": r'''package pl.drogowskazy.sora;
import android.content.Context;
import android.net.Uri;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

public final class ProjectStoreTest {
  private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
  private static void write(File file,byte[] data)throws IOException{
    file.getParentFile().mkdirs();Files.write(file.toPath(),data);
  }
  private static File zip(File dir,String name,String app,boolean valid)throws IOException{
    File file=new File(dir,name);
    try(ZipOutputStream out=new ZipOutputStream(new FileOutputStream(file))){
      String[] paths=valid?new String[]{"app.py","templates/index.html","static/app.js","clean_core/__init__.py"}:new String[]{"missing.txt"};
      for(String path:paths){out.putNextEntry(new ZipEntry(path));out.write(app.getBytes(java.nio.charset.StandardCharsets.UTF_8));out.closeEntry();}
    }
    return file;
  }
  public static void main(String[] args)throws Exception{
    File dir=new File(args[0]);
    Context context=new Context(new File(dir,"app"),new File(args[1]));
    check(ProjectStore.needsBundledInstall(context),"Fresh install must prepare runtime");
    ProjectStore.installBundled(context);
    File current=ProjectStore.projectDir(context);
    check(ProjectStore.isInstalled(context),"Bundled install");
    check(!ProjectStore.needsBundledInstall(context),"No repeat installation");
    check(!new File(current,"data/drogowskazy.sqlite3").exists(),"Private data not embedded");
    byte[] database="synthetic-private-database".getBytes();
    byte[] wal="synthetic-uncheckpointed-wal".getBytes();
    write(new File(current,"data/drogowskazy.sqlite3"),database);
    write(new File(current,"data/drogowskazy.sqlite3-wal"),wal);
    write(new File(current,"data/notes/user.txt"),"private-note".getBytes());
    File manual=zip(dir,"manual.zip","manual-version",true);
    ProjectStore.importZip(context,Uri.parse(manual.toString()));
    check(Files.readString(new File(current,"app.py").toPath()).equals("manual-version"),"Manual version active");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Database preserved");
    check(Arrays.equals(wal,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-wal").toPath())),"WAL preserved");
    check(new File(current,"data/notes/user.txt").isFile(),"Other user files preserved");
    ProjectStore.installBundled(context);
    check(Files.readString(new File(current,"app.py").toPath()).equals("manual-version"),"Explicit manual update not overwritten");
    File invalid=zip(dir,"invalid.zip","broken",false);
    try{ProjectStore.importZip(context,Uri.parse(invalid.toString()));throw new AssertionError("Invalid ZIP accepted");}
    catch(IOException expected){}
    check(Files.readString(new File(current,"app.py").toPath()).equals("manual-version"),"Invalid import leaves program intact");
    File traversal=new File(dir,"traversal.zip");
    try(ZipOutputStream out=new ZipOutputStream(new FileOutputStream(traversal))){
      out.putNextEntry(new ZipEntry("../escape.txt"));out.write(1);out.closeEntry();
    }
    try{ProjectStore.importZip(context,Uri.parse(traversal.toString()));throw new AssertionError("Traversal ZIP accepted");}
    catch(IOException expected){}
    check(!new File(current.getParentFile(),"escape.txt").exists(),"Traversal blocked");
    context.getSharedPreferences("drogowskazy_bundle",0).edit().putString("installed_version","previous-apk").commit();
    check(ProjectStore.needsBundledInstall(context),"APK upgrade recognized");
    ProjectStore.installBundled(context);
    check(!Files.readString(new File(current,"app.py").toPath()).equals("manual-version"),"Upgrade activates bundled runtime");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Upgrade preserves database");
    File previous=new File(current.getParentFile(),"previous");
    check(current.renameTo(previous),"Simulate interruption after old installation was moved");
    ProjectStore.installBundled(context);
    check(ProjectStore.isInstalled(context),"Interrupted installation recovered");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Recovery preserves database");
    check(!previous.exists()&&!new File(current.getParentFile(),"staging").exists(),"Temporary files removed");
    System.out.println("PASS: fresh install, idempotency, manual update, database and WAL preservation, invalid ZIP rollback, traversal, APK upgrade, interruption recovery");
  }
}'''
}

with tempfile.TemporaryDirectory(prefix="sora-installer-test-") as tmp:
    base = Path(tmp)
    sources = []
    for name, text in SOURCES.items():
        path = base / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        sources.append(str(path))
    sources.append(str(ROOT / "app/src/main/java/pl/drogowskazy/sora/ProjectStore.java"))
    classes = base / "classes"
    classes.mkdir()
    subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(classes), *sources], check=True)
    subprocess.run(["java", "-cp", str(classes), "pl.drogowskazy.sora.ProjectStoreTest",
        str(base), str(ROOT / "app/src/main/assets")], check=True)
