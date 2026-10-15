from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .text_tools import build_text_overview, stable_api_shape
from .suggestions import build_clean_suggestions, polish_suggestions_summary
from .text_cleaning import split_source_and_meta
from .guards import build_guard_cards
from .semantic_candidates import detect_semantic_candidate_specs
from .canonical_entity_builder import (
    build_canonical_entity_cards_from_relations,
    build_canonical_source_cards_from_relations,
    build_canonical_affiliation_cards_from_relations,
)
from .fact_opinion_quote import detect_fact_opinion_quote_cards, summarize_claim_types
from .relation_pipeline import build_relation_pipeline
from .pipeline_context import build_pipeline_context
from .entity_grouping import build_entity_group_cards
from .canonical_relation import synchronize_public_relation_fields
from .version import STAGE
ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"

PL_TRANS = str.maketrans({
    "ą":"a","ć":"c","ę":"e","ł":"l","ń":"n","ó":"o","ś":"s","ź":"z","ż":"z",
    "Ą":"a","Ć":"c","Ę":"e","Ł":"l","Ń":"n","Ó":"o","Ś":"s","Ź":"z","Ż":"z",
})

TECHNICAL_WORDS = re.compile(r"\b(?:termin|koszt|koszty|harmonogram|metodolog|procedur|autor(?:zy|ow|ów)?|zgodno[śs]ć|konsultacj|wej[śs]cia|komisja|ekspert(?:ow|ów)?|raport|wymieniono|miasto|miasta)\b", re.I)
CITY_WORDS = re.compile(r"\b(?:Warszawa|Krak[oó]w|Gda[nń]sk|Pozna[nń]|Wroc[łl]aw|[ŁL]ód[źz]|Lublin|Katowice|Szczecin|Bydgoszcz)\b", re.I)

ARGUMENT_CONTEXT = re.compile(
    r"\b(?:rząd|rzad|ustaw|reform|projekt|państw|panstw|obywatel|opozycj|krytyk|zwolennik|przeciwnik|"
    r"polityk|władzy|wladzy|instytucj|kontrol|bezpieczeństw|bezpieczenstw|odpowiedzialn|decyzj|"
    r"społeczn|spoleczn|praw|demokrac|nadzor|centralizac|jawno[śs]ć|ryzyko|zagroż|zagroz|chaos|kryzys|"
    r"naduży|naduzy|ogranicz|osłab|oslab|ukry|manipul|narrac|ramow|dialog|rytuał|rytual|"
    r"rewitalizac\w*|wysiedl\w*|relokac\w*|mieszkańc\w*|mieszkanc\w*|wymian\w*|przemoc\w*|gentryfikac\w*)\b", re.I)
VALUE_CONTEXT = re.compile(r"\b(?:chaos|kryzys|ryzyko|zagroż|zagroz|naduży|naduzy|osłab|oslab|ogranicz|odpowiedzialn|stabiln|skuteczn|bezpieczeństw|bezpieczenstw|kontrol|jawno[śs]ć|porządek|porzadek|centralizac|wysiedl\w*|relokac\w*|wymian\w*|przemoc\w*|gentryfikac\w*|rytuał|rytual)\b", re.I)
NARRATIVE_NEUTRAL = re.compile(r"\b(?:ludzie|książk|ksiazk|rozmow|schronien|zegark|miasto|dzielnic|port|budynk|klatki|schodow|deszcz|wiatr|bibliotek|szpital|ulic|oknach|mieszkał|mieszkaly|przychodzili|siedzieli|patrzyli)\b", re.I)

# O5: słownik języka administracyjno-eufemizującego. To nie jest jeszcze
# jawna warstwa reguł dla tekstów urzędowych,
# miejskich i medialnych. Reguły są ostrożne: samo słowo „transformacja” nie
# zawsze jest manipulacją, ale w pobliżu mieszkańców/lokatorów/decyzji może
# stać się istotnym sygnałem łagodzenia straty albo ukrywania sprawczości.
EUPHEMISM_TERMS_RX = re.compile(
    r"\b(?:relokacj\w*|optymalizacj\w*|reorganizacj\w*|racjonalizacj\w*|"
    r"przeniesieni\w*\s+zasobu|zas[oó]b\s+lokalow\w*|program\s+os[łl]onow\w*|"
    r"czasow\w*\s+zmian\w*\s+miejsca\s+zamieszkania|alternatywn\w*\s+[śs]cie[żz]k\w*\s+zamieszkania|"
    r"obj[ęe]ci\s+wsparciem|indywidualn\w*\s+wsparci\w*|popraw\w*\s+standard\w*|"
    r"interesariusz\w*|transformacj\w*)\b",
    re.I,
)

ADMIN_LANGUAGE_RX = re.compile(
    r"\b(?:proces\s+zostanie\s+uruchomion\w*|rozwi[ąa]zania\s+zostan[ąa]\s+wdro[żz]on\w*|"
    r"decyzj\w*\s+zostan[ąa]\s+podj[ęe]t\w*|potrzeb\w*\s+zostan[ąa]\s+rozpoznan\w*|lokal\w*\s+zostan[ąa]\s+wskazan\w*|"
    r"ka[żz]d\w*\s+przypad\w*\s+b[ęe]dzie\s+analizowan\w*\s+indywidualnie|"
    r"w\s+przypadkach,?\s+w\s+kt[oó]rych\s+b[ęe]dzie\s+to\s+(?:technicznie,?\s+prawnie,?\s+i\s+ekonomicznie\s+)?mo[żz]liwe|"
    r"z\s+poszanowaniem\s+interesu\s+spo[łl]ecznego|"
    r"w\s+trosce\s+o\s+sprawny\s+przebieg\s+procesu|"
    r"w\s+celu\s+uwzgl[ęe]dnienia\s+pa[ńn]stwa\s+indywidualnej\s+sytuacji)\b",
    re.I,
)



# O6: nominalizacje — rzeczownikowe ujęcie działań/procesów, które może
# osłabiać widoczność sprawcy i skutku. Reguły są kontekstowe: neutralna
# „analiza danych” nie powinna być mocną techniką, ale „podjęcie decyzji”
# albo „optymalizacja zasobu lokalowego” w kontekście mieszkańców/lokali tak.
NOMINALIZATION_TERMS_RX = re.compile(
    r"\b(?:podj[ęe]ci\w*\s+decyzj\w*|uruchomieni\w*\s+procesu|wdro[żz]eni\w*\s+rozwi[ąa]za[ńn]\w*|"
    r"przeprowadzeni\w*\s+relokacj\w*|optymalizacj\w*\s+zasob\w*|optymalizacj\w*\s+lokal\w*|"
    r"reorganizacj\w*\s+funkcj\w*|reorganizacj\w*\s+zasob\w*|racjonalizacj\w*\s+koszt\w*|"
    r"aktywizacj\w*\s+przestrzen\w*|przeniesieni\w*\s+zasobu|mapowani\w*\s+oczekiwa[ńn]\w*|"
    r"rozpoznani\w*\s+potrzeb\w*|relokacj\w*\s+funkcj\w*|zmian\w*\s+funkcj\w*\s+mieszkaniow\w*|"
    r"racjonalizacj\w*\s+wykorzystani\w*|czasow\w*\s+reorganizacj\w*\s+uprawnie[ńn]\w*|"
    r"etapow\w*\s+reorganizacj\w*|optymalizacj\w*\s+rozmieszczeni\w*|"
    r"przeniesieni\w*\s+koszt\w*|minimalizacj\w*\s+uci[ąa][żz]liwo[śs]ci|"
    r"kompensacj\w*\s+spo[łl]eczn\w*)\b",
    re.I,
)

NEUTRAL_NOMINALIZATION_CONTEXT_RX = re.compile(
    r"\b(?:analiza\s+danych|badanie\s+laboratoryjne|wdro[żz]enie\s+aplikacji|"
    r"uruchomienie\s+serwera|optymalizacja\s+kodu|transformacja\s+energetyczna)\b",
    re.I,
)

HUMAN_AFFECTED_RX = re.compile(
    r"\b(?:lokator\w*|najemc\w*|mieszka[ńn]c\w*|gospodarstw\w*\s+domow\w*|"
    r"rodzin\w*|dziec\w*|senior\w*|os[oó]b\w*\s+starsz\w*|u[żz]ytkownik\w*\s+lokal\w*)\b",
    re.I,
)

ADMIN_PASSIVE_RX = re.compile(r"\b(?:zostan[ąa]|zostanie|b[ęe]dzie\s+analizowan\w*|b[ęe]d[ąa]\s+podejmowan\w*)\b", re.I)


# O7: ukrycie sprawcy — zdania, w których decyzja lub działanie wobec ludzi/lokali
# jest opisane stroną bierną albo bezosobową formułą proceduralną. O7 nie oznacza
# każdej strony biernej; neutralne techniczne pasywy są ignorowane albo zostają
# kandydatem, jeśli nie ma kontekstu społecznego.
AGENT_HIDING_RX = re.compile(
    r"\b(?:decyzj\w*\s+zostan[ąa]\s+podj[ęe]t\w*|lokal\w*\s+zostan[ąa]\s+wskazan\w*|"
    r"proces\s+zostanie\s+uruchomion\w*|rozwi[ąa]zania\s+zostan[ąa]\s+wdro[żz]on\w*|"
    r"potrzeb\w*\s+zostan[ąa]\s+rozpoznan\w*|sytuacj\w*\s+(?:\w+\s+){0,4}zostan[ąa]\s+przeanalizowan\w*|sytuacj\w*\s+(?:\w+\s+){0,4}zostanie\s+przeanalizowan\w*|"
    r"mieszka[ńn]c\w*\s+zostan[ąa]\s+obj[ęe]c\w*\s+(?:wsparciem|procesem)|lokator\w*\s+zostan[ąa]\s+obj[ęe]c\w*\s+(?:wsparciem|procesem)|"
    r"najemc\w*\s+zostan[ąa]\s+obj[ęe]c\w*\s+(?:wsparciem|programem)|"
    r"ka[żz]d\w*\s+przypad\w*\s+b[ęe]dzie\s+analizowan\w*\s+indywidualnie|"
    r"umow\w*\s+zostan[ąa]\s+przygotowan\w*|czynsz\w*\s+zostan[ąa]\s+ustalon\w*|"
    r"gwarancj\w*\s+zostan[ąa]\s+okre[śs]lon\w*|termin\w*\s+zostan[ąa]\s+wyznaczon\w*)\b",
    re.I,
)

BEZOSOBOWE_DECYZJE_RX = re.compile(
    r"\b(?:podj[ęe]to\s+decyzj\w*|zaplanowano\s+przeniesieni\w*|przeniesieni\w+\s+lokator\w*\s+zaplanowano|przewidziano\s+relokacj\w*|"
    r"wskazano\s+lokal\w*|ustalono\s+harmonogram|zdecydowano\s+o\s+przeniesieni\w*|"
    r"uznano\s+za\s+konieczn\w*)\b",
    re.I,
)

NEUTRAL_PASSIVE_CONTEXT_RX = re.compile(
    r"\b(?:serwer\s+zostanie\s+uruchomiony|plik\s+zostanie\s+zapisany|"
    r"wynik\s+zostanie\s+obliczony|raport\s+zostanie\s+wygenerowany|"
    r"aplikacja\s+zostanie\s+wdro[żz]ona|kod\s+zostanie\s+zoptymalizowany)\b",
    re.I,
)


# O8: depolityzacja decyzji — sytuacja, w której decyzja społeczna/polityczna
# jest opisana jako neutralna konieczność techniczna, ekonomiczna albo procedura.
# To jest rama P3, nie prosty werdykt z jednego słowa.
DEPOLITICIZATION_MARKERS_RX = re.compile(
    r"\b(?:wynika\s+z\s+konieczno[śs]ci|konieczno[śs][ćc]\s+optymalizacj\w*|"
    r"wymog\w*\s+(?:techniczn\w*|ekonomiczn\w*|prawn\w*)|uwarunkowa[ńn]\w*\s+(?:techniczn\w*|ekonomiczn\w*|prawn\w*)|"
    r"charakter\s+techniczn\w*|kwesti\w*\s+techniczn\w*|standardow\w*\s+element\w*\s+procesu|"
    r"proces\s+strategiczn\w*|racjonalizacj\w*|optymalizacj\w*|ze\s+wzgl[ęe]d[oó]w\s+(?:techniczn\w*|ekonomiczn\w*|prawn\w*)|"
    r"nie\s+jeste[śs]my\s+(?:dzi[śs]\s+)?na\s+etapie\s+decyzj\w*\s+indywidualn\w*|"
    r"po\s+zako[ńn]czeniu\s+prac\s+analityczn\w*|w\s+[śs]wietle\s+analiz|"
    r"z\s+punktu\s+widzenia\s+(?:technicznego|ekonomicznego|prawnego))\b",
    re.I,
)

DEPOLITICIZATION_SOCIAL_CONTEXT_RX = re.compile(
    r"\b(?:decyzj\w*|uchwa[łl]\w*|konsultacj\w*|mieszka[ńn]c\w*|lokator\w*|najemc\w*|"
    r"lokal\w*|mieszka[ńn]\w*|czynsz\w*|gwarancj\w*|relokacj\w*|przeniesieni\w*|wysiedl\w*|"
    r"rewitalizacj\w*|transformacj\w*|inwestycj\w*|grunt\w*|zas[oó]b\s+lokalow\w*|program\s+os[łl]onow\w*)\b",
    re.I,
)

NEUTRAL_DEPOLITICIZATION_CONTEXT_RX = re.compile(
    r"\b(?:optymalizacja\s+kodu|optymalizacja\s+zapytania|serwer\w*|plik\w*|algorytm\w*|"
    r"test\w*\s+jednostkow\w*|kompilacj\w*|baza\s+danych|procedura\s+testow\w*)\b",
    re.I,
)

# Słabsze markery O8 są wieloznaczne. „Optymalizacja” i „racjonalizacja”
# występują również w neutralnych opisach kosztów, harmonogramów i audytów.
# Same nie mogą więc tworzyć ramy depolityzacji bez wskazania ludzi, których
# decyzja dotyczy, oraz bez języka przymusu/proceduralnego ukrycia sprawcy.
WEAK_DEPOLITICIZATION_MARKER_RX = re.compile(
    r"\b(?:proces\s+strategiczn\w*|racjonalizacj\w*|optymalizacj\w*|"
    r"po\s+zako[ńn]czeniu\s+prac\s+analityczn\w*|w\s+[śs]wietle\s+analiz)\b",
    re.I,
)

LEGAL_PROCEDURE_CONTEXT_RX = re.compile(
    r"\b(?:areszt\w*|tymczasow\w*\s+areszt\w*|podejrzan\w*|oskar[żz]on\w*|"
    r"prokurator\w*|prokuratur\w*|s[ąa]d\w*|post[ęe]powan\w*|zarzut\w*|"
    r"wymiar\w*\s+kary|woln\w*\s+cz[łl]owiek\w*)\b",
    re.I,
)

PUBLIC_SECURITY_POLICY_RX = re.compile(
    r"\b(?:bezpiecze[ńn]stw\w*\s+(?:narodow\w*|pa[ńn]stw\w*|publiczn\w*|Europ\w*)|"
    r"obron\w*|wojn\w*|atak\w*|agresj\w*|granica\w*|schron\w*|"
    r"zarz[ąa]dzani\w*\s+kryzysow\w*|ochron\w*\s+ludno[śs]ci)\b",
    re.I,
)



# O9: naturalizacja konieczności — decyzja, projekt lub linia działania jest
# przedstawiana jako nieunikniona, oczywista albo wymuszona przez „rzeczywistość”.
# To rama P3, a nie werdykt z pojedynczego słowa. Wymaga kontekstu społecznego,
# miejskiego, politycznego lub instytucjonalnego; neutralne techniczne użycia
# („nie ma alternatywy dla algorytmu”) są ignorowane.
NATURALIZATION_MARKERS_RX = re.compile(
    r"\b(?:miasto\s+nie\s+mo[żz]e\s+d[łl]u[żz]ej\s+czeka[ćc]|"
    r"nie\s+mo[żz]emy\s+pozwoli[ćc]\s+sobie\s+na\s+luksus\s+stagnacji|"
    r"matematyka\s+jest\s+nieub[łl]agana|nie\s+mo[żz]emy\s+obra[żz]a[ćc]\s+si[ęe]\s+na\s+rzeczywisto[śs][ćc]|"
    r"(?:rozw[oó]j|transformacj\w*|modernizacj\w*|zmian\w*)\s+(?:jest\s+)?konieczn\w*|"
    r"(?:rozw[oó]j|transformacj\w*|modernizacj\w*|zmian\w*)\s+musi\s+(?:nast[ąa]pi[ćc]|si[ęe]\s+dokona[ćc])|"
    r"nie\s+ma\s+(?:realnej\s+)?alternatywy|jedyn\w*\s+(?:realn\w*\s+)?(?:drog\w*|wyb[oó]r|rozwi[ąa]zani\w*)|"
    r"czas\s+dzia[łl]a\s+na\s+niekorzy[śs][ćc]|trzeba\s+podj[ąa][ćc]\s+trudn\w*\s+decyzj\w*|"
    r"odpowiedzialno[śs][ćc]\s+wymaga\s+(?:trudn\w*\s+)?decyzj\w*|"
    r"nie\s+da\s+si[ęe]\s+inaczej|takie\s+s[ąa]\s+realia|rzeczywisto[śs][ćc]\s+jest\s+nieub[łl]agana)\b",
    re.I,
)

NATURALIZATION_SOCIAL_CONTEXT_RX = re.compile(
    r"\b(?:miast\w*|ratusz\w*|urz[ąa]d\w*|samorz[ąa]d\w*|rada\s+miasta|prezydent\w*|"
    r"mieszka[ńn]c\w*|lokator\w*|najemc\w*|lokal\w*|mieszka[ńn]\w*|czynsz\w*|"
    r"rewitalizacj\w*|relokacj\w*|wysiedl\w*|przeniesieni\w*|transformacj\w*|modernizacj\w*|"
    r"inwestycj\w*|projekt\w*|uchwa[łl]\w*|decyzj\w*|strategi\w*|program\w*|interes\s+spo[łl]eczn\w*|rozw[oó]j\w*)\b",
    re.I,
)

NEUTRAL_NATURALIZATION_CONTEXT_RX = re.compile(
    r"\b(?:algorytm\w*|kod\w*|serwer\w*|plik\w*|test\w*|kompilacj\w*|baza\s+danych|"
    r"fizyka|chemia|matematyka\s+szkolna|r[oó]wnani\w*|procedura\s+testow\w*)\b",
    re.I,
)


# O10: rama „rozsądek kontra emocje” — tekst ustawia jedną stronę jako
# racjonalną, odpowiedzialną i techniczną, a drugą jako emocjonalną,
# sentymentalną, przestraszoną albo blokującą rozwój. To rama P3, więc
# wymaga kontekstu społecznego/medialnego; neutralne opisy psychologiczne
# lub techniczne nie są oznaczane.
RATIONALITY_EMOTION_MARKERS_RX = re.compile(
    r"\b(?:emocj\w*(?:\s+\w+){0,5}\s+s[ąa]\s+zrozumia[łl]\w*,?\s+ale|"
    r"emocj\w*(?:\s+\w+){0,6}\s+nie\s+mog[ąa]\s+zast[ąa]pi[ćc]|"
    r"sentyment\w*(?:\s+\w+){0,5}\s+nie\s+mo[żz]e(?:\s+zatrzyma[ćc]|\s+blokowa[ćc])?|"
    r"trzeba\s+zachowa[ćc]\s+rozs[ąa]dek|nie\s+mo[żz]na\s+kierowa[ćc]\s+si[ęe]\s+strach\w*|"
    r"racjonaln\w*\s+decyzj\w*|odpowiedzialn\w*\s+zarz[ąa]dzani\w*|"
    r"wymog\w*\s+nowoczesn\w*\s+zarz[ąa]dzani\w*\s+s[ąa]\s+wa[żz]niejsz\w*\s+ni[żz]\s+sentyment|wymog\w*\s+nowoczesn\w*\s+zarz[ąa]dzani\w*|"
    r"kieruj[ąa]\s+si[ęe]\s+(?:l[ęe]kiem|strachem)|"
    r"l[ęe]k\w*\s+przed\s+zmian\w*|strach\w*\s+przed\s+zmian\w*|"
    r"emocjonaln\w*\s+szanta[żz]\w*|blokowani\w*\s+rozwoj\w*|"
    r"sentyment\w*\s+mo[żz]e\s+zatrzyma[ćc]\s+rozwoj\w*|"
    r"rozs[ąa]dek\w*\s+kontra\s+emocj\w*)\b",
    re.I,
)

RATIONALITY_EMOTION_SOCIAL_CONTEXT_RX = re.compile(
    r"\b(?:mieszka[ńn]c\w*|lokator\w*|najemc\w*|aktywist\w*|protest\w*|spo[łl]eczno[śs]\w*|"
    r"media\w*|redakcj\w*|urz[ąa]d\w*|ratusz\w*|samorz[ąa]d\w*|prezydent\w*|"
    r"miast\w*|projekt\w*|decyzj\w*|uchwa[łl]\w*|rewitalizacj\w*|relokacj\w*|"
    r"wysiedl\w*|modernizacj\w*|rozwoj\w*|inwestycj\w*|konsultacj\w*|kamienic\w*)\b",
    re.I,
)

NEUTRAL_RATIONALITY_EMOTION_CONTEXT_RX = re.compile(
    r"\b(?:model\s+rozpoznawania\s+emocji|badani\w*\s+emocji|psycholog\w*|terapi\w*|"
    r"ankiet\w*\s+emocji|emocje\s+w\s+filmie|reakcj\w*\s+emocjonaln\w*\s+u\s+dzieci)\b",
    re.I,
)

def _load_json(name: str, default: Any) -> Any:
    path = KNOWLEDGE_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

P0_MARKERS: Dict[str, List[str]] = _load_json("p0_markers.json", {})
P1_STRUCTURES: Dict[str, Any] = _load_json("p1_structures.json", {})
P2_PATTERNS: Dict[str, Any] = _load_json("p2_patterns.json", {})
THEORY_MAP: Dict[str, Any] = _load_json("theory_map.json", {})

@dataclass
class Card:
    label: str
    level: str
    role: str
    fragment: str
    phrase: str = ""
    start: int = -1
    end: int = -1
    # O2: rozdzielenie pewności dopasowania wzorca od pewności interpretacji.
    # Pole confidence zostaje dla stałego kontraktu API i oznacza widoczną
    # ogólną pewność karty, ale UI/API dostają też dwa jawne pola poniżej.
    confidence: str = "medium"
    pattern_confidence: str | None = None
    interpretation_confidence: str | None = None
    score: float = 0.0
    why: str = ""
    guards: List[str] | None = None
    requires_review: bool = False
    part_a: str | None = None
    part_b: str | None = None
    source: str = "scientific_structural_classifier"
    blocked_promotion_to: List[str] | None = None
    theory: Dict[str, Any] | None = None
    analytical_relevance: str = "unknown"
    visibility: str = "default"
    # Aktualna warstwa: nowa, szczegółowa skala analityczna P0–P5.
    # Pole level zostaje stałe dla kontraktu API; analysis_level
    # mówi dokładniej, czy karta jest markerem, strukturą, techniką, ramą,
    # strategią czy diagnozą syntetyczną.
    analysis_level: str | None = None
    analysis_level_name: str | None = None
    rank_score: float = 0.0
    # Current: jawna tożsamość dokumentu i oba układy współrzędnych podświetlenia.
    document_id: str = ""
    document_local_start: int = -1
    document_local_end: int = -1
    # P4/P5 muszą wskazywać rzeczywiste, dosłowne fragmenty tekstu, z których
    # powstała synteza. To usuwa wcześniejsze „dowody” będące opisem reguły.
    evidence_fragments: List[str] | None = None
    supporting_labels: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        # O2: jeżeli karta nie podała osobnych pewności,
        # ustawiamy bezpieczne wartości domyślne. Dzięki temu zmiana jest
        # stała dla testów i endpointów.
        if self.pattern_confidence is None:
            self.pattern_confidence = self.confidence
        if self.interpretation_confidence is None:
            self.interpretation_confidence = self.confidence
        d = asdict(self)
        d["guards"] = d["guards"] or []
        d["blocked_promotion_to"] = d["blocked_promotion_to"] or []
        d["evidence_fragments"] = d["evidence_fragments"] or []
        d["supporting_labels"] = d["supporting_labels"] or []
        if self.analysis_level is None:
            _apply_o4_level_and_rank(self)
        d["analysis_level"] = self.analysis_level
        d["analysis_level_name"] = self.analysis_level_name
        d["rank_score"] = self.rank_score
        d["theory"] = d["theory"] or THEORY_MAP.get(self.label, {})
        return d


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def norm_ascii(text: str) -> str:
    return normalize(text).translate(PL_TRANS).lower()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wąćęłńóśźż]+\b", text or "", re.I))


def sentences(text: str) -> List[Tuple[int, int, str]]:
    text = text or ""
    out: List[Tuple[int, int, str]] = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text, re.U):
        frag = text[m.start():m.end()].strip()
        if frag:
            out.append((m.start(), m.end(), frag))
    if not out and text.strip():
        out.append((0, len(text), text.strip()))
    return out


def find_phrase(text: str, phrase: str) -> List[Tuple[int, int, str]]:
    if not phrase:
        return []
    # Warstwa P0: marker P0 ma być samodzielnym słowem/frazą.
    # Wcześniej `ale` wpadało w imiona: MagdALEna, ZALEwska, ALEksandra.
    # Używamy własnych granic znaków słowa dla polskich liter, bo zwykłe `\b`
    # bywa niewystarczająco czytelne przy audycie podświetleń.
    word_chars = r"A-Za-z0-9_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
    core = re.escape(phrase.strip()).replace(r"\ ", r"\s+")
    pattern = rf"(?<![{word_chars}]){core}(?![{word_chars}])"
    return [(m.start(), m.end(), text[m.start():m.end()]) for m in re.finditer(pattern, text, re.I | re.U)]


def context_for(text: str, start: int, end: int) -> str:
    for s, e, frag in sentences(text):
        if start >= s and end <= e:
            return frag
    return text[max(0, start - 80):min(len(text), end + 120)].strip()


def add_unique(cards: List[Card], card: Card):
    # Jedna technika ma jedną kartę na ten sam fragment. Różne walidatory
    # mogą znaleźć tę samą strukturę z innym opisem ``phrase``; publikowanie
    # obu kart zawyżało liczniki i wyglądało jak dwa niezależne dowody.
    key = (card.label, card.role, normalize(card.fragment))
    for c in cards:
        if (c.label, c.role, normalize(c.fragment)) == key:
            return
    cards.append(card)


def analytical_relevance(sentence: str, label: str) -> Tuple[str, float, List[str]]:
    """Ocena, czy struktura językowa ma znaczenie analityczne, czy jest tylko opisowa/fabularna."""
    n = norm_ascii(sentence)
    reasons: List[str] = []
    score = 0.0
    if ARGUMENT_CONTEXT.search(sentence):
        score += 2.0
        reasons.append("kontekst publicystyczny/instytucjonalny/społeczny")
    if VALUE_CONTEXT.search(sentence):
        score += 1.5
        reasons.append("obecne słownictwo wartościujące lub konfliktowe")
    if re.search(r"\b(?:mafia|złodziejstw\w*|patologi\w*|tchórzofretk\w*|świstk\w* papieru|rozwibrowan\w*|obrzydliw\w*|korupcj\w*|polityczn\w* hucp\w*|całkowit\w* bzdur\w*|bełkot\w*|pseudokomisj\w*|minister\w* bezprawi\w*)\b", sentence, re.I):
        score += 3.0
        reasons.append("Q1.2: silna ocena, delegitymizacja lub przypisanie odpowiedzialności")
    if label in {"P1_eufemizacja", "P1_jezyk_administracyjny", "P1_nominalizacja", "P1_ukrycie_sprawcy"}:
        if EUPHEMISM_TERMS_RX.search(sentence) or ADMIN_LANGUAGE_RX.search(sentence) or NOMINALIZATION_TERMS_RX.search(sentence) or AGENT_HIDING_RX.search(sentence) or BEZOSOBOWE_DECYZJE_RX.search(sentence):
            score += 2.2
            reasons.append("O5/O6/O7: język administracyjno-eufemizujący, nominalizacyjny lub ukrywający sprawcę")
        if HUMAN_AFFECTED_RX.search(sentence):
            score += 1.4
            reasons.append("O5: dotyczy ludzi/lokatorów/mieszkańców")
        if ADMIN_PASSIVE_RX.search(sentence):
            score += 0.8
            reasons.append("O5: forma bierna/proceduralna")
    if label in {"P1_falszywa_dychotomia", "P1_insynuacja", "P1_pytanie_retoryczne"}:
        score += 1.0
        reasons.append("technika z natury argumentacyjna")
    if label not in {"P1_eufemizacja", "P1_jezyk_administracyjny", "P1_nominalizacja", "P1_ukrycie_sprawcy"} and NARRATIVE_NEUTRAL.search(sentence) and not ARGUMENT_CONTEXT.search(sentence):
        score -= 2.0
        reasons.append("neutralny/fabularny opis bez kontekstu argumentacyjnego")
    if label not in {"P1_wyliczenie", "P1_eufemizacja", "P1_jezyk_administracyjny", "P1_nominalizacja", "P1_ukrycie_sprawcy"} and TECHNICAL_WORDS.search(sentence):
        score -= 1.0
        reasons.append("kontekst techniczny lub proceduralny")
    if score >= 2.5:
        return "high", score, reasons
    if score >= 1.0:
        return "medium", score, reasons
    return "low", score, reasons


def _min_confidence(*values: str | None) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    inv = {0: "low", 1: "medium", 2: "high"}
    nums = [order.get(str(v or "medium"), 1) for v in values]
    return inv[min(nums) if nums else 1]


def _derive_interpretation_confidence(card: Card, rel: str) -> str:
    """O2: pewność interpretacji zależy od roli i istotności, nie tylko od regexu."""
    if card.role in {"STRUCTURE_CANDIDATE", "SEMANTIC_CANDIDATE", "BLOCKED_BY_GUARD"}:
        return "low" if rel == "low" else "medium"
    if card.role == "NARRATIVE_HYPOTHESIS":
        return "medium" if rel in {"medium", "high", "unknown"} else "low"
    if card.role == "DECISION_SUGGESTION":
        if rel == "high":
            return card.confidence
        if rel == "medium":
            return _min_confidence(card.confidence, "medium")
        if rel == "low":
            # O2: mocna, pełna struktura P1 może mieć niską istotność kontekstową
            # w krótkim zdaniu testowym, ale nie powinna tracić całej pewności
            # interpretacji, jeśli przeszła walidator jako decyzja.
            if card.label in {"P1_antyteza", "P1_falszywa_dychotomia", "P1_insynuacja", "P1_pytanie_retoryczne"}:
                return "medium"
            return "low"
    return card.confidence


def promote_or_candidate(card: Card) -> Card:
    rel, rel_score, reasons = analytical_relevance(card.fragment, card.label)
    card.analytical_relevance = rel
    card.score += rel_score
    if card.pattern_confidence is None:
        card.pattern_confidence = card.confidence
    if reasons:
        card.why += " Relevance: " + "; ".join(reasons) + "."
    # O3: niska istotność analityczna nie może być potwierdzoną techniką P1.
    # Regex może dobrze rozpoznać wzorzec, ale przy braku kontekstu argumentacyjnego
    # karta trafia do kandydatów zamiast do głównych decyzji.
    if rel == "low" and card.role == "DECISION_SUGGESTION":
        card.role = "STRUCTURE_CANDIDATE"
        card.requires_review = True
        card.visibility = "collapsed"
        card.why += " O3: niska istotność analityczna — wynik przeniesiono do kandydatów, nie do potwierdzonych technik P1."

    # Kontrast i metafory opisowe są często tylko strukturą, nie główną decyzją.
    if card.label in {"P1_kontrast", "P1_metafora", "P1_personifikacja", "P1_wyliczenie"} and rel == "low":
        card.role = "STRUCTURE_CANDIDATE"
        card.requires_review = True
        card.visibility = "collapsed"
        card.why += " Struktura jest poprawna językowo, ale nie ma wystarczającej istotności analitycznej dla głównej decyzji P1."
    # O2: ogólna pewność karty jest ostrożna; osobno zachowujemy pewność wzorca.
    card.interpretation_confidence = _derive_interpretation_confidence(card, rel)
    card.confidence = _min_confidence(card.pattern_confidence, card.interpretation_confidence)
    return card



def _is_metadata_fragment_for_p0(fragment: str) -> bool:
    frag = normalize(fragment).lower()
    # Warstwa P0: P0 nie powinno robić podświetleń w stopce/metadanych,
    # bo takie trafienia psują ocenę tekstu właściwego.
    meta_markers = [
        "tagi:", "podziel się", "link skopiowany", "autorka/autor:",
        "autor:", "źródło:", "zrodlo:", "czytaj więcej", "dowiedz się",
    ]
    return any(m in frag for m in meta_markers)

def detect_p0(text: str) -> List[Card]:
    cards: List[Card] = []
    for label, phrases in P0_MARKERS.items():
        for phrase in phrases:
            for start, end, matched in find_phrase(text, phrase):
                frag = context_for(text, start, end)
                if _is_metadata_fragment_for_p0(frag):
                    continue
                add_unique(cards, Card(
                    label=label,
                    level="P0",
                    role="RAW_SIGNAL",
                    phrase=matched,
                    fragment=frag,
                    start=start,
                    end=end,
                    confidence="low",
                    score=1.0,
                    why="Surowy marker P0. Sam marker nie awansuje do P1 bez pełnej struktury i istotności analitycznej.",
                    blocked_promotion_to=P1_STRUCTURES.get(label, {}).get("may_promote_to", []),
                    visibility="p0_preview",
                ))
    return cards


def split_by_marker(sentence: str, marker: str) -> Tuple[str, str] | None:
    rx = re.compile(r"\b" + re.escape(marker) + r"\b", re.I | re.U)
    m = rx.search(sentence)
    if not m:
        return None
    left = sentence[:m.start()].strip(" ,;:-")
    right = sentence[m.end():].strip(" ,;:-")
    return left, right


def valid_contrast(sentence: str) -> Card | None:
    s_norm = norm_ascii(sentence)
    if re.search(r"\bz jednej strony\b.+\bz drugiej strony\b", s_norm):
        return promote_or_candidate(Card("P1_kontrast", "P1", "DECISION_SUGGESTION", sentence, phrase="z jednej strony ... z drugiej strony", confidence="high", score=4.5,
                    why="Pełna dwuczłonowa struktura kontrastu: 'z jednej strony A, z drugiej strony B'."))
    if re.search(r"\bnie tylko\b.{1,220}\bale\s+(?:takze|rowniez|tez)\b", s_norm):
        return promote_or_candidate(Card("P1_kontrast", "P1", "DECISION_SUGGESTION", sentence, phrase="nie tylko ... ale także", confidence="medium", score=3.7,
                    why="Pełna struktura: 'nie tylko A, ale także B'."))
    for marker in ["choć", "chociaż", "ale", "jednak", "natomiast", "mimo że", "podczas gdy"]:
        parts = split_by_marker(sentence, marker)
        if not parts:
            continue
        left, right = parts
        if word_count(left) >= 2 and word_count(right) >= 2:
            return promote_or_candidate(Card("P1_kontrast", "P1", "DECISION_SUGGESTION", sentence, phrase=marker, confidence="medium", score=3.0,
                        why="Wykryto dwuczłonową strukturę kontrastu: człon A + marker + człon B.", part_a=left, part_b=right))
    return None


def valid_false_dichotomy(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    coercive_patterns = [
        r"\bnie ma (?:zadnej )?trzeciej drogi\b",
        r"\btylko dwie (?:opcje|drogi|mozliwosci|wyjscia)\b",
        r"\bjedyny wybor\b.{1,140}\b(?:inaczej|albo|bo)\b",
    ]
    explicit_coercion = any(re.search(p, n, re.I) for p in coercive_patterns)
    albo_albo = bool(re.search(r"\balbo\b.{1,160}\balbo\b", n, re.I))
    pressure = bool(re.search(
        r"\b(?:musisz|musicie|musimy|musi|trzeba|nalezy|wybierz|wybor|"
        r"z nami|przeciwko nam|inaczej|nie ma alternatywy|czeka nas tylko)\b",
        n,
        re.I,
    ))
    if explicit_coercion or (albo_albo and pressure):
        return promote_or_candidate(Card("P1_falszywa_dychotomia", "P1", "DECISION_SUGGESTION", sentence, phrase="struktura wyboru", confidence="high", score=4.5,
                    why="Wykryto zawężenie wyboru do wymuszonych wariantów i pominięcie alternatyw."))
    return None


def valid_rhetorical_question(sentence: str) -> Card | None:
    if "?" not in sentence:
        return None
    n = norm_ascii(sentence)
    if TECHNICAL_WORDS.search(sentence):
        return None
    if re.search(r"\b(?:czy naprawde|czy ktokolwiek|kto normalny|czy mozna|jak dlugo|ile jeszcze)\b", n):
        return promote_or_candidate(Card("P1_pytanie_retoryczne", "P1", "DECISION_SUGGESTION", sentence, phrase="pytanie retoryczne", confidence="high", score=4.0,
                    why="Pytanie nie służy uzyskaniu informacji, tylko wzmacnia ocenę lub presję."))
    return None


def valid_enumeration(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if CITY_WORDS.search(sentence) or TECHNICAL_WORDS.search(sentence):
        return None
    if re.search(r"\bpo pierwsze\b.+\bpo drugie\b", n):
        return promote_or_candidate(Card("P1_wyliczenie", "P1", "DECISION_SUGGESTION", sentence, phrase="po pierwsze / po drugie", confidence="high", score=4.0,
                    why="Jawna enumeracja argumentacyjna."))
    if re.search(r":\s*[^:.!?]+,\s*[^:.!?]+,\s*(?:i|oraz)\s*[^:.!?]+", sentence, re.I | re.U):
        value_words = ["bezpieczenstwo", "odpowiedzialnosc", "chaos", "kryzys", "ryzyko", "naduzyc", "centralizacja", "kontrola", "skutecznosc", "stabilnosc", "porzadek"]
        if any(v in n for v in value_words):
            return promote_or_candidate(Card("P1_wyliczenie", "P1", "DECISION_SUGGESTION", sentence, phrase="lista wartościująca", confidence="medium", score=3.2,
                        why="Lista ma funkcję argumentacyjną/wartościującą, a nie tylko informacyjną."))
    return None


def valid_insinuation(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if TECHNICAL_WORDS.search(sentence) and not re.search(r"\b(?:przypadek|zbieg okolicznosci|trudno nie zauwazyc|ukryt|zyska|komu sluzy)\b", n):
        return None
    patterns = [
        r"\bczy to (?:naprawde )?przypadek\b",
        r"\btrudno nie zauwazyc\b",
        r"\bnie twierdzimy ze\b.{0,180}\b(?:ale|jednak)\b",
        r"\bpojawiaja sie pytania\b.{0,220}\b(?:kto|dlaczego|czy to|przypadek|ukry|zyska)\b",
        r"\bpytania same sie nasuwaja\b",
    ]
    if any(re.search(p, n, re.I) for p in patterns):
        card = Card("P1_insynuacja", "P1", "DECISION_SUGGESTION", sentence, phrase="sugestia bez dowodu", confidence="medium", score=3.6,
                    why="Fragment sugeruje winę, ukryty motyw lub powiązanie bez przedstawienia dowodu.", requires_review=True)
        return promote_or_candidate(card)
    return None


def valid_hyperbole(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if re.search(r"\bnie\s+(?:jest|byla|bylo|oznacza)\b.{0,60}\b(?:katastrof|chaos|skandal|kryzys|upadek)\b", n):
        return Card("P1_hiperbola", "P1", "BLOCKED_BY_GUARD", sentence, phrase="zanegowana hiperbola", confidence="high", score=0,
                    why="Sygnał hiperboli został zablokowany przez negację bezpośrednią.", guards=["negacja"], blocked_promotion_to=["P1_hiperbola"])
    extreme = re.search(r"\b(?:najwieksz|najgorsz|absolutn|totaln|bezprecedens|koniec wszystkiego|katastrof|runie|nigdy wczesniej)\b", n)
    emotion = re.search(r"\b(?:chaos|kryzys|skandal|upadek|zniszcz|dramat|porazk|panstw)\b", n)
    factual_comparison = re.search(
        r"\b(?:najwieksz\w*|najgorsz\w*)\b.{0,90}\b(?:od\s+(?:czasu|roku|lat)|"
        r"wedlug\s+(?:danych|szacunkow|raportu)|dane\s+wskazuja|wyniosl\w*|"
        r"liczb\w*|procent\w*|w\s+porownaniu\s+z)\b",
        n,
    )
    explicit_exaggeration = re.search(
        r"\b(?:absolutn|totaln|koniec wszystkiego|zrujnuje wszystko|"
        r"caly system rozpadnie|niewyobrazaln|lawin\w* nieodwracaln)\b",
        n,
    )
    if factual_comparison and not explicit_exaggeration:
        return None
    if extreme and emotion:
        return promote_or_candidate(Card("P1_hiperbola", "P1", "DECISION_SUGGESTION", sentence, phrase=extreme.group(0), confidence="high", score=4.0,
                    why="Skrajna skala połączona z emocjonalnym skutkiem."))
    return None


def valid_generalization(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if re.search(r"\b(?:pamietajmy|nie zapominajmy|apelujmy|prosze pamietac|musimy pamietac)\b", n):
        return None
    if re.search(r"\b(?:wszyscy|nikt|kazdy|zawsze|nigdy|cale spoleczenstwo|wiekszosc|bez wyjatku)\b", n) and re.search(r"\b(?:ludzie|obywatele|przeciwnicy|zwolennicy|politycy|system|spoleczenstwo|wiedza|uwaza|mowi|blokuja|dziala)\b", n):
        return promote_or_candidate(Card("P1_generalizacja", "P1", "DECISION_SUGGESTION", sentence, phrase="kwantyfikator", confidence="medium", score=3.5,
                    why="Kwantyfikator obejmuje szeroką grupę i przypisuje jej cechę lub zachowanie."))
    return None


def valid_metaphor_personification(sentence: str) -> List[Card]:
    n = norm_ascii(sentence)
    out: List[Card] = []
    if re.search(r"\b(?:panstwo|demokracja|ustawa|procedury|instytucje)\b.{0,80}\b(?:maszyna|tarcza|kaganiec|organizm|burza|machina|tryby)\b", n):
        out.append(promote_or_candidate(Card("P1_metafora", "P1", "DECISION_SUGGESTION", sentence, phrase="metafora", confidence="medium", score=3.2,
                        why="Jedna domena pojęciowa opisuje inną, np. państwo jako maszyna/tarcza/organizm.")))
    if re.search(r"\b(?:demokracja|procedury|ustawa|panstwo|administracja)\b.{0,50}\b(?:oddycha|dusi|patrzy|czeka|wchodzi do gry|przemawia)\b", n):
        out.append(promote_or_candidate(Card("P1_personifikacja", "P1", "DECISION_SUGGESTION", sentence, phrase="personifikacja", confidence="medium", score=3.2,
                        why="Abstrakt lub instytucja otrzymuje cechy żywej istoty.")))
    return out



# -----------------------------
# Warstwa wiedzy P1
# -----------------------------
# To nie jest przeniesienie zewnętrznego silnika linia_T. To mała, jawna warstwa reguł
# tekstowych oparta na benchmarkach: wejście = zdanie, wyjście = karta P1.

def _has_negated_extreme(n: str) -> bool:
    return bool(re.search(r"\bnie\s+(?:jest|byla|bylo|bedzie|oznacza|stanowi)\b.{0,70}\b(?:katastrof|kryzys|skandal|upadek|koniec|dramat|cios|przelom)\b", n))


# -----------------------------
# O1: poprawiona antyteza
# -----------------------------
# Antyteza P1 nie może być automatycznie wyprowadzana z każdego wzorca
# "nie ... ale/lecz". Poniższe blokady oddzielają mocną antytezę
# retoryczną od zwykłego kontrastu informacyjnego i rozszerzenia zakresu.
ANTITHESIS_BLOCKERS = [
    (re.compile(r"\bnie\s+tylko\b.{1,220}\b(?:ale|lecz)\s+(?:takze|rowniez|tez)\b", re.I),
     "nie tylko A, ale także/również/też B = rozszerzenie zakresu, nie antyteza"),
    (re.compile(r"\bnie\s+ma\b.{0,140}\b(?:ale|lecz)\b.{0,160}\b(?:poszukuje|szuka|analizuje|rozwaza|rozpatruje|bada)\b", re.I),
     "brak obecnej możliwości + deklaracja szukania/analizy = kontrast informacyjny"),
    (re.compile(r"\bnie\s+(?:mozna|moze|jest\s+mozliwe|da\s+sie)\b.{0,140}\b(?:ale|lecz)\b.{0,160}\b(?:zostanie|bedzie|trwaja|trwa|zapowiedziano|planowane|analizowane|rozwazane)\b", re.I),
     "niemożność teraz + zapowiedź działań = kontrast informacyjny"),
    (re.compile(r"\bnie\s+(?:jest\s+jeszcze|bylo|byla|zakonczono|przyjeto|rozpoczeto)\b.{0,140}\b(?:ale|lecz)\b.{0,160}\b(?:bedzie|jest|sa|pojawi|pojawilo|zapowiedziano|rozpoczeto|przyjeto)\b", re.I),
     "korekta informacyjna/czasowa = kontrast słaby, nie antyteza"),
    (re.compile(r"\bnie\s+(?:przyjeto|udalo\s+sie|bylo)\b.{0,160}\b(?:ale|lecz)\b.{0,160}\b(?:obiecano|kontynuuja|pojawil|pojawilo|dokument|rozmowy)\b", re.I),
     "słaby kontrast proceduralny/czasowy = nie antyteza"),
]


def antithesis_block_reason(n: str) -> str | None:
    for rx, reason in ANTITHESIS_BLOCKERS:
        if rx.search(n):
            return reason
    return None


def valid_scope_extension(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if re.search(r"\bnie\s+tylko\b.{1,220}\b(?:ale|lecz)\s+(?:takze|rowniez|tez)\b", n, re.I):
        return promote_or_candidate(Card(
            "P1_rozszerzenie_zakresu", "P1", "STRUCTURE_CANDIDATE", sentence,
            phrase="nie tylko A, ale także B", confidence="medium", score=2.8,
            why="Wykryto konstrukcję rozszerzającą zakres wypowiedzi. To nie jest automatycznie antyteza retoryczna.",
            requires_review=True, visibility="collapsed", blocked_promotion_to=["P1_antyteza"],
        ))
    return None


def valid_antithesis(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if re.search(r"\bnie\s+twierdzimy\b|\btrudno\s+nie\s+zauwazyc\b", n):
        return None
    blocked = antithesis_block_reason(n)
    if blocked:
        return None
    patterns = [
        (r"\bpod\s+pozorem\s+[^.!?]{1,90}\s+(?:wprowadzono|dokonano|przeprowadzono|ukryto)\s+[^.!?]{1,140}", "pod pozorem A dokonano B"),
        (r"\b(?:to\s+)?nie\s+[^.!?]{1,90}\s+(?:lecz|ale)\s+[^.!?]{1,120}", "nie A, lecz/ale B"),
        (r"\bzamiast\s+[^,.!?]{1,90}\s+[^,.!?]{1,120}", "zamiast A — B"),
        (r"\bmial[ao]?\s+byc\s+[^.!?]{1,90}\s+(?:jest|sa)\s+[^.!?]{1,120}", "miało/miała być A, jest B"),
        (r"\bobiecywano\s+[^,.!?]{1,90},?\s+(?:dostarczono|wybrano)\s+[^,.!?]{1,120}", "obiecywano A, dostarczono/wybrano B"),
        (r"\bmniej\s+[^,.!?]{1,60},\s*wiecej\s+[^,.!?]{1,90}", "mniej A, więcej B"),
        (r"\bto\s+nie\s+[^.!?]{1,90}\s+lecz\s+[^.!?]{1,120}", "to nie A, lecz B"),
        (r"\b(?:to\s+)?nie\s+[^.!?]{1,90}\s+tylko\s+[^.!?]{1,120}", "nie A, tylko B"),
    ]
    for rx, phrase in patterns:
        if re.search(rx, n, re.I):
            # Zwykła korekta nazwy lub neutralne „nie A, lecz B” nie jest
            # automatycznie figurą retoryczną. Dla ogólnych wzorców wymagamy
            # lokalnego języka wartości, konfliktu albo oceny.
            generic = phrase in {"nie A, lecz/ale B", "zamiast A — B", "to nie A, lecz B", "nie A, tylko B"}
            rhetorical_value = bool(
                VALUE_CONTEXT.search(sentence)
                or re.search(r"\b(?:poz[oó]r\w*|obiecyw\w*|k[łl]am\w*|propagand\w*|"
                             r"krzywd\w*|niszcz\w*|ratun\w*|wolno[śs][ćc]|prawd\w*)\b", sentence, re.I)
            )
            if generic and not rhetorical_value:
                continue
            return promote_or_candidate(Card(
                "P1_antyteza", "P1", "DECISION_SUGGESTION", sentence,
                phrase=phrase, confidence="high", score=4.2,
                why="Wykryto przeciwstawienie dwóch wartości/obrazów w układzie antytezy A–B. O1: wynik przeszedł blokady fałszywej antytezy."
            ))
    return None


def valid_false_dichotomy_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    patterns = [
        r"\b(?:jestes|jesteście|jestescie)\s+z\s+nami\s+albo\s+przeciwko\s+nam\b",
        r"\bwybor\s*:\s*[^:.!?]{1,120}\balbo\b[^:.!?]{1,120}",
        r"\bbez\s+tego\s+[^,.!?]{1,80}\s+czeka\s+nas\s+tylko\s+[^,.!?]{1,120}",
        r"\bkto\s+nie\s+[^,.!?]{1,90},?\s+ten\s+[^,.!?]{1,120}",
        r"\bjest\s+tylko\s+jedna\s+droga\b",
        r"\bnie\s+ma\s+trzeciej\s+(?:opcji|drogi|mozliwosci)\b",
    ]
    if any(re.search(rx, n, re.I) for rx in patterns):
        return promote_or_candidate(Card(
            "P1_falszywa_dychotomia", "P1", "DECISION_SUGGESTION", sentence,
            phrase="wymuszony wybór", confidence="high", score=4.4,
            why="Warstwa wiedzy wykryła przymusowy wybór albo konstrukcję 'kto nie A, ten B'."
        ))
    return None


def valid_generalization_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    quant = r"(?:wszyscy|wszystkie|nikt|kazdy|kazda|zawsze|nigdy)"
    # Guard: samo pytanie 'czy ktoś' bez oceny nie jest generalizacją.
    if re.search(r"\bczy\s+ktos\b", n) or re.search(
        r"\b(?:pamietajmy|nie zapominajmy|apelujmy|prosze pamietac|musimy pamietac)\b", n
    ):
        return None
    if re.search(rf"\b{quant}\b", n) and re.search(r"\b(?:urzednik\w*|media|instytucj\w*|reform\w*|scenariusz\w*|obietnic\w*|projekt\w*|dzialania|obywatel\w*|polityk\w*|system\w*|spoleczenstw\w*|prawd\w*|odpowiedzialn\w*|chaos\w*|strat\w*|pozorn\w*|procedur\w*)\b", n):
        return promote_or_candidate(Card(
            "P1_generalizacja", "P1", "DECISION_SUGGESTION", sentence,
            phrase="uogólnienie", confidence="high", score=4.0,
            why="Wykryto szeroki kwantyfikator przypisujący ocenę lub zachowanie całej grupie/zjawisku."
        ))
    return None


def valid_hyperbole_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if _has_negated_extreme(n):
        return Card("P1_hiperbola", "P1", "BLOCKED_BY_GUARD", sentence, phrase="zanegowana hiperbola", confidence="high", score=0,
                    why="Sygnał hiperboli zablokowany przez bezpośrednią negację.", guards=["negacja"], blocked_promotion_to=["P1_hiperbola"])
    if re.search(
        r"\b(?:najwieksz\w*|najgorsz\w*)\b.{0,90}\b(?:od\s+(?:czasu|roku|lat)|"
        r"wedlug\s+(?:danych|szacunkow|raportu)|wyniosl\w*|liczb\w*|procent\w*)\b",
        n,
    ):
        return None
    patterns = [
        r"\bnajwieksz[yae]?\s+kryzys\b",
        r"\bzrujnuje\s+wszystko\b",
        r"\bnigdy\s+wczesniej\s+nie\s+bylo\s+tak\s+dramatycznie\b",
        r"\babsolutn[ae]?\s+katastrof",
        r"\bcaly\s+system\s+rozpadnie\s+sie\b",
        r"\bniewyobrazalne\b",
        r"\bkoniec\s+wszystkiego\b",
        r"\bmiliony\s+problemow\b",
        r"\blawine\s+nieodwracalnych\s+szkod\b",
        r"\bbezprecedensow[yae]?\s+cios\b",
    ]
    if any(re.search(rx, n, re.I) for rx in patterns):
        return promote_or_candidate(Card(
            "P1_hiperbola", "P1", "DECISION_SUGGESTION", sentence,
            phrase="wyolbrzymienie", confidence="high", score=4.3,
            why="Warstwa wiedzy wykryła skrajne powiększenie skali lub skutków."
        ))
    return None


def valid_contrast_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    patterns = [
        (r"\bz\s+jednej\s+strony\b.{1,160}\bz\s+drugiej\b", "z jednej strony / z drugiej"),
        (r"\bwczoraj\b.{1,120}\bdzis\b", "wczoraj / dziś"),
        (r"\bnie\s+jest\s+to\s+[^.!?]{1,100}\s+lecz\s+[^.!?]{1,120}", "nie jest to A, lecz B"),
        (r"\bobiecywano\b.{1,120}\btymczasem\b", "obiecywano / tymczasem"),
        (r"\bmialo\s+byc\b.{1,120}\b(?:a|ale)\b.{1,120}", "miało być A, a/ale B"),
        (r"\bslowa\b.{1,120}\bdzialania\b", "słowa / działania"),
    ]
    for rx, phrase in patterns:
        if re.search(rx, n, re.I):
            return promote_or_candidate(Card(
                "P1_kontrast", "P1", "DECISION_SUGGESTION", sentence,
                phrase=phrase, confidence="high", score=4.0,
                why="Warstwa wiedzy wykryła pełne przeciwstawienie dwóch stanów, deklaracji lub działań."
            ))
    return None


def valid_rhetorical_question_knowledge(sentence: str) -> Card | None:
    if "?" not in sentence:
        return None
    n = norm_ascii(sentence)
    if TECHNICAL_WORDS.search(sentence):
        return None
    patterns = [
        r"\bkto\s+uwierzy\b",
        r"\bile\s+razy\s+mamy\s+sluchac\b",
        r"\bczy\s+to\s+nie\s+jest\b",
        r"\bczy\s+ktos\s+jeszcze\s+ma\s+watpliwosci\b",
        r"\bczy\s+to\s+ma\s+byc\b",
        r"\bkto\s+poniesie\s+odpowiedzialnosc\b",
    ]
    if any(re.search(rx, n, re.I) for rx in patterns):
        return promote_or_candidate(Card(
            "P1_pytanie_retoryczne", "P1", "DECISION_SUGGESTION", sentence,
            phrase="pytanie retoryczne", confidence="high", score=4.1,
            why="Pytanie wzmacnia ocenę lub presję, zamiast neutralnie prosić o informację."
        ))
    return None


def valid_enumeration_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    comma_count = sentence.count(",")
    has_list = comma_count >= 2 or bool(re.search(r"\b(?:i|oraz)\b", n) and comma_count >= 1)
    intro = re.search(r"\b(?:obejmuje|wskazano|dotyczy|wymieniono|zawiera|lista obejmuje|potrzebne sa|najwazniejsze sa)\b", n)
    list_values = re.search(r"\b(?:koszt|termin|kontrol|opoznienia|bledy|straty|chaos|edukacj|zdrowi|bezpieczenstw|wzrost|spadek|ryzyko|procedur|finansowan|nadzor|analiz|konsultacj|wdrozenie|brak|podatk|wydatk|dlug|inwestycj|prawne|finansowe|organizacyjne|dane|odpowiedzialn)\b", n)
    if has_list and (intro or list_values):
        return promote_or_candidate(Card(
            "P1_wyliczenie", "P1", "DECISION_SUGGESTION", sentence,
            phrase="wyliczenie elementów", confidence="medium", score=3.8,
            why="Warstwa wiedzy wykryła listę elementów pełniącą funkcję porządkującą lub argumentacyjną."
        ))
    return None


def valid_insinuation_knowledge(sentence: str) -> Card | None:
    n = norm_ascii(sentence)
    if TECHNICAL_WORDS.search(sentence) and not re.search(r"\b(?:zbieg\s+okolicznosci|zniknely|przypadek|ukryt)\b", n):
        return None
    if re.search(r"\bzbieg\s+okolicznosci\??\b", n):
        return promote_or_candidate(Card(
            "P1_insynuacja", "P1", "DECISION_SUGGESTION", sentence,
            phrase="zbieg okoliczności?", confidence="high", score=4.0,
            why="Pytanie sugeruje podejrzany związek czasowy bez przedstawienia dowodu.",
            requires_review=True,
        ))
    return None



# -----------------------------
# O5: eufemizmy i język administracyjny
# -----------------------------
def valid_o5_euphemization(sentence: str) -> Card | None:
    """Wykrywa łagodzenie straty/przymusu przez słownictwo urzędowe.

    Reguła awansuje do potwierdzonej techniki tylko wtedy, gdy słowo
    eufemizujące pojawia się w kontekście ludzi, mieszkań, lokali albo
    proceduralnej decyzji. Bez tego zostaje kandydatem, a nie werdyktem.
    """
    n = norm_ascii(sentence)
    # Aktualna warstwa: twarde blokady dla neutralnych technicznych użyć, które wcześniej
    # dawały fałszywą eufemizację: transformacja energetyczna, optymalizacja kodu.
    if re.search(r"\b(?:transformacj\w*\s+energetyczn\w*|optymalizacj\w*\s+kodu|optymalizacj\w*\s+zapytania|optymalizacj\w*\s+algorytm\w*)\b", n):
        m_neutral = EUPHEMISM_TERMS_RX.search(sentence)
        if m_neutral:
            return promote_or_candidate(Card(
                "P1_eufemizacja", "P1", "STRUCTURE_CANDIDATE", sentence,
                phrase=m_neutral.group(0), confidence="medium", pattern_confidence="high",
                score=2.0, why=" neutralne techniczne użycie słowa z listy eufemizmów pozostaje tylko kandydatem P1, nie potwierdzoną techniką.",
                requires_review=True, visibility="collapsed",
            ))
        return None
    m = EUPHEMISM_TERMS_RX.search(sentence)
    admin_m = ADMIN_LANGUAGE_RX.search(sentence)
    # Aktualna warstwa: wybrane formuły administracyjne pełnią w praktyce funkcję
    # eufemizacji/łagodzenia decyzji, nawet jeśli wcześniej były tylko
    # P1_jezyk_administracyjny.
    if not m and admin_m and re.search(r"\b(?:kazd\w*\s+przypad\w*|rozwi[aą]zania\s+zostan[aą]\s+wdro[zż]on|w\s+trosce\s+o\s+sprawny\s+przebieg\s+procesu|z\s+poszanowaniem\s+interesu\s+spolecznego)\b", n, re.I):
        m = admin_m
    if not m:
        return None

    has_people = bool(HUMAN_AFFECTED_RX.search(sentence))
    has_admin = bool(ADMIN_PASSIVE_RX.search(sentence) or ADMIN_LANGUAGE_RX.search(sentence))
    # Neutralne użycie słowa transformacja bez ludzi/decyzji nie jest jeszcze techniką.
    if "transformac" in norm_ascii(m.group(0)) and not (has_people or has_admin or re.search(r"\b(?:decyzj|uchwal|program|lokal|mieszkan|czynsz|przenies|relokac)\b", n)):
        return promote_or_candidate(Card(
            "P1_eufemizacja", "P1", "STRUCTURE_CANDIDATE", sentence,
            phrase=m.group(0), confidence="medium", pattern_confidence="high",
            score=2.2, why="O5: wykryto możliwy eufemizm, ale bez mocnego kontekstu ludzi/decyzji pozostaje kandydatem.",
            requires_review=True, visibility="collapsed",
        ))

    role = "DECISION_SUGGESTION" if (has_people or has_admin or re.search(r"\b(?:wysiedl|eksmis|przenies|mieszkan|lokal|czynsz)\b", n)) else "STRUCTURE_CANDIDATE"
    return promote_or_candidate(Card(
        "P1_eufemizacja", "P1", role, sentence,
        phrase=m.group(0), confidence="high" if role == "DECISION_SUGGESTION" else "medium",
        pattern_confidence="high", score=4.4 if role == "DECISION_SUGGESTION" else 2.8,
        why="O5: wykryto słownictwo administracyjno-eufemizujące, które może łagodzić stratę, przymus lub zmianę sytuacji mieszkańców.",
        requires_review=(role != "DECISION_SUGGESTION"),
        visibility="default" if role == "DECISION_SUGGESTION" else "collapsed",
    ))


def valid_o5_admin_language(sentence: str) -> Card | None:
    """Wykrywa proceduralny język urzędowy, który może ukrywać sprawczość.

    O5 nie rozstrzyga jeszcze pełnego ukrycia sprawcy z O7. Daje osobną kartę
    języka administracyjnego, szczególnie gdy decyzje dotyczą ludzi/lokali.
    """
    m = ADMIN_LANGUAGE_RX.search(sentence)
    if not m:
        return None
    has_people = bool(HUMAN_AFFECTED_RX.search(sentence))
    role = "DECISION_SUGGESTION" if has_people or ADMIN_PASSIVE_RX.search(sentence) else "STRUCTURE_CANDIDATE"
    return promote_or_candidate(Card(
        "P1_jezyk_administracyjny", "P1", role, sentence,
        phrase=m.group(0), confidence="high" if role == "DECISION_SUGGESTION" else "medium",
        pattern_confidence="high", score=4.1 if role == "DECISION_SUGGESTION" else 2.7,
        why="O5: wykryto język proceduralny/urzędowy, który opisuje decyzję przez proces, warunki lub formułę instytucjonalną zamiast przez jasnego sprawcę i skutek.",
        requires_review=(role != "DECISION_SUGGESTION"),
        visibility="default" if role == "DECISION_SUGGESTION" else "collapsed",
    ))



# -----------------------------
# O6: nominalizacje
# -----------------------------
def valid_o6_nominalization(sentence: str) -> Card | None:
    """Wykrywa nominalizacje procesów/decyzji, zwłaszcza w języku urzędowym.

    Nominalizacja jest potwierdzoną techniką wtedy, gdy rzeczownik procesu
    zastępuje jawne działanie i występuje przy decyzjach, lokalach, mieszkańcach
    albo skutkach społecznych. Neutralne techniczne użycia zostają kandydatem.
    """
    if NEUTRAL_NOMINALIZATION_CONTEXT_RX.search(sentence):
        return None
    m = NOMINALIZATION_TERMS_RX.search(sentence)
    if not m:
        return None
    n = norm_ascii(sentence)
    has_people = bool(HUMAN_AFFECTED_RX.search(sentence))
    has_admin = bool(ADMIN_PASSIVE_RX.search(sentence) or ADMIN_LANGUAGE_RX.search(sentence))
    has_decision_context = bool(re.search(r"\b(?:decyzj\w*|uchwa[łl]\w*|lokal\w*|mieszka[ńn]\w*|najemc\w*|czynsz\w*|zas[oó]b|relokacj\w*|przeniesieni\w*|wysiedl\w*|program\w*)\b", n))

    role = "DECISION_SUGGESTION" if (has_people or has_admin or has_decision_context) else "STRUCTURE_CANDIDATE"
    return promote_or_candidate(Card(
        "P1_nominalizacja", "P1", role, sentence,
        phrase=m.group(0), confidence="high" if role == "DECISION_SUGGESTION" else "medium",
        pattern_confidence="high", score=4.2 if role == "DECISION_SUGGESTION" else 2.5,
        why="O6: wykryto nominalizację, czyli rzeczownikowe nazwanie procesu/decyzji. Taka forma może odsuwać uwagę od sprawcy, działania i konkretnego skutku społecznego.",
        requires_review=(role != "DECISION_SUGGESTION"),
        visibility="default" if role == "DECISION_SUGGESTION" else "collapsed",
    ))



# -----------------------------
# O7: ukrycie sprawcy
# -----------------------------
def valid_o7_agent_hiding(sentence: str) -> Card | None:
    """Wykrywa ukrycie sprawcy w decyzjach opisanych biernie lub bezosobowo.

    Potwierdzenie wymaga kontekstu społecznego/administracyjnego: ludzie,
    lokale, czynsze, gwarancje, decyzje albo proces relokacji. Neutralne
    pasywy techniczne nie są kartą P1/P2.
    """
    if NEUTRAL_PASSIVE_CONTEXT_RX.search(sentence):
        return None
    m = AGENT_HIDING_RX.search(sentence) or BEZOSOBOWE_DECYZJE_RX.search(sentence)
    if not m:
        return None
    n = norm_ascii(sentence)
    has_people = bool(HUMAN_AFFECTED_RX.search(sentence))
    has_decision_context = bool(re.search(r"\b(?:decyzj\w*|uchwa[łl]\w*|lokal\w*|mieszka[ńn]\w*|najemc\w*|lokator\w*|czynsz\w*|gwarancj\w*|relokacj\w*|przeniesieni\w*|wysiedl\w*|program\w*|wsparci\w*)\b", n))
    has_passive_or_impersonal = bool(AGENT_HIDING_RX.search(sentence) or BEZOSOBOWE_DECYZJE_RX.search(sentence))

    role = "DECISION_SUGGESTION" if (has_passive_or_impersonal and (has_people or has_decision_context)) else "STRUCTURE_CANDIDATE"
    return promote_or_candidate(Card(
        "P1_ukrycie_sprawcy", "P1", role, sentence,
        phrase=m.group(0), confidence="high" if role == "DECISION_SUGGESTION" else "medium",
        pattern_confidence="high", score=4.3 if role == "DECISION_SUGGESTION" else 2.6,
        why="O7: wykryto stronę bierną lub formę bezosobową opisującą decyzję/proces bez jasnego wskazania sprawcy. To może rozpraszać odpowiedzialność instytucji.",
        requires_review=(role != "DECISION_SUGGESTION"),
        visibility="default" if role == "DECISION_SUGGESTION" else "collapsed",
    ))

def valid_q12_delegitimization(sentence: str) -> Card | None:
    """Q1.2: mocne przypisanie przestępczości lub bezprawności aktorowi/instytucji."""
    n = norm_ascii(sentence)
    # Sama nazwa kategorii („grupy przestępcze należy obserwować”) jest opisem
    # referencyjnym, a nie delegitymizacją. Wymagamy etykiety przypisanej komuś,
    # instytucji, wypowiedzi albo działaniu.
    strong = re.search(
        r"\b(?:mafia|zlodziejstw\w*|swistk\w* papieru zamiast wyrok\w*|"
        r"uzbrojon\w* tchorzofretk\w*|polityczn\w* hucp\w*|"
        r"(?:calkowit\w*\s+)?bzdur\w*|"
        r"(?:to|jest|byl|byla|bylo)\s*[\"'„”]?\s*(?:zwykl\w*\s+)?belkot\w*|"
        r"pseudokomisj\w*|minister\w*\s+bezprawi\w*(?:\s+i\s+niesprawiedliwosc\w*)?)\b",
        n,
    )
    if not strong:
        return None
    return promote_or_candidate(Card(
        "P1_delegitymizacja", "P1", "DECISION_SUGGESTION", sentence,
        phrase=strong.group(0), confidence="high", pattern_confidence="high", score=4.6,
        why="Q1.2: fragment używa mocnej etykiety przestępczej lub odbiera legitymację aktorowi, instytucji albo jej działaniu.",
        requires_review=True, visibility="default",
    ))


def detect_p1(text: str) -> List[Card]:
    cards: List[Card] = []
    validators = [valid_q12_delegitimization, valid_false_dichotomy_knowledge, valid_insinuation_knowledge, valid_rhetorical_question_knowledge, valid_o5_euphemization, valid_o5_admin_language, valid_o6_nominalization, valid_o7_agent_hiding, valid_antithesis, valid_scope_extension, valid_contrast_knowledge, valid_enumeration_knowledge, valid_hyperbole_knowledge, valid_generalization_knowledge, valid_contrast, valid_false_dichotomy, valid_rhetorical_question, valid_enumeration, valid_insinuation, valid_hyperbole, valid_generalization]
    for s, e, frag in sentences(text):
        for validator in validators:
            card = validator(frag)
            if card:
                card.start = s
                card.end = e
                add_unique(cards, card)
        for card in valid_metaphor_personification(frag):
            card.start = s
            card.end = e
            add_unique(cards, card)
    return cards


def detect_semantic_candidates(text: str) -> List[Card]:
    cards: List[Card] = []
    for s, e, frag in sentences(text):
        n = norm_ascii(frag)
        if re.search(r"\bkto\b.{0,80}\bblokuje\b.{0,120}\bodpowiedzialn", n) or re.search(r"\bodrzucenie\b.{0,120}\boznacza\b.{0,80}\bzgode\b", n):
            add_unique(cards, Card("P1_falszywa_dychotomia", "P1", "SEMANTIC_CANDIDATE", frag, phrase="parafraza presji wyboru", start=s, end=e, confidence="medium", score=2.5,
                                  why="Fragment semantycznie zawęża pole wyboru, ale nie ma jawnej struktury 'albo... albo'.", requires_review=True))
        if re.search(r"\bkomu naprawde sluzy\b|\bukryte motywy\b|\bdzialaja na cudze zlecenie\b", n):
            add_unique(cards, Card("P1_insynuacja", "P1", "SEMANTIC_CANDIDATE", frag, phrase="możliwa insynuacja", start=s, end=e, confidence="medium", score=2.3,
                                  why="Możliwa sugestia ukrytego motywu bez jawnego dowodu. Do przeglądu.", requires_review=True))

        # P3/P-linia: głębsze kandydaty semantyczne. To nadal tropy do
        # ręcznego przeglądu, nie potwierdzone P1/P2.
        for spec in detect_semantic_candidate_specs(frag):
            add_unique(cards, Card(
                spec["label"], "P1", "SEMANTIC_CANDIDATE", frag,
                phrase=spec["phrase"], start=s, end=e, confidence="medium",
                pattern_confidence="medium", interpretation_confidence="low",
                score=2.8, analytical_relevance="medium",
                why="P3/P-linia: " + spec["why"] + " To kandydat semantyczny do zatwierdzenia przez analityka.",
                requires_review=True, visibility="collapsed",
            ))
    return cards


def detect_p2(text: str, p0: List[Card], p1: List[Card], candidates: List[Card]) -> List[Card]:
    cards: List[Card] = []
    labels_p0 = [c.label for c in p0]
    labels_p1 = [c.label for c in p1]
    all_text = norm_ascii(text)

    # O8: depolityzacja decyzji. Rama powstaje, gdy język konieczności
    # technicznej/proceduralnej spotyka się z kontekstem społecznym: ludzie,
    # lokale, czynsze, relokacja, uchwały, rewitalizacja. Neutralne techniczne
    # zdania o kodzie/serwerze są ignorowane.
    o8_hits: List[Card] = []
    for s, e, frag in sentences(text):
        if NEUTRAL_DEPOLITICIZATION_CONTEXT_RX.search(frag):
            continue
        marker = DEPOLITICIZATION_MARKERS_RX.search(frag)
        if marker and WEAK_DEPOLITICIZATION_MARKER_RX.fullmatch(marker.group(0)):
            has_human_cost = bool(HUMAN_AFFECTED_RX.search(frag))
            has_coercive_form = bool(
                ADMIN_PASSIVE_RX.search(frag)
                or re.search(r"\b(?:musi|musz[ąa]|konieczn\w*|nieuniknion\w*|bez\s+alternatywy)\b", frag, re.I)
            )
            if not (has_human_cost and has_coercive_form):
                continue
        if marker and DEPOLITICIZATION_SOCIAL_CONTEXT_RX.search(frag):
            o8_hits.append(Card(
                "P3_depolityzacja_decyzji", "P3", "NARRATIVE_HYPOTHESIS", frag,
                phrase=marker.group(0), start=s, end=e, confidence="medium",
                pattern_confidence="high", interpretation_confidence="medium",
                score=4.2, analytical_relevance="high", requires_review=True,
                why="O8: decyzja społeczna/polityczna jest opisana językiem technicznej, ekonomicznej lub proceduralnej konieczności. To hipoteza ramy depolityzacji, nie automatyczny werdykt."
            ))
    if o8_hits:
        example = o8_hits[0]
        add_unique(cards, Card(
            "P3_depolityzacja_decyzji", "P3", "NARRATIVE_HYPOTHESIS", example.fragment,
            phrase=example.phrase, start=example.start, end=example.end, confidence="medium",
            pattern_confidence="high", interpretation_confidence="medium", score=4.4,
            analytical_relevance="high", requires_review=True,
            why="O8: wykryto ramę depolityzacji decyzji — społeczny/polityczny skutek jest przedstawiany jako sprawa techniczna, ekonomiczna albo proceduralna. Liczba wspierających fragmentów: %d." % len(o8_hits)
        ))

    # O9: naturalizacja konieczności. Rama powstaje, gdy tekst przedstawia
    # decyzję lub projekt jako nieunikniony, oczywisty, wymuszony przez czas,
    # matematykę, rzeczywistość albo brak alternatywy. Wymaga kontekstu
    # społecznego/instytucjonalnego, żeby nie łapać neutralnych zdań technicznych.
    o9_hits: List[Card] = []
    for s, e, frag in sentences(text):
        if NEUTRAL_NATURALIZATION_CONTEXT_RX.search(frag):
            continue
        marker = NATURALIZATION_MARKERS_RX.search(frag)
        if marker and NATURALIZATION_SOCIAL_CONTEXT_RX.search(frag):
            o9_hits.append(Card(
                "P3_naturalizacja_koniecznosci", "P3", "NARRATIVE_HYPOTHESIS", frag,
                phrase=marker.group(0), start=s, end=e, confidence="medium",
                pattern_confidence="high", interpretation_confidence="medium",
                score=4.3, analytical_relevance="high", requires_review=True,
                why="O9: decyzja/projekt jest przedstawiany jako konieczny, nieunikniony albo wymuszony przez rzeczywistość. To hipoteza ramy naturalizacji konieczności, nie automatyczny werdykt."
            ))
    if o9_hits:
        example = o9_hits[0]
        add_unique(cards, Card(
            "P3_naturalizacja_koniecznosci", "P3", "NARRATIVE_HYPOTHESIS", example.fragment,
            phrase=example.phrase, start=example.start, end=example.end, confidence="medium",
            pattern_confidence="high", interpretation_confidence="medium", score=4.5,
            analytical_relevance="high", requires_review=True,
            why="O9: wykryto ramę naturalizacji konieczności — działanie jest przedstawiane jako nieuniknione lub pozbawione alternatywy. Liczba wspierających fragmentów: %d." % len(o9_hits)
        ))

    # O10: rozsądek kontra emocje. Rama powstaje, gdy tekst przeciwstawia
    # racjonalność/odpowiedzialne zarządzanie emocjom, lękowi lub sentymentowi.
    # Wymagamy kontekstu społecznego, żeby nie łapać neutralnych zdań
    # psychologicznych ani technicznych.
    o10_hits: List[Card] = []
    for s, e, frag in sentences(text):
        if NEUTRAL_RATIONALITY_EMOTION_CONTEXT_RX.search(frag):
            continue
        marker = RATIONALITY_EMOTION_MARKERS_RX.search(frag)
        if marker and RATIONALITY_EMOTION_SOCIAL_CONTEXT_RX.search(frag):
            o10_hits.append(Card(
                "P3_rozsadek_kontra_emocje", "P3", "NARRATIVE_HYPOTHESIS", frag,
                phrase=marker.group(0), start=s, end=e, confidence="medium",
                pattern_confidence="high", interpretation_confidence="medium",
                score=4.4, analytical_relevance="high", requires_review=True,
                why="O10: tekst przeciwstawia racjonalność, odpowiedzialność lub zarządzanie emocjom, lękowi albo sentymentowi. To hipoteza ramy narracyjnej, nie automatyczny werdykt."
            ))
    if o10_hits:
        example = o10_hits[0]
        add_unique(cards, Card(
            "P3_rozsadek_kontra_emocje", "P3", "NARRATIVE_HYPOTHESIS", example.fragment,
            phrase=example.phrase, start=example.start, end=example.end, confidence="medium",
            pattern_confidence="high", interpretation_confidence="medium", score=4.6,
            analytical_relevance="high", requires_review=True,
            why="O10: wykryto ramę ‘rozsądek kontra emocje’ — jedna strona sporu jest ustawiana jako racjonalna/odpowiedzialna, a druga jako emocjonalna, sentymentalna lub blokująca rozwój. Liczba wspierających fragmentów: %d." % len(o10_hits)
        ))
    security_count = labels_p0.count("P0_rama_bezpieczenstwa")
    legal_only = bool(LEGAL_PROCEDURE_CONTEXT_RX.search(text)) and not bool(PUBLIC_SECURITY_POLICY_RX.search(text))
    security_support = [c for c in p0 if c.label == "P0_rama_bezpieczenstwa" and 0 <= c.start < c.end <= len(text)]
    if security_count >= 2 and not legal_only and re.search(r"\b(?:chaos|zagrozenie|ryzyko|porzadek|stabilnosc)\b", all_text) and re.search(r"\b(?:trzeba|musi|musimy|nie czas|szybkie dzialanie|dzialac)\b", all_text):
        example = security_support[0] if security_support else None
        if example is not None:
            add_unique(cards, Card(
                "P2_ramowanie_bezpieczenstwa", "P2", "NARRATIVE_HYPOTHESIS",
                text[example.start:example.end], phrase=text[example.start:example.end],
                start=example.start, end=example.end, confidence="medium", score=3.0,
                evidence_fragments=[text[c.start:c.end] for c in security_support[:4]],
                supporting_labels=[c.label for c in security_support[:4]],
                why="Powtarza się język bezpieczeństwa połączony z zagrożeniem i presją działania.", requires_review=True,
            ))
    if re.search(r"\bpo jednej stronie\b.+\bpo drugiej\b", all_text) and re.search(r"\b(?:odpowiedzial|blokuj|chaos|sabota|wrog|ryzykuj)\b", all_text):
        add_unique(cards, Card("P2_polaryzacja", "P2", "NARRATIVE_HYPOTHESIS", text[:500], phrase="dwa obozy", confidence="medium", score=3.0,
                              why="Tekst buduje układ dwóch obozów i wartościuje ich role.", requires_review=True))
    strong_cards = [c for c in p1 if c.label in {"P1_insynuacja", "P1_falszywa_dychotomia", "P1_generalizacja"}]
    strong = bool(strong_cards)
    if strong and ("P0_marker_hiperboli" in labels_p0 or "P0_odpowiedzialnosc_wina" in labels_p0 or "P0_rama_bezpieczenstwa" in labels_p0):
        example = strong_cards[0]
        add_unique(cards, Card(
            "P2_manipulacja_narracyjna", "P2", "NARRATIVE_HYPOTHESIS",
            text[example.start:example.end] if 0 <= example.start < example.end <= len(text) else example.fragment,
            phrase=example.phrase if example.phrase and example.phrase.casefold() in example.fragment.casefold() else example.fragment[:160],
            start=example.start, end=example.end, confidence="low", score=2.5,
            evidence_fragments=[example.fragment], supporting_labels=[example.label],
            why="Potwierdzona technika P1 występuje razem z emocjonalnym/wartościującym P0. To hipoteza, nie werdykt.", requires_review=True,
        ))
    return cards



# -----------------------------
# Lingwistyczny profil tekstu
# -----------------------------
MODALITY_RX = re.compile(r"\b(?:musi|muszą|powinien|powinni|trzeba|należy|nie wolno|może|mogą|warto|konieczne|wymaga)\b", re.I)
NEGATION_RX = re.compile(r"\b(?:nie|nigdy|żaden|zadna|żadna|bez|ani)\b", re.I)
CAUSAL_RX = re.compile(r"\b(?:bo|ponieważ|poniewaz|dlatego|z powodu|w efekcie|skutkiem|prowadzi do|oznacza|wynika z)\b", re.I)
TEMPORAL_RX = re.compile(r"\b(?:najpierw|potem|później|pozniej|wtedy|następnie|nastepnie|od pomocnicza|w ostatnich|teraz|dziś|dzis)\b", re.I)
ATTRIBUTION_RX = re.compile(r"\b(?:mówi|mowia|twierdzi|przekonuje|odpowiada|podkreśla|podkresla|według|wedlug|zdaniem|cytuje|pisze)\b", re.I)
ACTOR_RX = re.compile(r"\b(?:rząd|rzad|opozycja|minister|prezydent|komisja|eksperci|obywatele|ludzie|krytycy|zwolennicy|przeciwnicy|państwo|panstwo|instytucje|media|redakcja|sąd|sad|politycy)\b", re.I)
EMOTION_RX = re.compile(r"\b(?:strach|obawa|gniew|chaos|kryzys|katastrofa|skandal|zagrożenie|zagrozenie|bezpieczeństwo|bezpieczenstwo|nadzieja|wina|odpowiedzialność|odpowiedzialnosc)\b", re.I)
STYLE_INTENS_RX = re.compile(r"\b(?:bardzo|absolutnie|całkowicie|calkowicie|totalnie|najbardziej|największy|najwiekszy|nigdy wcześniej|nigdy wczesniej|bezprecedensowy)\b", re.I)


def tokenize_words(text: str) -> List[str]:
    return re.findall(r"\b[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\b", text or "", re.I | re.U)


def count_rx(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text or ""))


def lexical_richness(tokens: List[str]) -> float:
    if not tokens:
        return 0.0
    return round(len(set(t.lower() for t in tokens)) / len(tokens), 3)


def linguistic_profile(text: str, p0: List[Card], p1_all: List[Card], p2: List[Card], candidates: List[Card]) -> Dict[str, Any]:
    """Warstwa opisowa: nie klasyfikuje sama, tylko daje pełny obraz lingwistyczny tekstu."""
    sent = sentences(text)
    tokens = tokenize_words(text)
    p0_by = Counter(c.label for c in p0)
    p1_by_role = Counter(c.role for c in p1_all)
    confirmed_p1 = [c for c in p1_all if c.role == "DECISION_SUGGESTION"]
    weak_structures = [c for c in p1_all if c.role == "STRUCTURE_CANDIDATE"]
    return {
        "schema": "linguistic_profile_v1",
        "surface": {
            "chars": len(text or ""),
            "tokens": len(tokens),
            "sentences": len(sent),
            "avg_sentence_tokens": round(len(tokens) / max(1, len(sent)), 2),
            "lexical_richness": lexical_richness(tokens),
        },
        "lexical_semantic": {
            "p0_groups": dict(p0_by),
            "emotion_or_value_markers": count_rx(EMOTION_RX, text),
            "intensifiers": count_rx(STYLE_INTENS_RX, text),
        },
        "morpho_syntactic_approx": {
            "negations": count_rx(NEGATION_RX, text),
            "modal_markers": count_rx(MODALITY_RX, text),
            "questions": text.count("?"),
            "enumeration_commas": len(re.findall(r",", text or "")),
        },
        "discourse_pragmatics": {
            "causal_connectors": count_rx(CAUSAL_RX, text),
            "temporal_connectors": count_rx(TEMPORAL_RX, text),
            "attribution_markers": count_rx(ATTRIBUTION_RX, text),
            "actors_detected": sorted(set(m.group(0).lower() for m in ACTOR_RX.finditer(text or "")))[:20],
        },
        "rhetorical_argumentative": {
            "confirmed_p1": len(confirmed_p1),
            "weak_structures": len(weak_structures),
            "semantic_candidates": len(candidates),
            "p1_by_role": dict(p1_by_role),
        },
        "narrative": {
            "p2_techniques": len(p2),
            "p2_labels": [c.label for c in p2],
        },
        "interpretation_note": "Profil lingwistyczny jest opisowy. Nie zastępuje decyzji P1/P2, lecz pomaga audytować tekst pod kątem słownictwa, składni, pragmatyki, argumentacji i narracji.",
    }


def result_quality(p0: List[Card], p1_all: List[Card], p2: List[Card], candidates: List[Card]) -> Dict[str, Any]:
    confirmed = [c for c in p1_all if c.role == "DECISION_SUGGESTION"]
    weak = [c for c in p1_all if c.role == "STRUCTURE_CANDIDATE"]
    warnings: List[str] = []
    if len(p0) > 20 and not confirmed:
        warnings.append("Dużo markerów P0, ale brak mocnych decyzji P1 — to prawdopodobnie tekst opisowy albo wymagający ręcznej interpretacji.")
    if len(weak) > len(confirmed) and weak:
        warnings.append("Więcej struktur słabo istotnych niż potwierdzonych P1 — UI powinien trzymać je w sekcji kandydatów, nie w głównych decyzjach.")
    if p2 and not confirmed and not candidates:
        warnings.append("P2 bez silnych P1/kandydatów wymaga ostrożnej kontroli.")
    risk = "low"
    if len(candidates) or len(p2) or len(weak) >= 3:
        risk = "medium"
    if len(confirmed) >= 5 or len(p2) >= 2:
        risk = "high"
    return {
        "schema": "analysis_quality_v1",
        "review_risk": risk,
        "warnings": warnings,
        "counts": {
            "p0": len(p0),
            "p1_confirmed": len(confirmed),
            "p1_weak_structures": len(weak),
            "p2_techniques": len(p2),
            "semantic_candidates": len(candidates),
        },
        "quality_gates": {
            "marker_is_not_p1": True,
            "p1_requires_structure": True,
            "p1_requires_relevance": True,
            "p2_requires_review": True,
            "suggestions_are_not_decisions": True,
            "p0_preview_visible": True,
            "o5_euphemisms_require_context": True,
            "o6_nominalizations_require_context": True,
            "o7_agent_hiding_requires_social_context": True,
        },
    }


def analysis_contract() -> Dict[str, Any]:
    return {
        "schema": "analysis_contract_v2_p0_p5",
        "levels": {
            "P0": "surowy marker / wskazówka / obserwacja; nie jest decyzją",
            "P1": "struktura językowa albo kandydat wymagający przeglądu",
            "P2": "potwierdzona technika retoryczna po walidatorze i filtrze istotności",
            "P3": "rama narracyjna z układu wielu sygnałów; hipoteza, nie wyrok",
            "P4": "strategia dyskursywna budowana przez powtarzalny układ P2/P3",
            "P5": "diagnoza syntetyczna całego fragmentu; zawsze wymaga kontroli człowieka",
        },
        "roles": {
            "RAW_SIGNAL": "P0 — pokazuj jako marker, nie jako decyzję",
            "STRUCTURE_CANDIDATE": "P1 — pełna struktura, ale niska/niepewna istotność; do przeglądu",
            "DECISION_SUGGESTION": "P2 — potwierdzona technika retoryczna",
            "SEMANTIC_CANDIDATE": "P1 — parafraza lub trop; wymaga przeglądu",
            "NARRATIVE_HYPOTHESIS": "P3 — możliwa rama narracyjna; nie werdykt",
            "DISCOURSE_STRATEGY": "P4 — strategia z wielu sygnałów; do kontroli",
            "SYNTHETIC_DIAGNOSIS": "P5 — syntetyczna diagnoza; najmocniej ostrożna",
            "BLOCKED_BY_GUARD": "P1 technicznie wykryte, ale zablokowane przez negację/neutralność/brak struktury",
            "REPORT_ONLY": "metryka lub komunikat, bez funkcji detekcyjnej",
        },
        "analysis_modes": {
            "Analizuj": "pokazuje TOP, P2/P3/P4/P5, kandydatów i P0 jako podgląd",
            "Szukaj sugestii": "pokazuje wyłącznie agregowane sugestie rozwojowe i kandydatów, nigdy decyzje",
        },
        "o4_rule": "Więcej poziomów oznacza większą ostrożność: P5 nie powstaje z jednego zdania, tylko z układu wielu sygnałów.",
        "o5_rule": "Eufemizm i język administracyjny są techniką dopiero wtedy, gdy słownictwo proceduralne dotyczy straty, decyzji lub ludzi; neutralne użycia zostają kandydatem.",
        "o6_rule": "Nominalizacja jest potwierdzoną techniką dopiero wtedy, gdy rzeczownik procesu/decyzji występuje w kontekście ludzi, lokali, kosztów społecznych albo sprawczości; neutralne techniczne użycia są pomijane lub zostają kandydatem.",
        "o7_rule": "Ukrycie sprawcy jest potwierdzoną techniką wtedy, gdy strona bierna lub forma bezosobowa dotyczy decyzji/procesu wobec ludzi, lokali albo praw. Neutralne pasywy techniczne są ignorowane lub zostają kandydatem.",
        "o8_rule": "Depolityzacja decyzji jest ramą P3: społeczny albo polityczny skutek zostaje opisany jako techniczna, ekonomiczna lub proceduralna konieczność. Wymaga kontekstu ludzi, lokali, uchwał, relokacji lub praw; neutralne techniczne zdania są ignorowane.",
    }



def p0_summary(p0: List[Card]) -> Dict[str, Any]:
    by_label = Counter(c.label for c in p0)
    by_phrase = Counter((c.label, c.phrase.lower()) for c in p0)
    examples: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    full: List[Dict[str, Any]] = []
    for c in p0:
        if len(examples[c.label]) < 5:
            examples[c.label].append({"phrase": c.phrase, "fragment": c.fragment, "why": c.why})
        full.append(c.to_dict())
    top_phrases = [
        {"label": label, "phrase": phrase, "count": count}
        for (label, phrase), count in by_phrase.most_common(20)
    ]
    return {
        "total": len(p0),
        "by_label": dict(by_label),
        "top_phrases": top_phrases,
        "examples": dict(examples),
        "full_raw_preview": full[:200],
        "note": "P0 to surowe markery. Pokazujemy podgląd i przykłady, ale P0 nie jest werdyktem ani techniką P1.",
    }



# -----------------------------
# Aktualna warstwa: szczegółowa skala P0–P5 i ranking wyników
# -----------------------------
LEVEL_NAMES = {
    "P0": "surowy marker",
    "P1": "struktura / kandydat do przeglądu",
    "P2": "potwierdzona technika retoryczna",
    "P3": "rama narracyjna",
    "P4": "strategia dyskursywna",
    "P5": "diagnoza syntetyczna",
}

LEVEL_BASE_RANK = {
    "P5": 600.0,
    "P4": 500.0,
    "P3": 400.0,
    "P2": 300.0,
    "P1": 150.0,
    "P0": 50.0,
}

STRONG_P2_LABELS = {
    "P1_falszywa_dychotomia",
    "P1_insynuacja",
    "P1_pytanie_retoryczne",
    "P1_antyteza",
    "P1_hiperbola",
    "P1_eufemizacja",
    "P1_jezyk_administracyjny",
    "P1_nominalizacja",
    "P1_ukrycie_sprawcy",
}


def _o4_level_for_card(card: Card) -> str:
    if card.role == "RAW_SIGNAL":
        return "P0"
    if card.role in {"STRUCTURE_CANDIDATE", "SEMANTIC_CANDIDATE", "BLOCKED_BY_GUARD"}:
        return "P1"
    if card.role == "DECISION_SUGGESTION":
        return "P2"
    if card.role == "NARRATIVE_HYPOTHESIS":
        return "P3"
    if card.role == "DISCOURSE_STRATEGY":
        return "P4"
    if card.role == "SYNTHETIC_DIAGNOSIS":
        return "P5"
    return card.level if card.level in LEVEL_NAMES else "P1"


def _confidence_bonus(value: str | None) -> float:
    return {"high": 12.0, "medium": 6.0, "low": 0.0}.get(str(value or ""), 3.0)


def _relevance_bonus(value: str | None) -> float:
    return {"high": 18.0, "medium": 8.0, "low": -8.0, "unknown": 0.0}.get(str(value or ""), 0.0)


def _apply_o4_level_and_rank(card: Card) -> Card:
    level = card.analysis_level or _o4_level_for_card(card)
    card.analysis_level = level
    card.analysis_level_name = LEVEL_NAMES.get(level, level)
    card.rank_score = round(
        LEVEL_BASE_RANK.get(level, 100.0)
        + float(card.score or 0.0)
        + _confidence_bonus(card.interpretation_confidence or card.confidence)
        + _relevance_bonus(card.analytical_relevance),
        3,
    )
    return card


def _sort_card_dicts(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(cards, key=lambda c: (float(c.get("rank_score", 0) or 0), float(c.get("score", 0) or 0)), reverse=True)


def _synthesis_evidence(text: str, supporting_cards: List[Card], max_span: int = 700) -> Dict[str, Any] | None:
    """Buduje P4/P5 wyłącznie z dosłownych wycinków analizowanego tekstu."""
    spans: List[Tuple[int, int, Card]] = []
    seen: set[Tuple[int, int, str]] = set()
    for card in supporting_cards:
        start, end = int(card.start or -1), int(card.end or -1)
        if not (0 <= start < end <= len(text)):
            fragment = str(card.fragment or "").strip()
            if fragment:
                start = text.casefold().find(fragment.casefold())
                end = start + len(fragment) if start >= 0 else -1
        if not (0 <= start < end <= len(text)):
            continue
        key = (start, end, card.label)
        if key in seen:
            continue
        seen.add(key)
        spans.append((start, end, card))
    if not spans:
        return None

    spans.sort(key=lambda row: (row[0], row[1]))
    combined_start, combined_end = spans[0][0], spans[-1][1]
    if combined_end - combined_start <= max_span:
        start, end = combined_start, combined_end
        selected = spans
    else:
        best = max(spans, key=lambda row: (float(row[2].score or 0), -(row[1] - row[0])))
        start, end = best[0], best[1]
        selected = [best]

    window = text[start:end]
    phrase = ""
    for _, _, card in sorted(selected, key=lambda row: float(row[2].score or 0), reverse=True):
        candidate = str(card.phrase or "").strip()
        if 3 <= len(candidate) <= 180 and candidate.casefold() in window.casefold():
            phrase = candidate
            break
    if not phrase:
        shortest = min((text[s:e] for s, e, _ in selected if e > s), key=len, default="").strip()
        phrase = shortest[:180].rsplit(" ", 1)[0] if len(shortest) > 180 else shortest
    if len(phrase) < 3 or phrase.casefold() not in window.casefold():
        return None

    exact_fragments: List[str] = []
    for s, e, _ in spans:
        fragment = text[s:e].strip()
        if fragment and fragment not in exact_fragments:
            exact_fragments.append(fragment)
        if len(exact_fragments) >= 8:
            break
    return {
        "fragment": window,
        "phrase": phrase,
        "start": start,
        "end": end,
        "evidence_fragments": exact_fragments,
        "supporting_labels": list(dict.fromkeys(card.label for _, _, card in spans)),
    }


def _add_synthesis_card(
    target: List[Card], text: str, support: List[Card], *, label: str, level: str,
    role: str, score: float, why: str, confidence: str = "medium", max_span: int = 700,
) -> None:
    evidence = _synthesis_evidence(text, support, max_span=max_span)
    if not evidence:
        return
    add_unique(target, Card(
        label, level, role, evidence["fragment"], phrase=evidence["phrase"],
        start=evidence["start"], end=evidence["end"],
        evidence_fragments=evidence["evidence_fragments"],
        supporting_labels=evidence["supporting_labels"],
        confidence=confidence, pattern_confidence="medium",
        interpretation_confidence="low" if level == "P5" else "medium",
        score=score, analytical_relevance="high", requires_review=True, why=why,
    ))


def detect_p4_p5(text: str, p0: List[Card], p1_all: List[Card], p2: List[Card], candidates: List[Card]) -> Tuple[List[Card], List[Card]]:
    """Agreguje wiele sygnałów, zachowując dokładny i klikalny dowód P4/P5."""
    strategies: List[Card] = []
    diagnoses: List[Card] = []
    confirmed = [c for c in p1_all if c.role == "DECISION_SUGGESTION"]
    p2_labels = {c.label for c in p2}
    n = norm_ascii(text)

    if len(p2) >= 2 and confirmed:
        _add_synthesis_card(
            strategies, text, p2 + confirmed,
            label="P4_strategia_argumentacyjna", level="P4", role="DISCOURSE_STRATEGY", score=4.8,
            why="Kilka potwierdzonych technik P2 tworzy możliwą strategię argumentacyjną w skali całego fragmentu.",
        )

    legitimizing_labels = {
        "P2_ramowanie_bezpieczenstwa", "P3_naturalizacja_koniecznosci", "P3_depolityzacja_decyzji",
    }
    necessity_signal = re.search(
        r"\b(?:koniecznosc|konieczno[śs][ćc]|musi|musimy|trzeba|nie ma alternatywy|"
        r"nie ma realnej alternatywy|nie moze czekac|rozwoj jest konieczn\w*|"
        r"rozw[oó]j jest konieczn\w*|zagrozenie|zagrożenie|bezpieczenstwo|bezpieczeństwo)\b",
        n,
    )
    if p2_labels.intersection(legitimizing_labels) and necessity_signal:
        support = [c for c in p2 if c.label in legitimizing_labels]
        support += [c for c in p0 if c.label == "P0_rama_bezpieczenstwa"]
        _add_synthesis_card(
            strategies, text, support,
            label="P4_strategia_legitymizacji", level="P4", role="DISCOURSE_STRATEGY", score=4.6,
            why="Język konieczności lub bezpieczeństwa współwystępuje z wykrytą ramą decyzji; to możliwa strategia legitymizowania decyzji.",
        )

    if "P3_depolityzacja_decyzji" in p2_labels and confirmed:
        support = [c for c in p2 if c.label == "P3_depolityzacja_decyzji"] + confirmed
        _add_synthesis_card(
            strategies, text, support,
            label="P4_strategia_depolityzacji", level="P4", role="DISCOURSE_STRATEGY", score=4.9,
            why="O8: rama depolityzacji współwystępuje z potwierdzonymi technikami. To możliwa strategia dyskursywna, nie wyrok.",
        )

    if "P3_naturalizacja_koniecznosci" in p2_labels and (confirmed or "P3_depolityzacja_decyzji" in p2_labels):
        support = [c for c in p2 if c.label in {"P3_naturalizacja_koniecznosci", "P3_depolityzacja_decyzji"}] + confirmed
        _add_synthesis_card(
            strategies, text, support,
            label="P4_strategia_naturalizacji", level="P4", role="DISCOURSE_STRATEGY", score=4.8,
            why="O9: rama konieczności współwystępuje z technikami P2 albo z depolityzacją. To możliwa strategia, nie wyrok.",
        )

    if "P3_rozsadek_kontra_emocje" in p2_labels and (confirmed or "P3_naturalizacja_koniecznosci" in p2_labels or "P3_depolityzacja_decyzji" in p2_labels):
        support = [c for c in p2 if c.label in {"P3_rozsadek_kontra_emocje", "P3_naturalizacja_koniecznosci", "P3_depolityzacja_decyzji"}] + confirmed
        _add_synthesis_card(
            strategies, text, support,
            label="P4_strategia_rozsadek_emocje", level="P4", role="DISCOURSE_STRATEGY", score=4.85,
            why="O10: rama rozsądku kontra emocji współwystępuje z technikami lub innymi ramami. To hipoteza do kontroli.",
        )

    if strategies and len(p2) >= 2 and (len(confirmed) + len(p2) + len(candidates)) >= 3:
        _add_synthesis_card(
            diagnoses, text, strategies + p2 + confirmed,
            label="P5_diagnoza_syntetyczna", level="P5", role="SYNTHETIC_DIAGNOSIS", score=5.0,
            confidence="low", max_span=900,
            why="Diagnoza syntetyczna powstała dopiero po wykryciu strategii P4 i kilku dokładnie zakotwiczonych sygnałów. To hipoteza do kontroli człowieka.",
        )

    for card in strategies + diagnoses:
        _apply_o4_level_and_rank(card)
    return strategies, diagnoses

def scientific_layer() -> Dict[str, Any]:
    return {
        "schema": "scientific_foundations_v1",
        "principle": "P0 = marker, P1 = struktura z walidatorem i istotnością, P2 = hipoteza narracyjna.",
        "sources_map": _load_json("scientific_sources_map.json", {}),
        "category_theory_map": THEORY_MAP,
        "quality_rule": "Marker bez struktury zostaje P0; struktura opisowa zostaje kandydatem; struktura argumentacyjnie istotna może wejść do P1.",
    }



def analyze_text(text: str) -> Dict[str, Any]:
    """Publiczny punkt wejścia: zawsze jeden aktywny rdzeń."""
    from .active_analysis import analyze_active
    return analyze_active(text)

def _aggregate_suggestions(p0: List[Card], p1_all: List[Card], candidates: List[Card], text: str) -> List[Dict[str, Any]]:
    return build_clean_suggestions(
        card_factory=Card,
        p0=p0,
        p1_all=p1_all,
        candidates=candidates,
        text=text,
    )


def suggest_text(text: str) -> Dict[str, Any]:
    pipeline = build_pipeline_context(text)
    original_text = pipeline.original_text
    cleaning = {"source_text": pipeline.analyzable_text, "meta_text": "", "metatext_segments": [], "removed_characters": int((pipeline.cleaning or {}).get("removed_characters", 0) or 0), "metatext_detected": bool(pipeline.metadata_segments)}
    # aktywny pipeline: wszystkie analizatory dostają wyłącznie ten sam tekst analityczny.
    text = normalize(pipeline.analyzable_text)
    p0 = detect_p0(text)
    p1_all = detect_p1(text)
    candidates = detect_semantic_candidates(text)
    suggestions = _aggregate_suggestions(p0, p1_all, candidates, text)
    return {
        "ok": True,
        "stage": STAGE,
        "schema": "czyste_sugestie_current_v1",
        "tekst_znormalizowany": text,
        "text_cleaning": cleaning,
        "pipeline_segments": pipeline.segments,
        "pipeline_metadata_segments": pipeline.metadata_segments,
        "suggestions": suggestions,
        "suggestions_count": len(suggestions),
        "podsumowanie_sugestii": polish_suggestions_summary(suggestions),
        "p0_summary": p0_summary(p0),
        "scientific_layer": scientific_layer(),
        "linguistic_profile": linguistic_profile(text, p0, p1_all, [], candidates),
        "analysis_quality": result_quality(p0, p1_all, [], candidates),
        "analysis_contract": analysis_contract(),
        "text_overview": build_text_overview(text),
        "api_shape": stable_api_shape(),
        "policy": "Current: sugestie są pomocnicze; analiza wejścia używa czyszczenia metatekstu i kandydatów semantycznych 2.0.",
    }
