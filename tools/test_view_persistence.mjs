// Regression: reopening Sora restores the last selected dashboard without writes.
// Node's virtual DOM only; the Android emulator test covers the real WebView.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {URLSearchParams} from 'node:url';

const source=readFileSync(new URL('./overview_assets/full-database.js',import.meta.url),'utf8');
function createElement(id) {
  return {
    id, hidden:true, value:'', options:[], disabled:false, _events:{},
    classList:{add(){},remove(){}},
    addEventListener(type,handler){(this._events[type]??=[]).push(handler);},
    dispatchEvent(event){for(const handler of this._events[event.type]??[])handler(event);},
    querySelector(){return null;},querySelectorAll(){return [];},prepend(){},
    replaceChildren(){},removeAttribute(){},setAttribute(){},
    get textContent(){return this._text??'';},set textContent(v){this._text=v;},
    get innerHTML(){return this._html??'';},set innerHTML(v){this._html=v;},
    click(){if(!this.disabled)this.dispatchEvent({type:'click',isTrusted:false});}
  };
}
async function test(saved, {late=false, storageFails=false, compareInitiallyDisabled=false}={}) {
  const names=['soraFullOverview','openFullOverviewBtn','soraFullOverviewBack',
    'soraFullOverviewRefresh','soraFullOverviewContent','soraFullOverviewStatus',
    'databaseComparisonResult','databaseCompareGroups','databaseCompareMode',
    'databaseComparePanel','compareDatabaseBtn','databaseCompareSelectedCount'];
  const elements=Object.fromEntries(names.map(k=>[k,createElement(k)]));
  const inputs=['RedakcjaA','RedakcjaB','RedakcjaC'].map(value=>({
    value, dataset:{compareGroup:value},checked:false,disabled:false
  }));
  const initial=late?[]:inputs;
  const observers=[];
  elements.compareDatabaseBtn.disabled=compareInitiallyDisabled;
  // Simulate the pre-existing comparison handler, independently of Sora's
  // added report handler. A real disabled HTML button fires neither.
  elements.compareDatabaseBtn.addEventListener('click',()=>{
    elements.databaseComparisonResult.innerHTML='<table>Przywrócone porównanie</table>';
  });
  const storage=new Map([['sora-zaznaczone-raport-v1',JSON.stringify(saved)]]);
  const localStorage={
    getItem(key){if(storageFails)throw Error('storage blocked');return storage.get(key)??null;},
    setItem(key,v){if(storageFails)throw Error('storage blocked');storage.set(key,v);}
  };
  const mode=elements.databaseCompareMode;
  mode.value='folder';
  const choices=elements.databaseCompareGroups;
  const populate=()=>{
    choices.options=inputs.map(i=>({value:i.value,textContent:i.value,selected:false}));
    elements.databaseComparePanel._groups=inputs;
  };
  elements.databaseComparePanel._groups=initial;
  if (!late)populate();
  Object.defineProperty(choices,'selectedOptions',{get(){return this.options.filter(o=>o.selected);}});
  elements.databaseComparePanel.querySelector=selector=>selector==='.sora-selection-choice'?createElement('selectionHost'):null;
  elements.databaseComparePanel.querySelectorAll=selector=>selector.includes('input[data-compare-group]')
    ?elements.databaseComparePanel._groups:[];
  const document={
    getElementById:id=>elements[id]??null,
    createElement:tag=>{const element=createElement(tag);if(tag==='div'&&!elements.scopeLabel)elements.scopeLabel=element;return element;}
  };
  class FakeMutationObserver{
    constructor(callback){this.callback=callback;observers.push(this);}
    observe(target,options){this.target=target;this.options=options;}
  }
  class FakeEvent{
    constructor(type){this.type=type;this.isTrusted=false;}
  }
  const requests=[];
  const fetch=async url=>{
    requests.push(url);
    return {ok:true,json:async()=>({
      ok:true,analyzed_articles:2,stats:{},summary:{},sources:[],
      rankings:{},selected_groups:['RedakcjaA','RedakcjaB']
    })};
  };
  const window={localStorage};
  runInNewContext(source,{
    window,document,MutationObserver:FakeMutationObserver,Event:FakeEvent,
    URLSearchParams,AbortController,fetch
  },{filename:'full-database.js'});
  if(late){
    populate();
    for(const observer of observers)observer.callback();
  }
  for(let i=0;i<8;i++)await Promise.resolve();
  return {elements,inputs,storage,requests,observers};
}
const prior={mode:'folder',groups:['RedakcjaA','RedakcjaB'],view:'report'};
const restored=await test(prior,{late:true});
assert.deepEqual(restored.inputs.filter(i=>i.checked).map(i=>i.value),prior.groups);
assert.equal(restored.elements.soraFullOverview.hidden,false);
assert.match(restored.elements.soraFullOverviewStatus.textContent,/Gotowe: 2/);
assert.equal(restored.requests.length,1,'Only the selected report is reloaded');
assert.match(restored.requests[0],/group=RedakcjaA/);
assert.match(restored.requests[0],/group=RedakcjaB/);
assert.equal(JSON.parse(restored.storage.get('sora-zaznaczone-raport-v1')).view,'report');
restored.elements.soraFullOverviewBack.click();
assert.equal(JSON.parse(restored.storage.get('sora-zaznaczone-raport-v1')).view,'hidden');
// Reproduces the Android CI failure: groups exist while the original
// compare button is still disabled during asynchronous database loading.
const pending=await test({...prior,view:'comparison'},{compareInitiallyDisabled:true});
assert.equal(pending.elements.soraFullOverview.hidden,true,
  'Do not finalize restoration through a disabled button');
assert.equal(pending.requests.length,0);
pending.elements.compareDatabaseBtn.disabled=false;
for(const observer of pending.observers.filter(o=>o.target===pending.elements.compareDatabaseBtn))
  observer.callback();
for(let i=0;i<8;i++)await Promise.resolve();
assert.equal(pending.elements.soraFullOverview.hidden,false,
  'Selected comparison must reopen after the button becomes available');
assert.match(pending.elements.databaseComparisonResult.innerHTML,/Przywrócone porównanie/);
assert.equal(pending.requests.length,1,'Reopen the selected report only once');
for(const observer of pending.observers.filter(o=>o.target===pending.elements.compareDatabaseBtn))
  observer.callback();
assert.equal(pending.requests.length,1,'No duplicate request after successful restoration');
assert.equal(JSON.parse(pending.storage.get('sora-zaznaczone-raport-v1')).view,'comparison');
const hidden=await test({...prior,view:'hidden'});
assert.equal(hidden.elements.soraFullOverview.hidden,true);
assert.equal(hidden.requests.length,0,'Explicitly hidden report must stay hidden');
// Original Sora session restore selects hidden <option>s and checks inputs
// without dispatching 'change'. Only its visible counter changes. The
// independent analytics dashboard must respond to that counter mutation.
const silentRestore=await test(null);
assert.equal(silentRestore.elements.openFullOverviewBtn.disabled,true);
for(const input of silentRestore.inputs)input.checked=true;
for(const option of silentRestore.elements.databaseCompareGroups.options)option.selected=true;
silentRestore.elements.databaseCompareSelectedCount.textContent='Wybrane: 3 · dostępne: 3 · limit: 10';
for(const observer of silentRestore.observers.filter(o=>
  o.target===silentRestore.elements.databaseCompareSelectedCount))observer.callback();
assert.equal(silentRestore.elements.openFullOverviewBtn.disabled,false,
  'Original app session restore must activate analysis of selected folders');
assert.match(silentRestore.elements.scopeLabel.innerHTML,/Wybrano: 3 foldery/,
  'Scope indicator must agree with three checked folder cards');
silentRestore.elements.openFullOverviewBtn.click();
for(let i=0;i<8;i++)await Promise.resolve();
assert.equal(silentRestore.elements.soraFullOverview.hidden,false);
assert.equal(silentRestore.requests.length,1);
assert.match(silentRestore.requests[0],/group=RedakcjaA/);
assert.match(silentRestore.requests[0],/group=RedakcjaB/);
assert.match(silentRestore.requests[0],/group=RedakcjaC/);
const unavailable=await test({...prior,groups:['usunięty folder']});
assert.equal(unavailable.elements.soraFullOverview.hidden,true);
assert.equal(unavailable.requests.length,0,'Removed folder cannot show a different report');
const noStorage=await test(prior,{storageFails:true});
assert.equal(noStorage.elements.soraFullOverview.hidden,true);
noStorage.elements.openFullOverviewBtn.click(); // no previous scope -> harmless
assert.equal(noStorage.requests.length,0);
console.log('PASS: original-app silent session restore, selected folder scope, delayed compare, hidden intent, stale groups, storage failure safe');
