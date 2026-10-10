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
  if (comparisonHost && typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(renderMobileComparison);
    observer.observe(comparisonHost, {childList:true, subtree:true, characterData:true});
    renderMobileComparison();
  }

  let report = null;
  let active = false;
  let busy = false;
  let metric = 'relations_per_1000_words';
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
      ranking('Ramy narracyjne P3',report.rankings?.p3) +
      '</div>' +
      '<section class="sora-overview-section"><h3>Ostatnio przeanalizowane dokumenty</h3><div class="sora-overview-docs">' +
      (report.recent_documents || []).map(d =>
        '<button type="button" class="sora-overview-document" data-sora-overview-document="' + esc(d.id) + '">' +
        '<strong>' + esc(d.path || d.name || 'Dokument #' + d.id) + '</strong><span>' +
        esc(d.publisher) + '</span></button>'
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
    if (busy) return;
    busy=true;
    if(refresh) refresh.disabled=true;
    if(status) status.textContent='Odczytuję wyniki wyłącznie zaznaczonych materiałów…';
    try {
      const mode=document.getElementById('databaseCompareMode')?.value||'folder';
      const chosen=Array.from(document.getElementById('databaseCompareGroups')?.selectedOptions||[]).map(x=>x.value).filter(Boolean);
      if(!chosen.length) throw new Error('Zaznacz co najmniej jeden folder lub redakcję.');
      if(chosen.length>10) throw new Error('Jednocześnie możesz zaznaczyć do 10 grup.');
      const params=new URLSearchParams({mode});
      chosen.forEach(name=>params.append('group',name));
      const response=await fetch('/api/baza/analiza_wybranych?'+params.toString(), {cache:'no-store'});
      const data=await response.json();
      if(!response.ok || !data.ok) throw new Error(data.wiadomosc || data.szczegoly || 'Nie udało się odczytać bazy.');
      report=data;
      render();
      if(status) status.textContent='Gotowe · ' + int(report.analyzed_articles) +
        ' artykułów z ' + int(report.selected_groups?.length) + ' zaznaczonych grup · zapisane analizy bez zmian.';
    } catch(error) {
      if(status) status.textContent='Błąd raportu: ' + (error?.message || 'Sprawdź backend.');
      report=null;output.innerHTML='<p class="sora-overview-empty">Brak wyników dla bieżącego zaznaczenia. Pobieranie i zapis dokumentów pozostają bez zmian.</p>';
    } finally {busy=false;if(refresh)refresh.disabled=false;}
  }
  function close() {
    active=false;
    panel.hidden=true;
    opener.classList.remove('active');
    opener.removeAttribute('aria-current');
  }
  function open() {
    active=true;
    panel.hidden=false;
    opener.classList.add('active');
    opener.setAttribute('aria-current','page');
    void load();
  }
  opener.addEventListener('click',()=>active?close():open());
  back?.addEventListener('click',close);
  refresh?.addEventListener('click',()=>void load());
  // Gdy porównanie kilku grup zostanie uruchomione, pokaż także pełne karty
  // analityczne obok wyboru — nie tylko istniejącą tabelę.
  document.getElementById('compareDatabaseBtn')?.addEventListener('click',()=>{
    const chosen=document.getElementById('databaseCompareGroups')?.selectedOptions?.length||0;
    if(chosen>=2 && chosen<=10) {active=true;panel.hidden=false;void load();}
  });
  document.getElementById('databaseComparePanel')?.addEventListener('change',event=>{
    const target=event.target;
    if(target?.matches?.('[data-compare-group], #databaseCompareMode')) {
      report=null;
      close();
      if(status) status.textContent='Zmieniono wybór. Kliknij „Pokaż analizę zaznaczonych”.';
      output.innerHTML='';
    }
  },true);
})();
