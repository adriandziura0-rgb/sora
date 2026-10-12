/* Niezależne, ręczne porównywanie treści z już zapisanych artykułów. */
(() => {
  'use strict';
  const button = document.getElementById('findSharedContentBtn');
  const status = document.getElementById('sharedContentStatus');
  const output = document.getElementById('sharedContentResults');
  const groupsSelect = document.getElementById('databaseCompareGroups');
  const picker = document.getElementById('databaseComparePanel');
  const modeChoice = document.getElementById('databaseCompareMode');
  if (!button || !output || !status || !groupsSelect) return;

  const html = x => String(x ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const scope = () => {
    const checked = [...(picker?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]') || [])]
      .filter(el => el.checked && !el.disabled);
    const groups = picker?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]')?.length
      ? checked.map(x => x.dataset.compareGroup || x.value).filter(Boolean)
      : [...groupsSelect.selectedOptions].map(x => x.value).filter(Boolean);
    const mode = modeChoice?.value || 'folder';
    return {groups,mode,key:JSON.stringify([mode,groups])};
  };
  let controller = null;
  let activeKey = null;
  const render = response => {
    if (!response.matches?.length) {
      output.innerHTML = '<p class="sora-shared-empty">Nie znaleziono wystarczająco podobnych fragmentów w wybranych grupach. '
        + 'To nie dowodzi, że artykuły nie opisują tych samych wydarzeń. '
        + 'Zmień wybór folderów albo sprawdź osobno „Ta sama sprawa”.</p>';
      return;
    }
    output.innerHTML = response.matches.map((pair,i) => {
      const common = (pair.shared || []).map(x=>'<blockquote class="sora-shared-quote">'
        + html(x.text) + ' <small>('+ html(x.words) +' wspólnych słów)</small></blockquote>').join('');
      const different = (items,label) => '<div class="sora-shared-diff"><strong>'+html(label)+'</strong>'
        + (items?.length ? items.map(x=>'<p>'+html(x)+'</p>').join('') : '<p>Nie znaleziono wyraźnie innego fragmentu w przeszukiwanej części tekstu.</p>')
        + '</div>';
      return '<article class="sora-shared-card"><h4>'+ (i+1) + '. ' + html(pair.match_kind) + '</h4>'
        + '<div class="sora-shared-titles"><div><strong>'+html(pair.left.group)+'</strong><p>'
        +html(pair.left.title)+'</p><small>Dokument #'+html(pair.left.id)+'</small></div>'
        + '<div><strong>'+html(pair.right.group)+'</strong><p>'
        +html(pair.right.title)+'</p><small>Dokument #'+html(pair.right.id)+'</small></div></div>'
        + '<h5>Wspólna treść</h5>'
        + (common || '<p>Podobny temat lub tytuł; brak potwierdzonego dosłownie wspólnego fragmentu.</p>')
        + '<h5>Fragmenty różniące się sformułowaniem</h5>'
        + '<div class="sora-shared-differences">'
        + different(pair.only_left,pair.left.group) + different(pair.only_right,pair.right.group)
        + '</div></article>';
    }).join('');
  };
  button.addEventListener('click',async()=>{
    if (controller) return;
    const chosen = scope();
    if (chosen.groups.length < 2 || chosen.groups.length > 10) {
      status.textContent='Zaznacz od 2 do 10 folderów lub redakcji w „Baza / porównania”.';
      return;
    }
    const params = new URLSearchParams({mode:chosen.mode});
    chosen.groups.forEach(x=>params.append('group',x));
    const next = new AbortController();
    controller = next;
    activeKey=chosen.key;
    output.replaceChildren();
    status.textContent='Szukam wspólnych fragmentów i różnic tylko w wybranych grupach…';
    button.disabled=true;
    try {
      const response=await fetch('/api/baza/wspolna_tresc?'+params.toString(),{signal:next.signal});
      const data=await response.json();
      if(controller!==next || scope().key!==chosen.key) return;
      if(!response.ok || !data.ok) throw new Error(data.szczegoly || 'Nie udało się porównać tekstów.');
      status.textContent='Przejrzano '+data.examined_articles+' artykułów. Znaleziono '
        +(data.matches?.length||0)+' par o wspólnej treści lub zbliżonym temacie.'
        +(data.excluded_after_limit ? ' Uwaga: niektóre artykuły pominięto z powodu limitu przetwarzania.' : '');
      render(data);
    } catch (error) {
      if (error.name!=='AbortError') status.textContent='Błąd wyszukiwania: '+(error.message||'Nieznany błąd');
    } finally {
      if (controller===next) {
        controller=null;
        button.disabled=false;
      }
    }
  });
  picker?.addEventListener('change',event=>{
    if(event.target===modeChoice || event.target===groupsSelect || event.target?.matches?.('[data-compare-group]')){
      if(activeKey && activeKey!==scope().key){
        controller?.abort(); controller=null; activeKey=null;
        button.disabled=false; output.replaceChildren();
        status.textContent='Zmieniono zaznaczenie. Kliknij „Szukaj wspólnych treści i różnic”.';
      }
    }
  },true);
})();