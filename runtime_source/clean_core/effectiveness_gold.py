from __future__ import annotations

"""Niezależny GOLD skuteczności na pełnych dokumentach.

W odróżnieniu od benchmarku regresyjnego, anotator zapisuje kompletną listę
oczekiwanych relacji dla dokumentu. Dzięki temu można policzyć także FN/recall.
"""

from hashlib import sha256
import re
from typing import Any, Dict, Iterable, Mapping

SCHEMA = "drogowskazy_effectiveness_gold_v1"
_WORD = re.compile(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", re.UNICODE)


def _clean(v: Any) -> str:
    return " ".join(str(v or "").split()).strip()


def _norm(v: Any) -> str:
    return _clean(v).casefold()


def _tokens(v: Any) -> set[str]:
    return {x.casefold() for x in _WORD.findall(_clean(v)) if len(x) > 1}


def _token_f1(a: Any, b: Any) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    inter = len(aa & bb)
    p, r = inter / len(aa), inter / len(bb)
    return (2 * p * r / (p + r)) if p + r else 0.0


def _relations(result: Mapping[str, Any]) -> list[Dict[str, str]]:
    rows = ((result.get("sekcje") or {}).get("relacje_wypowiedzi") or [])
    out, seen = [], set()
    for card in rows:
        if not isinstance(card, dict):
            continue
        rel = card.get("relacja_wypowiedzi") or {}
        row = {
            "relation_id": _clean(card.get("relation_id")),
            "speaker": _clean(card.get("kto_mowi") or rel.get("kto_mowi")),
            "claim": _clean(card.get("fraza") or rel.get("co_mowi")),
            "target": _clean(card.get("o_kim") or rel.get("o_kim")),
            "source": _clean(card.get("zrodlo_przywolane")),
        }
        key = (row["relation_id"], row["speaker"], row["claim"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_gold_document_sample(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]], *,
    size: int = 10, seed: str = "gold-v1", exclude_document_ids: set[int] | None = None,
) -> Dict[str, Any]:
    excluded = exclude_document_ids or set()
    candidates = []
    for document, result in completed_results:
        doc_id = int(document.get("id") or 0)
        if not doc_id or doc_id in excluded:
            continue
        text = str(document.get("_text_content") or "")
        key = sha256(f"{seed}|{doc_id}|{document.get('content_sha256','')}".encode("utf-8")).hexdigest()
        candidates.append((key, {
            "document_id": doc_id,
            "filename": document.get("filename") or "",
            "relative_path": document.get("relative_path") or "",
            "text": text,
            "predicted_relations": _relations(result),
        }))
    candidates.sort(key=lambda x: x[0])
    safe = max(1, min(50, int(size)))
    return {"ok": True, "schema": SCHEMA, "available": len(candidates), "items": [x for _, x in candidates[:safe]]}


def _pair_score(pred: Mapping[str, Any], gold: Mapping[str, Any]) -> tuple[float, bool, bool]:
    speaker_equal = bool(_norm(gold.get("speaker"))) and _norm(pred.get("speaker")) == _norm(gold.get("speaker"))
    claim_score = _token_f1(pred.get("claim"), gold.get("claim"))
    target_gold = _norm(gold.get("target"))
    source_gold = _norm(gold.get("source"))
    target_ok = not target_gold or _norm(pred.get("target")) == target_gold
    source_ok = not source_gold or _norm(pred.get("source")) == source_gold
    strict = speaker_equal and claim_score >= 0.75 and target_ok and source_ok
    lenient = speaker_equal and claim_score >= 0.50
    score = (2.0 if speaker_equal else 0.0) + claim_score + (0.25 if target_ok else 0.0) + (0.25 if source_ok else 0.0)
    return score, strict, lenient


def _match(predicted: list[Mapping[str, Any]], expected: list[Mapping[str, Any]], *, lenient: bool) -> tuple[int, int, int, list[Dict[str, Any]]]:
    pairs = []
    for pi, p in enumerate(predicted):
        for gi, g in enumerate(expected):
            score, strict_ok, lenient_ok = _pair_score(p, g)
            ok = lenient_ok if lenient else strict_ok
            if ok:
                pairs.append((score, pi, gi))
    pairs.sort(reverse=True)
    used_p, used_g, matches = set(), set(), []
    for score, pi, gi in pairs:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi); used_g.add(gi)
        matches.append({"predicted_index": pi, "expected_index": gi, "score": round(score, 4)})
    tp = len(matches)
    fp = len(predicted) - tp
    fn = len(expected) - tp
    return tp, fp, fn, matches


def _metrics(tp: int, fp: int, fn: int) -> Dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def summarize_effectiveness_gold(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]],
    annotations: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    ann = {int(x.get("document_id") or 0): x for x in annotations if x.get("completed")}
    strict_tot = [0, 0, 0]
    lenient_tot = [0, 0, 0]
    docs = []
    for document, result in completed_results:
        doc_id = int(document.get("id") or 0)
        if doc_id not in ann:
            continue
        predicted = _relations(result)
        expected = [x for x in (ann[doc_id].get("expected_relations") or []) if isinstance(x, dict)]
        stp, sfp, sfn, sm = _match(predicted, expected, lenient=False)
        ltp, lfp, lfn, lm = _match(predicted, expected, lenient=True)
        strict_tot[0] += stp; strict_tot[1] += sfp; strict_tot[2] += sfn
        lenient_tot[0] += ltp; lenient_tot[1] += lfp; lenient_tot[2] += lfn
        docs.append({
            "document_id": doc_id,
            "filename": document.get("filename") or "",
            "predicted": len(predicted), "expected": len(expected),
            "strict": _metrics(stp, sfp, sfn), "lenient": _metrics(ltp, lfp, lfn),
            "strict_matches": sm, "lenient_matches": lm,
        })
    return {
        "ok": True,
        "schema": SCHEMA,
        "documents": len(docs),
        "strict": _metrics(*strict_tot),
        "lenient": _metrics(*lenient_tot),
        "per_document": docs,
        "method_note": "Strict: ten sam speaker, podobieństwo claim >= 0.75 oraz zgodny target/source, jeśli oznaczone. Lenient: ten sam speaker i podobieństwo claim >= 0.50. Wynik ma sens tylko dla dokumentów oznaczonych jako kompletne GOLD.",
    }
