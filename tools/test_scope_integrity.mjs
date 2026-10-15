/* Regresja A1: spójność zakresu analiz A/B i jednej sprawy bez urządzenia. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import vm from 'node:vm';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source=readFileSync(resolve(root,'runtime_source/static/app.js'),'utf8');
const mobile=readFileSync(resolve(root,'runtime_source/static/same-story-mobile.js'),'utf8');
assert.match(mobile,/JSON\.stringify\(chosen\)===JSON\.stringify\(returned\)/);
function slice(first,last){
 const start=source.indexOf(first),end=source.indexOf(last,start+first.length);
 assert.ok(start>=0&&end>start,first);
 return source.slice(start,end);
}
const code=slice('// A1 — jedynym prawidłowym wynikiem','function wybraneGrupyTejSamejSprawy(){')
 +slice('async function porownajTaSamaSprawe(){','function renderujPorownanieMultiDo(')
 +slice('function pobierzPorownanieTejSamejSprawy(){','function renderujWynikBenchmarku(');
const elements={};
for(const id of ['databaseCompareMode','databaseCompareStatus','databaseComparisonResult',
 'compareDatabaseBtn','downloadDatabaseComparisonBtn','sameStoryStatus',
 'sameStoryComparisonResult','compareSameStoryBtn','downloadSameStoryComparisonBtn','sameStoryTopic']){
 elements[id]={value:'',textContent:'',innerHTML:'',disabled:false};
}
elements.databaseCompareMode.value='folder';
elements.sameStoryTopic.value='topic_1';
let folders=['Folder A','Folder B'],groups=['TVN24','tvp.info'];
let topic='topic_1',calls=[],exports=[];
const context=vm.createContext({
 URLSearchParams,AbortController,
 ostatniePorownanieBazy:null,ostatniePorownanieTejSamejSprawy:null,
 aktywnePorownanieBazy:null,aktywnePorownanieSprawy:null,
 zakresWynikuPorownaniaBazy:'',zakresWynikuPorownaniaSprawy:'',
 $:id=>elements[id],
 wybraneGrupyPorownania:()=>folders.slice(),
 wybraneGrupyTejSamejSprawy:()=>groups.slice(),
 pobierzJson:(url,opts)=>new Promise((resolve,reject)=>calls.push({url,opts,resolve,reject})),
 renderujPorownanieMulti:p=>{elements.databaseComparisonResult.innerHTML=p.marker;},
 renderujPorownanieBazy:p=>{elements.databaseComparisonResult.innerHTML=p.marker;},
 renderujPorownanieMultiDo:(el,p)=>{el.innerHTML=p.marker;},
 renderujPorownanieBazyDo:(el,p)=>{el.innerHTML=p.marker;},
 pobierzPlik:name=>exports.push(name),
 pokazPostepOperacji:()=>1,zakonczPostepOperacji:()=>{},
 bladPostepuOperacji:()=>{},zaplanujZapisSesji:()=>{}
});
vm.runInContext(code,context);
const get=n=>vm.runInContext(n,context);
const last=()=>calls.at(-1);
const folderPayload=marker=>({ok:true,marker,mode:'folder',group_a:{name:'Folder A'},group_b:{name:'Folder B'}});
const storyPayload=marker=>({ok:true,marker,same_story:{topic_id:topic},group_a:{name:groups[0]},group_b:{name:groups[1]}});
let task=get('porownajGrupyBazy')();last().resolve(folderPayload('old'));await task;
assert.equal(elements.databaseComparisonResult.innerHTML,'old');
let errTask=get('porownajGrupyBazy')();assert.equal(elements.databaseComparisonResult.innerHTML,'');
last().reject(Error('HTTP 500'));await errTask;
assert.equal(get('ostatniePorownanieBazy'),null);
assert.equal(elements.downloadDatabaseComparisonBtn.disabled,true);
get('pobierzPorownanieBazy')();assert.equal(exports.length,0);
task=get('porownajGrupyBazy')();let old=last();
folders=['Folder A','Folder C'];const current=get('porownajGrupyBazy')(),fresh=last();
old.resolve(folderPayload('WRONG'));await task;
assert.notEqual(elements.databaseComparisonResult.innerHTML,'WRONG');
fresh.resolve(folderPayload('new'));await current;
assert.equal(elements.databaseComparisonResult.innerHTML,'new');
folders=['Folder A','Folder D'];get('pobierzPorownanieBazy')();
assert.equal(elements.databaseComparisonResult.innerHTML,'');
assert.equal(exports.length,0);
task=get('porownajTaSamaSprawe')();last().resolve(storyPayload('case'));await task;
assert.equal(elements.sameStoryComparisonResult.innerHTML,'case');
errTask=get('porownajTaSamaSprawe')();last().reject(Error('HTTP 404'));await errTask;
assert.equal(elements.sameStoryComparisonResult.innerHTML,'');
assert.equal(elements.downloadSameStoryComparisonBtn.disabled,true);
task=get('porownajTaSamaSprawe')();old=last();topic='topic_2';elements.sameStoryTopic.value=topic;
const next=get('porownajTaSamaSprawe')(),newer=last();
old.resolve({ok:true,marker:'WRONG',same_story:{topic_id:'topic_1'}});await task;
assert.notEqual(elements.sameStoryComparisonResult.innerHTML,'WRONG');
newer.resolve(storyPayload('good'));await next;
assert.equal(elements.sameStoryComparisonResult.innerHTML,'good');
groups=['TVN24','PAP'];get('pobierzPorownanieTejSamejSprawy')();
assert.equal(exports.length,0);assert.equal(elements.sameStoryComparisonResult.innerHTML,'');
task=get('porownajTaSamaSprawe')();last().resolve({ok:true,marker:'WRONG_TOPIC',same_story:{topic_id:'topic_other'}});await task;
assert.equal(get('ostatniePorownanieTejSamejSprawy'),null);
assert.equal(elements.sameStoryComparisonResult.innerHTML,'');
console.log('PASS: A1 two folders/same story: HTTP 500/404, stale result, wrong topic, changed selection, export protection');