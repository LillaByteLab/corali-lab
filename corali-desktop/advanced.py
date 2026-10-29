"""Advanced tools shared by the ARM64 and x64 desktop builds."""
from pathlib import Path
import json, re, shutil, threading, uuid
from local_ai import LocalAI
import workspace_tools as tools
from local_operations import execute

COMMANDS={'advancedStatus','preferences','renameCopy','aiSetup','aiAsk','aiStop','aiSuggestOperation','operationPreview','context','saveText','voiceText','pdfTables','tariff','batch'}


class Advanced:
    def __init__(self,app,root):
        self.app=app;self.ai=LocalAI(app.root,root/'ai-manifest.json',architecture=app.engine_info['architecture']);self.settings=app.root/'preferences.json'

    def preferences(self):
        try:return json.loads(self.settings.read_text(encoding='utf8'))
        except (OSError,ValueError):return {'folder':'','directSave':False}

    def save_preferences(self,p):
        folder=str(p.get('folder','')).strip();direct=bool(p.get('directSave'))
        if folder:
            path=Path(folder).expanduser().resolve()
            if not path.is_dir() or path.is_relative_to(self.app.root/'inputs'):raise ValueError('Scegli una cartella esistente, diversa dalle copie sorgenti.')
            folder=str(path)
        elif direct:raise ValueError('Indica prima una cartella.')
        value={'folder':folder,'directSave':direct};temp=self.settings.with_suffix('.tmp');temp.write_text(json.dumps(value),encoding='utf8');temp.replace(self.settings);return value

    def dispatch(self,p):
        a=self.app;cmd=p['cmd']
        if cmd=='advancedStatus':return {'ai':self.ai.status(),'preferences':self.preferences()}
        if cmd=='preferences':return self.save_preferences(p)
        if cmd=='aiStop':self.ai.stop();return self.ai.status()
        if cmd=='operationPreview':
            result=execute(p.get('action'),p.get('data'))
            return {'result':result,'method':'verified-local-operation','applied':False}
        if cmd=='tariff':
            result=tools.tariff(p.get('base',''),p.get('rate',''))
            if p.get('export'):
                from decimal import Decimal
                folder=a.folder();dest=folder/'Tariffe e riduzioni.xlsx'
                tools.write_xlsx(dest,[('Tariffe',[['Importo base','Riduzione percentuale','Importo ridotto'],[Decimal(result['base']),Decimal(result['rate']),tools.Formula('ROUND(A2*(1-B2/100),2)',Decimal(result['amount']))]])])
                result['files']=[a.meta(dest)]
            return result
        if cmd=='context':
            source=a.resolve(p.get('id'));content=tools.text(source)
            return {'text':content,'truncated':len(content)>=40000,'repetitions':tools.repetition_warnings(content)}
        if cmd=='saveText':
            content=p.get('text','')
            if not isinstance(content,str) or not content.strip() or len(content)>500000:raise ValueError('Testo vuoto o troppo grande.')
            folder=a.folder();name=re.sub(r'[^\w .-]','_',str(p.get('name','Documento revisionato')))[:100].strip(' .') or 'Documento revisionato'
            txt=folder/(name+'.txt');txt.write_text(content,encoding='utf-8-sig');word=folder/(name+'.docx');tools.write_docx(word,content)
            return {'files':[a.meta(txt),a.meta(word)],'message':'Nuove copie TXT e Word. Il documento originale è conservato.'}
        if cmd=='renameCopy':
            source=a.resolve(p.get('id'));name=str(p.get('name','')).strip()
            if not name or len(name)>120 or re.search(r'[\\/:*?"<>|\x00-\x1f]',name):raise ValueError('Nome non valido.')
            if Path(name).suffix.lower()!=source.suffix.lower():name+=source.suffix
            dest=a.folder()/name;shutil.copy2(source,dest);return {'files':[a.meta(dest)],'message':'Copia creata con il nuovo nome.'}
        if cmd=='batch':return self.batch(p)
        if not a.busy.acquire(blocking=False):raise ValueError('Attendi che termini l’elaborazione in corso.')
        a.cancel.clear()
        try:
            if cmd=='aiSetup':return self.ai.setup(lambda v:setattr(a,'progress',v),a.cancel,p.get('backend'))
            if cmd=='aiSuggestOperation':
                a.progress={'label':'L’assistente suggerisce una operazione da confermare','percent':-1}
                return self.ai.suggest(p.get('prompt',''),p.get('data'),a.cancel)
            if cmd=='aiAsk':
                a.progress={'label':'L’assistente sta elaborando sul PC','percent':-1}
                return self.ai.ask(p.get('prompt',''),p.get('context',''),p.get('mode','documenti'),a.cancel)
            if cmd=='voiceText':
                source=a.resolve(p.get('id'));folder=a.folder();(folder/'.corali-pending').touch()
                try:
                    outputs=a.transcript([source],{'model':0,'cpu':True},folder);txt=next(f for f in outputs if f.suffix=='.txt');content=txt.read_text(encoding='utf-8-sig')
                    (folder/'.corali-pending').unlink();return {'text':content,'files':[a.meta(f) for f in outputs]}
                except Exception:shutil.rmtree(folder,ignore_errors=True);raise
            if cmd=='pdfTables':
                source=a.resolve(p.get('id'))
                if source.suffix.lower()!='.pdf':raise ValueError('Scegli un PDF.')
                a.progress={'label':'Ricostruzione e controllo delle tabelle sul PC','percent':-1}
                sheets,warnings=tools.tables(source,p.get('profile','tables'));folder=a.folder();dest=folder/(source.stem+'-tabelle.xlsx');tools.write_xlsx(dest,sheets)
                return {'files':[a.meta(dest)],'warnings':warnings,'rows':sum(max(0,len(rows)-1) for _,rows in sheets),'message':('Excel creato con '+str(len(warnings))+' righe da verificare; controlla la colonna Controllo.' if warnings else 'Excel creato. Controlla l’impaginazione e i dati prima di usarlo.')}
            raise ValueError('Operazione non disponibile.')
        finally:a.busy.release()

    def batch(self,p):
        a=self.app;ids=p.get('ids',[])
        if not isinstance(ids,list) or not 1<=len(ids)<=100:raise ValueError('Scegli da 1 a 100 file.')
        operation=p.get('operation');results=[];files=[]
        if operation not in ('compress','convert'):raise ValueError('Operazione in serie non disponibile.')
        # A separate lock reserves the whole queue, including gaps between individual operations.
        if not a.queue_lock.acquire(blocking=False):raise ValueError('È già presente una coda.')
        a.queue_thread=threading.get_ident();a.queue_cancel.clear()
        try:
            for id in ids:
                if a.queue_cancel.is_set():break
                source=a.resolve(id)
                try:
                    request={'cmd':'pdf','action':'compress','mode':p.get('mode','balanced'),'ids':[id]} if operation=='compress' else {'cmd':'convert','action':p.get('action'),'quality':p.get('quality',82),'options':p.get('options',{}),'ids':[id]}
                    result=a.dispatch(request);files.extend(result['files']);results.append({'name':source.name,'ok':True})
                except Exception as error:results.append({'name':source.name,'ok':False,'error':str(error)})
            return {'files':files,'items':results,'cancelled':a.queue_cancel.is_set(),'message':str(sum(r['ok'] for r in results))+' file completati su '+str(len(ids))+'. Ogni originale è conservato.'}
        finally:a.queue_thread=None;a.queue_lock.release()
