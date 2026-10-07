"""Desktop adapter to the exact runtime asset used by the Android APK.
No HTTP server, browser, JavaScript, or second analysis implementation.
"""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import os
import sys
import zipfile


def runtime_asset():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'drogowskazy-runtime.zip'
    return Path(__file__).resolve().parents[1] / 'app/src/main/assets/drogowskazy-runtime.zip'


def runtime_identity(asset=None):
    asset = Path(asset or runtime_asset())
    with zipfile.ZipFile(asset) as archive:
        digest = hashlib.sha256()
        for name in sorted(archive.namelist()):
            if name == 'app.py' or name.startswith(('clean_core/', 'knowledge/', 'benchmark/')):
                digest.update(name.encode()); digest.update(b'\0')
                digest.update(archive.read(name)); digest.update(b'\0')
        return {'engine_sha256': digest.hexdigest(),
                'asset_sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
                'database_schema': 3}


class Engine:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.identity = runtime_identity()
        runtime = self.home / 'runtime' / self.identity['asset_sha256']
        runtime.mkdir(parents=True, exist_ok=True)
        # Assets are immutable and content-addressed. User data lives elsewhere.
        with zipfile.ZipFile(runtime_asset()) as archive:
            for info in archive.infolist():
                path = Path(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                    raise ValueError('Nieprawidłowa ścieżka w silniku')
                if info.is_dir():
                    continue
                target = runtime / path
                target.parent.mkdir(parents=True, exist_ok=True)
                content = archive.read(info)
                if not target.exists() or target.read_bytes() != content:
                    target.write_bytes(content)
        sys.path.insert(0, str(runtime))
        os.environ['DROGOWSKAZY_DB_PATH'] = str(self.home / 'data/drogowskazy.sqlite3')
        spec = importlib.util.spec_from_file_location('sora_shared_runtime', runtime / 'app.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.version = self.module.APP_VERSION
        self.identity['engine_version'] = self.version

    def request(self, path, payload=None):
        # Flask dispatch is reused in process: no socket is opened.
        with self.module.app.test_client() as client:
            response = client.get(path) if payload is None else client.post(path, json=payload)
            result = response.get_json()
            if response.status_code >= 400:
                raise ValueError((result or {}).get('wiadomosc') or (result or {}).get('szczegoly') or (result or {}).get('blad') or str(response.status_code))
            return result

    def import_file(self, path, relative_path=None):
        path = Path(path)
        if path.stat().st_size > self.module.MAX_INPUT_BYTES:
            raise ValueError('Plik przekracza limit 2 MB: ' + path.name)
        with self.module.app.test_client() as client:
            response = client.post('/api/baza/importuj', data={
                'file': (io.BytesIO(path.read_bytes()), path.name),
                'relative_path': relative_path or path.name,
            })
            result = response.get_json()
            if response.status_code >= 400:
                raise ValueError(result.get('wiadomosc') or result.get('blad'))
            return result

    def backup(self, destination):
        self.module.DOCUMENT_DATABASE.backup_to(destination)
        return self.identity.copy()

    def stop(self):
        # Stop taking new work and drain the current analysis before exit.
        self.module._IMPORT_QUEUE.join()
