// Test mostu WebView2 z dokładnym interfejsem PHONE.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const src=readFileSync(new URL('./windows_adapter.js',import.meta.url),'utf8');
const names=Array.from({length:1511},(_,i)=>'dokument-'+String(i).padStart(4,'0')+'.txt');
let reads=0;
const actions={
 async select_folder(){return {name:'Prasa',root:'token-xyz',path:'',kind:'directory'}},
 async list_directory(root,path,offset,limit){
   assert.equal(root,'token-xyz');
   assert.equal(path,'');
   reads++;
   return {items:names.slice(offset,offset+limit).map(name=>
     ({name,root,path:name,kind:'file',size:5})),
     has_more:offset+limit<names.length};
 },
 async read_file(root,path){
   assert.equal(root,'token-xyz');
   assert.ok(names.includes(path));
   return {base64:Buffer.from('tekst','utf8').toString('base64')};
 }
};
const window={pywebview:{api:actions},addEventListener(){}};
const document={readyState:'complete',body:{dataset:{}},getElementById(){return null;}};
class MockFile{
 constructor(parts,name){this.name=name;this.contents=Buffer.from(parts[0]).toString('utf8');this.size=parts[0].length;}
}
runInNewContext(src,{window,document,DOMException,File:MockFile,Uint8Array,atob});
assert.equal(window.__soraWindowsBridgeInstalled,true);
const folder=await window.showDirectoryPicker();
assert.equal(folder.name,'Prasa');
const found=[];
for await(const [name,entry] of folder.entries()){
 found.push(name);
 if(found.length===1511){
   const file=await entry.getFile();
   assert.equal(file.contents,'tekst');
 }
}
assert.deepEqual(found,names);
assert.ok(reads>=6,'More than 1500 files must be enumerated');
console.log('PASS: PHONE folder UI enumerates >1500 Windows files and reads text without loss');
