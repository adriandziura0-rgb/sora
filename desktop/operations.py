"""Native Windows/Tk application. Uses the unchanged Android engine asset."""
from pathlib import Path
import argparse
import json
import os
import queue
import sys
import threading
import traceback
from urllib.parse import urlencode
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from engine import Engine

EXTENSIONS = {'.txt','.md','.markdown','.csv','.json','.log','.html','.htm'}


def home_path():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'DrogowskazySoraPC'


def flatten(value, prefix=''):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(flatten(item, prefix + str(key) + ' / '))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            rows.extend(flatten(item, prefix + str(i + 1) + ' / '))
    else:
        rows.append((prefix.rstrip(' /'), str(value) if value is not None else ''))
    return rows


class Operations:
    def button(self,parent,text,command):
        button=ttk.Button(parent,text=text,command=command);button.pack(side='left',padx=3,pady=3);self.buttons.append(button)

    def source_text(self):return self.editor.get('1.0','end-1c')

    def run(self,job,done):
        if self.busy:return
        self.captured_text=self.source_text()
        self.busy=True;self.status.set('Przetwarzanie…')
        for button in self.buttons:button.configure(state='disabled')
        def work():
            try:self.events.put((done,job(),None))
            except Exception as exc:self.events.put((done,None,str(exc)))
        self.pool.submit(work)

    def poll(self):
        if self.closed:return
        try:
            while True:
                done,result,error=self.events.get_nowait()
                self.busy=False
                for button in self.buttons:button.configure(state='normal')
                if error:self.status.set('Błąd: '+error);messagebox.showerror('Drogowskazy',error)
                else:self.status.set('Gotowy');done(result)
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def load_text(self):
        path=filedialog.askopenfilename(filetypes=[('Dokumenty','*.txt *.md *.markdown *.csv *.json *.log *.html *.htm'),('Wszystkie','*.*')])
        if not path:return
        try:
            p=Path(path)
            if p.stat().st_size>2*1024*1024:raise ValueError('Limit dokumentu wynosi 2 MB')
            from clean_core.text_cleaning import decode_text_bytes
            from clean_core.document_database import prepare_document_text
            text,_=decode_text_bytes(p.read_bytes());text=prepare_document_text(text,p.suffix)
            self.editor.delete('1.0','end');self.editor.insert('1.0',text);self.tabs.select(self.editor_tab)
            self.analysis=None
        except Exception as exc:messagebox.showerror('Wczytanie pliku',str(exc))

    def analyze(self):
        text=self.source_text()
        def finished(result):self.analysis=(text,result);self.show_result(result)
        self.run(lambda:self.engine.request('/api/analizuj',{'tekst':text}),finished)

    def report(self):
        text=self.source_text();run_id=''
        if self.analysis and self.analysis[0]==text:run_id=self.analysis[1].get('analysis_run_id','')
        self.run(lambda:self.engine.request('/api/raport',{'tekst':text,'analysis_run_id':run_id}),self.show_result)

    def import_files(self):
        paths=filedialog.askopenfilenames(filetypes=[('Dokumenty','*.txt *.md *.markdown *.csv *.json *.log *.html *.htm')])
        if paths:self.import_paths([(Path(p),Path(p).name) for p in paths])

    def import_folder(self):
        folder=filedialog.askdirectory()
        if not folder:return
        parent=Path(folder)
        paths=[(p,parent.name+'/'+p.relative_to(parent).as_posix()) for p in sorted(parent.rglob('*')) if p.is_file() and p.suffix.lower() in EXTENSIONS]
        self.import_paths(paths)

    def import_paths(self,paths):
        def job():
            counts={'queued':0,'duplicate':0};errors=[]
            for p,relative in paths:
                try:
                    result=self.engine.import_file(p,relative);key=result.get('status','queued');counts[key]=counts.get(key,0)+1
                except Exception as exc:errors.append(relative+': '+str(exc))
            return {'liczniki':counts,'błędy':errors}
        def done(result):
            self.refresh();messagebox.showinfo('Import dokumentów',json.dumps(result,ensure_ascii=False,indent=2))
        self.run(job,done)

    def refresh(self):
        offset=self.offset
        def job():return (self.engine.request('/api/baza/status'),self.engine.request(f'/api/baza/dokumenty?limit=100&offset={offset}'))
        def done(result):
            status,documents=result;stats=status['stats']
            self.stats.set('Baza: '+str(stats.get('total',0))+' | Gotowe: '+str(stats.get('done',0))+' | W kolejce: '+str(stats.get('processing',0))+' | Błędy: '+str(stats.get('error',0)))
            self.docs.delete(*self.docs.get_children())
            for doc in documents['documents']:
                self.docs.insert('','end',iid=str(doc['id']),values=(doc.get('filename',''),doc.get('relative_path',''),{'done':'Gotowy','processing':'Przetwarzanie','error':'Błąd'}.get(doc.get('status'),doc.get('status'))))
            self.status.set('Baza odświeżona. Strona '+str(offset//100+1))
        self.run(job,done)

    def page(self,delta):self.offset=max(0,self.offset+delta);self.refresh()

    def document(self,_event=None):
        selected=self.docs.selection()
        if selected:
            ident=int(selected[0]);self.run(lambda:self.engine.request(f'/api/baza/dokument/{ident}/wynik'),self.show_result)

    def backup(self):
        destination=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile='drogowskazy_baza.sqlite3',filetypes=[('Baza SQLite','*.sqlite3')])
        if destination:self.run(lambda:self.engine.backup(destination),lambda _:messagebox.showinfo('Kopia bazy','Zapisano spójną kopię SQLite.'))

    def save_json(self):
        if self.result is None:return
        destination=filedialog.asksaveasfilename(defaultextension='.json',initialfile='drogowskazy_wynik.json',filetypes=[('JSON','*.json')])
        if destination:Path(destination).write_text(json.dumps(self.result,ensure_ascii=False,indent=2),encoding='utf-8')

    def save_text(self):
        if self.result is None:return
        destination=filedialog.asksaveasfilename(defaultextension='.txt',initialfile='drogowskazy_wynik.txt',filetypes=[('Tekst','*.txt')])
        if destination:Path(destination).write_text('\n'.join(f'{key}: {value}' for key,value in flatten(self.result)),encoding='utf-8')

    def autosave(self):
        if self.closed:return
        try:
            temp=self.session.with_suffix('.tmp');temp.write_text(json.dumps({'text':self.source_text(),'geometry':self.root.geometry()},ensure_ascii=False),encoding='utf-8');temp.replace(self.session)
        except OSError:pass
        self.root.after(5000,self.autosave)

    def close(self):
        if self.closed:return
        self.autosave()
        self.closed=True
        for button in self.buttons:button.configure(state='disabled')
        self.status.set('Kończenie bieżącej pracy i zapis danych…')
        def stop():
            self.pool.shutdown(wait=True);self.engine.stop();self.events.put(('closed',None,None))
        threading.Thread(target=stop,daemon=True).start()
        def check():
            try:
                while True:
                    callback,_,_=self.events.get_nowait()
                    if callback=='closed':self.root.destroy();return
            except queue.Empty:pass
            self.root.after(100,check)
        self.root.after(100,check)

