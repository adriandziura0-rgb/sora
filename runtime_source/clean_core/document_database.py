"""Lokalna baza dokumentow i wynikow analizy.

Modul uzywa wyłącznie standardowego SQLite. Każdy dokument ma jeden rekord
identyfikowany skrótem SHA-256 z unormowanej treści. Pełny wynik analizy jest
kompresowany, dzięki czemu baza pozostaje praktyczna także na telefonie.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Iterator, Optional

from .text_cleaning import sanitize_document
from .document_kind import document_kind, is_article_document


SCHEMA_VERSION = 3

_HTML_EXTENSIONS = {".html", ".htm"}
_PLAIN_ARTICLE_EXTENSIONS = {".txt", ".md", ".markdown"}
_SCRAPER_SAVED_LINE_RE = re.compile(r"(?m)^\s*[✅✔]\s*\[?\d+[/\]]")


class StaleImportError(RuntimeError):
    """Wynik dotyczy treści, która została zastąpiona w czasie analizy."""



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_document_text(text: str) -> str:
    """Normalizacja techniczna zachowująca znaczenie i pozycje znaków."""
    return str(text or "").replace("\ufeff", "", 1).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def prepare_document_text(text: str, extension: str = "") -> str:
    """Zwraca treść, która faktycznie ma trafić do bazy i analizatora.

    HTML jest formatem źródłowym, a nie tekstem analitycznym. Usuwamy więc
    tagi, skrypty, konfiguracje odtwarzaczy i adresy techniczne *przed*
    obliczeniem SHA-256. Dzięki temu baza nie przechowuje dziesiątek tysięcy
    znaków szablonu strony i nie analizuje ich ponownie przy odczycie.
    """
    normalized = normalize_document_text(text)
    if str(extension or "").casefold() in _HTML_EXTENSIONS:
        normalized = str(sanitize_document(normalized).get("source_text") or "")
        return normalize_document_text(normalized).strip()
    # Dla zwykłych plików zachowujemy dokładną treść (łącznie z końcowym
    # znakiem nowej linii), aby istniejące SHA i pozycje znaków były stabilne.
    return normalize_document_text(normalized)


def is_probable_scraper_log(text: str) -> bool:
    """Bardzo konserwatywna bramka oczywistego logu technicznego.

    Pojedynczy stack trace lub zwykły plik ``.log`` nadal może zostać
    przeanalizowany. Odrzucamy dopiero charakterystyczne połączenie raportu
    scrapera: licznik znalezionych linków, wiele linii „Zapisano” i ślad
    Selenium/Pythona. To chroni bazę artykułów bez zgadywania gatunku tekstu.
    """
    value = str(text or "")
    saved_lines = len(_SCRAPER_SAVED_LINE_RE.findall(value))
    return bool(
        re.search(r"Znaleziono\s+\d+\s+link", value, re.I)
        and saved_lines >= 10
        and ("Stacktrace" in value or "Scripts\\python.exe" in value or "Błąd: Message" in value)
    )


def _normalized_source_parts(relative_path: str) -> tuple[str, str]:
    """Normalizuje katalog i rdzeń nazwy bez rozszerzenia.

    Eksportery Windows potrafią uciąć końcówkę długiej nazwy osobno dla HTML
    i TXT. Dlatego obok identycznych rdzeni dopuszczamy bardzo małą różnicę na
    samym końcu długiej nazwy.
    """
    value = str(relative_path or "").replace("\\", "/").replace("\u00a0", " ")
    parent, _, name = value.rpartition("/")
    stem = Path(name).stem
    parent = " ".join(parent.split()).strip().casefold()
    stem = " ".join(stem.split()).strip().casefold()
    return parent, stem


def _same_article_representation(
    existing_path: str,
    existing_extension: str,
    incoming_path: str,
    incoming_extension: str,
) -> bool:
    """Rozpoznaje parę HTML/TXT tego samego artykułu bez zgadywania tematu."""
    old_ext = str(existing_extension or "").casefold()
    new_ext = str(incoming_extension or "").casefold()
    if not (
        (old_ext in _HTML_EXTENSIONS and new_ext in _PLAIN_ARTICLE_EXTENSIONS)
        or (new_ext in _HTML_EXTENSIONS and old_ext in _PLAIN_ARTICLE_EXTENSIONS)
    ):
        return False
    old_parent, old_stem = _normalized_source_parts(existing_path)
    new_parent, new_stem = _normalized_source_parts(incoming_path)
    if old_parent != new_parent or not old_stem or not new_stem:
        return False
    if old_stem == new_stem:
        return True
    shorter, longer = sorted((old_stem, new_stem), key=len)
    # Różnica 1–3 znaków na końcu jest typowym skutkiem limitu długości nazwy.
    return len(shorter) >= 80 and len(longer) - len(shorter) <= 3 and longer.startswith(shorter)


def content_sha256(text: str) -> str:
    return hashlib.sha256(normalize_document_text(text).encode("utf-8")).hexdigest()


def _json_bytes(value: Dict[str, Any]) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return gzip.compress(raw, compresslevel=6, mtime=0)


def _json_from_bytes(value: bytes) -> Dict[str, Any]:
    decoded = json.loads(gzip.decompress(value).decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Zapisany wynik analizy nie jest obiektem JSON.")
    return decoded


class DocumentDatabase:
    """Mały, bezpieczny magazyn SQLite otwierający połączenie na operację."""

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_sha256 TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    encoding TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL,
                    text_chars INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing', 'done', 'error')),
                    attempts INTEGER NOT NULL DEFAULT 1,
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    analyzed_at TEXT,
                    app_version TEXT NOT NULL,
                    analysis_run_id TEXT,
                    summary_json TEXT,
                    analysis_gzip BLOB,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
                CREATE INDEX IF NOT EXISTS idx_documents_added_at ON documents(added_at DESC);

                CREATE TABLE IF NOT EXISTS import_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER,
                    content_sha256 TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK(outcome IN ('imported', 'duplicate', 'retried', 'error')),
                    created_at TEXT NOT NULL,
                    message TEXT,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_import_events_outcome ON import_events(outcome);

                CREATE TABLE IF NOT EXISTS manual_benchmark_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    relation_id TEXT NOT NULL,
                    overall_label TEXT NOT NULL CHECK(overall_label IN ('correct','partial','false')),
                    speaker_label TEXT NOT NULL DEFAULT 'unknown' CHECK(speaker_label IN ('correct','partial','false','unknown')),
                    claim_label TEXT NOT NULL DEFAULT 'unknown' CHECK(claim_label IN ('correct','partial','false','unknown')),
                    target_label TEXT NOT NULL DEFAULT 'unknown' CHECK(target_label IN ('correct','partial','false','unknown')),
                    source_label TEXT NOT NULL DEFAULT 'unknown' CHECK(source_label IN ('correct','partial','false','unknown')),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(document_id, relation_id),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_manual_benchmark_overall ON manual_benchmark_labels(overall_label);

                CREATE TABLE IF NOT EXISTS gold_document_annotations (
                    document_id INTEGER PRIMARY KEY,
                    expected_json TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 1 CHECK(completed IN (0,1)),
                    app_version TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_gold_document_completed ON gold_document_annotations(completed);
                """
            )
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            # Rekordy ``processing`` są trwałą kolejką pracy. V4.5.10 nie
            # zamienia ich przy starcie w błąd: worker aplikacji wznowi je po
            # restarcie procesu/aplikacji. Dzięki temu analiza folderu nie ginie
            # po przejściu telefonu do tła ani po automatycznym restarcie.

    @staticmethod
    def _public_document(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        data = dict(row)
        return {
            "id": int(data["id"]),
            "content_sha256": str(data["content_sha256"]),
            "filename": str(data["filename"]),
            "relative_path": str(data["relative_path"]),
            "extension": str(data["extension"]),
            "encoding": str(data["encoding"]),
            "source_bytes": int(data["source_bytes"]),
            "text_chars": int(data["text_chars"]),
            "status": str(data["status"]),
            "attempts": int(data["attempts"]),
            "added_at": str(data["added_at"]),
            "updated_at": str(data["updated_at"]),
            "analyzed_at": data.get("analyzed_at"),
            "app_version": str(data["app_version"]),
            "analysis_run_id": data.get("analysis_run_id"),
            "error": data.get("error"),
            "document_kind": document_kind(data),
            "is_article": is_article_document(data),
        }

    def begin_import(
        self,
        *,
        text: str,
        filename: str,
        relative_path: str,
        extension: str,
        encoding: str,
        source_bytes: int,
        app_version: str,
    ) -> Dict[str, Any]:
        normalized = prepare_document_text(text, extension)
        if not normalized.strip():
            raise ValueError("Dokument nie zawiera tekstu po oczyszczeniu.")
        if is_probable_scraper_log(normalized):
            raise ValueError("Wykryto log techniczny scrapera zamiast treści dokumentu.")
        digest = content_sha256(normalized)
        now = utc_now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM documents WHERE content_sha256 = ?", (digest,)).fetchone()
            if existing is not None and existing["status"] in {"done", "processing"}:
                db.execute(
                    """INSERT INTO import_events
                       (document_id, content_sha256, filename, relative_path, outcome, created_at, message)
                       VALUES (?, ?, ?, ?, 'duplicate', ?, ?)""",
                    (existing["id"], digest, filename, relative_path, now, f"Istniejący status: {existing['status']}"),
                )
                return {"action": "duplicate", "document": self._public_document(existing), "text": normalized}

            # Ten sam artykuł bywa dostarczany równocześnie jako surowy HTML i
            # wyczyszczony TXT. SHA nie jest wtedy identyczne, choć to ta sama
            # publikacja. Preferujemy TXT/Markdown; HTML nie tworzy drugiego
            # dokumentu. Długi rdzeń różniący się wyłącznie końcówką obsługuje
            # nazwy ucięte przez system plików.
            representation_match = None
            candidates = db.execute(
                "SELECT * FROM documents WHERE extension IN ('.html', '.htm', '.txt', '.md', '.markdown') ORDER BY id",
            ).fetchall()
            for candidate in candidates:
                if _same_article_representation(
                    str(candidate["relative_path"]),
                    str(candidate["extension"]),
                    relative_path,
                    extension,
                ):
                    representation_match = candidate
                    break

            if representation_match is not None:
                old_ext = str(representation_match["extension"] or "").casefold()
                new_ext = str(extension or "").casefold()
                if old_ext in _PLAIN_ARTICLE_EXTENSIONS or new_ext in _HTML_EXTENSIONS:
                    db.execute(
                        """INSERT INTO import_events
                           (document_id, content_sha256, filename, relative_path, outcome, created_at, message)
                           VALUES (?, ?, ?, ?, 'duplicate', ?, ?)""",
                        (
                            representation_match["id"],
                            representation_match["content_sha256"],
                            filename,
                            relative_path,
                            now,
                            "Druga reprezentacja tego samego artykułu; zachowano wariant tekstowy.",
                        ),
                    )
                    return {
                        "action": "duplicate",
                        "duplicate_reason": "same_article_representation",
                        "document": self._public_document(representation_match),
                        "text": normalized,
                    }

                # HTML zapisano wcześniej, a teraz nadszedł lepszy TXT/MD.
                # Zastępujemy rekord w miejscu, aby zachować stabilne ID.
                db.execute(
                    """UPDATE documents
                       SET content_sha256 = ?, filename = ?, relative_path = ?, extension = ?,
                           encoding = ?, source_bytes = ?, text_chars = ?, text_content = ?,
                           status = 'processing', attempts = attempts + 1, updated_at = ?,
                           app_version = ?, analysis_run_id = NULL, summary_json = NULL,
                           analysis_gzip = NULL, analyzed_at = NULL, error = NULL
                       WHERE id = ?""",
                    (
                        digest,
                        filename,
                        relative_path,
                        extension,
                        encoding,
                        int(source_bytes),
                        len(normalized),
                        normalized,
                        now,
                        app_version,
                        representation_match["id"],
                    ),
                )
                row = db.execute("SELECT * FROM documents WHERE id = ?", (representation_match["id"],)).fetchone()
                return {
                    "action": "replacement",
                    "duplicate_reason": "preferred_text_representation",
                    "document": self._public_document(row),
                    "text": normalized,
                }

            if existing is not None:
                db.execute(
                    """UPDATE documents
                       SET filename = ?, relative_path = ?, extension = ?, encoding = ?, source_bytes = ?,
                           text_chars = ?, text_content = ?, status = 'processing', attempts = attempts + 1,
                           updated_at = ?, app_version = ?, analysis_run_id = NULL,
                           summary_json = NULL, analysis_gzip = NULL, error = NULL
                       WHERE id = ?""",
                    (
                        filename,
                        relative_path,
                        extension,
                        encoding,
                        int(source_bytes),
                        len(normalized),
                        normalized,
                        now,
                        app_version,
                        existing["id"],
                    ),
                )
                row = db.execute("SELECT * FROM documents WHERE id = ?", (existing["id"],)).fetchone()
                return {"action": "retry", "document": self._public_document(row), "text": normalized}

            cursor = db.execute(
                """INSERT INTO documents
                   (content_sha256, filename, relative_path, extension, encoding, source_bytes,
                    text_chars, text_content, status, added_at, updated_at, app_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?)""",
                (
                    digest,
                    filename,
                    relative_path,
                    extension,
                    encoding,
                    int(source_bytes),
                    len(normalized),
                    normalized,
                    now,
                    now,
                    app_version,
                ),
            )
            row = db.execute("SELECT * FROM documents WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return {"action": "new", "document": self._public_document(row), "text": normalized}

    def _guard_active_import(
        self,
        db: sqlite3.Connection,
        document_id: int,
        expected_content_sha256: str | None,
    ) -> sqlite3.Row:
        row = db.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
        if row is None:
            raise KeyError(f"Brak dokumentu {document_id}")
        expected = str(expected_content_sha256 or "").strip()
        if expected and str(row["content_sha256"] or "") != expected:
            raise StaleImportError(
                f"Dokument {document_id} został zastąpiony nowszą treścią podczas analizy."
            )
        if expected and str(row["status"] or "") != "processing":
            raise StaleImportError(
                f"Dokument {document_id} nie jest już aktywnym importem (status={row['status']})."
            )
        return row

    def mark_success(
        self,
        document_id: int,
        result: Dict[str, Any],
        *,
        retried: bool = False,
        expected_content_sha256: str | None = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        summary = {
            "analysis_run_id": result.get("analysis_run_id"),
            "analysis_generated_at": result.get("analysis_generated_at"),
            "podsumowanie": result.get("podsumowanie") or {},
        }
        packed = _json_bytes(result)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._guard_active_import(db, document_id, expected_content_sha256)
            params = [
                now,
                now,
                str(result.get("analysis_run_id") or ""),
                json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                packed,
                int(document_id),
            ]
            where = "id = ?"
            if expected_content_sha256:
                where += " AND content_sha256 = ? AND status = 'processing'"
                params.append(str(expected_content_sha256))
            cursor = db.execute(
                f"""UPDATE documents
                    SET status = 'done', updated_at = ?, analyzed_at = ?, analysis_run_id = ?,
                        summary_json = ?, analysis_gzip = ?, error = NULL
                    WHERE {where}""",
                tuple(params),
            )
            if cursor.rowcount != 1:
                raise StaleImportError(f"Dokument {document_id} zmienił się przed zapisem wyniku.")
            row = db.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
            db.execute(
                """INSERT INTO import_events
                   (document_id, content_sha256, filename, relative_path, outcome, created_at, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(document_id),
                    row["content_sha256"],
                    row["filename"],
                    row["relative_path"],
                    "retried" if retried else "imported",
                    now,
                    "Analiza zakończona i zapisana.",
                ),
            )
            return self._public_document(row)

    def mark_error(
        self,
        document_id: int,
        message: str,
        *,
        retried: bool = False,
        expected_content_sha256: str | None = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        clean_message = str(message or "Nieznany błąd analizy")[:2000]
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._guard_active_import(db, document_id, expected_content_sha256)
            params = [now, clean_message, int(document_id)]
            where = "id = ?"
            if expected_content_sha256:
                where += " AND content_sha256 = ? AND status = 'processing'"
                params.append(str(expected_content_sha256))
            cursor = db.execute(
                f"UPDATE documents SET status = 'error', updated_at = ?, error = ? WHERE {where}",
                tuple(params),
            )
            if cursor.rowcount != 1:
                raise StaleImportError(f"Dokument {document_id} zmienił się przed zapisem błędu.")
            row = db.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
            db.execute(
                """INSERT INTO import_events
                   (document_id, content_sha256, filename, relative_path, outcome, created_at, message)
                   VALUES (?, ?, ?, ?, 'error', ?, ?)""",
                (int(document_id), row["content_sha256"], row["filename"], row["relative_path"], now, clean_message),
            )
            return self._public_document(row)

    def stats(self) -> Dict[str, int]:
        with self._connect() as db:
            counts = {str(row["status"]): int(row["count"]) for row in db.execute(
                "SELECT status, COUNT(*) AS count FROM documents GROUP BY status"
            )}
            duplicates = db.execute(
                "SELECT COUNT(*) AS count FROM import_events WHERE outcome = 'duplicate'"
            ).fetchone()["count"]
            events = db.execute("SELECT COUNT(*) AS count FROM import_events").fetchone()["count"]
            rows = db.execute("SELECT filename, relative_path, extension, status FROM documents").fetchall()
        articles = support_files = done_articles = done_support_files = 0
        for row in rows:
            if is_article_document(dict(row)):
                articles += 1
                if str(row["status"] or "") == "done":
                    done_articles += 1
            else:
                support_files += 1
                if str(row["status"] or "") == "done":
                    done_support_files += 1
        return {
            "total": sum(counts.values()),
            "done": counts.get("done", 0),
            "processing": counts.get("processing", 0),
            "error": counts.get("error", 0),
            "duplicates": int(duplicates),
            "import_events": int(events),
            "articles": int(articles),
            "support_files": int(support_files),
            "done_articles": int(done_articles),
            "done_support_files": int(done_support_files),
        }

    @staticmethod
    def _root_folder(relative_path: str) -> str:
        path = str(relative_path or "").replace("\\", "/").strip("/")
        if not path:
            return "(bez folderu)"
        parts = [part for part in path.split("/") if part]
        return parts[0] if len(parts) > 1 else "(bez folderu)"

    @staticmethod
    def _like_escape(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def list_document_folders(self) -> list[Dict[str, Any]]:
        """Lekki indeks folderów do nawigacji w bazie dokumentów."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT filename, relative_path, extension, status, source_bytes, text_chars FROM documents ORDER BY id DESC"
            ).fetchall()
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            folder = self._root_folder(row["relative_path"])
            item = grouped.setdefault(folder, {
                "id": folder,
                "label": folder,
                "documents": 0,
                "articles": 0,
                "support_files": 0,
                "done": 0,
                "processing": 0,
                "error": 0,
                "source_bytes": 0,
                "text_chars": 0,
            })
            item["documents"] += 1
            if is_article_document(dict(row)):
                item["articles"] += 1
            else:
                item["support_files"] += 1
            status = str(row["status"] or "")
            if status in {"done", "processing", "error"}:
                item[status] += 1
            item["source_bytes"] += int(row["source_bytes"] or 0)
            item["text_chars"] += int(row["text_chars"] or 0)
        return sorted(grouped.values(), key=lambda item: (-int(item["articles"]), str(item["label"]).casefold()))

    def list_documents(self, *, limit: int = 50, offset: int = 0, folder: str = "") -> list[Dict[str, Any]]:
        safe_limit = max(1, min(200, int(limit)))
        safe_offset = max(0, int(offset))
        safe_folder = str(folder or "").strip()
        query = """SELECT id, content_sha256, filename, relative_path, extension, encoding,
                          source_bytes, text_chars, status, attempts, added_at, updated_at,
                          analyzed_at, app_version, analysis_run_id, error
                   FROM documents"""
        params: list[Any] = []
        if safe_folder:
            if safe_folder == "(bez folderu)":
                query += " WHERE instr(replace(relative_path, '\\', '/'), '/') = 0 OR relative_path = ''"
            else:
                escaped = self._like_escape(safe_folder)
                query += " WHERE replace(relative_path, '\\', '/') LIKE ? ESCAPE '\\'"
                params.append(f"{escaped}/%")
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([safe_limit, safe_offset])
        with self._connect() as db:
            rows = db.execute(query, tuple(params)).fetchall()
        return [self._public_document(row) for row in rows]

    def get_document(self, document_id: int, *, include_result: bool = False, include_text: bool = False) -> Optional[Dict[str, Any]]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
        if row is None:
            return None
        payload: Dict[str, Any] = {"document": self._public_document(row)}
        if include_text:
            payload["text"] = str(row["text_content"])
        if include_result:
            payload["result"] = _json_from_bytes(row["analysis_gzip"]) if row["analysis_gzip"] else None
        return payload

    def processing_snapshots(self) -> list[Dict[str, Any]]:
        """Zwraca trwałą kolejkę dokumentów oczekujących na analizę.

        ``processing`` jest celowo utrzymywane między restartami procesu.
        Worker V4.5.10 pobiera te rekordy ponownie po starcie i kończy analizę.
        """
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, content_sha256, filename, relative_path, text_content, attempts
                   FROM documents WHERE status = 'processing' ORDER BY id ASC"""
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "content_sha256": str(row["content_sha256"]),
                "filename": str(row["filename"]),
                "relative_path": str(row["relative_path"]),
                "text_content": str(row["text_content"]),
                "attempts": int(row["attempts"] or 1),
            }
            for row in rows
        ]

    def reanalysis_snapshots(self) -> list[Dict[str, Any]]:
        """Zwraca stabilne snapshoty zakończonych dokumentów do ponownej analizy."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, content_sha256, filename, relative_path, text_content
                   FROM documents WHERE status = 'done' ORDER BY id ASC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_analysis_if_unchanged(
        self, document_id: int, result: Dict[str, Any], *, expected_content_sha256: str, app_version: str
    ) -> Dict[str, Any]:
        """Podmienia tylko analizę, nigdy treść dokumentu; blokuje wyścig z importem."""
        now = utc_now()
        summary = {
            "analysis_run_id": result.get("analysis_run_id"),
            "analysis_generated_at": result.get("analysis_generated_at"),
            "podsumowanie": result.get("podsumowanie") or {},
        }
        packed = _json_bytes(result)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """UPDATE documents
                   SET updated_at = ?, analyzed_at = ?, analysis_run_id = ?, summary_json = ?,
                       analysis_gzip = ?, app_version = ?, error = NULL
                   WHERE id = ? AND content_sha256 = ? AND status = 'done'""",
                (now, now, str(result.get("analysis_run_id") or ""),
                 json.dumps(summary, ensure_ascii=False, separators=(",", ":")), packed,
                 str(app_version), int(document_id), str(expected_content_sha256)),
            )
            if cursor.rowcount != 1:
                raise StaleImportError(f"Dokument {document_id} zmienił się przed zapisem ponownej analizy.")
            row = db.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
            db.execute(
                """INSERT INTO import_events
                   (document_id, content_sha256, filename, relative_path, outcome, created_at, message)
                   VALUES (?, ?, ?, ?, 'retried', ?, ?)""",
                (int(document_id), row["content_sha256"], row["filename"], row["relative_path"], now,
                 f"Ponowna analiza aktualnym silnikiem: {app_version}"),
            )
            return self._public_document(row)

    def iter_completed_results(self, *, include_text: bool = False, article_only: bool = False) -> Iterator[tuple[Dict[str, Any], Dict[str, Any]]]:
        """Iteruje po zapisanych wynikach bez ładowania całej bazy do pamięci.

        ``article_only=True`` pozostawia w SQLite pliki pomocnicze, ale nie
        przepuszcza ich do raportów/porównań, które mają opisywać artykuły.

        Każdy element to ``(publiczny_dokument, wynik_analizy)``. Rekordy bez
        blobu analizy są pomijane. Metoda jest przeznaczona dla zbiorczego
        raportu z całej bazy i dzięki strumieniowej dekompresji skaluje się do
        setek dokumentów bez jednoczesnego rozwijania wszystkich JSON-ów.
        """
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM documents
                   WHERE status = 'done' AND analysis_gzip IS NOT NULL
                   ORDER BY id ASC"""
            )
            for row in rows:
                try:
                    result = _json_from_bytes(row["analysis_gzip"])
                except Exception:
                    # Uszkodzony pojedynczy blob nie może zablokować zebrania
                    # pozostałych poprawnych analiz. Informację o pominięciu
                    # raportuje warstwa agregująca.
                    continue
                public_document = self._public_document(row)
                if article_only and not bool(public_document.get("is_article")):
                    continue
                if include_text:
                    public_document["_text_content"] = str(row["text_content"] or "")
                yield public_document, result


    def save_benchmark_label(
        self, *, document_id: int, relation_id: str, overall_label: str,
        speaker_label: str = "unknown", claim_label: str = "unknown",
        target_label: str = "unknown", source_label: str = "unknown", note: str = ""
    ) -> Dict[str, Any]:
        allowed_overall = {"correct", "partial", "false"}
        allowed_field = {"correct", "partial", "false", "unknown"}
        overall = str(overall_label or "").strip().casefold()
        fields = [str(x or "unknown").strip().casefold() for x in (speaker_label, claim_label, target_label, source_label)]
        if overall not in allowed_overall or any(x not in allowed_field for x in fields):
            raise ValueError("Nieprawidłowa etykieta benchmarku.")
        relation = str(relation_id or "").strip()
        if not relation:
            raise ValueError("relation_id jest wymagane.")
        now = utc_now()
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM documents WHERE id=? AND status='done'", (int(document_id),)).fetchone()
            if not exists:
                raise LookupError("Nie znaleziono zakończonego dokumentu benchmarku.")
            db.execute(
                """INSERT INTO manual_benchmark_labels
                   (document_id, relation_id, overall_label, speaker_label, claim_label, target_label, source_label, note, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(document_id, relation_id) DO UPDATE SET
                     overall_label=excluded.overall_label, speaker_label=excluded.speaker_label,
                     claim_label=excluded.claim_label, target_label=excluded.target_label, source_label=excluded.source_label,
                     note=excluded.note, updated_at=excluded.updated_at""",
                (int(document_id), relation, overall, fields[0], fields[1], fields[2], fields[3], str(note or "")[:2000], now, now),
            )
            row = db.execute("SELECT * FROM manual_benchmark_labels WHERE document_id=? AND relation_id=?", (int(document_id), relation)).fetchone()
        return dict(row)

    def list_benchmark_labels(self) -> list[Dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM manual_benchmark_labels ORDER BY updated_at DESC, id DESC").fetchall()
        return [dict(row) for row in rows]

    def benchmark_label_keys(self) -> set[tuple[int, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT document_id, relation_id FROM manual_benchmark_labels").fetchall()
        return {(int(row["document_id"]), str(row["relation_id"])) for row in rows}

    def save_gold_annotation(
        self, *, document_id: int, expected_relations: list[Dict[str, Any]],
        note: str = "", completed: bool = True, app_version: str = ""
    ) -> Dict[str, Any]:
        if not isinstance(expected_relations, list):
            raise ValueError("expected_relations musi być listą.")
        cleaned = []
        for idx, item in enumerate(expected_relations, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Relacja GOLD #{idx} nie jest obiektem.")
            row = {
                "speaker": str(item.get("speaker") or "").strip(),
                "claim": str(item.get("claim") or "").strip(),
                "target": str(item.get("target") or "").strip(),
                "source": str(item.get("source") or "").strip(),
            }
            if not row["speaker"] and not row["claim"]:
                continue
            cleaned.append(row)
        now = utc_now()
        payload = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM documents WHERE id=? AND status='done'", (int(document_id),)).fetchone()
            if not exists:
                raise LookupError("Nie znaleziono zakończonego dokumentu GOLD.")
            db.execute(
                """INSERT INTO gold_document_annotations
                   (document_id, expected_json, note, completed, app_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(document_id) DO UPDATE SET
                     expected_json=excluded.expected_json, note=excluded.note, completed=excluded.completed,
                     app_version=excluded.app_version, updated_at=excluded.updated_at""",
                (int(document_id), payload, str(note or "")[:4000], 1 if completed else 0, str(app_version or ""), now, now),
            )
            row = db.execute("SELECT * FROM gold_document_annotations WHERE document_id=?", (int(document_id),)).fetchone()
        out = dict(row)
        out["expected_relations"] = json.loads(out.pop("expected_json"))
        out["completed"] = bool(out.get("completed"))
        return out

    def list_gold_annotations(self, *, completed_only: bool = False) -> list[Dict[str, Any]]:
        query = "SELECT * FROM gold_document_annotations" + (" WHERE completed=1" if completed_only else "") + " ORDER BY updated_at DESC, document_id ASC"
        with self._connect() as db:
            rows = db.execute(query).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["expected_relations"] = json.loads(item.pop("expected_json"))
            except Exception:
                item["expected_relations"] = []
                item.pop("expected_json", None)
            item["completed"] = bool(item.get("completed"))
            out.append(item)
        return out

    def gold_annotated_document_ids(self, *, completed_only: bool = True) -> set[int]:
        query = "SELECT document_id FROM gold_document_annotations" + (" WHERE completed=1" if completed_only else "")
        with self._connect() as db:
            rows = db.execute(query).fetchall()
        return {int(row["document_id"]) for row in rows}

    def backup_to(self, destination: Path | str) -> Path:
        target = Path(destination).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        source_db = sqlite3.connect(str(self.path), timeout=30.0)
        target_db = sqlite3.connect(str(target), timeout=30.0)
        try:
            source_db.backup(target_db)
            target_db.commit()
        finally:
            target_db.close()
            source_db.close()
        return target
