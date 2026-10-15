from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from .canonical_relation import get_canonical_relation_cards
from .segmentation import split_sentences

SCHEMA = "semantic_effectiveness_v2"

MEDIA_RX = re.compile(r"\b(TVN24|PAP|RMF\s*FM?|Radio\s*ZET|Polsat|Onet|Interia|Gazeta\.pl|WP\.pl|Shutterstock)\b", re.I)
PARTY_RX = re.compile(r"\b(KO|PiS|Konfederacj\w*|Lewic\w*|Platform\w*|Koalicj\w*)\b", re.I)
PERSON_RX = re.compile(r"\b([A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż-]+\s+[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż-]+)\b")
INSTITUTION_RX = re.compile(r"\b(Sejm|Senat|komisj\w*|rząd|rzad|sąd|sad|prokuratur\w*|Trybunał|Trybunal|ministerstw\w*)\b", re.I)

FRAME_SPECS: Dict[str, Dict[str, Any]] = {
    "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW": {
        "phrase": "inwigilacja opozycji kontra uczciwość wyborów",
        "why": "P3: lokalny dowód łączy inwigilację przeciwników politycznych z wpływem na wolność, równość lub uczciwość procesu wyborczego.",
        "score": 9.7, "specificity": 1.0,
    },
    "SEM_FRAME_INWIGILACJA_KONTRA_STANDARDY_DEMOKRATYCZNE": {
        "phrase": "inwigilacja państwa kontra standardy demokratyczne",
        "why": "P3: lokalny dowód zestawia inwigilację obywateli/polityków z kryzysem demokracji, praworządnością lub demokratyczną kontrolą państwa.",
        "score": 9.3, "specificity": 0.95,
    },
    "SEM_FRAME_INWIGILACJA_JAKO_NARZEDZIE_WALKI_POLITYCZNEJ": {
        "phrase": "inwigilacja jako narzędzie walki politycznej",
        "why": "P3: lokalny dowód łączy inwigilację z niszczeniem lub zwalczaniem niewygodnych przeciwników politycznych, bez dopowiadania wpływu na uczciwość wyborów.",
        "score": 8.9, "specificity": 0.9,
    },
    "SEM_FRAME_ODPOWIEDZIALNOSC_URZEDU_KONTRA_DYSTANSOWANIE": {
        "phrase": "odpowiedzialność urzędu kontra dystansowanie się",
        "why": "P3: osoba pełniąca wysoką funkcję jest konfrontowana z odpowiedzialnością, a lokalny dowód zawiera dystansowanie się przez brak wiedzy, pamięci lub udziału.",
        "score": 8.6, "specificity": 0.86,
    },
    "SEM_FRAME_POWAGA_KONTRA_SPEKTAKL": {
        "phrase": "powaga państwa kontra spektakl polityczny",
        "why": "P3: lokalny fragment jawnie zestawia instytucjonalną/proceduralną powagę ze spektaklem, cyrkiem, hucpą lub grą polityczną.",
        "score": 8.4, "specificity": 0.82,
    },
    "SEM_FRAME_ODPOWIEDZIALNOSC_KONTRA_UNIKANIE": {
        "phrase": "odpowiedzialność kontra unikanie",
        "why": "P3: lokalny fragment zestawia wezwanie do odpowiedzialności/przesłuchania z odmową, unikaniem lub niestawiennictwem.",
        "score": 8.2, "specificity": 0.76,
    },
    "SEM_FRAME_LEGALNOSC_KONTRA_GRA_POLITYCZNA": {
        "phrase": "legalność/procedura kontra gra polityczna",
        "why": "P3: lokalny fragment zestawia legalność/procedurę z jawną grą, hucpą, atakiem, sporem lub konfliktem politycznym.",
        "score": 7.9, "specificity": 0.72,
    },
    "SEM_FRAME_INSTYTUCJA_KONTRA_OSOBA": {
        "phrase": "instytucja kontra osoba",
        "why": "P3: lokalny fragment pokazuje instytucję i konkretną osobę w rzeczywistym konflikcie, odmowie lub unikaniu odpowiedzialności. To rama ogólna i przegrywa z ramami specyficznymi.",
        "score": 6.6, "specificity": 0.35,
    },
}


def _clean(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip())


def _frag(text: str, start: int, end: int, radius: int = 180) -> str:
    if start < 0 or end <= start:
        return _clean(text[:420])
    return _clean(text[max(0, start - radius): min(len(text), end + radius)])


def _card(label: str, level: str, role: str, fragment: str, phrase: str, why: str, *, start: int = -1, end: int = -1, score: float = 6.0, relevance: str = "high", requires_review: bool = True, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "label": label,
        "level": level,
        "analysis_level": level,
        "analysis_level_name": "audyt jakości semantycznej",
        "role": role,
        "fragment": _clean(fragment),
        "phrase": _clean(phrase),
        "start": int(start),
        "end": int(end),
        "confidence": "medium",
        "pattern_confidence": "medium",
        "interpretation_confidence": "medium",
        "score": float(score),
        "rank_score": float(score),
        "analytical_relevance": relevance,
        "requires_review": bool(requires_review),
        "why": why,
        "source": SCHEMA,
        "status_pl": "Audyt jakości semantycznej",
    }
    if extra:
        d.update(extra)
    return d


def _source_role(name: str) -> str:
    n = _clean(name)
    if not n:
        return "nieustalone"
    if re.fullmatch(r"TVN24|RMF\s*FM?|Radio\s*ZET|Polsat|Onet|Interia|Gazeta\.pl|WP\.pl", n, re.I):
        return "medium"
    if re.fullmatch(r"PAP", n, re.I):
        return "agencja"
    if "PAP" in n and PERSON_RX.search(n):
        return "autor / źródło agencyjne"
    if PARTY_RX.search(n):
        return "partia / klub"
    if INSTITUTION_RX.search(n):
        return "instytucja"
    if PERSON_RX.search(n):
        return "aktor / mówca"
    return "źródło / encja"


def build_source_role_cards(text: str, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
    del text
    buckets: Dict[str, Counter[str]] = defaultdict(Counter)
    key_roles = (
        ("actor_map", "aktor / mówca"),
        ("source_map", "źródło / medium"),
        ("affiliation_map", "partia / afiliacja"),
    )
    for key, fallback_role in key_roles:
        for card in sections.get(key, []) or []:
            name = _clean(card.get("phrase") or card.get("canonical_name") or card.get("fragment"))
            if not name or len(name) > 100:
                continue
            entity_type = _clean(card.get("entity_type"))
            role = {
                "person": "aktor / mówca",
                "institution": "instytucja",
                "party": "partia / afiliacja",
                "medium": "medium",
                "source": "źródło",
                "document_source": "źródło dokumentu",
                "image_source": "źródło zdjęcia",
                "product": "obiekt / produkt",
            }.get(entity_type, fallback_role)
            buckets[role][name] += 1

    cards: List[Dict[str, Any]] = []
    for role, counter in sorted(buckets.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        items = counter.most_common(12)
        phrase = f"{role}: " + ", ".join(f"{name} ({count})" for name, count in items[:6])
        cards.append(_card(
            "SEM_SOURCE_ROLE_CLASSIFIER",
            "R1",
            "SEMANTIC_SOURCE_ROLE",
            "",
            phrase,
            "Current: podsumowanie ról nie wykonuje własnego NER; korzysta wyłącznie z publicznych map zaakceptowanych relacji.",
            score=6.6 + min(1.8, sum(counter.values()) * 0.15),
            requires_review=False,
            extra={"items": [f"{name} · {count}" for name, count in items], "semantic_role": role},
        ))
    return cards[:12]


def build_relation_quality_cards(text: str, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
    relations = get_canonical_relation_cards(sections)
    if not relations:
        return [_card(
            "SEM_RELATION_MISSING",
            "R2",
            "SEMANTIC_RELATION_QUALITY",
            text[:360],
            "brak relacji kto mówi → o kim → co mówi",
            "Nie znaleziono stabilnych relacji wypowiedzi. Jeżeli tekst zawiera cytaty, trzeba sprawdzić atrybucję ręcznie.",
            score=5.4,
            relevance="medium",
            requires_review=True,
        )]
    by_speaker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    complete = 0
    for r in relations:
        rel = r.get("statement_relation") or {}
        speaker = _clean(rel.get("kto_mowi") or r.get("speaker") or "nieustalony")
        phrase = _clean(rel.get("co_mowi") or r.get("phrase"))
        target = _clean(rel.get("o_kim") or r.get("target"))
        if speaker and speaker != "nieustalony" and phrase:
            complete += 1
        by_speaker[speaker].append(r)
    cards = []
    for speaker, rows in sorted(by_speaker.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:8]:
        examples = []
        targets = Counter()
        for r in rows:
            rel = r.get("statement_relation") or {}
            if rel.get("o_kim"):
                targets[_clean(rel.get("o_kim"))] += 1
            if len(examples) < 4:
                examples.append(_clean(rel.get("co_mowi") or r.get("phrase") or r.get("fragment"))[:140])
        target_part = ", ".join(f"{t} ({n})" for t, n in targets.most_common(3)) or "cel nieustalony"
        cards.append(_card(
            "SEM_SPEAKER_RELATION_SUMMARY",
            "R2",
            "SEMANTIC_RELATION_QUALITY",
            rows[0].get("fragment", text[:360]),
            f"{speaker} → {target_part}",
            "Aktywny audyt agreguje wypowiedzi według nadawcy. To jest rdzeń analizy medialnej: kto mówi, o kim mówi i co przypisuje drugiej stronie.",
            start=int(rows[0].get("start", -1) or -1),
            end=int(rows[0].get("end", -1) or -1),
            score=7.2 + min(1.4, len(rows) * 0.2),
            extra={"items": examples, "speaker": speaker, "target": target_part},
        ))
    cards.insert(0, _card(
        "SEM_RELATION_COMPLETENESS",
        "R2",
        "SEMANTIC_RELATION_QUALITY",
        text[:500],
        f"pełne relacje: {complete}/{len(relations)}",
        "Kontrola jakości relacji: relacja jest mocna dopiero wtedy, gdy ma nadawcę i treść wypowiedzi; cel wypowiedzi zwiększa jakość, ale może wymagać ręcznej kontroli.",
        score=6.2 + min(2.0, complete / max(1, len(relations)) * 2.0),
        requires_review=complete < len(relations),
        extra={"items": [f"pełne: {complete}", f"wszystkie: {len(relations)}"]},
    ))
    return cards


def build_claim_status_quality_cards(text: str, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
    claims = sections.get("fact_opinion_quote", []) or []
    if not claims:
        return []
    counts = Counter(_clean(c.get("claim_type_pl") or c.get("claim_type") or "inne") for c in claims)
    items = [f"{k}: {v}" for k, v in counts.most_common()]
    ambiguous = [c for c in claims if c.get("requires_review") or c.get("claim_type") in {"ocena_redakcyjna", "cytat"}]
    cards = [_card(
        "SEM_CLAIM_STATUS_SUMMARY",
        "R2",
        "SEMANTIC_CLAIM_STATUS",
        text[:500],
        ", ".join(items[:8]),
        "Aktywny audyt porządkuje status twierdzeń: fakt opisowy, opinia/cytat, źródło/medium i ocena wymagająca kontroli. To chroni przed traktowaniem opinii jako faktu redakcyjnego.",
        score=7.0,
        requires_review=bool(ambiguous),
        extra={"items": items},
    )]
    if ambiguous:
        cards.append(_card(
            "SEM_CLAIM_REVIEW_NEEDED",
            "R2",
            "SEMANTIC_CLAIM_STATUS",
            ambiguous[0].get("fragment", text[:360]),
            f"do kontroli: {len(ambiguous)}",
            "Część twierdzeń jest cytatem, możliwą oceną redakcyjną albo opinią z niepełną atrybucją. System oznacza je jako materiał do ręcznego sprawdzenia, nie jako pewny fakt.",
            start=int(ambiguous[0].get("start", -1) or -1),
            end=int(ambiguous[0].get("end", -1) or -1),
            score=7.4,
            requires_review=True,
            extra={"items": [_clean(c.get("phrase") or c.get("fragment"))[:120] for c in ambiguous[:8]]},
        ))
    return cards


def build_p0_to_p1_gate_cards(text: str, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
    p0 = sections.get("p0_raw_signals", []) or []
    p1 = sections.get("p1_candidates", []) or []
    p2 = sections.get("p2_techniques", []) or []
    p0_phrases = Counter(_clean(c.get("phrase") or c.get("fraza")).lower() for c in p0 if _clean(c.get("phrase") or c.get("fraza")))
    marker_count = sum(p0_phrases.values())
    strong_count = len(p1) + len(p2)
    cards = [_card(
        "SEM_P0_TO_P1_GATE_SUMMARY",
        "R1",
        "SEMANTIC_P0_P1_GATE",
        text[:520],
        f"P0={marker_count}; P1/P2={strong_count}",
        "Aktywny audyt kontroluje awans: P0 jest tylko sygnałem. P1/P2 ma sens dopiero przy pełnej strukturze, istotności i kontekście argumentacyjnym.",
        score=6.8 if marker_count else 5.8,
        requires_review=marker_count > 0,
        extra={"items": [f"{p}: {n}" for p, n in p0_phrases.most_common(10)]},
    )]
    if p0_phrases.get("albo") and not any("dychot" in _clean(c.get("label")).lower() for c in p1 + p2):
        cards.append(_card(
            "SEM_ALBO_MARKER_BLOCKED",
            "R1",
            "SEMANTIC_P0_P1_GATE",
            text[:420],
            "albo = marker, nie automatyczna fałszywa dychotomia",
            "W tekście jest marker „albo”, ale bez pełnej konstrukcji wymuszającej wybór system zostawia go jako sygnał P0/R0, nie potwierdzoną technikę.",
            score=7.0,
            requires_review=False,
        ))
    return cards


_TITLE_CONTEXT_RE = re.compile(
    r"\b(?:podcast\w*|program\w*|audycj\w*|wideopodcast\w*|cykl\w*)\b[^.!?]{0,70}?[\"„](?P<title>[^\"”]{1,80})[\"”]"
    r"|\b(?:w|we)\s+[\"„](?P<title2>[A-ZĄĆĘŁŃÓŚŹŻ][^\"”]{1,70})[\"”]",
    re.I,
)
_MEDIA_FALSE_FRIEND_RE = re.compile(
    # Maskujemy wyłącznie pełną nazwę medium. Current maskowało również samotne
    # „Wyborczej”, co usuwało prawdziwy dowód z fraz „walka wyborcza”,
    # „kampania wyborcza” i powodowało false negative P3.
    r"\b(?:Gazeta\s+Wyborcza|Gazety\s+Wyborczej|Gazecie\s+Wyborczej)\b",
    re.I,
)
_DISCOURSE_LINK_RE = re.compile(
    r"^(?:dlatego|jednak|tymczasem|natomiast|w\s+efekcie|z\s+tego\s+powodu|co\s+więcej|w\s+związku\s+z\s+tym)\b",
    re.I,
)

_SURVEILLANCE_RE = re.compile(r"\b(?:inwigil\w*|podsłuch\w*|podsluch\w*|Pegasus\w*)\b", re.I)
_POLITICAL_TARGET_RE = re.compile(
    r"\b(?:opozycj\w*|konkurencj\w*\s+polityczn\w*|sztab\w*(?:\s+(?:wyborcz\w*|opozycj\w*))?|"
    r"parti\w*\s+opozycyjn\w*|osob\w*\s+krytyczn\w*\s+wobec\s+rządu|polityk\w*\s+opozycj\w*|"
    r"niewygodn\w*\s+przeciwnik\w*)\b",
    re.I,
)
_ELECTION_RE = re.compile(r"\b(?:wybory|wyborów|wyborach|wyborcz\w*|kampani\w*)\b", re.I)
_ELECTION_FAIRNESS_RE = re.compile(
    r"\b(?:uczciw\w*|wiarygodno\w*|nierówn\w*\s+szans\w*|równ\w*\s+szans\w*|"
    r"przewag\w*\s+wyborcz\w*|wpływ\w*\s+(?:na\s+)?(?:wynik\w*\s+)?(?:wybor\w*|kampani\w*)|"
    r"wygryw\w*\s+(?:polityczn\w*\s+batali\w*|wybor\w*)|podważa\w*\s+uczciwo\w*|"
    r"zamach\w*\s+na\s+woln\w*\s+wybor\w*|uderz\w*\s+(?:w|na)\s+(?:woln\w*\s+)?wybor\w*|"
    r"woln\w*\s+wybor\w*)\b",
    re.I,
)
_INSTITUTION_RE = re.compile(r"\b(?:komisj\w*|Sejm\w*|Senat\w*|sąd\w*|sad\w*|prokuratur\w*|ministerstw\w*|rząd\w*|rzad\w*|instytucj\w*)\b", re.I)
_PERSON_LOCAL_RE = re.compile(r"\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+)\b")
_RESPONSIBILITY_RE = re.compile(r"\b(?:odpowiedzialn\w*|rozlicz\w*|przesłuch\w*|przesluch\w*|wezwa\w*|ukar\w*|doprowadz\w*|żąda\w*\s+wyjaśnień|zada\w*\s+wyjaśnień)\b", re.I)
_AVOIDANCE_RE = re.compile(r"\b(?:unika\w*|odm[oó]wi\w*|niestaw\w*|nie\s+stawi\w*|odwleka\w*|przeciąg\w*|przeciag\w*|klucz\w*|zasłania\w*\s+się)\b", re.I)
_ACCOUNTABILITY_PROCEDURE_RE = re.compile(
    r"\b(?:komisj\w*|[śs]wiadk\w*|przes[łl]uch\w*|wezw\w*|ukaran\w*|"
    r"doprowadz\w*|stawien\w*\s+si[ęe]|przyrzeczeni\w*)\b",
    re.I,
)
_SERIOUS_RE = re.compile(r"\b(?:powag\w*|państw\w*|panstw\w*|komisj\w*|procedur\w*)\b", re.I)
_STRONG_SERIOUS_RE = re.compile(r"\b(?:powag\w*|szacun\w*\s+do\s+(?:państw\w*|panstw\w*|prawa)|zaufani\w*\s+obywatel\w*\s+do\s+instytucj\w*|lekceważ\w*\s+(?:przepis\w*|procedur\w*|instytucj\w*))\b", re.I)
_SPECTACLE_RE = re.compile(
    r"\b(?:cyrk\w*|spektakl\w*|błazenad\w*|blazenad\w*|hucp\w*\s+polityczn\w*|"
    r"gra\s+polityczn\w*|igrzysk\w*\s+polityczn\w*|kotka\s+i\s+myszk\w*)\b",
    re.I,
)

_DEMOCRACY_RE = re.compile(
    r"\b(?:kryzys\w*\s+demokrac\w*|demokrac\w*|praworządno\w*|praworzadno\w*|"
    r"państw\w*\s+prawa|panstw\w*\s+prawa|demokratyczn\w*\s+(?:kontrol\w*|standard\w*|gwaranc\w*))\b", re.I,
)
_POLITICAL_WEAPON_RE = re.compile(
    r"\b(?:niszcz\w*\s+niewygodn\w*\s+przeciwnik\w*|prób\w*\s+zniszcz\w*\s+.*?przeciwnik\w*|"
    r"narzędz\w*\s+walki\s+polityczn\w*|system\w*\s+działani\w*\s+.*?niszcz\w*\s+.*?przeciwnik\w*|"
    r"uderz\w*\s+w\s+(?:opozycj\w*|przeciwnik\w*))\b", re.I,
)
# Current: jawny cel polityczny/wyborczy jest samodzielnym dowodem funkcji
# inwigilacji. Poprzednia wersja wymagała dodatkowo słów typu „niszczyć
# przeciwników”, przez co naturalne zdania „używać w walce wyborczej i
# politycznej” oraz „wykorzystać do celów politycznych” były false negative.
_POLITICAL_PURPOSE_RE = re.compile(
    r"\b(?:"
    r"(?:używ\w*|uzyw\w*|wykorzyst\w*|stosow\w*)[^.!?]{0,90}?"
    r"(?:w\s+walce\s+(?:wyborcz\w*(?:\s+(?:oraz|i)\s+polityczn\w*)?|polityczn\w*(?:\s+(?:oraz|i)\s+wyborcz\w*)?)|"
    r"do\s+cel\w*\s+(?:polityczn\w*|wyborcz\w*))|"
    r"(?:walka|walce|walki)\s+(?:wyborcz\w*|polityczn\w*)|"
    r"cel\w*\s+(?:polityczn\w*|wyborcz\w*)"
    r")\b",
    re.I,
)
_HIGH_OFFICE_RE = re.compile(
    r"\b(?:druga\s+osoba\s+w\s+państw\w*|marszał\w*\s+Sejm\w*|premier\w*|minister\w*|prezydent\w*|"
    r"szef\w*\s+(?:służb\w*|resort\w*|urzędu|urzedu)|wysok\w*\s+funkcj\w*|odpowiedzialn\w*\s+za)\b", re.I,
)
_NAMED_HIGH_OFFICE_RE = re.compile(
    r"\b(?:druga\s+osoba\s+w\s+państw\w*|marszał\w*\s+Sejm\w*|premier\w*|minister\w*|"
    r"prezydent\w*|szef\w*\s+(?:służb\w*|resort\w*|urzędu|urzedu)|wysok\w*\s+funkcj\w*)\b",
    re.I,
)
_NON_PERSON_PROPER_NAME_RE = re.compile(
    r"\b(?:Zjednoczon\w*|Królestw\w*|Krolestw\w*|Republik\w*|Komisj\w*|Europejsk\w*|"
    r"Uni\w*|Trybuna[łl]\w*|S[ąa]d\w*|Organizacj\w*|Ministerstw\w*)\b",
    re.I,
)
_DISTANCING_RE = re.compile(
    r"\b(?:nie\s+(?:wiem|wie|wiedzia\w*|pamięta\w*|pamieta\w*|uczestnicz\w*|zna\w*)|"
    r"nic\s+nie\s+(?:wie|pamięta\w*|pamieta\w*|uczestnicz\w*)|nie\s+był\w*\s+zaangażowan\w*)\b", re.I,
)
_GENERIC_CONFLICT_RE = re.compile(
    r"\b(?:żąda\w*|zada\w*|oskarż\w*|kwestion\w*|konflikt\w*|"
    r"sp[oó]r(?:u|em|ze|y|ów|ow|ach|ami)?)\b", re.I,
)
_LEGAL_RE = re.compile(r"\b(?:legalno\w*|prawidłowo\w*|prawidlowo\w*|immunitet\w*|sąd\w*|sad\w*|procedur\w*)\b", re.I)
_POLITICAL_CONFLICT_RE = re.compile(
    r"\b(?:gra\s+polityczn\w*|atak\s+polityczn\w*|sp[oó]r\s+polityczn\w*|"
    r"konflikt\s+polityczn\w*|hucp\w*\s+polityczn\w*|wykorzyst\w*\s+polityczn\w*|"
    r"polityczn\w*\s+(?:gr\w*|atak\w*|sp[oó]r\w*|konflikt\w*|hucp\w*))\b",
    re.I,
)


def _mask_preserve(text: str, regex: re.Pattern[str]) -> str:
    return regex.sub(lambda m: " " * len(m.group(0)), text)


def _semantic_scan_text(text: str) -> str:
    """Maskuje span tytułu/medium, ale zachowuje długość i offsety.

    Nazwa programu typu ``Wybory kobiet`` pozostaje dostępna w warstwie R,
    lecz jej tokeny nie mogą udawać dowodu semantycznego P3.
    """
    masked = _mask_preserve(text, _MEDIA_FALSE_FRIEND_RE)
    masked = _mask_preserve(masked, _TITLE_CONTEXT_RE)
    return masked


def _local_semantic_windows(text: str) -> List[Dict[str, Any]]:
    """Buduje lokalne okna P3 z zachowaniem granic akapitów.

    Standardowe okno obejmuje maksymalnie trzy sąsiednie zdania tego samego
    akapitu. Przejście przez granicę akapitu jest możliwe wyłącznie przy
    jawnym łączniku dyskursowym w następnym akapicie. Dzięki temu P3 nie skleja
    Pegasusa z przypadkową wzmianką o wyborach kilkadziesiąt zdań dalej.
    """
    raw = str(text or "")
    normalized = _clean(raw)
    paragraphs = [p for p in re.split(r"\n\s*\n+", raw) if _clean(p)] or [raw]
    result: List[Dict[str, Any]] = []
    paragraph_sentences: List[List[Dict[str, Any]]] = []
    cursor = 0
    for p_idx, paragraph in enumerate(paragraphs):
        p_clean = _clean(paragraph)
        p_start = normalized.find(p_clean, cursor)
        if p_start < 0:
            p_start = cursor
        local_cursor = p_start
        rows: List[Dict[str, Any]] = []
        for s_idx, sentence in enumerate(split_sentences(paragraph)):
            sent = _clean(sentence)
            if not sent:
                continue
            start = normalized.find(sent, local_cursor)
            if start < 0:
                start = local_cursor
            end = min(len(normalized), start + len(sent))
            rows.append({"text": sent, "start": start, "end": end, "paragraph_id": p_idx, "sentence_id": s_idx})
            local_cursor = end
        paragraph_sentences.append(rows)
        cursor = max(cursor, p_start + len(p_clean) + 1)
        for i in range(len(rows)):
            for j in range(i, min(len(rows), i + 3)):
                result.append({
                    "text": " ".join(r["text"] for r in rows[i:j+1]),
                    "start": rows[i]["start"], "end": rows[j]["end"],
                    "paragraph_id": p_idx, "sentence_a": rows[i]["sentence_id"],
                    "sentence_b": rows[j]["sentence_id"], "sentence_gap": j - i,
                    "link_reason": "same_paragraph",
                })
    # Kontrolowane przejście przez sąsiedni akapit: tylko z jawnym spójnikiem.
    for p_idx in range(len(paragraph_sentences) - 1):
        left, right = paragraph_sentences[p_idx], paragraph_sentences[p_idx + 1]
        if not left or not right or not _DISCOURSE_LINK_RE.match(right[0]["text"]):
            continue
        result.append({
            "text": left[-1]["text"] + " " + right[0]["text"],
            "start": left[-1]["start"], "end": right[0]["end"],
            "paragraph_id": p_idx, "sentence_a": left[-1]["sentence_id"],
            "sentence_b": right[0]["sentence_id"], "sentence_gap": 1,
            "link_reason": "adjacent_paragraph_discourse_link",
        })
    # Najkrótsze okno wygrywa przy tym samym początku, co ogranicza szerokie evidence.
    result.sort(key=lambda w: (w["end"] - w["start"], w["start"]))
    return result


def _match_text(regex: re.Pattern[str], text: str) -> str:
    match = regex.search(text)
    return _clean(match.group(0)) if match else ""


def _name_signature(value: str) -> Tuple[str, ...]:
    tokens = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+", _clean(value).casefold())
    return tuple(token[:5] for token in tokens if len(token) >= 3)


def _verified_person(person: str, sentence: str, known_people: set[Tuple[str, ...]]) -> bool:
    if _NON_PERSON_PROPER_NAME_RE.search(person):
        return False
    signature = _name_signature(person)
    if signature and any(
        len(signature) == len(known) and all(a == b for a, b in zip(signature, known))
        for known in known_people
    ):
        return True
    # Bez relacji mówcy dopuszczamy tylko osobę opisaną jawnym tytułem lub
    # lokalnym czasownikiem sprawczym. To odcina fałszywe „osoby” typu
    # „Zjednoczone Królestwo” czy nazwy własne organizacji.
    escaped = re.escape(person)
    return bool(re.search(
        rf"\b(?:prezydent\w*|premier\w*|minister\w*|pose[łl]\w*|senator\w*|"
        rf"s[ęe]dzi\w*|prokurator\w*|profesor\w*|prof\.)\s+{escaped}\b|"
        rf"\b{escaped}\b[^.!?]{{0,70}}\b(?:powiedzia[łl]\w*|stwierdzi[łl]\w*|"
        rf"odm[oó]wi[łl]\w*|odmaw\w*|unika[łl]\w*|żąda[łl]\w*|zada[łl]\w*|oskar[żz]y[łl]\w*)\b",
        sentence,
        re.I,
    ))


def _frame_candidate(label: str, window: Dict[str, Any], known_people: set[Tuple[str, ...]]) -> Dict[str, Any] | None:
    original = _clean(window.get("text"))
    scan = _semantic_scan_text(original)
    if len(scan.split()) < 5:
        return None

    a = b = ""
    evidence_parts: List[str] = []
    if label == "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW":
        a = _match_text(_SURVEILLANCE_RE, scan)
        target = _match_text(_POLITICAL_TARGET_RE, scan)
        election = _match_text(_ELECTION_RE, scan)
        b = _match_text(_ELECTION_FAIRNESS_RE, scan)
        if not (a and target and election and b):
            return None
        evidence_parts = [a, target, election, b]
    elif label == "SEM_FRAME_INWIGILACJA_KONTRA_STANDARDY_DEMOKRATYCZNE":
        a = _match_text(_SURVEILLANCE_RE, scan)
        b = _match_text(_DEMOCRACY_RE, scan)
        if not (a and b):
            return None
        evidence_parts = [a, b]
    elif label == "SEM_FRAME_INWIGILACJA_JAKO_NARZEDZIE_WALKI_POLITYCZNEJ":
        a = _match_text(_SURVEILLANCE_RE, scan)
        target = _match_text(_POLITICAL_TARGET_RE, scan)
        weapon = _match_text(_POLITICAL_WEAPON_RE, scan)
        purpose = _match_text(_POLITICAL_PURPOSE_RE, scan)
        # Dwie równoważne ścieżki dowodowe:
        # 1) jawny cel polityczny/wyborczy użycia systemu; albo
        # 2) konkretny cel polityczny + język niszczenia/zwalczania.
        # Nie wymagamy słowa „opozycja”, gdy cel polityczny jest nazwany wprost.
        if not (a and (purpose or (target and weapon))):
            return None
        b = purpose or weapon
        evidence_parts = [x for x in (a, target, weapon, purpose) if x]
    elif label == "SEM_FRAME_ODPOWIEDZIALNOSC_URZEDU_KONTRA_DYSTANSOWANIE":
        a = _match_text(_HIGH_OFFICE_RE, scan)
        b = _match_text(_DISTANCING_RE, scan)
        if not (a and b):
            return None
        evidence_parts = [a, b]
    elif label == "SEM_FRAME_POWAGA_KONTRA_SPEKTAKL":
        a = _match_text(_SERIOUS_RE, scan)
        b = _match_text(_SPECTACLE_RE, scan)
        if not (a and b):
            return None
        evidence_parts = [a, b]
    elif label == "SEM_FRAME_ODPOWIEDZIALNOSC_KONTRA_UNIKANIE":
        a = _match_text(_RESPONSIBILITY_RE, scan)
        b = _match_text(_AVOIDANCE_RE, scan)
        if not (a and b):
            return None
        named_people = _PERSON_LOCAL_RE.findall(original)
        has_accountable_actor = bool(_NAMED_HIGH_OFFICE_RE.search(scan) or _ACCOUNTABILITY_PROCEDURE_RE.search(scan)) or any(
            _verified_person(person, original, known_people) for person in named_people
        )
        if not has_accountable_actor:
            return None
        evidence_parts = [a, b]
    elif label == "SEM_FRAME_LEGALNOSC_KONTRA_GRA_POLITYCZNA":
        a = _match_text(_LEGAL_RE, scan)
        b = _match_text(_POLITICAL_CONFLICT_RE, scan)
        if not (a and b):
            return None
        evidence_parts = [a, b]
    elif label == "SEM_FRAME_INSTYTUCJA_KONTRA_OSOBA":
        # Rama ogólna wymaga bezpośredniego lokalnego konfliktu: instytucja,
        # konkretna osoba i sygnał konfliktu muszą współwystąpić w jednym
        # zdaniu. To zatrzymuje pożyczanie „konfliktu” z sąsiedniego tematu.
        direct = None
        for sentence in split_sentences(original):
            sent_scan = _semantic_scan_text(_clean(sentence))
            inst = _match_text(_INSTITUTION_RE, sent_scan)
            pers = _match_text(_PERSON_LOCAL_RE, sent_scan)
            conf = _match_text(_AVOIDANCE_RE, sent_scan) or _match_text(_GENERIC_CONFLICT_RE, sent_scan)
            if inst and pers and conf and _verified_person(pers, sentence, known_people):
                direct = (inst, pers, conf)
                break
        if not direct:
            return None
        institution, person, conflict = direct
        a, b = institution, person
        evidence_parts = [institution, person, conflict]
    else:
        return None

    spec = FRAME_SPECS[label]
    gap = int(window.get("sentence_gap", 0) or 0)
    specificity = float(spec.get("specificity", 0.5) or 0.5)
    unique_evidence = len(set(x.casefold() for x in evidence_parts if x))
    local_bonus = 1.0 if gap == 0 else max(0.55, 0.9 - gap * 0.15)
    # Current: ranking jest przede wszystkim rankingiem DOWODU, a dopiero potem
    # prioru ramy. W Current evidence_strength było tylko metadanym i nie wpływało
    # na zwycięzcę, przez co ogólna rama mogła wygrywać nad bezpośrednią.
    evidence_strength = round(min(1.0, 0.42 + 0.11 * unique_evidence + 0.16 * local_bonus), 3)
    coverage = round(min(1.0, unique_evidence / (4.0 if label == "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW" else 3.0)), 3)
    explicitness = round(min(1.0, 0.55 + 0.30 * local_bonus + 0.10 * min(2, unique_evidence)), 3)
    prior = float(spec["score"]) / 10.0
    semantic_adjustment = 0.0
    if label == "SEM_FRAME_INSTYTUCJA_KONTRA_OSOBA":
        # Rama ogólna jest wyłącznie fallbackiem; nie może wygrać tylko dlatego,
        # że ma trzy łatwe elementy evidence.
        semantic_adjustment -= 1.10
    elif label == "SEM_FRAME_POWAGA_KONTRA_SPEKTAKL" and _STRONG_SERIOUS_RE.search(scan) and _SPECTACLE_RE.search(scan):
        # Jawne dwa bieguny („polityczny spektakl” + „powaga/szacunek do państwa/prawa”)
        # są silniejsze niż sama informacja o niestawiennictwie.
        semantic_adjustment += 0.70
    elif label == "SEM_FRAME_INWIGILACJA_JAKO_NARZEDZIE_WALKI_POLITYCZNEJ" and _POLITICAL_PURPOSE_RE.search(scan):
        semantic_adjustment += 0.45
    elif label == "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW" and _ELECTION_FAIRNESS_RE.search(scan):
        semantic_adjustment += 0.55
    rank_score = 5.0 + evidence_strength * 2.15 + coverage * 1.15 + explicitness * 0.75 + specificity * 0.65 + prior * 0.30 + semantic_adjustment
    return _card(
        label, "P3", "SEMANTIC_FRAME_DETECTOR", original, spec["phrase"], spec["why"],
        start=int(window.get("start", -1)), end=int(window.get("end", -1)),
        score=float(spec["score"]), requires_review=True,
        extra={
            "rank_score": round(rank_score, 3), "specificity": specificity,
            "evidence_strength": evidence_strength, "evidence_coverage": coverage,
            "evidence_explicitness": explicitness, "semantic_adjustment": round(semantic_adjustment, 3),
            "evidence_count": len(evidence_parts), "evidence_text": original,
            "evidence_parts": evidence_parts, "evidence_a": a, "evidence_b": b,
            "frame_id": label, "frame_label": spec["phrase"],
            "evidence_roles": [
                role for role, value in (
                    ("SURVEILLANCE", a if label.startswith("SEM_FRAME_INWIGILACJA") else ""),
                    ("POLITICAL_TARGET", locals().get("target", "")),
                    ("POLITICAL_PURPOSE", locals().get("purpose", "")),
                    ("POLITICAL_WEAPON", locals().get("weapon", "")),
                    ("ELECTION_CONTEXT", _match_text(_ELECTION_RE, scan) if label.startswith("SEM_FRAME_INWIGILACJA") else ""),
                    ("ELECTION_HARM", _match_text(_ELECTION_FAIRNESS_RE, scan) if label == "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW" else ""),
                ) if value
            ],
            "paragraph_id": int(window.get("paragraph_id", -1)),
            "sentence_a": int(window.get("sentence_a", -1)),
            "sentence_b": int(window.get("sentence_b", -1)),
            "sentence_gap": gap, "link_reason": _clean(window.get("link_reason")),
        },
    )


def build_semantic_frame_cards(text: str, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
    known_people: set[Tuple[str, ...]] = set()
    for card in sections.get("canonical_relations", []) or []:
        relation = card.get("canonical_relation") or card
        if _clean(relation.get("speaker_kind")) != "person":
            continue
        signature = _name_signature(_clean(relation.get("speaker")))
        if signature:
            known_people.add(signature)
    windows = _local_semantic_windows(text or "")
    cards: List[Dict[str, Any]] = []
    for label in FRAME_SPECS:
        candidates = [c for window in windows if (c := _frame_candidate(label, window, known_people))]
        if candidates:
            # Najmocniejszy dowód, potem mniejsze okno. Nie bierzemy po prostu
            # pierwszego regexowego trafienia.
            candidates.sort(key=lambda c: (-float(c.get("rank_score", 0) or 0), int(c.get("end", 0))-int(c.get("start", 0))))
            cards.append(candidates[0])


    # Legalność/procedura jest bardziej precyzyjna od ogólnego powaga/spektakl,
    # gdy obie powstały z tej samej lokalnej pary zdań.
    labels = {c.get("label") for c in cards}
    if "SEM_FRAME_LEGALNOSC_KONTRA_GRA_POLITYCZNA" in labels:
        specific = next(c for c in cards if c.get("label") == "SEM_FRAME_LEGALNOSC_KONTRA_GRA_POLITYCZNA")
        cards = [c for c in cards if c.get("label") != "SEM_FRAME_POWAGA_KONTRA_SPEKTAKL" or not (
            int(c.get("paragraph_id", -2)) == int(specific.get("paragraph_id", -3))
            and abs(int(c.get("sentence_a", 0)) - int(specific.get("sentence_a", 0))) <= 1
        )]
    return sorted(cards, key=lambda c: -float(c.get("rank_score", c.get("score", 0)) or 0))[:8]


def build_effectiveness_report_cards(text: str, sections: Dict[str, Any], semantic_sections: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    relation_cards = get_canonical_relation_cards(sections)
    relations = [c.get("canonical_relation") or {} for c in relation_cards]
    rejected = sections.get("canonical_relation_rejections", []) or []
    accepted = len(relations)
    total = accepted + len(rejected)

    # aktywny kontrakt: relacje źródłowe i relacje wypowiedzi mają różne kontrakty.
    # Mapa sprawczości projektuje wyłącznie relacje z jawnie ustalonym mówcą,
    # więc nie wolno porównywać jej do source-only records i nazywać tego
    # niespójnością.
    speech_relations = [r for r in relations if _clean(r.get("speaker"))]
    source_only = accepted - len(speech_relations)
    complete = sum(
        1 for r in speech_relations
        if _clean(r.get("speaker")) and _clean(r.get("claim"))
        and (_clean(r.get("speaker_action")) or _clean(r.get("attribution_marker")))
    )
    canonical = sum(
        1 for r in speech_relations
        if str(r.get("speaker_entity_id") or "").startswith(("person:", "institution:", "party:"))
        and not _clean(r.get("speaker")).lower().startswith(("pan ", "pani "))
    )
    unique_ids = len({_clean(r.get("relation_id")) for r in relations if _clean(r.get("relation_id"))})
    speech_ids = {_clean(r.get("relation_id")) for r in speech_relations if _clean(r.get("relation_id"))}
    projection_ids = {
        _clean(value) for value in (sections.get("_agency_projection_relation_ids", []) or []) if _clean(value)
    }
    if not projection_ids:
        projection_ids = {_clean(c.get("relation_id")) for c in sections.get("agency_map", []) or [] if _clean(c.get("relation_id"))}
    projection_ok = speech_ids == projection_ids
    actor_types_ok = all(c.get("entity_type") in {"person", "institution", "party"} for c in sections.get("actor_map", []) or [])

    target_bearing = [r for r in relations if _clean(r.get("target"))]
    canonical_targets = sum(
        1 for r in target_bearing
        if (
            (_clean(r.get("target_type")) == "role" and _clean(r.get("target_resolution_mode")) == "role_target")
            or (
                _clean(r.get("target_resolution_mode")) in {"claim_local_raw_match", "claim_local_explicit_cue", "predicate_local_raw_match"}
                and _clean(r.get("target_entity_id")).startswith(("person:", "institution:", "product:"))
            )
        )
    )
    targets_ok = canonical_targets == len(target_bearing)
    accepted_ratio = accepted / max(1, total)

    speech_count = len(speech_relations)
    score = 0
    score += round(30 * complete / max(1, speech_count)) if speech_count else 0
    score += round(20 * canonical / max(1, speech_count)) if speech_count else 0
    score += round(15 * unique_ids / max(1, accepted)) if accepted else 0
    score += 10 if projection_ok else 0
    score += 10 if actor_types_ok else 0
    score += 10 if targets_ok else round(10 * canonical_targets / max(1, len(target_bearing)))
    score += round(5 * accepted_ratio)
    score = max(0, min(100, score))

    # Integralność głównego kontraktu jest warunkiem jakości "dobrej/wysokiej".
    # Nie pozwalamy wysokiemu accepted_ratio zamaskować niespójnej projekcji,
    # niekanonicznego mówcy albo nieudowodnionego targetu.
    contract_ok = (
        complete == speech_count
        and canonical == speech_count
        and unique_ids == accepted
        and projection_ok
        and actor_types_ok
        and targets_ok
    )
    if not contract_ok:
        score = min(score, 74)

    quality = "wysoka" if score >= 90 else "dobra" if score >= 75 else "średnia" if score >= 50 else "niska"
    items = [
        f"zaakceptowane relacje: {accepted}",
        f"odrzucone relacje: {len(rejected)}",
        f"kompletne relacje wypowiedzi: {complete}/{speech_count} (relacje źródłowe: {source_only})",
        f"kanoniczni mówcy: {canonical}/{speech_count}",
        f"unikalne relation_id: {unique_ids}/{accepted}",
        f"projekcja mapy sprawczości: {'zgodna' if projection_ok else 'niespójna'} ({len(projection_ids)}/{len(speech_ids)} relacji z mówcą)",
        f"typy mapy aktorów: {'zgodne' if actor_types_ok else 'niespójne'}",
        f"lokalnie udowodnione targety: {canonical_targets}/{len(target_bearing)} (brak targetu: {accepted - len(target_bearing)})",
    ]
    return [_card(
        "SEM_ANALYSIS_EFFECTIVENESS_REPORT",
        "R3",
        "SEMANTIC_EFFECTIVENESS_REPORT",
        text[:620],
        f"integralność pipeline: {quality} ({score}/100)",
        "To jest wynik integralności technicznej zaakceptowanych danych, a nie procent skuteczności semantycznej. Sprawdza spójność speaker → target → claim, relation_id, projekcji i typów encji. Rzeczywistą precision/recall mierzy osobny benchmark GOLD.",
        score=max(1.0, score / 10.0),
        requires_review=score < 90 or bool(rejected),
        extra={
            "items": items,
            "quality_label": quality,
            "quality_score": score,
            "contract_ok": contract_ok,
            "metric_kind": "pipeline_integrity",
            "not_semantic_accuracy": True,
        },
    )]


def build_semantic_effectiveness_sections(text: str, sections: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    source_roles = build_source_role_cards(text, sections)
    relation_quality = build_relation_quality_cards(text, sections)
    claim_quality = build_claim_status_quality_cards(text, sections)
    p0_p1_gate = build_p0_to_p1_gate_cards(text, sections)
    semantic_frames = build_semantic_frame_cards(text, sections)
    semantic_sections = {
        "source_roles": source_roles,
        "relation_quality": relation_quality,
        "claim_quality": claim_quality,
        "p0_p1_gate": p0_p1_gate,
        "semantic_frames": semantic_frames,
    }
    semantic_sections["effectiveness_report"] = build_effectiveness_report_cards(text, sections, semantic_sections)
    return semantic_sections


def summarize_semantic_effectiveness(sections: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    report = (sections.get("effectiveness_report") or [{}])[0]
    return {
        "source_roles": len(sections.get("source_roles", [])),
        "relation_quality": len(sections.get("relation_quality", [])),
        "claim_quality": len(sections.get("claim_quality", [])),
        "p0_p1_gate": len(sections.get("p0_p1_gate", [])),
        "semantic_frames": len(sections.get("semantic_frames", [])),
        "quality_label": report.get("quality_label", ""),
        "quality_score": report.get("quality_score", 0),
    }
