from __future__ import annotations

from typing import Any, Dict, List, Tuple

SCHEMAT_PODSWIETLEN_PL = "podswietlanie_tekstu_current_v2_slim"


def _lista(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _poziom_sort(poziom: str) -> int:
    """Priorytet prezentacji: P2 zasłania P1, P1 zasłania P0."""
    return {"P5": 0, "P4": 1, "P3": 2, "P2": 3, "P1": 4, "P0": 5}.get(str(poziom or "").upper(), 99)


def _slug_techniki(nazwa: str) -> str:
    """Stabilna klasa CSS dla rodzaju techniki, bez wprowadzania logiki detekcji do UI."""
    raw = str(nazwa or "").lower()
    mapa = {
        "kontrast": "kontrast",
        "hiperbola": "hiperbola",
        "generalizacja": "generalizacja",
        "pytanie retoryczne": "pytanie-retoryczne",
        "retoryczne": "pytanie-retoryczne",
        "fałszywa dychotomia": "falszywa-dychotomia",
        "falszywa dychotomia": "falszywa-dychotomia",
        "antyteza": "antyteza",
        "wyliczenie": "wyliczenie",
        "insynuacja": "insynuacja",
        "rama zagrożenia": "rama-zagrozenia",
        "zagrożenia": "rama-zagrozenia",
        "zagrozenia": "rama-zagrozenia",
        "bezpieczeństwo": "bezpieczenstwo",
        "bezpieczenstwo": "bezpieczenstwo",
        "kontrola": "kontrola",
        "chaos": "chaos",
    }
    for needle, slug in mapa.items():
        if needle in raw:
            return slug
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:40] or "inne"


def _karty_z_analizy(analiza_pl: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Zbiera tylko aktywne karty, które mogą mieć podświetlenie w tekście."""
    sekcje = analiza_pl.get("sekcje", {}) or {}
    out: List[Dict[str, Any]] = []
    kolejnosc = [
        "top_wyniki", "fact_opinia_cytat", "relacje_wypowiedzi",
        "diagnozy_p5", "strategie_p4", "ramy_p3", "techniki_p2",
        "potwierdzone_p1", "kandydaci_p1", "mapa_aktorow", "mapa_zrodel",
        "mapa_sprawczosci", "kandydaci_struktur", "kandydaci_semantyczni",
        "zablokowane_przez_bramki",
    ]
    for nazwa in kolejnosc:
        for x in _lista(sekcje.get(nazwa)):
            if isinstance(x, dict):
                item = dict(x)
                item.setdefault("sekcja_podgladu", nazwa)
                out.append(item)
    p0 = analiza_pl.get("p0", {}) or {}
    for x in _lista(p0.get("pelny_podglad")):
        if isinstance(x, dict):
            item = dict(x)
            item.setdefault("sekcja_podgladu", "p0_pelny_podglad")
            out.append(item)
    return out


def _szukaj_frazy_w_zakresie(tekst: str, fraza: str, s: int, e: int) -> Tuple[int, int] | None:
    fraza = str(fraza or "").strip()
    if not fraza or len(fraza) < 3:
        return None
    # Nie próbujemy robić z całych akapitów osobnej frazy. Dla czytelności
    # szukamy krótkiego rdzenia dowodowego, a nie długiego opisu karty.
    kandydaci = [fraza]
    if len(fraza) > 180:
        kandydaci.append(fraza[:180].rsplit(" ", 1)[0])
    if len(fraza) > 90:
        kandydaci.append(fraza[:90].rsplit(" ", 1)[0])
    okno = tekst[max(0, s): min(len(tekst), e)]
    low_okno = okno.lower()
    for kand in kandydaci:
        kand = kand.strip()
        if len(kand) < 3:
            continue
        idx = low_okno.find(kand.lower())
        if idx >= 0:
            return s + idx, s + idx + len(kand)
    return None


def _czy_warto_skrocic(karta: Dict[str, Any], s: int, e: int) -> bool:
    dl = e - s
    poziom = str(karta.get("poziom") or karta.get("level") or "").upper()
    sekcja = str(karta.get("sekcja_podgladu") or "").lower()
    rola = str(karta.get("rola_techniczna") or karta.get("rola") or "").lower()
    # Warstwa prezentacji
    # zamieniać całych akapitów w jeden ciężki blok koloru. Podświetlamy rdzeń.
    if dl <= 220:
        return False
    if poziom in {"P2", "P3", "P4", "P5"}:
        return True
    if sekcja in {"fact_opinia_cytat", "relacje_wypowiedzi"}:
        return True
    if "statement" in rola or "wypowied" in rola or "fact_opinion" in rola:
        return True
    return False


def _znajdz_zakres(tekst: str, karta: Dict[str, Any]) -> Tuple[int, int] | None:
    start = karta.get("poczatek")
    end = karta.get("koniec")
    fraza = str(karta.get("fraza") or "").strip()
    try:
        s, e = int(start), int(end)
        if 0 <= s < e <= len(tekst):
            if _czy_warto_skrocic(karta, s, e):
                core = _szukaj_frazy_w_zakresie(tekst, fraza, s, e)
                if core:
                    return core
                # Warstwa prezentacji
                # Jeżeli nie da się znaleźć krótkiego rdzenia dowodowego, nie robimy
                # ogromnego podświetlenia w tekście. Karta zostaje w panelu.
                poziom = str(karta.get("poziom") or karta.get("level") or "").upper()
                if poziom in {"P4", "P5"}:
                    return None
            return s, e
    except Exception:
        pass

    fragment = str(karta.get("fragment") or "").strip()
    if fragment:
        idx = tekst.find(fragment)
        if idx >= 0:
            s, e = idx, idx + len(fragment)
            if _czy_warto_skrocic(karta, s, e):
                core = _szukaj_frazy_w_zakresie(tekst, fraza, s, e)
                if core:
                    return core
                # Warstwa prezentacji
                # Jeżeli nie da się znaleźć krótkiego rdzenia dowodowego, nie robimy
                # ogromnego podświetlenia w tekście. Karta zostaje w panelu.
                poziom = str(karta.get("poziom") or karta.get("level") or "").upper()
                if poziom in {"P4", "P5"}:
                    return None
            return s, e
        idx = tekst.lower().find(fragment.lower())
        if idx >= 0:
            s, e = idx, idx + len(fragment)
            if _czy_warto_skrocic(karta, s, e):
                core = _szukaj_frazy_w_zakresie(tekst, fraza, s, e)
                if core:
                    return core
            return s, e

    # Current: encja kanoniczna może występować w tekście w formie
    # fleksyjnej. Nawigacja korzysta więc z zapisanych surface_forms, a nie
    # wymaga dosłownego mianownika.
    probes = []
    probes.extend(karta.get("surface_forms") or [])
    relation = karta.get("canonical_relation") if isinstance(karta.get("canonical_relation"), dict) else {}
    probes.extend(relation.get("evidence") or [])
    probes.extend([relation.get("sentence"), relation.get("claim"), fraza])
    for probe in probes:
        if isinstance(probe, dict):
            probe = probe.get("text") or probe.get("fragment") or ""
        probe = str(probe or "").strip()
        if len(probe) < 3:
            continue
        idx = tekst.casefold().find(probe.casefold())
        if idx >= 0:
            return idx, idx + len(probe)
    return None


def _buduj_span(karta: Dict[str, Any], zakres: Tuple[int, int]) -> Dict[str, Any]:
    s, e = zakres
    return {
        "poczatek": s,
        "koniec": e,
        "poziom": karta.get("poziom") or "INFO",
        "tytul": karta.get("tytul") or "Trafienie",
        "typ_techniki": _slug_techniki(karta.get("tytul") or karta.get("fraza") or ""),
        "rola": karta.get("rola") or "",
        "rola_techniczna": karta.get("rola_techniczna") or "",
        "sekcja_podgladu": karta.get("sekcja_podgladu") or "",
        "fraza": karta.get("fraza") or "",
        "fragment": karta.get("fragment") or "",
        "uzasadnienie": karta.get("uzasadnienie") or "",
        "pewnosc": karta.get("pewnosc") or "",
        "wymaga_przegladu": bool(karta.get("wymaga_przegladu")),
        "highlight_id": karta.get("highlight_id") or "",
        "link_status": karta.get("link_status") or "",
        "zasloniete": [],
    }


def _z_id(spany: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    out = []
    for i, span in enumerate(spany):
        item = dict(span)
        item["id"] = str(item.get("highlight_id") or f"{prefix}-{i}")
        out.append(item)
    return out


def _iteruj_karty_mutowalne(analiza_pl: Dict[str, Any]):
    """Iteruje po kartach prezentacyjnych, które mogą być połączone z tekstem."""
    sekcje = analiza_pl.get("sekcje", {}) or {}
    for nazwa, lista in list(sekcje.items()):
        if isinstance(lista, list):
            for karta in lista:
                if isinstance(karta, dict):
                    karta.setdefault("sekcja_podgladu", nazwa)
                    yield nazwa, karta
    p0 = analiza_pl.get("p0", {}) or {}
    lista = p0.get("pelny_podglad")
    if isinstance(lista, list):
        for karta in lista:
            if isinstance(karta, dict):
                karta.setdefault("sekcja_podgladu", "p0_pelny_podglad")
                yield "p0_pelny_podglad", karta


def uzupelnij_linki_kart_do_tekstu(tekst: str, analiza_pl: Dict[str, Any]) -> Dict[str, Any]:
    """aktywny kontrakt: łączy karty z podświetleniami 1:1, bez ślepych przycisków."""
    tekst = tekst or ""
    linked = 0
    missing = 0
    total = 0
    for total, (_sekcja, karta) in enumerate(_iteruj_karty_mutowalne(analiza_pl), start=1):
        zakres = _znajdz_zakres(tekst, karta)
        if zakres:
            s, e = zakres
            karta["poczatek"] = s
            karta["koniec"] = e
            karta["highlight_id"] = karta.get("highlight_id") or f"hl-card-{total}"
            karta["link_status"] = "linked"
            karta["brak_podswietlenia_powod"] = ""
            linked += 1
        else:
            karta.setdefault("highlight_id", "")
            karta["link_status"] = "missing_exact_evidence"
            if karta.get("fragment") or karta.get("fraza"):
                karta["brak_podswietlenia_powod"] = "Nie znaleziono dokładnej frazy w oczyszczonym tekście."
            else:
                karta["brak_podswietlenia_powod"] = "Karta nie ma dokładnego cytatu/frazy do podświetlenia."
            missing += 1
    analiza_pl["linkowanie_kart"] = {
        "schemat": "card_highlight_links_current_v1",
        "liczba_kart": total,
        "podlaczone": linked,
        "bez_dokladnego_fragmentu": missing,
        "zasada": "Przycisk Pokaż w tekście pojawia się tylko wtedy, gdy karta ma jednoznaczny fragment w tekście."
    }
    return analiza_pl

def buduj_podglad_tekstu(tekst: str, analiza_pl: Dict[str, Any], widok: str = "wszystko") -> Dict[str, Any]:
    """Lekki kontrakt podglądu: jeden tekst + jedna lista surowych spanów.

    Selekcja widoku, usuwanie nakładek i budowa HTML są deterministyczną
    warstwą prezentacji i wykonują się w przeglądarce. Dzięki temu JSON nie
    powiela tych samych zakresów ani całego tekstu czternaście razy.
    """
    tekst = tekst or ""
    wszystkie: List[Dict[str, Any]] = []
    for karta in _karty_z_analizy(analiza_pl):
        zakres = _znajdz_zakres(tekst, karta)
        if zakres:
            wszystkie.append(_buduj_span(karta, zakres))

    wszystkie = sorted(
        wszystkie,
        key=lambda x: (int(x.get("poczatek", 0)), _poziom_sort(str(x.get("poziom") or ""))),
    )
    return {
        "schemat": SCHEMAT_PODSWIETLEN_PL,
        "zasada": "Jeden tekst i jedna lista spanów; widoki oraz HTML są składane lokalnie w przeglądarce.",
        "renderowanie": "client_side_from_raw_spans_v2",
        "tekst": tekst,
        "spany_surowe": _z_id(wszystkie, "raw"),
        "widoki_dostepne": [
            "wszystko", "czyste", "aktorzy", "sprawczosc", "zrodla", "fact", "relacje",
            "p5", "p4", "p3", "p2", "p1", "p0", "kandydaci",
        ],
    }
