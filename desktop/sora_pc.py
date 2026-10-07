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


class Window:
    def __init__(self, root, engine, home):
        self.root, self.engine, self.home = root, engine, home
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        self.result = None
        self.analysis = None
        self.session = home / 'session.json'
        root.title('Drogowskazy Sora — PC')
        root.geometry('1150x780'); root.minsize(850, 600)
        style = ttk.Style(root)
        if 'vista' in style.theme_names(): style.theme_use('vista')
        style.configure('Treeview', rowheight=26)
        self.status = tk.StringVar(value='Gotowy')
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill='both', expand=True, padx=10,pady=10)
        self.editor_tab = ttk.Frame(self.tabs); self.tabs.add(self.editor_tab,text='Tekst i analiza')
        self.database_tab = ttk.Frame(self.tabs); self.tabs.add(self.database_tab,text='Baza dokumentów')
        self.compare_tab = ttk.Frame(self.tabs); self.tabs.add(self.compare_tab,text='Porównania')
        self.results_tab = ttk.Frame(self.tabs); self.tabs.add(self.results_tab,text='Wyniki')
        self.buttons = []
        bar = ttk.Frame(self.editor_tab); bar.pack(fill='x',pady=5)
        self.button(bar,'Wczytaj plik',self.load_text)
        self.button(bar,'Analizuj',self.analyze)
        self.button(bar,'Sugestie',lambda:self.run(lambda:engine.request('/api/sugestie',{'tekst':self.captured_text}),self.show_result))
        self.button(bar,'Raport',self.report)
        self.editor = tk.Text(self.editor_tab,wrap='word',undo=True,font=('Segoe UI',11))
        self.editor.pack(fill='both',expand=True)
        scrollbar=ttk.Scrollbar(self.editor_tab,command=self.editor.yview); scrollbar.pack(side='right',fill='y')
        self.editor.configure(yscrollcommand=scrollbar.set)
        self.stats = tk.StringVar()
        ttk.Label(self.database_tab,textvariable=self.stats).pack(anchor='w',pady=8)
        bar=ttk.Frame(self.database_tab);bar.pack(fill='x',pady=5)
        self.button(bar,'Dodaj pliki',self.import_files)
        self.button(bar,'Dodaj folder',self.import_folder)
        self.button(bar,'Odśwież',self.refresh)
        self.button(bar,'Wynik zbiorczy',lambda:self.run(lambda:engine.request('/api/baza/zbiorczy_wynik'),self.show_result))
        self.button(bar,'Kopia SQLite',self.backup)
        self.docs=ttk.Treeview(self.database_tab,columns=('name','path','state'),show='headings')
        for key,title,width in [('name','Plik',260),('path','Folder / ścieżka',480),('state','Stan',130)]:
            self.docs.heading(key,text=title);self.docs.column(key,width=width)
        self.docs.pack(fill='both',expand=True);self.docs.bind('<Double-1>',self.document)
        bar=ttk.Frame(self.database_tab);bar.pack(fill='x')
        self.offset=0
        self.button(bar,'Poprzednie 100',lambda:self.page(-100))
        self.button(bar,'Następne 100',lambda:self.page(100))
        ttk.Label(self.database_tab,text='Dwuklik na dokumencie otwiera zapisany wynik analizy.').pack(anchor='w')
        bar=ttk.Frame(self.compare_tab);bar.pack(fill='x',pady=10)
        self.mode=tk.StringVar(value='Foldery')
        ttk.Combobox(bar,textvariable=self.mode,values=['Foldery','Redakcje'],state='readonly',width=18).pack(side='left',padx=5)
        self.button(bar,'Wczytaj grupy',self.groups)
        self.button(bar,'Porównaj zaznaczone',self.compare)
        self.button(bar,'Ta sama sprawa',lambda:self.run(lambda:engine.request('/api/baza/tematy'),self.show_result))
        ttk.Label(self.compare_tab,text='Zaznacz od 2 do 10 grup (Ctrl+klik). Dane pochodzą z zapisanych analiz.').pack(anchor='w')
        self.group_list=tk.Listbox(self.compare_tab,selectmode='extended',exportselection=False,font=('Segoe UI',11));self.group_list.pack(fill='both',expand=True)
        bar=ttk.Frame(self.results_tab);bar.pack(fill='x',pady=5)
        self.button(bar,'Zapisz JSON',self.save_json)
        self.button(bar,'Zapisz TXT',self.save_text)
        self.result_tree=ttk.Treeview(self.results_tab,columns=('field','value'),show='headings')
        self.result_tree.heading('field',text='Pole');self.result_tree.heading('value',text='Wartość')
        self.result_tree.column('field',width=500);self.result_tree.column('value',width=550)
        self.result_tree.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(self.results_tab,command=self.result_tree.yview);scroll.pack(side='right',fill='y');self.result_tree.configure(yscrollcommand=scroll.set)
        self.detail=tk.Text(self.results_tab,height=6,wrap='word',font=('Segoe UI',10));self.detail.pack(fill='x')
        self.result_tree.bind('<<TreeviewSelect>>',self.selected_result)
        ttk.Label(root,textvariable=self.status).pack(fill='x',padx=10,pady=5)
        menu=tk.Menu(root);root.config(menu=menu)
        files=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Plik',menu=files)
        files.add_command(label='Wczytaj dokument',command=self.load_text)
        files.add_command(label='Dodaj folder do bazy',command=self.import_folder)
        files.add_separator();files.add_command(label='Zakończ',command=self.close)
        helpmenu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Pomoc',menu=helpmenu)
        helpmenu.add_command(label='Wersja i zgodność silnika',command=lambda:messagebox.showinfo('Silnik PHONE / PC',json.dumps(engine.identity,ensure_ascii=False,indent=2)))
        root.protocol('WM_DELETE_WINDOW',self.close)
        try:
            state=json.loads(self.session.read_text('utf-8'));self.editor.insert('1.0',state.get('text',''));root.geometry(state.get('geometry','1150x780'))
        except (OSError,ValueError,tk.TclError):pass
        root.after(100,self.poll);root.after(1000,self.refresh);root.after(5000,self.autosave)

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

    def show_result(self,result):
        self.result=result;self.result_tree.delete(*self.result_tree.get_children())
        for field,value in flatten(result):self.result_tree.insert('', 'end',values=(field,value))
        self.tabs.select(self.results_tab)

    def selected_result(self,_event):
        selected=self.result_tree.selection()
        if selected:
            field,value=self.result_tree.item(selected[0],'values');self.detail.delete('1.0','end');self.detail.insert('1.0',field+'\n\n'+value)

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

    def groups(self):
        mode='folder' if self.mode.get()=='Foldery' else 'publisher'
        def job():return self.engine.request('/api/baza/porownanie/grupy?mode='+mode)
        def done(result):
            self.group_list.delete(0,'end')
            self.group_names=[]
            for row in result.get('groups',[]):
                name=row.get('name') or row.get('group') or row.get('label')
                if name:self.group_names.append(name);self.group_list.insert('end',name)
        self.run(job,done)

    def compare(self):
        groups=[self.group_list.get(i) for i in self.group_list.curselection()]
        mode='folder' if self.mode.get()=='Foldery' else 'publisher'
        self.run(lambda:self.engine.request('/api/baza/porownanie?'+urlencode([('mode',mode)]+[('group',g) for g in groups])),self.show_result)

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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');parser.add_argument('--data-dir');args=parser.parse_args()
    home=Path(args.data_dir) if args.data_dir else home_path()
    home.mkdir(parents=True,exist_ok=True)
    lock_handle=None
    if os.name=='nt':
        import msvcrt
        lock_handle=(home/'application.lock').open('a+b')
        lock_handle.seek(0);lock_handle.write(b'0');lock_handle.flush();lock_handle.seek(0)
        try:msvcrt.locking(lock_handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            lock_handle.close()
            root=tk.Tk();root.withdraw();messagebox.showinfo('Drogowskazy Sora','Aplikacja jest już uruchomiona. Otwórz jej okno z paska zadań.');root.destroy();return
    root=tk.Tk()
    try:
        engine=Engine(home)
        window=Window(root,engine,home)
        if args.smoke_test:
            def check():
                window.editor.insert('1.0','Premier przedstawił projekt ustawy. Sejm rozpocznie debatę.')
                def job():
                    from engine import runtime_identity
                    result=engine.request('/api/analizuj',{'tekst':window.captured_text})
                    assert result.get('analysis_run_id')
                    if getattr(sys,'frozen',False):
                        reference=json.loads((Path(sys._MEIPASS)/'engine-reference.json').read_text('utf-8'))
                        def stable(value):
                            if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in {'analysis_run_id','analysis_generated_at','generated_at','utworzono','czas_generowania','timestamp'}}
                            if isinstance(value,list):return [stable(v) for v in value]
                            return value
                        for text,expected in zip(reference['cases'],reference['results']):
                            assert stable(engine.request('/api/analizuj',{'tekst':text}))==stable(expected),'Frozen EXE/PHONE result mismatch'
                    fixture=home/'smoke-document.txt'
                    fixture.write_text('Rada miasta przyjęła uchwałę. Burmistrz poinformował o decyzji.',encoding='utf-8')
                    engine.import_file(fixture,'Test/smoke-document.txt')
                    engine.stop()
                    assert engine.request('/api/baza/status')['stats']['done']==1
                    return result
                def analyzed(result):
                    window.show_result(result)
                    (home/'smoke-ok.json').write_text(json.dumps(engine.identity),encoding='utf-8');window.close()
                window.run(job,analyzed)
            root.after(100,check)
        root.mainloop()
        if lock_handle:lock_handle.close()
    except Exception:
        text=traceback.format_exc();(home/'blad_startu.txt').write_text(text,encoding='utf-8');messagebox.showerror('Drogowskazy Sora',text);root.destroy();raise

if __name__=='__main__':main()
