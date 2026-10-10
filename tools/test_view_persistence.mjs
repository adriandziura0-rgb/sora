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
    click(){this.dispatchEvent({type:'click',isTrusted:false});}
  };
}
async function test(saved, {late=false, storageFails=false}={}) {
  const names=['soraFullOverview','openFullOverviewBtn','soraFullOverviewBack',
    'soraFullOverviewRefresh','soraFullOverviewContent','soraFullOverviewStatus',
    'databaseComparisonResult','databaseCompareGroups','databaseCompareMode',
    'databaseComparePanel','compareDatabaseBtn'];
  const elements=Object.fromEntries(names.map(k=>[k,createElement(k)]));
  const inputs=['RedakcjaA','RedakcjaB'].map(value=>({
    value, dataset:{compareGroup:value},checked:false,disabled:false
  }));
  const initial=late?[]:inputs;
  const observers=[];
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
    createElement:()=>createElement('scope')
  };
  class FakeMutationObserver{
    constructor(callback){this.callback=callback;observers.push(this);}
    observe(){}
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
  return {elements,inputs,storage,requests};
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
const hidden=await test({...prior,view:'hidden'});
assert.equal(hidden.elements.soraFullOverview.hidden,true);
assert.equal(hidden.requests.length,0,'Explicitly hidden report must stay hidden');
const unavailable=await test({...prior,groups:['usunięty folder']});
assert.equal(unavailable.elements.soraFullOverview.hidden,true);
assert.equal(unavailable.requests.length,0,'Removed folder cannot show a different report');
const noStorage=await test(prior,{storageFails:true});
assert.equal(noStorage.elements.soraFullOverview.hidden,true);
noStorage.elements.openFullOverviewBtn.click(); // no previous scope -> harmless
assert.equal(noStorage.requests.length,0);
console.log('PASS: selected dashboard restored after reload, hidden intent respected, no stale groups, storage failure safe');
