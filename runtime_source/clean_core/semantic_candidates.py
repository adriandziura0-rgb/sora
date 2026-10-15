from __future__ import annotations

import re
from typing import Any, Dict, List

PL_TRANS = str.maketrans({
    "ą":"a","ć":"c","ę":"e","ł":"l","ń":"n","ó":"o","ś":"s","ź":"z","ż":"z",
    "Ą":"a","Ć":"c","Ę":"e","Ł":"l","Ń":"n","Ó":"o","Ś":"s","Ź":"z","Ż":"z",
})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(PL_TRANS).lower()).strip()

PATTERNS: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("SEM_PROCEDURA_JAKO_UKRYTY_ROZKAZ", "procedura jako ukryty rozkaz", "Fragment sugeruje, że przymus lub decyzja wobec ludzi jest opisana jako neutralna procedura.", re.compile(r"\b(?:procedur\w*|proces\w*|zostanie\s+uruchomion\w*|lokal\w*\s+zostan\w*\s+wskazan\w*|zostan\w*\s+objec\w*)\b.*\b(?:mieszkanc\w*|lokator\w*|najemc\w*|relokac\w*|przenies\w*)\b|\b(?:mieszkanc\w*|lokator\w*|najemc\w*)\b.*\b(?:procedur\w*|proces\w*|zostan\w*)\b", re.I)),
    ("SEM_LUDZIE_JAKO_RYZYKO_KOMUNIKACYJNE", "ludzie jako ryzyko komunikacyjne", "Ludzie lub protest zostają opisani jako problem komunikacji, wizerunku albo zarządzania ryzykiem.", re.compile(r"\b(?:mieszkanc\w*|lokator\w*|protest\w*|aktywist\w*)\b.*\b(?:ryzyk\w*\s+komunikacyjn\w*|problem\w*\s+wizerunk\w*|zarzadzani\w*\s+komunikac\w*)\b|\bryzyk\w*\s+komunikacyjn\w*\b", re.I)),
    ("SEM_ROZWOJ_JAKO_MORALNY_PRZYMUS", "rozwój jako moralny przymus", "Rozwój jest przedstawiany jako dobro nadrzędne, a sprzeciw jako blokowanie dobra wspólnego.", re.compile(r"\b(?:rozwoj\w*|modernizac\w*|inwestyc\w*)\b.*\b(?:konieczn\w*|musi|trzeba|nie\s+ma\s+alternatywy|blokuj\w*|zatrzym\w*)\b|\b(?:blokuj\w*|zatrzym\w*)\b.*\b(?:rozwoj\w*|modernizac\w*)\b", re.I)),
    ("SEM_RELOKACJA_JAKO_UTRATA", "relokacja jako eufemizm utraty", "Neutralny termin relokacji/reorganizacji może przykrywać utratę domu, miejsca albo relacji społecznych.", re.compile(r"\b(?:relokac\w*|reorganizac\w*|optymalizac\w*)\b.*\b(?:dom\w*|mieszkan\w*|lokal\w*|utrac\w*|strat\w*|przenies\w*)\b|\b(?:utrac\w*|strat\w*)\b.*\b(?:relokac\w*|reorganizac\w*)\b", re.I)),
    ("SEM_BEZPIECZENSTWO_JAKO_KONTROLA", "bezpieczeństwo jako rama kontroli", "Język bezpieczeństwa/stabilności może przesuwać uwagę z kosztów społecznych na ochronę procesu.", re.compile(r"\b(?:bezpieczenstw\w*|stabiln\w*|ochron\w*|zagrozen\w*|destabilizac\w*)\b.*\b(?:proces\w*|procedur\w*|porzadk\w*|krytyk\w*|protest\w*)\b", re.I)),
    ("SEM_PRZECIEK_JAKO_DESTABILIZACJA", "przeciek jako destabilizacja", "Ujawnienie informacji jest przedstawiane jako zagrożenie dla procesu, a nie jako kontrola społeczna.", re.compile(r"\b(?:przeciek\w*|ujawnien\w*|wyciek\w*)\b.*\b(?:destabilizac\w*|zagrozen\w*|atak\w*|cyniczn\w*)\b|\b(?:destabilizac\w*)\b.*\b(?:przeciek\w*|ujawnien\w*)\b", re.I)),
    ("SEM_KAPITAL_JAKO_NIEWIDZIALNY_BENEFICJENT", "kapitał jako niewidzialny beneficjent", "Inwestor/deweloper/kapitał może być beneficjentem procesu, ale niekoniecznie jawnym sprawcą.", re.compile(r"\b(?:kapital\w*|inwestor\w*|deweloper\w*)\b.*\b(?:zysk\w*|skorzyst\w*|beneficjent\w*|przewag\w*)\b", re.I)),
    ("SEM_KONSULTACJE_JAKO_RYTUAL", "konsultacje jako rytuał legitymizacji", "Konsultacje mogą być opisane jako rozmowa pozorna, która zatwierdza decyzję zamiast dawać realny wpływ.", re.compile(r"\b(?:konsultac\w*|dialog\w*|spotkan\w*)\b.*\b(?:pozorn\w*|rytual\w*|legitymiz\w*|bez\s+realnego\s+wplywu|decyzj\w*\s+zapadl\w*)\b", re.I)),
    ("SEM_EMOCJE_JAKO_DELEGITYMIZACJA", "emocje jako delegitymizacja", "Emocje są przeciwstawiane rozsądkowi, realizmowi lub odpowiedzialności, co może osłabiać głos mieszkańców.", re.compile(r"\b(?:emocj\w*|strach\w*|lek\w*|sentyment\w*)\b.*\b(?:rozsad\w*|odpowiedzialn\w*|racjonaln\w*|nie\s+mog\w*\s+zastapic|blokuj\w*)\b", re.I)),
    ("SEM_MIASTO_JAKO_PROCES", "miasto jako proces zamiast wspólnoty", "Miasto jest opisywane jako strategia/proces/harmonogram, a nie jako wspólnota mieszkańców.", re.compile(r"\bmiast\w*\b.*\b(?:proces\w*|strategi\w*|harmonogram\w*|wdrozen\w*|optymalizac\w*)\b", re.I)),
]


def detect_semantic_candidate_specs(sentence: str) -> List[Dict[str, Any]]:
    n = _norm(sentence)
    out: List[Dict[str, Any]] = []
    for label, phrase, why, rx in PATTERNS:
        if rx.search(n):
            out.append({"label": label, "phrase": phrase, "why": why})
    return out
