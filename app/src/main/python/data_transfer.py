"""Versioned PHONE/PC transfer outside the unchanged analysis CORE.
Callers must suspend database writers for import; all writes commit together.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
import gzip
import io

FORMAT = 'drogowskazy-sora-transfer'
VERSION = 1
SCHEMA = 3
MAX_BYTES = 512 * 1024 * 1024
TABLES = ('documents', 'import_events', 'manual_benchmark_labels', 'gold_document_annotations')


def runtime_identity(root):
    root = Path(root)
    names = ['app.py']
    for folder in ('clean_core', 'knowledge', 'benchmark'):
        names.extend(p.relative_to(root).as_posix() for p in (root / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(name.encode()); digest.update(b'\0'); digest.update((root / name).read_bytes()); digest.update(b'\0')
    version = None
    for node in ast.parse((root / 'clean_core/version.py').read_text('utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'APP_VERSION' for n in node.targets):
            version = ast.literal_eval(node.value)
    if not isinstance(version, str):raise ValueError('Brak wersji silnika.')
    return {'engine_sha256': digest.hexdigest(), 'engine_version': version, 'database_schema': SCHEMA}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):digest.update(block)
    return digest.hexdigest()


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):raise ValueError('Nieprawidłowy czas modyfikacji w bazie.')


def connect(path, readonly=False):
    path = Path(path).resolve()
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) if readonly else sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def validate(db, identity, expected=None):
    if db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA:raise ValueError('Niezgodny schemat bazy TRANSFER.')
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Baza TRANSFER jest uszkodzona lub ma niespójne powiązania.')
    for table in TABLES:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            raise ValueError('Brak wymaganej tabeli: ' + table)
        if expected is not None and [tuple(r) for r in db.execute(f'PRAGMA table_info("{table}")')] != [tuple(r) for r in expected.execute(f'PRAGMA table_info("{table}")')]:
            raise ValueError('Niezgodna struktura tabeli: ' + table)
    for row in db.execute('SELECT * FROM documents'):
        if row['app_version'] != identity['engine_version']:raise ValueError('Dokument używa innej wersji silnika.')
        if hashlib.sha256(row['text_content'].encode('utf-8')).hexdigest() != row['content_sha256']:
            raise ValueError('Nieprawidłowy identyfikator treści dokumentu.')
        stamp(row['added_at']); stamp(row['updated_at'])
        if row['analyzed_at']:stamp(row['analyzed_at'])
        for key in ('summary_json',):
            if row[key] is not None and not isinstance(json.loads(row[key]), dict):raise ValueError('Nieprawidłowe podsumowanie dokumentu.')
        if row['status'] == 'done':
            if not row['analysis_gzip']:raise ValueError('Dokument gotowy nie ma analizy.')
            with gzip.GzipFile(fileobj=io.BytesIO(row['analysis_gzip'])) as stream:
                raw = stream.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024 or not isinstance(json.loads(raw), dict):raise ValueError('Nieprawidłowa analiza dokumentu.')
    for row in db.execute('SELECT * FROM gold_document_annotations'):
        if row['app_version'] not in ('', identity['engine_version']):raise ValueError('Ocena GOLD używa innego silnika.')
        value = json.loads(row['expected_json'])
        if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):raise ValueError('Nieprawidłowe relacje GOLD.')
    for table in TABLES[1:]:
        for row in db.execute(f'SELECT * FROM "{table}"'):
            stamp(row['created_at'])
            if table != 'import_events':stamp(row['updated_at'])


def export_zip(database, destination, identity, origin):
    destination = Path(destination).resolve(); database = Path(database).resolve()
    if destination == database:raise ValueError('ZIP musi być osobnym plikiem.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        snapshot = Path(tmp) / 'core.sqlite3'
        source = connect(database, True); target = connect(snapshot)
        try:source.backup(target)
        finally:source.close(); target.close()
        checked = connect(snapshot, True)
        try:validate(checked, identity)
        finally:checked.close()
        if snapshot.stat().st_size > MAX_BYTES:raise ValueError('Baza przekracza limit 512 MB pakietu TRANSFER.')
        manifest = {'format': FORMAT, 'transfer_version': VERSION, 'schema_version': SCHEMA,
                    'package_id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                    'origin': origin, 'engine_version': identity['engine_version'], 'engine_sha256': identity['engine_sha256'],
                    'database_file': 'core.sqlite3', 'database_sha256': file_hash(snapshot)}
        ready = Path(tmp) / 'transfer.zip'
        with zipfile.ZipFile(ready, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.write(snapshot, 'core.sqlite3')
        os.replace(ready, destination)
    return manifest


def merge_zip(database, package, identity, storage):
    database, package, storage = Path(database).resolve(), Path(package).resolve(), Path(storage).resolve()
    if package == database:raise ValueError('Wybierz ZIP TRANSFER, nie aktywną bazę.')
    if not database.is_file():raise ValueError('Najpierw uruchom Sorę i utwórz lokalną bazę.')
    storage.mkdir(parents=True, exist_ok=True)
    result = {k: 0 for k in ('documents_added', 'documents_updated', 'documents_unchanged', 'annotations_updated', 'annotations_unchanged', 'events_added', 'conflicts')}
    with tempfile.TemporaryDirectory(dir=storage) as tmp:
        snapshot = Path(tmp) / 'core.sqlite3'
        with zipfile.ZipFile(package) as archive:
            entries = archive.infolist()
            if len(entries) != 2 or {i.filename for i in entries} != {'manifest.json', 'core.sqlite3'}:
                raise ValueError('ZIP TRANSFER musi zawierać tylko manifest.json i core.sqlite3.')
            if archive.getinfo('manifest.json').file_size > 65536 or archive.getinfo('core.sqlite3').file_size > MAX_BYTES:
                raise ValueError('Pakiet TRANSFER przekracza dopuszczalny rozmiar.')
            manifest = json.loads(archive.read('manifest.json'))
            if not isinstance(manifest, dict):raise ValueError('Nieprawidłowy manifest TRANSFER.')
            if manifest.get('format') != FORMAT or manifest.get('transfer_version') != VERSION or manifest.get('schema_version') != SCHEMA:
                raise ValueError('Nieobsługiwana wersja pakietu lub schematu TRANSFER.')
            if manifest.get('database_file') != 'core.sqlite3':raise ValueError('Nieprawidłowa nazwa bazy w manifeście.')
            for key in ('engine_version', 'engine_sha256'):
                if manifest.get(key) != identity[key]:raise ValueError('PHONE i PC mają różne silniki. Import anulowany.')
            uuid.UUID(manifest['package_id']); stamp(manifest['created_at'])
            with archive.open('core.sqlite3') as source, snapshot.open('wb') as out:
                shutil.copyfileobj(source, out, length=1024 * 1024)
        if file_hash(snapshot) != manifest.get('database_sha256'):
            raise ValueError('Suma kontrolna bazy TRANSFER jest niezgodna.')
        incoming = connect(snapshot, True); target = connect(database)
        try:
            validate(incoming, identity, target)
            target.execute('BEGIN IMMEDIATE')
            # Lock writers while taking a consistent pre-import snapshot.
            backup = storage / ('przed_transferem_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
            reader = connect(database, True); saved = connect(backup)
            try:reader.backup(saved)
            finally:reader.close(); saved.close()
            archived = storage / ('pakiet_' + str(uuid.UUID(manifest['package_id'])) + '_' + manifest['database_sha256'][:16] + '.zip')
            if not archived.exists():shutil.copyfile(package, archived)
            mapping = {}
            for item in incoming.execute('SELECT * FROM documents ORDER BY id'):
                row = dict(item); old_id = row.pop('id')
                existing = target.execute('SELECT * FROM documents WHERE content_sha256=?', (row['content_sha256'],)).fetchone()
                if existing is None:
                    keys = list(row)
                    cursor = target.execute('INSERT INTO documents ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')', [row[k] for k in keys])
                    mapping[old_id] = cursor.lastrowid; result['documents_added'] += 1
                else:
                    mapping[old_id] = existing['id']
                    if stamp(row['updated_at']) > stamp(existing['updated_at']) and not (existing['status'] == 'done' and row['status'] != 'done'):
                        keys = [k for k in row if k != 'added_at']
                        target.execute('UPDATE documents SET '+','.join(k+'=?' for k in keys)+' WHERE id=?', [row[k] for k in keys]+[existing['id']]); result['documents_updated'] += 1
                    else:
                        result['documents_unchanged'] += 1
                        if stamp(row['updated_at']) == stamp(existing['updated_at']) and any(row[k] != existing[k] for k in row if k != 'added_at'):result['conflicts'] += 1
            for table in ('manual_benchmark_labels', 'gold_document_annotations'):
                for item in incoming.execute(f'SELECT * FROM "{table}"'):
                    row = dict(item); row.pop('id', None); row['document_id'] = mapping[row['document_id']]
                    lookup = ['document_id'] + (['relation_id'] if table == 'manual_benchmark_labels' else [])
                    where = ' AND '.join(k+'=?' for k in lookup)
                    existing = target.execute(f'SELECT * FROM "{table}" WHERE '+where, [row[k] for k in lookup]).fetchone()
                    keys = list(row)
                    if existing is None:
                        target.execute(f'INSERT INTO "{table}" ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')', [row[k] for k in keys]); result['annotations_updated'] += 1
                    elif stamp(row['updated_at']) > stamp(existing['updated_at']):
                        keys = [k for k in row if k not in lookup and k != 'created_at']
                        target.execute(f'UPDATE "{table}" SET '+','.join(k+'=?' for k in keys)+' WHERE '+where, [row[k] for k in keys]+[row[k] for k in lookup]); result['annotations_updated'] += 1
                    else:
                        result['annotations_unchanged'] += 1
                        if stamp(row['updated_at']) == stamp(existing['updated_at']) and any(row[k] != existing[k] for k in row if k != 'created_at'):result['conflicts'] += 1
            for item in incoming.execute('SELECT * FROM import_events'):
                row = dict(item); row.pop('id')
                if row['document_id'] is not None:row['document_id'] = mapping[row['document_id']]
                keys = list(row)
                if not target.execute('SELECT 1 FROM import_events WHERE '+' AND '.join(k+' IS ?' for k in keys)+' LIMIT 1', [row[k] for k in keys]).fetchone():
                    target.execute('INSERT INTO import_events ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')', [row[k] for k in keys]); result['events_added'] += 1
            if target.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Scalanie naruszyłoby powiązania danych.')
            target.commit()
            result.update(backup=str(backup), archived_package=str(archived), package_id=manifest['package_id'])
        except Exception:
            target.rollback(); raise
        finally:incoming.close(); target.close()
    return result
