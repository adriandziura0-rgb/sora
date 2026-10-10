/* Raport wszystkich analiz z SQLite — tylko odczyt; import i pobieranie bez zmian. */
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
      card('Artykuły w bazie',int(stats.articles),'Wszystkie rozpoznane artykuły') +
      card('Przeanalizowane',int(ready),'Zapisane wyniki z całej bazy') +
      card('Redakcje',int(report.publisher_count),'Wszystkie rozpoznane źródła') +
      card('Relacje wypowiedzi',int(summary.relations),'Suma relacji z dokumentów') +
      card('Oczekujące',int(stats.processing),'Analiza może trwać w tle') +
      card('Błędy',int(stats.error),'Rekordy wymagające kontroli') +
      card('Duplikaty importu',int(stats.duplicates),'Zdarzenia wykrycia duplikatu') +
      card('Pliki techniczne',int(stats.support_files),'Wyłączone z porównań') +
      '</div>' +
      (ready === 0 ? '<p class="sora-overview-empty">Baza nie ma jeszcze ukończonych analiz artykułów. Po ich zapisaniu wyniki pojawią się tutaj automatycznie po odświeżeniu.</p>' : '') +
      '<div class="sora-overview-columns"><section class="sora-overview-section"><h3>Cała baza — pokrycie P1–P5</h3>' +
      layerRows(report) +
      '<p class="sora-overview-muted">Odsetek artykułów, w których wykryto co najmniej jeden element danej warstwy.</p></section>' +
      '<section class="sora-overview-section"><h3>Podsumowanie relacji</h3><div class="sora-overview-facts">' +
      '<div><strong>' + int(summary.documents_with_relation) + '</strong><span>Artykułów z relacją</span></div>' +
      '<div><strong>' + pct(summary.coverage_relation_documents) + '</strong><span>Pokrycie relacjami</span></div>' +
      '<div><strong>' + num(summary.relations_per_1000_words) + '</strong><span>Relacji / 1000 słów</span></div>' +
      '<div><strong>' + pct(summary.relation_review_rate) + '</strong><span>Relacji do sprawdzenia</span></div>' +
      '</div></section></div>' +
      '<section class="sora-overview-section"><h3>Porównanie wszystkich redakcji</h3>' +
      '<p class="sora-overview-muted">Porównanie obejmuje każdą rozpoznaną redakcję, bez limitu 10 źródeł. Wybierz wskaźnik, by zobaczyć ranking znormalizowany.</p>' +
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
    if(status) status.textContent='Liczenie przekrojowych wyników całej bazy…';
    try {
      const response=await fetch('/api/baza/raport_calosciowy', {cache:'no-store'});
      const data=await response.json();
      if(!response.ok || !data.ok) throw new Error(data.wiadomosc || data.szczegoly || 'Nie udało się odczytać bazy.');
      report=data;
      render();
      if(status) status.textContent='Gotowe · ' + int(report.analyzed_articles) +
        ' artykułów z ' + int(report.publisher_count) + ' redakcji · raport bez zmiany danych.';
    } catch(error) {
      if(status) status.textContent='Błąd raportu: ' + (error?.message || 'Sprawdź backend.');
      if(!report) output.innerHTML='<p class="sora-overview-empty">Nie udało się odczytać analiz z bazy. Pobieranie i zapis dokumentów pozostają bez zmian.</p>';
    } finally {busy=false;if(refresh)refresh.disabled=false;}
  }
  function close() {
    active=false;
    panel.hidden=true;
    document.body.classList.remove('sora-full-overview-mode');
    opener.classList.remove('active');
    opener.removeAttribute('aria-current');
  }
  function open() {
    active=true;
    panel.hidden=false;
    document.body.classList.add('sora-full-overview-mode');
    opener.classList.add('active');
    opener.setAttribute('aria-current','page');
    panel.scrollIntoView({behavior:'smooth',block:'start'});
    void load();
  }
  opener.addEventListener('click',()=>active?close():open());
  back?.addEventListener('click',close);
  refresh?.addEventListener('click',()=>void load());
  document.querySelectorAll('.production-nav-btn').forEach(x=>x.addEventListener('click',close, true));
  document.getElementById('expertModeBtn')?.addEventListener('click',close,true);
  document.getElementById('userModeBtn')?.addEventListener('click',close,true);
})();
