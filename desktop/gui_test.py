"""Exercise the shipped native EXE, shared engine, data and readable views."""
from pathlib import Path
import json
import os
import sys
from urllib.parse import urlencode
from presentation import materialize, readable_report, write_pdf


def stable(value):
    if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in {'analysis_run_id','analysis_generated_at','generated_at','utworzono','czas_generowania','timestamp'}}
    if isinstance(value,list):return [stable(v) for v in value]
    return value


def exercise(window,home):
    window.root.geometry(f'{max(980,min(1280,window.root.winfo_screenwidth()-40))}x{max(640,min(850,window.root.winfo_screenheight()-100))}+10+25')
    reference=json.loads((Path(sys._MEIPASS)/'engine-reference.json').read_text('utf-8'))
    def job():
        engine=window.engine
        for text,expected in zip(reference['cases'],reference['results']):
            assert stable(engine.request('/api/analizuj',{'tekst':text}))==stable(expected),'PHONE/EXE mismatch'
        for i,text in enumerate(reference['cases']):
            path=home/f'przyklad{i}.txt';path.write_text(text,encoding='utf-8');engine.import_file(path,f'Grupa{i}/przyklad{i}.txt')
        engine.stop()
        assert engine.request('/api/baza/status')['stats']['done']==2
        assert engine.import_file(home/'przyklad0.txt','Grupa0/przyklad0.txt')['status']=='duplicate'
        groups=engine.request('/api/baza/porownanie/grupy?mode=folder')['groups']
        comparison=engine.request('/api/baza/porownanie?'+urlencode([('mode','folder')]+[('group',g['id']) for g in groups]))
        aggregate=engine.request('/api/baza/zbiorczy_wynik')
        assert readable_report(materialize(aggregate))
        samples={k:engine.request(f'/api/baza/{k}/proba?size=10&seed=sora&unlabeled=0')['items'] for k in ('benchmark','gold')}
        assert samples['benchmark'] and samples['gold']
        item=samples['benchmark'][0]
        engine.request('/api/baza/benchmark/ocena',{'document_id':item['document_id'],'relation_id':item['relation_id'],'overall_label':'correct','speaker_label':'correct','claim_label':'correct','target_label':'unknown','source_label':'unknown','note':'EXE integration test'})
        item=samples['gold'][0]
        engine.request('/api/baza/gold/dokument',{'document_id':item['document_id'],'expected_relations':item['predicted_relations'],'completed':True,'note':'EXE integration test'})
        summary={k:engine.request(f'/api/baza/{k}/wynik') for k in samples}
        engine.request('/api/baza/tematy')
        snapshot=home/'test-copy.sqlite3';engine.backup(snapshot);previous=engine.restore(snapshot);assert previous.exists()
        write_pdf(home/'test-raport.pdf','Zażółć gęślą jaźń\nRaport Drogowskazy Sora')
        assert (home/'test-raport.pdf').read_bytes().startswith(b'%PDF')
        return comparison,aggregate,samples,summary
    def ready(payload):
        comparison,aggregate,samples,summary=payload
        window.show_result(aggregate);window.show_comparison(comparison)
        for kind,items in samples.items():
            window.samples[kind]=items;window.sample_index[kind]=0;window.render_sample(kind)
        # Walk every page in the actual packaged window.
        for page in window.pages:window.navigate(page);window.root.update_idletasks()
        window.editor.delete('1.0','end');window.editor.insert('1.0',reference['cases'][0]);window.navigate('editor');window.analyze()
        wait_analysis()
    def idle(callback):
        if window.busy:window.root.after(100,lambda:idle(callback))
        else:callback()
    def wait_analysis():
        def check():
            assert window.result and window.analysis
            assert window.result_views['summary'].text.get('1.0','end').strip()
            assert window.result_views['relations'].text.get('1.0','end').strip()
            window.report();idle(report_done)
        window.root.after(200,lambda:idle(check))
    def report_done():
        assert window.report_package and window.report_text
        assert window.report_package['analysis_run_id']==window.analysis[1]['analysis_run_id']
        window.navigate('result');window.result_modes.select(0)
        window.root.after(500,finish)
    def finish():
        from PIL import ImageGrab
        window.root.update_idletasks()
        assert window.evidence.winfo_ismapped() and window.evidence.winfo_height()>60,'Source evidence panel is clipped'
        assert window.evidence.winfo_rooty()+window.evidence.winfo_height()<=window.root.winfo_rooty()+window.root.winfo_height(),'Evidence below window'
        x,y=window.root.winfo_rootx(),window.root.winfo_rooty();w,h=window.root.winfo_width(),window.root.winfo_height()
        ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(home/'SORA_WYNIK.png')
        (home/'smoke-ok.json').write_text(json.dumps({'native_window':True,'engine_phone_parity':True,'database_restart_and_duplicates':True,'safe_restore':True,'benchmark_and_gold':True,'readable_views':True,'report_same_analysis':True,'pdf_polish_font':True,**window.engine.identity},indent=2),encoding='utf-8')
        window.close()
    # No blocking error dialogs in unattended test builds.
    from tkinter import messagebox
    def fail(title,message,*args,**kwargs):
        (home/'smoke-error.txt').write_text(str(title)+'\n'+str(message),encoding='utf-8');os._exit(1)
    messagebox.showerror=fail
    if window.busy:window.root.after(150,lambda:exercise(window,home))
    else:window.run(job,ready)
