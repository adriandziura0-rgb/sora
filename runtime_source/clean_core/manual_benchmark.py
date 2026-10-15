from __future__ import annotations

"""Ręczny benchmark jakości zaakceptowanych relacji.

Moduł nie udaje recallu: próbkuje relacje wygenerowane przez system i pozwala
człowiekowi oznaczyć poprawność całej relacji oraz pól speaker/claim/target/source.
"""

from collections import Counter
from hashlib import sha256
from typing import Any, Dict, Iterable

from .editorial_compare import comparison_group

BENCHMARK_SCHEMA = "manual_relation_benchmark_v1"
LABELS = {"correct", "partial", "false"}
FIELD_LABELS = LABELS | {"unknown"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _relations(result: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows = ((result.get("sekcje") or {}).get("relacje_wypowiedzi") or [])
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = _clean(row.get("relation_id"))
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def _snippet(text: str, card: Dict[str, Any], radius: int = 420) -> str:
    text = str(text or "")
    fragment = _clean(card.get("fragment") or card.get("evidence_text") or card.get("fraza"))
    if not text:
        return fragment[:900]
    if fragment:
        pos = text.find(fragment)
        if pos >= 0:
            return " ".join(text[max(0, pos-radius):min(len(text), pos+len(fragment)+radius)].split())
    claim = _clean(card.get("fraza") or ((card.get("relacja_wypowiedzi") or {}).get("co_mowi")))
    if claim:
        pos = text.find(claim)
        if pos >= 0:
            return " ".join(text[max(0, pos-radius):min(len(text), pos+len(claim)+radius)].split())
    return " ".join(text[:900].split())


def build_benchmark_sample(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]], *,
    size: int = 30, seed: str = "default", mode: str = "", group: str = "",
    exclude_keys: set[tuple[int, str]] | None = None,
) -> Dict[str, Any]:
    safe_size = max(1, min(200, int(size)))
    excluded = exclude_keys or set()
    candidates = []
    for document, result in completed_results:
        if mode and group and comparison_group(document, result, mode) != group:
            continue
        doc_id = int(document.get("id") or 0)
        text = str(document.get("_text_content") or "")
        for card in _relations(result):
            rid = _clean(card.get("relation_id"))
            if (doc_id, rid) in excluded:
                continue
            key = sha256(f"{seed}|{doc_id}|{rid}".encode("utf-8")).hexdigest()
            rel = card.get("relacja_wypowiedzi") or {}
            candidates.append((key, {
                "document_id": doc_id,
                "relation_id": rid,
                "filename": document.get("filename") or "",
                "relative_path": document.get("relative_path") or "",
                "publisher": comparison_group(document, result, "publisher"),
                "speaker": _clean(card.get("kto_mowi") or rel.get("kto_mowi")),
                "action": _clean(card.get("dzialanie")),
                "target": _clean(card.get("o_kim") or rel.get("o_kim")),
                "claim": _clean(card.get("fraza") or rel.get("co_mowi")),
                "source": _clean(card.get("zrodlo_przywolane")),
                "requires_review": bool(card.get("wymaga_przegladu")),
                "confidence": card.get("surowa_pewnosc_relacji") or card.get("pewnosc_wzorca") or card.get("pewnosc") or "",
                "snippet": _snippet(text, card),
            }))
    candidates.sort(key=lambda x: x[0])
    return {
        "ok": True,
        "schema": BENCHMARK_SCHEMA,
        "size_requested": safe_size,
        "available": len(candidates),
        "items": [item for _, item in candidates[:safe_size]],
        "method_note": "Próba jest deterministyczna dla podanego seed. Mierzy precyzję wygenerowanych relacji, nie recall brakujących relacji.",
    }


def summarize_benchmark(labels: list[Dict[str, Any]]) -> Dict[str, Any]:
    def metric(field: str, allow_unknown: bool = False) -> Dict[str, Any]:
        values = [str(row.get(field) or "unknown").casefold() for row in labels]
        if not allow_unknown:
            values = [x for x in values if x in LABELS]
        else:
            values = [x for x in values if x in FIELD_LABELS and x != "unknown"]
        counts = Counter(values)
        n = sum(counts.values())
        strict = counts.get("correct", 0) / n * 100.0 if n else 0.0
        lenient = (counts.get("correct", 0) + counts.get("partial", 0)) / n * 100.0 if n else 0.0
        return {
            "n": n,
            "correct": counts.get("correct", 0), "partial": counts.get("partial", 0), "false": counts.get("false", 0),
            "strict_percent": round(strict, 2), "lenient_percent": round(lenient, 2),
        }
    return {
        "ok": True,
        "schema": BENCHMARK_SCHEMA,
        "labels_total": len(labels),
        "overall": metric("overall_label"),
        "speaker": metric("speaker_label", True),
        "claim": metric("claim_label", True),
        "target": metric("target_label", True),
        "source": metric("source_label", True),
        "warning": "To precyzja ręcznie ocenionej próby zaakceptowanych relacji. Recall wymaga osobno oznaczonego zbioru wszystkich oczekiwanych relacji.",
    }
