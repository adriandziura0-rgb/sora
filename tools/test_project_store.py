"""Exercise the real ProjectStore filesystem installer on the JVM.

Android stubs exercise installer, restore rollback metadata, WAL/SHM snapshots
and interrupted restore recovery. Real SQLite integrity is checked by test_runtime.py.
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
"android/content/pm/PackageInfo.java": r'''package android.content.pm;
public final class PackageInfo {
  public String versionName;
}''',
"android/content/pm/PackageManager.java": r'''package android.content.pm;
public final class PackageManager {
  private final String version;
  public PackageManager(String version){this.version=version;}
  public PackageInfo getPackageInfo(String name,int flags)throws NameNotFoundException{
    if(!"pl.drogowskazy.sora".equals(name))throw new NameNotFoundException();
    PackageInfo info=new PackageInfo();info.versionName=version;return info;
  }
  public static final class NameNotFoundException extends Exception{}
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
import android.content.pm.PackageManager;
public final class Context {
  public static final int MODE_PRIVATE=0;
  private final File root,assets;
  private String apkVersion="1.2.8";
  private final SharedPreferences prefs=new SharedPreferences();
  public Context(File root,File assets){this.root=root;this.assets=assets;getFilesDir().mkdirs();getCacheDir().mkdirs();}
  public File getFilesDir(){return new File(root,"files");}
  public File getCacheDir(){return new File(root,"cache");}
  public AssetManager getAssets(){return new AssetManager(assets);}
  public ContentResolver getContentResolver(){return new ContentResolver();}
  public String getPackageName(){return "pl.drogowskazy.sora";}
  public PackageManager getPackageManager(){return new PackageManager(apkVersion);}
  public void setPackageVersion(String version){apkVersion=version;}
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
import java.io.*;
public final class SQLiteDatabase {
  public static final int OPEN_READONLY=1;
  public static SQLiteDatabase openDatabase(String path,Object factory,int flags) {
    try(FileInputStream in=new FileInputStream(path)){
      byte[] header=new byte[16];
      if(in.read(header)!=16 || !new String(header,java.nio.charset.StandardCharsets.US_ASCII).equals("SQLite format 3\0"))
        throw new IllegalArgumentException("Not SQLite");
    }catch(IOException e){throw new IllegalStateException(e);}
    return new SQLiteDatabase();
  }
  public Cursor rawQuery(String sql,String[] args) {
    String value=sql.startsWith("PRAGMA integrity")?"ok":"1";
    return new Cursor(){
      public boolean moveToFirst(){return !sql.contains("LIMIT 0");}
      public String getString(int i){return value;}
      public int getColumnCount(){return 7;}
      public void close(){}
    };
  }
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
    // Symulacja faktycznej aktualizacji APK, bez kasowania SharedPreferences
    // ani prywatnych danych użytkownika. Stara stała wersji nie przechodzi tego testu.
    context.setPackageVersion("1.2.11");
    check(ProjectStore.needsBundledInstall(context),"New APK version must reinstall bundled runtime");
    ProjectStore.installBundled(context);
    check(!Files.readString(new File(current,"app.py").toPath()).equals("manual-version"),"Upgrade activates bundled runtime");
    check(!ProjectStore.needsBundledInstall(context),"Updated APK does not reinstall repeatedly");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Upgrade preserves database");
    check(Arrays.equals(wal,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-wal").toPath())),"Upgrade preserves WAL");
    check(new File(current,"data/notes/user.txt").isFile(),"Upgrade preserves user notes");
    // Istniejące instalacje 1.2.4–1.2.8 zachowały ten sam identyfikator,
    // mimo że zawierały już nową paczkę APK. Teraz muszą ją rozpakować.
    context.getSharedPreferences("drogowskazy_bundle",0).edit().putString("installed_version","4.5.12-inapp-2").commit();
    check(ProjectStore.needsBundledInstall(context),"Legacy bundled version must not suppress new APK assets");
    ProjectStore.installBundled(context);
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Legacy migration keeps private database");
    check(Arrays.equals(wal,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-wal").toPath())),"Legacy migration keeps WAL");
    File previous=new File(current.getParentFile(),"previous");
    check(current.renameTo(previous),"Simulate interruption after old installation was moved");
    ProjectStore.installBundled(context);
    check(ProjectStore.isInstalled(context),"Interrupted installation recovered");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Recovery preserves database");
    check(!previous.exists()&&!new File(current.getParentFile(),"staging").exists(),"Temporary files removed");
    // Przywracanie: zły plik nie może naruszyć ani DB, ani WAL.
    File badBackup=new File(dir,"badbackup.sqlite3");
    write(badBackup,"invalid".getBytes());
    try{ProjectStore.restoreDatabase(context,Uri.parse(badBackup.toString()));throw new AssertionError("Bad SQLite accepted");}
    catch(IOException expected){}
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Invalid restore preserved DB");
    check(Arrays.equals(wal,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-wal").toPath())),"Invalid restore preserved WAL");

    byte[] shm="synthetic-shared-memory".getBytes();
    write(new File(current,"data/drogowskazy.sqlite3-shm"),shm);
    byte[] good=new byte[256];
    byte[] header="SQLite format 3\0".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    System.arraycopy(header,0,good,0,header.length);
    File validBackup=new File(dir,"validbackup.sqlite3");
    write(validBackup,good);
    ProjectStore.restoreDatabase(context,Uri.parse(validBackup.toString()));
    check(Arrays.equals(good,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Restored SQLite active");
    File[] archived=new File(current,"data").listFiles(f->f.isDirectory()&&f.getName().startsWith("backup-before-restore-"));
    check(archived!=null&&archived.length==1,"Persistent restore backup created");
    File archivedData=archived[0];
    check(Arrays.equals(database,Files.readAllBytes(new File(archivedData,"drogowskazy.sqlite3").toPath())),"Original DB retained");
    check(Arrays.equals(wal,Files.readAllBytes(new File(archivedData,"drogowskazy.sqlite3-wal").toPath())),"Original WAL retained");
    check(Arrays.equals(shm,Files.readAllBytes(new File(archivedData,"drogowskazy.sqlite3-shm").toPath())),"Original SHM retained");
    // Symulacja przerwania przywracania po uszkodzeniu aktywnego pliku.
    write(new File(current,"data/drogowskazy.sqlite3"),"interrupted".getBytes());
    write(new File(current,"data/.restore-pending"),archivedData.getName().getBytes(java.nio.charset.StandardCharsets.UTF_8));
    check(ProjectStore.hasInterruptedRestore(context),"Interrupted restore marker detected");
    ProjectStore.recoverInterruptedRestore(context);
    check(!ProjectStore.hasInterruptedRestore(context),"Restore marker removed after recovery");
    check(Arrays.equals(database,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3").toPath())),"Recovered old DB after interruption");
    check(Arrays.equals(wal,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-wal").toPath())),"Recovered old WAL after interruption");
    check(Arrays.equals(shm,Files.readAllBytes(new File(current,"data/drogowskazy.sqlite3-shm").toPath())),"Recovered old SHM after interruption");
    System.out.println("PASS: installer, upgrades, SQLite invalid restore, durable DB/WAL/SHM snapshot, interrupted restore recovery");
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
