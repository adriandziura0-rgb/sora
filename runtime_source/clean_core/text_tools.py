from __future__ import annotations

import re
from typing import Any, Dict, List

WORD_RX = re.compile(r"\b[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\b", re.I | re.U)
SENTENCE_RX = re.compile(r"[^.!?\n]+(?:[.!?]+|$)", re.U)
QUESTION_RX = re.compile(r"\?")
NEGATION_RX = re.compile(r"\b(?:nie|nigdy|żaden|zadna|żadna|bez|ani)\b", re.I)
MODAL_RX = re.compile(r"\b(?:musi|muszą|powinien|powinni|trzeba|należy|nie wolno|może|mogą|warto|konieczne|wymaga)\b", re.I)
CONNECTOR_RX = re.compile(r"\b(?:ale|jednak|choć|chociaż|natomiast|ponieważ|dlatego|tymczasem|zamiast|albo|lecz)\b", re.I)
INTENSIFIER_RX = re.compile(r"\b(?:bardzo|absolutnie|całkowicie|totalnie|najbardziej|największy|najgorszy|bezprecedensowy|nigdy wcześniej)\b", re.I)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def split_sentences(text: str) -> List[Dict[str, Any]]:
    raw = text or ""
    rows: List[Dict[str, Any]] = []
    for idx, match in enumerate(SENTENCE_RX.finditer(raw), start=1):
        value = match.group(0).strip()
        if value:
            tokens = WORD_RX.findall(value)
            rows.append({
                "idx": idx,
                "start": match.start(),
                "end": match.end(),
                "text": value,
                "tokens": len(tokens),
                "chars": len(value),
                "has_question": "?" in value,
            })
    if not rows and raw.strip():
        value = raw.strip()
        rows.append({"idx": 1, "start": 0, "end": len(raw), "text": value, "tokens": len(WORD_RX.findall(value)), "chars": len(value), "has_question": "?" in value})
    return rows


def build_text_overview(text: str) -> Dict[str, Any]:
    cleaned = normalize_whitespace(text)
    tokens = WORD_RX.findall(cleaned)
    sentences = split_sentences(cleaned)
    unique_tokens = {t.lower() for t in tokens}
    counts = {
        "characters": len(cleaned),
        "tokens": len(tokens),
        "unique_tokens": len(unique_tokens),
        "sentences": len(sentences),
        "questions": len(QUESTION_RX.findall(cleaned)),
        "negations": len(NEGATION_RX.findall(cleaned)),
        "modal_markers": len(MODAL_RX.findall(cleaned)),
        "connectors": len(CONNECTOR_RX.findall(cleaned)),
        "intensifiers": len(INTENSIFIER_RX.findall(cleaned)),
    }
    return {
        "schema": "text_overview_current_v1",
        "counts": counts,
        "avg_sentence_tokens": round(counts["tokens"] / max(1, counts["sentences"]), 2),
        "lexical_richness": round(counts["unique_tokens"] / max(1, counts["tokens"]), 3),
        "sentences": sentences,
    }


def stable_api_shape() -> Dict[str, Any]:
    return {
        "schema": "api_shape_current_v1",
        "stable_fields": [
            "ok", "stage", "summary", "sections", "p0_summary",
            "linguistic_profile", "analysis_quality", "text_overview", "analysis_contract",
        ],
        "rule": "To jest jedyny aktualny kontrakt pomocniczy rdzenia analizy.",
    }
