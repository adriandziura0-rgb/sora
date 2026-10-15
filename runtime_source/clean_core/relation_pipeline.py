from __future__ import annotations

"""Current — aktywny rdzeń relacji.

Przepływ jest zamknięty i jednokierunkowy:
resolver → CanonicalEntityRegistry → RelationValidator → accepted/rejected → PublicProjection.
Żadna warstwa pomocnicza nie ustala ponownie mówcy, źródła, medium ani claimu.
"""

import hashlib
import re
from typing import Any, Dict, Iterable, List, Tuple

from .canonical_entity_builder import CanonicalEntityBuilder
from .public_projection import accepted_cards, rejected_cards
from .relation_resolver import resolve_structural_relation_bundle
from .relation_validator import validate_relation
from .segmentation import segment_document

from .version import STAGE

_PROGRAM_PATTERNS = (
    re.compile(r"\b(?:w|we)\s+[\"„]([^\"”]{2,80})[\"”]", re.I),
    re.compile(r"\bprogram(?:ie|u)?\s+[\"„]([^\"”]{2,80})[\"”]", re.I),
    re.compile(r"\bwydani(?:u|a)\s+[\"„]([^\"”]{2,80})[\"”]", re.I),
)
_TOPIC_PATTERNS = (
    ("Pegasus", re.compile(r"\bpegasus\w*\b|\binwigilacj\w*\b|\bspyware\b", re.I)),
    ("komisja śledcza", re.compile(r"\bkomisj\w*\s+śledcz\w*\b", re.I)),
    ("bezpieczeństwo", re.compile(r"\bbezpieczeństw\w*\b|\bprywatnoś\w*\b", re.I)),
    ("demokracja i praworządność", re.compile(r"\bdemokracj\w*\b|\bpraworządnoś\w*\b|\bprocedur\w*\b", re.I)),
    ("KRS i wymiar sprawiedliwości", re.compile(r"\bKRS\b|Krajow\w*\s+Rad\w*\s+Sądownictw\w*|wymiar\w*\s+sprawiedliwoś\w*|sędzi\w*", re.I)),
    ("odpowiedzialność i immunitet", re.compile(r"\bimmunitet\w*\b|\bodpowiedzialnoś\w*\b|Trybunał\w*\s+Stanu", re.I)),
    ("prokuratura i postępowanie", re.compile(r"\bprokuratur\w*\b|\bśledztw\w*\b|\bzarzut\w*\b|\bpostępowani\w*\b", re.I)),
    ("wybory i kampania", re.compile(r"\bwybor\w*\b|\bkampani\w*\b|\bsztab\w*\b", re.I)),
    ("służby specjalne", re.compile(r"\bCBA\b|\bsłużb\w*\b|\bkontrol\w*\s+operacyjn\w*\b", re.I)),
    ("Fundusz Sprawiedliwości", re.compile(r"\bFundusz\w*\s+Sprawiedliwoś\w*\b", re.I)),
    ("prywatyzacja CIECH", re.compile(r"\bCIECH\w*\b|\bprywatyzacj\w*\b", re.I)),
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,:;–—-")


def _slug(value: str) -> str:
    value = value.casefold().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _relation_id(row: Dict[str, Any]) -> str:
    raw = "|".join(
        _clean(row.get(key)).casefold()
        for key in ("document_id", "speaker_entity_id", "speaker_action", "attribution_marker", "claim", "target_entity_id", "sentence")
    )
    return "rel_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _segment_id(row: Dict[str, Any]) -> str:
    raw = f"{_clean(row.get('document_id'))}|{_clean(row.get('sentence'))}|{row.get('block_index')}|{row.get('sentence_index')}"
    return "seg_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]


def _forms_in_text(entity: Dict[str, Any], text: str) -> bool:
    r"""Sprawdza pełny span encji, nigdy dowolny substring.

    Krytyczne dla krótkich aliasów partii: ``KO`` nie może pasować do
    ``kompetencji`` ani ``okolice``. Granice ``\w`` działają dla polskich
    liter w Pythonie i zachowują poprawne dopasowania typu ``(KO)``.
    """
    haystack = _clean(text)
    for form in entity.get("surface_forms") or [entity.get("canonical_name")]:
        value = _clean(form)
        if value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", haystack, re.I):
            return True
    return False


def _entities_in(builder: CanonicalEntityBuilder, text: str, entity_type: str) -> List[Dict[str, Any]]:
    return [entity for entity in builder.entities() if entity.get("entity_type") == entity_type and _forms_in_text(entity, text)]


def _program(sentence: str, medium: str = "") -> str:
    for pattern in _PROGRAM_PATTERNS:
        match = pattern.search(sentence or "")
        if not match:
            continue
        value = _clean(match.group(1))
        value = {"faktach po faktach": "Fakty po Faktach", "kropce nad i": "Kropka nad i"}.get(value.casefold(), value)
        if value and value.casefold() != _clean(medium).casefold():
            return value
    return ""


def _local_medium(builder: CanonicalEntityBuilder, evidence: str) -> Dict[str, Any] | None:
    # Program ma jawne, kontrolowane przypisanie do medium. To nie jest
    # globalny fallback: działa wyłącznie, gdy nazwa programu występuje w
    # lokalnym zdaniu/kontekście tej relacji.
    if re.search(r"[\"„'](?:Faktach po Faktach|Kropce nad i)[\"”']", evidence, re.I):
        return builder.resolve("TVN24", "medium")

    candidates = _entities_in(builder, evidence, "medium")
    if not candidates:
        return None
    # Prefer medium preceded by broadcast context; otherwise do not guess.
    for entity in candidates:
        for form in entity.get("surface_forms") or [entity.get("canonical_name")]:
            match = re.search(rf"(?<!\w){re.escape(str(form))}(?!\w)", evidence, re.I)
            if not match:
                continue
            prefix = evidence[max(0, match.start()-70):match.start()]
            if re.search(r"(?:według|wg|zdaniem|powołując\s+się\s+na)\s+[\"„']?\s*$", prefix, re.I):
                continue
            if re.search(r"(?:\bw|\bwe|na\s+antenie|w\s+studiu)\s+[\"„']?\s*$", prefix, re.I):
                return entity
    return None


def _local_editorial_source(
    builder: CanonicalEntityBuilder,
    sentence: str,
    context: str,
    medium_entity: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Źródło afiliacyjne jest jawne lokalnie, np. „X z Gazety Wyborczej”.

    Nie zamieniamy każdego medium w źródło i nie dziedziczymy źródła między
    mówcami. Kandydat musi wystąpić po przyimku „z/ze” w zdaniu relacji.
    """
    local = f"{context} {sentence}".strip()
    medium_id = _clean((medium_entity or {}).get("entity_id"))
    for entity in _entities_in(builder, local, "medium"):
        if _clean(entity.get("entity_id")) == medium_id:
            continue
        for form in entity.get("surface_forms") or [entity.get("canonical_name")]:
            for match in re.finditer(rf"(?<!\w){re.escape(str(form))}(?!\w)", local, re.I):
                prefix = local[max(0, match.start()-20):match.start()]
                if re.search(
                    r"\b(?:z|ze)\s+(?:(?:portalu|serwisu|redakcji|telewizji|radia|dziennika|gazety)\s+)?[\"„']?\s*$",
                    prefix, re.I,
                ):
                    return entity
    return None


def _local_affiliation(
    builder: CanonicalEntityBuilder, speaker: str, sentence: str, context: str
) -> Dict[str, Any] | None:
    """Zwraca tylko afiliację lokalnie związaną z *tym* mówcą.

    Sama obecność jednej partii gdzieś w zdaniu nie jest dowodem afiliacji
    mówcy (np. pytanie Joanny Kluzik-Rostkowskiej o kandydata Konfederacji).
    Akceptujemy wyłącznie partię w krótkim deskryptorze bezpośrednio przy
    powierzchni osoby: ``Dariusz Joński z KO``, ``Lubnauer (KO)``,
    ``poseł PiS Tobiasz Bocheński``.
    """
    speaker = _clean(speaker)
    if not speaker:
        return None
    local = f"{context} {sentence}".strip()
    parties = _entities_in(builder, local, "party")
    if not parties:
        return None
    speaker_forms = [speaker]
    resolved_speaker = builder.resolve(speaker, "person", confirmed=True)
    if resolved_speaker:
        speaker_forms.extend(resolved_speaker.get("surface_forms") or [])
    for party in parties:
        party_forms = list(party.get("surface_forms") or [party.get("canonical_name")])
        for sf in speaker_forms:
            sf = _clean(sf)
            if not sf:
                continue
            for pf in party_forms:
                pf = _clean(pf)
                if not pf:
                    continue
                patterns = (
                    rf"(?<!\w){re.escape(sf)}(?!\w)\s*(?:\(\s*{re.escape(pf)}\s*\)|(?:z|ze)\s+{re.escape(pf)}(?!\w))",
                    rf"(?:poseł|posłanka|europoseł|europosłanka|senator|senatorka|polityk|polityczka)\s+{re.escape(pf)}\s+{re.escape(sf)}(?!\w)",
                )
                if any(re.search(pattern, local, re.I) for pattern in patterns):
                    return party
    return None


def _local_institution(builder: CanonicalEntityBuilder, speaker: str, sentence: str, context: str) -> Dict[str, Any] | None:
    """Instytucja osoby tylko przy lokalnym dowodzie związku z tym mówcą.

    Sama wzmianka o CBA, ministerstwie czy prokuraturze w treści wypowiedzi nie
    jest afiliacją instytucjonalną osoby. Akceptujemy role bezpośrednio przy
    nazwie mówcy (np. „Rzecznik Prokuratury Krajowej Przemysław Nowak”).
    """
    speaker = _clean(speaker)
    if not speaker:
        return None
    local = _clean(f"{context} {sentence}")
    speaker_entity = builder.resolve(speaker, "person")
    speaker_forms = [speaker, *((speaker_entity or {}).get("surface_forms") or [])]

    def near(pattern: str) -> bool:
        return any(re.search(pattern.format(sp=re.escape(_clean(sf))), local, re.I) for sf in speaker_forms if _clean(sf))

    if near(r"(?:rzecznik|rzeczniczka)\s+Prokuratury\s+Krajowej\s+{sp}(?!\w)"):
        return builder.resolve("Prokuratura Krajowa", "institution")
    if near(r"(?:minister|ministra|wiceminister|wiceministra)\s+sprawiedliwości\s+{sp}(?!\w)"):
        return builder.resolve("Ministerstwo Sprawiedliwości", "institution")
    if near(r"(?:szef|szefowa|funkcjonariusz|funkcjonariuszka)\s+CBA\s+{sp}(?!\w)"):
        return builder.resolve("CBA", "institution")

    institutions = _entities_in(builder, local, "institution")
    for inst in institutions:
        inst_forms = list(inst.get("surface_forms") or [inst.get("canonical_name")])
        for sf in speaker_forms:
            sf = _clean(sf)
            if not sf:
                continue
            for inf in inst_forms:
                inf = _clean(inf)
                if not inf:
                    continue
                patterns = (
                    rf"(?<!\w){re.escape(sf)}(?!\w)\s+(?:z|w|we)\s+{re.escape(inf)}(?!\w)",
                    rf"(?:rzecznik|rzeczniczka|szef|szefowa|dyrektor|dyrektorka|przedstawiciel|przedstawicielka)\s+{re.escape(inf)}\s+{re.escape(sf)}(?!\w)",
                )
                if any(re.search(pattern, local, re.I) for pattern in patterns):
                    return inst
    return None


def _topic(*parts: Any) -> str:
    # Najpierw claim, potem bieżące zdanie, dopiero na końcu kontekst.
    # Dzięki temu zmiana tematu Pegasus → KRS nie jest przykrywana przez
    # poprzednią wypowiedź tego samego mówcy.
    for part in reversed(parts):
        text = _clean(part)
        if not text:
            continue
        for label, pattern in reversed(_TOPIC_PATTERNS):
            if pattern.search(text):
                return label
    return ""


def _entity_start(entity: Dict[str, Any], text: str) -> int:
    """Zwraca początek pełnego, lokalnego span-u encji albo -1."""
    best = -1
    for form in entity.get("surface_forms") or [entity.get("canonical_name")]:
        value = _clean(form)
        if not value:
            continue
        match = re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text or "", re.I)
        if match and (best < 0 or match.start() < best):
            best = match.start()
    return best


def _fallback_topic(builder: CanonicalEntityBuilder, claim: str, target_name: str = "") -> str:
    """Ostrożny temat awaryjny oparty wyłącznie na treści claimu.

    Nie korzysta z poprzedniego zdania. Najpierw bierze jawny target, a później
    jedną kontrolowaną encję produktu/instytucji obecną w samej wypowiedzi.
    """
    if _clean(target_name):
        return _clean(target_name)
    for entity_type in ("product", "institution"):
        entities = _entities_in(builder, claim, entity_type)
        if len(entities) == 1:
            return _clean(entities[0].get("canonical_name"))
    return ""


def _target(builder: CanonicalEntityBuilder, raw_target: str, claim: str, sentence: str, speaker_id: str) -> tuple[Dict[str, Any] | None, str, str]:
    """aktywny kontrakt: target musi być udowodniony *wewnątrz claimu*.

    Nie wystarcza, że poprawna encja występuje w całym zdaniu, sąsiednim zdaniu
    albo dalszym kontekście. Resolver może podać surowego kandydata, ale do
    CanonicalRelation przechodzi on tylko wtedy, gdy po kanonizacji ta sama encja
    jest obecna w samym claimie. Brak lokalnego dowodu => target=None.

    ``sentence`` pozostaje w sygnaturze dla zgodności wywołań, ale nie bierze
    udziału w wyborze targetu. To celowo usuwa dawną ścieżkę
    ``sentence_local_raw_match`` i automatyczne zgadywanie jedynej encji claimu.
    """
    allowed_types = {"person", "institution", "product"}
    claim_entities: Dict[str, Dict[str, Any]] = {}
    for entity_type in ("person", "institution", "product"):
        for entity in _entities_in(builder, claim, entity_type):
            eid = _clean(entity.get("entity_id"))
            if eid and eid != speaker_id:
                claim_entities[eid] = entity

    raw = _clean(raw_target)
    if not raw:
        # Bez surowego targetu wolno użyć encji tylko przy jawnym lokalnym
        # sygnale obiektu wypowiedzi w samym claimie. To nie jest dawny
        # fallback "jedyna encja = target".
        explicit_cue = re.search(
            r"\b(?:o|wobec|przeciwko|dotycz(?:y|ący|ąca|ące)|zachowanie|immunitetu|sprawie|na temat)\b",
            claim,
            re.I,
        )
        if explicit_cue and len(claim_entities) == 1:
            return next(iter(claim_entities.values())), "claim_local_explicit_cue", raw
        # Sama encja na początku claimu NIE jest targetem. Najczęściej jest
        # podmiotem treści (np. „ABW zatrzymała Pawła G.”), więc dawny fallback
        # claim_lead_named_entity sztucznie zamieniał wykonawcę czynności w „o kim”.
        # Bez jawnego sygnału obiektu wolimy brak targetu. Wyjątkiem pozostaje
        # produkt nazwany w claimie, który może być bezpiecznym celem rzeczowym.
        if len(claim_entities) == 1:
            candidate = next(iter(claim_entities.values()))
            if _clean(candidate.get("entity_type")) == "product":
                return candidate, "claim_named_product", raw
        return None, "none", raw

    entity = builder.resolve(raw, None)
    if not entity:
        return None, "none", raw

    eid = _clean(entity.get("entity_id"))
    etype = _clean(entity.get("entity_type"))
    if not eid or eid == speaker_id or etype not in allowed_types:
        return None, "none", raw

    if eid in claim_entities:
        # Current: lokalność encji nie wystarcza. Konstrukcja czysto lokatywna/czasowa
        # (np. "kiedy dojdzie do zmiany w Pałacu Prezydenckim") nie oznacza,
        # że miejsce/instytucja jest obiektem wypowiedzi. Jawne sygnały obiektu
        # (o, wobec, przeciwko, w sprawie, na temat...) mają pierwszeństwo.
        object_cue = re.search(
            r"\b(?:o|wobec|przeciwko|na\s+temat|w\s+sprawie|dotycz(?:y|ący|ąca|ące))\s+(?:[^,.;:!?]{0,40}\s+)?" + re.escape(raw) + r"\b",
            claim, re.I,
        )
        locative_cue = re.search(
            r"\b(?:w|we|na|do|z|ze|przy|pod|nad|przed|po)\s+" + re.escape(raw) + r"\b",
            claim, re.I,
        )
        if locative_cue and not object_cue:
            return None, "none", raw
        return claim_entities[eid], "claim_local_raw_match", raw

    # Niektóre resolvery zwracają jako claim wyłącznie cytowaną ocenę (np.
    # "ostentacyjne lekceważenie"), podczas gdy obiekt jest jawnie związany
    # z predykatem w tym samym zdaniu: "zachowanie Zbigniewa Ziobry ocenił".
    # To nadal jest lokalny dowód, ale tylko przy wyraźnym znaczniku obiektu
    # bezpośrednio przed surową nazwą targetu.
    if raw and sentence:
        cue_pattern = re.compile(
            r"\b(?:zachowanie|immunitet(?:u|em)?|spraw(?:a|ę|ie|y)|wobec|przeciwko|o)\s+(?:[^,.;]{0,40}\s+)?" + re.escape(raw) + r"\b",
            re.I,
        )
        if cue_pattern.search(sentence):
            for candidate in _entities_in(builder, sentence, etype):
                if _clean(candidate.get("entity_id")) == eid:
                    return candidate, "predicate_local_raw_match", raw

    # aktywny kontrakt: poprawna encja z kontekstu nie jest jeszcze dowodem, że jest
    # obiektem tej konkretnej wypowiedzi. Wolimy jawne ``no_target``.
    return None, "none", raw


def _claim_object(action: str, claim: str, sentence: str, context: str) -> Tuple[str, str, str]:
    target = ""
    target_type = ""
    obj = ""
    obligation = re.search(
        r"\bzobowiązał(?:a)?\s+(?P<target>ministra\s+sprawiedliwości|prezydenta|premiera|prokuratora\s+generalnego)\s+do\s+(?P<object>[^,.;]{2,100})",
        claim,
        re.I,
    )
    if obligation:
        target = _clean(obligation.group("target")).casefold()
        target_type = "role"
        obj = _clean(obligation.group("object"))
        if re.match(r"^(?:ich|jej|jego)\s+przekazania", obj, re.I) and re.search(r"\bdokument\w*\b", f"{context} {sentence}", re.I):
            obj = "dokumenty"
    return target, target_type, obj


def _speaker_resolution(raw: Dict[str, Any], speaker_entity: Dict[str, Any] | None, sentence: str, context: str) -> Dict[str, Any]:
    """Jednoznaczny ślad pochodzenia mówcy dla aktywnego kontraktu.

    Mówca może pochodzić tylko z jawnej atrybucji w bieżącym zdaniu,
    kontrolowanego aliasu nazwiska albo z jawnie oznaczonej kontynuacji
    poprzedniego mówcy w tym samym bloku. Ta informacja jest później
    sprawdzana przez końcową bramkę relacji.
    """
    if not speaker_entity:
        return {"mode": "none", "method": _clean(raw.get("method")), "raw_speaker": ""}

    method = _clean(raw.get("method"))
    raw_speaker = _clean(raw.get("speaker"))
    warnings = set(raw.get("warnings") or [])

    inherited_methods = {
        "same_block_role_or_pronoun_attribution", "same_block_previous_explicit_speaker",
    }
    if method in inherited_methods:
        return {
            "mode": "inherited_same_block",
            "method": method,
            "raw_speaker": raw_speaker,
            "has_context": bool(_clean(context)),
            "warning": (
                "speaker_inherited_from_previous_sentence"
                if "speaker_inherited_from_previous_sentence" in warnings
                else "speaker_resolved_from_previous_explicit_role"
                if "speaker_resolved_from_previous_explicit_role" in warnings
                else ""
            ),
        }

    if method == "surname_attribution_resolved_from_document_alias":
        return {
            "mode": "surname_alias",
            "method": method,
            "raw_speaker": raw_speaker,
            "has_context": bool(_clean(context)),
        }

    return {
        "mode": "explicit_sentence",
        "method": method,
        "raw_speaker": raw_speaker,
        "has_context": bool(_clean(context)),
    }


def _calibrated_confidence(raw: Dict[str, Any], speaker_resolution: Dict[str, Any], has_source: bool) -> float:
    """Kalibruje pewność do realnego sposobu pozyskania atrybucji.

    Wartość resolvera pozostaje w ``raw_confidence``. Publiczne ``confidence``
    nie może sugerować prawie 100% pewności dla dziedziczenia lub kontynuacji.
    """
    raw_value = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
    method = _clean(raw.get("method"))
    mode = _clean(speaker_resolution.get("mode"))
    caps = {
        "source_quote_continuation": 0.82,
        "forward_quote_signature_attribution": 0.86,
        "surname_attribution_resolved_from_document_alias": 0.88,
        "same_block_role_or_pronoun_attribution": 0.84,
        "same_block_previous_explicit_speaker": 0.84,
        "explicit_lead_source_attribution": 0.90,
    }
    cap = caps.get(method, 0.97 if mode == "explicit_sentence" else 0.90)
    if mode == "inherited_same_block":
        cap = min(cap, 0.84)
    if mode == "surname_alias":
        cap = min(cap, 0.88)
    if not speaker_resolution.get("raw_speaker") and not has_source:
        cap = min(cap, 0.75)
    return round(min(raw_value, cap), 3)


def _canonical_source_for_document(source: str, doc_meta: Dict[str, Any]) -> str:
    """Rozwija skróconą nazwę źródła tylko przy jednoznacznym metadanym dokumencie."""
    value = _clean(source)
    if value.casefold() != "gazeta":
        return value
    candidates = [
        _clean(doc_meta.get("document_label")),
        *[_clean(x) for x in (doc_meta.get("quoted_sources") or [])],
    ]
    normalized_candidates = [re.sub(r"[_\-]+", " ", candidate) for candidate in candidates]
    if any(re.search(r"\b(?:Gazeta\s+Wyborcza|Wyborcza|GW)\b", candidate, re.I) for candidate in normalized_candidates):
        return "Gazeta Wyborcza"
    return value


def _canonical_action_for_speaker(action: str, speaker_entity: Dict[str, Any] | None) -> str:
    """Dopasowuje formę karty do kanonicznej nazwy instytucji rodzaju nijakiego."""
    value = _clean(action).casefold()
    entity = speaker_entity or {}
    name = _clean(entity.get("canonical_name"))
    if _clean(entity.get("entity_type")) != "institution" or not (
        name.casefold().startswith("ministerstwo ") or name.casefold().endswith("stwo")
    ):
        return value
    neuter = {
        "uznał": "uznało", "poinformował": "poinformowało", "podał": "podało",
        "przekazał": "przekazało", "stwierdził": "stwierdziło", "dodał": "dodało",
        "podkreślił": "podkreśliło", "wyjaśnił": "wyjaśniło", "ocenił": "oceniło",
    }
    return neuter.get(value, value)


def _lead_source_relation(text: str) -> Dict[str, Any] | None:
    first = _clean(re.split(r"(?<=[.!?])\s+|\n+", text or "", maxsplit=1)[0])
    match = re.match(r"^(?P<marker>według|wg)\s+(?P<source>(?:doniesień\s+)?[^,]{3,80}?mediów)\s*,\s*(?P<claim>.+)$", first, re.I)
    if not match or len(_clean(match.group("claim")).split()) < 5:
        return None
    return {
        "speaker": "", "speaker_kind": "", "speaker_action": "", "source": _clean(match.group("source")),
        "source_kind": "source", "claim": _clean(match.group("claim")), "attribution_marker": _clean(match.group("marker")).casefold(),
        "target": "", "confidence": 0.91, "method": "explicit_lead_source_attribution", "sentence": first,
        "context_sentence": "", "block_index": 0, "sentence_index": -1, "warnings": [],
    }


def _canonicalize(
    raw: Dict[str, Any],
    builder: CanonicalEntityBuilder,
    document_sources: List[str],
    image_sources: List[str],
    document_ids: List[str],
    document_metadata: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    sentence = _clean(raw.get("sentence"))
    context = _clean(raw.get("context_sentence"))
    claim = _clean(raw.get("claim"))
    raw_action = _clean(raw.get("action")).casefold()

    raw_speaker = _clean(raw.get("speaker"))
    raw_speaker_kind = _clean(raw.get("speaker_kind"))
    allowed_speaker_types = {"person", "institution", "party"}
    expected_speaker_type = raw_speaker_kind if raw_speaker_kind in allowed_speaker_types else "person"
    trusted_person_methods = {
        "explicit_subject_before_verb", "explicit_role_referent_before_verb", "explicit_subject_after_verb",
        "quote_role_program_medium_explicit_speaker", "jak_named_speaker_explicit",
        "surname_after_action_with_complement", "surname_colon_explicit_alias",
        "trailing_surname_explicit_alias", "leading_surname_explicit_alias", "surname_attribution_resolved_from_document_alias",
        "same_block_role_or_pronoun_attribution", "same_block_previous_explicit_speaker",
        "passive_interview_context", "attribution_source_plus_explicit_speaker",
        "quote_explicit_institutional_speaker", "embedded_jak_explicit_speaker", "colon_attribution",
        "document_nearby_explicit_quote_continuation", "turn_change_explicit_interruption",
        "parenthetical_explicit_attribution",
    }
    confirmed_person = expected_speaker_type == "person" and _clean(raw.get("method")) in trusted_person_methods
    speaker_entity = builder.resolve(raw_speaker, expected_speaker_type, confirmed=confirmed_person) if raw_speaker else None
    speaker_resolution = _speaker_resolution(raw, speaker_entity, sentence, context)
    action = _canonical_action_for_speaker(raw_action, speaker_entity)
    medium_entity = _local_medium(builder, f"{context} {sentence}")
    raw_source_kind = _clean(raw.get("source_kind"))
    source_expected_type = raw_source_kind if raw_source_kind in {"medium", "institution", "party"} else None
    source_entity = builder.resolve(raw.get("source"), source_expected_type) if _clean(raw.get("source")) else None
    if not source_entity:
        source_entity = _local_editorial_source(builder, sentence, context, medium_entity)
    speaker_entity_type = _clean((speaker_entity or {}).get("entity_type"))
    affiliation = _local_affiliation(builder, _clean((speaker_entity or {}).get("canonical_name")) or raw_speaker, sentence, context) if speaker_entity_type == "person" else None
    institution = _local_institution(builder, _clean((speaker_entity or {}).get("canonical_name")) or raw_speaker, sentence, context) if speaker_entity_type == "person" else None
    target_entity, target_resolution_mode, raw_target = _target(
        builder, _clean(raw.get("target")), claim, sentence, _clean((speaker_entity or {}).get("entity_id"))
    )
    role_target, role_target_type, obj = _claim_object(action, claim, sentence, context)

    source = _clean((source_entity or {}).get("canonical_name")) or (_clean(raw.get("source")) if _clean(raw.get("source_kind")) == "source" else "")
    source_id = _clean((source_entity or {}).get("entity_id"))
    medium = _clean((medium_entity or {}).get("canonical_name"))
    program = _program(f"{context} {sentence}", medium)

    raw_document_index = int(raw.get("document_index") or 0)
    # Current: tożsamość dokumentu pochodzi bezpośrednio z resolvera. Nie
    # odtwarzamy jej ponownie z pozycji na globalnej liście.
    canonical_document_id = _clean(raw.get("document_id"))
    if not canonical_document_id:
        canonical_document_id = document_ids[raw_document_index] if 0 <= raw_document_index < len(document_ids) else "doc_0001_input"
    doc_meta = dict(document_metadata.get(canonical_document_id) or {})
    source = _canonical_source_for_document(source, doc_meta)
    if source == "Gazeta Wyborcza":
        canonical_source_entity = builder.resolve(source, "medium")
        source_id = _clean((canonical_source_entity or {}).get("entity_id")) or "medium:gazeta_wyborcza"
    local_document_sources, local_source_warnings = _sanitize_document_sources(doc_meta.get("document_sources") or [])
    local_image_sources = list(dict.fromkeys(_clean(value) for value in (doc_meta.get("image_sources") or []) if _clean(value)))

    topic = _topic(context, sentence, claim)
    target_name = _clean((target_entity or {}).get("canonical_name")) or role_target
    if not topic:
        topic = _fallback_topic(builder, claim, target_name)
    calibrated_confidence = _calibrated_confidence(raw, speaker_resolution, bool(source))

    relation: Dict[str, Any] = {
        "document_id": canonical_document_id,
        "document_index": raw_document_index,
        "segment_id": _segment_id(raw),
        "fragment_type": "wypowiedz" if speaker_entity else "ustalenie_zrodlowe",
        "speaker": _clean((speaker_entity or {}).get("canonical_name")),
        "speaker_entity_id": _clean((speaker_entity or {}).get("entity_id")),
        "speaker_kind": _clean((speaker_entity or {}).get("entity_type")),
        "speaker_role": "jawnie atrybuowany mówca" if speaker_entity else ("źródło przywołane" if source else "mówca nieustalony"),
        "speaker_action": action if speaker_entity else "",
        "speaker_resolution": speaker_resolution,
        "speaker_resolution_mode": _clean(speaker_resolution.get("mode")),
        "speaker_resolution_method": _clean(speaker_resolution.get("method")),
        "coreference_scope": _clean(raw.get("coreference_scope")),
        "coreference_score": float(raw.get("coreference_score") or 0.0),
        "coreference_gender_previous": _clean(raw.get("coreference_gender_previous")),
        "coreference_gender_current": _clean(raw.get("coreference_gender_current")),
        "coreference_gender_agreement": bool(raw.get("coreference_gender_agreement")),
        "attribution_marker": _clean(raw.get("attribution_marker")),
        "source": source,
        "source_entity_id": source_id,
        "source_kind": _clean((source_entity or {}).get("entity_type")) or _clean(raw.get("source_kind")),
        "document_source": str(doc_meta.get("publisher_source") or (local_document_sources[0] if local_document_sources else "")),
        "document_sources": list(local_document_sources[:1]),
        "publisher_source": str(doc_meta.get("publisher_source") or (local_document_sources[0] if local_document_sources else "")),
        "quoted_sources": list(doc_meta.get("quoted_sources") or []),
        "document_source_entity_id": "document_sources:" + _slug("|".join(local_document_sources)) if local_document_sources else "",
        "document_source_warnings": list(local_source_warnings),
        "image_sources": list(local_image_sources),
        "medium": medium,
        "medium_entity_id": _clean((medium_entity or {}).get("entity_id")),
        "program": program,
        "affiliation": _clean((affiliation or {}).get("canonical_name")),
        "affiliation_entity_id": _clean((affiliation or {}).get("entity_id")),
        "institution": _clean((institution or {}).get("canonical_name")),
        "institution_entity_id": _clean((institution or {}).get("entity_id")),
        "target": target_name,
        "target_entity_id": _clean((target_entity or {}).get("entity_id")),
        "target_type": _clean((target_entity or {}).get("entity_type")) or role_target_type,
        "target_resolution_mode": target_resolution_mode if target_entity else ("role_target" if role_target else "none"),
        "target_raw": raw_target,
        "target_quality": "canonical_claim_local" if target_entity else ("canonical_role" if role_target else "no_target"),
        "topic": topic,
        "object": obj,
        "claim": claim,
        "claim_subject": "",
        "claim_subject_entity_id": "",
        "claim_action": "",
        "claim_object": obj,
        "evidence": list(dict.fromkeys(value for value in (sentence, context) if value)),
        "confidence": calibrated_confidence,
        "raw_confidence": round(max(0.0, min(1.0, float(raw.get("confidence") or 0.0))), 3),
        "warnings": list(dict.fromkeys(raw.get("warnings") or [])),
        "attribution_method": _clean(raw.get("method")),
        "sentence": sentence,
        "context_sentence": context,
        "block_index": raw.get("block_index"),
        "sentence_index": raw.get("sentence_index"),
        "pipeline_stage": "canonical_relation_v1",
        "implementation_stage": STAGE,
        "roles_separated": True,
        "roles_strict": True,
        "single_source_of_truth": True,
        "speaker_contract": "canonical_speaker_v1",
        "speaker_action_surface": raw_action,
    }
    relation["relation_id"] = _relation_id(relation)
    return relation



def _sanitize_document_sources(values: Iterable[str]) -> tuple[List[str], List[str]]:
    """Oddziela jakość metadanych od jakości relacji.

    Błędna lub niepełna linia źródła nie może skasować poprawnie przypisanej
    wypowiedzi. Rozpoznane domeny są kanonizowane, a zdania i śmieci trafiają
    do ostrzeżeń dokumentu zamiast do bramki relacji.
    """
    aliases = {
        "tvn24.pl": "TVN24",
        "www.tvn24.pl": "TVN24",
        "pap.pl": "PAP",
        "www.pap.pl": "PAP",
    }
    clean: List[str] = []
    rejected: List[str] = []
    for raw in values or []:
        value = _clean(raw)
        if not value:
            continue
        canonical = aliases.get(value.casefold(), value)
        # Dopuszczamy kontrolowane nazwy, domeny oraz krótkie nazwy własne.
        # Fragment zdania z jawnej linii „Źródło:” trafia do ostrzeżeń, lecz
        # nigdy nie unieważnia poprawnej relacji wypowiedzi.
        is_domain = bool(re.fullmatch(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+", value, re.I))
        words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9.-]+", value)
        known = value.casefold() in aliases or value.casefold() in {
            "tvn24", "pap", "reuters", "afp", "ap", "haaretz", "kalkalist", "calcalist"
        }
        proper_name = bool(words) and len(words) <= 4 and all(
            token.isupper() or token[:1].isupper() or re.fullmatch(r"[A-Z]{2,}[0-9]*", token)
            for token in words
        )
        looks_sentence = bool(
            re.search(r"[!?]", value)
            or re.search(r"\b(?:jest|są|był|była|byli|został|została|zostało|rozpoczęło|przegłosowała|dotarł|funkcjonariusze|który|która|które|nie\s+powinno)\b", value, re.I)
        )
        if len(value) > 70 or len(words) > 6 or (not known and not is_domain and (looks_sentence or not proper_name)):
            rejected.append(value)
            continue
        if canonical not in clean:
            clean.append(canonical)
    return clean, rejected


def _normalized_claim_key(value: Any) -> str:
    text = _clean(value).casefold()
    text = re.sub(r'^["„”\s]+|["„”\s]+$', '', text)
    text = re.sub(r"[^a-z0-9ąćęłńóśźż]+", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _deduplicate_relations(relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scala identyczne twierdzenia bez utraty informacji o dokumentach.

    Ten sam boilerplate bywa kopiowany do kilku artykułów. Jedna relacja pozostaje
    publiczna, a wszystkie dokumenty i pierwotne relation_id są zachowane jako dowód.
    """
    output: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    for source_row in relations:
        row = dict(source_row)
        actor = _clean(row.get("speaker_entity_id") or row.get("speaker") or row.get("source_entity_id") or row.get("source")).casefold()
        claim = _normalized_claim_key(row.get("claim"))
        key = f"{actor}|{claim}"
        # Krótkich fraz bez aktora/źródła nie scalamy — byłyby zbyt ogólne.
        if not actor or len(claim.split()) < 4:
            output.append(row)
            continue
        existing = index.get(key)
        if existing is None:
            row["supporting_document_ids"] = [_clean(row.get("document_id"))] if _clean(row.get("document_id")) else []
            row["supporting_relation_ids"] = [_clean(row.get("relation_id"))] if _clean(row.get("relation_id")) else []
            row["deduped_repetitions_count"] = 0
            index[key] = row
            output.append(row)
            continue

        for field in ("document_id",):
            value = _clean(row.get(field))
            if value and value not in existing["supporting_document_ids"]:
                existing["supporting_document_ids"].append(value)
        relation_id = _clean(row.get("relation_id"))
        if relation_id and relation_id not in existing["supporting_relation_ids"]:
            existing["supporting_relation_ids"].append(relation_id)
        existing["deduped_repetitions_count"] = int(existing.get("deduped_repetitions_count") or 0) + 1
        for field in ("source", "source_entity_id", "medium", "medium_entity_id", "program", "target", "target_entity_id", "topic", "object"):
            if not _clean(existing.get(field)) and _clean(row.get(field)):
                existing[field] = row[field]
        existing["evidence"] = list(dict.fromkeys([*(existing.get("evidence") or []), *(row.get("evidence") or [])]))
        existing["document_sources"] = list(dict.fromkeys([*(existing.get("document_sources") or []), *(row.get("document_sources") or [])]))
        existing["quoted_sources"] = list(dict.fromkeys([*(existing.get("quoted_sources") or []), *(row.get("quoted_sources") or [])]))
        existing["warnings"] = list(dict.fromkeys([*(existing.get("warnings") or []), "deduplicated_repeated_claim", *(row.get("warnings") or [])]))
    return output


def build_relation_pipeline(
    text: str,
    *,
    document_sources: Iterable[str] | None = None,
    image_sources: Iterable[str] | None = None,
    document_ids: Iterable[str] | None = None,
    document_metadata: Dict[str, Dict[str, Any]] | None = None,
    document_texts: Dict[str, str] | None = None,
    segments: List[Dict[str, Any]] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    document_sources, metadata_source_warnings = _sanitize_document_sources(document_sources or [])
    image_sources = list(dict.fromkeys(_clean(value) for value in (image_sources or []) if _clean(value)))
    document_ids = list(dict.fromkeys(_clean(value) for value in (document_ids or []) if _clean(value)))
    document_metadata = dict(document_metadata or {})
    document_texts = dict(document_texts or {})
    if not document_texts:
        grouped_doc_texts: Dict[str, List[str]] = {}
        for seg in segment_document(text):
            if seg.analyzable and _clean(seg.text):
                grouped_doc_texts.setdefault(seg.document_id, []).append(_clean(seg.text))
        document_texts = {doc_id: " ".join(parts) for doc_id, parts in grouped_doc_texts.items()}
    fallback_builder = CanonicalEntityBuilder(text)
    builders = {doc_id: CanonicalEntityBuilder(doc_text) for doc_id, doc_text in document_texts.items() if _clean(doc_text)}
    bundle = resolve_structural_relation_bundle(text, segments=segments)
    raw_relations = list(bundle.get("relations") or [])
    lead = _lead_source_relation(text)
    if lead and not any(_clean(row.get("sentence")).casefold() == _clean(lead.get("sentence")).casefold() for row in raw_relations):
        # Syntetyczna relacja lead nie dostaje własnej tożsamości dokumentu.
        # Używa dokładnie identyfikatora przekazanego przez PipelineContext.
        if document_ids:
            lead["document_id"] = document_ids[0]
            lead["document_index"] = int((document_metadata.get(document_ids[0]) or {}).get("document_index", 0) or 0)
        raw_relations.insert(0, lead)

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for raw in raw_relations:
        raw_doc_id = _clean(raw.get("document_id"))
        builder = builders.get(raw_doc_id, fallback_builder)
        relation = _canonicalize(raw, builder, document_sources, image_sources, document_ids, document_metadata)
        verdict = validate_relation(relation)
        if not verdict.accepted:
            rejected.append({**relation, "rejected": True, "reasons": verdict.reasons})
            continue
        if relation["relation_id"] in seen:
            continue
        seen.add(relation["relation_id"])
        accepted.append(relation)

    for row in bundle.get("rejections") or []:
        rejected.append({
            "relation_id": "",
            "sentence": _clean(row.get("sentence")),
            "claim": "",
            "rejected": True,
            "reasons": [_clean(row.get("reason")) or "unresolved_relation"],
        })

    accepted = _deduplicate_relations(accepted)

    # Current: odrzucone kandydaty deduplikujemy w modelu danych, nie dopiero w UI.
    deduped_rejected: List[Dict[str, Any]] = []
    rejected_seen: set[str] = set()
    for row in rejected:
        # Current: ta sama odrzucona fraza z tym samym powodem jest jedną blokadą.
        # Część niskopoziomowych rejections nie ma jeszcze document_id, więc nie
        # może to tworzyć drugiej karty dla identycznego zdania.
        fingerprint = "|".join((
            _clean(row.get("sentence") or row.get("claim")).casefold(),
            ",".join(sorted(_clean(x) for x in (row.get("reasons") or []) if _clean(x))),
        ))
        if fingerprint in rejected_seen:
            continue
        rejected_seen.add(fingerprint)
        deduped_rejected.append(row)
    rejected = deduped_rejected

    return {
        "accepted_relations": accepted,
        "rejected_relations": rejected,
        "accepted_cards": accepted_cards(accepted),
        "rejected_cards": rejected_cards(rejected),
        "registry": [entity for b in (list(builders.values()) or [fallback_builder]) for entity in b.entities()],
        "metadata_source_warnings": metadata_source_warnings,
    }
