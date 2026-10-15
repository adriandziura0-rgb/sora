from __future__ import annotations

"""ER3 / Current: jeden budowniczy encji oraz jedna polityka ról.

Typ encji jest stały dla dokumentu. Rola jest przypisywana wyłącznie w konkretnej
CanonicalRelation. Medium pozostaje źródłem/medium; jawnym nadawcą wypowiedzi
może być osoba, instytucja lub partia, o ile resolver udowodni tę rolę lokalnie.
"""

import re
from typing import Any, Dict, Iterable, List, Optional

from .entity_registry import EntityRegistry, strip_leading_known_medium
from .entity_role_policy import (
    is_public_entity_name,
    role_allows_type,
    role_for_type,
    strip_person_title,
)
from .semantic_entity_filter import validate_entity_candidate

PREFIXES = re.compile(
    r"^(?:zdaniem|według|wg|jak\s+powiedział|jak\s+powiedziała|jak\s+zaznaczył|jak\s+zaznaczyła)\s+",
    re.I,
)


def clean_surface(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip(" ,:;–—-"))
    text = PREFIXES.sub("", text).strip()
    return text


class CanonicalEntityBuilder:
    def __init__(self, document_text: str) -> None:
        self.registry = EntityRegistry(document_text or "")

    def resolve(self, value: Any, expected_type: Optional[str] = None, *, confirmed: bool = False) -> Optional[Dict[str, Any]]:
        raw = clean_surface(value)
        if expected_type == "person":
            raw = strip_person_title(strip_leading_known_medium(raw))
        if not raw or not is_public_entity_name(raw):
            return None

        # Najpierw alias znanej encji. Znana partia, medium lub instytucja nie może
        # zostać ponownie zarejestrowana jako osoba tylko dlatego, że pole oczekiwało mówcy.
        existing = self.registry.resolve(raw, None)
        if existing:
            if not expected_type or existing.get("entity_type") == expected_type:
                return existing
            return None

        verdict = validate_entity_candidate(raw, expected_type)
        if not verdict.accepted:
            return None
        if expected_type == "person" and confirmed:
            return self.registry.resolve_confirmed_person(verdict.cleaned)
        return self.registry.resolve(verdict.cleaned, expected_type)

    def entities(self) -> List[Dict[str, Any]]:
        unique: Dict[str, Dict[str, Any]] = {}
        for entity in self.registry.all():
            eid = str(entity.get("entity_id") or "")
            if not eid or not is_public_entity_name(entity.get("canonical_name")):
                continue
            current = unique.get(eid)
            if not current:
                unique[eid] = dict(entity)
                continue
            current["surface_forms"] = sorted(
                set(current.get("surface_forms", [])) | set(entity.get("surface_forms", []))
            )
        return sorted(unique.values(), key=lambda x: (x.get("entity_type", ""), x.get("canonical_name", "").lower()))

    def cards(self, roles: Iterable[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        usage: Dict[str, Dict[str, Any]] = {}
        role_rows = list(roles or [])
        for role in role_rows:
            value = role.get("value")
            expected = role.get("expected_type")
            role_name = str(role.get("role") or "mentioned")
            entity = self.resolve(value, expected)
            if not entity or not role_allows_type(role_name, str(entity.get("entity_type") or "")):
                continue
            item = usage.setdefault(entity["entity_id"], {**entity, "mentions": 0, "roles": set()})
            item["mentions"] += 1
            item["roles"].add(role_name)

        if not role_rows:
            for entity in self.entities():
                usage[entity["entity_id"]] = {
                    **entity,
                    "mentions": len(entity.get("surface_forms", [])) or 1,
                    "roles": {role_for_type(str(entity.get("entity_type") or ""))},
                }

        out: List[Dict[str, Any]] = []
        for item in sorted(usage.values(), key=lambda x: (-x["mentions"], x["canonical_name"].lower())):
            roles_sorted = sorted(item["roles"])
            out.append({
                "label": "Aktor lub instytucja",
                "level": "R1",
                "role": "CANONICAL_ENTITY",
                "fragment": item["canonical_name"],
                "phrase": item["canonical_name"],
                "entity_id": item["entity_id"],
                "canonical_name": item["canonical_name"],
                "entity_type": item["entity_type"],
                "surface_forms": item.get("surface_forms", []),
                "mentions": item["mentions"],
                "entity_roles": roles_sorted,
                "display_role": roles_sorted[0] if roles_sorted else role_for_type(item["entity_type"]),
                "why": "Nazwa została ujednolicona na podstawie roli użytej w zaakceptowanej relacji.",
                "score": min(10, 2 + item["mentions"]),
                "rank_score": min(10, 2 + item["mentions"]),
            })
        return out


def build_canonical_entities(document_text: str) -> List[Dict[str, Any]]:
    return CanonicalEntityBuilder(document_text).entities()


def _relation_rows(relations: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for card in relations or []:
        rr = card.get("canonical_relation") if isinstance(card, dict) else None
        if isinstance(rr, dict) and not rr.get("rejected"):
            yield rr


def build_canonical_entity_cards_from_relations(relations: List[Dict[str, Any]], document_text: str = "") -> List[Dict[str, Any]]:
    """Publiczna mapa aktorów wyłącznie z entity_id zaakceptowanych relacji.

    Current usuwa ponowne skanowanie całego korpusu. Widok aktorów jest projekcją
    tego samego kontraktu relacji, więc nie może wynaleźć nowej osoby/lokalizacji.
    Parametr ``document_text`` pozostaje tylko dla zgodności API i nie jest analizowany.
    """
    del document_text
    usage: Dict[str, Dict[str, Any]] = {}

    def add(entity_id: Any, name: Any, role: str) -> None:
        eid = clean_surface(entity_id)
        canonical = clean_surface(name)
        if not eid or not canonical:
            return
        entity_type = eid.split(":", 1)[0] if ":" in eid else ""
        if entity_type not in {"person", "institution", "party"}:
            return
        key = eid
        row = usage.setdefault(key, {
            "canonical_name": canonical, "entity_id": eid, "entity_type": entity_type,
            "roles": set(), "mentions": 0, "surface_forms": {canonical},
        })
        row["roles"].add(role)
        row["mentions"] += 1

    for rr in _relation_rows(relations):
        add(rr.get("speaker_entity_id"), rr.get("speaker"), "speaker")
        add(rr.get("target_entity_id"), rr.get("target"), "target")
        add(rr.get("institution_entity_id"), rr.get("institution"), "institution")

    cards: List[Dict[str, Any]] = []
    for row in sorted(usage.values(), key=lambda x: (-x["mentions"], x["canonical_name"].casefold())):
        roles = sorted(row["roles"])
        cards.append({
            "label": "Aktor lub instytucja", "level": "R1", "role": "CANONICAL_ENTITY",
            "fragment": row["canonical_name"], "phrase": row["canonical_name"],
            "entity_id": row["entity_id"], "canonical_name": row["canonical_name"],
            "entity_type": row["entity_type"], "surface_forms": sorted(row["surface_forms"]),
            "mentions": row["mentions"], "entity_roles": roles,
            "display_role": roles[0] if roles else "entity",
            "why": "Current: mapa aktorów jest bezpośrednią projekcją entity_id zaakceptowanych relacji; nie skanuje tekstu ponownie.",
            "score": min(10, 2 + row["mentions"]), "rank_score": min(10, 2 + row["mentions"]),
        })
    return cards

def build_canonical_source_cards_from_relations(relations: List[Dict[str, Any]], document_text: str) -> List[Dict[str, Any]]:
    """Buduje osobne karty dla medium, źródła lokalnego i źródeł dokumentu.

    Current: lista źródeł dokumentu nie jest sklejona w jedną encję. Źródła
    zdjęć pozostają metadanymi relacji i nie trafiają do mapy źródeł treści.
    """
    builder = CanonicalEntityBuilder(document_text)
    usage: Dict[tuple[str, str], Dict[str, Any]] = {}
    for rr in _relation_rows(relations):
        rows = [
            ("medium", clean_surface(rr.get("medium")), clean_surface(rr.get("medium_entity_id")), "medium"),
            ("source", clean_surface(rr.get("source")), clean_surface(rr.get("source_entity_id")), "source"),
        ]
        document_sources = list(rr.get("document_sources") or [])
        if not document_sources and clean_surface(rr.get("document_source")):
            document_sources = [x.strip() for x in str(rr.get("document_source")).split(",") if x.strip()]
        for name in document_sources:
            clean_name = clean_surface(name)
            if clean_name:
                rows.append(("document_source", clean_name, f"document_source:{clean_name.casefold().replace(' ', '_')}", "document_source"))

        for role, name, entity_id, fallback_type in rows:
            if not name:
                continue
            resolved = builder.resolve(name, None) if role != "document_source" else None
            entity_type = str((resolved or {}).get("entity_type") or fallback_type)
            canonical_name = str((resolved or {}).get("canonical_name") or name)
            eid = str((resolved or {}).get("entity_id") or entity_id or f"{entity_type}:{canonical_name.casefold().replace(' ', '_')}")
            key = (eid, role)
            row = usage.setdefault(key, {
                "canonical_name": canonical_name,
                "entity_id": eid,
                "entity_type": entity_type,
                "roles": set(),
                "mentions": 0,
                "surface_forms": set((resolved or {}).get("surface_forms") or [canonical_name]),
            })
            row["roles"].add(role)
            row["mentions"] += 1

    merged: Dict[str, Dict[str, Any]] = {}
    for row in usage.values():
        item = merged.setdefault(row["entity_id"], {**row, "roles": set(), "mentions": 0, "surface_forms": set()})
        item["roles"].update(row["roles"])
        item["surface_forms"].update(row.get("surface_forms") or [])
        item["mentions"] += row["mentions"]

    cards: List[Dict[str, Any]] = []
    for row in sorted(merged.values(), key=lambda x: (-x["mentions"], x["canonical_name"].casefold())):
        roles = sorted(row["roles"])
        cards.append({
            "label": "Aktor lub instytucja",
            "level": "R1",
            "role": "CANONICAL_ENTITY",
            "fragment": row["canonical_name"],
            "phrase": row["canonical_name"],
            "entity_id": row["entity_id"],
            "canonical_name": row["canonical_name"],
            "entity_type": row["entity_type"],
            "surface_forms": sorted(row.get("surface_forms") or {row["canonical_name"]}, key=lambda value: (len(value), value.casefold())),
            "mentions": row["mentions"],
            "entity_roles": roles,
            "display_role": roles[0] if roles else "source",
            "why": "Current: każde źródło dokumentu, źródło lokalne i medium ma osobną kartę; źródło zdjęcia nie jest źródłem treści.",
            "score": min(10, 2 + row["mentions"]),
            "rank_score": min(10, 2 + row["mentions"]),
        })
    return cards

def build_canonical_affiliation_cards_from_relations(relations: List[Dict[str, Any]], document_text: str) -> List[Dict[str, Any]]:
    builder = CanonicalEntityBuilder(document_text)
    roles = [
        {"value": rr.get("affiliation"), "expected_type": "party", "role": "affiliation"}
        for rr in _relation_rows(relations)
        if rr.get("affiliation")
    ]
    if not roles:
        return []
    return [c for c in builder.cards(roles) if c.get("entity_type") == "party"]
