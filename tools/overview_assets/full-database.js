/* Raport TYLKO zaznaczonych materiałów — bez zmian w pobieraniu. */
(() => {
  'use strict';
  const panel = document.getElementById('soraFullOverview');
  const opener = document.getElementById('openFullOverviewBtn');
  const back = document.getElementById('soraFullOverviewBack');
  const refresh = document.getElementById('soraFullOverviewRefresh');
  const output = document.getElementById('soraFullOverviewContent');
  const status = document.getElementById('soraFullOverviewStatus');
  if (!panel || !opener || !output) return;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, s => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[s]);
  const int = value => (Number(value) || 0).toLocaleString('pl-PL', {maximumFractionDigits: 0});
  const num = value => (Number(value) || 0).toLocaleString('pl-PL', {maximumFractionDigits: 2});
  const pct = value => num(value) + '%';

  // Mobilny widok oryginalnej tabeli porównania: każda zaznaczona grupa
  // otrzymuje własną kartę z WSZYSTKIMI metrykami, bez obcinania kolumn.
  // Tabela źródłowa jest zachowana i nadal działa na PC / w eksporcie.
  const comparisonHost = document.getElementById('databaseComparisonResult');
  const renderedTables = new WeakMap();
  function renderMobileComparison() {
    if (!comparisonHost) return;
    // Po zmianie zaznaczenia blokujemy także spóźnioną odpowiedź
    // wcześniejszego porównania, nawet jeśli przyszła już po wyczyszczeniu.
    if (comparedScope && comparedScope !== selectedScope().key) {
      clearStaleScope();
      return;
    }
    if (!comparedScope) {
      if (comparisonHost.querySelector('table.database-compare-table')) comparisonHost.replaceChildren();
      return;
    }
    comparisonHost.querySelectorAll('table.database-compare-table').forEach(table => {
      const wrapper = table.closest('.database-compare-table-wrap');
      const headers = [...(table.tHead?.rows?.[0]?.cells || [])].map(c => (c.textContent || '').trim());
      const rows = [...(table.tBodies?.[0]?.rows || [])];
      if (!wrapper || headers.length < 2 || !rows.length) return;
      const signature = headers.join('|') + '#' + rows.map(r => r.textContent || '').join('|');
      if (renderedTables.get(table) === signature) return;
      const groupCards = headers.slice(1).map((group, index) => {
        const metrics = rows.flatMap(row => {
          const cells = [...row.cells];
          if (cells.length <= index + 1) return [];
          const label = (cells[0]?.textContent || '').trim();
          const value = (cells[index + 1]?.textContent || '').trim();
          if (!label || !value) return [];
          return '<div class="sora-comparison-metric"><dt>' + esc(label) +
            '</dt><dd>' + esc(value) + '</dd></div>';
        }).join('');
        return '<article class="sora-comparison-source-card"><h5>' +
          esc(group || ('Grupa ' + (index + 1))) + '</h5><dl>' + metrics + '</dl></article>';
      }).join('');
      let cards = wrapper.previousElementSibling;
      if (!cards || !cards.classList.contains('sora-compare-mobile-cards')) {
        cards = document.createElement('div');
        cards.className = 'sora-compare-mobile-cards';
        wrapper.parentNode.insertBefore(cards, wrapper);
      }
      renderedTables.set(table, signature);
      cards.innerHTML = '<p class="sora-overview-muted">Pełne wyniki dla zaznaczonych grup — przewijaj w dół, nie w bok.</p>' +
        groupCards;
      wrapper.classList.add('sora-has-mobile-cards');
    });
  }
  let report = null;
  let active = false;
  let metric = 'relations_per_1000_words';
  let inFlight = null;
  let comparedScope = null;
  let reportScope = null;
  const choices = document.getElementById('databaseCompareGroups');
  const modeChoice = document.getElementById('databaseCompareMode');
  const comparePanel = document.getElementById('databaseComparePanel');
  const compareButton = document.getElementById('compareDatabaseBtn');
  const selectionHost = comparePanel?.querySelector('.sora-selection-choice');
  const scopeLabel = document.createElement('div');
  scopeLabel.id = 'soraSelectionScope';
  scopeLabel.className = 'sora-selection-scope';
  scopeLabel.setAttribute('role', 'status');
  scopeLabel.setAttribute('aria-live', 'polite');
  if (selectionHost) selectionHost.prepend(scopeLabel);
  // Raport można zapisać osobno od kopii bazy SQLite.
  const reportActions = panel.querySelector('.sora-overview-actions');
  const exportReport = document.createElement('button');
  exportReport.type='button';
  exportReport.id='soraDownloadSelectedReport';
  exportReport.textContent='Pobierz raport HTML';
  exportReport.disabled=true;
  const exportData = document.createElement('button');
  exportData.type='button';
  exportData.id='soraDownloadSelectedData';
  exportData.textContent='Pobierz dane raportu JSON';
  exportData.disabled=true;
  if(reportActions){ reportActions.appendChild(exportReport); reportActions.appendChild(exportData); }
  function exportFile(name,contents,mime){
    if(typeof window.pobierzPlik==='function'){
      window.pobierzPlik(name,contents,mime);
    }else{
      const a=document.createElement('a');
      const url=URL.createObjectURL(new Blob([contents],{type:mime}));
      a.href=url; a.download=name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),30000);
    }
  }
  const canExport=()=>!!report && reportScope===selectedScope().key && !inFlight;
  function updateExportButtons(){ exportReport.disabled=!canExport(); exportData.disabled=!canExport(); }
  const reportName=ext=>'Sora_raport_zaznaczonych_'+new Date().toISOString().slice(0,10)+'.'+ext;
  exportData.addEventListener('click',()=>{
    if(!canExport()) return;
    exportFile(reportName('json'),JSON.stringify({
      format:'sora_selected_report_v1',scope:{mode:selectedScope().mode,groups:selectedScope().groups},
      report
    },null,2),'application/json;charset=utf-8');
  });
  exportReport.addEventListener('click',()=>{
    if(!canExport()) return;
    const title='SORA — raport zaznaczonych artykułów';
    const content='<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>'+title+'</title>'
      +'<meta name="viewport" content="width=device-width,initial-scale=1">'
      +'<style>body{font:15px/1.5 Arial,sans-serif;max-width:960px;margin:24px auto;padding:15px;color:#102133}'
      +'h1,h2,h3{color:#155e75}.sora-overview-kpis,.sora-overview-columns,.sora-overview-facts{display:grid;grid-template-columns:1fr 1fr;gap:12px}'
      +'.sora-overview-kpi,.sora-overview-section,.sora-overview-facts>div{border:1px solid #cbd5e1;border-radius:10px;padding:12px;break-inside:avoid}'
      +'.sora-overview-kpi strong{display:block;font-size:24px}.sora-overview-bar{margin:8px 0}'
      +'.sora-overview-bar-label{display:flex;justify-content:space-between}.sora-overview-track{height:9px;background:#e2e8f0}'
      +'.sora-overview-track>div{height:9px;background:#0891b2}.sora-overview-document{display:block;padding:8px}'
      +'@media(max-width:650px){.sora-overview-kpis,.sora-overview-columns,.sora-overview-facts{grid-template-columns:1fr}}'
      +'@media print{body{margin:0;max-width:none}}</style></head><body><h1>'+title+'</h1>'
      +'<p>Wybrane grupy: '+esc(selectedScope().labels.join(', '))+'</p>'
      +'<p>Data: '+esc(new Date().toLocaleString('pl-PL'))+'. Tylko zapisane wyniki zaznaczonych grup.</p>'
      +output.innerHTML+'</body></html>';
    exportFile(reportName('html'),content,'text/html;charset=utf-8');
  });

  // Zachowujemy wyłącznie zakres i rodzaj widoku, nigdy treść artykułów
  // ani wynik analizy. Raport jest ponownie odczytywany z istniejącej SQLite.
  const VIEW_STORAGE_KEY = 'sora-zaznaczone-raport-v1';
  function readSavedView() {
    try {
      const value = JSON.parse(window.localStorage.getItem(VIEW_STORAGE_KEY) || 'null');
      if (!value || !['folder', 'publisher'].includes(value.mode) ||
          !Array.isArray(value.groups) || !['report', 'comparison', 'hidden'].includes(value.view)) return null;
      const groups = [...new Set(value.groups.filter(x => typeof x === 'string' && x.length > 0 && x.length <= 400))];
      if (!groups.length || groups.length > 10) return null;
      return {mode:value.mode, groups, view:value.view};
    } catch (_) {
      return null;  // Wyłączona pamięć WebView nie może zepsuć raportu.
    }
  }
  function saveView(view) {
    if (restoringSaved) return;
    const scope = selectedScope();
    if (!scope.groups.length || scope.groups.length > 10) return;
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify({
        mode:scope.mode, groups:scope.groups, view
      }));
    } catch (_) { /* LocalStorage może być wyłączony, działanie bieżące bez zmian. */ }
  }
  let savedView = readSavedView();
  let restoredSavedView = !savedView;
  let restoringSaved = false;
  function restoreSavedView() {
    if (restoredSavedView || restoringSaved || !savedView || !modeChoice || !choices) return;
    // Grupy w bazie są pobierane asynchronicznie. Nie odtwarzamy wyboru
    // na pustej lub niepełnej liście, żeby nie pokazać niewłaściwych danych.
    if (modeChoice.value !== savedView.mode) {
      restoringSaved = true;
      try {
        modeChoice.value = savedView.mode;
        modeChoice.dispatchEvent(new Event('change', {bubbles:true}));
      } finally { restoringSaved = false; }
      return; // Zaczekaj na przerysowanie grup po zmianie trybu.
    }
    const checkboxes = [...(comparePanel?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]') || [])];
    const options = [...choices.options].filter(o => o.value);
    const available = checkboxes.length
      ? checkboxes.map(c => c.dataset.compareGroup || c.value)
      : options.map(o => o.value);
    if (!available.length || !savedView.groups.every(name => available.includes(name))) return;
    restoringSaved = true;
    try {
      const wanted = new Set(savedView.groups);
      if (checkboxes.length) {
        // W aplikacji mobilnej checkboxy są sterowaniem źródłowym,
        // select jest używany na PC i przez oryginalny eksport.
        for (const checkbox of checkboxes) {
          checkbox.checked = wanted.has(checkbox.dataset.compareGroup || checkbox.value);
        }
      }
      for (const option of options) option.selected = wanted.has(option.value);
      choices.dispatchEvent(new Event('change', {bubbles:true}));
      // Program może zaktualizować jedną listę po synchronizacji drugiej;
      // otwieramy wynik dopiero wtedy, gdy aktualny zakres jest poprawny.
      const scope = selectedScope();
      if (scope.mode !== savedView.mode || scope.groups.length !== savedView.groups.length ||
          !scope.groups.every(name => wanted.has(name))) return;
      // In Android the list of folders may be ready before the original
      // compare button is enabled. Calling .click() on a disabled button
      // does nothing; do not mark restoration complete until it can run.
      if (savedView.view === 'comparison' && scope.groups.length >= 2 &&
          (!compareButton || compareButton.disabled)) return;
      restoredSavedView = true;
      paintScope();
      if (savedView.view === 'comparison' && scope.groups.length >= 2) {
        comparedScope = scope.key;
        compareButton.click();
      } else if (savedView.view === 'report') {
        open();
      }
    } finally {
      restoringSaved = false;
    }
  }

  const selectedScope = () => {
    const mode = modeChoice?.value || 'folder';
    const checkboxes = [...(comparePanel?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]') || [])];
    const checked = checkboxes.filter(input => input.checked && !input.disabled);
    const selected = [...(choices?.selectedOptions || [])].filter(option => option.value);
    // Na telefonie rzeczywistym sterowaniem są checkboxy, a select może
    // pozostać pusty mimo komunikatu „Zaznaczone: 2”.
    const useChecks = checkboxes.length > 0;
    const groups = useChecks ? checked.map(input => input.dataset.compareGroup || input.value).filter(Boolean)
      : selected.map(option => option.value);
    const labels = useChecks ? checked.map(input => {
      const value = input.dataset.compareGroup || input.value;
      const option = [...(choices?.options || [])].find(o => o.value === value);
      return option?.textContent?.trim() || input.closest('label')?.textContent?.trim() || value;
    }) : selected.map(option => option.textContent?.trim() || option.value);
    return {mode, groups, labels, key: JSON.stringify([mode, groups])};
  };
  function paintScope() {
    const current = selectedScope();
    if (!selectionHost) return;
    const name = current.mode === 'publisher' ? 'redakcja' : 'folder';
    const count = current.groups.length;
    const few = count % 10 >= 2 && count % 10 <= 4 && !(count % 100 >= 12 && count % 100 <= 14);
    let text = count === 0
      ? 'Nie zaznaczono ' + (name === 'folder' ? 'folderu' : 'redakcji') + '.'
      : 'Wybrano: ' + count + ' ' +
        (name === 'folder' ? (count === 1 ? 'folder' : few ? 'foldery' : 'folderów')
          : (count === 1 ? 'redakcję' : few ? 'redakcje' : 'redakcji')) + '.';
    const labels = current.labels.map(label => '<span class="sora-scope-item">' + esc(label) + '</span>').join('');
    scopeLabel.innerHTML = '<strong>Aktualny zakres: ' + esc(text) + '</strong>' +
      (labels ? '<div class="sora-scope-labels">' + labels + '</div>' : '') +
      '<p>Wyniki poniżej dotyczą tylko zaznaczonych grup. Komunikat „Brak aktywnego wyniku” u góry dotyczy wyłącznie pojedynczego artykułu.</p>';
    if (opener) opener.disabled = count === 0 || count > 10;
    updateExportButtons();
    if (refresh && !inFlight) refresh.disabled = count === 0 || count > 10;
    const existing = panel && !panel.hidden && reportScope && reportScope !== current.key;
    const staleTable = comparedScope && comparedScope !== current.key;
    if (existing || staleTable) clearStaleScope();
  }
  function clearStaleScope() {
    if (!restoringSaved) {
      // Po zmianie wybranych folderów poprzedni raport nie może wrócić
      // samoczynnie przy następnym uruchomieniu.
      saveView('hidden');
    }
    if (inFlight) { inFlight.abort(); inFlight = null; }
    reportScope = null;
    comparedScope = null;
    report = null;
    updateExportButtons();
    if (panel) panel.hidden = true;
    active = false;
    opener?.classList.remove('active');
    opener?.removeAttribute('aria-current');
    if (output) output.replaceChildren();
    if (comparisonHost) comparisonHost.replaceChildren();
    if (status) status.textContent = 'Zmieniono zaznaczenie. Poprzedni wynik ukryto. Pokaż analizę zaznaczonych.';
    const download = document.getElementById('downloadDatabaseComparisonBtn');
    if (download) download.disabled = true;
  }

  const metricTypes = [
    ['relations_per_1000_words', 'Relacje / 1000 słów', 'number'],
    ['coverage_relation_documents', 'Dokumenty z relacją', 'percent'],
    ['relation_review_rate', 'Relacje do weryfikacji', 'percent'],
    ['coverage_p1', 'P1 — pokrycie', 'percent'],
    ['coverage_p2', 'P2 — pokrycie', 'percent'],
    ['coverage_p3', 'P3 — pokrycie', 'percent'],
    ['coverage_p4', 'P4 — pokrycie', 'percent'],
    ['coverage_p5', 'P5 — pokrycie', 'percent'],
  ];

  function card(label, value, description='') {
    return '<article class="sora-overview-kpi"><span>' + esc(label) + '</span><strong>' +
      esc(value) + '</strong><small>' + esc(description) + '</small></article>';
  }
  function bars(values, kind='count') {
    if (!values.length) return '<p class="sora-overview-muted">Brak danych w zapisanych analizach.</p>';
    const max = Math.max(1, ...values.map(x => Number(x.value) || 0));
    return '<div class="sora-overview-bars">' + values.map(x => {
      const width = Math.max(0, Math.min(100, ((Number(x.value) || 0) / max) * 100));
      const value = kind === 'percent' ? pct(x.value) : kind === 'number' ? num(x.value) : int(x.value);
      return '<div class="sora-overview-bar"><div class="sora-overview-bar-label"><span>' +
        esc(x.name) + '</span><b>' + esc(value) + '</b></div><div class="sora-overview-track"><div style="width:' +
        width.toFixed(2) + '%"></div></div>' +
        (x.extra ? '<small>' + esc(x.extra) + '</small>' : '') + '</div>';
    }).join('') + '</div>';
  }
  function ranking(title, items) {
    return '<section class="sora-overview-section"><h3>' + esc(title) + '</h3>' +
      bars((items || []).map(x=>({name:x.name,value:x.count}))) + '</section>';
  }
  function metricsTable(sources, metricName, kind) {
    return bars(sources.map(s=>({
      name:s.name, value:s[metricName] ?? 0,
      extra: int(s.documents) + ' artykułów · ' + int(s.words) + ' słów'
    })), kind);
  }
  function layerRows(data) {
    const m = data.summary || {};
    const layers = [1,2,3,4,5].map(n=>({
      name:'P'+n, value:Number(m['coverage_p'+n]||0)
    }));
    return bars(layers,'percent');
  }
  function render() {
    if (!report) return;
    const stats = report.stats || {}, summary = report.summary || {}, sources = report.sources || [];
    const provenance = report.source_audit || {};
    const ready = Number(report.analyzed_articles||0);
    const opts = metricTypes.map(([key,label])=>
      '<option value="' + esc(key) + '"' + (metric===key?' selected':'') + '>' + esc(label) + '</option>'
    ).join('');
    output.innerHTML =
      '<div class="sora-overview-kpis">' +
      card('Artykuły w zaznaczeniu',int(ready),'Tylko wskazane foldery lub redakcje') +
      card('Przeanalizowane',int(ready),'Gotowe wyniki w zaznaczeniu') +
      card('Redakcje',int(report.publisher_count),'Tylko źródła z zaznaczenia') +
      card('Relacje wypowiedzi',int(summary.relations),'Suma relacji z dokumentów') +
      card('Wybrane grupy',int(report.selected_groups?.length),'Od 1 do 10 wskazanych folderów lub redakcji') +
      '</div>' +
      '<section class="sora-overview-section"><h3>Kontrola przypisania redakcji</h3>' +
      '<p class="sora-overview-muted">Źródło publikacji nie jest tym samym co źródło cytatu. Nazwa folderu nie potwierdza wydawcy.</p>' +
      '<div class="sora-overview-facts">' +
      '<div><strong>' + int(provenance.confirmed) + '</strong><span>Źródło z nagłówka lub URL</span></div>' +
      '<div><strong>' + int(provenance.indirect) + '</strong><span>Źródło tylko pośrednie</span></div>' +
      '<div><strong>' + int(provenance.unknown) + '</strong><span>Redakcja nieustalona</span></div>' +
      '</div>' +
      '<p class="sora-overview-muted">Żadna z tych kategorii nie zmienia danych w bazie. Weryfikuj artykuły przed wnioskowaniem o różnicach między redakcjami.</p></section>' +
      (ready === 0 ? '<p class="sora-overview-empty">Zaznaczone grupy nie mają jeszcze ukończonych analiz artykułów. Po ich zapisaniu wyniki pojawią się tutaj automatycznie po odświeżeniu.</p>' : '') +
      '<div class="sora-overview-columns"><section class="sora-overview-section"><h3>Wybrane materiały — pokrycie P1–P5</h3>' +
      layerRows(report) +
      '<p class="sora-overview-muted">Odsetek artykułów, w których wykryto co najmniej jeden element danej warstwy.</p></section>' +
      '<section class="sora-overview-section"><h3>Podsumowanie relacji</h3><div class="sora-overview-facts">' +
      '<div><strong>' + int(summary.documents_with_relation) + '</strong><span>Artykułów z relacją</span></div>' +
      '<div><strong>' + pct(summary.coverage_relation_documents) + '</strong><span>Pokrycie relacjami</span></div>' +
      '<div><strong>' + num(summary.relations_per_1000_words) + '</strong><span>Relacji / 1000 słów</span></div>' +
      '<div><strong>' + pct(summary.relation_review_rate) + '</strong><span>Relacji do sprawdzenia</span></div>' +
      '</div></section></div>' +
      '<section class="sora-overview-section"><h3>Porównanie wszystkich redakcji</h3>' +
      '<p class="sora-overview-muted">Raport liczy tylko zaznaczone materiały. Wybierz wskaźnik, aby zobaczyć różnice między redakcjami w tym wyborze.</p>' +
      '<label class="sora-overview-control">Wskaźnik porównania <select id="soraOverviewMetric">' + opts + '</select></label>' +
      '<div id="soraOverviewSourceBars">' + metricsTable(sources, metric, metricTypes.find(x=>x[0]===metric)?.[2]) + '</div></section>' +
      '<div class="sora-overview-columns">' +
      ranking('Najczęstsze tematy relacji',report.rankings?.topics) +
      ranking('Najczęściej wskazywani aktorzy',report.rankings?.speakers) +
      ranking('O kim / o czym mówią',report.rankings?.targets) +
      ranking('Fakt, opinia, cytat',report.rankings?.claim_types) +
      ranking('Sygnały P0 — bez oceny intencji',report.rankings?.p0) +
      ranking('Potwierdzone struktury P1',report.rankings?.p1) +
      ranking('Techniki P2',report.rankings?.p2) +
      ranking('Ramy narracyjne P3',report.rankings?.p3) +
      ranking('Strategie P4',report.rankings?.p4) +
      ranking('Diagnozy P5',report.rankings?.p5) +
      '</div>' +
      '<p class="sora-overview-muted">Brak elementów P2, P4 lub P5 oznacza brak potwierdzonych wyników w wybranych artykułach, a nie awarię silnika. P0 jest sygnałem, nie oceną intencji.</p>' +
      '<section class="sora-overview-section"><h3>Ostatnio przeanalizowane dokumenty</h3><div class="sora-overview-docs">' +
      (report.recent_documents || []).map(d =>
        '<button type="button" class="sora-overview-document" data-sora-overview-document="' + esc(d.id) + '">' +
        '<strong>' + esc(d.path || d.name || 'Dokument #' + d.id) + '</strong><span>' +
        esc(d.publisher) + ' · ' + esc(d.publisher_evidence || 'źródło niezweryfikowane') + '</span></button>'
      ).join('') +
      (ready===0 ? '<p class="sora-overview-muted">Brak ukończonych dokumentów.</p>' : '') +
      '</div></section>' +
      '<section class="sora-overview-section"><h3>Jakość danych i zastrzeżenia</h3><ul class="sora-overview-notes">' +
      (report.notes||[]).map(note=>'<li>'+esc(note)+'</li>').join('') +
      '</ul><p class="sora-overview-muted">' + esc(report.method||'') + '</p></section>';
    const selector = document.getElementById('soraOverviewMetric');
    if (selector) selector.addEventListener('change', () => {
      metric=selector.value;
      const box=document.getElementById('soraOverviewSourceBars');
      if(box)box.innerHTML=metricsTable(sources,metric,metricTypes.find(x=>x[0]===metric)?.[2]);
    });
    output.querySelectorAll('[data-sora-overview-document]').forEach(button=>{
      button.addEventListener('click',async ()=>{
        const id=Number(button.dataset.soraOverviewDocument);
        if (!id || typeof window.otworzWynikZBazy !== 'function') return;
        close();
        await window.otworzWynikZBazy(id);
      });
    });
  }
  async function load() {
    const scope = selectedScope();
    if (inFlight) inFlight.abort();
    const controller = new AbortController();
    inFlight = controller;
    if (refresh) refresh.disabled = true;
    if (status) status.textContent = 'Odczytuję wyniki wybranych materiałów…';
    try {
      if (!scope.groups.length) throw new Error('Najpierw zaznacz folder lub redakcję.');
      if (scope.groups.length > 10) throw new Error('Możesz zaznaczyć maksymalnie 10 grup.');
      const params = new URLSearchParams({mode: scope.mode});
      scope.groups.forEach(group => params.append('group', group));
      const response = await fetch('/api/baza/analiza_wybranych?' + params.toString(),
                                   {cache: 'no-store', signal: controller.signal});
      const data = await response.json();
      if (inFlight !== controller || selectedScope().key !== scope.key) return;
      if (!response.ok || !data.ok) throw new Error(data.szczegoly || data.wiadomosc || 'Nie udało się odczytać wyniku.');
      report = data;
      reportScope = scope.key;
      render();
      if (status) {
        const count = scope.groups.length;
        const few = count % 10 >= 2 && count % 10 <= 4 && !(count % 100 >= 12 && count % 100 <= 14);
        const noun = count === 1 ? 'wybrana grupa' : (few ? 'wybrane grupy' : 'wybranych grup');
        status.textContent = data.analyzed_articles === 0
          ? 'Brak ukończonych analiz w zaznaczonych materiałach. Sprawdź ich stan w bazie.'
          : 'Gotowe: ' + int(data.analyzed_articles) + ' przeanalizowanych artykułów; ' +
            int(count) + ' ' + noun + '. Pozostałe foldery pominięto.';
      }
    } catch(error) {
      if (inFlight !== controller || error?.name === 'AbortError') return;
      report = null;
      reportScope = null;
      if (status) status.textContent = 'Błąd wyświetlania: ' + (error?.message || 'Spróbuj ponownie.');
      if (output) output.innerHTML = '<p class="sora-overview-empty">Brak aktualnych wyników dla tego wyboru. Dane w bazie nie zostały zmienione.</p>';
    } finally {
      if (inFlight === controller) {
        inFlight = null;
        if (refresh) refresh.disabled = selectedScope().groups.length === 0;
        updateExportButtons();
      }
    }
  }
  function close() {
    saveView('hidden');
    if (inFlight) { inFlight.abort(); inFlight = null; }
    active = false;
    panel.hidden = true;
    opener.classList.remove('active');
    opener.removeAttribute('aria-current');
  }
  function open() {
    const scope = selectedScope();
    if (!scope.groups.length || scope.groups.length > 10) {
      paintScope();
      return;
    }
    active = true;
    panel.hidden = false;
    opener.classList.add('active');
    opener.setAttribute('aria-current', 'page');
    reportScope = scope.key;
    saveView('report');
    void load();
  }
  opener.addEventListener('click', () => active ? close() : open());
  back?.addEventListener('click', close);
  refresh?.addEventListener('click', () => void load());
  compareButton?.addEventListener('click', () => {
    const scope = selectedScope();
    if (scope.groups.length < 2 || scope.groups.length > 10) return;
    comparedScope = scope.key;
    if (!active) {
      active = true;
      panel.hidden = false;
      opener.classList.add('active');
      opener.setAttribute('aria-current', 'page');
    }
    reportScope = scope.key;
    saveView('comparison');
    void load();
  });
  comparePanel?.addEventListener('change', event => {
    if (event.target === choices || event.target === modeChoice ||
        event.target?.matches?.('[data-compare-group]')) {
      const scope = selectedScope();
      if (comparedScope && comparedScope !== scope.key) clearStaleScope();
      if (reportScope && reportScope !== scope.key) clearStaleScope();
      paintScope();
      if (!restoringSaved && event.isTrusted) saveView('hidden');
      if (!restoringSaved) restoreSavedView();
    }
  }, true);
  if (typeof MutationObserver !== 'undefined') {
    const syncChoices = () => { paintScope(); restoreSavedView(); };
    if (choices) new MutationObserver(syncChoices).observe(choices, {childList:true,subtree:true});
    const groupList = document.getElementById('databaseCompareGroupList');
    if (groupList) new MutationObserver(syncChoices).observe(groupList, {childList:true,subtree:true});
    // The base Sora UI restores checkbox and <select> states programmatically,
    // then updates this counter. Neither .checked nor option.selected emits
    // 'change', and a MutationObserver on the options cannot see properties.
    // Observe the original picker counter to keep the separate report in sync
    // after reopening an existing database session, without changing SQLite.
    const pickerCounter = document.getElementById('databaseCompareSelectedCount');
    if (pickerCounter) new MutationObserver(syncChoices).observe(pickerCounter,
      {childList:true,subtree:true,characterData:true});
    // The original application enables the compare button asynchronously.
    // Retry a pending restoration when its disabled state changes.
    if (compareButton) new MutationObserver(syncChoices).observe(compareButton,
      {attributes:true,attributeFilter:['disabled']});
  }
  paintScope();
  restoreSavedView();
  // Initialize the comparison observer LAST: selectedScope, comparedScope and
  // the surrounding handlers must be initialized before the first callback.
  if (comparisonHost && typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(renderMobileComparison);
    observer.observe(comparisonHost, {childList:true, subtree:true, characterData:true});
    renderMobileComparison();
  }
})();
