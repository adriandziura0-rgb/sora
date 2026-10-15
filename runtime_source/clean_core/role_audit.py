from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

from .canonical_relation import get_canonical_relation_cards


MEDIA_RX = re.compile(r"\b(?:Gazeta\s+Wyborcza|Gazecie\s+Wyborczej|Wyborczej|TVN24|tvn24\.pl|PAP|Onet|Newsweek|RMF|Polsat|Interia)\b", re.I)
PROGRAM_RX = re.compile(r"\b(?:Fakty\s+po\s+Faktach|Wybory\s+kobiet|Kawa\s+na\s+ławę|Kawa\s+na\s+lawe)\b", re.I)
BAD_ACTOR_RX = re.compile(r"^(?:wi[eę]cej\s+[źz]r[oó]d[łl]o|[źz]r[oó]d[łl]o|czytaj\s+wi[eę]cej|podziel\s+si[eę]|link\s+skopiowany|temat|tagi|gazecie\s+wyborczej|gazeta\s+wyborcza|wyborczej|faktach\s+po\s+faktach|wybory\s+kobiet|kawa\s+na\s+[łl]aw[eę])\b", re.I)
PERSON_RX = re.compile(r"\b[A-ZŁŚŻŹĆŃÓ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+\s+[A-ZŁŚŻŹĆŃÓ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+\b")
ANON_RX = re.compile(r"\b(?:informator|źr[oó]d[łl]o|rozm[oó]wca)\b", re.I)
ACTION_RX = re.compile(r"\b(?:powiedzia[łl]a?|m[oó]wi[łl]a?|oceni[łl]a?|komentuje|skomentowa[łl]a?|podaje|poda[łl]a?|ustali[łl]a?|wyja[śs]ni[łl]a?|podkre[śs]li[łl]a?|zaznaczy[łl]a?|po[śs]redniczy[łl]a?|sprzeda[łl]a?|zaj[ęe][łl]o\s+si[ęe]|rozpracowywa[łl]a?)\b", re.I)
OBJECT_ONLY_RX = re.compile(r"\b(?:Zbigniewa\s+Ziobr[ęe]|Ziobro|Jaros[łl]awie\s+Kaczy[ńn]skim|Jaros[łl]awa\s+Kaczy[ńn]skiego|Pegasus|system\s+Pegasus|Centralnego\s+Biura|Biura\s+Antykorupcyjnego)\b", re.I)


def _clean(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip())


def _rel(card: Dict[str, Any]) -> Dict[str, Any]:
    rel = card.get("statement_relation") or card.get("relacja_wypowiedzi")
    return rel if isinstance(rel, dict) else {}


def _relation_roles(card: Dict[str, Any]) -> Dict[str, str]:
    rel = _rel(card)
    speaker = _clean(rel.get("kto_mowi") or card.get("speaker") or card.get("kto_mowi"))
    target = _clean(rel.get("o_kim") or card.get("target") or card.get("o_kim"))
    claim = _clean(rel.get("co_mowi") or card.get("phrase") or card.get("co_mowi"))
    medium = _clean(rel.get("medium") or card.get("medium"))
    program = _clean(rel.get("program") or card.get("program"))
    role = "speaker_unknown"
    if speaker:
        if ANON_RX.fullmatch(speaker):
            role = "speaker_anonymous"
        elif MEDIA_RX.fullmatch(speaker) or MEDIA_RX.search(speaker):
            role = "source_media_as_speaker"
        elif PERSON_RX.search(speaker):
            role = "speaker_person"
        else:
            role = "speaker_other"
    return {"speaker": speaker, "target": target, "claim": claim, "medium": medium, "program": program, "speaker_role": role}


def _actor_from_top(card: Dict[str, Any]) -> str:
    for item in card.get("items", []) or []:
        if isinstance(item, str) and item.lower().startswith(("aktor:", "mówca:", "kto mówi:")):
            return _clean(item.split(":", 1)[1])
    for k in ("actor", "speaker", "kto_mowi"):
        if card.get(k):
            return _clean(card.get(k))
    rel = _rel(card)
    return _clean(rel.get("kto_mowi"))


def _role_flags(actor: str, card: Dict[str, Any]) -> Dict[str, Any]:
    actor = _clean(actor)
    text = " ".join([_clean(card.get("fragment")), _clean(card.get("phrase")), _clean(card.get("why")), " ".join(str(x) for x in card.get("items", []) or [])])
    is_media = bool(actor and (MEDIA_RX.fullmatch(actor) or MEDIA_RX.search(actor)))
    is_program = bool(actor and (PROGRAM_RX.fullmatch(actor) or PROGRAM_RX.search(actor)))
    is_bad = bool(actor and BAD_ACTOR_RX.search(actor))
    is_object = bool(actor and OBJECT_ONLY_RX.fullmatch(actor))
    is_person = bool(actor and PERSON_RX.fullmatch(actor))
    has_action_near = bool(actor and ACTION_RX.search(text))
    confidence = 80 if is_person and has_action_near else 60 if is_person else 45
    if is_media or is_program or is_bad or is_object:
        confidence = 20
    return {
        "actor": actor,
        "czy_aktor_jest_mowca": bool(is_person and has_action_near and not (is_media or is_program or is_bad or is_object)),
        "czy_aktor_jest_medium": is_media,
        "czy_aktor_jest_programem": is_program,
        "czy_aktor_jest_obiektem": is_object,
        "czy_aktor_jest_smieciem_meta": is_bad,
        "pewnosc_aktora": confidence,
    }


def build_role_audit_cards(sections: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    relations = get_canonical_relation_cards(sections)
    top_units = (
        sections.get("t2_top_meaning_units", [])
        or sections.get("public_top", [])
        or []
    )
    agency = sections.get("agency_map", []) or []
    roles = [_relation_roles(c) for c in relations if isinstance(c, dict)]
    role_counts = Counter(r["speaker_role"] for r in roles)
    media_as_speaker = [r for r in roles if r["speaker_role"] == "source_media_as_speaker"]
    no_speaker = [r for r in roles if not r["speaker"]]
    with_program_as_claim = [r for r in roles if r["claim"] and PROGRAM_RX.search(r["claim"])]
    target_as_speaker = [r for r in roles if r.get("speaker") and r.get("target") and re.sub(r"[^a-ząćęłńóśźż]+", " ", r["speaker"].lower()).strip() in {"jarosławie kaczyńskim", "jarosława kaczyńskiego", "zbigniewa ziobrę", "zbigniewa ziobre"}]

    cards: List[Dict[str, Any]] = []
    cards.append({
        "label": "AUDIT_ROLE_SUMMARY",
        "level": "INFO",
        "role": "ROLE_AUDIT",
        "phrase": "audyt ról relacji",
        "fragment": "",
        "why": (
            "Audyt aktywnego runtime sprawdza, czy aplikacja rozdziela role: osoba mówiąca, informator, medium, program, obiekt wypowiedzi i sprawca działania. "
            f"Relacje: {len(relations)}; mówcy-osoby: {role_counts.get('speaker_person', 0)}; informatorzy: {role_counts.get('speaker_anonymous', 0)}; "
            f"media jako mówca do kontroli: {len(media_as_speaker)}; obiekt jako mówca do kontroli: {len(target_as_speaker)}; bez mówcy: {len(no_speaker)}; program w polu 'co mówi': {len(with_program_as_claim)}."
        ),
        "score": float(len(relations)),
        "rank_score": float(len(relations)),
        "evidence": {
            "role_counts": dict(role_counts),
            "relacje_wypowiedzi": len(relations),
            "media_jako_mowca_do_kontroli": len(media_as_speaker),
            "program_jako_tresc_do_kontroli": len(with_program_as_claim),
            "brak_mowcy": len(no_speaker),
            "obiekt_jako_mowca_do_kontroli": len(target_as_speaker),
        },
    })

    suspicious_top = []
    confident_top = []
    for c in top_units:
        actor = _actor_from_top(c)
        flags = _role_flags(actor, c)
        if flags["pewnosc_aktora"] < 50:
            suspicious_top.append((c, flags))
        else:
            confident_top.append((c, flags))
    examples = []
    for c, flags in suspicious_top[:5]:
        examples.append({"aktor": flags.get("actor"), "fraza": _clean(c.get("phrase"))[:160], "powod": {k:v for k,v in flags.items() if k != "actor"}})
    cards.append({
        "label": "AUDIT_ROLE_TOP_ACTOR_CONTROL",
        "level": "INFO",
        "role": "ROLE_AUDIT",
        "phrase": "kontrola aktora TOP",
        "fragment": "",
        "why": (
            f"TOP jednostki: {len(top_units)}; aktor pewny: {len(confident_top)}; aktor do kontroli: {len(suspicious_top)}. "
            "Kontrola pilnuje, żeby medium, program, obiekt sprawy albo metadane nie zastępowały osoby mówiącej/sprawcy."
        ),
        "score": float(max(0, len(top_units) - len(suspicious_top))),
        "rank_score": float(max(0, len(top_units) - len(suspicious_top))),
        "evidence": {
            "top_jednostki": len(top_units),
            "aktor_pewny": len(confident_top),
            "aktor_do_kontroli": len(suspicious_top),
            "przyklady_do_kontroli": examples,
        },
    })

    agency_actions = []
    for c in agency:
        txt = " ".join([_clean(c.get("phrase")), _clean(c.get("fragment")), _clean(c.get("why"))])
        m = ACTION_RX.search(txt)
        if m:
            agency_actions.append(_clean(c.get("phrase") or m.group(0)))
    cards.append({
        "label": "AUDIT_ROLE_AGENCY_CONTROL",
        "level": "INFO",
        "role": "ROLE_AUDIT",
        "phrase": "sprawczość aktorów",
        "fragment": "",
        "why": (
            f"Mapa sprawczości ma {len(agency)} kart, w tym {len(agency_actions)} z jawnym czasownikiem działania/wypowiedzi. "
            "Docelowo każda mocna jednostka powinna dawać układ: aktor → czynność → obiekt → skutek/temat."
        ),
        "score": float(len(agency_actions)),
        "rank_score": float(len(agency_actions)),
        "evidence": {
            "mapa_sprawczosci": len(agency),
            "jawne_dzialania": len(agency_actions),
            "przyklady": agency_actions[:8],
        },
    })
    return cards
