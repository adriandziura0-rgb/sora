from __future__ import annotations

"""Pojedynczy kontekst wejściowy z trwałą tożsamością dokumentów.

Każdy dokument zachowuje własne ``document_id`` oraz własne metadane źródłowe.
Metadane dokumentu nie są już spłaszczane do globalnej listy używanej przez
relacje. Globalne listy pozostają wyłącznie jako podsumowanie wejścia.
"""

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Dict, List

from .input_metadata_parser import parse_input_metadata
from .segmentation import segment_document, make_document_id
from .text_cleaning import split_source_and_meta, sanitize_document

_FILE_HEADER_RE = re.compile(r"^\s*---\s*WCZYTANY\s+PLIK\s*:\s*(.+?)\s*---\s*$", re.I | re.M)


@dataclass(frozen=True)
class PipelineContext:
    original_text: str
    analyzable_text: str
    relation_text: str
    segments: List[Dict[str, object]]
    metadata_segments: List[Dict[str, object]]
    cleaning: Dict[str, object]
    document_source: str
    document_sources: List[str]
    image_sources: List[str]
    document_ids: List[str]
    document_metadata: Dict[str, Dict[str, object]]
    document_texts: Dict[str, str]
    document_structured_texts: Dict[str, str]


def _unique(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _split_documents(original: str) -> List[tuple[int, str, str]]:
    """Zwraca ``(document_index, label, raw_text)`` bez mieszania plików."""
    matches = list(_FILE_HEADER_RE.finditer(original))
    if not matches:
        return [(0, "input", original)]

    docs: List[tuple[int, str, str]] = []
    prefix = original[: matches[0].start()].strip()
    next_index = 0
    if prefix:
        docs.append((next_index, "input", prefix))
        next_index += 1

    for pos, match in enumerate(matches):
        start = match.end()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(original)
        label = re.sub(r"\s+", " ", match.group(1)).strip() or f"document_{next_index + 1}"
        body = original[start:end].strip()
        docs.append((next_index, label, body))
        next_index += 1
    return docs


def _canonical_document_body(body: str) -> str:
    """Stabilny klucz treści do deduplikacji całych dokumentów.

    Normalizujemy wyłącznie zapis Unicode i białe znaki. Nie stosujemy
    stemmingu ani podobieństwa semantycznego, więc dwa różne artykuły nie są
    łączone tylko dlatego, że opisują ten sam temat.
    """
    value = unicodedata.normalize("NFKC", str(body or ""))
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", value).strip()


def _deduplicate_documents(docs: List[tuple[int, str, str]]) -> tuple[List[tuple[int, str, str]], List[Dict[str, object]], List[Dict[str, object]]]:
    """Usuwa dokładne duplikaty całych dokumentów przed jakąkolwiek analizą.

    Pierwsze wystąpienie zostaje źródłem prawdy. Duplikat nie może dostać
    drugiego document_id, relacji, TOP-u ani kart P0–P5.
    """
    unique: List[tuple[int, str, str]] = []
    duplicates: List[Dict[str, object]] = []
    empty_documents: List[Dict[str, object]] = []
    seen: Dict[str, tuple[int, str]] = {}
    for _old_index, label, body in docs:
        canonical = _canonical_document_body(body)
        # Pusty plik/nagłówek wejściowy nie jest dokumentem analitycznym.
        # Pomijamy go przed nadaniem indeksu i document_id, aby cały pipeline
        # widział wyłącznie realne dokumenty z treścią.
        if not canonical:
            empty_documents.append({
                "document_label": label,
                "original_index": _old_index,
                "reason": "empty_document_ignored",
            })
            continue
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest and digest in seen:
            kept_index, kept_label = seen[digest]
            duplicates.append({
                "document_label": label,
                "duplicate_of_label": kept_label,
                "duplicate_of_index": kept_index,
                "content_sha256": digest,
            })
            continue
        new_index = len(unique)
        unique.append((new_index, label, body))
        if digest:
            seen[digest] = (new_index, label)
    return unique, duplicates, empty_documents


def _document_metadata(docs: List[tuple[int, str, str]]) -> Dict[str, Dict[str, object]]:
    mapping: Dict[str, Dict[str, object]] = {}
    for document_index, label, body in docs:
        document_id = make_document_id(document_index, label)
        meta = parse_input_metadata(body)
        mapping[document_id] = {
            "document_id": document_id,
            "document_index": document_index,
            "document_label": label,
            "document_source": (list(meta.document_sources)[0] if meta.document_sources else ""),
            "document_sources": list(meta.document_sources[:1]),
            "publisher_source": (list(meta.document_sources)[0] if meta.document_sources else ""),
            "quoted_sources": list(meta.document_sources[1:]),
            "image_sources": list(meta.image_sources),
        }
    return mapping


def build_pipeline_context(text: str) -> PipelineContext:
    original = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    docs_all = _split_documents(original)
    docs_raw, duplicate_documents, empty_documents = _deduplicate_documents(docs_all)
    sanitized_parts: List[str] = []
    sanitizer_stats: List[Dict[str, object]] = []
    for _idx, _label, _body in docs_raw:
        _san = sanitize_document(_body)
        sanitizer_stats.append({"document_index": _idx, "document_label": _label, **{k:v for k,v in _san.items() if k not in {"source_text", "sanitized_text"}}})
        if len(docs_raw) > 1 or _label != "input":
            sanitized_parts.append(f"--- WCZYTANY PLIK: {_label} ---")
        sanitized_parts.append(str(_san.get("source_text") or ""))
    sanitized_input = "\n\n".join(sanitized_parts).strip()
    cleaning = split_source_and_meta(sanitized_input)
    cleaning = {**dict(cleaning), "sanitizer_documents": sanitizer_stats, "source_text": sanitized_input}
    segments = [segment.to_dict() for segment in segment_document(sanitized_input)]
    analyzable = [segment for segment in segments if segment.get("analyzable")]
    metadata = [segment for segment in segments if not segment.get("analyzable")]
    per_document = _document_metadata(docs_raw)

    grouped: Dict[tuple[str, int], List[str]] = {}
    for segment in analyzable:
        key = (str(segment.get("document_id") or ""), int(segment.get("block_index", 0)))
        grouped.setdefault(key, []).append(str(segment.get("text") or "").strip())
    ordered_keys = sorted(grouped, key=lambda key: (key[0], key[1]))
    blocks = [" ".join(grouped[key]).strip() for key in ordered_keys if " ".join(grouped[key]).strip()]
    document_texts: Dict[str, str] = {}
    document_structured_texts: Dict[str, str] = {}
    for key in ordered_keys:
        doc_id, _block_index = key
        block = " ".join(grouped[key]).strip()
        if block:
            document_texts[doc_id] = (document_texts.get(doc_id, "") + " " + block).strip()
            previous = document_structured_texts.get(doc_id, "")
            document_structured_texts[doc_id] = (previous + ("\n\n" if previous else "") + block).strip()
    analyzable_text = "\n\n".join(document_texts.get(doc_id, "") for doc_id in document_texts if document_texts.get(doc_id, ""))

    document_ids = list(dict.fromkeys(str(segment.get("document_id") or "") for segment in segments if segment.get("document_id")))

    # Resolver relacji dostaje dokładnie te same nagłówki dokumentów, z których
    # segmentacja utworzyła document_id. Dzięki temu nie tworzy drugiego zestawu
    # identyfikatorów na podstawie anonimowego znacznika boundary.
    relation_parts: List[str] = []
    current_doc = ""
    current_block_index: int | None = None
    current_block: List[str] = []

    def flush_relation_block() -> None:
        nonlocal current_block
        if current_block:
            relation_parts.append(" ".join(current_block).strip())
            current_block = []

    for segment in segments:
        doc_id = str(segment.get("document_id") or "")
        block_idx = int(segment.get("block_index", 0) or 0)
        if doc_id and doc_id != current_doc:
            flush_relation_block()
            meta = per_document.get(doc_id) or {}
            label = str(meta.get("document_label") or "input").strip() or "input"
            relation_parts.append(f"--- WCZYTANY PLIK: {label} ---")
            current_doc = doc_id
            current_block_index = block_idx
        elif current_block_index is not None and block_idx != current_block_index:
            flush_relation_block()
            current_block_index = block_idx
        if bool(segment.get("analyzable")):
            text_part = str(segment.get("text") or "").strip()
            if text_part:
                current_block.append(text_part)
        else:
            # Metadane/śródtytuły stanowią barierę dla dziedziczenia mówcy.
            flush_relation_block()
    flush_relation_block()
    relation_text = "\n\n".join(part for part in relation_parts if part)

    # Uzupełnij ewentualne dokumenty z segmentacji, nawet jeśli nie zawierają
    # jawnych metadanych źródłowych.
    for segment in segments:
        doc_id = str(segment.get("document_id") or "")
        if not doc_id:
            continue
        per_document.setdefault(doc_id, {
            "document_id": doc_id,
            "document_index": int(segment.get("document_index", 0)),
            "document_label": "input",
            "document_source": "",
            "document_sources": [],
            "publisher_source": "",
            "quoted_sources": [],
            "image_sources": [],
        })

    all_sources: List[str] = []
    all_images: List[str] = []
    for doc_id in document_ids:
        meta = per_document.get(doc_id) or {}
        all_sources.extend(list(meta.get("document_sources") or []))
        all_images.extend(list(meta.get("image_sources") or []))
    all_sources = _unique(all_sources)
    all_images = _unique(all_images)

    actual_removed = max(0, len(original) - len(analyzable_text))
    cleaning = {
        **dict(cleaning),
        "removed_characters": actual_removed,
        "original_characters": len(original),
        "analyzable_characters": len(analyzable_text),
        "sanitizer_removed_characters_approx": sum(int(x.get("removed_characters_approx", 0) or 0) for x in sanitizer_stats),
        "duplicate_documents_removed": len(duplicate_documents),
        "duplicate_documents": duplicate_documents,
        "empty_documents_ignored": len(empty_documents),
        "empty_documents": empty_documents,
    }

    return PipelineContext(
        original_text=original,
        analyzable_text=analyzable_text,
        relation_text=relation_text,
        segments=segments,
        metadata_segments=metadata,
        cleaning=dict(cleaning),
        document_source=", ".join(all_sources),
        document_sources=all_sources,
        image_sources=all_images,
        document_ids=document_ids,
        document_metadata=per_document,
        document_texts=document_texts,
        document_structured_texts=document_structured_texts,
    )
