"""Read-only, bounded cache for *requested* same-story searches.

Does not alter the classifier, database schema, document lifecycle or its
background import worker. One snapshot of DB metadata is much cheaper than
scanning and scoring all cross-publisher article pairs repeatedly.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from threading import RLock

_LOCK = RLock()
_GENERATION = None
_TOPICS = None
_COMPARISONS = {}
_OVERVIEWS = {}
_SHARED_CONTENT = {}
_MAX_COMPARISONS = 12
_MAX_OVERVIEWS = 8


def _generation(database):
    # Every completed article ID, content digest and analysis update contributes.
    # Works after restarts and replacements even if document count is unchanged.
    digest = sha256()
    with database._connect() as db:
        rows = db.execute(
            """SELECT id, content_sha256, updated_at, LENGTH(analysis_gzip) AS result_size
               FROM documents WHERE status='done' ORDER BY id"""
        )
        for doc_id, content_hash, updated, result_size in rows:
            part = (str(doc_id), str(content_hash or ""), str(updated or ""), str(result_size or 0))
            digest.update("\0".join(part).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _check_generation(generation):
    global _GENERATION, _TOPICS
    if _GENERATION != generation:
        _GENERATION = generation
        _TOPICS = None
        _COMPARISONS.clear()
        _OVERVIEWS.clear()
        _SHARED_CONTENT.clear()


def cached_topics(database, discover):
    global _TOPICS
    with _LOCK:
        _check_generation(_generation(database))
        if _TOPICS is None:
            _TOPICS = discover(database.iter_completed_results(include_text=True, article_only=True))
        return deepcopy(_TOPICS)


def cached_comparison(database, build, *, topic_id, mode, groups, group_a, group_b):
    # A cached comparison is scoped to its *exact* explicit topic and groups.
    key = (str(topic_id), str(mode), tuple(groups), str(group_a), str(group_b))
    with _LOCK:
        _check_generation(_generation(database))
        cached = _COMPARISONS.get(key)
        if cached is None:
            cached = build(
                database.iter_completed_results(include_text=True, article_only=True),
                topic_id=topic_id, mode=mode, groups=groups,
                group_a=group_a, group_b=group_b,
            )
            if len(_COMPARISONS) >= _MAX_COMPARISONS:
                del _COMPARISONS[next(iter(_COMPARISONS))]
            _COMPARISONS[key] = cached
        return deepcopy(cached)


def cached_selected_overview(database, build, *, mode, groups):
    """Return the same read-only report while the database is unchanged.

    The cache is invalidated on any completed-analysis update, not on a timer.
    It never stores editable database objects, and is limited to eight scopes.
    """
    names = [str(name).strip() for name in groups]
    key = (str(mode or "").strip().casefold(), tuple(names))
    with _LOCK:
        _check_generation(_generation(database))
        result = _OVERVIEWS.get(key)
        if result is None:
            result = build(
                database.iter_completed_results(include_text=True, article_only=True),
                mode=mode, groups=names,
            )
            if len(_OVERVIEWS) >= _MAX_OVERVIEWS:
                del _OVERVIEWS[next(iter(_OVERVIEWS))]
            _OVERVIEWS[key] = result
        return deepcopy(result)


def cached_shared_content(database, build, *, mode, groups):
    """Pamiętaj porównanie do kolejnej zmiany ukończonych analiz.

    Żadne operacje po starcie aplikacji; dopiero jawne żądanie HTTP.
    """
    names = list(dict.fromkeys(str(x).strip() for x in groups if str(x).strip()))
    key = (str(mode).casefold(), tuple(names))
    with _LOCK:
        _check_generation(_generation(database))
        result = _SHARED_CONTENT.get(key)
        if result is None:
            result = build(
                database.iter_completed_results(include_text=True, article_only=True),
                mode=mode, groups=names,
            )
            if len(_SHARED_CONTENT) >= 5:
                del _SHARED_CONTENT[next(iter(_SHARED_CONTENT))]
            _SHARED_CONTENT[key] = result
        return deepcopy(result)
