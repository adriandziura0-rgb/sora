import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {File} from 'node:buffer';
import vm from 'node:vm';

const source = readFileSync(new URL('../app/src/main/assets/native-panel.js', import.meta.url), 'utf8');
const bytes = Buffer.from('Zażółć gęślą jaźń.');
const listing = {
  root: [{name:'podfolder',kind:'directory',uri:'child'}],
  child: [{name:'tekst.txt',kind:'file',uri:'text',size:bytes.length},
    {name:'duży.txt',kind:'file',uri:'big',size:3*1024*1024},
    {name:'obraz.jpg',kind:'file',uri:'image',size:400}]
};
let picked, reads=0, printed=0;
const window = {DrogowskazyAndroid:{
  pickFolder(id){picked=id;},
  listChildren(uri){return JSON.stringify({entries:listing[uri]});},
  readFile(uri){assert.equal(uri,'text'); reads++; return JSON.stringify({base64:bytes.toString('base64')});},
  printPanel(){printed++;}
}};
vm.runInNewContext(source, {window, document:{getElementById(){return null;}}, File, DOMException, Uint8Array, Map, JSON, atob});
const pending=window.showDirectoryPicker();
window.__drogowskazyFolderResult(picked,{name:'wybrany',uri:'root'});
const root=await pending;
const children=[];
for await (const item of root.entries()) children.push(item);
assert.equal(children[0][0],'podfolder');
const files=[];
for await (const [,handle] of children[0][1].entries()) files.push(await handle.getFile());
assert.equal(await files[0].text(),'Zażółć gęślą jaźń.');
assert.equal(files[1].size,3*1024*1024);
assert.equal(files[2].size,400);
assert.equal(reads,1);
const cancel=window.showDirectoryPicker();
window.__drogowskazyFolderResult(picked,null);
await assert.rejects(cancel,e=>e.name==='AbortError');
const failure=window.showDirectoryPicker();
window.__drogowskazyFolderResult(picked,{error:'Brak dostępu do folderu.'});
await assert.rejects(failure,e=>e.name==='Error' && /Brak dostępu/.test(e.message));
const retry=window.showDirectoryPicker();
window.__drogowskazyFolderResult(picked,{name:'wybrany',uri:'root'});
assert.equal((await retry).name,'wybrany');
window.print();
assert.equal(printed,1);
console.log('PASS: folder contract, nested paths, UTF-8, oversized/unsupported file skipping, cancellation, print');
