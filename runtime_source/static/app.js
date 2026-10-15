
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c] || c));
let ostatnieDane = null;
let ostatnieSpanyPodgladu = [];
let aktywnyWidokPodgladu = 'wszystko';
let aktywnyTrybPracy = 'analiza';
let trybyPracy = null;
let ostatniZbiorczyPayload = null;
let zbiorczeDokumentyMap = {};
let ostatniePorownanieBazy = null;
let ostatniePorownanieTejSamejSprawy = null;
let wykryteTematyBazy = [];
let benchmarkProba = [];
let benchmarkIndex = 0;
let goldProba = [];
let goldIndex = 0;

let aktywnaOperacjaPostepu = 0;
let timerPostepuOperacji = null;
let timerUkryciaPostepu = null;


// Lokalna sesja robocza. Dane zostają wyłącznie w przeglądarce użytkownika.
// IndexedDB jest używane zamiast localStorage, bo wynik analizy i wiele dokumentów
// mogą mieć rozmiar większy niż rozsądny limit localStorage.
const SESSION_DB_NAME = 'drogowskazy.session';
const SESSION_DB_VERSION = 1;
const SESSION_STORE = 'state';
const SESSION_KEY = 'current';
let timerZapisuSesji = null;
let sesjaWTrakciePrzywracania = false;
let oczekujacyStanBazySesji = null;

function ustawStatusSesji(tekst, typ='ok'){
  const el = $('sessionStatus');
  if(!el) return;
  el.textContent = tekst || '';
  el.dataset.state = typ;
}

function otworzBazeSesji(){
  return new Promise((resolve, reject) => {
    if(!('indexedDB' in window)) return reject(new Error('IndexedDB niedostępne w tej przeglądarce.'));
    const req = indexedDB.open(SESSION_DB_NAME, SESSION_DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if(!db.objectStoreNames.contains(SESSION_STORE)) db.createObjectStore(SESSION_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('Nie udało się otworzyć lokalnej bazy sesji.'));
  });
}

async function zapiszSnapshotSesji(snapshot){
  const db = await otworzBazeSesji();
  try{
    await new Promise((resolve, reject) => {
      const tx = db.transaction(SESSION_STORE, 'readwrite');
      tx.objectStore(SESSION_STORE).put(snapshot, SESSION_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error('Nie udało się zapisać sesji.'));
      tx.onabort = () => reject(tx.error || new Error('Zapis sesji został przerwany.'));
    });
  } finally { db.close(); }
}

async function odczytajSnapshotSesji(){
  const db = await otworzBazeSesji();
  try{
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(SESSION_STORE, 'readonly');
      const req = tx.objectStore(SESSION_STORE).get(SESSION_KEY);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error || new Error('Nie udało się odczytać sesji.'));
    });
  } finally { db.close(); }
}

async function usunSnapshotSesji(){
  clearTimeout(timerZapisuSesji); timerZapisuSesji = null;
  try{
    const db = await otworzBazeSesji();
    try{
      await new Promise((resolve, reject) => {
        const tx = db.transaction(SESSION_STORE, 'readwrite');
        tx.objectStore(SESSION_STORE).delete(SESSION_KEY);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error || new Error('Nie udało się usunąć sesji.'));
      });
    } finally { db.close(); }
    ustawStatusSesji('Sesja lokalna wyczyszczona.', 'empty');
  }catch(err){
    ustawStatusSesji(`Nie udało się wyczyścić zapisu: ${err.message || err}`, 'error');
  }
}

function snapshotBiezacejSesji(){
  const pole = $('textInput');
  return {
    schema: 1,
    saved_at: new Date().toISOString(),
    tekst: pole ? String(pole.value || '') : '',
    wynik: (ostatnieDane && ostatnieDane.aggregate_from_database) ? (ostatniZbiorczyPayload || kompaktujZbiorczyPayload(ostatnieDane)) : (ostatnieDane || null),
    eksport: ostatniEksport || null,
    work_mode: aktywnyTrybPracy || 'analiza',
    preview_mode: aktywnyWidokPodgladu || 'wszystko',
    interface_mode: (typeof trybInterfejsu !== 'undefined' ? trybInterfejsu : 'uzytkownik'),
    production_view: (typeof aktywnyWidokProdukcyjny !== 'undefined' ? aktywnyWidokProdukcyjny : 'wynik'),
    result_label: (typeof aktywnyOpisWyniku !== 'undefined' ? aktywnyOpisWyniku : ''),
    user_view: (typeof ostatniWidokUzytkownika !== 'undefined' ? ostatniWidokUzytkownika : 'start'),
    expert_view: (typeof ostatniWidokEksperta !== 'undefined' ? ostatniWidokEksperta : 'p0'),
    database_ui: {
      compare_mode: $('databaseCompareMode')?.value || 'folder',
      compare_groups: (typeof wybraneGrupyPorownania === 'function' ? wybraneGrupyPorownania() : []),
      same_story_topic: $('sameStoryTopic')?.value || '',
      same_story_groups: (typeof wybraneGrupyTejSamejSprawy === 'function' ? wybraneGrupyTejSamejSprawy() : []),
      database_compare_had_result: !!ostatniePorownanieBazy,
      same_story_had_result: !!ostatniePorownanieTejSamejSprawy,
      database_panel_open: !!$('databasePanel')?.open,
      database_compare_panel_open: !!$('databaseComparePanel')?.open,
      same_story_panel_open: !!$('sameStoryComparePanel')?.open
    }
  };
}

async function zapiszSesjeTeraz(powod='autosave'){
  if(sesjaWTrakciePrzywracania) return false;
  try{
    const snap = snapshotBiezacejSesji();
    const dbState=snap.database_ui||{};
    const maStanBazy=!!(dbState.database_panel_open || dbState.database_compare_panel_open || dbState.same_story_panel_open || (dbState.compare_groups||[]).length || dbState.same_story_topic || (dbState.same_story_groups||[]).length || dbState.database_compare_had_result || dbState.same_story_had_result);
    if(!snap.tekst.trim() && !snap.wynik && !maStanBazy){
      await usunSnapshotSesji();
      return true;
    }
    await zapiszSnapshotSesji(snap);
    const when = new Date(snap.saved_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    ustawStatusSesji(`Autosave lokalny: zapisano ${when}`, 'saved');
    return true;
  }catch(err){
    ustawStatusSesji(`Autosave nieudany: ${err.message || err}`, 'error');
    console.warn('Drogowskazy session autosave error', powod, err);
    return false;
  }
}

function zaplanujZapisSesji(opoznienie=450){
  if(sesjaWTrakciePrzywracania) return;
  clearTimeout(timerZapisuSesji);
  timerZapisuSesji = setTimeout(() => { void zapiszSesjeTeraz('debounce'); }, opoznienie);
  ustawStatusSesji('Autosave lokalny: oczekuje na zapis…', 'pending');
}

async function przywrocSesjeLokalna(){
  try{
    const snap = await odczytajSnapshotSesji();
    const dbState=snap?.database_ui||{};
    const maStanBazy=!!(dbState.database_panel_open || dbState.database_compare_panel_open || dbState.same_story_panel_open || (dbState.compare_groups||[]).length || dbState.same_story_topic || (dbState.same_story_groups||[]).length || dbState.database_compare_had_result || dbState.same_story_had_result);
    if(!snap || (!String(snap.tekst || '').trim() && !snap.wynik && !maStanBazy)){
      ustawStatusSesji('Autosave lokalny: brak zapisanej sesji.', 'empty');
      return false;
    }
    sesjaWTrakciePrzywracania = true;
    const pole = $('textInput');
    if(pole) pole.value = String(snap.tekst || '');
    aktywnyTrybPracy = snap.work_mode || 'analiza';
    aktywnyWidokPodgladu = snap.preview_mode || 'wszystko';
    oczekujacyStanBazySesji = (snap.database_ui && typeof snap.database_ui === 'object') ? snap.database_ui : null;
    if(oczekujacyStanBazySesji?.compare_mode && $('databaseCompareMode')) $('databaseCompareMode').value=oczekujacyStanBazySesji.compare_mode;
    if($('databasePanel') && oczekujacyStanBazySesji) $('databasePanel').open=!!oczekujacyStanBazySesji.database_panel_open;
    if($('databaseComparePanel') && oczekujacyStanBazySesji) $('databaseComparePanel').open=!!oczekujacyStanBazySesji.database_compare_panel_open;
    if($('sameStoryComparePanel') && oczekujacyStanBazySesji) $('sameStoryComparePanel').open=!!oczekujacyStanBazySesji.same_story_panel_open;
    if(pole){
      const names = nazwyDokumentowZPola(pole);
      ustawPodsumowanieZrodel(names, pole.value.length, false);
    }
    if(snap.wynik && snap.wynik.aggregate_from_database){
      ostatniZbiorczyPayload = snap.wynik;
      zbiorczeDokumentyMap = snap.wynik.zbiorcze_dokumenty || {};
      snap.wynik = materializujZbiorczyWynik(snap.wynik);
    }
    if(snap.wynik) renderuj(snap.wynik);
    // Nowa analiza unieważnia poprzedni eksport.
    // Przy odtwarzaniu snapshotu wynik i eksport są jednak z tej samej zapisanej sesji.
    ostatniEksport = snap.eksport || null;
    if(typeof zastosujTrybInterfejsu === 'function') zastosujTrybInterfejsu(snap.interface_mode || 'uzytkownik',{restoreView:false});
    if(snap.wynik && snap.interface_mode === 'ekspert' && typeof pokazWidok === 'function') pokazWidok(snap.expert_view || 'p0');
    if(snap.wynik && snap.interface_mode !== 'ekspert' && typeof pokazWidokProdukcyjny6 === 'function') pokazWidokProdukcyjny6(snap.production_view || 'wynik');
    if(snap.wynik && typeof renderujPodgladTekstu === 'function') renderujPodgladTekstu(snap.wynik, aktywnyWidokPodgladu || 'wszystko');
    if(snap.wynik && typeof ustawStatusAktywnegoWyniku === 'function') ustawStatusAktywnegoWyniku(snap.result_label || 'przywrócony wynik', true);
    const when = snap.saved_at ? new Date(snap.saved_at).toLocaleString() : 'wcześniej';
    ustawStatusSesji(`Przywrócono ostatnią sesję (${when}).`, 'restored');
    return true;
  }catch(err){
    ustawStatusSesji(`Nie udało się przywrócić sesji: ${err.message || err}`, 'error');
    console.warn('Drogowskazy session restore error', err);
    return false;
  }finally{
    sesjaWTrakciePrzywracania = false;
  }
}

function przyciskiOperacji(){
  return ['loadFileBtn','appendFileBtn','appendManyFilesBtn','appendAllFilesBtn','importFilesToDatabaseBtn','importFolderToDatabaseBtn','restoreDatabaseBackupBtn','aggregateDatabaseBtn','reanalyzeDatabaseBtn','analyzeBtn','suggestBtn','reportBtn']
    .map(id => $(id)).filter(Boolean);
}

function ustawZajetoscOperacji(zajety){
  przyciskiOperacji().forEach(btn => {
    btn.disabled = !!zajety;
    btn.classList.toggle('operation-busy', !!zajety);
    if(zajety) btn.setAttribute('aria-busy','true'); else btn.removeAttribute('aria-busy');
  });
}

function pokazPostepOperacji(etykieta, {wartosc=null, szczegol='', zajety=true}={}){
  // Odświeżenie tematów w tle nie może zwolnić blokady trwającej analizy/importu.
  if(!zajety && (importBazyAktywny || przyciskiOperacji().some(btn=>btn.classList.contains('operation-busy')))) return 0;
  const box = $('operationProgress'), bar = $('operationProgressBar');
  const label = $('operationProgressLabel'), value = $('operationProgressValue'), detail = $('operationProgressDetail');
  if(!box || !bar) return 0;
  clearTimeout(timerUkryciaPostepu);
  aktywnaOperacjaPostepu += 1;
  const token = aktywnaOperacjaPostepu;
  box.hidden = false;
  box.classList.remove('is-error','is-done');
  if(label) label.textContent = etykieta || 'Praca w toku';
  if(detail) detail.textContent = szczegol || '';
  if(wartosc === null || wartosc === undefined){
    bar.removeAttribute('value'); // indeterminate: nie udajemy procentu backendu
    if(value) value.textContent = 'trwa…';
  }else{
    const pct = Math.max(0, Math.min(100, Number(wartosc) || 0));
    bar.value = pct;
    if(value) value.textContent = `${Math.round(pct)}%`;
  }
  if(zajety) ustawZajetoscOperacji(true);
  return token;
}

function aktualizujPostepOperacji(token, {etykieta=null, wartosc=undefined, szczegol=null, tekstWartosci=null}={}){
  if(token !== aktywnaOperacjaPostepu) return;
  const bar = $('operationProgressBar'), label = $('operationProgressLabel');
  const value = $('operationProgressValue'), detail = $('operationProgressDetail');
  if(etykieta !== null && label) label.textContent = etykieta;
  if(szczegol !== null && detail) detail.textContent = szczegol;
  if(wartosc !== undefined && bar){
    if(wartosc === null){ bar.removeAttribute('value'); if(value) value.textContent = tekstWartosci || 'trwa…'; }
    else { const pct=Math.max(0,Math.min(100,Number(wartosc)||0)); bar.value=pct; if(value) value.textContent=tekstWartosci || `${Math.round(pct)}%`; }
  }else if(tekstWartosci !== null && value) value.textContent = tekstWartosci;
}

function zakonczPostepOperacji(token, etykieta='Gotowe', szczegol=''){
  if(token !== aktywnaOperacjaPostepu) return;
  clearInterval(timerPostepuOperacji); timerPostepuOperacji=null;
  const box=$('operationProgress'), bar=$('operationProgressBar');
  if(box) box.classList.add('is-done');
  if(bar) bar.value=100;
  const label=$('operationProgressLabel'), value=$('operationProgressValue'), detail=$('operationProgressDetail');
  if(label) label.textContent=etykieta;
  if(value) value.textContent='100%';
  if(detail) detail.textContent=szczegol || 'Operacja zakończona.';
  ustawZajetoscOperacji(false);
  timerUkryciaPostepu=setTimeout(()=>{ if(token===aktywnaOperacjaPostepu && box) box.hidden=true; }, 2200);
}

function bladPostepuOperacji(token, etykieta='Błąd', szczegol=''){
  if(token !== aktywnaOperacjaPostepu) return;
  clearInterval(timerPostepuOperacji); timerPostepuOperacji=null;
  const box=$('operationProgress'), bar=$('operationProgressBar');
  if(box){ box.hidden=false; box.classList.add('is-error'); box.classList.remove('is-done'); }
  if(bar) bar.removeAttribute('value');
  const label=$('operationProgressLabel'), value=$('operationProgressValue'), detail=$('operationProgressDetail');
  if(label) label.textContent=etykieta;
  if(value) value.textContent='błąd';
  if(detail) detail.textContent=szczegol || 'Operacja nie została wykonana.';
  ustawZajetoscOperacji(false);
}

function startPostepuSerwera(etykieta, tekst){
  const docs = Math.max(1, nazwyDokumentowZPola($('textInput')).length || (tekst.trim() ? 1 : 0));
  const bytes = bajtyUtf8(tekst || '');
  const token = pokazPostepOperacji(etykieta, {wartosc:null, szczegol:`${docs} ${odmienPliki(docs)} · ${Math.round(bytes/1024)} KB · serwer przetwarza materiał`});
  const start = Date.now();
  clearInterval(timerPostepuOperacji);
  timerPostepuOperacji=setInterval(()=>{
    const sekundy=Math.max(0, Math.floor((Date.now()-start)/1000));
    aktualizujPostepOperacji(token,{tekstWartosci:`${sekundy}s`, szczegol:`${docs} ${odmienPliki(docs)} · ${Math.round(bytes/1024)} KB · analiza po stronie serwera`});
  },1000);
  return token;
}


function ustawTrybPracy(tryb){
  aktywnyTrybPracy = String(tryb || 'analiza');
  const lista = Array.isArray(trybyPracy?.tryby) ? trybyPracy.tryby : [];
  const opis = lista.find(x => x.id === aktywnyTrybPracy);
  if(!opis) return;
  const nameEl = $('activeModeName');
  const descEl = $('activeModeDescription');
  if(nameEl) nameEl.textContent = opis.nazwa || aktywnyTrybPracy;
  if(descEl) descEl.textContent = opis.opis || '';
  document.querySelectorAll('[data-work-mode]').forEach(b => b.classList.toggle('active-mode', b.dataset.workMode === aktywnyTrybPracy));
  renderujKartyTrybow();
}

function renderujKartyTrybow(){
  const box = $('modeCards');
  if(!box) return;
  const lista = Array.isArray(trybyPracy?.tryby) ? trybyPracy.tryby : [];
  box.innerHTML = lista.map(t => `<div class="mode-card ${t.id === aktywnyTrybPracy ? 'active' : ''}"><strong>${esc(t.nazwa)}</strong><small>${esc(t.opis)}</small><ul>${(t.nie_robi || []).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`).join('');
}

function ustawStanBackend(ok, opis='') {
  const pill = $('backendStatusPill');
  const text = $('backendStatusText');
  if(pill){
    pill.classList.remove('backend-checking','backend-ok','backend-offline');
    pill.classList.add(ok === true ? 'backend-ok' : ok === false ? 'backend-offline' : 'backend-checking');
  }
  if(text) text.textContent = ok === true ? 'backend: działa' : ok === false ? 'backend: brak połączenia' : 'backend: sprawdzam…';
  if(pill && opis) pill.title = opis;
}

function opisPolaczeniaBackend(err){
  const proto = String(window.location.protocol || '');
  const origin = proto === 'http:' || proto === 'https:' ? window.location.origin : '';
  if(proto === 'file:'){
    return 'Interfejs został otwarty poza aplikacją. Wróć do Drogowskazy Sora i użyj przycisku otwierającego aplikację po uruchomieniu serwera.';
  }
  if(origin){
    return `Backend nie odpowiada pod ${origin}. Wróć do Drogowskazy Sora, uruchom serwer i ponownie otwórz aplikację.`;
  }
  return 'Backend nie odpowiada. Wróć do Drogowskazy Sora, uruchom serwer i ponownie otwórz aplikację.';
}

async function pobierzJson(url, options={}, kontekst='Żądanie HTTP'){
  let res;
  try{
    res = await fetch(url, options);
  }catch(err){
    ustawStanBackend(false, opisPolaczeniaBackend(err));
    throw new Error(`${kontekst}: brak połączenia z backendem. ${opisPolaczeniaBackend(err)}`);
  }

  let data = null;
  let raw = '';
  const contentType = String(res.headers.get('content-type') || '').toLowerCase();
  try{
    if(contentType.includes('application/json')) data = await res.json();
    else raw = await res.text();
  }catch(_err){
    // Poniżej powstanie jeden spójny komunikat kontraktu HTTP.
  }

  if(!res.ok){
    const apiMsg = data && (data.wiadomosc || data.szczegoly || data.blad || data.error || data.message);
    const tail = apiMsg || (raw ? raw.slice(0, 160) : `HTTP ${res.status}`);
    throw new Error(`${kontekst}: ${tail}`);
  }
  if(!data || typeof data !== 'object')
    throw new Error(`${kontekst}: serwer nie zwrócił JSON.`);
  return data;
}

async function sprawdzBackend(){
  ustawStanBackend(null, 'Sprawdzanie /api/health…');
  try{
    const health = await pobierzJson('/api/health', {}, 'Start aplikacji');
    if(health.ok !== true) throw new Error('backend zgłosił stan niegotowy');
    if(health.transport && health.transport !== 'http_json')
      throw new Error(`niezgodny transport: ${health.transport}`);
    if(health.websocket !== false)
      throw new Error('niezgodny kontrakt: aplikacja nie powinna wymagać WebSocket');
    ustawStanBackend(true, `Połączono z ${health.request_origin || window.location.origin || 'backendem'} · ${health.etap || ''}`);
    return true;
  }catch(err){
    const msg = err && err.message ? err.message : opisPolaczeniaBackend(err);
    ustawStanBackend(false, msg);
    const summary = $('summary');
    if(summary) summary.innerHTML = `<div class="file-load-error"><strong>Aplikacja nie połączyła się z backendem.</strong><br>${esc(msg)}<br><strong>Co zrobić:</strong> wróć do aplikacji Drogowskazy Sora, uruchom serwer i ponownie otwórz Drogowskazy.</div>`;
    ustawStatusPliku(`Błąd startu: ${msg}`, true);
    console.error('Drogowskazy runtime health error', err);
    return false;
  }
}

async function zaladujTrybyPracy(){
  trybyPracy = await pobierzJson('/api/tryby', {}, 'Tryby pracy');
  ustawTrybPracy(aktywnyTrybPracy);
}

function kratkaPodsumowania(podsumowanie){
  const dane = podsumowanie || {};
  const opisy = {
    top_najwazniejszych_relacji: ['TOP relacji', 'Najlepiej ocenione, niepowtarzające się relacje z jednego modelu danych.'],
    canonical_relation: ['relacje kanoniczne', 'Zaakceptowane relacje wypowiedzi po walidacji.'],
    potwierdzone_p1: ['potwierdzone P1', 'Potwierdzone struktury językowo-retoryczne.'],
    techniki_p2: ['techniki P2', 'Techniki P2 wykryte przez aktywny klasyfikator.'],
    ramy_p3: ['ramy P3', 'Ramy narracyjne wykryte lokalnie w dokumentach.'],
    strategie_p4: ['strategie P4', 'Strategie tworzone tylko przy wystarczającym wsparciu P2.'],
    diagnozy_p5: ['diagnozy P5', 'Najwyższa warstwa syntetyczna wymagająca wsparcia P2/P4.'],
    kandydaci_struktur: ['kandydaci struktur', 'Struktury pozostawione do przeglądu.'],
    markery_p0: ['markery P0', 'Surowe wskaźniki; same nie są decyzją.'],
    zablokowane_przez_bramki: ['zablokowane', 'Relacje odrzucone przez bramki integralności.'],
    raport_skutecznosci_semantycznej: ['audyt jakości', 'Karta integralności aktywnego pipeline.'],
    dokumenty: ['dokumenty', 'Unikalne dokumenty po deduplikacji wejścia.']
  };
  const keys = ['dokumenty','top_najwazniejszych_relacji','canonical_relation','potwierdzone_p1','techniki_p2','ramy_p3','strategie_p4','diagnozy_p5','kandydaci_struktur','markery_p0','zablokowane_przez_bramki','raport_skutecznosci_semantycznej'];
  const boxes = keys.filter(k => {
    if(!Object.prototype.hasOwnProperty.call(dane,k)) return false;
    const v = Number(dane[k]);
    return Number.isFinite(v) ? v > 0 : Boolean(String(dane[k] ?? '').trim());
  }).map(k => {
    const v=dane[k]; const [nazwa,opis]=opisy[k];
    return `<div class="stat-box" title="${esc(opis)}"><strong>${esc(v)}</strong><span>${esc(nazwa)}</span><small>${esc(opis)}</small></div>`;
  }).join('');
  return `<div class="stats-grid">${boxes}</div><details class="mini stats-help"><summary>Co oznaczają te statystyki?</summary><p>To liczniki faktycznie istniejących sekcji aktualnego wyniku.</p></details>`;
}

function klasaTechniki(nazwa){
  const raw = String(nazwa || '').toLowerCase();
  const mapa = [
    ['kontrast','kontrast'], ['hiperbola','hiperbola'], ['generalizacja','generalizacja'],
    ['pytanie retoryczne','pytanie-retoryczne'], ['retoryczne','pytanie-retoryczne'],
    ['fałszywa dychotomia','falszywa-dychotomia'], ['falszywa dychotomia','falszywa-dychotomia'],
    ['antyteza','antyteza'], ['wyliczenie','wyliczenie'], ['insynuacja','insynuacja'],
    ['rama zagrożenia','rama-zagrozenia'], ['zagrożenia','rama-zagrozenia'], ['bezpieczeństwo','bezpieczenstwo'],
    ['kontrola','kontrola'], ['chaos','chaos']
  ];
  for(const [needle, slug] of mapa){ if(raw.includes(needle)) return slug; }
  return raw.replace(/[^a-z0-9ąćęłńóśźż]+/g,'-').replace(/^-+|-+$/g,'').slice(0,40) || 'inne';
}

function atrybutyTrafienia(k){
  return `data-hit-card="1" data-highlight-id="${esc(k.highlight_id || '')}" data-link-status="${esc(k.link_status || '')}" data-level="${esc(k.poziom || '')}" data-start="${esc(k.poczatek ?? '')}" data-end="${esc(k.koniec ?? '')}" data-phrase="${esc(k.fraza || '')}" data-fragment="${esc(k.fragment || '')}"`;
}

function skrocTekst(txt, limit=220){
  const s = String(txt || '').replace(/\s+/g, ' ').trim();
  if(s.length <= limit) return s;
  return s.slice(0, limit).replace(/\s+\S*$/, '').trim() + '…';
}


/* Interfejs: aktywna implementacja
   Główny widok nie pokazuje pustych kategorii, audytowych kart zerowych
   ani technicznych liczników. Pełne dane są dostępne w eksporcie JSON. */
function czyPustaLubTechnicznaKarta(k){
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.kod_techniczny || ''} ${k?.uzasadnienie || ''} ${k?.fragment || ''} ${k?.fraza || ''}`.toLowerCase();
  const count = Number(k?.liczba ?? k?.count ?? k?.liczba_kandydatow ?? k?.wynik);
  const emptyText = /brak przykładów|brak przykladów|brak przykladow|brak mapy|brak frazy|nie znaleziono dokładnej frazy|nie znaleziono dokladnej frazy|liczba kandydatów w kategorii:\s*0/.test(hay);
  const p04LowZero = /p04\.1|p-04\.1|kategoria/.test(hay) && (/niskie|do odrzucenia/.test(hay) || count === 0) && emptyText;
  const pureAudit = /sekcja audytowa|liczniki grup|raportowa|kontrola techniczna/.test(hay) && emptyText;
  return !!(emptyText || p04LowZero || pureAudit);
}

function filtrujKartyWidoku(lista){
  return (Array.isArray(lista) ? lista : []).filter(k => !czyPustaLubTechnicznaKarta(k));
}

function htmlJesliSa(lista, renderer, empty=''){
  const clean = filtrujKartyWidoku(lista);
  return clean.length ? renderer(clean) : empty;
}

function entityKeyZKarty(k){
  const direct = k?.aktor || k?.nazwa_aktora || k?.osoba || k?.medium || k?.zrodlo || k?.źródło || k?.kto_mowi || k?.relacja_wypowiedzi?.kto_mowi || k?.fraza || '';
  const clean = normalizujDoKluczaR(direct);
  if(!clean || clean.length < 2) return '';
  if(/^(aktor nazwany|zrodlo|źrodlo|medium|nieustalony|dzialanie wypowiedz aktora|działanie wypowiedź aktora)$/.test(clean)) return '';
  return clean.slice(0, 80);
}

function metaClaimChunks(k){
  const bits = [];
  if(k.typ_twierdzenia) bits.push(`<strong>${esc(k.typ_twierdzenia)}</strong>`);
  if(k.kto_mowi) bits.push(`kto mówi: ${esc(k.kto_mowi)}`);
  if(k.marker_atrybucji) bits.push(`marker: ${esc(k.marker_atrybucji)}`);
  if(k.o_kim) bits.push(`target: ${esc(k.o_kim)}`);
  if(k.temat) bits.push(`temat: ${esc(k.temat)}`);
  if(k.obiekt) bits.push(`obiekt: ${esc(k.obiekt)}`);
  if(k.zrodlo_przywolane) bits.push(`źródło przywołane: ${esc(k.zrodlo_przywolane)}`);
  if(k.zrodlo_dokumentu) bits.push(`źródło dokumentu: ${esc(k.zrodlo_dokumentu)}`);
  if(Array.isArray(k.zrodla_zdjec) && k.zrodla_zdjec.length) bits.push(`źródło zdjęcia: ${esc(k.zrodla_zdjec.join(', '))}`);
  if(k.medium) bits.push(`medium: ${esc(k.medium)}`);
  if(k.program) bits.push(`program: ${esc(k.program)}`);
  return bits.join(' · ');
}


function publicznaNazwa(value){
  let out = String(value || '');
  out = out.replace(/\bR[0-3]\b/gi, '');
  out = out.replace(/\bcanonical entity\b/gi, '');
  out = out.replace(/[_\s]+/g, ' ').trim();
  return out;
}

function ustawSekcje(id, html, hasData=true){
  const el = $(id);
  if(!el) return;
  const shell = el.closest('details') || el.parentElement;
  if(!hasData){
    el.innerHTML = '';
    if(shell) shell.hidden = true;
    return;
  }
  if(shell) shell.hidden = false;
  el.innerHTML = html;
}

function karta(k, opts={}){
  const showTechnical = !!opts.showTechnical;
  const compact = !!opts.compact;
  const przyklady = Array.isArray(k.przyklady) && k.przyklady.length
    ? `<details class="mini"><summary>Przykłady · ${k.przyklady.length}</summary>${k.przyklady.map(p => karta(p, opts)).join('')}</details>` : '';
  const grupy = k.liczniki_grup ? `<details class="mini"><summary>Liczniki grup</summary>${Object.entries(k.liczniki_grup).map(([a,b])=>`<div class="p0row"><strong>${esc(a)}</strong><span>${esc(b)}</span></div>`).join('')}</details>` : '';
  const levelRaw = String(k.poziom || '').toUpperCase();
  const cls = ['P0','P1','P2','P3','P4','P5','R0','R1','R2','R3'].includes(levelRaw) ? levelRaw : 'CAND';
  const techCls = `tech-${klasaTechniki(k.tytul || k.fraza || '')}`;
  const maZakres = k.link_status === 'linked' && Number(k.poczatek) >= 0 && Number(k.koniec) > Number(k.poczatek);
  const roleR = Array.isArray(k.role_r_kontekst) && k.role_r_kontekst.length
    ? `<div class="r-context"><strong>R jako metadane:</strong> ${k.role_r_kontekst.map(r => `${esc(r.level || '')} ${esc(r.label || '')}`).join(' · ')}</div>`
    : (k.notatka_o_roli_r ? `<div class="r-context">${esc(k.notatka_o_roli_r)}</div>` : '');
  const claimMeta = metaClaimChunks(k);
  const claimInfo = claimMeta ? `<div class="claim-type">${claimMeta}</div>` : "";
  const relationInfo = k.relacja_wypowiedzi && Object.keys(k.relacja_wypowiedzi).length
    ? `<div class="statement-relation compact-relation"><strong>Kto mówi → co mówi</strong><div class="relation-grid">${k.relacja_wypowiedzi.kto_mowi ? `<span>Kto mówi</span><b>${esc(k.relacja_wypowiedzi.kto_mowi)}</b>` : ''}${k.relacja_wypowiedzi.attribution_marker ? `<span>Marker atrybucji</span><b>${esc(k.relacja_wypowiedzi.attribution_marker)}</b>` : ''}${k.relacja_wypowiedzi.o_kim ? `<span>Target</span><b>${esc(k.relacja_wypowiedzi.o_kim)}</b>` : ''}${k.relacja_wypowiedzi.topic ? `<span>Temat</span><b>${esc(k.relacja_wypowiedzi.topic)}</b>` : ''}${k.relacja_wypowiedzi.object ? `<span>Obiekt</span><b>${esc(k.relacja_wypowiedzi.object)}</b>` : ''}${k.relacja_wypowiedzi.co_mowi ? `<span>Co mówi</span><b>${esc(skrocTekst(k.relacja_wypowiedzi.co_mowi, 120))}</b>` : ''}${k.relacja_wypowiedzi.zrodlo ? `<span>Źródło przywołane</span><b>${esc(k.relacja_wypowiedzi.zrodlo)}</b>` : ''}${k.relacja_wypowiedzi.zrodlo_dokumentu ? `<span>Źródło dokumentu</span><b>${esc(k.relacja_wypowiedzi.zrodlo_dokumentu)}</b>` : ''}${Array.isArray(k.relacja_wypowiedzi.zrodla_zdjec) && k.relacja_wypowiedzi.zrodla_zdjec.length ? `<span>Źródło zdjęcia</span><b>${esc(k.relacja_wypowiedzi.zrodla_zdjec.join(', '))}</b>` : ''}${k.relacja_wypowiedzi.medium ? `<span>Medium</span><b>${esc(k.relacja_wypowiedzi.medium)}</b>` : ''}${k.relacja_wypowiedzi.program ? `<span>Program</span><b>${esc(k.relacja_wypowiedzi.program)}</b>` : ''}</div></div>`
    : '';
  const entityList = Array.isArray(k.lista_elementow) && k.lista_elementow.length
    ? `<details class="mini entity-list"><summary>Lista · ${k.lista_elementow.length}</summary><ol>${k.lista_elementow.map(x => `<li>${esc(x)}</li>`).join('')}</ol></details>`
    : '';
  const linkInfo = maZakres
    ? '<div class="link-status linked">Połączono z fragmentem tekstu.</div>'
    : (k.brak_podswietlenia_powod ? `<div class="link-status missing">Brak przycisku: ${esc(k.brak_podswietlenia_powod)}</div>` : '');
  const aggregateDocIds = Array.isArray(k.dokumenty_bazy_ids) ? k.dokumenty_bazy_ids : [];
  const aggregateDocNames = aggregateDocIds.slice(0, 3).map(id => {
    const doc = zbiorczeDokumentyMap[String(id)] || {};
    return doc.relative_path || doc.filename || `#${id}`;
  });
  const aggregateDocInfo = aggregateDocIds.length
    ? `<div class="meta database-card-origin">baza: ${esc(aggregateDocNames.join(' · '))}${aggregateDocIds.length > 3 ? ` · +${aggregateDocIds.length - 3} dokumentów` : ''}</div>`
    : '';
  const technical = showTechnical ? `<details class="mini"><summary>Dane techniczne</summary><div class="meta">kod: <code>${esc(k.kod_techniczny || '')}</code><br>rola techniczna: <code>${esc(k.rola_techniczna || '')}</code></div></details>` : '';
  const fragmentText = (k.tytul === 'Mini-mapa sprawczości') ? skrocTekst(k.fragment, compact ? 120 : 180) : (compact ? skrocTekst(k.fragment, 160) : k.fragment);
  const reasoningText = compact ? skrocTekst(k.uzasadnienie, 180) : k.uzasadnienie;
  return `<div class="card ${cls} ${techCls}" ${atrybutyTrafienia(k)}>
    <div class="title"><strong>${esc(publicznaNazwa(k.tytul) || 'Karta')}</strong>${k.poziom?`<span class="badge">${esc(k.poziom)}</span>`:''}<span class="role">${esc(publicznaNazwa(k.rola))}</span></div>
    ${k.fraza ? `<div class="meta">fraza: <code>${esc(skrocTekst(k.fraza, compact ? 90 : 160))}</code></div>` : ''}
    ${fragmentText ? `<div class="fragment">${esc(fragmentText)}</div>` : ''}
    ${k.dzialanie ? `<div class="why lead">${esc(compact ? skrocTekst(k.dzialanie, 160) : k.dzialanie)}</div>` : ''}
    ${reasoningText ? `<div class="why">${esc(reasoningText)}</div>` : ''}
    ${roleR}
    ${claimInfo}
    ${relationInfo}
    ${aggregateDocInfo}
    ${entityList}
    ${showTechnical ? `<div class="meta">pewność wzorca: ${esc(k.pewnosc_wzorca || k.pewnosc || '')} · interpretacja: ${esc(k.pewnosc_interpretacji || k.pewnosc || '')} · wynik: ${esc(k.wynik ?? '')}${k.wymaga_przegladu ? ' · wymaga przeglądu' : ''}</div>` : ''}
    ${linkInfo}
    ${maZakres ? `<button type="button" class="show-hit-btn" ${atrybutyTrafienia(k)}>Pokaż w tekście</button>` : ''}
    ${technical}
    ${przyklady}${grupy}
  </div>`;
}

function czyKartaAktorZrodlo(k){
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.poziom || ''} ${k?.kod_techniczny || ''} ${k?.typ_twierdzenia || ''}`.toLowerCase();
  if(/opinia cytowana|fakt opisowy|mikrodiagnoza|mini-mapa|raport|checklista|ranking|ryzyka/.test(hay)) return false;
  return /aktor nazwany|aktorzy|źródło\/medium|zrodlo_medium|source|medium/.test(hay);
}


function typGlobalnejGrupy(k){
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.kod_techniczny || ''} ${k?.typ_twierdzenia || ''} ${k?.poziom || ''} ${k?.fraza || ''}`.toLowerCase();
  if(czyKartaAktorZrodlo(k)) return 'Aktorzy / źródła';
  if(/opinia cytowana|opinia przypisana|fakt\/opinia|fakt opisowy|cytat|status twierd|źródło\/medium|zrodlo_medium/.test(hay)) return 'Fakt / opinia / cytat';
  if(/relacja wypowiedzi|kto mówi|kto mowi|o kim|co mówi|co mowi/.test(hay) || (k?.relacja_wypowiedzi && Object.keys(k.relacja_wypowiedzi).length)) return 'Relacje wypowiedzi';
  if(/sprawczo|odpowiedzial|kto robi|wykonuje|decyduje/.test(hay)) return 'Sprawczość';
  if(/p3|rama|ramy narracyjne|ramowanie/.test(hay)) return 'Ramy P3';
  if(/p2|hipotez/.test(hay)) return 'Hipotezy P2';
  if(/p1|generalizacja|kontrast|dychotom|hiperbol|antytez|wyliczenie/.test(hay)) return 'Struktury P1';
  if(/p0|wskaźnik|wskaznik|marker/.test(hay)) return 'Wskaźniki P0';
  if(/p4|strateg/.test(hay)) return 'Strategie P4';
  if(/p5|diagnoz/.test(hay)) return 'Diagnozy P5';
  if(/check|sprawdzenia|audyt|raport|jakość|jakosc/.test(hay)) return 'Kontrola / raport';
  return 'Inne wyniki';
}

function grupujGlobalnieKarty(lista){
  const buckets = {};
  (Array.isArray(lista) ? lista : []).forEach(k => {
    const typ = typGlobalnejGrupy(k);
    (buckets[typ] ||= []).push(k);
  });
  const order = [
    'Fakt / opinia / cytat',
    'Relacje wypowiedzi',
    'Aktorzy / źródła',
    'Sprawczość',
    'Ramy P3',
    'Hipotezy P2',
    'Struktury P1',
    'Wskaźniki P0',
    'Strategie P4',
    'Diagnozy P5',
    'Kontrola / raport',
    'Inne wyniki'
  ];
  return order.filter(n => buckets[n]?.length).map(n => [n, buckets[n]]);
}

function opisGlobalnejGrupy(name){
  return {
    'Fakt / opinia / cytat': 'Status twierdzeń, cytatów, opinii i źródeł wypowiedzi.',
    'Relacje wypowiedzi': 'Kto mówi, o kim mówi i co mówi.',
    'Aktorzy / źródła': 'Aktorzy, instytucje, media, agencje i autorzy.',
    'Sprawczość': 'Kto działa, kto unika, kto odpowiada i kto wykonuje czynność.',
    'Ramy P3': 'Najwyższe ramy narracyjne wykryte w tekście.',
    'Hipotezy P2': 'Hipotezy narracyjne i techniki pośrednie.',
    'Struktury P1': 'Potwierdzone albo kandydackie struktury P1.',
    'Wskaźniki P0': 'Surowe markery językowe bez awansu do wyższej warstwy.',
    'Strategie P4': 'Strategie dyskursywne.',
    'Diagnozy P5': 'Diagnozy syntetyczne i wnioski wysokiego poziomu.',
    'Kontrola / raport': 'Checklisty, audyty i raporty jakości.',
    'Inne wyniki': 'Pozostałe wyniki analizy.'
  }[name] || 'Grupa wyników analizy.';
}

function renderGlobalGroupSummary(name, arr){
  const top = (arr || []).slice(0, 4).map((k) => {
    const title = semCardTitle(k);
    const summary = semCardSummary(k, 115);
    return `<li><strong>${esc(title)}</strong><div class="mini-subline">${esc(summary)}</div></li>`;
  }).join('');
  return top || `<li><span class="mini-subline">Brak skrótu.</span></li>`;
}


function relacjaSprawczosciZKarty(k){
  return {
    kto: String(k?.aktor || k?.kto_mowi || '').trim(),
    robi: String(k?.dzialanie || k?.czynność || k?.czynnosc || '').trim(),
    co: String(k?.obiekt || k?.claim || k?.fraza || '').trim(),
    card: k
  };
}

function renderAgencyRelationCompact(r, i, prefix){
  const cardId = inlineDetailId(prefix || 'agency_relation', `fragmenty_${i}`, i);
  const cardHtml = karta(r.card, {compact:true, noAutoGroup:true, showTechnical:false});
  const linked = r.card?.link_status === 'linked' || (Number(r.card?.poczatek) >= 0 && Number(r.card?.koniec) > Number(r.card?.poczatek));
  return `<div class="agency-relation-row compact-detail-row">
    <div class="agency-relation-main"><strong>${esc(r.kto)}</strong> → ${esc(r.robi)} → <span>${esc(r.co)}</span></div>
    <div class="mini-subline">${linked ? 'Połączone z fragmentem tekstu.' : 'Relacja bez pewnego zakresu w tekście.'}</div>
    ${detailButton('Pokaż powiązany fragment', cardId)}
    ${inlineDetailBox(cardId, `<div class="second-level-detail">${cardHtml}</div>`)}
  </div>`;
}

function renderCollapsedAgencyMap(cards, opts={}){
  const list = Array.isArray(cards) ? cards : [];
  if(!list.length) return ''; // Aktywna implementacja
  const rels = list.map(relacjaSprawczosciZKarty).filter(r => r.kto && r.robi && r.co);
  if(!rels.length) return '';
  const id = inlineDetailId(opts.prefix || 'agency_map', 'lista_relacji_sprawczosci', 0);
  const top = rels.slice(0, 6).map((r, i) => `<li><strong>${esc(r.kto)}</strong> → ${esc(r.robi)} → <span>${esc(r.co)}</span></li>`).join('');
  const compactDetails = rels.slice(0, 12).map((r, i) => renderAgencyRelationCompact(r, i, `${opts.prefix || 'agency_map'}_rel`)).join('');
  const more = list.length > 12 ? `<div class="hint-box">Pokazano 12 relacji z ${list.length}. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
  return `<div class="card R2 grouped-card top-level-group agency-map-collapsed-card compact-details-mode">
    <div class="title"><strong>${esc(opts.title || 'Mapa sprawczości')}</strong><span class="badge">${list.length}</span><span class="role">relacje kto → robi → co</span></div>
    <div class="why">Widok szczegółów: najpierw pokazuje krótką listę relacji. Mini-karty i fragmenty są dopiero po drugim kliknięciu.</div>
    <ol class="summary-list agency-summary-list">${top}</ol>
    ${detailButton('Pokaż listę relacji', id)}
    ${inlineDetailBox(id, `<div class="agency-detail-list compact-relation-list">${compactDetails}${more}</div>`)}
  </div>`;
}

function podtypP0(k){
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.kod_techniczny || ''} ${k?.fraza || ''} ${k?.uzasadnienie || ''}`.toLowerCase();
  if(/aktor|źródło|zrodlo|medium/.test(hay)) return 'aktorzy / źródła';
  if(/sprawczo|odpowiedzial|bierni/.test(hay)) return 'sprawczość / bierni aktorzy';
  if(/check|sprawd/.test(hay)) return 'check / kontrola';
  if(/kontrast|generalizacja|marker|wskaźnik|wskaznik/.test(hay)) return 'markery językowe';
  return 'inne P0';
}

function renderCollapsedP0Cards(cards, opts={}){
  const list = Array.isArray(cards) ? cards : [];
  if(!list.length) return ''; // Aktywna implementacja
  const buckets = {};
  list.forEach(k => (buckets[podtypP0(k)] ||= []).push(k));
  const id = inlineDetailId(opts.prefix || 'p0_group', 'pelne_p0', 0);
  const rows = Object.entries(buckets).sort((a,b)=>b[1].length-a[1].length).map(([name, arr]) =>
    `<div class="p0row"><strong>${esc(name)}</strong><span>${arr.length}</span></div>`
  ).join('');
  const details = Object.entries(buckets).map(([name, arr]) => {
    const cardsHtml = arr.slice(0, 8).map(k => karta(k, {compact:true, noAutoGroup:true})).join('');
    const more = arr.length > 8 ? `<div class="mini-subline">Pokazano 8 z ${arr.length}. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
    return `<div class="p0-subgroup"><h4>${esc(name)} <span class="pill-count">${arr.length}</span></h4>${cardsHtml}${more}</div>`;
  }).join('');
  return `<div class="card P0 grouped-card top-level-group p0-collapsed-card">
    <div class="title"><strong>${esc(opts.title || 'Wskaźniki P0')}</strong><span class="badge">${list.length}</span><span class="role">surowe, zwinięte</span></div>
    <div class="why">P0 jest techniczne: pokazuje liczniki i podgrupy, a szczegóły dopiero po rozwinięciu.</div>
    <div class="p0box">${rows}</div>
    ${detailButton('Wyświetl szczegóły P0 w tym poziomie', id)}
    ${inlineDetailBox(id, details)}
  </div>`;
}

function renderCollapsedCheckCards(cards, opts={}){
  const list = Array.isArray(cards) ? cards : [];
  if(!list.length) return ''; // Aktywna implementacja
  const id = inlineDetailId(opts.prefix || 'check_group', 'pelna_checklista', 0);
  const top = list.slice(0, 7).map((k, i) => `<li><strong>${esc(semCardTitle(k))}</strong><div class="mini-subline">${esc(semCardSummary(k, 125))}</div></li>`).join('');
  const details = list.slice(0, 12).map(k => karta(k, {compact:true, noAutoGroup:true})).join('');
  const more = list.length > 12 ? `<div class="hint-box">Pokazano 12 z ${list.length}. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
  return `<div class="card P4 grouped-card top-level-group check-collapsed-card">
    <div class="title"><strong>${esc(opts.title || 'Checklista / kontrola')}</strong><span class="badge">${list.length}</span><span class="role">zwinięte</span></div>
    <div class="why">Checklisty i audyty są pokazane zbiorczo, żeby nie powtarzać podobnych kart.</div>
    <ol class="summary-list">${top}</ol>
    ${detailButton('Wyświetl checklistę w tym poziomie', id)}
    ${inlineDetailBox(id, `<div class="check-detail-list">${details}${more}</div>`)}
  </div>`;
}

function renderGlobalGroupDetails(name, arr, prefix){
  const list = Array.isArray(arr) ? arr : [];
  if(name === 'Aktorzy / źródła') return renderListaRPoDedupe(list, {level:'R1/R2', limit:30, empty:'Brak aktorów lub źródeł.'});
  if(name === 'Fakt / opinia / cytat') return renderListaRPoDedupe(list, {level:'R2/R3', limit:30, empty:'Brak statusów twierdzeń.'});
  if(name === 'Relacje wypowiedzi') return renderListaRPoDedupe(list, {level:'R3', limit:30, empty:'Brak relacji wypowiedzi.'});
  if(name === 'Sprawczość') return renderListaRPoDedupe(list, {level:'R3', limit:30, empty:'Brak sprawczości.'});
  if(name === 'Wskaźniki P0') return renderCollapsedP0Cards(list, {title:name, prefix});
  if(name === 'Kontrola / raport') return renderCollapsedCheckCards(list, {title:name, prefix});
  const visible = list.slice(0, 10).map(k => karta(k, {compact:true, noAutoGroup:true})).join('');
  const more = list.length > 10 ? `<div class="hint-box">Pokazano 10 z ${list.length}. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
  return `<div class="global-group-detail-list">${visible}${more}</div>`;
}

function renderGlobalGroupedCards(lista, pusty='Brak.', opts={}){
  const cleanList = filtrujKartyWidoku(lista);
  if(!cleanList.length) return '';
  const groups = grupujGlobalnieKarty(cleanList);
  if(groups.length === 1){
    const [name, arr] = groups[0];
    if(name === 'Aktorzy / źródła') return renderCollapsedActorMap(arr, [], {title:name, prefix:'global_actor_only'});
    if(name === 'Fakt / opinia / cytat') return `<div class="card P2 grouped-card top-level-group global-card-group"><div class="title"><strong>${esc(name)}</strong><span class="badge">${arr.length}</span><span class="role">grupa automatyczna</span></div><div class="why">${esc(opisGlobalnejGrupy(name))}</div>${renderGroupedClaimSection(arr)}</div>`;
    if(name === 'Sprawczość') return renderCollapsedAgencyMap(arr, {title:name, prefix:'global_agency_only'});
    if(name === 'Wskaźniki P0') return renderCollapsedP0Cards(arr, {title:name, prefix:'global_p0_only'});
    if(name === 'Kontrola / raport') return renderCollapsedCheckCards(arr, {title:name, prefix:'global_check_only'});
  }
  const rows = groups.map(([name, arr], i) => {
    const id = inlineDetailId('global_group', name, i);
    const details = renderGlobalGroupDetails(name, arr, `global_${i}_${name}`);
    return `<div class="global-group-row">
      <div class="semantic-group-head"><strong>${esc(name)}</strong><span class="pill-count">${arr.length}</span></div>
      <div class="mini-subline">${esc(opisGlobalnejGrupy(name))}</div>
      <ol class="summary-list global-summary-list">${renderGlobalGroupSummary(name, arr)}</ol>
      ${detailButton('Wyświetl wszystkie w tym poziomie', id)}
      ${inlineDetailBox(id, details)}
    </div>`;
  }).join('');
  return `<div class="card P2 grouped-card top-level-group global-card-group">
    <div class="title"><strong>Wyniki pogrupowane</strong><span class="badge">${lista.length}</span><span class="role">${groups.length} grup</span></div>
    <div class="why">Globalny filtr 3.3.3 zwija powtarzające się karty przed renderowaniem. Pełne dane są dostępne w eksporcie JSON.</div>
    <div class="global-groups">${rows}</div>
  </div>`;
}

function listaKart(lista, pusty='Brak.', opts={}){
  const clean = opts.includeTechnical ? (Array.isArray(lista) ? lista : []) : filtrujKartyWidoku(lista);
  if(!clean.length) return opts.hideEmpty ? '' : `<div class="empty compact-empty">${esc(pusty)}</div>`;
  if(!opts.noAutoGroup && clean.length >= 5){
    return renderGlobalGroupedCards(clean, pusty, opts);
  }
  return clean.map(k => karta(k, opts)).join('');
}

function inlineDetailId(prefix, groupName, i){
  return `${prefix}_${String(groupName || 'grupa').replace(/[^a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+/g,'_')}_${i}`;
}

function detailButton(label, targetId){
  return `<button type="button" class="inline-detail-btn" data-inline-detail="${esc(targetId)}">${esc(label || 'Pokaż w tym poziomie')}</button>`;
}

function inlineDetailBox(id, html){
  return `<div id="${esc(id)}" class="inline-detail-box" hidden>${html}</div>`;
}

/* Interfejs: aktywna implementacja
   Start pokazuje raport, jednostki, czysty TOP, aktorów i sprawczość.
   Pełne listy techniczne nie ładują się automatycznie do głównego scrolla. */
const STARTOWE_SEKCJE = new Set(['start','czyste','jednostki','aktorzy','sprawczosc','audytwidocznosci']);

function jestWidocznyElement(el){
  return !!(el && !el.hidden && el.offsetParent !== null);
}

function ustawInlineButtonState(btn, open){
  if(!btn) return;
  if(!btn.dataset.openLabel) btn.dataset.openLabel = btn.textContent || 'Pokaż w tym poziomie';
  btn.classList.toggle('active', !!open);
  btn.textContent = open ? 'Zamknij ten szczegół' : btn.dataset.openLabel;
}

function otworzPodpoziomyWidocznychSekcji(){
  const roots = [...document.querySelectorAll('[data-section]')].filter(sec => !sec.hidden);
  roots.forEach(root => {
    root.querySelectorAll('.inline-detail-box').forEach(box => { box.hidden = false; });
    root.querySelectorAll('[data-inline-detail]').forEach(btn => ustawInlineButtonState(btn, true));
    root.querySelectorAll('details').forEach(d => { d.open = true; });
  });
}

function zamknijPodpoziomyWidocznychSekcji(){
  const roots = [...document.querySelectorAll('[data-section]')].filter(sec => !sec.hidden);
  roots.forEach(root => {
    root.querySelectorAll('.inline-detail-box').forEach(box => { box.hidden = true; });
    root.querySelectorAll('[data-inline-detail]').forEach(btn => ustawInlineButtonState(btn, false));
    root.querySelectorAll('details.mini, details.technical-details').forEach(d => { d.open = false; });
  });
}

function otworzWszystkieOknaIPodpoziomy(){
  // Pełny tryb audytowy: pokazuje wszystkie sekcje i pełny tekst bez wewnętrznego limitu wysokości.
  // To jest jedyna ścieżka dla przycisku „Otwórz wszystkie okna i podpoziomy”.
  document.body.classList.add('force-all-open');
  const textPreview = $('textPreviewDetails');
  if(textPreview) textPreview.open = true;
  // Tryb audytowy zawsze pokazuje pełny tekst w widoku Hierarchia.
  if(ostatnieDane) renderujPodgladTekstu(ostatnieDane, 'wszystko');
  document.querySelectorAll('[data-section]').forEach(sec => {
    sec.hidden = false;
    if('open' in sec) sec.open = true;
    sec.querySelectorAll('details').forEach(d => { d.open = true; });
    sec.querySelectorAll('.inline-detail-box').forEach(box => { box.hidden = false; });
    sec.querySelectorAll('[data-inline-detail]').forEach(btn => ustawInlineButtonState(btn, true));
  });
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === 'wszystko');
  });
  if(typeof window.aktualizujNawigacjeAktywnejSekcji === 'function'){
    window.aktualizujNawigacjeAktywnejSekcji('wszystko');
  }
}

function zamknijWszystkieOknaWidoku(){
  // Wyjście z pełnego audytu przywraca kompaktowy, przewijany podgląd tekstu.
  document.body.classList.remove('force-all-open');
  document.querySelectorAll('[data-section]').forEach(sec => {
    if(sec.hidden) return;
    if('open' in sec && !String(sec.dataset.section || '').includes('start')) sec.open = false;
    sec.querySelectorAll('.inline-detail-box').forEach(box => { box.hidden = true; });
    sec.querySelectorAll('[data-inline-detail]').forEach(btn => ustawInlineButtonState(btn, false));
  });
}


/* Aktywne listy R: deduplikacja + połączenie z tekstem. */
function normalizujDoKluczaR(v){
  return String(v || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9ąćęłńóśźż]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function tekstZAnalizy(){
  const candidates = [
    ostatnieDane?.tekst,
    ostatnieDane?.input_text,
    ostatnieDane?.wejscie,
    ostatnieDane?.oryginalny_tekst,
    ostatnieDane?.podglad?.tekst,
    ostatnieDane?.podglad_tekstu?.tekst,
    ostatnieDane?.preview?.tekst
  ];
  for(const c of candidates){
    const s = String(c || '').trim();
    if(s.length > 20) return s;
  }
  const preview = $('highlightPreview');
  return preview ? preview.textContent || '' : '';
}

function znajdzZakresDlaKarty(k){
  if(!k) return null;
  if(k.link_status === 'linked' && Number(k.poczatek) >= 0 && Number(k.koniec) > Number(k.poczatek)){
    return {start:Number(k.poczatek), end:Number(k.koniec)};
  }
  const text = tekstZAnalizy();
  if(!text) return null;
  const probes = [
    k.fragment,
    k.fraza,
    k.relacja_wypowiedzi?.co_mowi,
    ...(Array.isArray(k.surface_forms) ? k.surface_forms : []),
    k.dzialanie
  ].map(x => String(x || '').replace(/\s+/g, ' ').trim()).filter(x => x.length >= 6);
  for(const raw of probes){
    const probe = raw.length > 180 ? raw.slice(0, 180).replace(/\s+\S*$/, '').trim() : raw;
    let idx = text.indexOf(probe);
    if(idx < 0){
      const shortProbe = probe.slice(0, 80).replace(/\s+\S*$/, '').trim();
      if(shortProbe.length >= 20) idx = text.indexOf(shortProbe);
      if(idx >= 0) return {start:idx, end:idx + shortProbe.length};
    }else{
      return {start:idx, end:idx + probe.length};
    }
  }
  return null;
}

function podlaczKarteRDoTekstu(k){
  const copy = Object.assign({}, k || {});
  const range = znajdzZakresDlaKarty(copy);
  if(range){
    copy.poczatek = range.start;
    copy.koniec = range.end;
    copy.link_status = 'linked';
    copy.highlight_id = copy.highlight_id || `r_micro_${range.start}_${range.end}`;
    copy.brak_podswietlenia_powod = '';
  }else if(!copy.link_status){
    copy.link_status = 'unlinked';
    copy.brak_podswietlenia_powod = 'nie znaleziono jednoznacznego fragmentu w tekście';
  }
  return copy;
}

function rPoziomKarty(k, fallback='R'){
  const raw = String(k?.poziom || k?.level || '').toUpperCase();
  if(/^R[0-9]/.test(raw)) return raw;
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.kod_techniczny || ''}`.toLowerCase();
  if(/mikrodiagnoza|relacja|sprawczo|kto mówi|kto mowi/.test(hay)) return 'R3';
  if(/opinia|cytat|źródło|zrodlo|medium/.test(hay)) return 'R2';
  if(/aktor/.test(hay)) return 'R1';
  return fallback;
}

function kluczDedupeR(k){
  const level = rPoziomKarty(k);
  const title = normalizujDoKluczaR(k?.tytul || k?.rola || k?.typ_twierdzenia || '');
  const entity = entityKeyZKarty(k);
  const rel = normalizujDoKluczaR(`${k?.relacja_wypowiedzi?.kto_mowi || ''} ${k?.relacja_wypowiedzi?.o_kim || ''} ${k?.relacja_wypowiedzi?.co_mowi || ''}`);
  if(entity && /aktor|zrodlo|źrodlo|medium|source/.test(title + ' ' + normalizujDoKluczaR(k?.rola || ''))){
    return `${level}|entity|${entity}`;
  }
  if(rel.length > 12) return `${level}|rel|${rel.slice(0, 160)}`;
  const frag = normalizujDoKluczaR(k?.fragment || k?.fraza || k?.dzialanie || rel || '').slice(0, 120);
  const start = Number(k?.poczatek);
  const end = Number(k?.koniec);
  if(Number.isFinite(start) && Number.isFinite(end) && end > start) return `${level}|range|${Math.floor(start/40)}|${title}|${entity || frag.slice(0,40)}`;
  return `${level}|${title}|${entity || frag}`;
}

function scoreKartyR(k){
  let s = 0;
  const level = rPoziomKarty(k);
  if(level === 'R3') s += 40;
  else if(level === 'R2') s += 30;
  else if(level === 'R1') s += 20;
  if(k?.link_status === 'linked') s += 20;
  if(k?.relacja_wypowiedzi && Object.keys(k.relacja_wypowiedzi).length) s += 10;
  if(k?.typ_twierdzenia) s += 7;
  if(k?.fragment) s += 5;
  if(k?.wymaga_przegladu) s += 2;
  const num = Number(k?.wynik);
  if(Number.isFinite(num)) s += Math.min(12, Math.max(0, num));
  return s;
}

function deduplikujKartyR(lista, limit=30){
  const arr = filtrujKartyWidoku(lista).map(podlaczKarteRDoTekstu);
  const map = new Map();
  arr.forEach(k => {
    const key = kluczDedupeR(k);
    const old = map.get(key);
    if(!old || scoreKartyR(k) > scoreKartyR(old)){
      map.set(key, k);
    }
  });
  return Array.from(map.values())
    .sort((a,b) => scoreKartyR(b) - scoreKartyR(a))
    .slice(0, limit);
}

function opisRListy(level, before, after){
  const diff = Math.max(0, before - after);
  return diff
    ? `${level}: oczyszczono ${before} → ${after}. Usunięto ${diff} duplikatów lub słabszych powtórek.`
    : `${level}: ${after} pozycji, bez wykrytych duplikatów do ukrycia.`;
}

function renderListaRPoDedupe(lista, opts={}){
  const raw = Array.isArray(lista) ? lista : [];
  const level = opts.level || 'R';
  const limit = opts.limit || 30;
  const clean = deduplikujKartyR(raw, limit);
  if(!clean.length) return ''; // Current: puste sekcje nie są renderowane
  const linked = clean.filter(k => k.link_status === 'linked').length;
  const unlinked = clean.length - linked;
  const visibleLimit = opts.visibleLimit || 5;
  const visibleCards = clean.slice(0, visibleLimit).map(k => karta(k, {compact:true, noAutoGroup:true, showTechnical:false})).join('');
  const fullId = inlineDetailId('r_full_list', level, raw.length + clean.length);
  const hiddenCards = clean.length > visibleLimit
    ? detailButton(`Pokaż pełną listę · ${clean.length}`, fullId) + inlineDetailBox(fullId, clean.slice(visibleLimit).map(k => karta(k, {compact:true, noAutoGroup:true, showTechnical:false})).join(''))
    : '';
  const note = raw.length > clean.length
    ? `<div class="hint-box">Pełna surowa lista: ${raw.length}. Widok pokazuje najpierw ${Math.min(visibleLimit, clean.length)} kart, a resztę dopiero po kliknięciu. Pełne dane są dostępne w eksporcie JSON.</div>`
    : `<div class="hint-box">Widok skrócony: na ekranie tylko TOP ${Math.min(visibleLimit, clean.length)}. Pełna lista jest ukryta pod przyciskiem, jeśli istnieje.</div>`;
  return `<div class="r-clean-list quick-view-panel">
    <div class="r-clean-summary">
      <strong>${esc(opisRListy(level, raw.length, clean.length))}</strong>
      <span>podłączone do tekstu: ${linked}</span>
      ${unlinked ? `<span>bez pewnego fragmentu: ${unlinked}</span>` : ''}
    </div>
    ${note}
    <div class="r-clean-cards">${visibleCards}</div>
    ${hiddenCards}
  </div>`;
}


function renderListaRCompactSummary(lista, opts={}){
  const raw = Array.isArray(lista) ? lista : [];
  const level = opts.level || 'R';
  const clean = deduplikujKartyR(raw, opts.limit || 30);
  if(!clean.length) return ''; // Current: puste sekcje nie są renderowane
  const id = inlineDetailId('r_compact_full', level, raw.length + clean.length);
  const topRows = clean.slice(0, opts.visibleLimit || 6).map((k, i) => {
    const title = semCardTitle(k);
    const summary = semCardSummary(k, 105);
    const type = k.typ_twierdzenia || rPoziomKarty(k, level);
    return `<li><strong>${esc(title)}</strong> <span class="readable-chip">${esc(type)}</span><div class="mini-subline">${esc(summary)}</div></li>`;
  }).join('');
  const fullCards = clean.map(k => karta(k, {compact:true, noAutoGroup:true, showTechnical:false})).join('');
  return `<div class="r-compact-summary quick-view-panel compact-details-mode">
    <div class="r-clean-summary"><strong>${esc(opts.title || level)}</strong><span>${clean.length} po deduplikacji</span><span>surowe: ${raw.length}</span></div>
    <ol class="summary-list compact-r-summary-list">${topRows}</ol>
    ${detailButton(`Pokaż pełne karty · ${clean.length}`, id)}
    ${inlineDetailBox(id, `<div class="second-level-detail">${fullCards}</div>`)}
  </div>`;
}

function renderR3MergedList(groups, opts={}){
  const all = [];
  (Array.isArray(groups) ? groups : []).forEach(g => {
    if(Array.isArray(g)) all.push(...g);
  });
  return renderListaRPoDedupe(all, Object.assign({level:'R3', limit:30}, opts));
}

function semCardTitle(k){
  return k?.tytul || k?.typ_twierdzenia || k?.rola || k?.poziom || 'wynik';
}

function semCardSummary(k, limit=120){
  const rel = k?.relacja_wypowiedzi || {};
  if(rel.kto_mowi || rel.o_kim || rel.co_mowi){
    const bits = [];
    if(rel.kto_mowi) bits.push(rel.kto_mowi);
    if(rel.o_kim) bits.push('o: ' + rel.o_kim);
    if(rel.co_mowi) bits.push('mówi: ' + rel.co_mowi);
    if(rel.medium) bits.push('medium: ' + rel.medium);
    return skrocTekst(bits.join(' → '), limit);
  }
  if(k?.kto_mowi || k?.o_kim){
    const bits = [];
    if(k.kto_mowi) bits.push(k.kto_mowi);
    if(k.o_kim) bits.push('o: ' + k.o_kim);
    if(k.fraza) bits.push('mówi: ' + k.fraza);
    if(k.medium) bits.push('medium: ' + k.medium);
    return skrocTekst(bits.join(' → '), limit);
  }
  if(Array.isArray(k?.aktorzy) && k.aktorzy.length){
    const bits = ['aktor: ' + k.aktorzy[0]];
    if(k.medium) bits.push('medium: ' + k.medium);
    if(k.frame) bits.push('rama: ' + k.frame);
    if(k.relation) bits.push(k.relation);
    return skrocTekst(bits.join(' · '), limit);
  }
  if(k?.medium || (Array.isArray(k?.zrodla) && k.zrodla.length)){
    return skrocTekst('medium/źródło: ' + (k.medium || k.zrodla[0]), limit);
  }
  return skrocTekst(k?.dzialanie || k?.fragment || k?.fraza || k?.uzasadnienie || semCardTitle(k), limit);
}

function renderLimitedDetails(cards, prefix){
  const arr = Array.isArray(cards) ? cards : [];
  if(!arr.length) return `<div class="empty compact-empty">Brak szczegółów.</div>`;
  const visible = arr.slice(0, 8).map(k => karta(k, {compact:true, noAutoGroup:true})).join('');
  const more = arr.length > 8 ? `<div class="hint-box">Pokazano 8 najważniejszych z ${arr.length}. Pełna lista jest dostępna w eksporcie JSON, żeby nie robić ściany kart.</div>` : '';
  return `<div class="semantic-detail-list">${visible}${more}</div>`;
}

function renderSemanticGroup(name, cards, prefix, opis){
  const arr = Array.isArray(cards) ? cards : [];
  const id = inlineDetailId(prefix, name, 0);
  const top = arr.slice(0, 3).map(k => `<li><strong>${esc(semCardTitle(k))}</strong><div class="mini-subline">${esc(semCardSummary(k, 110))}</div></li>`).join('');
  const list = top || `<li><span class="mini-subline">Brak wyników w tej grupie.</span></li>`;
  return `<div class="semantic-group-row">
    <div class="semantic-group-head"><strong>${esc(name)}</strong><span class="pill-count">${arr.length}</span></div>
    <div class="mini-subline">${esc(opis || '')}</div>
    <ol class="summary-list semantic-mini-list">${list}</ol>
    ${arr.length ? detailButton('Wyświetl w tym poziomie', id) + inlineDetailBox(id, renderLimitedDetails(arr, prefix)) : ''}
  </div>`;
}

function renderSemanticEffectivenessPanel(s){
  s = s || {};
  const cards = filtrujKartyWidoku(s.raport_skutecznosci_semantycznej || []);
  if(!cards.length) return '';
  return `<div class="card P3 grouped-card top-level-group semantic-effectiveness-card">
    <div class="title"><strong>Audyt jakości analizy</strong><span class="badge">${cards.length}</span></div>
    <div class="why">Audyt odczytuje ten sam aktywny wynik; nie uruchamia drugiej analizy.</div>
    ${renderLimitedDetails(cards, 'quality_report')}
  </div>`;
}

function pickFirst(arr, pred){
  if(!Array.isArray(arr)) return null;
  return pred ? (arr.find(pred) || arr[0] || null) : (arr[0] || null);
}

function cleanTopSemanticKey(card){
  if(!card || typeof card !== 'object') return '';
  const rr = card.canonical_relation || card.relacja_wypowiedzi || card.statement_relation || {};
  const relId = card.relation_id || rr.relation_id || '';
  if(relId) return `rel:${String(relId).trim()}`;
  const speaker = String(card.kto_mowi || card.speaker || rr.kto_mowi || rr.speaker || '').toLowerCase().trim();
  const claim = String(card.co_mowi || card.claim || card.fraza || card.fragment || rr.co_mowi || rr.claim || '').toLowerCase()
    .replace(/[„”"'.,;:!?()\[\]{}–—-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if(speaker && claim) return `sem:${speaker}|${claim.slice(0,180)}`;
  return `card:${String(card.kod_techniczny || card.tytul || card.label || '')}|${claim.slice(0,180)}`;
}

function dedupeCleanTopRows(rows){
  const seen = new Set();
  const out = [];
  (rows || []).forEach(row => {
    const key = cleanTopSemanticKey(row?.[1]);
    if(key && seen.has(key)) return;
    if(key) seen.add(key);
    out.push(row);
  });
  return out;
}

function renderCleanTopSemantic(s){
  s = s || {};
  const rawPicks = [
    ['Relacja wypowiedzi', pickFirst(s.relacje_wypowiedzi), 'Najmocniejsze kto mówi → o kim → co mówi.'],
    ['Rama P3', pickFirst(s.ramy_p3), 'Najważniejsza rama interpretacyjna.'],
    ['Status twierdzenia', pickFirst(s.fact_opinia_cytat), 'Najważniejszy fakt/opinia/cytat.'],
    ['Źródło/medium', pickFirst(s.mapa_zrodel, k => /medium|źródło|zrodlo|agencja/i.test(`${k?.tytul || ''} ${k?.rola || ''} ${k?.typ_twierdzenia || ''}`)), 'Najważniejsze źródło lub medium.'],
    ['Aktor/instytucja', pickFirst(s.mapa_aktorow), 'Najważniejszy aktor albo instytucja.'],
    ['Potwierdzone P1', pickFirst(s.potwierdzone_p1), 'Najmocniejsza potwierdzona technika P1.'],
    ['Hipoteza/diagnoza wyższa', pickFirst(s.diagnozy_p5 || s.techniki_p2), 'Najwyższy dostępny wniosek interpretacyjny.']
  ].filter(x => x[1]);
  const picks = dedupeCleanTopRows(rawPicks);

  if(!picks.length) return `<div class="empty compact-empty">Brak czystych kart TOP.</div>`;
  const rows = picks.slice(0, 10).map((row, i) => {
    const [label, card, opis] = row;
    const id = inlineDetailId('clean_sem_top', label, i);
    let summary = semCardSummary(card, 120);
    let evidence = '';
    if(label === 'Rama P3') {
      summary = card?.frame_label || card?.fraza || card?.tytul || summary;
      evidence = card?.evidence_text || card?.fragment || '';
    }
    return `<li><strong>${esc(label)}</strong><div class="mini-subline">${esc(opis)}</div><div class="mini-subline">${esc(summary)}</div>${evidence ? `<div class="mini-subline"><strong>Dowód:</strong> ${esc(skrocTekst(evidence, 140))}</div>` : ''}${detailButton('Wyświetl w tym poziomie', id)}${inlineDetailBox(id, karta(card, {compact:true, noAutoGroup:true}))}</li>`;
  }).join('');
  return `<div class="card P2 grouped-card top-level-group clean-top-semantic-card">
    <div class="title"><strong>Czyste TOP</strong><span class="badge">${picks.length}</span><span class="role">bez powtórek</span></div>
    <div class="why">TOP pokazuje przekrój najlepszych typów wyników, a nie pełną surową listę kart.</div>
    <ol class="summary-list">${rows}</ol>
  </div>`;
}

function czyKartaSemantyczna(k){
  const hay = `${k?.tytul || ''} ${k?.rola || ''} ${k?.kod_techniczny || ''} ${k?.typ_twierdzenia || ''}`.toLowerCase();
  return /skuteczno|semantyk|bramka|status twierd|fakt\/opinia|opinia cytowana|relacja wypowiedzi|kto mówi|ramy p3|źródło\/medium|zrodlo_medium/.test(hay);
}

function renderGroupedClaimSection(cards){
  if(!Array.isArray(cards) || !cards.length) return `<div class="empty compact-empty">Brak rozpoznanych faktów/opinii/cytatów.</div>`;
  const groups = {};
  cards.forEach(c => {
    const key = c.typ_twierdzenia || 'Inne';
    (groups[key] ||= []).push(c);
  });
  const order = ['Opinia cytowana', 'Opinia przypisana', 'Źródło/medium', 'Fakt opisowy', 'Cytat', 'Możliwa ocena redakcyjna', 'Inne'];
  return order.filter(name => groups[name]).map(name => {
    const arr = groups[name];
    const rows = arr.slice(0, 10).map((c, i) => {
      const id = inlineDetailId('claim', name, i);
      let main;
      if(name === 'Źródło/medium') {
        main = `<strong>${esc(c.medium || c.fraza || 'Źródło')}</strong>${c.fragment ? ` <span>· ${esc(skrocTekst(c.fragment, 90))}</span>` : ''}`;
      } else {
        const bits = [];
        if(c.kto_mowi) bits.push(`<strong>${esc(c.kto_mowi)}</strong>`);
        if(c.o_kim) bits.push(`o kim: ${esc(c.o_kim)}`);
        const core = c.relacja_wypowiedzi?.co_mowi || c.fraza || c.fragment || '';
        if(core) bits.push(`„${esc(skrocTekst(core, 88))}”`);
        main = bits.join(' · ') || esc(skrocTekst(c.fragment || c.fraza || '', 110));
      }
      return `<li>${main}${detailButton('Wyświetl w tym poziomie', id)}${inlineDetailBox(id, karta(c, {compact:true}))}</li>`;
    }).join('');
    const more = arr.length > 10 ? `<div class="mini-subline">Ukryto ${arr.length - 10} mniej ważnych powtórek. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
    return `<div class="card R2 grouped-card top-level-group"><div class="title"><strong>${esc(name)}</strong><span class="badge">${arr.length}</span><span class="role">najwyższy poziom</span></div><div class="why">Jedna karta zbiorcza. Szczegóły otwierają się w obrębie tego samego poziomu, bez tunelu powtórek.</div><ol class="summary-list">${rows}</ol>${more}</div>`;
  }).join('');
}

function renderGroupedSourceSection(cards){
  if(!Array.isArray(cards) || !cards.length) return `<div class="empty compact-empty">Brak wykrytych źródeł/mediów.</div>`;
  const seen = new Map();
  cards.forEach((c, idx) => {
    const key = String(c.medium || c.fraza || '').trim();
    if(!key) return;
    const row = seen.get(key) || {name:key, count:0, examples:[], card:c, idx};
    row.count += 1;
    if(row.examples.length < 2 && c.fragment) row.examples.push(skrocTekst(c.fragment, 110));
    seen.set(key, row);
  });
  const items = [...seen.values()].sort((a,b)=>b.count-a.count || a.name.localeCompare(b.name,'pl'));
  const rows = items.slice(0, 12).map((it, i) => {
    const id = inlineDetailId('source', it.name, i);
    return `<li><strong>${esc(it.name)}</strong> <span class="pill-count">${it.count}</span>${it.examples[0] ? `<div class="mini-subline">${esc(it.examples[0])}</div>` : ''}${detailButton('Wyświetl w tym poziomie', id)}${inlineDetailBox(id, karta(it.card, {compact:true}))}</li>`;
  }).join('');
  const more = items.length > 12 ? `<div class="mini-subline">Ukryto ${items.length - 12} rzadszych źródeł. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
  return `<div class="card R1 grouped-card top-level-group"><div class="title"><strong>Źródła/media</strong><span class="badge">${items.length}</span><span class="role">najwyższy poziom</span></div><div class="why">Pokazujemy krótką nazwę źródła. Szczegóły otwierają się tutaj, a nie jako druga długa lista.</div><ol class="summary-list sources-list">${rows}</ol>${more}</div>`;
}

function renderGroupedRelationSection(cards){
  if(!Array.isArray(cards) || !cards.length) return `<div class="empty compact-empty">Brak relacji wypowiedzi do pokazania.</div>`;
  const rows = cards.slice(0, 12).map((c, i) => {
    const rel = c.relacja_wypowiedzi || {};
    const id = inlineDetailId('rel', `${rel.kto_mowi || c.kto_mowi || 'nadawca'}_${i}`, i);
    return `<li><strong>${esc(rel.kto_mowi || c.kto_mowi || 'Nieustalony nadawca')}</strong>${(rel.o_kim || c.o_kim) ? ` <span>→ o kim: ${esc(rel.o_kim || c.o_kim)}</span>` : ''}<div class="mini-subline">${esc(skrocTekst(rel.co_mowi || c.fraza || c.fragment || '', 110))}</div>${(rel.medium || c.medium) ? `<div class="mini-subline">medium: ${esc(rel.medium || c.medium)}</div>` : ''}${detailButton('Wyświetl w tym poziomie', id)}${inlineDetailBox(id, karta(c, {compact:true}))}</li>`;
  }).join('');
  const more = cards.length > 12 ? `<div class="mini-subline">Ukryto ${cards.length - 12} mniej ważnych relacji. Pełna lista jest dostępna w eksporcie JSON.</div>` : '';
  return `<div class="card R2 grouped-card top-level-group"><div class="title"><strong>Kto mówi → o kim → co mówi</strong><span class="badge">${cards.length}</span><span class="role">najwyższy poziom</span></div><div class="why">Najpierw relacje skrócone. Po kliknięciu szczegół pojawia się w tej samej karcie zbiorczej.</div><ol class="summary-list relation-summary-list">${rows}</ol>${more}</div>`;
}


function normalizujNazweAktora(x){
  let s = String(x || '').trim();
  s = s.replace(/^(fraza|aktor|medium|źródło)\s*:\s*/i, '');
  s = s.replace(/\s+/g, ' ');
  s = s.replace(/[.,;:]+$/g, '');
  return s;
}

function nazwaAktoraZKarty(c){
  const direct = c.canonical_name || c.nazwa_kanoniczna || c.aktor || c.nazwa_aktora || c.osoba || c.medium || c.fraza || c.name || c.label || '';
  const clean = normalizujNazweAktora(direct);
  if(clean && clean.length <= 80) return clean;

  const frag = String(c.fragment || c.tekst || '').trim();
  const m = frag.match(/\b([A-ZŁŚŻŹĆŃÓ][\wąćęłńóśźż-]+(?:\s+[A-ZŁŚŻŹĆŃÓ][\wąćęłńóśźż-]+){0,3}|TVN24|PAP|KO|PiS|Sejm|komisja)\b/u);
  return normalizujNazweAktora(m ? m[1] : clean || 'Nieustalony aktor');
}

function rolaAktoraZKarty(c, name=''){
  const entityType = String(c?.entity_type || c?.typ_encji || '').toLowerCase();
  if(entityType === 'person') return 'Osoby';
  if(entityType === 'institution') return 'Instytucje';
  if(entityType === 'medium' || entityType === 'source' || entityType === 'document_source') return 'Media i źródła';
  if(entityType === 'party') return 'Partie / środowiska';
  if(entityType === 'product' || entityType === 'topic' || entityType === 'fund') return 'Obiekty / sprawy';
  const hay = `${c?.rola || ''} ${c?.typ || ''} ${c?.typ_twierdzenia || ''} ${c?.tytul || ''} ${c?.uzasadnienie || ''} ${c?.fragment || ''} ${name}`.toLowerCase();
  if(/tvn24|pap|źródło|zrodlo|medium|agencj|autor|autorka|redakc|shutterstock/.test(hay)) return 'Media i źródła';
  if(/fundusz|komisj|sejm|trybunał|trybunal|sąd|sad|prokuratur|instytucj|ministerstwo|służb|sluzb|najwyższa izba kontroli|\bnik\b/.test(hay)) return 'Instytucje';
  if(/pegasus|immunitet|przesłuch|przesluch|posiedzeni|legalno|prawidłowo|celowość|celowosc|procedur/.test(hay)) return 'Obiekty / sprawy';
  if(/ko|pis|konfederac|lewica|parti/.test(hay)) return 'Partie / środowiska';
  return 'Inne role';
}

function opisRoliAktora(c, name=''){
  const roles = Array.isArray(c?.entity_roles) ? c.entity_roles.map(x => String(x || '').toLowerCase()) : [];
  if(roles.includes('speaker')) return roles.includes('target') ? 'mówca + obiekt wypowiedzi' : 'mówi / ocenia';
  if(roles.includes('target')) return 'obiekt wypowiedzi';
  if(roles.includes('institution')) return 'instytucja / kontekst';
  if(roles.includes('medium') || roles.includes('source') || roles.includes('document_source')) return 'źródło / medium';
  if(roles.includes('affiliation')) return 'afiliacja';
  return 'występuje w zaakceptowanych relacjach';
}

function zbierzAktorowDoGrup(rawCards, groupCards){
  const all = []
    .concat(Array.isArray(rawCards) ? rawCards : [])
    .concat(Array.isArray(groupCards) ? groupCards : []);

  const map = new Map();
  all.forEach((c) => {
    const name = nazwaAktoraZKarty(c);
    if(!name || name === 'Nieustalony aktor') return;
    const key = name.toLowerCase();
    const row = map.get(key) || {
      name,
      count: 0,
      cards: [],
      examples: [],
      role: rolaAktoraZKarty(c, name),
      roleHint: opisRoliAktora(c, name)
    };
    const realMentions = Math.max(1, Number(c?.mentions || c?.liczba_wzmianek || 1));
    // Mapa aktorów używa jednej aktywnej listy encji.
    // Nie sumujemy duplikatów warstwy prezentacji; pokazujemy licznik relacji
    // wyliczony w core.
    row.count = Math.max(row.count, realMentions);
    if(row.cards.length < 4 && !row.cards.some(x => String(x?.entity_id || '').toLowerCase() === String(c?.entity_id || '').toLowerCase())) row.cards.push(c);
    const ex = skrocTekst(c.fragment || c.tekst || c.uzasadnienie || c.fraza || '', 130);
    if(ex && row.examples.length < 2 && !row.examples.includes(ex)) row.examples.push(ex);
    if(row.role === 'Inne role') row.role = rolaAktoraZKarty(c, name);
    if(row.roleHint === 'występuje w tekście') row.roleHint = opisRoliAktora(c, name);
    map.set(key, row);
  });

  return [...map.values()].sort((a,b)=>b.count-a.count || a.name.localeCompare(b.name,'pl'));
}

function renderActorRoleGroup(title, items, prefix){
  if(!items.length) return '';
  const id = inlineDetailId(prefix || 'actor_role', title, 0);
  const top = items.slice(0, 6).map((it, i) => `<li>
    <strong>${esc(it.name)}</strong> <span class="pill-count">${it.count}</span>
    <div class="mini-subline">${esc(it.roleHint || 'występuje w tekście')}${it.examples[0] ? ' · ' + esc(it.examples[0]) : ''}</div>
  </li>`).join('');
  const details = items.map((it, i) => {
    const rows = it.cards.slice(0, 6).map((k, j) => {
      const fid = inlineDetailId(`${prefix || 'actor_occ'}_${i}`, it.name, j);
      const linked = k.link_status === 'linked' || (Number(k.poczatek) >= 0 && Number(k.koniec) > Number(k.poczatek));
      return `<li><strong>${esc(skrocTekst(k.fraza || k.medium || it.name, 70))}</strong><div class="mini-subline">${esc(skrocTekst(k.fragment || k.uzasadnienie || '', 120))}</div>${linked ? `<button type="button" class="small-action show-hit-btn" ${atrybutyTrafienia(k)}>Pokaż w tekście</button>` : ''}${detailButton('Pokaż kartę', fid)}${inlineDetailBox(fid, karta(k, {compact:true, noAutoGroup:true, showTechnical:false}))}</li>`;
    }).join('');
    const moreRows = it.count > it.cards.length ? `<div class="mini-subline">Pozostałe wystąpienia są dostępne w eksporcie JSON.</div>` : '';
    return `<div class="actor-detail-person"><h4>${esc(it.name)} <span class="pill-count">${it.count}</span></h4><div class="mini-subline">${esc(it.roleHint || '')}</div><ol class="summary-list">${rows}</ol>${moreRows}</div>`;
  }).join('');
  const more = items.length > 6 ? `<div class="mini-subline">W skrócie pokazano 6 z ${items.length}. Pełna grupa otwiera się poniżej.</div>` : '';
  return `<div class="actor-role-group">
    <div class="semantic-group-head"><strong>${esc(title)}</strong><span class="pill-count">${items.length}</span></div>
    <ol class="summary-list actor-summary-list">${top}</ol>${more}
    ${detailButton('Wyświetl pełną grupę w tym poziomie', id)}
    ${inlineDetailBox(id, details)}
  </div>`;
}

function renderCollapsedActorMap(rawCards, groupCards, opts={}){
  const items = zbierzAktorowDoGrup(filtrujKartyWidoku(rawCards), filtrujKartyWidoku(groupCards));
  if(!items.length) return `<div class="empty compact-empty">Brak mapy aktorów.</div>`;

  const order = ['Osoby','Instytucje','Media i źródła','Obiekty / sprawy','Partie / środowiska','Inne role'];
  const grouped = new Map(order.map(k => [k, []]));
  items.forEach(it => {
    const role = grouped.has(it.role) ? it.role : 'Inne role';
    grouped.get(role).push(it);
  });

  const topId = inlineDetailId(opts.prefix || 'actor_map', 'pelna_mapa', 0);
  const najwazniejsi = items.slice(0, 5).map((it, i) => `<li><strong>${esc(it.name)}</strong> <span class="pill-count">${it.count}</span><div class="mini-subline">${esc(it.role)} · ${esc(it.roleHint || 'występuje w tekście')}</div></li>`).join('');

  const groupHtml = order.map(role => renderActorRoleGroup(role, grouped.get(role) || [], `${opts.prefix || 'actor_map'}_${role}`)).join('');
  const rawCount = (Array.isArray(rawCards) ? rawCards.length : 0) + (Array.isArray(groupCards) ? groupCards.length : 0);

  return `<div class="card R1 grouped-card top-level-group actor-group-card actor-map-collapsed-card">
    <div class="title"><strong>${esc(opts.title || 'Mapa aktorów')}</strong><span class="badge">${rawCount}</span><span class="role">${items.length} unikalnych</span></div>
    <div class="why">Mapa jest zwinięta do ról. Nie pokazuje osobnej karty i osobnego przycisku dla każdego aktora. Pełna lista jest dostępna w eksporcie JSON.</div>
    <h4>Najważniejsi</h4>
    <ol class="summary-list actor-summary-list">${najwazniejsi}</ol>
    ${detailButton('Wyświetl pełną mapę w tym poziomie', topId)}
    ${inlineDetailBox(topId, `<div class="actor-role-groups">${groupHtml}</div>`)}
  </div>`;
}


function priorytetPoziomuPodgladu(poziom){
  return ({P5:0, P4:1, P3:2, P2:3, P1:4, P0:5})[String(poziom || '').toUpperCase()] ?? 99;
}

function spanPasujeDoWidoku(span, widok){
  const key = String(widok || 'wszystko').toLowerCase();
  if(['wszystko','all','hierarchia','hierarchiczny'].includes(key)) return true;
  const poziom = String(span?.poziom || '').toLowerCase();
  const rola = String(span?.rola_techniczna || span?.rola || '').toLowerCase();
  const sekcja = String(span?.sekcja_podgladu || '').toLowerCase();
  if(['p0','p1','p2','p3','p4','p5'].includes(key)) return poziom === key;
  if(key === 'czyste') return sekcja === 'top_wyniki';
  if(key === 'aktorzy') return sekcja === 'mapa_aktorow' || rola.includes('actor') || rola.includes('aktor');
  if(key === 'sprawczosc') return sekcja === 'mapa_sprawczosci' || rola.includes('agency') || rola.includes('spraw');
  if(key === 'zrodla') return sekcja === 'mapa_zrodel' || rola.includes('source') || rola.includes('media') || rola.includes('źródło') || rola.includes('zrodlo');
  if(key === 'fact') return sekcja === 'fact_opinia_cytat' || rola.includes('fact_opinion_quote') || rola.includes('fakt') || rola.includes('opinia') || rola.includes('cytat');
  if(['relacje','wypowiedzi'].includes(key)) return sekcja === 'relacje_wypowiedzi' || rola.includes('statement') || rola.includes('wypowied');
  if(key === 'kandydaci') return rola.includes('candidate') || rola.includes('kandydat') || Boolean(span?.wymaga_przegladu) || sekcja.includes('kandydaci');
  return false;
}

function spanyNakladajaSie(a, b){
  return !(Number(a?.koniec) <= Number(b?.poczatek) || Number(a?.poczatek) >= Number(b?.koniec));
}

function dzieckoSpanPodgladu(span){
  return {
    poczatek:span?.poczatek, koniec:span?.koniec, poziom:span?.poziom, tytul:span?.tytul,
    typ_techniki:span?.typ_techniki, fraza:span?.fraza, rola:span?.rola,
    rola_techniczna:span?.rola_techniczna, sekcja_podgladu:span?.sekcja_podgladu,
    uzasadnienie:span?.uzasadnienie, highlight_id:span?.highlight_id
  };
}

function zbudujSpanyWidoku(rawSpans, widok){
  const key = String(widok || 'wszystko').toLowerCase();
  const filtered = (Array.isArray(rawSpans) ? rawSpans : [])
    .filter(span => spanPasujeDoWidoku(span, key))
    .map(span => Object.assign({}, span, {zasloniete:[]}));

  let selected = [];
  if(['wszystko','all','hierarchia','hierarchiczny'].includes(key)){
    const ordered = filtered.sort((a,b) =>
      priorytetPoziomuPodgladu(a?.poziom) - priorytetPoziomuPodgladu(b?.poziom) ||
      Number(a?.poczatek || 0) - Number(b?.poczatek || 0) ||
      -((Number(a?.koniec || 0)-Number(a?.poczatek || 0)) - (Number(b?.koniec || 0)-Number(b?.poczatek || 0)))
    );
    ordered.forEach(span => {
      const parent = selected.find(existing => spanyNakladajaSie(span, existing));
      if(parent) parent.zasloniete.push(dzieckoSpanPodgladu(span));
      else selected.push(span);
    });
    selected.sort((a,b) => Number(a?.poczatek || 0) - Number(b?.poczatek || 0));
  }else{
    const ordered = filtered.sort((a,b) =>
      Number(a?.poczatek || 0) - Number(b?.poczatek || 0) ||
      -((Number(a?.koniec || 0)-Number(a?.poczatek || 0)) - (Number(b?.koniec || 0)-Number(b?.poczatek || 0)))
    );
    ordered.forEach(span => {
      if(selected.some(existing => spanyNakladajaSie(span, existing))) return;
      selected.push(span);
    });
  }
  return selected.map((span, i) => Object.assign({}, span, {
    id:String(span?.highlight_id || `hit-${key}-${i}`)
  }));
}

function aktualnyWidokPodgladu(data, widok){
  const podglad = data && data.podglad_tekstu ? data.podglad_tekstu : null;
  if(!podglad) return null;
  const key = String(widok || 'wszystko').toLowerCase();
  const widoki = podglad.widoki || {};
  const legacy = widoki[key] || widoki.wszystko;
  if(legacy && Array.isArray(legacy.spany)) return legacy;
  const spany = zbudujSpanyWidoku(podglad.spany_surowe || [], key);
  return {nazwa:key, liczba_podswietlen:spany.length, spany};
}

function ustawAktywnyFiltrPodgladu(widok){
  const key = String(widok || 'wszystko').toLowerCase();
  document.querySelectorAll('.preview-filter').forEach(b => b.classList.toggle('active', b.dataset.previewView === key));
}

function renderujHtmlZPodswietleniami(tekst, spany){
  const source = String(tekst || '');
  const ranges = Array.isArray(spany) ? spany : [];
  if(!source) return '';
  let out = '';
  let pos = 0;
  ranges.forEach((span, i) => {
    const start = Math.max(0, Math.min(source.length, Number(span?.poczatek) || 0));
    const end = Math.max(start, Math.min(source.length, Number(span?.koniec) || start));
    if(start < pos || end <= start) return;
    out += esc(source.slice(pos, start));
    const poziom = String(span?.poziom || 'INFO');
    const technika = String(span?.typ_techniki || 'inne');
    const tytul = String(span?.tytul || 'Trafienie');
    const rola = String(span?.rola || '');
    const hitId = String(span?.id || span?.highlight_id || `hit-${i}`);
    const childCount = Array.isArray(span?.zasloniete) ? span.zasloniete.length : 0;
    const childLabel = childCount ? `<span class="hl-covered">+${childCount}</span>` : '';
    out += `<mark id="${esc(hitId)}" class="hl hl-${esc(poziom.toLowerCase())} hl-tech-${esc(technika)}" data-hit-index="${i}" data-hit-id="${esc(hitId)}" data-level="${esc(poziom)}" data-start="${start}" data-end="${end}" title="${esc(tytul)} · ${esc(rola)}"><span class="hl-label">${esc(poziom)}</span>${childLabel}${esc(source.slice(start, end))}</mark>`;
    pos = end;
  });
  out += esc(source.slice(pos));
  return out.replace(/\n/g, '<br>');
}

function renderujPodgladTekstu(data, widok='wszystko'){
  const box = $('highlightPreview');
  const details = $('highlightDetails');
  if(!box) return;
  aktywnyWidokPodgladu = String(widok || 'wszystko').toLowerCase();
  ustawAktywnyFiltrPodgladu(aktywnyWidokPodgladu);
  const aktywny = aktualnyWidokPodgladu(data, aktywnyWidokPodgladu);
  ostatnieSpanyPodgladu = aktywny && Array.isArray(aktywny.spany) ? aktywny.spany : [];
  const tekst = String(data?.podglad_tekstu?.tekst || '');
  const html = aktywny && aktywny.html
    ? aktywny.html
    : renderujHtmlZPodswietleniami(tekst, ostatnieSpanyPodgladu);
  box.innerHTML = html || 'Brak tekstu do wyświetlenia dla bieżącego widoku.';
  box.classList.toggle('empty-preview', !tekst && !html);
  if(details){
    const n = aktywny ? (aktywny.liczba_podswietlen || 0) : 0;
    details.textContent = n
      ? `Widok: ${etykietaWidoku(aktywnyWidokPodgladu)}. Oznaczone fragmenty: ${n}. Kliknij fragment albo przycisk „Pokaż w tekście” przy karcie wyniku.`
      : `Widok: ${etykietaWidoku(aktywnyWidokPodgladu)}. Brak oznaczonych fragmentów.`;
  }
  box.querySelectorAll('.hl').forEach(el => el.addEventListener('click', () => pokazTrafienieWPodgladzie(el, false)));
}

function etykietaWidoku(widok){
  return {wszystko:'hierarchia głównych oznaczeń', czyste:'czyste TOP', aktorzy:'aktorzy', sprawczosc:'sprawczość', zrodla:'źródła/media', relacje:'kto mówi → o kim → co mówi', p5:'tylko P5', p4:'tylko P4', p3:'tylko P3', p2:'tylko P2', p1:'tylko P1', p0:'tylko P0', kandydaci:'kandydaci', fact:'fakt / opinia / cytat'}[widok] || widok;
}

function szczegolyZaslonietych(span){
  const kids = Array.isArray(span.zasloniete) ? span.zasloniete : [];
  if(!kids.length) return '';
  return `<details class="mini covered-tree" open><summary>Niższe warstwy przykryte przez to trafienie · ${kids.length}</summary>${kids.map(k => `<div class="covered-row"><strong>${esc(k.poziom || '')} · ${esc(k.tytul || '')}</strong>${k.fraza ? `<div>fraza: <code>${esc(k.fraza)}</code></div>` : ''}${k.uzasadnienie ? `<small>${esc(k.uzasadnienie)}</small>` : ''}</div>`).join('')}</details>`;
}

function pokazTrafienieWPodgladzie(el, przewin=true){
  const details = $('highlightDetails');
  if(!details || !ostatnieDane) return;
  document.querySelectorAll('.hl.active').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  el.classList.remove('pulse-hit');
  void el.offsetWidth;
  el.classList.add('pulse-hit');
  if(przewin) el.scrollIntoView({behavior:'smooth', block:'center', inline:'center'});
  const idx = Number(el.dataset.hitIndex || -1);
  const span = ostatnieSpanyPodgladu[idx];
  if(!span) return;
  details.innerHTML = `<strong>${esc(span.poziom || '')} · ${esc(span.tytul || 'Trafienie')}</strong>
    <div>${esc(span.rola || '')}${span.pewnosc ? ` · pewność: ${esc(span.pewnosc)}` : ''}</div>
    ${span.fraza ? `<div>fraza: <code>${esc(span.fraza)}</code></div>` : ''}
    ${span.uzasadnienie ? `<div class="hit-frag">${esc(span.uzasadnienie)}</div>` : ''}
    ${szczegolyZaslonietych(span)}`;
}

function znajdzElementTrafienia(start, end, level, highlightId){
  const box = $('highlightPreview');
  if(!box) return null;
  const candidates = [...box.querySelectorAll('.hl')];
  if(highlightId){
    const byId = candidates.find(x => String(x.id || '') === String(highlightId));
    if(byId) return byId;
  }
  let el = candidates.find(x => String(x.dataset.start) === String(start) && String(x.dataset.end) === String(end));
  if(el) return el;
  el = candidates.find(x => String(x.dataset.level || '').toLowerCase() === String(level || '').toLowerCase() && Number(x.dataset.start) <= Number(start) && Number(x.dataset.end) >= Number(end));
  return el || null;
}

function pokazKarteWPodgladzie(btn){
  if(!ostatnieDane) return;
  const previewDetails = $('textPreviewDetails');
  if(previewDetails) previewDetails.open = true;
  const start = btn.dataset.start;
  const end = btn.dataset.end;
  const level = String(btn.dataset.level || '').toLowerCase();
  const highlightId = btn.dataset.highlightId || '';
  let el = znajdzElementTrafienia(start, end, level, highlightId);
  if(!el){
    // Karta może być ukryta w innym filtrze podglądu. Najpierw spróbuj poziomu,
    // potem wróć do hierarchii. Nie pokazujemy ślepych przycisków, więc brak el
    // oznacza tylko filtr/warstwę, nie brak dowodu.
    renderujPodgladTekstu(ostatnieDane, level || 'wszystko');
    el = znajdzElementTrafienia(start, end, level, highlightId);
  }
  if(!el){
    renderujPodgladTekstu(ostatnieDane, 'wszystko');
    el = znajdzElementTrafienia(start, end, level, highlightId);
  }
  if(el) pokazTrafienieWPodgladzie(el, true);
}

function podlaczNawigacjeKart(){
  document.querySelectorAll('.show-hit-btn').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      pokazKarteWPodgladzie(btn);
    });
  });
}



function meaningUnitCard(u, i){
  const linked = u.link_status === 'linked' && Number(u.poczatek) >= 0 && Number(u.koniec) > Number(u.poczatek);
  const layers = Array.isArray(u.warstwy) ? u.warstwy.map(x => `<span class="readable-chip">${esc(x)}</span>`).join('') : '';
  const hasTech = Array.isArray(u.techniczne_karty) && u.techniczne_karty.length;
  const techId = inlineDetailId('meaning_tech', u.tytul || `unit_${i}`, i);
  const tech = '';
  return `<div class="meaning-unit-card card R3 compact-details-mode" data-hit-card="1" data-highlight-id="${esc(u.highlight_id || '')}" data-link-status="${esc(u.link_status || '')}" data-level="R3" data-start="${esc(u.poczatek ?? '')}" data-end="${esc(u.koniec ?? '')}" data-fragment="${esc(u.fragment || '')}">
    <div class="title"><strong>${esc(u.tytul || `Jednostka znaczenia #${i+1}`)}</strong><span class="badge">${esc(u.liczba_polaczonych_kart || 1)}</span><span class="role">wynik dla odbiorcy · sens + dowody</span></div>
    ${u.fragment ? `<div class="fragment meaning-fragment">${esc(skrocTekst(u.fragment, 180))}</div>` : ''}
    ${(u.score || u.priorytet) ? `<div class="meaning-score-line"><span>ranking: ${esc(u.score || '')}</span>${u.priorytet ? `<span>priorytet: ${esc(u.priorytet)}</span>` : ''}${u.wymaga_przegladu ? '<span>wymaga kontroli</span>' : ''}</div>` : ''}
    <div class="meaning-grid">
      ${u.aktor ? `<span>Aktor</span><b>${esc(u.aktor)}</b>` : ''}
      ${u.marker_atrybucji ? `<span>Marker atrybucji</span><b>${esc(u.marker_atrybucji)}</b>` : ''}
      ${u.zrodlo ? `<span>Źródło przywołane</span><b>${esc(u.zrodlo)}</b>` : ''}
      ${u.zrodlo_dokumentu ? `<span>Źródło dokumentu</span><b>${esc(u.zrodlo_dokumentu)}</b>` : ''}
      ${Array.isArray(u.zrodla_zdjec) && u.zrodla_zdjec.length ? `<span>Źródło zdjęcia</span><b>${esc(u.zrodla_zdjec.join(', '))}</b>` : ''}
      ${u.medium ? `<span>Medium</span><b>${esc(u.medium)}</b>` : ''}
      ${u.program ? `<span>Program</span><b>${esc(u.program)}</b>` : ''}
      ${u.typ_wypowiedzi ? `<span>Typ wypowiedzi</span><b>${esc(u.typ_wypowiedzi)}</b>` : ''}
      ${u.sprawczosc ? `<span>Czynność mówienia</span><b>${esc(skrocTekst(u.sprawczosc, 110))}</b>` : ''}
      ${u.target ? `<span>Target</span><b>${esc(u.target)}</b>` : ''}
      ${u.temat ? `<span>Temat</span><b>${esc(u.temat)}</b>` : ''}
      ${u.obiekt ? `<span>Obiekt</span><b>${esc(u.obiekt)}</b>` : ''}
      ${u.rama ? `<span>Rama</span><b>${esc(skrocTekst(u.rama, 100))}</b>` : ''}
      ${u.struktura ? `<span>Struktura</span><b>${esc(skrocTekst(u.struktura, 100))}</b>` : ''}
    </div>
    ${Array.isArray(u.dokumenty_bazy_ids) && u.dokumenty_bazy_ids.length ? `<div class="meta database-card-origin">baza: ${esc(u.dokumenty_bazy_ids.slice(0,3).map(id => (zbiorczeDokumentyMap[String(id)]||{}).relative_path || `#${id}`).join(' · '))}${u.dokumenty_bazy_ids.length>3 ? ` · +${u.dokumenty_bazy_ids.length-3} dokumentów` : ''}</div>` : ''}
    ${Array.isArray(u.dowody_pomocnicze) && u.dowody_pomocnicze.length ? `<details class="mini"><summary>Dowody pomocnicze / scalone powtórzenia · ${esc(u.dowody_pomocnicze.length)}</summary><ol>${u.dowody_pomocnicze.slice(0,5).map(x => `<li>${esc(skrocTekst(x, 180))}</li>`).join('')}</ol></details>` : ''}
    ${u.liczba_powtorzen_scalonych ? `<div class="technical-note">Scalono powtórzenia sensu: ${esc(u.liczba_powtorzen_scalonych)}</div>` : ''}
    ${layers ? `<div class="meaning-layers">${layers}</div>` : ''}
    ${linked ? `<button type="button" class="show-hit-btn" data-hit-card="1" data-highlight-id="${esc(u.highlight_id || '')}" data-link-status="linked" data-level="R3" data-start="${esc(u.poczatek)}" data-end="${esc(u.koniec)}" data-fragment="${esc(u.fragment || '')}">Pokaż w tekście</button>` : ''}
    ${tech}
  </div>`;
}

function renderMeaningUnits(units){
  const list = Array.isArray(units) ? units : [];
  if(!list.length) return '<div class="empty compact-empty">Brak jednostek znaczenia. Pełne dane są dostępne w eksporcie JSON.</div>';
  const limit = 5;
  const visible = list.slice(0, limit).map((u, i) => meaningUnitCard(u, i)).join('');
  const hidden = list.length > limit
    ? detailButton(`Pokaż pełną listę jednostek · ${list.length}`, 'meaning_units_full_list') + inlineDetailBox('meaning_units_full_list', list.slice(limit).map((u, i) => meaningUnitCard(u, i + limit)).join(''))
    : '';
  return `<div class="meaning-units-panel quick-view-panel"><p class="hint">Nazwy osób, instytucji i źródeł są ujednolicane, a wszystkie widoki korzystają z tych samych zaakceptowanych relacji.</p>${visible}${hidden}</div>`;
}

function renderCzytelnyRaport(report){
  const r = report || {};
  const items = Array.isArray(r.items) ? r.items : [];
  const checks = Array.isArray(r.do_sprawdzenia) ? r.do_sprawdzenia : [];
  if(!items.length && !checks.length){
    return '<div class="empty compact-empty">Raport czytelny pojawi się po analizie.</div>';
  }
  const rows = items.map((it, i) => {
    const target = it.sekcja || 'czyste';
    return `<li class="readable-report-item">
      <div><strong>${esc(it.tytul || `Wniosek ${i+1}`)}</strong></div>
      <div class="readable-value">${esc(it.wartosc || 'Brak danych.')}</div>
      ${it.opis ? `<div class="mini-subline">${esc(it.opis)}</div>` : ''}
      ${target ? `<div class="readable-actions"><button type="button" class="small-action readable-jump" data-readable-view="${esc(target)}">Pokaż sekcję</button><button type="button" class="small-action readable-window" data-readable-view="${esc(target)}">Otwórz w oknie</button></div>` : ''}
    </li>`;
  }).join('');
  const checkRows = checks.map(x => `<li>${esc(x)}</li>`).join('');
  const metryka = r.metryka || {};
  const chips = Object.entries(metryka).filter(([,v]) => { const n=Number(v); return Number.isFinite(n) ? n > 0 : Boolean(String(v ?? '').trim()); }).map(([k,v]) => `<span class="readable-chip"><strong>${esc(v)}</strong> ${esc(k.replaceAll('_',' '))}</span>`).join('');
  return `<div class="readable-report-card">
    <div class="readable-report-head">
      <div><h3>${esc(r.tytul || 'Wynik analizy')}</h3><p>${esc(r.podtytul || 'Najpierw sens, potem szczegóły.')}</p></div>
      <span class="readable-stage">raport czytelny</span>
    </div>
    <ol class="summary-list readable-report-list">${rows}</ol>
    <div class="readable-checks"><strong>Do sprawdzenia</strong><ol>${checkRows}</ol></div>
    ${chips ? `<div class="readable-metrics">${chips}</div>` : ''}
    ${r.zasada ? `<div class="hint-box">${esc(r.zasada)}</div>` : ''}
  </div>`;
}

function p0Html(p0){
  if(!p0) return '<div class="empty">Brak danych P0.</div>';
  const grupy = Object.entries(p0.wedlug_etykiet || {});
  const top = p0.najczestsze_frazy || [];
  return `<p class="hint">${esc(p0.zasada || 'P0 to surowe wskazówki, nie werdykt.')}</p>
    <div class="p0box"><h3>Grupy P0</h3>${grupy.length ? grupy.map(([k,v])=>`<div class="p0row"><strong>${esc(k)}</strong><span>${esc(v)}</span></div>`).join('') : '<div class="empty">Brak.</div>'}</div>
    <details class="mini"><summary>Najczęstsze frazy</summary>${top.length ? top.map(x=>`<div class="p0row"><code>${esc(x.phrase || x.fraza || '')}</code><span>${esc(x.count || x.liczba || '')}</span></div>`).join('') : '<div class="empty">Brak.</div>'}</details>
    <div class="p0-main-collapsed">${renderCollapsedP0Cards(p0.pelny_podglad || [], {title:'Pełny podgląd P0', prefix:'main_p0_preview'})}</div>`;
}

function planSekcjiHtml(uklad){
  const right = (uklad && uklad.prawy_panel) || [];
  if(!right.length) return 'Brak planu sekcji.';
  const chips = right.filter(s => Number(s?.liczba || 0) > 0).map(s => `<button type="button" class="chip section-jump" data-target-section="${esc(s.id || '')}" title="${esc(s.opis)}"><strong>${esc(s.tytul)}</strong> · ${esc(s.liczba)}</button>`).join('');
  if(!chips) return '';
  return `<div class="section-chips">${chips}</div><details class="mini stats-help"><summary>Jak czytać te liczby?</summary><p><strong>Narzędzia i statystyki</strong> to jedyny moduł liczników. Nie ma już drugiego, powielonego modułu liczników.</p><p><strong>Widok kart</strong> steruje kartami. <strong>Widok podświetleń w tekście</strong> steruje kolorami w tekście.</p></details>`;
}


// Jedyny kontroler zmiany widoku. Nie wolno go opakowywać ani nadpisywać.
function pokazWidok(widok){
  document.body.classList.remove('force-all-open');
  let key = String(widok || 'start').toLowerCase();
  const expertMode = document.body.classList.contains('expert-mode');
  if(!expertMode && typeof bezpiecznyWidokUzytkownika === 'function'){
    key = bezpiecznyWidokUzytkownika(key);
  }

  if(typeof zapamietajWidokDlaTrybu === 'function') zapamietajWidokDlaTrybu(key);
  document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === key));
  if(ostatnieDane) renderujPodgladTekstu(ostatnieDane, key === 'start' ? 'czyste' : key);

  document.querySelectorAll('[data-section]').forEach(sec => {
    const values = String(sec.dataset.section || '').split(/\s+/).filter(Boolean);
    if(key === 'start') sec.hidden = !values.some(v => STARTOWE_SEKCJE.has(v));
    else if(key === 'wszystko') sec.hidden = false;
    else sec.hidden = !values.includes(key);

    if(!sec.hidden && 'open' in sec){
      if(key === 'start') sec.open = values.some(v => ['start','czyste','jednostki'].includes(v));
      else sec.open = true;
    }
  });

  if(expertMode && typeof ustawAktywnaNawigacjeEkspercka === 'function'){
    ustawAktywnaNawigacjeEkspercka(key);
  }
  if(typeof window.aktualizujNawigacjeAktywnejSekcji === 'function'){
    window.aktualizujNawigacjeAktywnejSekcji(key);
  }
  return key;
}



function pierwszaRelacjaProdukcyjna(data){const s=(data&&data.sekcje)||{};return [...(s.relacje_wypowiedzi||[]),...(s.top_wyniki||[])].find(x=>x&&typeof x==='object')||null;}
function poleRelacji(card,keys,fallback='—'){for(const k of keys){const v=card&&card[k];if(v!==undefined&&v!==null&&String(v).trim())return String(v).trim()}return fallback}
function renderProductionRelation(data){
  const c=pierwszaRelacjaProdukcyjna(data);
  if(!c)return '<div class="empty">Nie wykryto zaakceptowanej relacji.</div>';
  const rel=c.relacja_wypowiedzi||{}, canon=c.canonical_relation||{};
  const speaker=wartoscPierwsza(rel.kto_mowi,canon.speaker,c.kto_mowi,c.mowca,c.aktor,'Nieustalony mówca');
  const action=wartoscPierwsza(canon.speaker_action,c.dzialanie,c.action,'mówi');
  const claim=wartoscPierwsza(rel.co_mowi,canon.claim,c.claim,c.fraza,c.fragment,'Brak treści');
  const target=wartoscPierwsza(rel.o_kim,canon.target,c.o_kim,c.target,rel.topic,canon.topic,'Nie wskazano');
  const medium=wartoscPierwsza(rel.medium,canon.medium,c.medium,'Nie wskazano');
  const source=wartoscPierwsza(rel.zrodlo_dokumentu,canon.document_source,rel.zrodlo,canon.source,c.zrodlo_dokumentu,'Nie wskazano');
  const typ=wartoscPierwsza(c.typ_twierdzenia,c.status,'Wypowiedź przypisana');
  return `<div class="production-relation"><dl class="production-relation-main"><div><dt>Kto mówi</dt><dd><strong>${esc(speaker)}</strong></dd><dt>Działanie</dt><dd>${esc(action)}</dd><dt>O kim / o czym</dt><dd>${esc(target)}</dd></div><div><dt>Co mówi</dt><dd>${esc(claim)}</dd><dt>Medium</dt><dd>${esc(medium)}</dd><dt>Źródło dokumentu</dt><dd>${esc(source)}</dd></div></dl><div class="production-relation-tabs"><button type="button" class="production-relation-tab active" data-rel-tab="klasyfikacja">Klasyfikacja</button><button type="button" class="production-relation-tab" data-rel-tab="dowod">Dowód</button></div><div class="production-relation-panel" data-rel-panel="klasyfikacja"><strong>Typ materiału:</strong> ${esc(typ)}</div><div class="production-relation-panel" data-rel-panel="dowod" hidden>${esc(claim)}</div></div>`;
}
function podlaczZakladkiRelacji6(){document.querySelectorAll('.production-relation-tab').forEach(btn=>btn.addEventListener('click',()=>{const k=btn.dataset.relTab;document.querySelectorAll('.production-relation-tab').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.production-relation-panel').forEach(x=>x.hidden=x.dataset.relPanel!==k)}))}
let aktywnyWidokProdukcyjny = 'wynik';
let aktywnyOpisWyniku = '';
function ustawStatusAktywnegoWyniku(opis='', aktywny=false){
  const el=$('activeResultStatus');
  if(!el) return;
  const label=String(opis||'').trim();
  aktywnyOpisWyniku = aktywny ? label : '';
  el.classList.toggle('has-result',!!aktywny);
  el.classList.toggle('no-result',!aktywny);
  el.innerHTML=aktywny
    ? `<strong>Aktywny wynik:</strong> ${esc(label || 'analiza gotowa')}`
    : '<strong>Aktywny wynik:</strong> brak. Otwórz dokument w „Baza / porównania” albo uruchom analizę tekstu.';
}
function ustawAktywnyWidokProdukcyjny(view){
  aktywnyWidokProdukcyjny = String(view || 'wynik').toLowerCase();
  document.querySelectorAll('.production-nav-btn').forEach(btn => {
    const active = btn.dataset.productionView === aktywnyWidokProdukcyjny;
    btn.classList.toggle('active', active);
    if(active) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });
}
function przewinDo(selector){
  const el = document.querySelector(selector);
  if(el) el.scrollIntoView({behavior:'smooth', block:'start'});
}
function ustawWidokBazy(active){
  const on=!!active;
  document.body.classList.toggle('database-focus-mode',on);
  const panel=$('databasePanel');
  if(on && panel){ panel.open=true; }
}

let aktywnyWidokTekstuUzytkownika = 'wszystko';
let spanyTekstuUzytkownika = [];

function wartoscPierwsza(...values){
  for(const value of values){
    if(value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return '';
}

function relacjeUzytkownika(data){
  const s=(data && data.sekcje) || {};
  const source=Array.isArray(s.relacje_wypowiedzi) ? s.relacje_wypowiedzi : [];
  const seen=new Set();
  return source.filter(card=>{
    const rel=card?.relacja_wypowiedzi || {};
    const canon=card?.canonical_relation || {};
    const key=wartoscPierwsza(card?.relation_id,canon?.relation_id,`${rel.kto_mowi||card?.kto_mowi||''}|${rel.co_mowi||card?.fraza||card?.fragment||''}|${rel.o_kim||card?.o_kim||''}`);
    if(seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function topUzytkownika(data){
  const units=Array.isArray(data?.jednostki_znaczenia) ? data.jednostki_znaczenia : [];
  if(units.length) return units.slice();
  const cards=Array.isArray(data?.sekcje?.top_wyniki) ? data.sekcje.top_wyniki : [];
  return cards.map((card,i)=>{
    const rel=card?.relacja_wypowiedzi || {};
    const canon=card?.canonical_relation || {};
    return {
      id:`TOP-${i+1}`,
      tytul:card?.tytul || `TOP #${i+1}`,
      fragment:wartoscPierwsza(rel.co_mowi,canon.claim,card?.fraza,card?.fragment),
      mowca:wartoscPierwsza(rel.kto_mowi,canon.speaker,card?.kto_mowi),
      target:wartoscPierwsza(rel.o_kim,canon.target,card?.o_kim),
      temat:wartoscPierwsza(rel.topic,canon.topic,card?.temat),
      medium:wartoscPierwsza(rel.medium,canon.medium,card?.medium),
      zrodlo:wartoscPierwsza(rel.zrodlo,canon.source,card?.zrodlo_przywolane),
      zrodlo_dokumentu:wartoscPierwsza(rel.zrodlo_dokumentu,canon.document_source,card?.zrodlo_dokumentu),
      pewnosc_relacji:wartoscPierwsza(canon.confidence,card?.pewnosc),
      poczatek:card?.poczatek,
      koniec:card?.koniec,
      highlight_id:card?.highlight_id,
      link_status:card?.link_status
    };
  });
}

function przyciskPokazWTekscie(card, widok='wszystko'){
  const start=Number(card?.poczatek);
  const end=Number(card?.koniec);
  const linked=Number.isFinite(start) && Number.isFinite(end) && end>start;
  if(!linked) return '';
  return `<div class="user-result-actions"><button type="button" class="secondary user-show-hit" data-user-hit-view="${esc(widok)}" data-highlight-id="${esc(card?.highlight_id||'')}" data-start="${start}" data-end="${end}">Pokaż w tekście</button></div>`;
}

function kartaTopUzytkownika(item,index){
  const canon=item?.canonical_relation || {};
  const speaker=wartoscPierwsza(item?.mowca,item?.aktor,canon.speaker);
  const claim=wartoscPierwsza(item?.claim,item?.fragment,canon.claim);
  const target=wartoscPierwsza(item?.target,item?.temat,item?.dotyczy,canon.target,canon.topic);
  const source=wartoscPierwsza(item?.zrodlo_dokumentu,item?.zrodlo,item?.medium,canon.document_source,canon.source,canon.medium);
  const confidence=wartoscPierwsza(item?.pewnosc_relacji,canon.confidence);
  return `<article class="user-result-card">
    <h3>${esc(item?.tytul || `TOP #${index+1}`)}</h3>
    ${speaker ? `<p><strong>${esc(speaker)}</strong></p>` : ''}
    <p>${esc(claim || 'Brak treści relacji.')}</p>
    ${target ? `<div class="user-target"><strong>Dotyczy:</strong> ${esc(target)}</div>` : ''}
    <div class="user-result-meta">${source ? `<span>źródło: ${esc(source)}</span>` : ''}${confidence ? `<span>pewność: ${esc(confidence)}</span>` : ''}</div>
    ${przyciskPokazWTekscie(item,'czyste')}
  </article>`;
}

function kartaRelacjiUzytkownika(card,index){
  const rel=card?.relacja_wypowiedzi || {};
  const canon=card?.canonical_relation || {};
  const speaker=wartoscPierwsza(rel.kto_mowi,canon.speaker,card?.kto_mowi,'Nieustalony mówca');
  const action=wartoscPierwsza(canon.speaker_action,card?.dzialanie,'mówi');
  const claim=wartoscPierwsza(rel.co_mowi,canon.claim,card?.fraza,card?.fragment,'Brak treści');
  const target=wartoscPierwsza(rel.o_kim,canon.target,card?.o_kim,rel.topic,canon.topic);
  const medium=wartoscPierwsza(rel.medium,canon.medium,card?.medium);
  const source=wartoscPierwsza(rel.zrodlo_dokumentu,canon.document_source,rel.zrodlo,canon.source,card?.zrodlo_dokumentu,card?.zrodlo_przywolane);
  const confidence=wartoscPierwsza(canon.confidence,card?.pewnosc);
  return `<article class="user-result-card">
    <div class="user-relation-line"><strong>${esc(speaker)}</strong><span class="user-relation-arrow">→ ${esc(action)} →</span><span>${esc(claim)}</span></div>
    ${target ? `<div class="user-target"><strong>O kim / o czym:</strong> ${esc(target)}</div>` : ''}
    <div class="user-result-meta"><span>#${index+1}</span>${medium ? `<span>medium: ${esc(medium)}</span>` : ''}${source ? `<span>źródło: ${esc(source)}</span>` : ''}${confidence ? `<span>pewność: ${esc(confidence)}</span>` : ''}</div>
    ${przyciskPokazWTekscie(card,'relacje')}
  </article>`;
}

function renderujWynikUzytkownika(data){
  const box=$('userResultWynik'); if(!box) return;
  if(!data || data.sugestie){
    box.innerHTML='<div class="user-empty-state"><strong>Brak aktywnej analizy.</strong><span>Otwórz dokument z bazy albo uruchom analizę tekstu.</span></div>';
    return;
  }
  const s=data.sekcje||{};
  const rels=relacjeUzytkownika(data);
  const top=topUzytkownika(data);
  const actors=Array.isArray(s.mapa_aktorow)?s.mapa_aktorow:[];
  const review=rels.filter(x=>Boolean(x?.wymaga_przegladu)).length;
  const report=data.raport_czytelny||{};
  const items=Array.isArray(report.items)?report.items:[];
  const conclusions=items.slice(0,5).map((it,i)=>`<article class="user-result-card"><h3>${esc(it?.tytul||`Wniosek ${i+1}`)}</h3><p>${esc(it?.wartosc||it?.opis||'Brak opisu.')}</p>${it?.opis&&it?.wartosc?`<div class="user-target">${esc(it.opis)}</div>`:''}</article>`).join('');
  const preview=rels.slice(0,3).map((r,i)=>kartaRelacjiUzytkownika(r,i)).join('');
  box.innerHTML=`<div class="user-result-head"><div><h2>Wynik analizy</h2><p>Najważniejsze informacje z aktywnego dokumentu.</p></div></div>
    <div class="user-metrics"><div class="user-metric"><strong>${rels.length}</strong><span>relacji</span></div><div class="user-metric"><strong>${top.length}</strong><span>TOP</span></div><div class="user-metric"><strong>${actors.length}</strong><span>aktorów</span></div><div class="user-metric"><strong>${review}</strong><span>do kontroli</span></div></div>
    ${conclusions || '<div class="user-section-note">Brak dodatkowego raportu opisowego. Relacje i TOP są dostępne w osobnych kartach.</div>'}
    ${preview ? `<div class="user-section-note"><strong>Najważniejsze relacje</strong> — poniżej trzy pierwsze. Pełna lista jest w zakładce „Relacje”.</div>${preview}` : ''}`;
}

function renderujTopUzytkownika(data){
  const box=$('userResultTop'); if(!box) return;
  const top=topUzytkownika(data);
  box.innerHTML=top.length
    ? `<div class="user-result-head"><div><h2>TOP</h2><p>${top.length} najważniejszych jednostek znaczenia bez technicznego menu sekcji.</p></div></div>${top.map(kartaTopUzytkownika).join('')}`
    : '<div class="user-empty-state"><strong>Brak TOP w tym wyniku.</strong><span>Dokument został otwarty, ale analiza nie zwróciła jednostek TOP.</span></div>';
}

function renderujRelacjeUzytkownika(data){
  const box=$('userResultRelacje'); if(!box) return;
  const rels=relacjeUzytkownika(data);
  box.innerHTML=rels.length
    ? `<div class="user-result-head"><div><h2>Relacje</h2><p>${rels.length} zaakceptowanych relacji: kto mówi → co mówi → o kim/o czym.</p></div></div>${rels.map(kartaRelacjiUzytkownika).join('')}`
    : '<div class="user-empty-state"><strong>Brak zaakceptowanych relacji.</strong><span>Ten dokument nie ma relacji spełniających aktualne bramki analizy.</span></div>';
}

function pokazSzczegolyTekstuUzytkownika(el){
  const detail=$('userTextDetails'); if(!detail) return;
  document.querySelectorAll('#userTextPreview .hl.active').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  const idx=Number(el.dataset.userHitIndex ?? el.dataset.hitIndex ?? -1);
  const span=spanyTekstuUzytkownika[idx];
  if(!span){ detail.textContent='Oznaczony fragment tekstu.'; return; }
  detail.innerHTML=`<strong>${esc(span.poziom||'')} · ${esc(span.tytul||'Trafienie')}</strong>${span.fraza?`<div>fraza: <code>${esc(span.fraza)}</code></div>`:''}${span.uzasadnienie?`<div>${esc(span.uzasadnienie)}</div>`:''}`;
}

function renderujTekstUzytkownika(data,widok='wszystko'){
  const box=$('userTextPreview'), detail=$('userTextDetails'); if(!box) return;
  aktywnyWidokTekstuUzytkownika=String(widok||'wszystko').toLowerCase();
  document.querySelectorAll('.user-text-filter').forEach(btn=>btn.classList.toggle('active',btn.dataset.userTextView===aktywnyWidokTekstuUzytkownika));
  const active=aktualnyWidokPodgladu(data,aktywnyWidokTekstuUzytkownika);
  spanyTekstuUzytkownika=active&&Array.isArray(active.spany)?active.spany:[];
  const text=String(data?.podglad_tekstu?.tekst || ($('textInput')?.value||''));
  box.innerHTML=text ? renderujHtmlZPodswietleniami(text,spanyTekstuUzytkownika) : 'Brak tekstu w aktywnym wyniku.';
  box.querySelectorAll('.hl').forEach((el,i)=>{el.dataset.userHitIndex=String(i);el.addEventListener('click',()=>pokazSzczegolyTekstuUzytkownika(el));});
  if(detail) detail.textContent=`Widok: ${etykietaWidoku(aktywnyWidokTekstuUzytkownika)} · oznaczone fragmenty: ${spanyTekstuUzytkownika.length}.`;
}

function podlaczAkcjeWynikuUzytkownika(){
  document.querySelectorAll('.user-show-hit').forEach(btn=>{
    if(btn.dataset.bound==='1') return; btn.dataset.bound='1';
    btn.addEventListener('click',()=>{
      pokazPanelUzytkownika('tekst');
      renderujTekstUzytkownika(ostatnieDane,btn.dataset.userHitView||'wszystko');
      const list=[...document.querySelectorAll('#userTextPreview .hl')];
      const hid=String(btn.dataset.highlightId||'');
      const start=Number(btn.dataset.start), end=Number(btn.dataset.end);
      const hit=list.find(el=>(hid&&String(el.id||'')===hid)||(Number(el.dataset.start)===start&&Number(el.dataset.end)===end));
      if(hit){ pokazSzczegolyTekstuUzytkownika(hit); hit.scrollIntoView({behavior:'smooth',block:'center'}); }
    });
  });
}

function renderujPaneleUzytkownika(data){
  renderujWynikUzytkownika(data);
  renderujTopUzytkownika(data);
  renderujRelacjeUzytkownika(data);
  renderujTekstUzytkownika(data,aktywnyWidokTekstuUzytkownika||'wszystko');
  podlaczAkcjeWynikuUzytkownika();
}

function pokazPanelUzytkownika(view){
  const allowed=new Set(['wynik','top','relacje','tekst']);
  const key=allowed.has(String(view||'').toLowerCase())?String(view).toLowerCase():'wynik';
  ustawAktywnyWidokProdukcyjny(key);
  document.querySelectorAll('[data-user-result-panel]').forEach(panel=>{
    const active=panel.dataset.userResultPanel===key;
    panel.hidden=!active;
    panel.classList.toggle('active',active);
  });
  if(key==='tekst' && ostatnieDane) renderujTekstUzytkownika(ostatnieDane,aktywnyWidokTekstuUzytkownika||'wszystko');
  podlaczAkcjeWynikuUzytkownika();
  return key;
}

function pokazWidokProdukcyjny6(v){
  const view = String(v || 'wynik').toLowerCase();
  ustawAktywnyWidokProdukcyjny(view);
  if(view !== 'baza') ustawWidokBazy(false);
  if(view === 'ekspert'){
    zastosujTrybInterfejsu('ekspert');
    zastosujUkladPracy('wynik');
    pokazWidok('p0');
    przewinDo('#analystPane');
    return;
  }
  zastosujTrybInterfejsu('uzytkownik',{restoreView:false});
  if(view === 'baza'){
    zastosujUkladPracy('podzial');
    ustawWidokBazy(true);
    const panel=$('databasePanel'); if(panel) panel.scrollIntoView({behavior:'smooth',block:'start'});
    void odswiezBazeDokumentow();
    return;
  }
  zastosujUkladPracy('wynik');
  pokazPanelUzytkownika(view);
  przewinDo('#analystPane');
}

function renderujRaportDruku(data){
  const el = $('printReport');
  if(!el) return;
  if(!data || data.sugestie){ el.innerHTML=''; return; }
  const s = data.sekcje || {};
  const p = data.podsumowanie || {};
  const relacje = Array.isArray(s.relacje_wypowiedzi) ? s.relacje_wypowiedzi : [];
  const top = Array.isArray(data.jednostki_znaczenia) ? data.jednostki_znaczenia.slice(0,5) : [];
  const review = relacje.filter(x => x && x.wymaga_przegladu).length;
  const linkedTop = top.filter(x => x && x.relation_id && x.link_status === 'linked').length;
  const cards = top.map((u,i) => {
    const who = u.mowca || u.aktor || u.zrodlo || 'Nieustalony autor';
    const claim = u.claim || u.fragment || '';
    const about = u.target || u.temat || u.dotyczy || '';
    const source = u.zrodlo || u.zrodlo_dokumentu || u.medium || '';
    return `<article class="print-top-card">
      <div class="print-top-index">${i+1}</div>
      <div><h2>${esc(who)}</h2>
      <p class="print-claim">${esc(claim)}</p>
      <dl>${about ? `<div><dt>Dotyczy</dt><dd>${esc(about)}</dd></div>` : ''}${source ? `<div><dt>Źródło</dt><dd>${esc(source)}</dd></div>` : ''}<div><dt>Pewność</dt><dd>${esc(u.pewnosc_relacji || '—')}${u.wymaga_przegladu ? ' · do kontroli' : ''}</dd></div></dl></div>
    </article>`;
  }).join('');
  const runId = data.analysis_run_id || 'brak-identyfikatora';
  el.innerHTML = `<header class="print-report-head"><div><p class="print-kicker">DROGOWSKAZY · RAPORT MOBILNY</p><h1>Wynik analizy tekstu</h1></div><span>${esc(data.wersja_aplikacji || '')}</span></header>
    <div class="print-run">Analiza: <strong>${esc(runId)}</strong></div>
    <section class="print-metrics">
      <div><strong>${esc(p.dokumenty || 0)}</strong><span>dokumentów</span></div>
      <div><strong>${esc(relacje.length)}</strong><span>relacji</span></div>
      <div><strong>${esc(top.length)}</strong><span>TOP</span></div>
      <div><strong>${esc(review)}</strong><span>do kontroli</span></div>
    </section>
    <div class="print-integrity ${linkedTop === top.length && top.length ? 'ok' : 'warn'}">TOP z dowodem: ${linkedTop}/${top.length} · JSON i PDF: ten sam przebieg ${esc(runId)}</div>
    <section class="print-top-list"><h2>Najważniejsze relacje</h2>${cards || '<p>Brak relacji TOP.</p>'}</section>
    <footer>Wynik automatyczny wspierający analityka. Pozycje „do kontroli” wymagają sprawdzenia w tekście źródłowym.</footer>`;
}

function renderuj(data){
  ostatnieDane = data;
  const activeStatus=$('activeResultStatus');
  if(activeStatus && !activeStatus.classList.contains('has-result')) ustawStatusAktywnegoWyniku('wynik analizy', true);
  renderujRaportDruku(data);
  zaplanujZapisSesji(80);
  ostatniEksport = null;
  $('sectionPlanBox').innerHTML = planSekcjiHtml(data.uklad_sekcji);
  podlaczSkokiSekcji();
  $('summary').innerHTML = kratkaPodsumowania(data.podsumowanie || {}) + `<p class="hint">${esc(data.polityka || '')}</p>`;
  const readableEl = $('readableReportSection');
  if(readableEl) readableEl.innerHTML = renderCzytelnyRaport(data.raport_czytelny || {});
  const meaningEl = $('meaningUnitsSection');
  if(meaningEl) meaningEl.innerHTML = renderMeaningUnits(data.jednostki_znaczenia || []);
  aktualizujPodsumowanie30Sekund(data);
  const prodRelEl=$('productionRelationSection'); if(prodRelEl){prodRelEl.innerHTML=renderProductionRelation(data);podlaczZakladkiRelacji6();}
  $('reportBox').textContent = data.raport_roboczy || 'Raport pojawi się po analizie.';

  if(data.sugestie){
    $('p0Section').innerHTML = p0Html(data.p0);
    $('p1Section').innerHTML = '<div class="empty">W trybie sugestii P1 nie jest główną sekcją.</div>';
    $('p2Section').innerHTML = '<div class="empty">W trybie sugestii P2 nie jest główną sekcją.</div>';
    $('candidatesSection').innerHTML = '<div class="empty">Kandydaci są pokazani wewnątrz sugestii, jeśli występują.</div>';
    ['readableReportSection','meaningUnitsSection','cleanTopSection','actorMapSection','agencyMapSection','factOpinionQuoteSection','statementRelationsSection','roleAuditSection','semanticEffectivenessSection','visibilityAuditSection','gatesAuditSection'].forEach(id => { const el=$(id); if(el) el.innerHTML = '<div class="empty">Ta sekcja jest dostępna w trybie analizy.</div>'; });
    $('suggestionsSection').innerHTML = `<p class="hint">Sugestie są pomocą analityczną. Nie są werdyktem i nie zastępują decyzji P1.</p>${listaKart(data.sugestie)}`;
    podlaczNawigacjeKart();
    renderujPaneleUzytkownika(data);
    renderujPodgladTekstu(data, 'wszystko');
    if(document.body.dataset.interfaceMode === 'ekspert') pokazWidok('sugestie');
    else pokazPanelUzytkownika('wynik');
    return;
  }

  const s = data.sekcje || {};
  $('p0Section').innerHTML = p0Html(data.p0);
  ustawSekcje('p1Section', listaKart(s.potwierdzone_p1, '', {hideEmpty:true}), Array.isArray(s.potwierdzone_p1) && s.potwierdzone_p1.length > 0);
  ustawSekcje('p2Section', listaKart(s.techniki_p2, '', {hideEmpty:true}), Array.isArray(s.techniki_p2) && s.techniki_p2.length > 0);
  $('candidatesSection').innerHTML = `<h3>Kandydaci struktur</h3>${listaKart(s.kandydaci_struktur)}<h3>Kandydaci semantyczni</h3>${listaKart(s.kandydaci_semantyczni)}<h3>Zablokowane przez bramki</h3>${listaKart(s.zablokowane_przez_bramki)}`;
  const cleanTopEl = $('cleanTopSection');
  if(cleanTopEl) cleanTopEl.innerHTML = `<p class="hint">Czyste TOP pokazuje przekrój najważniejszych wyników bez dublowania pełnych list semantycznych.</p>${renderCleanTopSemantic(s)}`;
  const actorEl = $('actorMapSection');
  if(actorEl) actorEl.innerHTML = `<p class="hint">Mapa aktorów jest zwinięta do ról: osoby, instytucje, media/źródła, obiekty sprawy. Pełne szczegóły otwierają się jednym przyciskiem.</p>${renderCollapsedActorMap(s.mapa_aktorow, [], {title:'Mapa aktorów', prefix:'main_actor_map'})}`;
  const agencyEl = $('agencyMapSection');
  if(agencyEl) agencyEl.innerHTML = `<p class="hint">Mapa sprawczości: jedna relacyjna mapa kto → robi → co, bez wielu mini-map jedna pod drugą.</p>${renderCollapsedAgencyMap(s.mapa_sprawczosci, {title:'Mapa sprawczości', prefix:'main_agency_map'})}`;
  const factEl = $('factOpinionQuoteSection');
  if(factEl) factEl.innerHTML = `<p class="hint">Fakt/opinia/cytat w trybie kompaktowym: najpierw typy i liczby, pełne karty dopiero po kliknięciu.</p>${renderListaRCompactSummary(s.fact_opinia_cytat, {level:'R2/R3', title:'Fakt / opinia / cytat', empty:'Brak statusów fakt/opinia/cytat.'})}`;
  const relationEl = $('statementRelationsSection');
  if(relationEl) relationEl.innerHTML = `<p class="hint">Relacje wypowiedzi są najpierw krótką listą kto → o kim → co mówi. Pełne fragmenty są po drugim kliknięciu.</p>${renderCollapsedAgencyMap(s.relacje_wypowiedzi, {title:'Relacje wypowiedzi', prefix:'statement_rel_compact'})}`;
  const semanticEl = $('semanticEffectivenessSection');
  if(semanticEl) semanticEl.innerHTML = `<p class="hint">Audyt rozdziela integralność techniczną od skuteczności mierzonej benchmarkiem GOLD. Grupy wyników i szczegóły pozostają w jednym poziomie.</p>${renderSemanticEffectivenessPanel(s)}`;
  const roleAuditEl = $('roleAuditSection');
  if(roleAuditEl) roleAuditEl.innerHTML = `<p class="hint">Audyt ról sprawdza, czy TOP i relacje nie mylą osoby mówiącej, medium, programu, obiektu wypowiedzi i sprawcy działania.</p>${listaKart(s.audyt_rol_relacji, 'Brak audytu ról relacji.', {hideEmpty:true, showTechnical:true})}`;
  const visibilityEl = $('visibilityAuditSection');
  if(visibilityEl) visibilityEl.innerHTML = `<p class="hint">Audyt widoczności pokazuje TOP, sekcje, karty bez przycisku „Pokaż w tekście” i szacunkowe ukrycie przez UI.</p>${listaKart(s.audyt_widocznosci, 'Brak audytu widoczności.', {hideEmpty:true, showTechnical:true})}`;
  const gatesEl = $('gatesAuditSection');
  if(gatesEl) gatesEl.innerHTML = `<p class="hint">Audyt bramek odróżnia blokadę przez bramkę od degradacji do kandydata i nieawansu P0. Dzięki temu widać, czy kod coś odrzucił, czy tylko nie pokazał jako decyzji.</p>${listaKart(s.audyt_bramek_degradacji, 'Brak audytu bramek/degradacji.', {hideEmpty:true, showTechnical:true})}`;
  $('suggestionsSection').innerHTML = '<div class="hint-box">Kliknij „Szukaj sugestii”, żeby wypełnić tę sekcję zbiorczymi wskazówkami. Sugestie pojawią się po uruchomieniu osobnego trybu sugestii.</div>';
  podlaczNawigacjeKart();
  renderujPaneleUzytkownika(data);
  // Ekspert zachowuje dawny pełny panel sekcji. Użytkownik korzysta z czterech prostych, niezależnych widoków.
  if(document.body.dataset.interfaceMode === 'ekspert') pokazWidok('start');
  else pokazPanelUzytkownika(aktywnyWidokProdukcyjny === 'baza' ? 'wynik' : aktywnyWidokProdukcyjny);
  renderujPodgladTekstu(data, 'wszystko');
}

function podlaczSkokiSekcji(){
  document.querySelectorAll('.section-jump').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.targetSection || '';
      const mapa = {
        narzedzia_i_statystyki: 'narzedziaCard', jednostki: 'meaningUnitsCard', jednostki_znaczenia: 'meaningUnitsCard', top_relacji: 'meaningUnitsCard',
        p0_wskazniki: 'p0Card', czyste: 'cleanTopCard', fact_opinia_cytat: 'factOpinionQuoteCard', p1_struktury: 'p1Card',
        relacje_wypowiedzi: 'statementRelationsCard', p2_techniki: 'p2Card', p3_ramy: 'p2Card', p4_strategie: 'p2Card', p5_diagnozy: 'p2Card',
        kandydaci: 'kandydaciCard', aktorzy_sprawczosc: 'sprawczoscCard', mapa_aktorow: 'aktorzyCard', mapa_zrodel: 'aktorzyCard', mapa_sprawczosci: 'sprawczoscCard',
        sugestie: 'sugestieCard', raport: 'raportCard',
        audyt_widocznosci: 'visibilityAuditCard', audyt_bramek_degradacji: 'gatesAuditCard', bramki: 'gatesAuditCard', audyt_rol_relacji: 'roleAuditCard', audytrole: 'roleAuditCard'
      };
      const el = document.getElementById(mapa[id] || '');
      if(el){ el.hidden = false; if('open' in el) el.open = true; el.scrollIntoView({behavior:'smooth', block:'start'}); }
    });
  });
}

async function wyslij(url){
  ostatniZbiorczyPayload = null;
  zbiorczeDokumentyMap = {};
  const tekst = $('textInput').value || '';
  if(!tekst.trim()){
    const komunikat = 'Pole tekstu jest puste. Wklej lub wczytaj materiał przed analizą.';
    $('summary').innerHTML = `<div class="file-load-error"><strong>Analiza nie została wykonana.</strong><br>${esc(komunikat)}</div>`;
    ustawStatusPliku(komunikat, true);
    return null;
  }
  const nazwaOperacji = url === '/api/sugestie' ? 'Szukanie sugestii' : 'Analiza materiału';
  const tokenPostepu = startPostepuSerwera(nazwaOperacji, tekst);
  $('summary').innerHTML = '<p class="hint">Analizuję...</p>';
  try{
    const data = await pobierzJson(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tekst})}, 'Analiza');
    renderuj(data);
    ustawStatusAktywnegoWyniku(url === '/api/sugestie' ? 'sugestie dla bieżącego tekstu' : 'bieżący tekst / plik', true);
    if(url !== '/api/sugestie' && document.body.dataset.interfaceMode !== 'ekspert') pokazWidokProdukcyjny6('wynik');
    const relacje = Array.isArray(data && data.relacje_wypowiedzi) ? data.relacje_wypowiedzi.length : null;
    zakonczPostepOperacji(tokenPostepu, 'Gotowe', relacje === null ? 'Wynik został odebrany i wyświetlony.' : `Wynik odebrany · ${relacje} relacji.`);
    return data;
  }catch(err){
    const msg = err && err.message ? err.message : 'Nie udało się uruchomić analizy.';
    $('summary').innerHTML = `<div class="file-load-error"><strong>Analiza nie została wykonana.</strong><br>${esc(msg)}</div>`;
    ustawStatusPliku(`Błąd analizy: ${msg}`, true);
    bladPostepuOperacji(tokenPostepu, 'Analiza przerwana', msg);
    console.error('Drogowskazy /api analysis error', err);
    return null;
  }
}


let ostatniEksport = null;

async function pobierzEksportRaportu(){
  if(ostatnieDane && ostatnieDane.aggregate_from_database){
    const compact = ostatniZbiorczyPayload || ostatnieDane;
    ostatniEksport = {
      ok:true,
      analysis_run_id: ostatnieDane.analysis_run_id || '',
      analysis_input_sha256: 'database-aggregate-no-single-input',
      raport_json: compact,
      raport_markdown: ostatnieDane.raport_roboczy || '',
      raport_szczegolowy_markdown: ostatnieDane.raport_roboczy || ''
    };
    return ostatniEksport;
  }
  const tekst = $('textInput').value || '';
  if(!tekst.trim()){
    const komunikat = 'Nie można wygenerować raportu z pustego pola tekstowego. Przywróć analizowany tekst albo uruchom nową analizę.';
    if($('reportBox')) $('reportBox').textContent = komunikat;
    ustawStatusPliku(komunikat, true);
    return null;
  }
  const tokenPostepu = startPostepuSerwera('Generowanie raportu', tekst);
  try{
    const requestedRunId = ostatnieDane && ostatnieDane.analysis_run_id ? ostatnieDane.analysis_run_id : '';
    const received = await pobierzJson('/api/raport', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tekst, analysis_run_id: requestedRunId})}, 'Eksport raportu');
    const exportedData = received && received.raport_json ? received.raport_json : null;
    // Po restarcie backendu zapisany lokalnie run może zniknąć z pamięci serwera.
    // W takim przypadku serwer zwraca nowy, kompletny przebieg. UI przełącza się
    // na niego, dzięki czemu ekran, JSON i późniejszy PDF nadal są identyczne.
    if(exportedData && (!ostatnieDane || exportedData.analysis_run_id !== ostatnieDane.analysis_run_id)){
      renderuj(exportedData);
    }
    ostatniEksport = received;
    zaplanujZapisSesji(80);
    if(ostatniEksport && (ostatniEksport.raport_szczegolowy_markdown || ostatniEksport.raport_markdown)){
      $('reportBox').textContent = ostatniEksport.raport_szczegolowy_markdown || ostatniEksport.raport_markdown;
    }
    zakonczPostepOperacji(tokenPostepu, 'Raport gotowy', 'Markdown / JSON zostały przygotowane.');
    return ostatniEksport;
  }catch(err){
    ostatniEksport = null;
    const msg = err && err.message ? err.message : 'Nie udało się pobrać raportu.';
    if($('reportBox')) $('reportBox').textContent = `Raport nie został wygenerowany. ${msg}`;
    ustawStatusPliku(`Błąd raportu: ${msg}`, true);
    bladPostepuOperacji(tokenPostepu, 'Raport przerwany', msg);
    console.error('Drogowskazy /api/raport error', err);
    return null;
  }
}

async function tekstRaportuMarkdown(){
  if(!ostatniEksport || !ostatniEksport.raport_markdown){
    await pobierzEksportRaportu();
  }
  return (ostatniEksport && ostatniEksport.raport_markdown) || '';
}

function pobierzPlik(nazwa, tresc, typ){
  if(window.DrogowskazyAndroid && typeof window.DrogowskazyAndroid.saveText === 'function'){
    window.DrogowskazyAndroid.saveText(String(nazwa), String(tresc), typ || 'text/plain;charset=utf-8');
    return;
  }
  const blob = new Blob([tresc], {type: typ || 'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nazwa;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 250);
}

async function kopiujRaport(){
  const txt = await tekstRaportuMarkdown();
  if(!txt) return;
  try{
    if(window.DrogowskazyAndroid && typeof window.DrogowskazyAndroid.copyText === 'function'){
      window.DrogowskazyAndroid.copyText(txt);
    }else{
      await navigator.clipboard.writeText(txt);
    }
    $('reportBox').textContent = txt + '\n\n[Skopiowano raport Markdown do schowka.]';
  }catch(e){
    $('reportBox').textContent = txt + '\n\n[Nie udało się użyć schowka w tej przeglądarce. Zaznacz tekst ręcznie.]';
  }
}

async function pobierzMarkdown(){
  const txt = await tekstRaportuMarkdown();
  if(!txt) return;
  pobierzPlik('drogowskazy_raport.md', txt, 'text/markdown;charset=utf-8');
}

async function pobierzJsonRaportu(){
  if(!ostatniEksport){ await pobierzEksportRaportu(); }
  if(!ostatniEksport) return;
  const payload = ostatniEksport.raport_json || ostatniEksport;
  pobierzPlik('drogowskazy_raport.json', JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
}


function bezpiecznyZnacznikCzasu(){
  return new Date().toISOString().replace(/[:.]/g,'-');
}

async function pobierzPelneWyniki(){
  if(!ostatnieDane){
    ustawStatusSesji('Najpierw uruchom „Analizuj”, potem pobierz wyniki.', 'error');
    return;
  }
  if(ostatnieDane.aggregate_from_database){
    const sourceOfTruth = ostatniZbiorczyPayload || ostatnieDane;
    const payload = {
      format: 'drogowskazy-database-aggregate-v1',
      exported_at: new Date().toISOString(),
      analysis_run_id: sourceOfTruth.analysis_run_id || null,
      stage: sourceOfTruth.stage || sourceOfTruth.etap || null,
      documents_count: Number(sourceOfTruth?.database_stats?.used_done_results || Object.keys(sourceOfTruth.zbiorcze_dokumenty||{}).length || 0),
      wynik_zbiorczy: sourceOfTruth
    };
    pobierzPlik(`drogowskazy_baza_wynik_zbiorczy_${bezpiecznyZnacznikCzasu()}.json`, JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
    ustawStatusSesji('Pobrano jeden zbiorczy JSON ze wszystkich zapisanych analiz.', 'saved');
    return;
  }
  const tekstBiezacy = String(($('textInput') && $('textInput').value) || '');
  if(!tekstBiezacy.trim()){
    ustawStatusSesji('Pole tekstu jest puste. Nie eksportuję wyniku, żeby nie stworzyć raportu dla pustego wsadu.', 'error');
    return;
  }
  let eksport = ostatniEksport;
  const currentRunId = ostatnieDane && ostatnieDane.analysis_run_id;
  if(!eksport || !currentRunId || eksport.analysis_run_id !== currentRunId) eksport = await pobierzEksportRaportu();
  if(!eksport) return;
  const sourceOfTruth = eksport.raport_json || ostatnieDane;
  const payload = {
    format: 'drogowskazy-full-result-v1',
    exported_at: new Date().toISOString(),
    analysis_run_id: sourceOfTruth && sourceOfTruth.analysis_run_id ? sourceOfTruth.analysis_run_id : null,
    stage: sourceOfTruth && (sourceOfTruth.stage || sourceOfTruth.etap) ? (sourceOfTruth.stage || sourceOfTruth.etap) : null,
    tekst_wejsciowy: String(($('textInput') && $('textInput').value) || ''),
    wynik_analizy: sourceOfTruth,
    raport: eksport || null
  };
  pobierzPlik(`drogowskazy_wyniki_${bezpiecznyZnacznikCzasu()}.json`, JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
  ustawStatusSesji('Pobrano pełne wyniki JSON. Do PDF użyj „Drukuj / PDF”.', 'saved');
  void zapiszSesjeTeraz('download-results');
}

async function drukujLubZapiszPdf(){
  if(!ostatnieDane){
    ustawStatusSesji('Najpierw uruchom „Analizuj”, potem zapisz PDF.', 'error');
    return;
  }
  const currentRunId = ostatnieDane.analysis_run_id || '';
  if(!ostatnieDane.aggregate_from_database && (!ostatniEksport || ostatniEksport.analysis_run_id !== currentRunId)){
    const got = await pobierzEksportRaportu();
    if(!got) return;
  }
  renderujRaportDruku(ostatnieDane);
  void zapiszSesjeTeraz('before-print');
  window.print();
}



// Wczytywanie plików tekstowych po stronie przeglądarki.
let trybWczytywaniaPliku = 'replace';
const DOZWOLONE_ROZSZERZENIA_PLIKOW = ['txt','md','markdown','csv','json','log','html','htm'];
const MAKSYMALNY_ROZMIAR_PLIKU = 2 * 1024 * 1024; // limit pojedynczego pliku wejściowego.
const MAKSYMALNY_ROZMIAR_PAKIETU = 1800 * 1024; // zapas pod JSON przed backendowym limitem 2 MB/request.
const ZALECANY_ROZMIAR_PAKIETU = 128 * 1024; // próg ostrzegawczy z lokalnego stress-testu relacyjnego.
const ZALECANA_LICZBA_DOKUMENTOW = 50;
const OBSLUGIWANE_ROZSZERZENIA = new Set(['txt','md','markdown','csv','json','log','html','htm']);

function bajtyUtf8(text){
  try{return new TextEncoder().encode(String(text || '')).length;}catch(_){return unescape(encodeURIComponent(String(text || ''))).length;}
}

function czyObslugiwanyPlik(file){
  if(!file || !file.name) return false;
  const ext = String(file.name).toLowerCase().split('.').pop();
  return OBSLUGIWANE_ROZSZERZENIA.has(ext);
}

function ustawStatusPliku(tekst, blad=false){
  const el = $('fileLoadStatus');
  if(!el) return;
  el.textContent = tekst;
  el.classList.toggle('file-load-error', !!blad);
  el.classList.toggle('file-load-ok', !blad && tekst && !tekst.startsWith('Obsługiwane'));
}

function rozszerzeniePliku(nazwa){
  const parts = String(nazwa || '').toLowerCase().split('.');
  return parts.length > 1 ? parts.pop() : '';
}

function walidujPlikTekstowy(file){
  if(!file) return 'Nie wybrano pliku.';
  const ext = rozszerzeniePliku(file.name);
  const typ = String(file.type || '').toLowerCase();
  const typTekstowy = typ.startsWith('text/') || typ.includes('json') || typ === '';
  if(!DOZWOLONE_ROZSZERZENIA_PLIKOW.includes(ext) && !typTekstowy){
    return 'Ten typ pliku nie jest obsługiwany. Użyj .txt, .md, .csv, .json, .log albo .html.';
  }
  if(file.size > MAKSYMALNY_ROZMIAR_PLIKU){
    return `Plik jest za duży (${Math.round(file.size/1024)} KB). Limit: ${Math.round(MAKSYMALNY_ROZMIAR_PLIKU/1024)} KB.`;
  }
  return '';
}

function naprawMojibakePolski(value){
  const mapa = {'å':'ć','Å':'Ć','ê':'ł','Ê':'Ł','Ñ':'ą','ñ':'ą','®':'ę','¥':'ż','©':'ę','õ':'ń','Õ':'Ń','¿':'ż','¯':'Ż','ÿ':'ś','Ÿ':'Ś','\uFFFE':'-','\uFFFF':'-'};
  return String(value || '').replace(/[åÅêÊÑñ®¥©õÕ¿¯ÿŸ\uFFFE\uFFFF]/g, ch => mapa[ch] || ch);
}

function ocenaDekodowania(value){
  const s = String(value || '');
  const replacement = (s.match(/�/g) || []).length * 20;
  const mojibake = (s.match(/[åÅêÊÑñ®¥©õÕ¿¯ÿŸ\uFFFE\uFFFF]/g) || []).length * 6;
  const controls = (s.match(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g) || []).length * 10;
  return replacement + mojibake + controls;
}

function dekodujPlikTekstowy(buffer){
  const bytes = new Uint8Array(buffer);
  const warianty = [];
  for(const encoding of ['utf-8','windows-1250','iso-8859-2']){
    try{
      const text = new TextDecoder(encoding, {fatal:false}).decode(bytes);
      warianty.push({text, score:ocenaDekodowania(text), encoding});
    }catch(_e){}
  }
  warianty.sort((a,b) => a.score - b.score);
  return warianty.length ? warianty[0] : {text:'', encoding:'utf-8'};
}

function ustawPodsumowanieZrodel(nazwy, liczbaZnakow=0, zamknij=false){
  const summary = $('sourceFileSummary');
  const details = $('sourceTextDetails');
  const lista = Array.isArray(nazwy) ? nazwy.filter(Boolean) : [];
  if(summary){
    if(lista.length === 0) summary.textContent = 'Wpisany tekst';
    else if(lista.length === 1) summary.textContent = lista[0];
    else { const pokaz = lista.slice(0,4); const reszta = Math.max(0, lista.length-pokaz.length); summary.textContent = `${lista.length} ${odmienPliki(lista.length)}: ${pokaz.join(', ')}${reszta ? ` … +${reszta}` : ''}`; }
    summary.title = lista.join('\n');
  }
  if(details && zamknij) details.open = false;
}

function odmienPliki(liczba){
  if(liczba === 1) return 'plik';
  const mod10 = liczba % 10, mod100 = liczba % 100;
  return (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) ? 'pliki' : 'plików';
}

function nazwyDokumentowZPola(pole){
  const text = pole ? String(pole.value || '') : '';
  return Array.from(text.matchAll(/^\s*---\s*WCZYTANY\s+PLIK\s*:\s*(.+?)\s*---\s*$/gmi)).map(m => m[1].trim()).filter(Boolean);
}

function wstawTekstZPliku(nazwa, tekst, tryb){
  const pole = $('textInput');
  if(!pole) return;
  const czystyTekst = naprawMojibakePolski(String(tekst || '').replace(/^\uFEFF/, ''));
  nazwa = naprawMojibakePolski(nazwa);
  const chunk = `--- WCZYTANY PLIK: ${nazwa} ---\n\n${czystyTekst}`;
  const candidate = (tryb === 'append' && pole.value.trim()) ? `${pole.value.trim()}\n\n${chunk}` : chunk;
  const candidateBytes = bajtyUtf8(candidate);
  if(candidateBytes > MAKSYMALNY_ROZMIAR_PAKIETU){
    throw new Error(`Pakiet po dodaniu miałby ${Math.round(candidateBytes/1024)} KB. Bezpieczny limit UI to ${Math.round(MAKSYMALNY_ROZMIAR_PAKIETU/1024)} KB. Podziel materiał na mniejsze partie.`);
  }
  if(tryb === 'append' && pole.value.trim()){
    pole.value = candidate;
  }else{
    // Current: nawet pierwszy plik ma jawny nagłówek dokumentu. Dzięki temu backend
    // i UI liczą ten sam zestaw dokumentów; nie powstaje anonimowy „prefix document”.
    pole.value = chunk;
  }
  ustawPodsumowanieZrodel(nazwyDokumentowZPola(pole), czystyTekst.length, true);
  pole.blur();
  ustawStatusPliku(`Wczytano: ${nazwa} · ${czystyTekst.length} znaków. Kliknij „Analizuj”, żeby uruchomić analizę.`);
  zaplanujZapisSesji(80);
}

async function odczytajPlikTekstowy(file, zachowajSciezke=false){
  const problem = walidujPlikTekstowy(file);
  if(problem) throw new Error(`${file && file.name ? file.name + ': ' : ''}${problem}`);
  const buffer = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error(`Nie udało się odczytać pliku: ${file.name}`));
    reader.readAsArrayBuffer(file);
  });
  const decoded = dekodujPlikTekstowy(buffer);
  const nazwa = zachowajSciezke && file.webkitRelativePath ? file.webkitRelativePath : file.name;
  return {name: naprawMojibakePolski(nazwa), text: decoded.text || '', size: file.size || 0};
}


function zbudujPakietTekstu(pole, loaded){
  const base = pole && pole.value ? pole.value.trim() : '';
  const chunks = loaded.map(item => `--- WCZYTANY PLIK: ${item.name} ---\n\n${naprawMojibakePolski(String(item.text || '').replace(/^\uFEFF/, ''))}`);
  return [base, ...chunks].filter(Boolean).join('\n\n');
}

function sprawdzPakietPrzedDodaniem(pole, loaded){
  const candidate = zbudujPakietTekstu(pole, loaded);
  const bytes = bajtyUtf8(candidate);
  if(bytes > MAKSYMALNY_ROZMIAR_PAKIETU){
    throw new Error(`Pakiet po dodaniu miałby ${Math.round(bytes/1024)} KB. Bezpieczny limit UI to ${Math.round(MAKSYMALNY_ROZMIAR_PAKIETU/1024)} KB, ponieważ backend przyjmuje maksymalnie 2 MB na całe żądanie. Podziel folder na mniejsze partie.`);
  }
  return {candidate, bytes};
}

function komunikatSkali(bytes, docCount){
  if(bytes > ZALECANY_ROZMIAR_PAKIETU || docCount > ZALECANA_LICZBA_DOKUMENTOW){
    return ` Duży pakiet (${Math.round(bytes/1024)} KB, ${docCount} dokumentów) — analiza na telefonie może potrwać wyraźnie dłużej.`;
  }
  return '';
}

async function dodajWielePlikow(loaded, dodatkowyStatus=''){
  const pole = $('textInput');
  if(!pole) return;
  const {candidate, bytes} = sprawdzPakietPrzedDodaniem(pole, loaded);
  pole.value = candidate;
  pole.focus();
  const chars = loaded.reduce((sum,item)=>sum+String(item.text||'').length,0);
  const nazwy = loaded.map(item => item.name);
  const widoczneNazwy = nazwy.slice(0,6);
  const resztaNazw = Math.max(0, nazwy.length - widoczneNazwy.length);
  const wszystkieNazwy = nazwyDokumentowZPola(pole);
  ustawPodsumowanieZrodel(wszystkieNazwy, chars, true);
  ustawStatusPliku(`Dodano ${loaded.length} ${odmienPliki(loaded.length)}: ${widoczneNazwy.join(', ')}${resztaNazw ? ` … +${resztaNazw}` : ''}. Łącznie w analizie: ${wszystkieNazwy.length} ${odmienPliki(wszystkieNazwy.length)}.${dodatkowyStatus}${komunikatSkali(bytes, wszystkieNazwy.length)} Kliknij „Analizuj”, żeby uruchomić analizę.`);
  zaplanujZapisSesji(80);
}

async function dodajPlikiZFileList(files, zachowajSciezke=false, dodatkowyStatus=''){
  const lista = Array.from(files || []);
  if(!lista.length) return;
  const supported = lista.filter(czyObslugiwanyPlik);
  const skippedUnsupported = lista.length - supported.length;
  const candidates = supported.filter(file => file.size <= MAKSYMALNY_ROZMIAR_PLIKU);
  const skippedTooLarge = supported.length - candidates.length;
  if(!candidates.length) throw new Error('Nie wybrano żadnych obsługiwanych plików tekstowych mieszczących się w limicie.');
  const tokenPostepu = pokazPostepOperacji('Wczytywanie plików', {wartosc:0, szczegol:`0/${candidates.length} · przygotowanie odczytu`});
  const accepted = [];
  try{
    for(let i=0;i<candidates.length;i++){
      const file=candidates[i];
      aktualizujPostepOperacji(tokenPostepu,{wartosc:(i/candidates.length)*92, szczegol:`${i}/${candidates.length} · ${file.name}`});
      accepted.push(await odczytajPlikTekstowy(file, zachowajSciezke));
      aktualizujPostepOperacji(tokenPostepu,{wartosc:((i+1)/candidates.length)*92, szczegol:`${i+1}/${candidates.length} · odczytano ${file.name}`});
    }
    const skipped = (skippedUnsupported || skippedTooLarge)
      ? ` Pominięto: ${skippedUnsupported} nieobsługiwanych i ${skippedTooLarge} zbyt dużych.`
      : '';
    aktualizujPostepOperacji(tokenPostepu,{wartosc:96,etykieta:'Składanie pakietu',szczegol:`${accepted.length} ${odmienPliki(accepted.length)} · kontrola limitu`});
    await dodajWielePlikow(accepted, `${dodatkowyStatus}${skipped}`);
    zakonczPostepOperacji(tokenPostepu,'Pliki dodane',`${accepted.length}/${candidates.length} odczytanych poprawnie.${skipped}`);
  }catch(err){
    bladPostepuOperacji(tokenPostepu,'Nie udało się dodać plików',err && err.message ? err.message : 'Błąd odczytu plików.');
    throw err;
  }
}

async function obsluzWyborFolderu(ev){
  const input = ev && ev.target ? ev.target : null;
  const files = input && input.files ? Array.from(input.files) : [];
  if(!files.length) return;
  try{
    await dodajPlikiZFileList(files, true, ' Tryb folderu zgodności.');
  }catch(err){
    ustawStatusPliku(err && err.message ? err.message : 'Nie udało się dodać plików z folderu.', true);
  }finally{
    if(input) input.value='';
  }
}

async function obsluzWyborWieluPlikow(ev){
  const input = ev && ev.target ? ev.target : null;
  const files = input && input.files ? Array.from(input.files) : [];
  if(!files.length) return;
  try{
    await dodajPlikiZFileList(files, false, ' Tryb wielu plików zgodności.');
  }catch(err){
    ustawStatusPliku(err && err.message ? err.message : 'Nie udało się dodać wielu plików.', true);
  }finally{
    if(input) input.value='';
  }
}

async function obsluzWyborPliku(ev){
  const input = ev && ev.target ? ev.target : null;
  const files = input && input.files ? Array.from(input.files) : [];
  if(!files.length) return;
  const tokenPostepu = pokazPostepOperacji('Wczytywanie pliku', {wartosc:8, szczegol:files[0].name || 'plik'});
  try{
    const first = await odczytajPlikTekstowy(files[0]);
    aktualizujPostepOperacji(tokenPostepu,{wartosc:82,szczegol:`Odczytano ${first.name} · składanie dokumentu`});
    if(trybWczytywaniaPliku === 'replace'){
      wstawTekstZPliku(first.name, first.text, 'replace');
    }else{
      wstawTekstZPliku(first.name, first.text, 'append');
    }
    zakonczPostepOperacji(tokenPostepu,'Plik gotowy',`${first.name} · ${first.text.length} znaków`);
  }catch(err){
    const msg=err && err.message ? err.message : 'Nie udało się odczytać pliku w przeglądarce.';
    ustawStatusPliku(msg, true);
    bladPostepuOperacji(tokenPostepu,'Błąd pliku',msg);
  }finally{
    if(input) input.value='';
  }
}

function czyAnulowanoPicker(err){
  return !!(err && (err.name === 'AbortError' || err.name === 'NotAllowedError') && /abort|cancel|anul|dismiss/i.test(String(err.message || err.name || '')));
}

let wymusKlasycznyPickerWielu = false;
let wymusKlasycznyPickerFolderu = false;

async function otworzWielePlikow(){
  const fallback = $('fileInputMany');
  if(!fallback){ ustawStatusPliku('Brak pola wyboru wielu plików w UI.', true); return; }
  // Na Androidzie nie przełączamy dynamicznie atrybutu `multiple` jednego inputu.
  // Używamy natywnego pickera z multiple:true, a gdy go nie ma — osobnego inputu,
  // który ma `multiple` już w HTML od chwili załadowania strony.
  if(!wymusKlasycznyPickerWielu && typeof window.showOpenFilePicker === 'function'){
    try{
      const handles = await window.showOpenFilePicker({multiple:true, id:'drogowskazy-wiele-plikow'});
      const files = await Promise.all(handles.map(h => h.getFile()));
      await dodajPlikiZFileList(files, false, ' Wybrano przez systemowy picker wielu plików.');
      return;
    }catch(err){
      if(czyAnulowanoPicker(err)) return;
      wymusKlasycznyPickerWielu = true;
      ustawStatusPliku('Systemowy wybór wielu plików nie zadziałał. Otwieram tryb zgodności; zaznacz kilka plików w jednym wyborze.', false);
    }
  }
  fallback.value='';
  fallback.click();
}

async function zbierzPlikiZKataloguHandle(dirHandle, prefix='', onScan=null){
  const wynik = [];
  for await (const [name, entry] of dirHandle.entries()){
    const rel = prefix ? `${prefix}/${name}` : name;
    if(entry.kind === 'file'){
      try{
        const file = await entry.getFile();
        wynik.push({file, relativePath:rel});
      }catch(error){
        // Błąd dostawcy jednego pliku nie blokuje pozostałych dokumentów.
        wynik.push({file:{name, size:0}, relativePath:rel, readError:error?.message || 'Nie można odczytać pliku.'});
      }
      if(typeof onScan === 'function') onScan(wynik.length, rel);
    }else if(entry.kind === 'directory'){
      const pod = await zbierzPlikiZKataloguHandle(entry, rel, onScan);
      wynik.push(...pod);
      if(typeof onScan === 'function') onScan(wynik.length, rel);
    }
  }
  return wynik;
}

async function dodajFolderZHandle(dirHandle){
  const tokenSkanu = pokazPostepOperacji('Skanowanie folderu', {wartosc:null, szczegol:'Szukam obsługiwanych dokumentów także w podfolderach…'});
  try{
    const entries = await zbierzPlikiZKataloguHandle(dirHandle, dirHandle.name || '', (count, rel)=>{
      aktualizujPostepOperacji(tokenSkanu,{tekstWartosci:`${count} pl.`,szczegol:`Znaleziono ${count} · ${rel}`});
    });
    const unreadable = entries.filter(item => item.readError);
    const supported = entries.filter(item => !item.readError && czyObslugiwanyPlik(item.file));
    const skippedUnsupported = entries.length - supported.length;
    const candidates = supported.filter(item=>item.file.size <= MAKSYMALNY_ROZMIAR_PLIKU);
    const skippedTooLarge = supported.length - candidates.length;
    if(!candidates.length) throw new Error('Folder nie zawiera obsługiwanych plików tekstowych mieszczących się w limicie.');
    // Przejmujemy ten sam widoczny komponent postępu, ale teraz mamy dokładny mianownik.
    aktualizujPostepOperacji(tokenSkanu,{etykieta:'Wczytywanie folderu',wartosc:0,szczegol:`0/${candidates.length} obsługiwanych plików`});
    const accepted=[];
    for(let i=0;i<candidates.length;i++){
      const item=candidates[i];
      aktualizujPostepOperacji(tokenSkanu,{wartosc:(i/candidates.length)*92,szczegol:`${i}/${candidates.length} · ${item.relativePath}`});
      const loaded=await odczytajPlikTekstowy(item.file,false);
      loaded.name=naprawMojibakePolski(item.relativePath || item.file.name);
      accepted.push(loaded);
      aktualizujPostepOperacji(tokenSkanu,{wartosc:((i+1)/candidates.length)*92,szczegol:`${i+1}/${candidates.length} · ${item.relativePath}`});
    }
    const extra=(skippedUnsupported || skippedTooLarge || unreadable.length)
      ? ` Pominięto: ${skippedUnsupported-unreadable.length} nieobsługiwanych, ${skippedTooLarge} zbyt dużych i ${unreadable.length} nieczytelnych.` : '';
    aktualizujPostepOperacji(tokenSkanu,{etykieta:'Składanie pakietu',wartosc:96,szczegol:`${accepted.length} ${odmienPliki(accepted.length)} · kontrola limitu`});
    await dodajWielePlikow(accepted, ` Wybrano cały folder z podfolderami.${extra}`);
    zakonczPostepOperacji(tokenSkanu,'Folder dodany',`${accepted.length} dokumentów gotowych do analizy.${extra}`);
  }catch(err){
    bladPostepuOperacji(tokenSkanu,'Błąd folderu',err && err.message ? err.message : 'Nie udało się wczytać folderu.');
    throw err;
  }
}

async function otworzFolder(){
  const fallback = $('folderInput');
  if(!fallback){ ustawStatusPliku('Brak pola wyboru folderu w UI.', true); return; }
  // Preferowany na współczesnym Chrome/Android File System Access API.
  // Fallback: <input webkitdirectory multiple>, bez dynamicznej zmiany atrybutów.
  if(!wymusKlasycznyPickerFolderu && typeof window.showDirectoryPicker === 'function'){
    try{
      const handle = await window.showDirectoryPicker({id:'drogowskazy-folder', mode:'read'});
      await dodajFolderZHandle(handle);
      return;
    }catch(err){
      if(czyAnulowanoPicker(err)) return;
      if(window.DrogowskazyAndroid){
        ustawStatusPliku(err?.message || 'Nie udało się otworzyć folderu. Spróbuj ponownie lub użyj „Dodaj kilka”.', true);
        return;
      }
      wymusKlasycznyPickerFolderu = true;
      ustawStatusPliku('Systemowy wybór folderu nie zadziałał. Otwieram tryb zgodności katalogu.', false);
    }
  }
  fallback.value='';
  fallback.click();
}


// Folder -> lokalna baza SQLite. Frontend szybko przekazuje pliki po jednym do
// trwałej kolejki SQLite. Właściwa analiza odbywa się po stronie serwera w tle,
// więc po zakończeniu przekazywania plików Chrome może zostać zminimalizowany.
let importBazyAktywny = false;
let monitorImportuWTleAktywny = false;
let zatrzymajImportBazyPoBiezacym = false;
let wymusKlasycznyPickerFolderuBazy = false;
let wymusKlasycznyPickerPakietuFolderowBazy = false;

function ustawStatusBazy(tekst, blad=false){
  const el = $('databaseStatus');
  if(!el) return;
  el.textContent = String(tekst || '');
  el.classList.toggle('is-error', !!blad);
}

function ustawLicznikiBazy({pending=0, saved=0, duplicates=0, errors=0, skipped=0}={}){
  const values = {
    databasePendingCount: pending,
    databaseSavedCount: saved,
    databaseDuplicateCount: duplicates,
    databaseErrorCount: errors,
    databaseSkippedCount: skipped,
  };
  Object.entries(values).forEach(([id,value]) => { const el=$(id); if(el) el.textContent=String(Math.max(0, Number(value)||0)); });
}

function ustawPostepBazy({label='', current='', completed=0, total=0, indeterminate=false, state=''}={}){
  const box=$('databaseProgress'), bar=$('databaseProgressBar');
  if(!box || !bar) return;
  box.hidden=false;
  box.classList.toggle('is-done', state==='done');
  box.classList.toggle('is-cancelled', state==='cancelled');
  const labelEl=$('databaseProgressLabel'), valueEl=$('databaseProgressValue'), currentEl=$('databaseCurrentFile');
  if(labelEl) labelEl.textContent=label || 'Import folderu';
  if(currentEl) currentEl.textContent=current || '';
  if(indeterminate){
    bar.removeAttribute('value');
    if(valueEl) valueEl.textContent='trwa…';
  }else{
    const safeTotal=Math.max(0, Number(total)||0), safeCompleted=Math.max(0, Number(completed)||0);
    bar.value=safeTotal ? Math.min(100, safeCompleted/safeTotal*100) : 0;
    if(valueEl) valueEl.textContent=`${safeCompleted}/${safeTotal}`;
  }
}

function ustawStanImportuBazy(aktywny){
  importBazyAktywny=!!aktywny;
  ustawZajetoscOperacji(aktywny);
  const cancel=$('cancelDatabaseImportBtn'), refresh=$('refreshDatabaseBtn'), download=$('downloadDatabaseBtn'), aggregate=$('aggregateDatabaseBtn'), reanalyze=$('reanalyzeDatabaseBtn'), compare=$('compareDatabaseBtn');
  if(cancel){cancel.hidden=!aktywny;cancel.disabled=false;}
  if(refresh) refresh.disabled=!!aktywny;
  if(download) download.disabled=!!aktywny;
  if(aggregate) aggregate.disabled=!!aktywny;
  if(reanalyze) reanalyze.disabled=!!aktywny;
  if(compare) compare.disabled=!!aktywny;
  ['importFilesToDatabaseBtn','importFolderToDatabaseBtn','addCompareFolderBtn','addCompareFolderPackBtn','restoreDatabaseBackupBtn'].forEach(id=>{const el=$(id);if(el) el.disabled=!!aktywny;});
}

function etykietaStatusuDokumentu(status){
  return {done:'zapisany',processing:'w toku',error:'błąd'}[String(status||'')] || String(status||'—');
}

function formatujDateBazy(value){
  if(!value) return '—';
  try{return new Date(value).toLocaleString('pl-PL');}catch(_err){return String(value);}
}

function formatujRozmiarBazy(bytes){
  const value=Math.max(0,Number(bytes)||0);
  if(value<1024) return `${value} B`;
  if(value<1024*1024) return `${Math.round(value/1024)} KB`;
  return `${(value/1024/1024).toFixed(1)} MB`;
}

const DATABASE_FOLDER_PAGE_SIZE=80;
let folderyBazyIndex=[];

function nazwaDokumentuWFoldeze(doc, folder){
  const raw=String(doc.relative_path || doc.filename || `Dokument ${doc.id}`).replace(/\\/g,'/');
  const prefix=`${String(folder||'').replace(/\\/g,'/').replace(/\/$/,'')}/`;
  return raw.startsWith(prefix) ? raw.slice(prefix.length) : raw;
}

function htmlDokumentuBazy(doc, folder){
  const status=String(doc.status||'');
  const path=nazwaDokumentuWFoldeze(doc,folder);
  const detail=status==='error' && doc.error ? ` · ${doc.error}` : '';
  const kindLabel=doc.is_article ? 'artykuł' : 'plik techniczny';
  return `<article class="database-document ${doc.is_article?'is-article':'is-support'}">
    <div class="database-document-main">
      <strong class="database-document-name">${esc(path)}</strong>
      <span class="database-document-meta">${esc(kindLabel)} · #${esc(doc.id)} · ${esc(formatujRozmiarBazy(doc.source_bytes))} · ${esc(doc.text_chars||0)} znaków · ${esc(formatujDateBazy(doc.analyzed_at||doc.updated_at))}${esc(detail)}</span>
    </div>
    <span class="database-document-status ${esc(status)}">${esc(etykietaStatusuDokumentu(status))}</span>
    <button class="secondary database-open-result" data-database-document-id="${Number(doc.id)||0}" type="button" ${status==='done'?'':'disabled'}>Otwórz wynik</button>
  </article>`;
}

function podlaczDokumentyBazy(container){
  if(!container) return;
  container.querySelectorAll('[data-database-document-id]').forEach(btn=>{
    if(btn.dataset.bound==='1') return;
    btn.dataset.bound='1';
    btn.addEventListener('click',()=>void otworzWynikZBazy(Number(btn.dataset.databaseDocumentId||0)));
  });
  container.querySelectorAll('[data-database-load-more]').forEach(btn=>{
    if(btn.dataset.bound==='1') return;
    btn.dataset.bound='1';
    btn.addEventListener('click',()=>{
      void zaladujDokumentyFolderu(btn.dataset.folder||'',Number(btn.dataset.offset||0),true);
    });
  });
}

async function zaladujDokumentyFolderu(folder, offset=0, append=false){
  const details=Array.from(document.querySelectorAll('.database-folder-group')).find(el=>el.dataset.folder===folder);
  const target=details?.querySelector('.database-folder-documents');
  if(!target) return;
  if(!append) target.innerHTML='<div class="database-empty">Wczytuję dokumenty folderu…</div>';
  try{
    const data=await pobierzJson(`/api/baza/dokumenty?folder=${encodeURIComponent(folder)}&limit=${DATABASE_FOLDER_PAGE_SIZE}&offset=${Math.max(0,offset)}`,{},'Dokumenty folderu');
    const docs=Array.isArray(data.documents)?data.documents:[];
    const meta=folderyBazyIndex.find(item=>String(item.id)===String(folder))||{};
    const total=Number(meta.documents)||docs.length;
    const html=docs.map(doc=>htmlDokumentuBazy(doc,folder)).join('');
    if(append){
      target.querySelector('.database-folder-more')?.remove();
      target.insertAdjacentHTML('beforeend',html);
    }else{
      target.innerHTML=html || '<div class="database-empty">Brak dokumentów w tym folderze.</div>';
    }
    const next=Math.max(0,offset)+docs.length;
    if(next<total){
      target.insertAdjacentHTML('beforeend',`<div class="database-folder-more"><button class="secondary" data-database-load-more data-folder="${esc(folder)}" data-offset="${next}" type="button">Pokaż kolejne (${next}/${total})</button></div>`);
    }
    details.dataset.loaded='1';
    podlaczDokumentyBazy(target);
  }catch(err){
    target.innerHTML=`<div class="database-empty">${esc(err?.message||'Nie udało się wczytać dokumentów folderu.')}</div>`;
  }
}

function renderujDokumentyBazy(folders){
  const box=$('databaseDocuments');
  const summary=$('databaseFolderSummary');
  if(!box) return;
  const rows=Array.isArray(folders)?folders:[];
  folderyBazyIndex=rows;
  if(summary) summary.textContent=rows.length ? `(${rows.length} folderów)` : '';
  if(!rows.length){
    box.innerHTML='<div class="database-empty">Brak zapisanych dokumentów.</div>';
    return;
  }
  box.innerHTML=rows.map(folder=>`<details class="database-folder-group" data-folder="${esc(folder.id||folder.label||'')}">
    <summary>
      <span class="database-folder-title">📁 ${esc(folder.label||folder.id||'(bez folderu)')}</span>
      <span class="database-folder-count">${esc(folder.articles||0)} artykułów</span>
    </summary>
    <div class="database-folder-meta">artykuły: ${esc(folder.articles||0)} · techniczne: ${esc(folder.support_files||0)} · rekordy razem: ${esc(folder.documents||0)} · błędy: ${esc(folder.error||0)} · ${esc(formatujRozmiarBazy(folder.source_bytes||0))}</div>
    <div class="database-folder-documents"><div class="database-empty">Rozwiń folder, aby wczytać dokumenty.</div></div>
  </details>`).join('');
  box.querySelectorAll('.database-folder-group').forEach(details=>details.addEventListener('toggle',()=>{
    if(details.open && details.dataset.loaded!=='1') void zaladujDokumentyFolderu(details.dataset.folder||'',0,false);
  }));
}

function pokazGlobalneStatystykiBazy(stats){
  const s=stats||{};
  ustawLicznikiBazy({pending:s.processing,saved:s.done,duplicates:s.duplicates,errors:s.error,skipped:0});
  const articles=Number(s.done_articles ?? s.articles)||0;
  const support=Number(s.done_support_files ?? s.support_files)||0;
  const total=Number(s.done)||Number(s.total)||0;
  const summary=$('databaseSummaryCount');
  if(summary) summary.textContent=`${articles} artykułów`;
  const kind=$('databaseKindStats');
  if(kind) kind.textContent=`Artykuły: ${articles} · pliki techniczne: ${support} · rekordy razem: ${total}. Porównania liczą tylko artykuły.`;
}

async function monitorujImportWTle(){
  if(monitorImportuWTleAktywny) return;
  monitorImportuWTleAktywny=true;
  try{
    while(true){
      let data;
      try{
        data=await pobierzJson('/api/baza/status',{},'Stan analizy w tle');
      }catch(err){
        ustawStatusBazy(`Analiza jest zapisana w SQLite, ale chwilowo nie mogę odczytać postępu: ${err?.message||err}`,true);
        return;
      }
      const stats=data.stats||{};
      const processing=Math.max(0,Number(stats.processing)||0);
      const done=Math.max(0,Number(stats.done)||0);
      const errors=Math.max(0,Number(stats.error)||0);
      const total=Math.max(1,done+processing+errors);
      const completed=Math.min(total,done+errors);
      pokazGlobalneStatystykiBazy(stats);
      if(processing<=0){
        ustawPostepBazy({label:'Analiza w tle zakończona',current:`Gotowe ${done} z ${total}. Nic nie jest liczone od początku po ponownym uruchomieniu.`,completed:total,total,state:'done'});
        ustawStatusBazy(`Analiza w tle zakończona · ${Number(stats.done_articles)||0} artykułów gotowych · ${errors} błędów.`);
        break;
      }
      const bg=data.background_import||{};
      const active=bg.active_document_id ? ` · dokument #${bg.active_document_id}` : '';
      const recovered=Math.max(0,Number(bg.recovered_after_restart)||0);
      const resumeNote=recovered>0 ? ` · po restarcie wznowiono ${recovered} niedokończonych` : '';
      ustawPostepBazy({label:'Kontynuacja analizy w tle',current:`Gotowe ${done} · pozostało ${processing}${active}${resumeNote}. Zakończone rekordy nie wracają do kolejki.`,completed,total});
      ustawStatusBazy(`Kontynuuję zapisany stan SQLite · gotowe ${done} · pozostało ${processing}. Nie zaczynam od zera.`);
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }finally{
    monitorImportuWTleAktywny=false;
  }
}

async function odswiezBazeDokumentow({zachowajLiczniki=false}={}){
  try{
    const data=await pobierzJson('/api/baza/dokumenty?limit=1&offset=0',{},'Odczyt bazy');
    renderujDokumentyBazy(data.folders||[]);
    if(!zachowajLiczniki) pokazGlobalneStatystykiBazy(data.stats||{});
    else {
      const summary=$('databaseSummaryCount');
      if(summary) summary.textContent=`${Number((data.stats||{}).done_articles ?? (data.stats||{}).articles)||0} artykułów`;
    }
    if(!importBazyAktywny){
      const stats=data.stats||{};
      const processing=Math.max(0,Number(stats.processing)||0);
      if(processing>0){
        ustawStatusBazy(`Baza działa w tle · pozostało ${processing} dokumentów do analizy.`);
        void monitorujImportWTle();
      }else{
        ustawStatusBazy(`Baza gotowa · ${Number(stats.articles)||0} artykułów · ${Number(stats.support_files)||0} plików technicznych · ${Number(stats.duplicates)||0} rozpoznanych duplikatów.`);
      }
    }
    await odswiezGrupyPorownania();
    if(oczekujacyStanBazySesji) przywrocStanBazyPoOdswiezeniu(false);
    // Wspólne sprawy obliczamy dopiero po kliknięciu użytkownika.
    // Wyniki benchmarku wczytujemy wyłącznie w jego sekcji.
    return data;
  }catch(err){
    ustawStatusBazy(err && err.message ? err.message : 'Nie udało się odczytać bazy.', true);
    return null;
  }
}

async function otworzWynikZBazy(documentId){
  if(!documentId) return;
  ostatniZbiorczyPayload = null;
  zbiorczeDokumentyMap = {};
  ustawStatusBazy(`Wczytuję zapisany wynik dokumentu #${documentId}…`);
  try{
    const data=await pobierzJson(`/api/baza/dokument/${documentId}/wynik`,{},'Odczyt wyniku z bazy');
    const pole=$('textInput');
    if(pole) pole.value=String(data.tekst||'');
    const doc=data.document||{};
    ustawPodsumowanieZrodel([doc.relative_path||doc.filename||`Dokument #${documentId}`], String(data.tekst||'').length, true);
    ustawTrybPracy('analiza');
    renderuj(data.wynik||{});
    zaplanujZapisSesji(80);
    const docLabel=doc.relative_path||doc.filename||`#${documentId}`;
    ustawStatusAktywnegoWyniku(`dokument z bazy · ${docLabel}`, true);
    ustawStatusBazy(`Otwarto zapisany wynik: ${docLabel}.`);
    ustawWidokBazy(false);
    zastosujTrybInterfejsu('uzytkownik',{restoreView:false});
    ustawAktywnyWidokProdukcyjny('wynik');
    zastosujUkladPracy('wynik');
    pokazWidok('start');
    const pane=$('analystPane'); if(pane) pane.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(err){
    ustawStatusBazy(err && err.message ? err.message : 'Nie udało się otworzyć wyniku.', true);
  }
}

function kompaktujZbiorczyPayload(data){
  const source = data && typeof data === 'object' ? data : {};
  const compact = Object.assign({}, source);
  delete compact.sekcje;
  delete compact.jednostki_znaczenia;
  delete compact.jednostki_znaczenia_surowe;
  if(source.p0){
    compact.p0 = Object.assign({}, source.p0);
    delete compact.p0.pelny_podglad;
  }
  return compact;
}

function materializujZbiorczyWynik(payload){
  const source = payload && typeof payload === 'object' ? payload : {};
  const registry = source.zbiorczy_rejestr_kart || {};
  const refs = source.zbiorcze_referencje_sekcji || {};
  const sections = {};
  Object.entries(refs).forEach(([name, ids]) => {
    if(name === '__p0_pelny_podglad') return;
    sections[name] = (Array.isArray(ids) ? ids : []).map(id => registry[id]).filter(Boolean);
  });
  const p0 = Object.assign({}, source.p0 || {});
  const p0Refs = Array.isArray(p0.pelny_podglad_refy) ? p0.pelny_podglad_refy : (refs.__p0_pelny_podglad || []);
  p0.pelny_podglad = p0Refs.map(id => registry[id]).filter(Boolean);
  const docs = source.zbiorcze_dokumenty || {};
  const data = Object.assign({}, source, {
    sekcje: sections,
    p0,
    jednostki_znaczenia: Array.isArray(source.zbiorcze_jednostki_znaczenia) ? source.zbiorcze_jednostki_znaczenia : [],
    jednostki_znaczenia_surowe: [],
    dokument: {
      document_count: Object.keys(docs).length,
      document_ids: Object.keys(docs),
      metadata_by_document: docs,
      sources: [],
      image_sources: [],
      segments: [],
      source_warnings: ['Wynik zbiorczy nie ma jednego tekstu źródłowego.'],
    },
    linkowanie_kart: {
      schemat: 'database_aggregate_links_v1',
      liczba_kart: Object.keys(registry).length,
      podlaczone: 0,
      bez_dokladnego_fragmentu: Object.keys(registry).length,
      zasada: 'Karty zbiorcze wskazują dokumenty bazy, a nie jeden wspólny zakres tekstu.',
    },
  });
  return data;
}

async function przeliczCalaBazeAktualnymSilnikiem(){
  if(importBazyAktywny){ ustawStatusBazy('Najpierw zakończ albo zatrzymaj import folderu.', true); return null; }
  if(!window.confirm("Przeliczyć WSZYSTKIE zapisane artykuły? Ta operacja może potrwać długo. Wykonaj najpierw kopię bazy/TRANSFER. Bez potwierdzenia nic nie zostanie uruchomione.")) return null;
  const button=$('reanalyzeDatabaseBtn');
  if(button) button.disabled=true;
  ustawPostepBazy({label:'Ponowna analiza całej bazy',current:'Przeliczam zapisane dokumenty aktualnym silnikiem. To może potrwać kilka minut…',indeterminate:true});
  ustawStatusBazy('Przeliczam wszystkie dokumenty statusu done. Treść i ID dokumentów pozostają bez zmian.');
  try{
    const payload=await pobierzJson('/api/baza/przelicz_wszystkie',{method:'POST'},'Ponowna analiza całej bazy');
    const done=Number(payload?.przeliczono||0), total=Number(payload?.razem||0), errs=Array.isArray(payload?.bledy)?payload.bledy.length:0;
    ustawPostepBazy({label:'Ponowna analiza zakończona',current:`${done}/${total} dokumentów · błędy: ${errs}`,completed:done,total:Math.max(total,1),state:errs?'cancelled':'done'});
    ustawStatusBazy(`Przeliczono ${done}/${total} dokumentów aktualnym silnikiem ${payload?.app_version||''}.${errs?` Błędy: ${errs}.`:''}`,!!errs);
    await odswiezBazeDokumentow();
    return payload;
  }catch(err){
    const msg=err && err.message ? err.message : 'Nie udało się przeliczyć całej bazy.';
    ustawPostepBazy({label:'Ponowna analiza nieudana',current:msg,completed:0,total:1,state:'cancelled'});
    ustawStatusBazy(msg,true);
    return null;
  }finally{ if(button) button.disabled=false; }
}

function formatCompareValue(value, kind){
  const n=Number(value)||0;
  if(kind==='percent') return `${n.toFixed(2).replace('.',',')}%`;
  if(kind==='number') return n.toFixed(2).replace('.',',');
  return Math.round(n).toLocaleString('pl-PL');
}

function renderCompareDistribution(title, dist, aName, bName){
  const rows=Array.isArray(dist?.rows)?dist.rows:[];
  if(!rows.length) return '';
  const body=rows.map(row=>`<tr>
    <td>${esc(row.label)}</td>
    <td><strong>${esc(row.a_count)}</strong> <span class="muted">${esc(String(row.a_share).replace('.',','))}% udziału · ${esc(String(row.a_doc_share??0).replace('.',','))}% dok. · ${esc(String(row.a_per_1000_words??0).replace('.',','))}/1000 słów</span></td>
    <td><strong>${esc(row.b_count)}</strong> <span class="muted">${esc(String(row.b_share).replace('.',','))}% udziału · ${esc(String(row.b_doc_share??0).replace('.',','))}% dok. · ${esc(String(row.b_per_1000_words??0).replace('.',','))}/1000 słów</span></td>
    <td class="compare-delta ${Number(row.delta_pp)>0?'positive':Number(row.delta_pp)<0?'negative':''}">${Number(row.delta_pp)>0?'+':''}${esc(String(row.delta_pp).replace('.',','))} pp udziału<br><span class="muted">${Number(row.delta_doc_pp)>0?'+':''}${esc(String(row.delta_doc_pp??0).replace('.',','))} pp dokumentów</span></td>
  </tr>`).join('');
  return `<section class="database-compare-section"><h4>${esc(title)}</h4><div class="database-compare-table-wrap"><table class="database-compare-table"><thead><tr><th>Element</th><th>${esc(aName)}</th><th>${esc(bName)}</th><th>A − B</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
}

function renderujPorownanieBazy(payload){
  renderujPorownanieBazyDo($('databaseComparisonResult'),payload);
}


function aktualizujPickerGrupPorownania(){
  const sel=$('databaseCompareGroups'), list=$('databaseCompareGroupList'), counter=$('databaseCompareSelectedCount');
  if(!sel||!list) return;
  const selected=new Set(Array.from(sel.selectedOptions||[]).map(o=>o.value));
  list.querySelectorAll('input[data-compare-group]').forEach(input=>{ input.checked=selected.has(input.value); });
  if(counter) counter.textContent=`Wybrane: ${selected.size} · dostępne: ${sel.options.length} · limit: 10`;
  const compareBtn=$('compareDatabaseBtn');
  if(compareBtn) compareBtn.disabled=selected.size<2 || selected.size>10 || importBazyAktywny;
  const status=$('databaseCompareStatus');
  if(status && sel.options.length){
    const mode=$('databaseCompareMode')?.value || 'folder';
    const label=mode==='folder'?'folderów':'redakcji / źródeł';
    status.textContent=`W bazie: ${sel.options.length} ${label}. Zaznaczone: ${selected.size}. Limit jednego porównania: 10.${mode==='folder'?' Możesz dodać 1 folder albo pakiet folderów przyciskami powyżej.':''}`;
  }
}

function renderujPickerGrupPorownania(groups){
  const list=$('databaseCompareGroupList'), sel=$('databaseCompareGroups');
  if(!list||!sel) return;
  const byId=new Map((groups||[]).map(g=>[String(g.id),g]));
  list.innerHTML=Array.from(sel.options).map(option=>{
    const g=byId.get(String(option.value))||{};
    return `<label class="database-group-option"><input type="checkbox" data-compare-group value="${esc(option.value)}" ${option.selected?'checked':''}><span class="database-group-option-text">${esc(g.label||option.textContent||option.value)}<small>${esc(g.documents||0)} dokumentów</small></span></label>`;
  }).join('') || '<div class="database-empty">Brak grup do porównania.</div>';
  list.querySelectorAll('input[data-compare-group]').forEach(input=>input.addEventListener('change',()=>{
    const opt=Array.from(sel.options).find(o=>o.value===input.value);
    if(!opt) return;
    if(input.checked && wybraneGrupyPorownania().length>=10){
      input.checked=false;
      const status=$('databaseCompareStatus');
      if(status) status.textContent='Maksymalnie 10 grup jednocześnie.';
      return;
    }
    opt.selected=input.checked;
    aktualizujPickerGrupPorownania();
    zaplanujZapisSesji(120);
  }));
  aktualizujPickerGrupPorownania();
}

async function odswiezGrupyPorownania(){
  const mode=$('databaseCompareMode')?.value || 'publisher';
  const sel=$('databaseCompareGroups'), status=$('databaseCompareStatus'), compareBtn=$('compareDatabaseBtn');
  if(!sel) return null;
  try{
    const selected=new Set(Array.from(sel.selectedOptions||[]).map(o=>o.value));
    const payload=await pobierzJson(`/api/baza/porownanie/grupy?mode=${encodeURIComponent(mode)}`,{},'Grupy porównania');
    const groups=Array.isArray(payload.groups)?payload.groups:[];
    sel.innerHTML=groups.map(g=>`<option value="${esc(g.id)}">${esc(g.label)} · ${esc(g.documents)} dok.</option>`).join('');
    Array.from(sel.options).forEach(o=>{ if(selected.has(o.value)) o.selected=true; });
    if(groups.length>1){
      const current=Array.from(sel.selectedOptions||[]);
      // Brak automatycznego zaznaczania folderów.
      if(status) status.textContent=`Dostępne w bazie: ${groups.length}. Zaznaczone: ${Array.from(sel.selectedOptions||[]).length}. Limit porównania: 10. Aby mieć więcej folderów, dodaj 1 folder albo cały pakiet folderów.`;
      if(compareBtn) compareBtn.disabled=false;
    }else{
      if(status) status.textContent=groups.length===1 ? 'W bazie jest tylko jedna grupa. Dodaj kolejny folder do bazy, aby uruchomić porównanie.' : 'Brak grup do porównania. Dodaj pierwszy folder do bazy.';
      if(compareBtn) compareBtn.disabled=true;
    }
    renderujPickerGrupPorownania(groups);
    return payload;
  }catch(err){
    const list=$('databaseCompareGroupList'); if(list) list.innerHTML='<div class="database-empty">Nie udało się wczytać grup.</div>';
    if(status) status.textContent=err?.message || 'Nie udało się wczytać grup porównania.';
    if(compareBtn) compareBtn.disabled=true;
    return null;
  }
}

function wybraneGrupyPorownania(){
  const sel=$('databaseCompareGroups');
  return sel ? Array.from(sel.selectedOptions||[]).map(o=>o.value).filter(Boolean) : [];
}

function renderujPorownanieMulti(payload){
  renderujPorownanieMultiDo($('databaseComparisonResult'),payload);
}

async function porownajGrupyBazy(){
  const mode=$('databaseCompareMode')?.value || 'publisher';
  const groups=wybraneGrupyPorownania();
  const status=$('databaseCompareStatus'), button=$('compareDatabaseBtn'), dl=$('downloadDatabaseComparisonBtn');
  if(groups.length<2 || groups.length>10){ if(status) status.textContent='Zaznacz od 2 do 10 różnych grup.'; return null; }
  if(button) button.disabled=true;
  if(status) status.textContent='Porównuję zapisane analizy bez ponownego uruchamiania klasyfikatora…';
  const token=pokazPostepOperacji('Porównuję grupy',{wartosc:null,szczegol:`${groups.length} grup · odczyt zapisanych analiz`});
  try{
    const params=new URLSearchParams({mode}); groups.forEach(group=>params.append('group',group));
    const payload=await pobierzJson(`/api/baza/porownanie?${params.toString()}`,{},'Porównanie bazy');
    ostatniePorownanieBazy=payload;
    if(Array.isArray(payload.groups)) renderujPorownanieMulti(payload); else renderujPorownanieBazy(payload);
    if(dl) dl.disabled=false;
    if(status) status.textContent=`Porównanie gotowe: ${groups.length} grup.`;
    zakonczPostepOperacji(token,'Porównanie gotowe',`${groups.length} grup porównanych.`);
    zaplanujZapisSesji(100);
    return payload;
  }catch(err){
    if(status) status.textContent=err?.message || 'Nie udało się wykonać porównania.';
    ostatniePorownanieBazy=null;
    if(dl) dl.disabled=true;
    bladPostepuOperacji(token,'Porównanie nieudane',err?.message||'Błąd porównania grup.');
    return null;
  }finally{ if(button) button.disabled=false; }
}

function pobierzPorownanieBazy(){
  if(!ostatniePorownanieBazy) return;
  const mode=ostatniePorownanieBazy.mode||'compare';
  const stamp=new Date().toISOString().replace(/[:.]/g,'-');
  pobierzPlik(`drogowskazy_porownanie_${mode}_${stamp}.json`,JSON.stringify(ostatniePorownanieBazy,null,2),'application/json;charset=utf-8');
}


function wybraneGrupyTejSamejSprawy(){
  const sel=$('sameStoryGroups');
  return sel ? Array.from(sel.selectedOptions||[]).map(o=>o.value).filter(Boolean) : [];
}

function aktualizujPickerTejSamejSprawy(){
  const sel=$('sameStoryGroups'), list=$('sameStoryGroupList'), counter=$('sameStorySelectedCount'), button=$('compareSameStoryBtn');
  if(!sel||!list) return;
  const selected=new Set(Array.from(sel.selectedOptions||[]).map(o=>o.value));
  list.querySelectorAll('input[data-same-story-group]').forEach(input=>{ input.checked=selected.has(input.value); });
  if(counter) counter.textContent=`Wybrane: ${selected.size} · dostępne: ${sel.options.length} · limit: 10`;
  if(button) button.disabled=selected.size<2 || selected.size>10;
}

function ustawRedakcjeDlaTematu(){
  const topicId=$('sameStoryTopic')?.value||'';
  const topic=wykryteTematyBazy.find(x=>x.topic_id===topicId);
  const sel=$('sameStoryGroups'), list=$('sameStoryGroupList'), status=$('sameStoryStatus');
  if(!sel||!list) return;
  const previous=new Set(Array.from(sel.selectedOptions||[]).map(o=>o.value));
  const pubs=Array.isArray(topic?.publishers)?topic.publishers:[];
  sel.innerHTML=pubs.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');
  Array.from(sel.options).forEach(o=>{ if(previous.has(o.value)) o.selected=true; });
  if(Array.from(sel.selectedOptions||[]).length<2 && pubs.length>1){
    // Domyślnie zaznacz wszystkie dostępne redakcje do limitu 10 — użytkownik może je odznaczyć.
    // Nie zaznaczaj redakcji bez decyzji użytkownika.
  }
  list.innerHTML=pubs.map(pub=>`<label class="database-group-option"><input type="checkbox" data-same-story-group value="${esc(pub)}" ${Array.from(sel.selectedOptions||[]).some(o=>o.value===pub)?'checked':''}><span class="database-group-option-text">${esc(pub)}</span></label>`).join('') || '<div class="database-empty">Brak co najmniej dwóch redakcji dla tego tematu.</div>';
  list.querySelectorAll('input[data-same-story-group]').forEach(input=>input.addEventListener('change',()=>{
    const opt=Array.from(sel.options).find(o=>o.value===input.value);
    if(!opt) return;
    if(input.checked && wybraneGrupyTejSamejSprawy().length>=10){
      input.checked=false;
      if(status) status.textContent='Maksymalnie 10 redakcji jednocześnie.';
      return;
    }
    opt.selected=input.checked;
    aktualizujPickerTejSamejSprawy();
    zaplanujZapisSesji(120);
  }));
  aktualizujPickerTejSamejSprawy();
  if(status && pubs.length) status.textContent=`Ta sprawa ma ${pubs.length} redakcji. Zaznacz od 2 do 10.`;
}

async function odswiezTematyTejSamejSprawy(){
  const sel=$('sameStoryTopic'), status=$('sameStoryStatus'), button=$('compareSameStoryBtn');
  if(!sel) return null;
  const token=pokazPostepOperacji('Wykrywanie wspólnych spraw',{wartosc:null,szczegol:'Porównuję tytuły, leady, rzadkie słowa i daty w zapisanej bazie.',zajety:false});
  try{
    const previous=sel.value||'';
    const payload=await pobierzJson('/api/baza/tematy',{},'Wykrywanie tych samych spraw');
    wykryteTematyBazy=Array.isArray(payload.topics)?payload.topics:[];
    sel.innerHTML=wykryteTematyBazy.length
      ? wykryteTematyBazy.map(t=>`<option value="${esc(t.topic_id)}">${esc(t.title)} · ${esc(t.publisher_count)} red. · ${esc(t.documents)} dok.</option>`).join('')
      : '<option value="">Brak wykrytych wspólnych tematów</option>';
    if(previous && Array.from(sel.options).some(o=>o.value===previous)) sel.value=previous;
    ustawRedakcjeDlaTematu();
    if(status) status.textContent=wykryteTematyBazy.length ? `Wykryto ${wykryteTematyBazy.length} spraw z co najmniej dwiema redakcjami.` : 'Nie wykryto jeszcze spraw opisanych przez co najmniej dwie redakcje.';
    if(button) button.disabled=wykryteTematyBazy.length===0 || wybraneGrupyTejSamejSprawy().length<2;
    zakonczPostepOperacji(token,'Tematy gotowe',`Wykryto ${wykryteTematyBazy.length} wspólnych spraw.`);
    return payload;
  }catch(err){
    if(status) status.textContent=err?.message||'Nie udało się wykryć tematów.';
    if(button) button.disabled=true;
    bladPostepuOperacji(token,'Wykrywanie tematów nieudane',err?.message||'Błąd wykrywania wspólnych spraw.');
    return null;
  }
}

async function porownajTaSamaSprawe(){
  const topicId=$('sameStoryTopic')?.value||'', groups=wybraneGrupyTejSamejSprawy();
  const status=$('sameStoryStatus'), box=$('sameStoryComparisonResult'), dl=$('downloadSameStoryComparisonBtn'), button=$('compareSameStoryBtn');
  if(!topicId||groups.length<2||groups.length>10){ if(status) status.textContent='Wybierz temat i zaznacz od 2 do 10 redakcji.'; return null; }
  if(button) button.disabled=true;
  const token=pokazPostepOperacji('Porównuję tę samą sprawę',{wartosc:null,szczegol:`${groups.length} redakcji · analiza zapisanych wyników`});
  try{
    const params=new URLSearchParams({topic_id:topicId,mode:'publisher'}); groups.forEach(group=>params.append('group',group));
    const payload=await pobierzJson(`/api/baza/temat/porownanie?${params.toString()}`,{},'Porównanie tej samej sprawy');
    ostatniePorownanieTejSamejSprawy=payload;
    if(box){ if(Array.isArray(payload.groups)) renderujPorownanieMultiDo(box,payload); else renderujPorownanieBazyDo(box,payload); }
    if(dl) dl.disabled=false;
    if(status) status.textContent=`Porównanie gotowe: ${groups.length} redakcji · ${payload.same_story?.title||''}`;
    zakonczPostepOperacji(token,'Porównanie gotowe',`${groups.length} redakcji w obrębie jednej sprawy.`);
    zaplanujZapisSesji(100);
    return payload;
  }catch(err){
    if(status) status.textContent=err?.message||'Nie udało się porównać tej samej sprawy.';
    if(box) box.innerHTML=''; if(dl) dl.disabled=true;
    bladPostepuOperacji(token,'Porównanie nieudane',err?.message||'Błąd porównania tej samej sprawy.');
    return null;
  } finally { if(button) button.disabled=false; }
}

function renderujPorownanieMultiDo(box,payload){
  if(!box||!payload||!payload.ok){if(box)box.innerHTML='';return;}
  const groups=Array.isArray(payload.groups)?payload.groups:[];
  const metrics=Array.isArray(payload.metrics)?payload.metrics:[];
  const head=groups.map(g=>`<th>${esc(g.name||'')}</th>`).join('');
  const rows=metrics.map(row=>`<tr><td>${esc(row.label)}</td>${groups.map(g=>`<td>${esc(formatCompareValue((row.values||{})[g.name],row.kind))}</td>`).join('')}</tr>`).join('');
  const warnings=(payload.warnings||[]).map(x=>`<div class="database-compare-warning">${esc(x)}</div>`).join('');
  const cards=groups.map(g=>`<div><strong>${esc(g.name||'')}</strong><span>${esc(g.documents||0)} dokumentów</span></div>`).join('');
  const topic=payload.same_story?`<div class="database-compare-warning"><strong>Ta sama sprawa:</strong> ${esc(payload.same_story.title||'')} · ${esc(payload.same_story.documents||0)} dok. · podobieństwo śr. ${esc(payload.same_story.avg_similarity||0)}</div>`:'';
  box.innerHTML=`${topic}<div class="database-compare-head database-compare-head-multi">${cards}</div>${warnings}<div class="database-compare-note">${esc(payload.method_note||'')}</div><section class="database-compare-section"><h4>Porównanie ${esc(groups.length)} grup</h4><div class="database-compare-table-wrap"><table class="database-compare-table"><thead><tr><th>Metryka</th>${head}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function renderujPorownanieBazyDo(box,payload){
  if(!box||!payload||!payload.ok){if(box)box.innerHTML='';return;}
  const a=payload.group_a||{}, b=payload.group_b||{};
  const metrics=(payload.metrics||[]).map(row=>`<tr><td>${esc(row.label)}</td><td>${esc(formatCompareValue(row.a,row.kind))}</td><td>${esc(formatCompareValue(row.b,row.kind))}</td><td class="compare-delta ${Number(row.delta)>0?'positive':Number(row.delta)<0?'negative':''}">${Number(row.delta)>0?'+':''}${esc(formatCompareValue(row.delta,row.kind))}</td></tr>`).join('');
  const warnings=(payload.warnings||[]).map(x=>`<div class="database-compare-warning">${esc(x)}</div>`).join('');
  const dist=payload.distributions||{};
  const topic=payload.same_story?`<div class="database-compare-warning"><strong>Ta sama sprawa:</strong> ${esc(payload.same_story.title||'')} · ${esc(payload.same_story.documents||0)} dok. · podobieństwo śr. ${esc(payload.same_story.avg_similarity||0)}</div>`:'';
  box.innerHTML=`${topic}<div class="database-compare-head"><div><strong>${esc(a.name||'A')}</strong><span>${esc(a.documents||0)} dokumentów</span></div><div class="database-compare-vs">VS</div><div><strong>${esc(b.name||'B')}</strong><span>${esc(b.documents||0)} dokumentów</span></div></div>${warnings}<div class="database-compare-note">${esc(payload.method_note||'')}</div><section class="database-compare-section"><h4>Podstawowe metryki</h4><div class="database-compare-table-wrap"><table class="database-compare-table"><thead><tr><th>Metryka</th><th>${esc(a.name||'A')}</th><th>${esc(b.name||'B')}</th><th>A − B</th></tr></thead><tbody>${metrics}</tbody></table></div></section>${renderCompareDistribution('Najczęściej przypisywani mówcy',dist.speakers,a.name,b.name)}${renderCompareDistribution('Najczęstsze targety / o kim',dist.targets,a.name,b.name)}${renderCompareDistribution('Tematy relacji',dist.topics,a.name,b.name)}${renderCompareDistribution('Źródła przywołane',dist.cited_sources,a.name,b.name)}${renderCompareDistribution('Fakt / opinia / cytat',dist.claim_types,a.name,b.name)}${renderCompareDistribution('P0 — sygnały',dist.p0,a.name,b.name)}${renderCompareDistribution('P1 — potwierdzone struktury',dist.p1,a.name,b.name)}${renderCompareDistribution('P2 — techniki',dist.p2,a.name,b.name)}${renderCompareDistribution('P3 — ramy',dist.p3,a.name,b.name)}${renderCompareDistribution('P4 — strategie',dist.p4,a.name,b.name)}${renderCompareDistribution('P5 — diagnozy',dist.p5,a.name,b.name)}`;
}

function pobierzPorownanieTejSamejSprawy(){
  if(!ostatniePorownanieTejSamejSprawy) return;
  const stamp=new Date().toISOString().replace(/[:.]/g,'-');
  pobierzPlik(`drogowskazy_ta_sama_sprawa_${stamp}.json`,JSON.stringify(ostatniePorownanieTejSamejSprawy,null,2),'application/json;charset=utf-8');
}

function renderujWynikBenchmarku(summary){
  const box=$('benchmarkStats'); if(!box||!summary) return;
  const rows=[['Cała relacja',summary.overall],['Mówca',summary.speaker],['Claim',summary.claim],['Target',summary.target],['Źródło',summary.source]].map(([label,m])=>`<tr><td>${label}</td><td>${esc(m?.n||0)}</td><td>${esc(String(m?.strict_percent||0).replace('.',','))}%</td><td>${esc(String(m?.lenient_percent||0).replace('.',','))}%</td><td>${esc(m?.false||0)}</td></tr>`).join('');
  box.innerHTML=`<section class="database-compare-section"><h4>Ręczny benchmark relacji</h4><div class="database-compare-table-wrap"><table class="database-compare-table"><thead><tr><th>Element</th><th>N</th><th>Ścisłe</th><th>Z częściowymi</th><th>Błędne</th></tr></thead><tbody>${rows}</tbody></table></div><p class="muted small">${esc(summary.warning||'')}</p></section>`;
}

async function odswiezWynikBenchmarku(){
  const box=$('benchmarkStats'); if(!box) return null;
  try{ const payload=await pobierzJson('/api/baza/benchmark/wynik',{},'Wynik benchmarku'); renderujWynikBenchmarku(payload); return payload; }
  catch(_err){ return null; }
}

function benchmarkSelect(id,label){
  return `<label>${label}<select id="${id}"><option value="unknown">—</option><option value="correct">poprawne</option><option value="partial">częściowe</option><option value="false">błędne</option></select></label>`;
}

function renderujKarteBenchmarku(){
  const box=$('benchmarkCard'), status=$('benchmarkStatus'); if(!box) return;
  const item=benchmarkProba[benchmarkIndex];
  if(!item){ box.innerHTML=''; if(status) status.textContent='Brak kolejnych nieocenionych relacji w tej próbie.'; return; }
  box.innerHTML=`<article class="database-document"><div class="database-document-main"><strong>${esc(item.publisher||'')} · ${esc(item.filename||'')}</strong><span class="database-document-meta">${esc(benchmarkIndex+1)}/${esc(benchmarkProba.length)} · relation_id ${esc(item.relation_id)}</span></div></article><div class="database-compare-note"><strong>Mówca:</strong> ${esc(item.speaker||'—')} · <strong>akcja:</strong> ${esc(item.action||'—')} · <strong>target:</strong> ${esc(item.target||'—')}<br><strong>Claim:</strong> ${esc(item.claim||'—')}<br><strong>Źródło:</strong> ${esc(item.source||'—')} · <strong>review:</strong> ${item.requires_review?'TAK':'NIE'} · <strong>confidence:</strong> ${esc(item.confidence||'—')}</div><blockquote class="manual-benchmark-snippet">${esc(item.snippet||'')}</blockquote><div class="database-compare-controls"><label>Cała relacja<select id="benchmarkOverall"><option value="correct">poprawna</option><option value="partial">częściowa</option><option value="false">błędna</option></select></label>${benchmarkSelect('benchmarkSpeaker','Mówca')}${benchmarkSelect('benchmarkClaim','Claim')}${benchmarkSelect('benchmarkTarget','Target')}${benchmarkSelect('benchmarkSource','Źródło')}<label>Notatka<input id="benchmarkNote" type="text" maxlength="2000"></label><button class="secondary strong-action" id="saveBenchmarkLabelBtn" type="button">Zapisz i następna</button></div>`;
  $('saveBenchmarkLabelBtn')?.addEventListener('click',()=>{void zapiszOceneBenchmarku();});
  if(status) status.textContent=`Próba: ${benchmarkProba.length} relacji. Oceniasz ${benchmarkIndex+1}.`;
}

async function wczytajProbeBenchmarku(){
  const size=$('benchmarkSampleSize')?.value||'30', seed=$('benchmarkSeed')?.value||'v44', status=$('benchmarkStatus');
  try{ const payload=await pobierzJson(`/api/baza/benchmark/proba?size=${encodeURIComponent(size)}&seed=${encodeURIComponent(seed)}&unlabeled=1`,{},'Próba benchmarku'); benchmarkProba=payload.items||[]; benchmarkIndex=0; renderujKarteBenchmarku(); renderujWynikBenchmarku(payload.summary); return payload; }
  catch(err){ if(status) status.textContent=err?.message||'Nie udało się wczytać próby.'; return null; }
}

async function zapiszOceneBenchmarku(){
  const item=benchmarkProba[benchmarkIndex]; if(!item) return;
  const payload={document_id:item.document_id,relation_id:item.relation_id,overall_label:$('benchmarkOverall')?.value||'correct',speaker_label:$('benchmarkSpeaker')?.value||'unknown',claim_label:$('benchmarkClaim')?.value||'unknown',target_label:$('benchmarkTarget')?.value||'unknown',source_label:$('benchmarkSource')?.value||'unknown',note:$('benchmarkNote')?.value||''};
  try{ const out=await pobierzJson('/api/baza/benchmark/ocena',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},'Zapis benchmarku'); renderujWynikBenchmarku(out.summary); benchmarkIndex+=1; renderujKarteBenchmarku(); }
  catch(err){ const status=$('benchmarkStatus'); if(status) status.textContent=err?.message||'Nie udało się zapisać oceny.'; }
}

function renderujGoldStats(summary){
  const box=$('goldStats'); if(!box||!summary) return;
  const row=(label,m)=>`<tr><td>${esc(label)}</td><td>${esc(m?.tp||0)}</td><td>${esc(m?.fp||0)}</td><td>${esc(m?.fn||0)}</td><td>${esc(((m?.precision||0)*100).toFixed(1).replace('.',','))}%</td><td>${esc(((m?.recall||0)*100).toFixed(1).replace('.',','))}%</td><td>${esc(((m?.f1||0)*100).toFixed(1).replace('.',','))}%</td></tr>`;
  box.innerHTML=`<section class="database-compare-section"><h4>GOLD skuteczności</h4><div class="database-compare-table-wrap"><table class="database-compare-table"><thead><tr><th>Tryb</th><th>TP</th><th>FP</th><th>FN</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>${row('Ścisły',summary.strict)}${row('Tolerancyjny',summary.lenient)}</tbody></table></div><p class="muted small">Kompletne dokumenty GOLD: ${esc(summary.documents||0)}. ${esc(summary.method_note||'')}</p></section>`;
}

function goldRelationsToJson(item){
  const rows=(item?.predicted_relations||[]).map(r=>({speaker:r.speaker||'',claim:r.claim||'',target:r.target||'',source:r.source||''}));
  return JSON.stringify(rows,null,2);
}

function renderujKarteGold(){
  const box=$('goldCard'), status=$('goldStatus'); if(!box) return;
  const item=goldProba[goldIndex];
  if(!item){ box.innerHTML=''; if(status) status.textContent='Brak kolejnych nieoznaczonych dokumentów GOLD w tej próbie.'; return; }
  const text=String(item.text||'');
  box.innerHTML=`<article class="database-document"><div class="database-document-main"><strong>${esc(item.relative_path||item.filename||'')}</strong><span class="database-document-meta">${esc(goldIndex+1)}/${esc(goldProba.length)} · document_id ${esc(item.document_id)}</span></div></article><div class="database-compare-note"><strong>Instrukcja:</strong> poniższy JSON ma być kompletną prawdą referencyjną dla tego dokumentu. Usuń relacje błędne, popraw pola i dopisz brakujące.</div><details open><summary>Tekst dokumentu</summary><pre class="manual-benchmark-snippet gold-document-text">${esc(text)}</pre></details><label class="gold-json-label">Oczekiwane relacje GOLD<textarea id="goldExpectedJson" class="gold-json-editor" spellcheck="false">${esc(goldRelationsToJson(item))}</textarea></label><label>Notatka<input id="goldNote" type="text" maxlength="4000"></label><div class="database-compare-controls"><button class="secondary strong-action" id="saveGoldDocumentBtn" type="button">Zapisz kompletny dokument i następny</button></div>`;
  $('saveGoldDocumentBtn')?.addEventListener('click',()=>{void zapiszDokumentGold();});
  if(status) status.textContent=`GOLD: dokument ${goldIndex+1}/${goldProba.length}. Przewidywane relacje: ${(item.predicted_relations||[]).length}.`;
}

async function wczytajProbeGold(){
  const size=$('goldSampleSize')?.value||'10', seed=$('goldSeed')?.value||'gold-v1', status=$('goldStatus');
  try{
    const payload=await pobierzJson(`/api/baza/gold/proba?size=${encodeURIComponent(size)}&seed=${encodeURIComponent(seed)}&unlabeled=1`,{},'Próba GOLD');
    goldProba=payload.items||[]; goldIndex=0; renderujKarteGold(); renderujGoldStats(payload.summary); return payload;
  }catch(err){ if(status) status.textContent=err?.message||'Nie udało się wczytać próby GOLD.'; return null; }
}

async function zapiszDokumentGold(){
  const item=goldProba[goldIndex]; if(!item) return;
  const status=$('goldStatus'); let expected=[];
  try{
    expected=JSON.parse($('goldExpectedJson')?.value||'[]');
    if(!Array.isArray(expected)) throw new Error('JSON musi być tablicą relacji.');
  }catch(err){ if(status) status.textContent=`Błąd JSON GOLD: ${err?.message||err}`; return; }
  const payload={document_id:item.document_id,expected_relations:expected,note:$('goldNote')?.value||'',completed:true};
  try{
    const out=await pobierzJson('/api/baza/gold/dokument',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},'Zapis GOLD');
    renderujGoldStats(out.summary); goldIndex+=1; renderujKarteGold();
  }catch(err){ if(status) status.textContent=err?.message||'Nie udało się zapisać dokumentu GOLD.'; }
}

async function odswiezGoldStats(){
  try{ const payload=await pobierzJson('/api/baza/gold/wynik',{},'Metryki GOLD'); renderujGoldStats(payload); return payload; }
  catch(_err){ return null; }
}

async function polaczWszystkieAnalizyBazy(){
  if(importBazyAktywny){
    ustawStatusBazy('Najpierw zakończ albo zatrzymaj import folderu.', true);
    return null;
  }
  const button=$('aggregateDatabaseBtn');
  if(button) button.disabled=true;
  ustawPostepBazy({label:'Łączenie zapisanych analiz',current:'Czytam wyniki SQLite i deduplikuję karty…',indeterminate:true});
  ustawStatusBazy('Tworzę jeden zbiorczy wynik ze wszystkich zakończonych analiz. Dokumenty nie są analizowane ponownie.');
  try{
    const payload=await pobierzJson('/api/baza/zbiorczy_wynik',{},'Zbiorczy wynik bazy');
    ostatniZbiorczyPayload=payload;
    zbiorczeDokumentyMap=payload.zbiorcze_dokumenty||{};
    const data=materializujZbiorczyWynik(payload);
    const pole=$('textInput'); if(pole) pole.value='';
    ustawTrybPracy('analiza');
    renderuj(data);
    const docs=Number(payload?.database_stats?.used_done_results || Object.keys(zbiorczeDokumentyMap).length || 0);
    const cards=Object.keys(payload.zbiorczy_rejestr_kart||{}).length;
    const rels=(payload.zbiorcze_referencje_sekcji?.relacje_wypowiedzi||[]).length;
    ustawStatusAktywnegoWyniku(`wynik zbiorczy bazy · ${docs} dokumentów`, true);
    ustawWidokBazy(false);
    zastosujTrybInterfejsu('uzytkownik',{restoreView:false});
    ustawAktywnyWidokProdukcyjny('wynik');
    zastosujUkladPracy('wynik');
    pokazWidok('start');
    ustawPostepBazy({label:'Wynik zbiorczy gotowy',current:`${docs} dokumentów · ${cards} unikalnych kart · ${rels} relacji`,completed:1,total:1,state:'done'});
    ustawStatusBazy(`Połączono ${docs} zakończonych analiz w jeden wynik: ${cards} unikalnych kart, ${rels} relacji. Użyj „Pobierz wyniki”, aby zapisać jeden zbiorczy JSON.`);
    const pane=$('analystPane'); if(pane) pane.scrollIntoView({behavior:'smooth',block:'start'});
    return data;
  }catch(err){
    const msg=err && err.message ? err.message : 'Nie udało się połączyć analiz.';
    ustawPostepBazy({label:'Łączenie nieudane',current:msg,completed:0,total:1,state:'cancelled'});
    ustawStatusBazy(msg,true);
    return null;
  }finally{
    if(button) button.disabled=false;
  }
}

function przygotujPlikiDoBazy(entries){
  const all=Array.from(entries||[]).map(item=>item && item.file ? item : {
    file:item,
    relativePath:(item && item.webkitRelativePath) || (item && item.name) || 'dokument.txt',
  }).filter(item=>item.file);
  const unreadable=all.filter(item=>item.readError);
  const supported=all.filter(item=>!item.readError && czyObslugiwanyPlik(item.file));
  const tooLarge=supported.filter(item=>Number(item.file.size||0)>MAKSYMALNY_ROZMIAR_PLIKU);
  const accepted=supported.filter(item=>Number(item.file.size||0)<=MAKSYMALNY_ROZMIAR_PLIKU);
  accepted.sort((a,b)=>String(a.relativePath||a.file.name).localeCompare(String(b.relativePath||b.file.name),'pl',{numeric:true,sensitivity:'base'}));
  return {
    accepted,
    skippedUnsupported:all.length-supported.length-unreadable.length,
    skippedTooLarge:tooLarge.length,
    unreadable,
  };
}

async function importujPlikiDoBazy(entries){
  if(importBazyAktywny) return;
  const prepared=przygotujPlikiDoBazy(entries);
  const feedback=$('databaseImportFeedback');if(feedback){feedback.hidden=true;feedback.textContent='';}
  const files=prepared.accepted;
  const skipped=prepared.skippedUnsupported+prepared.skippedTooLarge+prepared.unreadable.length;
  if(!files.length){
    const message=prepared.unreadable.length ? `Nie można odczytać plików. ${prepared.unreadable[0].relativePath}: ${prepared.unreadable[0].readError}` : 'Nie wybrano obsługiwanych dokumentów do 2 MB. Kopię .sqlite3 wczytaj przez „Przywróć kopię SQLite”; archiwum ZIP najpierw rozpakuj.';
    ustawStatusBazy(message,true);
    if(feedback){feedback.hidden=false;feedback.classList.add('is-error');feedback.textContent=message;}
    ustawLicznikiBazy({skipped});
    return;
  }

  const details=$('databasePanel'); if(details) details.open=true;
  zatrzymajImportBazyPoBiezacym=false;
  ustawStanImportuBazy(true);
  const batch={pending:files.length,saved:0,duplicates:0,errors:0,skipped,queued:0};
  const errorFiles=prepared.unreadable.map(item=>`${item.relativePath}: ${item.readError}`);
  ustawLicznikiBazy(batch);
  ustawPostepBazy({label:'Przekazywanie do kolejki tła',current:'Przygotowanie plików…',completed:0,total:files.length});
  ustawStatusBazy(`Przekazuję ${files.length} plików do trwałej kolejki SQLite. Po zakończeniu tego etapu analiza może działać bez otwartej strony.`);

  let completed=0;
  try{
    for(const item of files){
      if(zatrzymajImportBazyPoBiezacym) break;
      const relativePath=naprawMojibakePolski(item.relativePath||item.file.name||'dokument.txt');
      batch.pending=files.length-completed;
      ustawLicznikiBazy(batch);
      ustawPostepBazy({
        label:'Przekazywanie do kolejki tła',
        current:`Dodaję: ${relativePath}`,
        completed,
        total:files.length,
      });
      const form=new FormData();
      form.append('file',item.file,item.file.name||'dokument.txt');
      form.append('relative_path',relativePath);
      try{
        const response=await pobierzJson('/api/baza/importuj',{method:'POST',body:form},`Kolejka ${relativePath}`);
        if(response.status==='duplicate') batch.duplicates+=1;
        else batch.queued+=1;
      }catch(err){
        batch.errors+=1;
        errorFiles.push(`${relativePath}: ${err && err.message ? err.message : 'błąd'}`);
      }
      completed+=1;
      batch.pending=Math.max(0,files.length-completed);
      ustawLicznikiBazy(batch);
      ustawPostepBazy({
        label:'Przekazywanie do kolejki tła',
        current:`Przekazano: ${relativePath}`,
        completed,
        total:files.length,
      });
    }

    const cancelled=zatrzymajImportBazyPoBiezacym && completed<files.length;
    const summary=`Do kolejki dodano ${batch.queued}, duplikaty ${batch.duplicates}, błędy przesyłania ${batch.errors}, pominięto ${batch.skipped}.`;
    if(feedback){
      feedback.hidden=false;
      feedback.classList.toggle('is-error',errorFiles.length>0);
      feedback.textContent=errorFiles.length ? `${summary} Pierwszy błąd: ${errorFiles[0]}` : summary;
    }
    ustawPostepBazy({
      label:cancelled?'Dodawanie zatrzymane':'Pliki przekazane — analiza trwa w tle',
      current:cancelled?`${summary} Nieprzekazanych zostało ${files.length-completed}.`:`${summary} Możesz teraz przejść do innej aplikacji lub wygasić ekran.`,
      completed,
      total:files.length,
      state:cancelled?'cancelled':'done',
    });
    await odswiezBazeDokumentow({zachowajLiczniki:false});
    // Odświeżenie listy nie może zastąpić komunikatu błędu ogólną statystyką.
    ustawStatusBazy(errorFiles.length ? `${summary} Pierwszy błąd: ${errorFiles[0]}` : summary, errorFiles.length>0);
    void monitorujImportWTle();
  }finally{
    ustawStanImportuBazy(false);
    zatrzymajImportBazyPoBiezacym=false;
  }
}

function wpisyPakietuFolderow(entries){
  const wynik=[];
  const grupy=new Set();
  for(const raw of Array.from(entries||[])){
    const item=raw && raw.file ? raw : {file:raw,relativePath:(raw&&raw.webkitRelativePath)||''};
    if(!item.file) continue;
    const rel=String(item.relativePath || item.file.webkitRelativePath || item.file.name || '').replace(/\\/g,'/').replace(/^\/+|\/+$/g,'');
    const parts=rel.split('/').filter(Boolean);
    // Picker katalogu zwraca: folder_nadrzedny/redakcja/.../plik.
    // Pliki leżące bezpośrednio w folderze nadrzędnym pomijamy, bo nie tworzą osobnej grupy.
    if(parts.length<3) continue;
    const stripped=parts.slice(1).join('/');
    const group=parts[1];
    if(!group || !stripped.includes('/')) continue;
    grupy.add(group);
    wynik.push({file:item.file,relativePath:stripped});
  }
  return {entries:wynik,groups:Array.from(grupy).sort((a,b)=>a.localeCompare(b,'pl',{numeric:true,sensitivity:'base'}))};
}

async function importujPakietFolderowDoBazy(entries){
  const pack=wpisyPakietuFolderow(entries);
  if(pack.groups.length<2){
    ustawStatusBazy('Pakiet folderów: wybierz folder nadrzędny, który zawiera co najmniej 2 osobne podfoldery redakcji/źródeł.',true);
    return;
  }
  ustawStatusBazy(`Wykryto ${pack.groups.length} folderów w pakiecie: ${pack.groups.slice(0,8).join(', ')}${pack.groups.length>8?'…':''}. Rozpoczynam import.`);
  await importujPlikiDoBazy(pack.entries);
}

async function obsluzPakietFolderowBazyZInput(ev){
  const input=ev && ev.target ? ev.target : null;
  const files=input && input.files ? Array.from(input.files) : [];
  try{
    if(files.length) await importujPakietFolderowDoBazy(files);
  }finally{
    if(input) input.value='';
  }
}

async function obsluzFolderBazyZInput(ev){
  const input=ev && ev.target ? ev.target : null;
  const files=input && input.files ? Array.from(input.files) : [];
  try{
    if(files.length) await importujPlikiDoBazy(files);
  }finally{
    if(input) input.value='';
  }
}

async function obsluzPlikiBazyZInput(ev){
  const input=ev?.target;
  const files=Array.from(input?.files || []);
  try{
    if(files.length) await importujPlikiDoBazy(files.map(file=>({file,relativePath:`Pliki/${file.name}`})));
  }catch(error){
    ustawStatusBazy(error?.message || 'Nie udało się dodać plików.',true);
  }finally{
    if(input) input.value='';
  }
}

function otworzPlikiDoBazy(){
  if(importBazyAktywny) return;
  const input=$('databaseFilesInput');
  if(!input){ustawStatusBazy('Brak pola wyboru plików.',true);return;}
  input.value='';
  input.click();
}

async function otworzFolderDoBazy(){
  if(importBazyAktywny) return;
  const fallback=$('databaseFolderInput');
  if(!fallback){ustawStatusBazy('Brak systemowego pola wyboru folderu.',true);return;}
  if(!wymusKlasycznyPickerFolderuBazy && typeof window.showDirectoryPicker==='function'){
    try{
      ustawPostepBazy({label:'Skanowanie folderu',current:'Szukam plików również w podfolderach…',indeterminate:true});
      const handle=await window.showDirectoryPicker({id:'drogowskazy-folder-baza',mode:'read'});
      const entries=await zbierzPlikiZKataloguHandle(handle,handle.name||'',(count,rel)=>{
        ustawPostepBazy({label:'Skanowanie folderu',current:`Znaleziono ${count}: ${rel}`,indeterminate:true});
      });
      await importujPlikiDoBazy(entries);
      return;
    }catch(err){
      if(czyAnulowanoPicker(err)){
        const box=$('databaseProgress'); if(box) box.hidden=true;
        return;
      }
      if(window.DrogowskazyAndroid){
        const box=$('databaseProgress');if(box) box.hidden=true;
        ustawStatusBazy(err?.message || 'Nie można otworzyć folderu. Spróbuj ponownie albo użyj „Dodaj pliki do bazy”.',true);
        return;
      }
      wymusKlasycznyPickerFolderuBazy=true;
      const box=$('databaseProgress'); if(box) box.hidden=true;
      ustawStatusBazy('Systemowy wybór folderu nie zadziałał. Otwieram tryb zgodności Android/Chrome.');
    }
  }
  fallback.value='';
  fallback.click();
}

async function otworzPakietFolderowDoBazy(){
  if(importBazyAktywny) return;
  const fallback=$('databaseFolderPackInput');
  if(!fallback){ustawStatusBazy('Brak systemowego pola wyboru pakietu folderów.',true);return;}
  if(!wymusKlasycznyPickerPakietuFolderowBazy && typeof window.showDirectoryPicker==='function'){
    try{
      ustawPostepBazy({label:'Skanowanie pakietu folderów',current:'Szukam podfolderów i dokumentów…',indeterminate:true});
      const handle=await window.showDirectoryPicker({id:'drogowskazy-folder-pack-baza',mode:'read'});
      const entries=await zbierzPlikiZKataloguHandle(handle,handle.name||'',(count,rel)=>{
        ustawPostepBazy({label:'Skanowanie pakietu folderów',current:`Znaleziono ${count}: ${rel}`,indeterminate:true});
      });
      await importujPakietFolderowDoBazy(entries);
      return;
    }catch(err){
      if(czyAnulowanoPicker(err)){
        const box=$('databaseProgress'); if(box) box.hidden=true;
        return;
      }
      if(window.DrogowskazyAndroid){
        const box=$('databaseProgress');if(box) box.hidden=true;
        ustawStatusBazy(err?.message || 'Nie można otworzyć pakietu folderów. Spróbuj ponownie.',true);
        return;
      }
      wymusKlasycznyPickerPakietuFolderowBazy=true;
      const box=$('databaseProgress'); if(box) box.hidden=true;
      ustawStatusBazy('Systemowy wybór pakietu folderów nie zadziałał. Otwieram tryb zgodności.');
    }
  }
  fallback.value='';
  fallback.click();
}

function otworzWybieraniePliku(tryb='replace'){
  trybWczytywaniaPliku = tryb;
  const input = $('fileInput');
  if(!input){ ustawStatusPliku('Brak pola wyboru pliku w UI.', true); return; }
  input.value='';
  input.click();
}

$('analyzeBtn').addEventListener('click', () => { ustawTrybPracy('analiza'); wyslij('/api/analizuj'); });
$('suggestBtn').addEventListener('click', () => { ustawTrybPracy('sugestie'); wyslij('/api/sugestie'); });
$('reportBtn').addEventListener('click', async () => { ustawTrybPracy('raport'); await pobierzEksportRaportu(); pokazWidok('raport'); });
const textInput = $('textInput'); if(textInput) textInput.addEventListener('input', () => { ustawPodsumowanieZrodel(nazwyDokumentowZPola(textInput), textInput.value.length, false); zaplanujZapisSesji(); });
const fileInput = $('fileInput'); if(fileInput) fileInput.addEventListener('change', obsluzWyborPliku);
const fileInputMany = $('fileInputMany'); if(fileInputMany) fileInputMany.addEventListener('change', obsluzWyborWieluPlikow);
const loadFileBtn = $('loadFileBtn'); if(loadFileBtn) loadFileBtn.addEventListener('click', () => otworzWybieraniePliku('replace'));
const appendFileBtn = $('appendFileBtn'); if(appendFileBtn) appendFileBtn.addEventListener('click', () => otworzWybieraniePliku('append'));
const appendManyFilesBtn = $('appendManyFilesBtn'); if(appendManyFilesBtn) appendManyFilesBtn.addEventListener('click', () => { void otworzWielePlikow(); });
const folderInput = $('folderInput'); if(folderInput) folderInput.addEventListener('change', obsluzWyborFolderu);
const databaseFilesInput = $('databaseFilesInput'); if(databaseFilesInput) databaseFilesInput.addEventListener('change', obsluzPlikiBazyZInput);
const importFilesToDatabaseBtn = $('importFilesToDatabaseBtn'); if(importFilesToDatabaseBtn) importFilesToDatabaseBtn.addEventListener('click', otworzPlikiDoBazy);
const appendAllFilesBtn = $('appendAllFilesBtn'); if(appendAllFilesBtn) appendAllFilesBtn.addEventListener('click', () => { void otworzFolder(); });
const databaseFolderInput = $('databaseFolderInput'); if(databaseFolderInput) databaseFolderInput.addEventListener('change', obsluzFolderBazyZInput);
const databaseFolderPackInput = $('databaseFolderPackInput'); if(databaseFolderPackInput) databaseFolderPackInput.addEventListener('change', obsluzPakietFolderowBazyZInput);
const importFolderToDatabaseBtn = $('importFolderToDatabaseBtn'); if(importFolderToDatabaseBtn) importFolderToDatabaseBtn.addEventListener('click', () => { void otworzFolderDoBazy(); });
const addCompareFolderBtn = $('addCompareFolderBtn'); if(addCompareFolderBtn) addCompareFolderBtn.addEventListener('click', () => { void otworzFolderDoBazy(); });
const addCompareFolderPackBtn = $('addCompareFolderPackBtn'); if(addCompareFolderPackBtn) addCompareFolderPackBtn.addEventListener('click', () => { void otworzPakietFolderowDoBazy(); });
const cancelDatabaseImportBtn = $('cancelDatabaseImportBtn'); if(cancelDatabaseImportBtn) cancelDatabaseImportBtn.addEventListener('click', () => {
  zatrzymajImportBazyPoBiezacym=true;
  cancelDatabaseImportBtn.disabled=true;
  ustawStatusBazy('Zatrzymam dodawanie po przesłaniu bieżącego pliku. Dokumenty już zapisane w kolejce będą dalej analizowane w tle.');
});
const refreshDatabaseBtn = $('refreshDatabaseBtn'); if(refreshDatabaseBtn) refreshDatabaseBtn.addEventListener('click', () => { void odswiezBazeDokumentow(); });
const aggregateDatabaseBtn = $('aggregateDatabaseBtn'); if(aggregateDatabaseBtn) aggregateDatabaseBtn.addEventListener('click', () => { void polaczWszystkieAnalizyBazy(); });
const reanalyzeDatabaseBtn = $('reanalyzeDatabaseBtn'); if(reanalyzeDatabaseBtn) reanalyzeDatabaseBtn.addEventListener('click', () => { void przeliczCalaBazeAktualnymSilnikiem(); });
const downloadDatabaseBtn = $('downloadDatabaseBtn'); if(downloadDatabaseBtn) downloadDatabaseBtn.addEventListener('click', () => { window.location.assign('/api/baza/pobierz'); });
const databasePanelEl=$('databasePanel'); if(databasePanelEl) databasePanelEl.addEventListener('toggle',()=>{
  if(databasePanelEl.open && document.body.dataset.interfaceMode==='uzytkownik' && !document.body.classList.contains('database-focus-mode')){
    ustawWidokBazy(true); ustawAktywnyWidokProdukcyjny('baza');
  }else if(document.body.classList.contains('database-focus-mode') && !databasePanelEl.open){
    ustawWidokBazy(false); ustawAktywnyWidokProdukcyjny('wynik');
  }
});

const databaseCompareMode = $('databaseCompareMode'); if(databaseCompareMode) databaseCompareMode.addEventListener('change', () => { ostatniePorownanieBazy=null; const dl=$('downloadDatabaseComparisonBtn'); if(dl) dl.disabled=true; const box=$('databaseComparisonResult'); if(box) box.innerHTML=''; void odswiezGrupyPorownania(); });
const compareDatabaseBtn = $('compareDatabaseBtn'); if(compareDatabaseBtn) compareDatabaseBtn.addEventListener('click', () => { void porownajGrupyBazy(); });
const downloadDatabaseComparisonBtn = $('downloadDatabaseComparisonBtn'); if(downloadDatabaseComparisonBtn) downloadDatabaseComparisonBtn.addEventListener('click', pobierzPorownanieBazy);
const sameStoryTopic = $('sameStoryTopic'); if(sameStoryTopic) sameStoryTopic.addEventListener('change',()=>{ ustawRedakcjeDlaTematu(); zaplanujZapisSesji(120); });
if(sameStoryTopic){
  const searchTopicsBtn=document.createElement('button');
  searchTopicsBtn.type='button'; searchTopicsBtn.id='searchSameStoryTopicsBtn';
  searchTopicsBtn.className='secondary';
  searchTopicsBtn.textContent='Wyszukaj wspólne sprawy';
  sameStoryTopic.insertAdjacentElement('beforebegin',searchTopicsBtn);
  searchTopicsBtn.addEventListener('click',async()=>{
    if(searchTopicsBtn.disabled) return;
    searchTopicsBtn.disabled=true;
    searchTopicsBtn.textContent='Wyszukuję sprawy…';
    const progress=$('sameStoryStatus');
    if(progress) progress.textContent='Szukam spraw opisanych przez co najmniej dwie redakcje. Może to potrwać chwilę.';
    try{ const found=await odswiezTematyTejSamejSprawy();
      if(found && Array.isArray(found.topics) && found.topics.length===0){
        const empty=$('sameStoryStatus');
        if(empty) empty.textContent='Nie znaleziono pewnych wspólnych spraw. Możesz niezależnie szukać cytatów i podobnych fragmentów w sekcji poniżej.';
        const panel=$('sharedContentPanel'); if(panel) panel.open=true;
      }
      if(oczekujacyStanBazySesji) przywrocStanBazyPoOdswiezeniu(true);
    } finally { searchTopicsBtn.disabled=false; searchTopicsBtn.textContent='Wyszukaj wspólne sprawy'; }
  });
  const storyStatus=$('sameStoryStatus');
  if(storyStatus) storyStatus.textContent='Wyszukiwanie tematów tylko na żądanie. Naciśnij „Wyszukaj wspólne sprawy”.';
}
const databaseCompareModePersist=$('databaseCompareMode'); if(databaseCompareModePersist) databaseCompareModePersist.addEventListener('change',()=>zaplanujZapisSesji(120));
['databasePanel','databaseComparePanel','sameStoryComparePanel'].forEach(id=>{ const el=$(id); if(el) el.addEventListener('toggle',()=>zaplanujZapisSesji(160)); });

const compareSameStoryBtn = $('compareSameStoryBtn'); if(compareSameStoryBtn) compareSameStoryBtn.addEventListener('click', () => { void porownajTaSamaSprawe(); });
const downloadSameStoryComparisonBtn = $('downloadSameStoryComparisonBtn'); if(downloadSameStoryComparisonBtn) downloadSameStoryComparisonBtn.addEventListener('click', pobierzPorownanieTejSamejSprawy);
const loadBenchmarkSampleBtn = $('loadBenchmarkSampleBtn'); if(loadBenchmarkSampleBtn) loadBenchmarkSampleBtn.addEventListener('click', () => { void wczytajProbeBenchmarku(); });
const refreshBenchmarkStatsBtn = $('refreshBenchmarkStatsBtn'); if(refreshBenchmarkStatsBtn) refreshBenchmarkStatsBtn.addEventListener('click', () => { void odswiezWynikBenchmarku(); });
const loadGoldSampleBtn = $('loadGoldSampleBtn'); if(loadGoldSampleBtn) loadGoldSampleBtn.addEventListener('click', () => { void wczytajProbeGold(); });
const refreshGoldStatsBtn = $('refreshGoldStatsBtn'); if(refreshGoldStatsBtn) refreshGoldStatsBtn.addEventListener('click', () => { void odswiezGoldStats(); });
$('clearBtn').addEventListener('click', () => {
  clearTimeout(timerZapisuSesji); timerZapisuSesji = null;
  if($('textInput')) $('textInput').value = '';
  if($('fileInput')) $('fileInput').value = '';
  if($('fileInputMany')) $('fileInputMany').value = '';
  if($('databaseFilesInput')) $('databaseFilesInput').value = '';
  if($('folderInput')) $('folderInput').value = '';
  if($('databaseFolderInput')) $('databaseFolderInput').value = '';
  if($('databaseFolderPackInput')) $('databaseFolderPackInput').value = '';
  ['summary','readableReportSection','meaningUnitsSection','p0Section','p1Section','p2Section','candidatesSection','candidateRankingSection','candidateCategoriesSection','p5EvidenceSection','expertSuggestionsSection','actorAgencyDashboardSection','humanChecklistSection','expertSummarySection','expertReportSection','actorMapSection','agencyMapSection','candidateCategoriesSection','actorAgencyDashboardSection','humanChecklistSection','expertSummarySection','expertReportSection','suggestionsSection','visibilityAuditSection','sectionPlanBox'].forEach(id => { const el=$(id); if(el) el.innerHTML=''; });
  ['productionRelationSection','cleanTopSection','factOpinionQuoteSection','statementRelationsSection','semanticEffectivenessSection','gatesAuditSection','roleAuditSection','printReport','sectionWindowBody','databaseComparisonResult','sameStoryComparisonResult','benchmarkCard','goldCard'].forEach(id=>{const el=$(id);if(el) el.innerHTML='';});
  const dialog=$('sectionWindowDialog');if(dialog?.open) dialog.close();
  $('reportBox').textContent='';
  if($('highlightPreview')) { $('highlightPreview').innerHTML='Podświetlenia pojawią się po analizie.'; $('highlightPreview').classList.add('empty-preview'); }
  if($('highlightDetails')) $('highlightDetails').textContent='Kliknij oznaczony fragment, żeby zobaczyć szczegóły.';
  ostatnieDane=null;
  renderujPaneleUzytkownika(null);
  aktualizujPodsumowanie30Sekund(null);
  ustawStatusAktywnegoWyniku('', false);
  ostatniZbiorczyPayload=null;
  zbiorczeDokumentyMap={};
  ostatniePorownanieBazy=null;
  ostatniePorownanieTejSamejSprawy=null;
  benchmarkProba=[]; benchmarkIndex=0; goldProba=[]; goldIndex=0;
  ostatniEksport=null;
  ostatnieSpanyPodgladu=[];
  ['downloadDatabaseComparisonBtn','downloadSameStoryComparisonBtn'].forEach(id=>{const el=$(id);if(el) el.disabled=true;});
  ustawPodsumowanieZrodel([], 0, false);
  const sourceDetails = $('sourceTextDetails'); if(sourceDetails) sourceDetails.open = true;
  const previewDetails = $('textPreviewDetails'); if(previewDetails) previewDetails.open = false;
  void usunSnapshotSesji();
});

document.addEventListener('click', (ev) => {
  const btn = ev.target && ev.target.closest ? ev.target.closest('[data-inline-detail]') : null;
  if(!btn) return;
  const id = btn.dataset.inlineDetail;
  const box = id ? document.getElementById(id) : null;
  if(!box) return;
  // Aktywna implementacja
  // Wcześniej kliknięcie jednej grupy zamykało inne okna w tej samej karcie
  // przez parentGroup.querySelectorAll(...). To psuło pracę na telefonie:
  // nie dało się porównać naraz np. Instytucje + Media + Sprawczość.
  // Teraz każdy przycisk steruje tylko swoim własnym boksem.
  const nextHidden = !box.hidden ? true : false;
  box.hidden = nextHidden;
  btn.classList.toggle('active', !nextHidden);
  const openLabel = btn.dataset.openLabel || btn.textContent || 'Wyświetl w tym poziomie';
  if(!btn.dataset.openLabel) btn.dataset.openLabel = openLabel;
  btn.textContent = nextHidden ? openLabel : 'Zamknij ten szczegół';
});

document.addEventListener('click', (ev) => {
  const jump = ev.target && ev.target.closest ? ev.target.closest('.readable-jump') : null;
  if(!jump) return;
  pokazWidok(jump.dataset.readableView || 'czyste');
});

function wyczyscIdKlonu(root){
  if(!root) return root;
  root.removeAttribute && root.removeAttribute('id');
  root.querySelectorAll && root.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));
  root.querySelectorAll && root.querySelectorAll('button, input, textarea, select, a').forEach(el => {
    if(el.matches('button')) el.disabled = true;
    el.removeAttribute('autofocus');
  });
  return root;
}

function otworzSekcjeWOkienku(view){
  const dialog = $('sectionWindowDialog');
  const body = $('sectionWindowBody');
  const title = $('sectionWindowTitle');
  if(!dialog || !body || !title) return;
  const key = String(view || 'start').toLowerCase();
  const source = Array.from(document.querySelectorAll('[data-section]')).filter(sec => {
    const values = String(sec.dataset.section || '').split(/\s+/).filter(Boolean);
    return key === 'start' ? values.some(v => STARTOWE_SEKCJE.has(v)) : values.includes(key);
  });
  body.innerHTML = '';
  source.forEach(sec => {
    const clone = wyczyscIdKlonu(sec.cloneNode(true));
    clone.hidden = false;
    if('open' in clone) clone.open = true;
    body.appendChild(clone);
  });
  const menuBtn = document.querySelector(`#sectionViewMenu .view-btn[data-view="${CSS.escape(key)}"]`);
  title.textContent = menuBtn ? menuBtn.textContent.trim() : `Sekcja: ${key}`;
  if(!source.length) body.innerHTML = '<p class="empty">Brak danych w tej sekcji.</p>';
  if(typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open','');
}

document.addEventListener('click', (ev) => {
  const button = ev.target && ev.target.closest ? ev.target.closest('.readable-window') : null;
  if(!button) return;
  otworzSekcjeWOkienku(button.dataset.readableView || 'start');
});
const closeSectionWindowBtn = $('closeSectionWindowBtn');
if(closeSectionWindowBtn) closeSectionWindowBtn.addEventListener('click', () => {
  const dialog = $('sectionWindowDialog');
  if(dialog && typeof dialog.close === 'function') dialog.close(); else if(dialog) dialog.removeAttribute('open');
});
const sectionWindowDialog = $('sectionWindowDialog');
if(sectionWindowDialog) sectionWindowDialog.addEventListener('click', ev => {
  if(ev.target === sectionWindowDialog && typeof sectionWindowDialog.close === 'function') sectionWindowDialog.close();
});
const openAllBtn = $('openAllWindowsBtn'); if(openAllBtn) openAllBtn.addEventListener('click', otworzWszystkieOknaIPodpoziomy);
const openSublevelsBtn = $('openSublevelsBtn'); if(openSublevelsBtn) openSublevelsBtn.addEventListener('click', otworzPodpoziomyWidocznychSekcji);
const closeSublevelsBtn = $('closeSublevelsBtn'); if(closeSublevelsBtn) closeSublevelsBtn.addEventListener('click', zamknijPodpoziomyWidocznychSekcji);
const closeAllBtn = $('closeAllWindowsBtn'); if(closeAllBtn) closeAllBtn.addEventListener('click', zamknijWszystkieOknaWidoku);
document.querySelectorAll('.view-btn').forEach(btn => btn.addEventListener('click', () => pokazWidok(btn.dataset.view)));
document.querySelectorAll('.preview-filter').forEach(btn => btn.addEventListener('click', () => {
  if(!ostatnieDane) return;
  const next = (aktywnyWidokPodgladu === btn.dataset.previewView) ? 'wszystko' : btn.dataset.previewView;
  renderujPodgladTekstu(ostatnieDane, next);
}));
const copyReportBtn = $('copyReportBtn'); if(copyReportBtn) copyReportBtn.addEventListener('click', kopiujRaport);
const downloadMdBtn = $('downloadMdBtn'); if(downloadMdBtn) downloadMdBtn.addEventListener('click', pobierzMarkdown);
const downloadJsonBtn = $('downloadJsonBtn'); if(downloadJsonBtn) downloadJsonBtn.addEventListener('click', pobierzJsonRaportu);
const downloadResultsBtn = $('downloadResultsBtn'); if(downloadResultsBtn) downloadResultsBtn.addEventListener('click', () => { void pobierzPelneWyniki(); });
const printPdfBtn = $('printPdfBtn'); if(printPdfBtn) printPdfBtn.addEventListener('click', drukujLubZapiszPdf);
function przywrocStanBazyPoOdswiezeniu(topicsReady=false){
  const state=oczekujacyStanBazySesji;
  if(!state) return;
  const mode=$('databaseCompareMode');
  if(mode && state.compare_mode) mode.value=state.compare_mode;
  const compareSel=$('databaseCompareGroups');
  if(compareSel && Array.isArray(state.compare_groups)){
    const wanted=new Set(state.compare_groups.map(String));
    Array.from(compareSel.options).forEach(o=>o.selected=wanted.has(o.value));
    aktualizujPickerGrupPorownania();
  }
  if($('databasePanel')) $('databasePanel').open=!!state.database_panel_open;
  if($('databaseComparePanel')) $('databaseComparePanel').open=!!state.database_compare_panel_open;
  if($('sameStoryComparePanel')) $('sameStoryComparePanel').open=!!state.same_story_panel_open;

  if(state.database_compare_had_result && wybraneGrupyPorownania().length>=2 && !ostatniePorownanieBazy){
    // Przywracamy wybór, nie rozpoczynamy ponownego porównania.
  }
  if(!topicsReady) return;

  const topic=$('sameStoryTopic');
  if(topic && state.same_story_topic && Array.from(topic.options).some(o=>o.value===state.same_story_topic)){
    topic.value=state.same_story_topic;
    ustawRedakcjeDlaTematu();
  }
  const sameSel=$('sameStoryGroups');
  if(sameSel && Array.isArray(state.same_story_groups)){
    const wanted=new Set(state.same_story_groups.map(String));
    Array.from(sameSel.options).forEach(o=>o.selected=wanted.has(o.value));
    aktualizujPickerTejSamejSprawy();
  }
  if(state.same_story_had_result && wybraneGrupyTejSamejSprawy().length>=2 && !ostatniePorownanieTejSamejSprawy){
    // Przywracamy wybór, nie rozpoczynamy ponownego porównania.
  }
  oczekujacyStanBazySesji=null;
}

window.addEventListener('DOMContentLoaded', async () => {
  const restored = await przywrocSesjeLokalna();
  const backendOk = await sprawdzBackend();
  if(!backendOk){
    return;
  }
  await zaladujTrybyPracy();
  await odswiezBazeDokumentow();
  if(restored){
    ustawTrybPracy(aktywnyTrybPracy);
    if(!ostatnieDane){
      const summary = $('summary');
      if(summary) summary.innerHTML = '<div class="hint-box"><strong>Przywrócono tekst roboczy.</strong> Wynik nie był zapisany — kliknij „Analizuj”.</div>';
    }
    ustawStatusPliku('Przywrócono ostatnią lokalną sesję. Nie trzeba wczytywać dokumentów od początku.');
    return;
  }
  const tekst = String(($('textInput') && $('textInput').value) || '').trim();
  const summary = $('summary');
  if(tekst){
    // Nigdy nie uruchamiaj kosztownej analizy automatycznie po odświeżeniu/ponownym otwarciu.
    // Użytkownik musi świadomie nacisnąć „Analizuj”; trwała kolejka bazy wznawia się niezależnie.
    if(summary) summary.innerHTML = '<div class="hint-box"><strong>Przywrócono tekst, bez ponownego liczenia.</strong> Kliknij „Analizuj” tylko jeśli chcesz wykonać nową analizę ręczną.</div>';
    ustawStatusPliku('Tekst jest zachowany. Po ponownym otwarciu nic nie jest analizowane od początku automatycznie.');
  }else{
    if(summary) summary.innerHTML = '<div class="hint-box"><strong>Aplikacja gotowa.</strong> Wklej tekst albo wczytaj plik, a następnie kliknij „Analizuj”.</div>';
    ustawStatusPliku('Aplikacja gotowa · backend HTTP/JSON działa. Wklej tekst lub wczytaj plik.');
  }
});

document.addEventListener('visibilitychange', () => {
  if(document.visibilityState === 'hidden') void zapiszSesjeTeraz('visibility-hidden');
});
window.addEventListener('pagehide', () => { void zapiszSesjeTeraz('pagehide'); });


const EXPERT_VIEWS = new Set(['p0','p1','p2','kandydaci','zrodla','semantyka','audytwidocznosci','bramki','audytrole']);
const INTERFACE_MODE_STORAGE = 'drogowskazy.interfaceMode';
const USER_VIEW_STORAGE = 'drogowskazy.interfaceMode.userView';
const EXPERT_VIEW_STORAGE = 'drogowskazy.interfaceMode.expertView';
let trybInterfejsu = 'uzytkownik';
let ostatniWidokUzytkownika = 'start';
let ostatniWidokEksperta = 'p0';

function bezpiecznyWidokUzytkownika(view){
  const key=String(view||'start').toLowerCase();
  return EXPERT_VIEWS.has(key) ? 'start' : key;
}
function zapiszOstatniWidok(mode, view){
  const key=mode==='ekspert' ? EXPERT_VIEW_STORAGE : USER_VIEW_STORAGE;
  const value=mode==='ekspert' ? String(view||'p0').toLowerCase() : bezpiecznyWidokUzytkownika(view);
  try { localStorage.setItem(key, value); } catch(_err) {}
}
function odczytajOstatniWidok(mode){
  const key=mode==='ekspert' ? EXPERT_VIEW_STORAGE : USER_VIEW_STORAGE;
  try {
    const value=localStorage.getItem(key);
    if(mode==='ekspert') return value && EXPERT_VIEWS.has(value) ? value : 'p0';
    return bezpiecznyWidokUzytkownika(value || 'start');
  } catch(_err) { return mode==='ekspert' ? 'p0' : 'start'; }
}

function zapiszTrybInterfejsu(mode){
  try { localStorage.setItem(INTERFACE_MODE_STORAGE, mode); } catch(_err) {}
}
function odczytajTrybInterfejsu(){
  try { return localStorage.getItem(INTERFACE_MODE_STORAGE) === 'ekspert' ? 'ekspert' : 'uzytkownik'; }
  catch(_err) { return 'uzytkownik'; }
}
function ustawStanPrzyciskowTrybu(){
  const user=$('userModeBtn'), expert=$('expertModeBtn');
  const isExpert=trybInterfejsu==='ekspert';
  if(user){ user.classList.toggle('active', !isExpert); user.setAttribute('aria-pressed', String(!isExpert)); }
  if(expert){ expert.classList.toggle('active', isExpert); expert.setAttribute('aria-pressed', String(isExpert)); }
  const status=$('interfaceModeStatus');
  if(status) status.textContent=isExpert
    ? 'Tryb Ekspert: pełne sekcje P/R, audyty i narzędzia techniczne.'
    : 'Tryb Użytkownik: skrócony wynik, TOP, relacje i podgląd tekstu.';
}
function zastosujTrybInterfejsu(mode, options={}){
  trybInterfejsu = mode === 'ekspert' ? 'ekspert' : 'uzytkownik';
  ostatniWidokUzytkownika = odczytajOstatniWidok('uzytkownik');
  ostatniWidokEksperta = odczytajOstatniWidok('ekspert');
  document.body.classList.toggle('expert-mode', trybInterfejsu === 'ekspert');
  document.body.dataset.interfaceMode = trybInterfejsu;
  document.querySelectorAll('.view-btn').forEach(btn => btn.classList.toggle('expert-only-ui', EXPERT_VIEWS.has(String(btn.dataset.view||'').toLowerCase())));
  document.querySelectorAll('[data-section]').forEach(sec => {
    const values = String(sec.dataset.section || '').split(/\s+/).filter(Boolean);
    const expert = values.some(v => EXPERT_VIEWS.has(v));
    sec.classList.toggle('expert-only-ui', expert && !values.some(v => ['start','czyste','jednostki','relacje','fact','aktorzy','sprawczosc'].includes(v)));
  });
  ustawStanPrzyciskowTrybu();
  zapiszTrybInterfejsu(trybInterfejsu);
  if(options.restoreView !== false){
    const target=trybInterfejsu==='ekspert' ? ostatniWidokEksperta : ostatniWidokUzytkownika;
    pokazWidok(target || (trybInterfejsu==='ekspert' ? 'p0' : 'start'));
  }
  if(typeof window.odswiezDostepnoscMenuSekcji === 'function') window.odswiezDostepnoscMenuSekcji();
}
function zapamietajWidokDlaTrybu(view){
  const key=String(view||'start').toLowerCase();
  if(trybInterfejsu==='ekspert'){
    ostatniWidokEksperta=EXPERT_VIEWS.has(key) ? key : 'p0';
    zapiszOstatniWidok('ekspert', ostatniWidokEksperta);
  }else{
    ostatniWidokUzytkownika=bezpiecznyWidokUzytkownika(key);
    zapiszOstatniWidok('uzytkownik', ostatniWidokUzytkownika);
  }
}

function ukryjPusteSekcje(){
  const dynamicTargets = {
    narzedziaCard:'summary',
    readableReportCard:'readableReportSection',
    productionRelationCard:'productionRelationSection',
    meaningUnitsCard:'meaningUnitsSection',
    p0Card:'p0Section',
    p1Card:'p1Section',
    p2Card:'p2Section',
    kandydaciCard:'candidatesSection',
    cleanTopCard:'cleanTopSection',
    factOpinionQuoteCard:'factOpinionQuoteSection',
    statementRelationsCard:'statementRelationsSection',
    semanticEffectivenessCard:'semanticEffectivenessSection',
    visibilityAuditCard:'visibilityAuditSection',
    gatesAuditCard:'gatesAuditSection',
    roleAuditCard:'roleAuditSection',
    aktorzyCard:'actorMapSection',
    sprawczoscCard:'agencyMapSection',
    sugestieCard:'suggestionsSection',
    raportCard:'reportBox'
  };
  document.querySelectorAll('details.section-card').forEach(sec => {
    const targetId = dynamicTargets[sec.id];
    const content = targetId ? document.getElementById(targetId) : sec.querySelector('.collapsible-content');
    if(!content) return;
    const txt=(content.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
    const empty = !txt || txt === 'brak.' || txt.startsWith('brak ') || txt.includes('ta sekcja jest dostępna w trybie analizy');
    sec.classList.toggle('auto-empty-section', empty);
  });
}

const _renderujBazowy = renderuj;
renderuj = function(data){
  _renderujBazowy(data);
  ukryjPusteSekcje();
  zastosujTrybInterfejsu(trybInterfejsu, {restoreView:false});
};

const userModeBtn=$('userModeBtn'); if(userModeBtn) userModeBtn.addEventListener('click',()=>{ustawWidokBazy(false);zastosujTrybInterfejsu('uzytkownik',{restoreView:false});pokazWidokProdukcyjny6('wynik');});
const expertModeBtn=$('expertModeBtn'); if(expertModeBtn) expertModeBtn.addEventListener('click',()=>{ustawWidokBazy(false);zastosujTrybInterfejsu('ekspert');ustawAktywnyWidokProdukcyjny('ekspert');});
window.addEventListener('DOMContentLoaded',()=>zastosujTrybInterfejsu(odczytajTrybInterfejsu()));

const EXPERT_QUICK_TARGETS = {
  p0:'p0', p1:'p1', p2:'p2', relacje:'relacje', audyt:'semantyka'
};
const EXPERT_AUDIT_VIEWS = new Set(['semantyka','audytwidocznosci','bramki','audytrole','kategorie','dowody','audytas','checklista','podsumowanie','raportekspercki','eksperckie','sugestie','raport']);
const EXPERT_RELATION_VIEWS = new Set(['relacje','rtryb','rjezyk','raktorzy','rsprawczosc','rmikro','zrodla','fact']);

function grupaNawigacjiEksperckiej(view){
  const key=String(view||'p0').toLowerCase();
  if(['p0','p1','p2'].includes(key)) return key;
  if(EXPERT_RELATION_VIEWS.has(key)) return 'relacje';
  if(EXPERT_AUDIT_VIEWS.has(key) || ['kandydaci','ranking'].includes(key)) return 'audyt';
  return 'p0';
}
function ustawAktywnaNawigacjeEkspercka(view){
  const group=grupaNawigacjiEksperckiej(view);
  document.querySelectorAll('.expert-quick-nav-btn').forEach(btn=>{
    const active=btn.dataset.expertView===group;
    btn.classList.toggle('active',active);
    if(active) btn.setAttribute('aria-current','page'); else btn.removeAttribute('aria-current');
  });
  const status=$('expertNavStatus');
  const activeBtn=document.querySelector(`.expert-quick-nav-btn[data-expert-view="${group}"]`);
  if(status) status.textContent=`Aktywny widok ekspercki: ${activeBtn ? activeBtn.textContent.trim() : group}.`;
}

document.querySelectorAll('.expert-quick-nav-btn').forEach(btn=>btn.addEventListener('click',()=>{
  if(trybInterfejsu!=='ekspert') zastosujTrybInterfejsu('ekspert',{restoreView:false});
  const target=EXPERT_QUICK_TARGETS[btn.dataset.expertView] || 'p0';
  pokazWidok(target);
  ustawAktywnaNawigacjeEkspercka(target);
  const pane=$('analystPane'); if(pane) pane.scrollIntoView({behavior:'smooth',block:'start'});
}));

window.addEventListener('DOMContentLoaded',()=>ustawAktywnaNawigacjeEkspercka(odczytajOstatniWidok('ekspert')));

document.querySelectorAll('.user-text-filter').forEach(btn=>btn.addEventListener('click',()=>{
  if(ostatnieDane) renderujTekstUzytkownika(ostatnieDane,btn.dataset.userTextView||'wszystko');
}));

document.querySelectorAll('.production-nav-btn').forEach(btn=>btn.addEventListener('click',()=>pokazWidokProdukcyjny6(btn.dataset.productionView)));


function aktualizujPodsumowanie30Sekund(d){
 const el=document.getElementById('summary30');
 if(!el)return;
 if(!d){el.textContent='Brak danych analizy.';return;}
 const s=d.sekcje||{};
 const relacje=Array.isArray(s.relacje_wypowiedzi)?s.relacje_wypowiedzi:[];
 const top=Array.isArray(d.jednostki_znaczenia)&&d.jednostki_znaczenia.length
   ? d.jednostki_znaczenia
   : (Array.isArray(s.top_wyniki)?s.top_wyniki:[]);
 const aktorzy=Array.isArray(s.mapa_aktorow)?s.mapa_aktorow:[];
 const krotkie=top.slice(0,3).map((k,i)=>{
   const who=k.mowca||k.kto_mowi||k.speaker||'';
   const claim=k.tekst||k.fraza||k.claim||k.fragment||'';
   const txt=[who,claim].filter(Boolean).join(': ');
   return txt?`${i+1}. ${skrocTekst(txt,115)}`:'';
 }).filter(Boolean);
 const head=`${relacje.length} relacji · ${aktorzy.length} aktorów · TOP ${Math.min(top.length,5)}`;
 el.textContent=krotkie.length ? `${head}. ${krotkie.join(' | ')}` : head;
}


let ukladPracy = 'podzial';
function zastosujUkladPracy(mode){
  ukladPracy = mode === 'wynik' ? 'wynik' : 'podzial';
  document.body.classList.toggle('results-focus-mode', ukladPracy === 'wynik');
  const splitBtn = document.getElementById('splitWorkspaceBtn');
  const focusBtn = document.getElementById('resultsFocusBtn');
  if(splitBtn) splitBtn.classList.toggle('active', ukladPracy === 'podzial');
  if(focusBtn) focusBtn.classList.toggle('active', ukladPracy === 'wynik');
  if(ukladPracy === 'wynik'){
    const analyst = document.getElementById('analystPane');
    if(analyst) analyst.scrollIntoView({behavior:'smooth', block:'start'});
  }
}
const splitWorkspaceBtn = document.getElementById('splitWorkspaceBtn');
if(splitWorkspaceBtn) splitWorkspaceBtn.addEventListener('click',()=>zastosujUkladPracy('podzial'));
const resultsFocusBtn = document.getElementById('resultsFocusBtn');
if(resultsFocusBtn) resultsFocusBtn.addEventListener('click',()=>zastosujUkladPracy('wynik'));


let trybJednegoOkna = false;
function widoczneOknaWynikow(){
  return Array.from(document.querySelectorAll('#analystPane details.section-card')).filter(card => !card.hidden);
}
function ustawTrybJednegoOkna(enabled){
  trybJednegoOkna = Boolean(enabled);
  document.body.classList.toggle('single-result-window-mode', trybJednegoOkna);
  const btn = document.getElementById('singleWindowModeBtn');
  if(btn){
    btn.setAttribute('aria-pressed', String(trybJednegoOkna));
    btn.classList.toggle('active', trybJednegoOkna);
    btn.textContent = `Tryb jednego okna: ${trybJednegoOkna ? 'włączony' : 'wyłączony'}`;
  }
  if(trybJednegoOkna){
    const windows = widoczneOknaWynikow();
    const active = windows.find(card => card.open) || windows[0];
    windows.forEach(card => { card.open = card === active; });
  }
}
const singleWindowModeBtn = document.getElementById('singleWindowModeBtn');
if(singleWindowModeBtn){
  singleWindowModeBtn.addEventListener('click', () => ustawTrybJednegoOkna(!trybJednegoOkna));
}
document.addEventListener('toggle', (ev) => {
  const opened = ev.target;
  if(!trybJednegoOkna || !(opened instanceof HTMLDetailsElement) || !opened.open) return;
  if(!opened.matches('#analystPane details.section-card')) return;
  widoczneOknaWynikow().forEach(card => { if(card !== opened) card.open = false; });
}, true);


ukryjPusteSekcje();

// Zgodność nazw kontraktów: uruchomFiltrowanieMenuSekcji, uruchomFiltrowanieMenuSekcji, odswiezDostepnoscMenu.
// Jedno menu steruje aktualnymi sekcjami wyniku.
(function uruchomFiltrowanieMenuSekcji(){
  const input = document.getElementById('sectionMenuSearch');
  const clearBtn = document.getElementById('clearSectionMenuSearch');
  const groupBar = document.getElementById('sectionMenuGroups');
  const menu = document.getElementById('sectionViewMenu');
  const status = document.getElementById('sectionMenuSearchStatus');
  if(!input || !clearBtn || !groupBar || !menu || !status) return;

  const buttons = Array.from(menu.querySelectorAll('.view-btn'));
  const groupButtons = Array.from(groupBar.querySelectorAll('.section-group-btn'));
  const ALWAYS_AVAILABLE = new Set(['start','wszystko']);
  let aktywnaGrupa = 'all';
  const normalizuj = value => String(value || '')
    .toLocaleLowerCase('pl-PL')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim();

  function sekcjaMaWynik(view){
    if(ALWAYS_AVAILABLE.has(view)) return true;
    const cards = Array.from(document.querySelectorAll('#analystPane details.section-card[data-section]'))
      .filter(card => String(card.dataset.section || '').split(/\s+/).includes(view));
    return cards.some(card => !card.classList.contains('auto-empty-section'));
  }

  function odswiezDostepnosc(){
    buttons.forEach(btn => {
      const view = String(btn.dataset.view || '').toLowerCase();
      const available = sekcjaMaWynik(view);
      btn.dataset.available = available ? 'true' : 'false';
      btn.classList.toggle('section-view-unavailable', !available);
      btn.setAttribute('aria-disabled', String(!available));
    });
    filtrujMenu();
  }

  function policzGrupe(group){
    return buttons.filter(btn => {
      const belongs = group === 'all' || btn.dataset.menuGroup === group;
      return belongs && btn.dataset.available !== 'false';
    }).length;
  }

  function odswiezPrzyciskiGrup(){
    groupButtons.forEach(btn => {
      const group = btn.dataset.menuGroup || 'all';
      const count = policzGrupe(group);
      const active = group === aktywnaGrupa;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', String(active));
      const base = btn.dataset.baseLabel || btn.textContent.replace(/\s*\(\d+\)\s*$/, '').trim();
      btn.dataset.baseLabel = base;
      btn.textContent = `${base} (${count})`;
      btn.hidden = group !== 'all' && count === 0;
    });
  }

  function filtrujMenu(){
    const query = normalizuj(input.value);
    let visible = 0;
    buttons.forEach(btn => {
      const available = btn.dataset.available !== 'false';
      const haystack = normalizuj(`${btn.textContent} ${btn.dataset.view || ''}`);
      const matchSearch = !query || haystack.includes(query);
      const matchGroup = aktywnaGrupa === 'all' || btn.dataset.menuGroup === aktywnaGrupa;
      const show = available && matchSearch && matchGroup;
      btn.hidden = !show;
      if(show) visible += 1;
    });
    odswiezPrzyciskiGrup();
    const groupLabel = aktywnaGrupa === 'all'
      ? ''
      : (groupButtons.find(btn => btn.dataset.menuGroup === aktywnaGrupa)?.dataset.baseLabel || aktywnaGrupa);
    if(!query){
      status.textContent = groupLabel
        ? `Dostępne sekcje — ${groupLabel}: ${visible}.`
        : `Dostępne sekcje: ${visible}.`;
    }else if(visible){
      status.textContent = `Pasujące dostępne sekcje: ${visible}.`;
    }else{
      status.textContent = 'Brak pasującej dostępnej sekcji. Wyczyść filtr albo wybierz inną grupę.';
    }
    menu.classList.toggle('section-menu-no-results', visible === 0);
  }

  function ustawGrupe(group){
    aktywnaGrupa = group || 'all';
    filtrujMenu();
  }

  input.addEventListener('input', filtrujMenu);
  input.addEventListener('keydown', ev => {
    if(ev.key === 'Escape'){
      input.value = '';
      filtrujMenu();
      input.blur();
    }
  });
  clearBtn.addEventListener('click', () => {
    input.value = '';
    filtrujMenu();
    input.focus();
  });
  groupButtons.forEach(btn => btn.addEventListener('click', () => ustawGrupe(btn.dataset.menuGroup)));
  buttons.forEach(btn => btn.addEventListener('click', () => {
    input.value = '';
    filtrujMenu();
  }));

  window.odswiezDostepnoscMenuSekcji = odswiezDostepnosc;
  odswiezDostepnosc();
})();



(function uruchomNawigacjeAktywnejSekcji(){
  const label = document.getElementById('activeSectionLabel');
  const prev = document.getElementById('previousSectionBtn');
  const next = document.getElementById('nextSectionBtn');
  const openMenu = document.getElementById('openResultsMenuBtn');
  const menuCard = document.getElementById('resultsNavigationCard');
  if(!label || !prev || !next || !openMenu || !menuCard) return;

  let aktywnyWidok = 'start';
  function dostepnePrzyciski(){
    // Nawigacja Poprzednia/Następna nie może zależeć od aktualnie wybranej grupy
    // menu ani od tego, czy rozwijane menu jest w tej chwili zamknięte. Bierzemy
    // pełną logiczną kolejność przycisków i odrzucamy wyłącznie sekcje naprawdę
    // puste/niedostępne oraz pozycje eksperckie w trybie Użytkownik.
    return Array.from(document.querySelectorAll('#sectionViewMenu .view-btn')).filter(btn => {
      // Atrybuty prezentacyjne rozwijanego menu nie skracają kolejności strzałek.
      // Nie mogą skracać logicznej kolejności strzałek.
      if(btn.disabled || btn.getAttribute('aria-disabled') === 'true') return false;
      if(btn.classList.contains('expert-only-ui') && !document.body.classList.contains('expert-mode')) return false;
      return true;
    });
  }
  function aktualizuj(key){
    aktywnyWidok = String(key || aktywnyWidok || 'start').toLowerCase();
    const buttons = dostepnePrzyciski();
    const current = buttons.find(btn => btn.dataset.view === aktywnyWidok) || document.querySelector(`#sectionViewMenu .view-btn[data-view="${aktywnyWidok}"]`);
    label.textContent = current ? current.textContent.trim() : aktywnyWidok;
    const index = buttons.findIndex(btn => btn.dataset.view === aktywnyWidok);
    // Aktywny widok może zniknąć z listy po zmianie trybu lub wyników.
    // Strzałki nadal prowadzą do ostatniej/pierwszej dostępnej sekcji.
    prev.disabled = buttons.length === 0 || index === 0;
    next.disabled = buttons.length === 0 || (index >= 0 && index >= buttons.length - 1);
    label.dataset.view = aktywnyWidok;
  }
  function przejdz(delta){
    const buttons = dostepnePrzyciski();
    let index = buttons.findIndex(btn => btn.dataset.view === aktywnyWidok);
    // Gdy aktywny widok nie występuje już na liście (np. po zmianie trybu lub
    // odświeżeniu dostępności), zaczynamy od logicznego początku/końca zamiast
    // blokować się na P0.
    if(index < 0) index = delta > 0 ? -1 : buttons.length;
    const target = buttons[index + delta];
    if(!target) return;
    const toolbar = document.getElementById('activeSectionToolbar');
    const beforeTop = toolbar ? toolbar.getBoundingClientRect().top : null;
    pokazWidok(target.dataset.view);
    requestAnimationFrame(() => {
      if(!toolbar || beforeTop === null) return;
      const afterTop = toolbar.getBoundingClientRect().top;
      const shift = afterTop - beforeTop;
      if(Math.abs(shift) > 1) window.scrollBy({top: shift, left: 0, behavior: 'auto'});
    });
  }
  prev.addEventListener('click', () => przejdz(-1));
  next.addEventListener('click', () => przejdz(1));
  openMenu.addEventListener('click', () => {
    menuCard.open = true;
    menuCard.scrollIntoView({behavior:'smooth', block:'start'});
  });
  window.aktualizujNawigacjeAktywnejSekcji = aktualizuj;
  aktualizuj('start');
})();
