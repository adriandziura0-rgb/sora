"""Read-only database of attributed quotations in explicitly selected articles.

Every row is taken from a persisted fact_opinia_cytat card. This is NOT a
source-verification system; common wording is not proof of original authorship.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from .editorial_compare import comparison_group, MAX_COMPARE_GROUPS, VALID_MODES
from .document_kind import is_article_document

QUOTE_TYPES = {"opinia_cytowana", "cytat_przypisany", "cytat"}
MAX_DOCS = 1200
MAX_QUOTES = 6000


def _clean(value):
    return " ".join(str(value or "").split()).strip()


def _key(value):
    return " ".join(re.findall(r"(?u)\w+", value.casefold()))


def selected_quote_database(rows, *, mode, groups):
    mode = str(mode or "").strip().casefold()
    if mode not in VALID_MODES:
        raise ValueError("Wybierz foldery lub redakcje.")
    chosen = []
    for value in groups:
        value = _clean(value)
        if value and value.casefold() not in {v.casefold() for v in chosen}:
            chosen.append(value)
    if not 1 <= len(chosen) <= MAX_COMPARE_GROUPS:
        raise ValueError("Zaznacz od 1 do 10 folderów lub redakcji.")
    wanted = {name.casefold() for name in chosen}
    counts = Counter()
    documents = Counter()
    records = []
    docs_seen = 0
    truncated = False
    seen_ids = set()
    for doc, result in rows:
        if not is_article_document(doc):
            continue
        group = comparison_group(doc, result, mode)
        if group.casefold() not in wanted:
            continue
        docs_seen += 1
        if docs_seen > MAX_DOCS:
            truncated = True
            break
        documents[group] += 1
        cards = (result.get("sekcje") or {}).get("fact_opinia_cytat") or []
        for card in cards:
            if not isinstance(card, dict):
                continue
            kind = _clean(card.get("claim_type")).casefold()
            if kind not in QUOTE_TYPES:
                continue
            quote = _clean(card.get("phrase") or card.get("fragment"))
            speaker = _clean(card.get("speaker"))
            if len(quote) < 12 or not speaker:
                continue
            identity = (int(doc["id"]), _clean(card.get("relation_id")) or _key(quote),
                        kind)
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
            counts[group] += 1
            records.append({
                "document_id": int(doc["id"]),
                "path": _clean(doc.get("relative_path") or doc.get("filename")),
                "group": group, "speaker": speaker, "statement": quote[:900],
                "classification": _clean(card.get("claim_type_pl") or kind),
                "relation_id": _clean(card.get("relation_id")),
                "requires_review": bool(card.get("requires_review")),
            })
            if len(records) >= MAX_QUOTES:
                truncated = True
                break
        if truncated:
            break

    matching = defaultdict(list)
    for record in records:
        # Exact normalized statement AND attributed speaker, no fuzzy guesses.
        k = (_key(record["speaker"]), _key(record["statement"]))
        if len(k[1]) >= 22:
            matching[k].append(record)
    common = []
    for appearances in matching.values():
        groups_here = {r["group"].casefold() for r in appearances}
        if len(groups_here) < 2:
            continue
        common.append({
            "speaker": appearances[0]["speaker"],
            "statement": appearances[0]["statement"],
            "appearances": len(appearances),
            "groups": sorted({r["group"] for r in appearances}),
            "documents": [{"document_id":r["document_id"],"group":r["group"],
                            "path":r["path"]} for r in appearances[:12]],
        })
    common.sort(key=lambda x: (-len(x["groups"]), -x["appearances"], x["speaker"].casefold()))
    return {
        "ok": True, "read_only": True, "schema": "sora_quote_database_v1",
        "mode": mode, "selected_groups": chosen, "scanned_documents": docs_seen,
        "quote_count": len(records), "per_group": [
            {"group":name, "documents":sum(n for g,n in documents.items() if g.casefold()==name.casefold()),
             "quotes":sum(n for g,n in counts.items() if g.casefold()==name.casefold())}
            for name in chosen
        ],
        "same_statement_across_groups": common[:100],
        "records": records,
        "truncated": truncated,
        "note": "Tylko zapisane karty opinia cytowana / cytat przypisany / cytat. "
                "Atrybucja pochodzi z analizy i wymaga weryfikacji w tekście źródłowym. "
                "Wspólny zapis słów nie dowodzi cytowania tego samego oryginalnego źródła. "
                "Brak dopasowania dosłownego nie wyklucza parafrazy.",
    }
