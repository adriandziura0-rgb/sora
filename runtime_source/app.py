from __future__ import annotations

from pathlib import Path
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import os
import queue
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, request, send_file

from clean_core.version import APP_VERSION, STAGE
from clean_core.api_pl import analiza_po_polsku, sugestie_po_polsku
from clean_core.classifier import analyze_text, suggest_text
from clean_core.reports import generuj_pakiet_eksportu
from clean_core.workflow_modes import lista_trybow_pracy
from clean_core.text_cleaning import decode_text_bytes, repair_polish_mojibake
from clean_core.document_database import DocumentDatabase, StaleImportError, prepare_document_text
from clean_core.database_aggregate import build_database_aggregate
from clean_core.database_overview import build_selected_database_overview
from clean_core.topic_report_cache import cached_topics, cached_comparison, cached_selected_overview, cached_shared_content
from clean_core.shared_content import compare_shared_content
from clean_core.quote_database import selected_quote_database
from clean_core.editorial_compare import list_comparison_groups, build_group_comparison, build_multi_group_comparison, MAX_COMPARE_GROUPS
from clean_core.topic_matcher import discover_same_story_topics, build_same_story_comparison
from clean_core.manual_benchmark import build_benchmark_sample, summarize_benchmark
from clean_core.effectiveness_gold import build_gold_document_sample, summarize_effectiveness_gold

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_INPUT_BYTES + 512 * 1024
DEFAULT_PORT = int(os.environ.get("DROGOWSKAZY_PORT", "5433"))
SUPPORTED_DATABASE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".html", ".htm"}


# Jeden jawny kontrakt HTTP dla frontendu i testów runtime.
# Aplikacja nie używa WebSocket; komunikacja odbywa się wyłącznie przez HTTP/JSON.
RUNTIME_CONTRACT = {
    "health": "/api/health",
    "modes": "/api/tryby",
    "analyze": "/api/analizuj",
    "suggest": "/api/sugestie",
    "report": "/api/raport",
    "upload": "/api/wczytaj_plik",
    "database_import": "/api/baza/importuj",
    "database_status": "/api/baza/status",
    "database_documents": "/api/baza/dokumenty",
    "database_aggregate": "/api/baza/zbiorczy_wynik",
    "database_reanalyze": "/api/baza/przelicz_wszystkie",
    "database_compare_groups": "/api/baza/porownanie/grupy",
    "database_compare": "/api/baza/porownanie",
    "database_topics": "/api/baza/tematy",
    "database_topic_compare": "/api/baza/temat/porownanie",
    "database_benchmark_sample": "/api/baza/benchmark/proba",
    "database_benchmark_label": "/api/baza/benchmark/ocena",
    "database_benchmark_result": "/api/baza/benchmark/wynik",
    "database_gold_sample": "/api/baza/gold/proba",
    "database_gold_annotation": "/api/baza/gold/dokument",
    "database_gold_result": "/api/baza/gold/wynik",
    "database_download": "/api/baza/pobierz",
}

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# Multipart dodaje nagłówki do rozmiaru pliku. Limit samej treści nadal wynosi
# dokładnie 2 MiB i jest sprawdzany jawnie w każdym endpointcie wejściowym.
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

DATABASE_PATH = Path(os.environ.get("DROGOWSKAZY_DB_PATH") or (ROOT / "data" / "drogowskazy.sqlite3"))
DOCUMENT_DATABASE = DocumentDatabase(DATABASE_PATH)

# Ostatnie przebiegi są przechowywane wyłącznie w pamięci procesu. Dzięki temu
# raport JSON i wydruk PDF mogą użyć dokładnie tego samego obiektu analizy,
# zamiast uruchamiać drugi, potencjalnie różny przebieg.
_ANALYSIS_RUNS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_ANALYSIS_RUNS = 4
_ANALYSIS_RUNS_LOCK = threading.RLock()
# Jeden aktywny klasyfikator naraz: kolejka tła i ręczne analizy nie wchodzą sobie w drogę.
_ANALYSIS_ENGINE_LOCK = threading.RLock()


def _input_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _new_analysis_run(text: str) -> dict:
    with _ANALYSIS_ENGINE_LOCK:
        result = analiza_po_polsku(analyze_text(text))
    run_id = "run_" + uuid.uuid4().hex[:16]
    result["analysis_run_id"] = run_id
    result["analysis_input_sha256"] = _input_sha256(text)
    result["analysis_generated_at"] = datetime.now(timezone.utc).isoformat()
    with _ANALYSIS_RUNS_LOCK:
        _ANALYSIS_RUNS[run_id] = result
        _ANALYSIS_RUNS.move_to_end(run_id)
        while len(_ANALYSIS_RUNS) > _MAX_ANALYSIS_RUNS:
            _ANALYSIS_RUNS.popitem(last=False)
    return result


def _analysis_run_by_id(run_id: str) -> dict | None:
    key = str(run_id or "").strip()
    if not key:
        return None
    with _ANALYSIS_RUNS_LOCK:
        result = _ANALYSIS_RUNS.get(key)
        if result:
            _ANALYSIS_RUNS.move_to_end(key)
        return result


def _cached_analysis_run(run_id: str, text: str) -> dict | None:
    result = _analysis_run_by_id(run_id)
    if not result or str(result.get("analysis_input_sha256") or "") != _input_sha256(text):
        return None
    return result


# Trwała kolejka importu folderów. Plik trafia najpierw do SQLite jako
# ``processing``; analiza wykonuje się po stronie serwera, niezależnie od tego,
# czy Chrome jest aktualnie na pierwszym planie. Po restarcie app.py rekordy
# ``processing`` są automatycznie wznowione.
_IMPORT_QUEUE: "queue.Queue[dict]" = queue.Queue()
_IMPORT_QUEUE_LOCK = threading.RLock()
_IMPORT_JOB_KEYS: set[tuple[int, str]] = set()
_IMPORT_ACTIVE: dict | None = None
_IMPORT_WORKER_THREAD: threading.Thread | None = None
_IMPORT_STOP_EVENT = threading.Event()
_IMPORT_RECOVERED_AFTER_RESTART = 0


def _enqueue_import_job(*, document_id: int, expected_sha256: str, text: str, retried: bool) -> bool:
    key = (int(document_id), str(expected_sha256 or ""))
    if not key[1]:
        return False
    with _IMPORT_QUEUE_LOCK:
        if key in _IMPORT_JOB_KEYS:
            return False
        _IMPORT_JOB_KEYS.add(key)
    _IMPORT_QUEUE.put({
        "document_id": key[0],
        "expected_sha256": key[1],
        "text": str(text or ""),
        "retried": bool(retried),
    })
    return True


def _background_import_worker() -> None:
    global _IMPORT_ACTIVE
    while not _IMPORT_STOP_EVENT.is_set():
        try:
            job = _IMPORT_QUEUE.get(timeout=0.5)
        except queue.Empty:
            continue
        key = (int(job["document_id"]), str(job["expected_sha256"]))
        with _IMPORT_QUEUE_LOCK:
            _IMPORT_ACTIVE = {"document_id": key[0], "content_sha256": key[1]}
        try:
            current = DOCUMENT_DATABASE.get_document(key[0], include_text=True)
            if not current:
                continue
            doc = current.get("document") or {}
            if str(doc.get("status") or "") != "processing":
                continue
            if str(doc.get("content_sha256") or "") != key[1]:
                continue
            text = str(current.get("text") or job.get("text") or "")
            result = _new_analysis_run(text)
            DOCUMENT_DATABASE.mark_success(
                key[0],
                result,
                retried=bool(job.get("retried")),
                expected_content_sha256=key[1],
            )
            print(f"IMPORT_BG: DONE id={key[0]}", flush=True)
        except StaleImportError:
            print(f"IMPORT_BG: STALE id={key[0]} — pomijam starsze zadanie", flush=True)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            try:
                DOCUMENT_DATABASE.mark_error(
                    key[0],
                    message,
                    retried=bool(job.get("retried")),
                    expected_content_sha256=key[1],
                )
            except StaleImportError:
                pass
            except Exception as mark_exc:
                print(f"IMPORT_BG: błąd zapisu błędu id={key[0]}: {mark_exc}", flush=True)
            print(f"IMPORT_BG: ERROR id={key[0]} {message}", flush=True)
        finally:
            with _IMPORT_QUEUE_LOCK:
                _IMPORT_JOB_KEYS.discard(key)
                _IMPORT_ACTIVE = None
            _IMPORT_QUEUE.task_done()


def _ensure_import_worker_started() -> None:
    global _IMPORT_WORKER_THREAD, _IMPORT_RECOVERED_AFTER_RESTART
    with _IMPORT_QUEUE_LOCK:
        if _IMPORT_WORKER_THREAD is not None and _IMPORT_WORKER_THREAD.is_alive():
            return
        _IMPORT_STOP_EVENT.clear()
        _IMPORT_WORKER_THREAD = threading.Thread(
            target=_background_import_worker,
            name="drogowskazy-import-worker",
            daemon=True,
        )
        _IMPORT_WORKER_THREAD.start()
    recovered = 0
    for snap in DOCUMENT_DATABASE.processing_snapshots():
        if _enqueue_import_job(
            document_id=int(snap["id"]),
            expected_sha256=str(snap["content_sha256"]),
            text=str(snap.get("text_content") or ""),
            retried=int(snap.get("attempts") or 1) > 1,
        ):
            recovered += 1
    _IMPORT_RECOVERED_AFTER_RESTART = recovered
    if recovered:
        print(f"IMPORT_BG: wznowiono tylko {recovered} niedokończonych zadań po restarcie; rekordy done pozostają bez zmian", flush=True)


def shutdown_background_worker(timeout: float = 45.0) -> bool:
    """Zatrzymaj worker przed podmianą runtime. Aktywna analiza może się dokończyć.

    Zadania pozostające w SQLite jako ``processing`` zostaną wznowione przez
    nowy runtime po ponownym uruchomieniu.
    """
    global _IMPORT_WORKER_THREAD
    _IMPORT_STOP_EVENT.set()
    thread = _IMPORT_WORKER_THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(0.0, float(timeout)))
    stopped = not (thread is not None and thread.is_alive())
    if stopped:
        _IMPORT_WORKER_THREAD = None
    return stopped


def _background_import_status() -> dict:
    with _IMPORT_QUEUE_LOCK:
        active = dict(_IMPORT_ACTIVE) if isinstance(_IMPORT_ACTIVE, dict) else None
        return {
            "worker_alive": bool(_IMPORT_WORKER_THREAD and _IMPORT_WORKER_THREAD.is_alive()),
            "queued_memory": int(_IMPORT_QUEUE.qsize()),
            "tracked": int(len(_IMPORT_JOB_KEYS)),
            "active_document_id": int(active["document_id"]) if active else None,
            "recovered_after_restart": int(_IMPORT_RECOVERED_AFTER_RESTART),
        }


_ensure_import_worker_started()


def _empty_text_error(context: str = "analiza"):
    return jsonify({
        "ok": False,
        "blad": "pusty_tekst",
        "kod": "EMPTY_INPUT",
        "kontekst": context,
        "wiadomosc": "Wklej lub wczytaj niepusty tekst przed uruchomieniem operacji.",
    }), 422


def _safe_upload_name(value: str, fallback: str = "dokument.txt") -> str:
    cleaned = repair_polish_mojibake(str(value or "")).replace("\x00", "").strip()
    return (cleaned or fallback)[:1000]


def _payload():
    if request.is_json:
        data = request.get_json(silent=True)
        if data is None:
            return None, (jsonify({"ok": False, "blad": "niepoprawny_json"}), 400)
        if not isinstance(data, dict):
            return None, (jsonify({"ok": False, "blad": "json_musi_byc_obiektem"}), 400)
    else:
        data = request.form or {}
    text = data.get("text") or data.get("tekst") or ""
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        return None, (jsonify({"ok": False, "blad": "tekst_za_duzy", "limit_bajtow": MAX_INPUT_BYTES}), 413)
    return text, None


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(413)
def request_too_large(_error):
    # MAX_CONTENT_LENGTH może zatrzymać request zanim _payload() dostanie sterowanie.
    # API ma mimo to zwracać ten sam typ odpowiedzi JSON co pozostałe błędy kontraktu.
    return jsonify({"ok": False, "blad": "request_za_duzy", "limit_bajtow": MAX_INPUT_BYTES}), 413


@app.errorhandler(404)
def not_found(_error):
    # Nie dokładamy sztucznego /ws. Nieznane endpointy API mają czytelny JSON,
    # a pozostałe nieznane ścieżki pozostają prawdziwym 404.
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "blad": "nieznany_endpoint", "path": request.path}), 404
    return "Not Found", 404


@app.get("/")
def index():
    return render_template("index.html", stage=STAGE, app_version=APP_VERSION)


@app.post("/api/analizuj")
def api_analyze():
    text, error = _payload()
    if error:
        return error
    if not text.strip():
        return _empty_text_error("analiza")
    return jsonify(_new_analysis_run(text))


@app.post("/api/sugestie")
def api_suggest():
    text, error = _payload()
    if error:
        return error
    if not text.strip():
        return _empty_text_error("sugestie")
    return jsonify(sugestie_po_polsku(suggest_text(text)))


@app.post("/api/wczytaj_plik")
def api_wczytaj_plik():
    f = request.files.get("file") or request.files.get("plik")
    if not f:
        return jsonify({"ok": False, "blad": "brak_pliku"}), 400
    raw = f.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return jsonify({"ok": False, "blad": "plik_za_duzy", "limit_bajtow": MAX_INPUT_BYTES}), 413
    text, encoding = decode_text_bytes(raw)
    filename = repair_polish_mojibake(f.filename or "")
    text = prepare_document_text(text, Path(filename).suffix.casefold())
    return jsonify({"ok": True, "nazwa": filename, "znaki": len(text), "tekst": text, "kodowanie": encoding})


@app.post("/api/baza/importuj")
def api_database_import():
    """Zapisuje jeden plik do trwałej kolejki SQLite; analizę wykonuje worker tła."""
    uploaded = request.files.get("file") or request.files.get("plik")
    if not uploaded:
        return jsonify({"ok": False, "blad": "brak_pliku"}), 400

    raw = uploaded.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return jsonify({"ok": False, "blad": "plik_za_duzy", "limit_bajtow": MAX_INPUT_BYTES}), 413

    filename = _safe_upload_name(uploaded.filename)
    relative_path = _safe_upload_name(request.form.get("relative_path") or filename, filename)
    extension = Path(filename).suffix.casefold()
    if extension not in SUPPORTED_DATABASE_EXTENSIONS:
        return jsonify({
            "ok": False,
            "blad": "nieobslugiwane_rozszerzenie",
            "rozszerzenie": extension,
            "dozwolone": sorted(SUPPORTED_DATABASE_EXTENSIONS),
        }), 415

    text, encoding = decode_text_bytes(raw)

    # Normalizacja/sanitizacja importu ma jedno źródło prawdy w DocumentDatabase.
    # V4.3.4 przygotowywała HTML tutaj i drugi raz w begin_import(), co było
    # zbędne i mogło zmienić zakresy przy nie-idempotentnym czyszczeniu.
    try:
        prepared = DOCUMENT_DATABASE.begin_import(
            text=text,
            filename=filename,
            relative_path=relative_path,
            extension=extension,
            encoding=encoding,
            source_bytes=len(raw),
            app_version=APP_VERSION,
        )
    except ValueError as exc:
        message = str(exc)
        if "log techniczny" in message.casefold():
            return jsonify({
                "ok": False,
                "blad": "plik_techniczny_nie_jest_dokumentem",
                "nazwa": filename,
                "wiadomosc": message,
            }), 422
        return jsonify({"ok": False, "blad": "pusty_plik", "nazwa": filename, "wiadomosc": message}), 422
    except Exception as exc:
        return jsonify({
            "ok": False,
            "blad": "nie_udalo_sie_rozpoczac_zapisu_do_bazy",
            "szczegoly": f"{type(exc).__name__}: {exc}",
        }), 500
    document = prepared["document"]
    if prepared["action"] == "duplicate":
        return jsonify({
            "ok": True,
            "status": "duplicate",
            "wiadomosc": "Treść jest już w bazie — pominięto ponowną analizę.",
            "document": document,
            "stats": DOCUMENT_DATABASE.stats(),
        })

    retried = prepared["action"] in {"retry", "replacement"}
    expected_sha256 = str(document.get("content_sha256") or "")
    _ensure_import_worker_started()
    queued = _enqueue_import_job(
        document_id=int(document["id"]),
        expected_sha256=expected_sha256,
        text=str(prepared.get("text") or ""),
        retried=retried,
    )
    return jsonify({
        "ok": True,
        "status": "queued" if queued else "processing",
        "wiadomosc": "Dokument zapisany w trwałej kolejce SQLite. Analiza trwa w tle.",
        "document": document,
        "stats": DOCUMENT_DATABASE.stats(),
        "background_import": _background_import_status(),
    }), 202


@app.get("/api/baza/status")
def api_database_status():
    stats = DOCUMENT_DATABASE.stats()
    return jsonify({
        "ok": True,
        "schema_version": 3,
        "stats": stats,
        "background_import": _background_import_status(),
        "continuation": {
            "done_kept": int(stats.get("done") or 0),
            "remaining_processing": int(stats.get("processing") or 0),
            "errors_kept": int(stats.get("error") or 0),
            "completed_are_never_requeued": True,
        },
    })


@app.get("/api/baza/dokumenty")
def api_database_documents():
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return jsonify({"ok": False, "blad": "limit_i_offset_musza_byc_liczbami"}), 400
    folder = str(request.args.get("folder") or "").strip()
    return jsonify({
        "ok": True,
        "stats": DOCUMENT_DATABASE.stats(),
        "folders": DOCUMENT_DATABASE.list_document_folders(),
        "folder": folder,
        "documents": DOCUMENT_DATABASE.list_documents(limit=limit, offset=offset, folder=folder),
    })


@app.get("/api/baza/dokument/<int:document_id>/wynik")
def api_database_document_result(document_id: int):
    stored = DOCUMENT_DATABASE.get_document(document_id, include_result=True, include_text=True)
    if stored is None:
        return jsonify({"ok": False, "blad": "nie_znaleziono_dokumentu"}), 404
    if stored["document"]["status"] != "done" or stored.get("result") is None:
        return jsonify({
            "ok": False,
            "blad": "wynik_niedostepny",
            "document": stored["document"],
        }), 409
    return jsonify({
        "ok": True,
        "document": stored["document"],
        "tekst": stored["text"],
        "wynik": stored["result"],
    })


@app.post("/api/baza/przelicz_wszystkie")
def api_database_reanalyze_all():
    """Przelicza zapisane dokumenty aktualnym silnikiem bez zmiany ich treści/ID."""
    snapshots = DOCUMENT_DATABASE.reanalysis_snapshots()
    if not snapshots:
        return jsonify({"ok": False, "blad": "brak_dokumentow_do_przeliczenia"}), 409
    done = 0
    errors = []
    for snap in snapshots:
        try:
            result = _new_analysis_run(str(snap.get("text_content") or ""))
            DOCUMENT_DATABASE.replace_analysis_if_unchanged(
                int(snap["id"]), result,
                expected_content_sha256=str(snap["content_sha256"]),
                app_version=APP_VERSION,
            )
            done += 1
        except Exception as exc:
            errors.append({"id": int(snap.get("id") or 0), "plik": str(snap.get("relative_path") or snap.get("filename") or ""),
                           "blad": f"{type(exc).__name__}: {exc}"})
    return jsonify({"ok": not errors, "przeliczono": done, "razem": len(snapshots),
                    "bledy": errors[:50], "stats": DOCUMENT_DATABASE.stats(), "app_version": APP_VERSION}), (200 if not errors else 207)


@app.get("/api/baza/zbiorczy_wynik")
def api_database_aggregate():
    stats = DOCUMENT_DATABASE.stats()
    if int(stats.get("done") or 0) <= 0:
        return jsonify({
            "ok": False,
            "blad": "brak_zapisanych_analiz",
            "kod": "DATABASE_NO_COMPLETED_ANALYSES",
            "wiadomosc": "Baza nie zawiera żadnych zakończonych analiz do połączenia.",
        }), 409
    try:
        aggregate = build_database_aggregate(
            DOCUMENT_DATABASE.iter_completed_results(article_only=True),
            database_stats={**stats, "scope": "articles", "done": int(stats.get("done_articles") or 0)},
        )
    except Exception as exc:
        return jsonify({
            "ok": False,
            "blad": "nie_udalo_sie_zbudowac_wyniku_zbiorczego",
            "szczegoly": f"{type(exc).__name__}: {exc}",
        }), 500
    return jsonify(aggregate)


@app.get("/api/baza/analiza_wybranych")
def api_database_selected_overview():
    """Odczyt tylko zaznaczonych grup, bez modyfikacji SQLite."""
    try:
        groups = request.args.getlist("group")
        mode = request.args.get("mode", "folder")
        if not groups:
            return jsonify({"ok": False, "szczegoly": "Najpierw zaznacz folder lub redakcję."}), 400
        report = cached_selected_overview(
            DOCUMENT_DATABASE, build_selected_database_overview,
            mode=mode, groups=groups,
        )
        return jsonify(report)
    except ValueError as exc:
        return jsonify({"ok": False, "szczegoly": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "szczegoly": f"{type(exc).__name__}: {exc}"}), 500


@app.get("/api/baza/cytaty_wybranych")
def api_selected_quote_database():
    """Zapisane cytaty tylko wskazanych grup; bez zapisów do SQLite."""
    try:
        mode = request.args.get("mode", "folder")
        groups = request.args.getlist("group")
        payload = selected_quote_database(
            DOCUMENT_DATABASE.iter_completed_results(article_only=True),
            mode=mode, groups=groups,
        )
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "szczegoly": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "szczegoly": f"{type(exc).__name__}: {exc}"}), 500


@app.get("/api/baza/wspolna_tresc")
def api_shared_content():
    """Wspólne fragmenty i różnice bez modyfikowania wyników analizy."""
    try:
        groups = request.args.getlist("group")
        mode = request.args.get("mode", "folder")
        report = cached_shared_content(DOCUMENT_DATABASE, compare_shared_content,
            mode=mode, groups=groups)
        return jsonify(report)
    except ValueError as exc:
        return jsonify({"ok": False, "szczegoly": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "szczegoly": f"{type(exc).__name__}: {exc}"}), 500


@app.get("/api/baza/porownanie/grupy")
def api_database_compare_groups():
    mode = str(request.args.get("mode") or "publisher").strip().casefold()
    try:
        groups = list_comparison_groups(DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True), mode=mode)
    except ValueError as exc:
        return jsonify({"ok": False, "blad": "nieprawidlowy_tryb_porownania", "wiadomosc": str(exc)}), 400
    return jsonify({
        "ok": True,
        "mode": mode,
        "groups": groups,
        "stats": DOCUMENT_DATABASE.stats(),
    })


@app.get("/api/baza/porownanie")
def api_database_compare():
    mode = str(request.args.get("mode") or "publisher").strip().casefold()
    groups = [str(value or "").strip() for value in request.args.getlist("group") if str(value or "").strip()]
    # Zgodność wsteczna z dotychczasowym API A/B. Frontend V4.5 używa `group=`.
    if not groups:
        group_a = str(request.args.get("a") or "").strip()
        group_b = str(request.args.get("b") or "").strip()
        groups = [x for x in (group_a, group_b) if x]
    try:
        if len(groups) > 2:
            comparison = build_multi_group_comparison(
                DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
                mode=mode, groups=groups,
            )
        elif len(groups) == 2:
            comparison = build_group_comparison(
                DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
                mode=mode, group_a=groups[0], group_b=groups[1],
            )
        else:
            raise ValueError("Wybierz co najmniej dwie grupy do porównania.")
    except ValueError as exc:
        return jsonify({"ok": False, "blad": "nieprawidlowe_parametry_porownania", "wiadomosc": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "blad": "brak_danych_do_porownania", "wiadomosc": str(exc)}), 404
    except Exception as exc:
        return jsonify({
            "ok": False,
            "blad": "nie_udalo_sie_porownac_grup",
            "szczegoly": f"{type(exc).__name__}: {exc}",
        }), 500
    return jsonify(comparison)


@app.get("/api/baza/tematy")
def api_database_topics():
    try:
        payload = cached_topics(DOCUMENT_DATABASE, discover_same_story_topics)
    except Exception as exc:
        return jsonify({"ok": False, "blad": "nie_udalo_sie_wykryc_tematow", "szczegoly": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify(payload)


@app.get("/api/baza/temat/porownanie")
def api_database_topic_compare():
    topic_id = str(request.args.get("topic_id") or "").strip()
    groups = [str(value or "").strip() for value in request.args.getlist("group") if str(value or "").strip()]
    group_a = str(request.args.get("a") or "").strip()
    group_b = str(request.args.get("b") or "").strip()
    mode = str(request.args.get("mode") or "publisher").strip().casefold()
    if not topic_id:
        return jsonify({"ok": False, "blad": "brak_topic_id", "wiadomosc": "Wybierz wykryty temat."}), 400
    try:
        payload = cached_comparison(
            DOCUMENT_DATABASE, build_same_story_comparison,
            topic_id=topic_id, group_a=group_a, group_b=group_b, groups=groups, mode=mode,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "blad": "nieprawidlowe_parametry_porownania", "wiadomosc": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "blad": "brak_tematu_do_porownania", "wiadomosc": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "blad": "nie_udalo_sie_porownac_tematu", "szczegoly": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify(payload)


@app.get("/api/baza/benchmark/proba")
def api_database_benchmark_sample():
    try:
        size = int(request.args.get("size") or 30)
    except (TypeError, ValueError):
        size = 30
    seed = str(request.args.get("seed") or "default")[:100]
    mode = str(request.args.get("mode") or "").strip().casefold()
    group = str(request.args.get("group") or "").strip()
    unlabeled = str(request.args.get("unlabeled") or "1").strip().casefold() not in {"0", "false", "no"}
    if mode and mode not in {"publisher", "folder"}:
        return jsonify({"ok": False, "blad": "nieprawidlowy_tryb_benchmarku"}), 400
    try:
        excluded = DOCUMENT_DATABASE.benchmark_label_keys() if unlabeled else set()
        payload = build_benchmark_sample(
            DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
            size=size, seed=seed, mode=mode, group=group, exclude_keys=excluded,
        )
        payload["summary"] = summarize_benchmark(DOCUMENT_DATABASE.list_benchmark_labels())
    except Exception as exc:
        return jsonify({"ok": False, "blad": "nie_udalo_sie_zbudowac_proby_benchmarku", "szczegoly": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify(payload)


@app.post("/api/baza/benchmark/ocena")
def api_database_benchmark_label():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "blad": "json_musi_byc_obiektem"}), 400
    try:
        row = DOCUMENT_DATABASE.save_benchmark_label(
            document_id=int(data.get("document_id") or 0),
            relation_id=str(data.get("relation_id") or ""),
            overall_label=str(data.get("overall_label") or ""),
            speaker_label=str(data.get("speaker_label") or "unknown"),
            claim_label=str(data.get("claim_label") or "unknown"),
            target_label=str(data.get("target_label") or "unknown"),
            source_label=str(data.get("source_label") or "unknown"),
            note=str(data.get("note") or ""),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "blad": "nieprawidlowa_ocena", "wiadomosc": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "blad": "brak_dokumentu", "wiadomosc": str(exc)}), 404
    summary = summarize_benchmark(DOCUMENT_DATABASE.list_benchmark_labels())
    return jsonify({"ok": True, "label": row, "summary": summary})


@app.get("/api/baza/benchmark/wynik")
def api_database_benchmark_result():
    return jsonify(summarize_benchmark(DOCUMENT_DATABASE.list_benchmark_labels()))


@app.get("/api/baza/gold/proba")
def api_database_gold_sample():
    try:
        size = int(request.args.get("size") or 10)
    except (TypeError, ValueError):
        size = 10
    seed = str(request.args.get("seed") or "gold-v1")[:100]
    unlabeled = str(request.args.get("unlabeled") or "1").strip().casefold() not in {"0", "false", "no"}
    try:
        excluded = DOCUMENT_DATABASE.gold_annotated_document_ids(completed_only=False) if unlabeled else set()
        payload = build_gold_document_sample(
            DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
            size=size, seed=seed, exclude_document_ids=excluded,
        )
        payload["summary"] = summarize_effectiveness_gold(
            DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
            DOCUMENT_DATABASE.list_gold_annotations(completed_only=True),
        )
    except Exception as exc:
        return jsonify({"ok": False, "blad": "nie_udalo_sie_zbudowac_gold", "szczegoly": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify(payload)


@app.post("/api/baza/gold/dokument")
def api_database_gold_annotation():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "blad": "json_musi_byc_obiektem"}), 400
    try:
        row = DOCUMENT_DATABASE.save_gold_annotation(
            document_id=int(data.get("document_id") or 0),
            expected_relations=data.get("expected_relations") or [],
            note=str(data.get("note") or ""),
            completed=bool(data.get("completed", True)),
            app_version=APP_VERSION,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "blad": "nieprawidlowa_anotacja_gold", "wiadomosc": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "blad": "brak_dokumentu", "wiadomosc": str(exc)}), 404
    summary = summarize_effectiveness_gold(
        DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
        DOCUMENT_DATABASE.list_gold_annotations(completed_only=True),
    )
    return jsonify({"ok": True, "annotation": row, "summary": summary})


@app.get("/api/baza/gold/wynik")
def api_database_gold_result():
    return jsonify(summarize_effectiveness_gold(
        DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),
        DOCUMENT_DATABASE.list_gold_annotations(completed_only=True),
    ))


@app.get("/api/baza/pobierz")
def api_database_download():
    descriptor, temporary_name = tempfile.mkstemp(prefix="drogowskazy_baza_", suffix=".sqlite3")
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        DOCUMENT_DATABASE.backup_to(temporary_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = send_file(
            temporary_path,
            as_attachment=True,
            download_name=f"drogowskazy_baza_{timestamp}.sqlite3",
            mimetype="application/vnd.sqlite3",
            max_age=0,
        )
        response.call_on_close(lambda: temporary_path.unlink(missing_ok=True))
        return response
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


@app.post("/api/raport")
def api_report_export():
    text, error = _payload()
    if error:
        return error
    if not text.strip():
        return _empty_text_error("raport")

    payload = request.get_json(silent=True) if request.is_json else request.form
    run_id = str((payload or {}).get("analysis_run_id") or "").strip()
    analiza = None
    if run_id:
        existing = _analysis_run_by_id(run_id)
        if existing is not None:
            expected_hash = str(existing.get("analysis_input_sha256") or "")
            current_hash = _input_sha256(text)
            if expected_hash != current_hash:
                return jsonify({
                    "ok": False,
                    "blad": "tekst_zmieniony_od_analizy",
                    "kod": "ANALYSIS_RUN_INPUT_MISMATCH",
                    "analysis_run_id": run_id,
                    "wiadomosc": "Tekst zmienił się po analizie. Uruchom analizę ponownie przed eksportem raportu.",
                }), 409
            analiza = existing

    # Po restarcie procesu pamięć runów jest pusta. Wtedy wolno odtworzyć raport
    # tylko z niepustego tekstu; nigdy nie robimy cichej analizy pustego pola.
    if analiza is None:
        analiza = _new_analysis_run(text)

    package = generuj_pakiet_eksportu(analiza, tekst_zrodlowy=text)
    package["analysis_run_id"] = analiza.get("analysis_run_id")
    package["analysis_input_sha256"] = analiza.get("analysis_input_sha256")
    package["analysis_generated_at"] = analiza.get("analysis_generated_at")
    package["single_run_export"] = True
    return jsonify(package)


@app.get("/api/tryby")
def api_tryby():
    return jsonify(lista_trybow_pracy())


@app.get("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "etap": STAGE,
        "wersja": APP_VERSION,
        "architektura": "jeden_pipeline_jeden_kontrakt",
        "serwer": "flask",
        "transport": "http_json",
        "websocket": False,
        "host_scope": "same_origin_http",
        "request_origin": request.host_url.rstrip("/"),
        "endpoints": RUNTIME_CONTRACT,
        "database": {
            "engine": "sqlite3",
            "schema_version": 3,
            "sequential_folder_import": True,
            "persistent_background_queue": True,
            "aggregate_saved_results": True,
        },
        "background_service": os.environ.get("DROGOWSKAZY_BACKGROUND_SERVICE") == "1",
        "background_import": _background_import_status(),
    })


if __name__ == "__main__":
    print(f"Drogowskazy {APP_VERSION}: http://127.0.0.1:{DEFAULT_PORT}/")
    app.run(host="127.0.0.1", port=DEFAULT_PORT, debug=False, use_reloader=False)
