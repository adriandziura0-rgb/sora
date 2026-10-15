"""Read-only presentation of the shared engine's public results."""
SECTIONS = {
 'top_najwazniejszych_relacji':'Najważniejsze relacje', 'relacje_wypowiedzi':'Kto mówi, o kim i co',
 'fact_opinia_cytat':'Fakty, opinie i cytaty', 'fact_opinion_quote':'Fakty, opinie i cytaty',
 'mapa_aktorow':'Aktorzy i instytucje', 'mapa_sprawczosci':'Działania i odpowiedzialność',
 'mapa_zrodel':'Źródła i media', 'potwierdzone_p1':'P1 · potwierdzone struktury',
 'techniki_p2':'P2 · techniki', 'ramy_p3':'P3 · ramy przekazu', 'strategie_p4':'P4 · strategie',
 'diagnozy_p5':'P5 · diagnozy', 'kandydaci_p1':'Kandydaci struktur',
 'kandydaci_semantyczni':'Kandydaci semantyczni', 'kandydaci_struktur':'Struktury do kontroli',
 'zablokowane_przez_bramki':'Odrzucone relacje', 'audyt_bramek_degradacji':'Kontrola bramek jakości',
 'audyt_rol_relacji':'Kontrola przypisania ról', 'audyt_widocznosci':'Kontrola widoczności',
 'raport_skutecznosci_semantycznej':'Skuteczność analizy semantycznej',
}


def materialize(payload):
    """Same aggregate projection as the PHONE view; the payload stays intact."""
    if 'zbiorczy_rejestr_kart' not in payload:return payload
    result=dict(payload);registry=payload['zbiorczy_rejestr_kart'];refs=payload.get('zbiorcze_referencje_sekcji',{})
    result['sekcje']={name:[registry[i] for i in ids if i in registry] for name,ids in refs.items() if name!='__p0_pelny_podglad'}
    result['jednostki_znaczenia']=payload.get('zbiorcze_jednostki_znaczenia',[])
    result['p0']=dict(payload.get('p0',{}));result['p0']['pelny_podglad']=[registry[i] for i in result['p0'].get('pelny_podglad_refy',refs.get('__p0_pelny_podglad',[])) if i in registry]
    return result


def card_lines(card):
    """User labels only; no schema names, UUIDs, or internal confidence fields."""
    rel=card.get('canonical_relation') or {}
    pairs=[('Mówca',card.get('mowca') or card.get('kto_mowi') or card.get('aktor') or rel.get('speaker')),
           ('Działanie',card.get('dzialanie_mowcy') or card.get('dzialanie') or rel.get('speaker_action')),
           ('Twierdzenie',card.get('claim') or (card.get('relacja_wypowiedzi') or {}).get('co_mowi') or rel.get('claim')),
           ('Dotyczy',card.get('o_kim') or card.get('target') or card.get('dotyczy') or rel.get('target')),
           ('Źródło',card.get('zrodlo_przywolane') or card.get('zrodlo') or rel.get('source')),
           ('Źródło dokumentu',card.get('zrodlo_dokumentu') or rel.get('document_source')),
           ('Medium',card.get('medium') or rel.get('medium')), ('Program',card.get('program') or rel.get('program')),
           ('Temat',card.get('temat') or card.get('topic')), ('Typ twierdzenia',card.get('typ_twierdzenia')),
           ('Wyjaśnienie',card.get('uzasadnienie'))]
    seen=set();out=[]
    for label,value in pairs:
        if value and str(value) not in seen:out.append((label,str(value)));seen.add(str(value))
    if not out:
        value=card.get('wartosc') or card.get('fraza') or card.get('fragment') or card.get('opis')
        if value:out.append(('',str(value)))
    return out


def evidence_range(card,text):
    start,end=card.get('poczatek',-1),card.get('koniec',-1)
    if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(text):return None
    fragment=card.get('fragment') or card.get('evidence_text')
    if fragment and text[start:end] != fragment:return None
    if card.get('link_status') not in ('linked',None):return None
    return start,end


def readable_report(result):
    public=result.get('raport_czytelny') or {}
    lines=['DROGOWSKAZY · WYNIK ANALIZY','']
    for item in public.get('items',[]):
        lines.extend([item.get('tytul',''),str(item.get('wartosc','')),item.get('opis',''),''])
    sections=result.get('sekcje',{})
    if result.get('jednostki_znaczenia'):sections={'najwazniejsze':result['jednostki_znaczenia'],**sections}
    for name,cards in sections.items():
        if not cards:continue
        lines.extend([SECTIONS.get(name,name.replace('_',' ').capitalize()),''])
        for card in cards:
            lines.append(card.get('tytul') or 'Relacja')
            lines.extend(f'{label}: {value}' if label else value for label,value in card_lines(card))
            if card.get('fragment'):lines.append('Fragment źródłowy: '+card['fragment'])
            if card.get('wymaga_przegladu'):lines.append('Wymaga sprawdzenia przez człowieka.')
            lines.append('')
    if public.get('do_sprawdzenia'):lines.extend(['Do sprawdzenia',*public['do_sprawdzenia']])
    return '\n'.join(lines)


def write_pdf(path,text):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    from xml.sax.saxutils import escape
    fonts=[Path('C:/Windows/Fonts/segoeui.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font=next((p for p in fonts if p.exists()),None)
    if font is None:raise ValueError('Nie znaleziono czcionki z polskimi znakami do PDF.')
    pdfmetrics.registerFont(TTFont('SoraPolski',str(font)))
    styles=getSampleStyleSheet();style=styles['BodyText'];style.fontName='SoraPolski';style.fontSize=10;style.leading=15
    blocks=[]
    for line in text.splitlines():
        if line:blocks.append(Paragraph(escape(line),style))
        else:blocks.append(Spacer(1,8))
    SimpleDocTemplate(str(path),leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=42).build(blocks)
