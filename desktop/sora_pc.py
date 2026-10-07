"""Native, user-facing Sora desktop; unchanged engine and database contract."""
from pathlib import Path
import argparse
import json
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from engine import Engine
from operations import Operations, home_path
from presentation import SECTIONS, materialize, card_lines, evidence_range, readable_report, write_pdf

BG='#101820'; PANEL='#19242f'; FG='#edf4f6'; MUTED='#a6b6c5'; ACCENT='#6be0b5'; LINE='#2b3b4a'
LABELS={'Poprawna':'correct','Częściowa':'partial','Błędna':'false','Nie oceniono':'unknown'}


class RichView(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.text=tk.Text(self,bg=PANEL,fg=FG,font=('Segoe UI',11),wrap='word',relief='flat',padx=24,pady=20,
                          insertbackground=FG,selectbackground='#356a70',spacing1=3,spacing3=6,borderwidth=0)
        scroll=ttk.Scrollbar(self,command=self.text.yview);scroll.pack(side='right',fill='y')
        self.text.pack(fill='both',expand=True);self.text.configure(yscrollcommand=scroll.set,state='disabled')
        for name,opts in {
            'title':{'font':('Segoe UI',22,'bold'),'foreground':FG,'spacing1':10,'spacing3':14},
            'heading':{'font':('Segoe UI',14,'bold'),'foreground':ACCENT,'spacing1':16,'spacing3':8},
            'label':{'font':('Segoe UI',10,'bold'),'foreground':MUTED},
            'muted':{'foreground':MUTED,'font':('Segoe UI',10)},
            'quote':{'foreground':'#d2e8e3','lmargin1':16,'lmargin2':16,'rmargin':18,'spacing1':10,'spacing3':12},
            'warning':{'foreground':'#ffc98e'},
            'link':{'foreground':ACCENT,'underline':True},
        }.items():self.text.tag_configure(name,**opts)
        self.plain=''
    def clear(self):
        self.text.configure(state='normal');self.text.delete('1.0','end');self.plain=''
        for name in self.text.tag_names():
            if name.startswith('evidence_'):self.text.tag_delete(name)
    def add(self,text,tag=None):
        text=str(text);self.text.insert('end',text,tag or ());self.plain+=text
    def title(self,text):self.add(text+'\n','title')
    def heading(self,text):self.add(text+'\n','heading')
    def line(self,label,value):
        if label:self.add(label+'  ','label')
        self.add(str(value)+'\n')
    def finish(self):self.text.configure(state='disabled');self.text.yview_moveto(0)
    def card(self,card,index,source,callback):
        title=card.get('tytul') or card.get('canonical_name') or 'Relacja'
        if title.startswith(('TOP jednostka','Relacja wypowiedzi')):title='Wypowiedź przypisana' if card.get('kto_mowi') or card.get('mowca') else 'Wynik'
        self.heading(f'{index}. {title}')
        for label,value in card_lines(card):self.line(label,value)
        fragment=card.get('fragment') or card.get('evidence_text')
        if fragment:self.add('„'+str(fragment)+'”\n','quote')
        if card.get('wymaga_przegladu'):self.add('Do sprawdzenia przez człowieka\n','warning')
        if evidence_range(card,source):
            name=f'evidence_{index}';self.text.tag_configure(name,foreground=ACCENT,underline=True)
            self.text.insert('end','Pokaż w tekście źródłowym\n',name)
            self.text.tag_bind(name,'<Button-1>',lambda _event,c=card:callback(c))
            self.text.tag_bind(name,'<Enter>',lambda _event:self.text.configure(cursor='hand2'))
            self.text.tag_bind(name,'<Leave>',lambda _event:self.text.configure(cursor='arrow'))
        self.add('\n')


class Window(Operations):
    def __init__(self,root,engine,home):
        self.root,self.engine,self.home=root,engine,home
        self.pool=ThreadPoolExecutor(max_workers=1);self.events=queue.Queue();self.progress=queue.Queue()
        self.busy=False;self.closed=False;self.result=None;self.analysis=None;self.source_snapshot=''
        self.session=home/'session.json';self.buttons=[];self.offset=0;self.cancel_import=threading.Event()
        self.samples={'benchmark':[],'gold':[]};self.sample_index={'benchmark':0,'gold':0}
        self.status=tk.StringVar(value='Gotowy do pracy');self.stats=tk.StringVar(value='Baza dokumentów jest gotowa.')
        root.title('Drogowskazy Sora');root.geometry('1280x850');root.minsize(1020,700);root.configure(bg=BG)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',background=BG,foreground=FG,font=('Segoe UI',10))
        style.configure('TFrame',background=BG);style.configure('TLabel',background=BG,foreground=FG)
        style.configure('Muted.TLabel',foreground=MUTED);style.configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        style.configure('Sub.TLabel',foreground=MUTED,font=('Segoe UI',10))
        style.configure('TButton',background=LINE,foreground=FG,borderwidth=0,padding=(14,9))
        style.map('TButton',background=[('active','#3a5265'),('disabled','#202b35')],foreground=[('disabled','#79858e')])
        style.configure('Accent.TButton',background=ACCENT,foreground='#0d2520',font=('Segoe UI',10,'bold'))
        style.map('Accent.TButton',background=[('active','#8debc9'),('disabled',LINE)])
        style.configure('Nav.TButton',background=BG,anchor='w',padding=(18,12),font=('Segoe UI',11))
        style.configure('Active.Nav.TButton',background=PANEL,foreground=ACCENT)
        style.configure('TNotebook',background=BG,borderwidth=0);style.configure('TNotebook.Tab',background=LINE,padding=(14,8))
        style.map('TNotebook.Tab',background=[('selected',PANEL)],foreground=[('selected',ACCENT)])
        style.layout('Pages.TNotebook.Tab',[])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=FG,rowheight=32,borderwidth=0)
        style.configure('Treeview.Heading',background=LINE,foreground=FG,padding=8)
        style.map('Treeview',background=[('selected','#34534f')],foreground=[('selected',FG)])
        style.configure('TEntry',fieldbackground=PANEL,foreground=FG,insertcolor=FG)
        style.configure('TCombobox',fieldbackground=PANEL,foreground=FG,arrowcolor=FG)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',FG)])
        sidebar=ttk.Frame(root,width=214);sidebar.pack(side='left',fill='y',padx=(12,0),pady=18);sidebar.pack_propagate(False)
        ttk.Label(sidebar,text='SORA',font=('Segoe UI',25,'bold'),foreground=ACCENT).pack(anchor='w',padx=18,pady=(8,0))
        ttk.Label(sidebar,text='DROGOWSKAZY',style='Muted.TLabel').pack(anchor='w',padx=18,pady=(0,25))
        main=ttk.Frame(root);main.pack(side='left',fill='both',expand=True,padx=20,pady=18)
        self.page_title=tk.StringVar();self.page_subtitle=tk.StringVar()
        ttk.Label(main,textvariable=self.page_title,style='Title.TLabel').pack(anchor='w')
        ttk.Label(main,textvariable=self.page_subtitle,style='Sub.TLabel',wraplength=850).pack(anchor='w',pady=(3,14))
        self.tabs=ttk.Notebook(main,style='Pages.TNotebook');self.tabs.pack(fill='both',expand=True)
        self.pages={};self.nav={}
        descriptions={
          'editor':('Dokument','Wczytaj tekst albo wklej treść. Analiza, raport i eksport korzystają z jednego wyniku.'),
          'result':('Wynik analizy','Wnioski, relacje i dowody. Wybierz kartę, aby przejść do jej fragmentu źródłowego.'),
          'database':('Baza dokumentów','Trwała kolejka, foldery i zapisane analizy. Dwuklik otwiera wynik dokumentu.'),
          'compare':('Porównania','Porównaj od 2 do 10 folderów lub redakcji na podstawie zapisanych artykułów.'),
          'topics':('Ta sama sprawa','Porównaj sposób przedstawienia jednego tematu przez różne redakcje.'),
          'quality':('Kontrola jakości','Ręczny benchmark relacji i kompletne dokumenty referencyjne GOLD.'),
          'reports':('Raport i eksport','Czytelny raport oraz zapis Markdown, PDF i JSON.'),
        }
        for key,(name,subtitle) in descriptions.items():
            frame=ttk.Frame(self.tabs);self.tabs.add(frame,text=name);self.pages[key]=frame
            button=ttk.Button(sidebar,text=name,style='Nav.TButton',command=lambda k=key:self.navigate(k));button.pack(fill='x',pady=3);self.nav[key]=button
        ttk.Label(sidebar,text='Silnik wspólny z telefonem\nDrogowskazy 4.5.12',style='Muted.TLabel',wraplength=185).pack(side='bottom',anchor='w',padx=16,pady=15)
        self.descriptions=descriptions
        self.editor_tab=self.pages['editor'];self.results_tab=self.pages['result'];self.database_tab=self.pages['database']
        self.build_editor();self.build_results();self.build_database();self.build_compare();self.build_topics();self.build_quality();self.build_reports()
        footer=ttk.Frame(main);footer.pack(fill='x',pady=(10,0));self.busy_bar=ttk.Progressbar(footer,mode='indeterminate',length=100);self.busy_bar.pack(side='right')
        ttk.Label(footer,textvariable=self.status,style='Muted.TLabel').pack(side='left')
        self.tabs.bind('<<NotebookTabChanged>>',lambda _e:self.sync_navigation())
        menu=tk.Menu(root);root.config(menu=menu)
        filemenu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Plik',menu=filemenu)
        for name,action in [('Wczytaj dokument',self.load_text),('Dodaj pliki do bazy',self.import_files),('Dodaj folder do bazy',self.import_folder),('Kopia bazy SQLite',self.backup)]:filemenu.add_command(label=name,command=action)
        filemenu.add_separator();filemenu.add_command(label='Zakończ',command=self.close)
        helpmenu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Pomoc',menu=helpmenu)
        helpmenu.add_command(label='Wersja i zgodność silnika',command=lambda:messagebox.showinfo('Silnik PHONE / PC',f"Drogowskazy {engine.version}\nWspólny silnik telefonu i PC.\n\nOdcisk silnika:\n{engine.identity['engine_sha256']}\n\nBaza:\n{home/'data/drogowskazy.sqlite3'}"))
        root.protocol('WM_DELETE_WINDOW',self.close)
        try:
            state=json.loads(self.session.read_text('utf-8'));self.editor.insert('1.0',state.get('text',''));root.geometry(state.get('geometry','1280x850'))
        except (OSError,ValueError,tk.TclError):pass
        self.navigate('editor');root.after(100,self.poll);root.after(400,self.refresh);root.after(5000,self.autosave);root.after(2000,self.tick)

    def navigate(self,key):self.tabs.select(self.pages[key]);self.sync_navigation()
    def sync_navigation(self):
        selected=self.tabs.select()
        for key,page in self.pages.items():
            active=str(page)==selected;self.nav[key].configure(style='Active.Nav.TButton' if active else 'Nav.TButton')
            if active:self.page_title.set(self.descriptions[key][0]);self.page_subtitle.set(self.descriptions[key][1])
    def bar(self,parent):
        bar=ttk.Frame(parent);bar.pack(fill='x',pady=(0,10));return bar
    def button(self,parent,text,command,accent=False):
        button=ttk.Button(parent,text=text,command=command,style='Accent.TButton' if accent else 'TButton');button.pack(side='left',padx=(0,7),pady=3);self.buttons.append(button);return button
    def text_widget(self,parent,height=8):
        widget=tk.Text(parent,height=height,wrap='word',bg=PANEL,fg=FG,insertbackground=FG,selectbackground='#356a70',font=('Segoe UI',11),relief='flat',padx=18,pady=14,undo=True)
        return widget
    def tree(self,parent,columns):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show='headings')
        for key,title,width in columns:tree.heading(key,text=title);tree.column(key,width=width,minwidth=70)
        y=ttk.Scrollbar(frame,command=tree.yview);y.pack(side='right',fill='y');tree.pack(fill='both',expand=True);tree.configure(yscrollcommand=y.set)
        x=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);x.pack(fill='x');tree.configure(xscrollcommand=x.set)
        return tree

    def build_editor(self):
        bar=self.bar(self.editor_tab);self.button(bar,'Wczytaj plik',self.load_text);self.button(bar,'Analizuj tekst',self.analyze,True)
        self.button(bar,'Sugestie',self.suggestions);self.button(bar,'Utwórz raport',self.report)
        ttk.Label(self.editor_tab,text='Tekst źródłowy',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=8)
        frame=ttk.Frame(self.editor_tab);frame.pack(fill='both',expand=True)
        self.editor=self.text_widget(frame,height=20);scroll=ttk.Scrollbar(frame,command=self.editor.yview);scroll.pack(side='right',fill='y');self.editor.pack(fill='both',expand=True);self.editor.configure(yscrollcommand=scroll.set)
        ttk.Label(self.editor_tab,text='TXT, MD, CSV, JSON, LOG i HTML · do 2 MB na dokument',style='Muted.TLabel').pack(anchor='w',pady=10)

    def build_results(self):
        bar=self.bar(self.results_tab);self.result_stats=tk.StringVar(value='Wczytaj dokument i wybierz „Analizuj tekst”.')
        ttk.Label(bar,textvariable=self.result_stats,foreground=ACCENT).pack(side='left')
        self.result_modes=ttk.Notebook(self.results_tab);self.result_modes.pack(fill='both',expand=True)
        self.result_views={}
        for key,name in [('summary','Wnioski'),('relations','Wypowiedzi'),('fact','Fakty / opinie / cytaty'),('actors','Aktorzy'),('sources','Źródła'),('expert','Ekspert')]:
            frame=ttk.Frame(self.result_modes);self.result_modes.add(frame,text=name)
            if key=='expert':
                self.expert_mode=tk.StringVar();self.expert_selector=ttk.Combobox(frame,textvariable=self.expert_mode,state='readonly')
                self.expert_selector.pack(fill='x',pady=8);self.expert_selector.bind('<<ComboboxSelected>>',lambda _e:self.render_expert())
            view=RichView(frame);view.pack(fill='both',expand=True);self.result_views[key]=view
            view.clear();view.title('Jeszcze nie ma wyniku');view.add('Uruchom analizę dokumentu lub otwórz zapisany wynik z bazy.','muted');view.finish()
        self.source_panel=ttk.Labelframe(self.results_tab,text='Fragment źródłowy');self.source_panel.pack(fill='x',pady=(10,0))
        self.evidence=self.text_widget(self.source_panel,5);self.evidence.pack(fill='x');self.evidence.configure(state='disabled')
        self.evidence.tag_configure('match',background='#2b6f5c',foreground='white')

    def show_evidence(self,card):
        span=evidence_range(card,self.source_snapshot)
        if not span:return
        start,end=span;self.evidence.configure(state='normal');self.evidence.delete('1.0','end');self.evidence.insert('1.0',self.source_snapshot)
        self.evidence.tag_add('match',f'1.0+{start}c',f'1.0+{end}c');self.evidence.see(f'1.0+{start}c');self.evidence.configure(state='disabled')
        self.status.set('Pokazano dokładny fragment tekstu użytego do analizy.')

    def render_cards(self,view,title,cards,empty='Brak wyników w tej sekcji.'):
        view.clear();view.title(title)
        if not cards:view.add(empty,'muted')
        for index,card in enumerate(cards,1):view.card(card,index,self.source_snapshot,self.show_evidence)
        view.finish()

    def show_result(self,payload):
        if 'wynik' in payload:
            self.source_snapshot=payload.get('tekst','');self.analysis=(self.source_snapshot,payload['wynik']);payload=payload['wynik']
        self.report_package=None
        if 'zbiorczy_rejestr_kart' in payload:self.analysis=None
        self.result=payload;self.display_result=materialize(payload)
        result=self.display_result;sections=result.get('sekcje',{});public=result.get('raport_czytelny',{})
        summary=result.get('podsumowanie',{})
        self.result_stats.set(f"Relacje: {summary.get('canonical_relation',summary.get('relacje_wypowiedzi',len(sections.get('relacje_wypowiedzi',[]))))}   ·   Aktorzy: {summary.get('mapa_aktorow',0)}   ·   Dokumenty: {summary.get('dokumenty',1)}")
        if result.get('podglad_tekstu',{}).get('tekst') is not None:self.source_snapshot=result['podglad_tekstu']['tekst']
        elif 'zbiorczy_rejestr_kart' in payload:self.source_snapshot=''
        view=self.result_views['summary'];view.clear();view.title('Najważniejsze wnioski')
        for item in public.get('items',[]):
            view.heading(item.get('tytul',''));view.add(str(item.get('wartosc',''))+'\n');view.add(item.get('opis','')+'\n','muted')
        cards=result.get('jednostki_znaczenia') or sections.get('top_najwazniejszych_relacji') or sections.get('relacje_wypowiedzi',[])
        if cards:
            view.heading('Relacje poparte tekstem')
            for index,card in enumerate(cards,1):view.card(card,index,self.source_snapshot,self.show_evidence)
        elif not public.get('items'):view.add('Nie wykryto zaakceptowanych relacji. Szczegóły są dostępne w pozostałych widokach.\n','muted')
        for note in (result.get('jakosc_analizy') or {}).get('warnings',[]):view.add(str(note)+'\n','warning')
        if public.get('do_sprawdzenia'):
            view.heading('Do sprawdzenia')
            for text in public['do_sprawdzenia']:view.add('• '+text+'\n')
        view.finish()
        self.render_cards(self.result_views['relations'],'Kto mówi, o kim i co',sections.get('relacje_wypowiedzi',[]))
        self.render_cards(self.result_views['fact'],'Fakty, opinie i cytaty',sections.get('fact_opinia_cytat') or sections.get('fact_opinion_quote',[]))
        self.render_cards(self.result_views['actors'],'Aktorzy i instytucje',sections.get('mapa_aktorow',[]))
        self.render_cards(self.result_views['sources'],'Źródła i media',sections.get('mapa_zrodel',[]),'Silnik nie przypisał osobnych kart źródeł. Sprawdź źródła wskazane w kartach wypowiedzi.')
        self.expert_sections={SECTIONS.get(k,k.replace('_',' ').capitalize()):k for k in sections}
        self.expert_sections['P0 · surowe sygnały']='p0'
        self.expert_selector.configure(values=list(self.expert_sections));self.expert_mode.set(next(iter(self.expert_sections)))
        self.render_expert();self.navigate('result')
        self.evidence.configure(state='normal');self.evidence.delete('1.0','end');self.evidence.insert('1.0',self.source_snapshot or 'Wynik zbiorczy obejmuje wiele dokumentów i nie ma jednego wspólnego tekstu źródłowego.');self.evidence.configure(state='disabled')
        self.render_report_text(readable_report(result))

    def render_expert(self):
        if self.result is None:return
        key=self.expert_sections.get(self.expert_mode.get());result=self.display_result
        cards=(result.get('p0') or {}).get('pelny_podglad',[]) if key=='p0' else result.get('sekcje',{}).get(key,[])
        self.render_cards(self.result_views['expert'],self.expert_mode.get(),cards)
        if key=='p0':
            view=self.result_views['expert'];view.text.configure(state='normal');view.text.insert('1.0','P0 to wskazówki — nie są werdyktem ani decyzją P1.\n\n','warning');view.finish()

    def build_database(self):
        ttk.Label(self.database_tab,textvariable=self.stats,foreground=ACCENT).pack(anchor='w',pady=(0,10))
        bar=self.bar(self.database_tab)
        for name,action in [('Dodaj pliki',self.import_files),('Dodaj folder',self.import_folder),('Odśwież',self.refresh),('Połącz analizy',self.aggregate)]:self.button(bar,name,action)
        self.cancel_button=ttk.Button(bar,text='Zatrzymaj dodawanie',command=self.cancel_import.set);self.cancel_button.pack(side='right')
        bar=self.bar(self.database_tab);self.button(bar,'Kopia SQLite',self.backup);self.button(bar,'Przywróć kopię',self.restore_database);self.button(bar,'Przelicz całą bazę',self.reanalyze)
        self.docs=self.tree(self.database_tab,[('name','Dokument',220),('path','Folder / ścieżka',380),('state','Stan',140)]);self.docs.bind('<Double-1>',self.document)
        bar=self.bar(self.database_tab);self.button(bar,'Poprzednie',lambda:self.page(-100));self.button(bar,'Następne',lambda:self.page(100))
        self.import_view=RichView(self.database_tab);self.import_view.configure(height=90);self.import_view.pack(fill='x');self.import_view.pack_propagate(False)
        self.import_view.clear();self.import_view.add('Dokumenty pozostają w bazie po zamknięciu aplikacji. Analiza kolejki działa po zminimalizowaniu okna.','muted');self.import_view.finish()

    def aggregate(self):self.run(lambda:self.engine.request('/api/baza/zbiorczy_wynik'),self.show_result)
    def reanalyze(self):
        if not messagebox.askyesno('Przeliczenie bazy','Przeliczyć wszystkie zapisane analizy aktualnym silnikiem? Dokumenty i ich identyfikatory pozostaną zachowane.'):return
        def done(result):self.refresh();messagebox.showinfo('Przeliczenie',f"Przeliczono {result.get('przeliczono',0)} z {result.get('razem',0)} dokumentów.\nBłędy: {len(result.get('bledy',[]))}")
        self.run(lambda:self.engine.request('/api/baza/przelicz_wszystkie',{}),done)

    def restore_database(self):
        path=filedialog.askopenfilename(filetypes=[('Kopia SQLite','*.sqlite3 *.sqlite *.db')])
        if not path:return
        if not messagebox.askyesno('Przywrócenie kopii','Wybrana kopia zastąpi całą bazę PC, razem z ocenami. Najpierw zostanie zachowana kopia obecnej bazy. To przywrócenie, nie scalanie danych. Kontynuować?'):return
        def done(backup):
            self.analysis=None;self.result=None;self.refresh();messagebox.showinfo('Baza przywrócona','Zachowano poprzednią bazę w:\n'+str(backup))
        self.run(lambda:self.engine.restore(path),done)

    def import_folder(self):
        folder=filedialog.askdirectory()
        if not folder:return
        parent=Path(folder)
        def paths():
            return [(p,parent.name+'/'+p.relative_to(parent).as_posix()) for p in sorted(parent.rglob('*')) if p.is_file() and p.suffix.lower() in {'.txt','.md','.markdown','.csv','.json','.log','.html','.htm'}]
        self.import_paths(paths)

    def import_paths(self,paths):
        self.cancel_import.clear()
        def job():
            entries=paths() if callable(paths) else paths;counts={'queued':0,'duplicate':0};errors=[];processed=0
            for p,relative in entries:
                if self.cancel_import.is_set():break
                try:
                    result=self.engine.import_file(p,relative);key=result.get('status','queued');counts[key]=counts.get(key,0)+1
                except Exception as exc:errors.append(relative+': '+str(exc))
                processed+=1;self.progress.put(f'Dodawanie: {processed}/{len(entries)} · {relative}')
            return {'counts':counts,'errors':errors,'processed':processed,'total':len(entries)}
        def done(result):
            view=self.import_view;view.clear();view.add(f"Dodano do kolejki: {result['counts'].get('queued',0)} · Duplikaty: {result['counts'].get('duplicate',0)} · Błędy: {len(result['errors'])}\n")
            if result['processed']<result['total']:view.add('Zatrzymano dodawanie nowych plików. Zapisana kolejka pozostaje w bazie.\n','warning')
            for error in result['errors']:view.add(error+'\n','warning')
            view.finish();self.refresh();self.navigate('database')
        self.run(job,done)

    def build_compare(self):
        page=self.pages['compare'];bar=self.bar(page);self.mode=tk.StringVar(value='Foldery')
        combo=ttk.Combobox(bar,textvariable=self.mode,values=['Foldery','Redakcje'],state='readonly',width=16);combo.pack(side='left',padx=(0,10));combo.bind('<<ComboboxSelected>>',lambda _e:self.groups())
        self.button(bar,'Wczytaj grupy',self.groups);self.button(bar,'Porównaj wybrane',self.compare,True)
        ttk.Label(page,text='Wybierz 2–10 grup. Ctrl+klik pozwala zaznaczyć kilka pozycji.',style='Muted.TLabel').pack(anchor='w',pady=4)
        self.group_list=tk.Listbox(page,selectmode='extended',exportselection=False,bg=PANEL,fg=FG,selectbackground='#34534f',relief='flat',font=('Segoe UI',11),height=5);self.group_list.pack(fill='x',pady=(0,10))
        self.compare_output=self.tree(page,[('metric','Wskaźnik',280),('a','Grupa A',180),('b','Grupa B',180),('delta','Różnica',110)])
        self.compare_notes=RichView(page);self.compare_notes.pack(fill='both',expand=True)
        self.compare_notes.clear();self.compare_notes.add('Najpierw dodaj dokumenty do bazy. Porównania opisują zapisane artykuły, uwzględniając liczebność prób.','muted');self.compare_notes.finish()

    def groups(self):
        mode='folder' if self.mode.get()=='Foldery' else 'publisher'
        def done(result):
            self.group_list.delete(0,'end');self.group_names=[]
            for group in result['groups']:self.group_names.append(group['id']);self.group_list.insert('end',f"{group['label']}   ·   {group['documents']} dokumentów")
        self.run(lambda:self.engine.request('/api/baza/porownanie/grupy?mode='+mode),done)
    def compare(self):
        names=[self.group_names[i] for i in self.group_list.curselection()]
        if not 2<=len(names)<=10:messagebox.showinfo('Porównanie','Zaznacz od 2 do 10 grup.');return
        mode='folder' if self.mode.get()=='Foldery' else 'publisher'
        self.run(lambda:self.engine.request('/api/baza/porownanie?'+urlencode([('mode',mode)]+[('group',g) for g in names])),self.show_comparison)
    def show_comparison(self,payload):
        comparison=payload.get('comparison') or payload;self.comparison=payload
        tree=self.compare_output;tree.delete(*tree.get_children())
        multi=bool(comparison.get('groups'));groups=comparison.get('groups') or [comparison.get('group_a',{}),comparison.get('group_b',{})]
        names=[g.get('name','') for g in groups]
        columns=['metric']+[f'g{i}' for i in range(len(names))]+([] if multi else ['delta'])
        tree.configure(columns=columns)
        tree.heading('metric',text='Wskaźnik');tree.column('metric',width=260)
        for i,name in enumerate(names):tree.heading(f'g{i}',text=name);tree.column(f'g{i}',width=150)
        if not multi:tree.heading('delta',text='Różnica');tree.column('delta',width=110)
        for metric in comparison.get('metrics',[]):
            values=metric.get('values',[]) if multi else [metric.get('a',0),metric.get('b',0)]
            if isinstance(values,dict):values=[values.get(n,0) for n in names]
            suffix='%' if metric.get('kind')=='percent' else ''
            row=[metric.get('label','')]+[f'{v:g}{suffix}' if isinstance(v,(int,float)) else str(v) for v in values]
            if not multi:row.append(f"{metric.get('delta',0):g}"+(' pp' if suffix else ''))
            tree.insert('','end',values=row)
        view=self.compare_notes;view.clear()
        if payload.get('title'):view.heading(payload['title'])
        for warning in comparison.get('warnings',[]):view.add(warning+'\n','warning')
        view.add(comparison.get('method_note','')+'\n','muted')
        dist_names={'speakers':'Mówcy','targets':'Dotyczy','topics':'Tematy','claim_types':'Rodzaje twierdzeń','cited_sources':'Przywołane źródła','p0':'P0 · sygnały','p1':'P1 · struktury','p2':'P2 · techniki','p3':'P3 · ramy','p4':'P4 · strategie','p5':'P5 · diagnozy'}
        for key,dist in comparison.get('distributions',{}).items():
            rows=dist.get('rows',[])
            if not rows:continue
            view.heading(dist_names.get(key,key))
            for row in rows:view.line(row['label'],f"{names[0]}: {row['a_count']} ({row['a_share']}%)   ·   {names[1]}: {row['b_count']} ({row['b_share']}%)")
        view.finish();self.navigate('compare')

    def build_topics(self):
        page=self.pages['topics'];bar=self.bar(page);self.button(bar,'Wyszukaj wspólne tematy',self.topics,True);self.button(bar,'Porównaj wybrany temat',self.compare_topic)
        self.topic_tree=self.tree(page,[('title','Wspólny temat',600),('documents','Artykuły',100),('sources','Redakcje',100)])
        self.topic_tree.bind('<Double-1>',lambda _e:self.compare_topic())
        self.topic_info=RichView(page);self.topic_info.pack(fill='both',expand=True)
        self.topic_info.clear();self.topic_info.add('Dodaj artykuły z różnych redakcji. Program wyszuka materiały opisujące wspólną sprawę.','muted');self.topic_info.finish()
    def topics(self):
        def done(payload):
            self.topic_data={};self.topic_tree.delete(*self.topic_tree.get_children())
            for topic in payload['topics']:
                self.topic_data[topic['topic_id']]=topic;self.topic_tree.insert('','end',iid=topic['topic_id'],values=(topic['title'],topic['documents'],topic['publisher_count']))
            self.topic_info.clear();self.topic_info.add(payload.get('method_note',''),'muted')
            if not payload['topics']:self.topic_info.heading('Nie znaleziono wspólnych tematów w obecnej bazie.')
            self.topic_info.finish()
        self.run(lambda:self.engine.request('/api/baza/tematy'),done)
    def compare_topic(self):
        selected=self.topic_tree.selection()
        if not selected:return
        ident=selected[0]
        self.run(lambda:self.engine.request('/api/baza/temat/porownanie?'+urlencode({'topic_id':ident,'mode':'publisher'})),self.show_comparison)

    def build_quality(self):
        page=self.pages['quality'];tabs=ttk.Notebook(page);tabs.pack(fill='both',expand=True)
        self.quality_views={};self.sample_size={};self.sample_seed={};self.quality_stats={};self.quality_note={}
        for kind,name,default in [('benchmark','Benchmark relacji','30'),('gold','Dokumenty GOLD','10')]:
            frame=ttk.Frame(tabs);tabs.add(frame,text=name);bar=self.bar(frame)
            ttk.Label(bar,text='Wielkość próby').pack(side='left',padx=4);size=tk.StringVar(value=default);self.sample_size[kind]=size;ttk.Entry(bar,textvariable=size,width=5).pack(side='left',padx=4)
            seed=tk.StringVar(value='sora');self.sample_seed[kind]=seed;ttk.Label(bar,text='Nazwa próby').pack(side='left',padx=4);ttk.Entry(bar,textvariable=seed,width=12).pack(side='left',padx=4)
            self.button(bar,'Wczytaj próbę',lambda k=kind:self.sample(k),True);self.button(bar,'Wyniki ocen',lambda k=kind:self.quality_summary(k))
            stat=tk.StringVar(value='Jeszcze nie wybrano próby.');self.quality_stats[kind]=stat;ttk.Label(frame,textvariable=stat,foreground=ACCENT).pack(anchor='w',pady=6)
            view=RichView(frame);view.pack(fill='both',expand=True);self.quality_views[kind]=view
            view.clear();view.add('Oceny zapisują się w bazie i pozostają dostępne po restarcie.','muted');view.finish()
            if kind=='benchmark':
                row=self.bar(frame);self.benchmark_fields={}
                for key,label in [('overall','Cała relacja'),('speaker','Mówca'),('claim','Twierdzenie'),('target','Dotyczy'),('source','Źródło')]:
                    col=ttk.Frame(row);col.pack(side='left',padx=(0,8));ttk.Label(col,text=label).pack(anchor='w');var=tk.StringVar(value='Poprawna' if key=='overall' else 'Nie oceniono');self.benchmark_fields[key]=var
                    options=list(LABELS)[:3] if key=='overall' else list(LABELS);ttk.Combobox(col,textvariable=var,values=options,state='readonly',width=13).pack()
            else:
                self.gold_rows=[];self.gold_tree=self.tree(frame,[('speaker','Mówca',150),('claim','Oczekiwane twierdzenie',400),('target','Dotyczy',130),('source','Źródło',130)])
                self.gold_tree.bind('<Double-1>',lambda _e:self.edit_gold())
                row=self.bar(frame);self.button(row,'Dodaj relację',lambda:self.edit_gold(new=True));self.button(row,'Edytuj',self.edit_gold);self.button(row,'Usuń relację',self.remove_gold)
            row=self.bar(frame);ttk.Label(row,text='Notatka').pack(side='left',padx=5);note=tk.StringVar();self.quality_note[kind]=note;ttk.Entry(row,textvariable=note).pack(side='left',fill='x',expand=True,padx=5)
            self.button(row,'Zapisz ocenę i następna',lambda k=kind:self.save_quality(k),True);self.button(row,'Pomiń',lambda k=kind:self.next_sample(k))

    def sample(self,kind):
        query=urlencode({'size':self.sample_size[kind].get(),'seed':self.sample_seed[kind].get(),'unlabeled':1})
        def done(payload):self.samples[kind]=payload['items'];self.sample_index[kind]=0;self.render_sample(kind)
        self.run(lambda:self.engine.request('/api/baza/'+kind+'/proba?'+query),done)
    def render_sample(self,kind):
        items=self.samples[kind];index=self.sample_index[kind];view=self.quality_views[kind];view.clear();self.quality_note[kind].set('')
        if index>=len(items):
            view.title('Próba zakończona' if items else 'Brak dokumentów do oceny');view.add('Wczytaj nową próbę albo otwórz wyniki zapisanych ocen.','muted');view.finish();return
        item=items[index];self.quality_stats[kind].set(f"Dokument {index+1}/{len(items)} · {item.get('relative_path') or item.get('filename')}")
        if kind=='benchmark':
            view.heading('Relacja do oceny')
            for key,label in [('speaker','Mówca'),('action','Działanie'),('claim','Twierdzenie'),('target','Dotyczy'),('source','Źródło')]:view.line(label,item.get(key) or 'Nie przypisano')
            view.heading('Fragment dokumentu');view.add(item.get('snippet',''),'quote')
            for key,var in self.benchmark_fields.items():var.set('Poprawna' if key=='overall' else 'Nie oceniono')
        else:
            view.heading('Tekst dokumentu');view.add(item.get('text',''),'quote');view.add('\nPopraw, usuń błędne i dodaj brakujące relacje. Zapis oznacza, że lista jest kompletną oceną referencyjną dokumentu.','warning')
            self.gold_rows=[{key:str(row.get(key,'') or '') for key in ['speaker','claim','target','source']} for row in item.get('predicted_relations',[])];self.refresh_gold()
        view.finish()
    def next_sample(self,kind):self.sample_index[kind]+=1;self.render_sample(kind)
    def refresh_gold(self):
        self.gold_tree.delete(*self.gold_tree.get_children())
        for i,row in enumerate(self.gold_rows):self.gold_tree.insert('','end',iid=str(i),values=tuple(row[k] for k in ['speaker','claim','target','source']))
    def edit_gold(self,new=False):
        if not self.samples['gold'] or self.sample_index['gold']>=len(self.samples['gold']):return
        selected=self.gold_tree.selection();index=None if new else int(selected[0]) if selected else None
        if not new and index is None:return
        win=tk.Toplevel(self.root);win.title('Oczekiwana relacja GOLD');win.configure(bg=BG);win.geometry('650x410');win.transient(self.root);win.grab_set()
        entries={};row={} if new else self.gold_rows[index]
        for key,label in [('speaker','Mówca'),('claim','Twierdzenie'),('target','Dotyczy'),('source','Źródło')]:
            ttk.Label(win,text=label).pack(anchor='w',padx=20,pady=(12,3));var=tk.StringVar(value=row.get(key,''));entries[key]=var;ttk.Entry(win,textvariable=var).pack(fill='x',padx=20)
        def save():
            value={k:v.get().strip() for k,v in entries.items()}
            if not value['speaker'] or not value['claim']:messagebox.showinfo('Relacja','Uzupełnij mówcę i twierdzenie.',parent=win);return
            if new:self.gold_rows.append(value)
            else:self.gold_rows[index]=value
            self.refresh_gold();win.destroy()
        ttk.Button(win,text='Zapisz relację',command=save,style='Accent.TButton').pack(pady=20)
    def remove_gold(self):
        selected=self.gold_tree.selection()
        if selected:self.gold_rows.pop(int(selected[0]));self.refresh_gold()
    def save_quality(self,kind):
        index=self.sample_index[kind]
        if index>=len(self.samples[kind]):return
        item=self.samples[kind][index];payload={'document_id':item['document_id'],'note':self.quality_note[kind].get()}
        if kind=='benchmark':
            payload.update({'relation_id':item['relation_id']});payload.update({key+'_label':LABELS[var.get()] for key,var in self.benchmark_fields.items()});endpoint='ocena'
        else:payload.update({'expected_relations':[dict(row) for row in self.gold_rows],'completed':True});endpoint='dokument'
        self.run(lambda:self.engine.request(f'/api/baza/{kind}/{endpoint}',payload),lambda _result:self.next_sample(kind))
    def quality_summary(self,kind):
        def done(payload):
            self.quality_payload=payload;view=self.quality_views[kind];view.clear();view.title('Wyniki zapisanych ocen')
            if kind=='benchmark':
                view.line('Ocenione relacje',payload.get('labels_total',0))
                for key,label in [('overall','Cała relacja'),('speaker','Mówca'),('claim','Twierdzenie'),('target','Dotyczy'),('source','Źródło')]:
                    stats=payload.get(key,{});view.heading(label);view.line('Poprawne',stats.get('correct',0));view.line('Częściowe',stats.get('partial',0));view.line('Błędne',stats.get('false',0));view.line('Ścisła precyzja',str(stats.get('strict_percent',0))+'%')
                view.add(payload.get('warning',''),'warning')
            else:
                view.line('Kompletne dokumenty referencyjne',payload.get('documents',0))
                for key,label in [('strict','Ocena ścisła'),('lenient','Ocena łagodna')]:
                    metrics=payload.get(key,{});view.heading(label)
                    for field,title in [('precision','Precyzja'),('recall','Pokrycie oczekiwanych relacji'),('f1','F1')]:view.line(title,f"{100*metrics.get(field,0):.2f}%")
                    view.line('Poprawne / błędne / pominięte',f"{metrics.get('tp',0)} / {metrics.get('fp',0)} / {metrics.get('fn',0)}")
                view.add(payload.get('method_note',''),'muted')
            view.finish()
        self.run(lambda:self.engine.request('/api/baza/'+kind+'/wynik'),done)

    def build_reports(self):
        page=self.pages['reports'];bar=self.bar(page);self.button(bar,'Raport bieżącej analizy',self.report,True)
        for label,fmt in [('Zapisz Markdown','md'),('Zapisz PDF','pdf'),('Zapisz JSON','json')]:self.button(bar,label,lambda f=fmt:self.export_report(f))
        self.report_view=RichView(page);self.report_view.pack(fill='both',expand=True);self.report_view.clear();self.report_view.add('Raport będzie dostępny po analizie dokumentu.','muted');self.report_view.finish();self.report_text='';self.report_package=None
    def render_report_text(self,text):
        self.report_text=text;view=self.report_view;view.clear()
        for line in text.splitlines():
            if line.startswith('#'):view.heading(line.lstrip('# ').strip())
            else:view.add(line+'\n')
        view.finish()
    def report(self):
        if self.analysis and (self.analysis[0]==self.source_text() or self.tabs.select()!=str(self.editor_tab)):
            text,result=self.analysis;ident=result.get('analysis_run_id','')
        else:
            text=self.source_text();ident=''
            if not text.strip():messagebox.showinfo('Raport','Najpierw wczytaj i przeanalizuj dokument.');return
        def done(package):self.report_package=package;self.render_report_text(package.get('raport_markdown',''));self.navigate('reports')
        self.run(lambda:self.engine.request('/api/raport',{'tekst':text,'analysis_run_id':ident}),done)
    def export_report(self,fmt):
        if not self.report_text:messagebox.showinfo('Eksport','Najpierw wykonaj analizę.');return
        path=filedialog.asksaveasfilename(defaultextension='.'+fmt,initialfile='drogowskazy_raport.'+fmt,filetypes=[(fmt.upper(),'*.'+fmt)])
        if not path:return
        text=self.report_text;payload=self.report_package or self.result
        def save():
            if fmt=='pdf':write_pdf(path,text)
            elif fmt=='json':Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            else:Path(path).write_text(text,encoding='utf-8')
        self.run(save,lambda _r:self.status.set('Zapisano raport: '+Path(path).name))
    def suggestions(self):
        text=self.source_text()
        def done(payload):
            self.suggestions_payload=payload;view=self.result_views['expert'];view.clear();view.title('Sugestie do kontroli')
            rows=payload.get('sugestie') or payload.get('items') or []
            if isinstance(rows,list):
                for index,row in enumerate(rows,1):
                    if isinstance(row,dict):view.card(row,index,text,self.show_evidence)
                    else:view.add(str(row)+'\n')
            if not rows:view.add(payload.get('wiadomosc') or 'Brak dodatkowych sugestii dla tego tekstu.','muted')
            view.finish();self.navigate('result');self.result_modes.select(5)
        self.source_snapshot=text
        self.run(lambda:self.engine.request('/api/sugestie',{'tekst':text}),done)
    def tick(self):
        if self.closed:return
        try:
            while True:self.status.set(self.progress.get_nowait())
        except queue.Empty:pass
        if self.busy:self.busy_bar.start(12)
        else:self.busy_bar.stop()
        if not self.busy and str(self.pages['database'])==self.tabs.select():self.refresh()
        self.root.after(1500,self.tick)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');parser.add_argument('--data-dir');args=parser.parse_args()
    home=Path(args.data_dir) if args.data_dir else home_path();home.mkdir(parents=True,exist_ok=True)
    lock=None
    if os.name=='nt':
        import msvcrt
        lock=(home/'application.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            lock.close();root=tk.Tk();root.withdraw();messagebox.showinfo('Drogowskazy Sora','Aplikacja jest już uruchomiona. Otwórz jej okno z paska zadań.');root.destroy();return
    root=tk.Tk()
    try:
        engine=Engine(home);window=Window(root,engine,home)
        if args.smoke_test:
            def callback_error(kind,value,tb):
                (home/'smoke-error.txt').write_text(''.join(traceback.format_exception(kind,value,tb)),encoding='utf-8');os._exit(1)
            root.report_callback_exception=callback_error
            from gui_test import exercise
            root.after(700,lambda:exercise(window,home))
        root.mainloop()
        if lock:lock.close()
    except Exception:
        text=traceback.format_exc();(home/'blad_startu.txt').write_text(text,encoding='utf-8');messagebox.showerror('Drogowskazy Sora',text);root.destroy();raise

if __name__=='__main__':main()
