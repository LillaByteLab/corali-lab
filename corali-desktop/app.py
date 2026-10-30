"""Coralì Lab PC. Loopback-only service and native WebView2 window, no exposed Python bridge."""
from pathlib import Path
import argparse
import base64
import hashlib
import heapq
import http.server
import ipaddress
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
import csv_tools
import pdf_tools
import advanced

VERSION='0.5.4-beta'
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
ASSETS=ROOT/'assets'
NO_WINDOW=0x08000000 if os.name=='nt' else 0
OFFICE=re.compile(r'\.(docx|xlsx|pptx|odt|ods|odp|doc|xls|ppt|docm|xlsm|pptm|dotx|xltx|potx|ppsx|csv)$',re.I)


def safe_name(name):
    value=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',Path(name).name).strip(' .')[:180]
    return value or 'documento'


class NativeWindow:
    """Private host channel; the document/browser never receives this token."""
    def call(self,route,payload):
        url=os.environ['CORALI_NATIVE_UI_URL']
        if not re.fullmatch(r'http://127\.0\.0\.1:\d+',url):raise ValueError('Finestra nativa non disponibile.')
        request=urllib.request.Request(url+route,json.dumps(payload).encode('ascii'),{'Content-Type':'application/json','X-Corali-Token':os.environ['CORALI_NATIVE_UI_TOKEN']})
        with urllib.request.urlopen(request,timeout=7200) as response:return json.load(response)
    def create_file_dialog(self,kind,save_filename):
        path=self.call('/save',{'name':save_filename}).get('path')
        return [path] if path else None
    def destroy(self):self.call('/close',{})


class Application:
    def __init__(self,data=None,cedro=None):
        # AppData can be virtualized per process by the Codex MSIX package. A neutral user folder
        # makes CLI outputs, the installed GUI and development tools see the same physical files.
        self.root=Path(data or Path.home()/'CoraliLab').resolve();self.root.mkdir(parents=True,exist_ok=True)
        for name in ('inputs','outputs','cache'):(self.root/name).mkdir(exist_ok=True)
        if data is None:self.migrate_legacy()
        bundled=ROOT/'engine'/'cedro.exe'
        self.cedro=Path(cedro) if cedro else bundled if bundled.is_file() or getattr(sys,'frozen',False) else Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Cedro/cedro.exe'
        info=ROOT/'engine/engine-info.json'
        self.engine_info=json.loads(info.read_text(encoding='utf8')) if info.is_file() else {'version':'0.18.5','architecture':'x64'}
        self.token=secrets.token_urlsafe(32);self.origin='';self.cookie='';self.window=None
        self.sessions={};self.busy=threading.Lock();self.cancel=threading.Event();self.child=None;self.progress={'label':'Pronto','percent':0}
        self.previews=threading.Lock();self.office_lock=threading.RLock()
        self.workspace_lock=threading.RLock()
        from workspace_cleanup import WorkspaceCleanup
        self.cleanup=WorkspaceCleanup(self)
        self.queue_lock=threading.Lock();self.queue_cancel=threading.Event();self.queue_thread=None
        self.advanced=advanced.Advanced(self,ROOT)

    @staticmethod
    def local_bases():
        return [Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local')),Path.home()/'AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local']

    def migrate_legacy(self):
        for base in self.local_bases():
            for name in ('inputs','outputs'):
                legacy=base/'CoraliLab'/name
                if not legacy.is_dir():continue
                for source in legacy.rglob('*'):
                    if not source.is_file():continue
                    dest=self.root/name/source.relative_to(legacy)
                    if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)

    def resolve(self,id):
        if not isinstance(id,str):raise ValueError('File non selezionato.')
        path=(self.root/id).resolve()
        if not path.is_file() or not any(path.is_relative_to(self.root/name) for name in ('inputs','outputs')):raise ValueError('File non disponibile: importalo nuovamente.')
        return path

    def meta(self,path):
        id=path.relative_to(self.root).as_posix()
        return {'id':id,'name':path.name,'bytes':path.stat().st_size,'date':int(path.stat().st_mtime*1000),'output':id.startswith('outputs/')}

    def scan(self):
        def entries(folder):
            if folder.is_symlink() or folder.is_junction() or (folder/'.corali-pending').exists():return
            try:
                with os.scandir(folder) as listing:
                    for entry in listing:
                        if entry.name.startswith('.') or entry.is_symlink():continue
                        path=Path(entry.path)
                        try:
                            if path.is_junction():continue
                            if entry.is_dir(follow_symlinks=False):yield from entries(path)
                            elif entry.is_file(follow_symlinks=False):
                                stat=entry.stat(follow_symlinks=False);id=path.relative_to(self.root).as_posix()
                                yield {'id':id,'name':entry.name,'bytes':stat.st_size,'date':int(stat.st_mtime*1000),'output':id.startswith('outputs/'),'_mtime':stat.st_mtime_ns}
                        except OSError:continue  # A file may disappear while scanning.
            except OSError:return
        candidates=(item for name in ('inputs','outputs') for item in entries(self.root/name))
        result=heapq.nlargest(5000,candidates,key=lambda x:(x['_mtime'],x['id']))
        for item in result:item.pop('_mtime')
        return result

    def import_bytes(self,name,data):
        if len(data)>250*1024*1024:raise ValueError('Importa file fino a 250 MB.')
        with self.workspace_lock:
            folder=self.root/'inputs'/uuid.uuid4().hex;folder.mkdir();path=folder/safe_name(name);path.write_bytes(data)
            return self.meta(path)

    def folder(self):
        path=self.root/'outputs'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);path.mkdir();return path

    def command(self,args,timeout=1800):
        if self.cancel.is_set():raise ValueError('Operazione annullata.')
        env=dict(os.environ,APPDATA=str(self.root/'engine-config'))
        if Path(args[0]).resolve()==self.cedro.resolve():env['LOCALAPPDATA']=str(self.engine_store())
        flags=NO_WINDOW;startup=None
        if os.name=='nt':
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            if Path(args[0]).resolve()==self.cedro.resolve():
                host=ROOT/'engine'/'CoraliEngineHostSilent.exe'
                if not host.is_file():raise ValueError('Collegamento al motore incompleto: ripristina Coralì Lab.')
                args=[host,*args];flags=subprocess.CREATE_NEW_CONSOLE
        process=subprocess.Popen([str(x) for x in args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=flags,startupinfo=startup,env=env);self.child=process
        buffers=[bytearray(),bytearray()]
        def collect(pipe,index):
            for line in iter(pipe.readline,b''):
                buffers[index].extend(line)
                if len(buffers[index])>256*1024:del buffers[index][:-256*1024]
                text=line.decode('utf-8',errors='replace').strip()
                # CLI emits download/load/progress steps as lines. Do not wait for exit to display them.
                if text and not text.startswith('['):
                    match=re.search(r'(\d{1,3})%',text)
                    self.progress={'label':text[:220],'percent':min(99,int(match.group(1))) if match else -1}
            pipe.close()
        readers=[threading.Thread(target=collect,args=(pipe,n),daemon=True) for n,pipe in enumerate((process.stdout,process.stderr))]
        for reader in readers:reader.start()
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.stop();raise ValueError('L’operazione ha superato il tempo massimo.')
        finally:
            for reader in readers:reader.join(timeout=2)
        out,err=map(bytes,buffers)
        code=process.returncode
        if self.child is process:self.child=None
        def decode(raw):
            try:return raw.decode('utf-8')
            except UnicodeDecodeError:return raw.decode('cp1252',errors='replace')
        text=decode(out);error=decode(err)
        if self.cancel.is_set():raise ValueError('Operazione annullata.')
        if code:raise ValueError((error or text or 'Il motore Cedro ha interrotto l’operazione.')[-2500:])
        return text+'\n'+error

    def stop(self):
        self.queue_cancel.set();self.advanced.ai.stop()
        self.cancel.set();child=self.child
        if child and child.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,creationflags=NO_WINDOW)
            else:child.terminate()

    def require_cedro(self):
        if not self.cedro.is_file():raise ValueError('Il motore incluso non è disponibile. Ripristina l’installazione di Coralì Lab.')

    def models(self):
        caches=[self.engine_store()/'Cedro/trascrizione',self.root/'engine-data/Cedro/trascrizione',*[base/'Cedro/trascrizione' for base in self.local_bases()]]
        return [{'id':i,'name':name,'bytes':size*1000000,'ready':any((cache/file).is_file() for cache in caches)} for i,(name,file,size) in enumerate((('Veloce','ggml-small-q8_0.bin',264),('Buona','ggml-medium-q5_0.bin',539),('Massima','ggml-large-v3-turbo-q5_0.bin',574)))]

    def native_arm(self):
        return any(str(value).upper() in ('ARM64','AARCH64') for value in (platform.machine(),os.environ.get('PROCESSOR_ARCHITEW6432'),os.environ.get('PROCESSOR_ARCHITECTURE'))) and (ROOT/'engine/native-arm64/cedro-trascrivi-dotprod.exe').is_file()

    def engine_store(self):
        return self.root/'engine-data'/(self.engine_info['version']+'-'+self.engine_info['architecture'])

    def prepare_native_engine(self):
        cache=self.engine_store()/'Cedro/trascrizione';cache.mkdir(parents=True,exist_ok=True)
        # Reuse immutable model files, never mix architectures in the original Cedro cache.
        for official in [self.root/'engine-data/Cedro/trascrizione',*sorted((self.root/'engine-data').glob('*/Cedro/trascrizione')),*(base/'Cedro/trascrizione' for base in self.local_bases())]:
            for source in official.glob('ggml-*.bin*'):
                if source.suffix not in ('.bin','.sha256'):continue
                dest=cache/source.name
                if not dest.exists():
                    try:os.link(source,dest)
                    except OSError:shutil.copy2(source,dest)
        arch=self.engine_info['architecture']
        for worker in self.engine_info.get('workers',[]):
            name=worker['name']
            if Path(name).name!=name or not re.fullmatch(r'cedro-trascrivi-[a-z0-9]+\.exe',name):
                raise ValueError('Metadati del motore di trascrizione non validi.')
            source=ROOT/'engine'/('native-'+arch)/name;dest=cache/name
            def digest(path):
                with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
            if not source.is_file() or digest(source)!=worker['sha256']:
                raise ValueError('Motore di trascrizione non integro: '+name)
            if not dest.exists() or digest(dest)!=worker['sha256']:shutil.copy2(source,dest)
            dest.with_suffix('.exe.version').write_text(self.engine_info['version'],encoding='utf8')

    def engine_settings(self,options=None,cpu=False):
        options=options or {}
        dpi=int(options.get('pdf_dpi',144));compression=int(options.get('compress',1));maximum=int(options.get('ocr_max',100));language=options.get('ocr_lang','auto')
        if dpi not in (72,100,144,200,300) or compression not in (0,1,2) or not 0<=maximum<=10000 or language not in ('auto','it','en'):raise ValueError('Impostazioni di conversione non valide.')
        config=self.root/'engine-config'/'Cedro'/'config.txt';config.parent.mkdir(parents=True,exist_ok=True)
        # Private configuration: never redirect results or change official Cedro settings.
        config.write_text(f'dest=same\nreplace=0\nnotify=0\nreveal=0\nprogress=0\nupdate_check=0\ngpu={0 if cpu else 1}\npdf_dpi={dpi}\ncompress={compression}\nocr_lang={language}\nocr_max={maximum}\n',encoding='utf-8')

    def conversion_options(self,path,action):
        result=[]
        if action=='compress':result.append({'key':'compress','title':'Intensità della compressione','type':'choice','default':1,'choices':[{'value':0,'label':'Leggera'},{'value':1,'label':'Media'},{'value':2,'label':'Forte'}]})
        if path.suffix.lower()=='.pdf' and action in ('jpg','png'):
            result.append({'key':'pdf_dpi','title':'Risoluzione delle immagini','type':'choice','default':144,'choices':[{'value':n,'label':str(n)+' DPI'} for n in (100,144,200,300)]})
        if action in ('ocr','docx') or (path.suffix.lower()=='.pdf' and action=='txt'):
            result.extend([{'key':'ocr_lang','title':'Lingua OCR','type':'choice','default':'auto','choices':[{'value':'auto','label':'Automatica'},{'value':'it','label':'Italiano'},{'value':'en','label':'Inglese'}]}, {'key':'ocr_max','title':'Massimo pagine da leggere con OCR','type':'range','min':0,'max':10000,'default':100,'note':'0 = tutte le pagine. Il limite riguarda il riconoscimento delle scansioni.'}])
        return result

    def transcript(self,paths,p,folder):
        self.require_cedro();outputs=[];precision=['veloce','buona','massima'][max(0,min(2,int(p.get('model',1))))]
        self.prepare_native_engine()
        self.engine_settings(cpu=bool(p.get('cpu')))
        for number,path in enumerate(paths):
            sub=folder/('trascrizione-'+str(number+1));sub.mkdir();copy=sub/path.name;shutil.copy2(path,copy)
            self.progress={'label':'Trascrizione con Cedro: '+path.name,'percent':0}
            args=[self.cedro,'trascrivi',copy,'--precisione',precision]
            if p.get('cpu'):args.append('--cpu')
            try:self.command(args)
            except ValueError as error:
                if self.cancel.is_set() or p.get('cpu') or not any(word in str(error).lower() for word in ('chiuso','vulkan','gpu','memoria')):raise
                self.progress={'label':'Accelerazione grafica interrotta: riprovo con il processore','percent':-1}
                self.engine_settings(cpu=True)
                self.command([*args,'--cpu'])
            generated=[f for f in sub.rglob('*') if f.is_file() and f!=copy]
            if not generated:raise ValueError('Il motore non ha prodotto una trascrizione. Prova il livello Veloce e attiva Usa soltanto il processore.')
            # The Word produced by Cedro also supplies a plain-text copy without a second transcription.
            for file in list(generated):
                if file.suffix.lower()=='.docx':
                    import xml.etree.ElementTree as ET
                    with zipfile.ZipFile(file) as z:tree=ET.fromstring(z.read('word/document.xml'))
                    lines=[''.join(n.itertext()) for n in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
                    txt=file.with_suffix('.txt');txt.write_text('\n'.join(lines),encoding='utf-8-sig');generated.append(txt)
            copy.unlink();outputs.extend(generated)
        return outputs

    def web_download(self,p,folder):
        from safe_web import PublicYoutubeDL,validate_url
        url=p.get('url','');validate_url(url)
        def hook(event):
            if self.cancel.is_set():raise ValueError('Download annullato.')
            total=event.get('total_bytes') or event.get('total_bytes_estimate') or 0
            self.progress={'label':'Scaricamento dal sito','percent':min(99,int(event.get('downloaded_bytes',0)*100/total)) if total else 0}
        from media_runtime import ensure_ffmpeg
        self.progress={'label':'Preparazione strumento video: primo download dal produttore, circa 92 MB','percent':-1}
        ffmpeg=ensure_ffmpeg(self.advanced.ai,ROOT/'media-manifest.json',lambda v:setattr(self,'progress',v),self.cancel)
        ffmpeg=str(ffmpeg);audio=bool(p.get('audio'))
        class Logger:
            def debug(self,message):pass
            def warning(self,message):pass
            def error(self,message):pass
        options={'outtmpl':str(folder/'%(title).120s-%(id)s.%(ext)s'),'noplaylist':True,'quiet':True,'noprogress':True,'logger':Logger(),'no_warnings':True,'progress_hooks':[hook],'ffmpeg_location':ffmpeg,'format':'bestaudio/best' if audio else 'bv*[height<=1080]+ba/b[height<=1080]/best','merge_output_format':'mp4','windowsfilenames':True,'socket_timeout':30,'max_filesize':1024*1024*1024}
        node=shutil.which('node')
        if node:options['js_runtimes']={'node':{'path':node}}
        if audio:options['postprocessors']=[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}]
        options.update(proxy='',external_downloader={'default':'native'},hls_prefer_native=True,
                       postprocessor_args={'ffmpeg_i':['-protocol_whitelist','file,pipe']})
        with PublicYoutubeDL(options) as ydl:ydl.download([url])
        if self.cancel.is_set():raise ValueError('Download annullato.')
        outputs=[f for f in folder.iterdir() if f.is_file() and not f.name.startswith('.') and not f.name.endswith(('.part','.ytdl'))]
        if p.get('transcribe'):outputs.extend(self.transcript(outputs.copy(),p,folder))
        return outputs

    def office_inspect(self,path):
        if not OFFICE.search(path.name):raise ValueError('Formato Office non supportato.')
        if path.stat().st_size>50*1024*1024:raise ValueError('Questa versione apre documenti Office fino a 50 MB.')
        ext=path.suffix.lower();allowed=ext in ('.docx','.xlsx','.pptx','.odt','.ods','.odp');reason=''
        with path.open('rb') as stream:head=stream.read(8)
        encrypted=head.startswith(bytes.fromhex('d0cf')) and ext in ('.docx','.xlsx','.pptx')
        if encrypted:allowed=False;reason='Documento protetto: apertura in sola lettura.'
        elif ext not in ('.doc','.xls','.ppt'):
            with zipfile.ZipFile(path) as archive:
                entries=archive.infolist()
                if len(entries)>30000 or sum(e.file_size for e in entries)>200*1024*1024:raise ValueError('Il documento richiede troppa memoria.')
                names=[e.filename.lower() for e in entries]
                if any(n.endswith('vbaproject.bin') or n.startswith('_xmlsignatures/') or n=='meta-inf/documentsignatures.xml' for n in names):allowed=False;reason='Documento con macro o firma: apertura in sola lettura.'
                import xml.etree.ElementTree as ET
                for e in entries:
                    if e.filename.endswith('.xml') and re.match(r'^(word/|xl/|ppt/|content.xml)',e.filename):
                        raw=archive.read(e)
                        if b'<!DOCTYPE' in raw.upper():raise ValueError('Il documento contiene una dichiarazione XML non supportata.')
                        for node in ET.fromstring(raw).iter():
                            kind=node.tag.rsplit('}',1)[-1];attributes={k.rsplit('}',1)[-1]:str(v).lower() for k,v in node.attrib.items()};truth=lambda key:attributes.get(key) in ('1','true','on')
                            protected=(kind=='documentProtection' and truth('enforcement')) or (kind=='sheetProtection' and truth('sheet')) or (kind=='workbookProtection' and any(truth(k) for k in ('lockStructure','lockWindows','lockRevision'))) or kind=='modifyVerifier' or truth('protected')
                            if protected:allowed=False;reason='Documento con restrizioni di modifica: apertura in sola lettura.'
        if not allowed and not reason:reason='Questo formato è disponibile in sola lettura.'
        return {'editable':allowed,'reason':reason,'encrypted':encrypted}

    def new_office(self,path):
        sid=uuid.uuid4().hex
        if path.suffix.lower()=='.csv':session={'path':path,'csv':csv_tools.CsvSession(path)};route='csv'
        else:session={'path':path,'inspection':self.office_inspect(path),'hash':csv_tools.digest(path)};route='office'
        self.sessions[sid]=session;return {'session':sid,'route':route}

    def session(self,sid):
        if sid not in self.sessions:raise ValueError('Documento scaduto: aprilo nuovamente.')
        return self.sessions[sid]

    def office(self,p,sid):
        with self.office_lock:
            if p.get('cmd')=='close':return self.close_session(sid,p.get('discard') is True)
            return self._office(p,sid)

    def close_session(self,sid,discard=False):
        with self.office_lock, self.workspace_lock:
            session=self.sessions.get(sid)
            if session is None:return {'closed':True}
            if not discard and (session.get('pending') or (session.get('csv') and session['csv'].dirty)):
                raise ValueError('Ci sono modifiche non salvate: salva una copia o conferma di scartarle.')
            if session.get('pending'):session['pending'].unlink(missing_ok=True)
            del self.sessions[sid]
            return {'closed':True}

    def _office(self,p,sid):
        session=self.session(sid);source=session['path'];cmd=p.get('cmd')
        with self.office_lock:
            if cmd=='info':return {**session['inspection'],'name':source.name,'size':source.stat().st_size,'url':'/office-source?sid='+sid}
            if cmd=='begin':
                if not session['inspection']['editable']:raise ValueError(session['inspection']['reason'])
                size=int(p.get('size',0))
                if not 0<size<=100*1024*1024:raise ValueError('Dimensione del risultato non valida.')
                if session.get('pending'):session['pending'].unlink(missing_ok=True)
                session.update(pending=self.root/'cache'/(uuid.uuid4().hex+'.part'),expected=size,written=0,token=secrets.token_urlsafe(24));session['pending'].touch();return {'token':session['token']}
            if cmd in ('chunk','commit'):
                if not secrets.compare_digest(str(p.get('token','')),session.get('token','invalid')) or not session.get('pending'):raise ValueError('Salvataggio scaduto: riprova.')
                if cmd=='chunk':
                    raw=base64.b64decode(p.get('data',''),validate=True)
                    if p.get('offset')!=session['written'] or len(raw)>196608 or session['written']+len(raw)>session['expected']:raise ValueError('Sequenza del salvataggio non valida.')
                    with session['pending'].open('ab') as out:out.write(raw)
                    session['written']+=len(raw);return {'written':session['written']}
                if session['written']!=session['expected']:raise ValueError('Salvataggio incompleto.')
                if csv_tools.digest(source)!=session['hash']:raise ValueError('La sorgente è cambiata: aprila nuovamente.')
                required={'.docx':'word/document.xml','.xlsx':'xl/workbook.xml','.pptx':'ppt/presentation.xml','.odt':'content.xml','.ods':'content.xml','.odp':'content.xml'}.get(source.suffix.lower())
                with zipfile.ZipFile(session['pending']) as archive:
                    if not required or required not in archive.namelist() or sum(e.file_size for e in archive.infolist())>200*1024*1024 or archive.testzip():raise ValueError('Il documento salvato non supera il controllo d’integrità.')
                dest=self.folder()/(source.stem+'-modificato'+source.suffix);session['pending'].replace(dest);session.update(saved=dest,pending=None,token=None);return {'name':dest.name,'size':dest.stat().st_size,'originalUnchanged':True}
            if cmd=='abort':
                if session.get('pending'):session['pending'].unlink(missing_ok=True)
                session.update(pending=None,token=None);return {}
            if cmd in ('export','share'):
                if not session.get('saved'):raise ValueError('Salva prima una copia.')
                return self.export(session['saved']) if cmd=='export' else self.reveal(session['saved'])
            raise ValueError('Operazione Office non disponibile.')

    def csv(self,p,sid):
        with self.office_lock:
            if p.get('cmd')=='close':return self.close_session(sid,p.get('discard') is True)
            return self._csv(p,sid)

    def _csv(self,p,sid):
        session=self.session(sid);editor=session['csv'];cmd=p.get('cmd')
        if cmd=='view':return editor.view(p.get('start',0))
        if cmd=='apply':editor.apply(p.get('changes',[]));return editor.view(p.get('start',0))
        if cmd=='add':editor.apply(p.get('changes',[]));editor.add(p.get('what'));return editor.view(p.get('start',0))
        if cmd=='separator':
            if editor.dirty:raise ValueError('Salva la copia prima di cambiare il separatore.')
            session['csv']=csv_tools.CsvSession(session['path'],p.get('delimiter'));return session['csv'].view()
        if cmd=='save':
            editor.apply(p.get('changes',[]));dest=self.folder()/(session['path'].stem+'-modificato.csv');editor.save(dest,p.get('encoding'));session['saved']=dest;return {'name':dest.name,'file':self.meta(dest)}
        if cmd in ('export','share') and session.get('saved'):return self.export(session['saved']) if cmd=='export' else self.reveal(session['saved'])
        raise ValueError('Operazione CSV non disponibile.')

    def export(self,source):
        preferred=self.advanced.preferences()
        if preferred.get('directSave') and preferred.get('folder'):
            folder=Path(preferred['folder']).resolve()
            if not folder.is_dir() or folder.is_relative_to(self.root/'inputs'):raise ValueError('La cartella preferita non è più disponibile. Modifica le preferenze.')
            dest=folder/source.name
            if dest.exists():dest=folder/(source.stem+'-'+uuid.uuid4().hex[:6]+source.suffix)
            with dest.open('xb') as out,source.open('rb') as original:shutil.copyfileobj(original,out)
            return {'saved':True,'path':str(dest)}
        if not self.window:raise ValueError('Apri la finestra Windows di Coralì Lab per scegliere dove salvare la copia.')
        selection=self.window.create_file_dialog(30,save_filename=source.name)
        target=selection[0] if selection else None
        if target:
            dest=Path(target).resolve()
            if dest.is_relative_to(self.root/'inputs'):raise ValueError('Scegli una destinazione diversa dalle copie sorgenti.')
            if dest!=source.resolve():shutil.copy2(source,dest)
        return {'saved':bool(target),'path':str(dest) if target else ''}

    def reveal(self,path):
        subprocess.Popen(['explorer.exe','/select,',str(path)],creationflags=NO_WINDOW);return {}

    def dispatch(self,p):
        cmd=p.get('cmd')
        if self.queue_lock.locked() and self.queue_thread!=threading.get_ident() and cmd not in ('progress','cancel','init','files','advancedStatus'):
            raise ValueError('Attendi che termini la coda, oppure annullala.')
        if cmd in advanced.COMMANDS:return self.advanced.dispatch(p)
        if cmd in ('cleanupPreview','cleanupApply','cleanupRestore','cleanupStatus','cleanupPurgePreview','cleanupPurge'):
            return self.cleanup.dispatch(p)
        if cmd=='exit':
            if self.window:self.window.destroy()
            return {}
        if cmd=='init':return {'files':self.scan(),'models':self.models(),'device':'Coralì Lab PC','android':VERSION,'version':VERSION,'engineVersion':self.engine_info['version'],'busy':self.busy.locked()}
        if cmd=='files':return {'files':self.scan(),'models':self.models()}
        if cmd=='progress':return {**self.progress,'busy':self.busy.locked() or self.queue_lock.locked()}
        if cmd=='cancel':self.stop();return {}
        if cmd=='openOffice':
            with self.office_lock, self.workspace_lock:return self.new_office(self.resolve(p.get('id')))
        if cmd=='pdfInfo':
            with self.previews:return pdf_tools.info(self.resolve(p.get('id')),p)
        if cmd=='catalog':
            if not self.busy.acquire(blocking=False):raise ValueError('Attendi che termini l’elaborazione in corso.')
            try:
                self.cancel.clear();self.require_cedro();path=self.resolve(p.get('id'));actions=[];seen=set()
                for mode in ('convert','tools','actions'):
                    for line in self.command([self.cedro,'slices',path,mode],timeout=30).splitlines():
                        if '\t' in line:
                            id,label=line.split('\t',1)
                            if id not in seen and id not in ('none','path'):actions.append({'id':id,'label':label,'options':self.conversion_options(path,id)});seen.add(id)
                return {'actions':actions}
            finally:self.busy.release()
        if cmd in ('export','share'):return self.export(self.resolve(p.get('id'))) if cmd=='export' else self.reveal(self.resolve(p.get('id')))
        if cmd not in ('pdf','convert','transcribe','web'):raise ValueError('Comando non disponibile.')
        if not self.busy.acquire(blocking=False):raise ValueError('È già in corso un’elaborazione.')
        folder=self.folder();(folder/'.corali-pending').touch();self.cancel.clear();self.progress={'label':'Elaborazione sul PC','percent':0}
        try:
            sources=[self.resolve(id) for id in p.get('ids',[])]
            hashes={path:csv_tools.digest(path) for path in sources}
            if cmd!='web' and not sources:raise ValueError('Scegli almeno un file.')
            result={}
            if cmd=='pdf':
                outputs=pdf_tools.run(p.get('action'),sources,p,folder,ASSETS/'TitilliumWeb-Regular.ttf',self.resolve,self.cancel)
                if p.get('action')=='compress':result.update(before=sources[0].stat().st_size,after=outputs[0].stat().st_size,message='Confronta il peso e controlla la leggibilità della nuova copia.')
            elif cmd=='transcribe':outputs=self.transcript(sources,p,folder)
            elif cmd=='web':outputs=self.web_download(p,folder)
            else:
                self.require_cedro();outputs=[]
                self.engine_settings(p.get('options'))
                for n,source in enumerate(sources):
                    sub=folder/('file-'+str(n+1));sub.mkdir();copy=sub/source.name;shutil.copy2(source,copy)
                    action=p.get('action','')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',action):raise ValueError('Operazione non valida.')
                    self.progress={'label':'Conversione con Cedro: '+source.name,'percent':int(n*100/len(sources))}
                    self.command([self.cedro,'--quality',str(max(40,min(95,int(p.get('quality',82))))),'convert',copy,action])
                    generated=[f for f in sub.rglob('*') if f.is_file() and f!=copy]
                    copy.unlink();outputs.extend(generated)
            if not outputs:raise ValueError('Nessun risultato prodotto.')
            for source,hash in hashes.items():
                if csv_tools.digest(source)!=hash:raise ValueError('La verifica della sorgente non è riuscita.')
            if self.cancel.is_set():raise ValueError('Operazione annullata. Nessun risultato incompleto pubblicato.')
            (folder/'.corali-pending').unlink(missing_ok=True)
            self.progress={'label':'Elaborazione completata','percent':100};result['files']=[self.meta(f) for f in outputs]
            return result
        except Exception:
            if self.cancel.is_set():self.progress={'label':'Operazione annullata','percent':0}
            shutil.rmtree(folder,ignore_errors=True);raise
        finally:self.busy.release()


def make_server(app,port=0):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def auth(self):
            header=self.headers.get('X-Corali-Token','')
            cookie=re.search(r'(?:^|;\s*)'+re.escape(app.cookie)+r'=([^;]*)',self.headers.get('Cookie',''))
            token=header or (cookie.group(1) if cookie else '')
            return secrets.compare_digest(token,app.token)
        def valid_host(self):return self.headers.get('Host')==app.origin.removeprefix('http://')
        def send(self,status,data,kind='application/json; charset=utf-8',cookie=False,headers=None):
            raw=json.dumps(data,ensure_ascii=False).encode() if isinstance(data,(dict,list)) else data
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            if cookie:self.send_header('Set-Cookie',app.cookie+'='+app.token+'; HttpOnly; SameSite=Strict; Path=/')
            for name,value in (headers or {}).items():self.send_header(name,value)
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if not self.valid_host():return self.send(403,{'error':'Host non consentito'})
            url=urllib.parse.urlsplit(self.path);query=urllib.parse.parse_qs(url.query)
            if url.path in ('/office-source','/local-file'):
                if not self.auth():return self.send(403,{'error':'Accesso non consentito'})
                try:
                    path=app.session(query.get('sid',[''])[0])['path'] if url.path=='/office-source' else app.resolve(query.get('id',[''])[0])
                    size=path.stat().st_size;kind=mimetypes.guess_type(path.name)[0] or 'application/octet-stream';requested=self.headers.get('Range')
                    if requested:
                        match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
                        if not match:return self.send(416,b'',kind,headers={'Content-Range':'bytes */'+str(size)})
                        start=int(match[1]);end=min(int(match[2]) if match[2] else size-1,size-1)
                        if not 0<=start<=end:return self.send(416,b'',kind,headers={'Content-Range':'bytes */'+str(size)})
                        with path.open('rb') as stream:stream.seek(start);raw=stream.read(end-start+1)
                        return self.send(206,raw,kind,headers={'Accept-Ranges':'bytes','Content-Range':f'bytes {start}-{end}/{size}'})
                    return self.send(200,path.read_bytes(),kind,headers={'Accept-Ranges':'bytes'})
                except Exception:return self.send(404,{'error':'File non disponibile'})
            name=urllib.parse.unquote(url.path).lstrip('/') or 'index.html';path=(ASSETS/name).resolve()
            if not path.is_relative_to(ASSETS.resolve()) or not path.is_file():return self.send(404,{'error':'Risorsa non disponibile'})
            kind={'.mjs':'text/javascript','.js':'text/javascript','.wasm':'application/wasm'}.get(path.suffix) or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.send(200,path.read_bytes(),kind)
        def do_POST(self):
            if not self.valid_host() or not self.auth() or self.headers.get('Origin',app.origin)!=app.origin:return self.send(403,{'ok':False,'error':'Accesso non consentito'})
            try:
                size=int(self.headers.get('Content-Length',0));route=urllib.parse.urlsplit(self.path)
                limit=250*1024*1024 if route.path=='/import' else 2*1024*1024
                if not 0<=size<=limit:raise ValueError('Richiesta troppo grande.')
                raw=self.rfile.read(size)
                if route.path=='/session':return self.send(200,{'ok':True},cookie=True)
                if route.path=='/import':return self.send(200,{'ok':True,'data':app.import_bytes(urllib.parse.unquote(self.headers.get('X-Filename','file')),raw)})
                p=json.loads(raw);sid=urllib.parse.parse_qs(route.query).get('sid',[''])[0]
                if route.path=='/office-rpc':result=app.office(p,sid)
                elif route.path=='/csv-rpc':result=app.csv(p,sid)
                elif route.path=='/rpc':result=app.dispatch(p)
                else:raise ValueError('Operazione non disponibile.')
                self.send(200,{'ok':True,'data':result})
            except Exception as error:self.send(200,{'ok':False,'error':str(error) or type(error).__name__})
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    app.origin='http://127.0.0.1:'+str(server.server_port);app.cookie='corali_'+str(server.server_port)
    return server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve-only',action='store_true');parser.add_argument('--data');parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
    app=Application(args.data);server=make_server(app,args.port);url=app.origin+'/#'+app.token
    (app.root/'session.json').write_text(json.dumps({'url':url,'pid':os.getpid()}),encoding='utf-8')
    if args.serve_only:
        if os.environ.get('CORALI_NATIVE_UI_URL'):app.window=NativeWindow()
        print('Corali Lab local test server ready',flush=True)
        try:server.serve_forever()
        finally:server.server_close()
        return
    import webview
    threading.Thread(target=server.serve_forever,daemon=True).start()
    window=webview.create_window('Coralì Lab — Il tuo laboratorio digitale',url,width=1180,height=820,min_size=(800,600),background_color='#FCF8FF',js_api=None,confirm_close=True)
    app.window=window
    try:webview.start(gui='edgechromium',private_mode=False,storage_path=str(app.root/'webview'),localization={'global.quitConfirmation':'Vuoi chiudere Coralì Lab? Eventuali modifiche non salvate andranno perse.','global.ok':'Chiudi','global.quit':'Chiudi','global.cancel':'Annulla','global.saveFile':'Salva una copia','windows.fileFilter.allFiles':'Tutti i file','windows.fileFilter.otherFiles':'Altri tipi di file'})
    finally:app.stop();server.shutdown();server.server_close();(app.root/'session.json').unlink(missing_ok=True)


if __name__=='__main__':main()
