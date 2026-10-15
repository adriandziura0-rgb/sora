"""Klasyfikacja rekordów bazy na artykuły i pliki techniczne.

Moduł nie usuwa żadnych rekordów. Służy wyłącznie do tego, aby statystyki,
porównania redakcyjne i matcher „tej samej sprawy” nie traktowały metadanych,
surowego HTML ani indeksów jako osobnych artykułów.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any, Dict

ARTICLE_KIND = "article"
SUPPORT_KIND = "support"

# Nazwy typowe dla eksportera artykułów i plików obsługowych.
_SUPPORT_BASENAMES = {
    "metadata.json",
    "raw.html",
    "raw.htm",
    "index.csv",
    "index.html",
    "index.htm",
    "processed_urls.json",
    "urls.json",
    "manifest.json",
    "audit.json",
    "audyt.json",
}
_ARTICLE_BASENAMES = {"artykul.txt", "artykuł.txt", "article.txt"}
_TEXT_ARTICLE_EXTENSIONS = {".txt", ".md", ".markdown"}

# Rozpoznaje strukturalny eksport pojedynczego artykułu niezależnie od nazwy.
_STRUCTURED_ARTICLE_RE = re.compile(
    r"(?ims)^\s*TYTUŁ\s*:.+?^\s*(?:URL|CANONICAL URL)\s*:\s*https?://.+?(?:^\s*TREŚĆ\s*:|\n-{10,}\s*\n)",
)


def _clean_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def document_basename(document: Dict[str, Any]) -> str:
    path = _clean_path(document.get("relative_path") or document.get("filename"))
    if path:
        return PurePosixPath(path).name
    return str(document.get("filename") or "")


def is_article_document(document: Dict[str, Any]) -> bool:
    """Konserwatywnie określa, czy rekord reprezentuje właściwy artykuł.

    Reguły są celowo proste i stabilne dla istniejących kolektorów:
    * ``artykul.txt`` / ``artykuł.txt`` / ``article.txt`` -> artykuł,
    * zwykły samodzielny TXT/Markdown -> artykuł,
    * znane pliki techniczne -> plik pomocniczy,
    * JSON/HTML/CSV/LOG domyślnie są pomocnicze, chyba że ich treść ma
      jednoznaczny nagłówek strukturalnego eksportu artykułu.
    """
    basename = document_basename(document).casefold()
    extension = str(document.get("extension") or PurePosixPath(basename).suffix or "").casefold()

    if basename in _SUPPORT_BASENAMES:
        return False
    if basename in _ARTICLE_BASENAMES:
        return True

    text = str(document.get("_text_content") or document.get("text_content") or "")
    if text and _STRUCTURED_ARTICLE_RE.search(text[:12000]):
        return True

    if extension in _TEXT_ARTICLE_EXTENSIONS:
        # Oczywiste pliki dokumentacyjne/logistyczne nie są artykułami.
        stem = PurePosixPath(basename).stem.casefold()
        if stem in {"readme", "instrukcja", "license", "licence", "wersja", "changelog"}:
            return False
        return True
    return False


def document_kind(document: Dict[str, Any]) -> str:
    return ARTICLE_KIND if is_article_document(document) else SUPPORT_KIND


def split_article_support_counts(documents: Any) -> tuple[int, int]:
    articles = 0
    support = 0
    for document in documents:
        if is_article_document(document):
            articles += 1
        else:
            support += 1
    return articles, support
