"""Optional, pinned local inference. No document is sent to a remote endpoint."""
from pathlib import Path
import atexit, hashlib, json, os, platform, secrets, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, zipfile
from assistant_checks import verified_answer
from assistant_messages import messages as document_messages
from local_operations import messages, parse_action, requires_router, NeedsReview


class LocalAI:
    def __init__(self, root, manifest, pack_dir=None, architecture=None):
        self.root=Path(root)/'ai';self.manifest=json.loads(Path(manifest).read_text(encoding='utf8'))
        # A packaged x64 application can run on an ARM host in emulation.
        # Its engine manifest is the authority; host environment variables are not.
        self.arch=architecture or ('arm64' if platform.machine().upper() in ('ARM64','AARCH64') else 'x64')
        if self.arch not in ('arm64','x64'):raise ValueError('Architettura AI non supportata.')
        self.runtime=self.root/('runtime-'+self.manifest['runtimeVersion']+'-'+self.arch)
        self.backend='cpu';self.backend_note=''
        try:
            if json.loads((self.root/'accelerator.json').read_text('utf8')).get('backend')=='vulkan':
                self.backend='vulkan';self.runtime=self.runtime_dir('vulkan')
        except (OSError,ValueError):pass
        self.model=self.root/self.manifest['model']['file'];self.process=None;self.lock=threading.Lock();self.key=secrets.token_urlsafe(32);self.origin=''
        self.log=None;self.active_profile=None;self.verified_files={}
        self.pack=Path(pack_dir) if pack_dir is not None else ((Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)/'ai-pack')
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}));atexit.register(self.stop)

    def trained_files(self):
        info=self.manifest.get('trained')
        if not info:return None
        for folder in (self.root/'trained-v1',self.pack):
            base=folder/info['base']['file'];adapter=folder/info['adapter']['file']
            if base.is_file() and adapter.is_file():return base,adapter
        return None

    def verify(self,path,info):
        signature=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns,info['sha256'])
        if self.verified_files.get(str(path))==signature:return
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=info['sha256']:raise ValueError('Componente AI non integro: '+path.name+'. Ripristina il pacchetto AI originale.')
        self.verified_files[str(path)]=signature

    def status(self):
        trained=self.trained_files()
        present=(bool(trained) or self.model.is_file()) and (self.runtime/'llama-server.exe').is_file()
        running=self.process is not None and self.process.poll() is None
        return {'ready':present,'componentsPresent':present,'integrity':'verified-at-start' if running else 'check-at-next-start','running':running,'model':self.manifest['model']['name'],'architecture':self.arch,'downloadBytes':self.manifest['model']['bytes'],'trainedAvailable':bool(trained),'trainedExperimental':True,'backend':self.backend,'backendNote':self.backend_note,'vulkanAvailable':self.arch in self.manifest.get('vulkanRuntime',{})}

    def runtime_dir(self,backend):
        return self.root/('runtime-'+self.manifest['runtimeVersion']+'-'+self.arch+('-vulkan' if backend=='vulkan' else ''))

    def runtime_info(self,backend):
        return self.manifest['vulkanRuntime' if backend=='vulkan' else 'runtime'][self.arch]

    def verify_runtime(self,folder,info):
        expected=info.get('files',{})
        if 'llama-server.exe' not in expected:raise ValueError('Manifest AI incompleto: reinstalla Coralì Lab.')
        actual={p.name for p in folder.iterdir() if p.suffix.lower() in ('.exe','.dll')}
        if actual!=set(expected):raise ValueError('File del motore AI mancanti o non previsti. Usa Ripara il motore AI.')
        for name,digest in expected.items():
            path=folder/name
            if Path(name).name!=name or path.is_symlink() or path.is_junction():raise ValueError('Percorso del motore AI non valido.')
            with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=digest:raise ValueError('Motore AI non integro: '+name+'. Usa Ripara il motore AI.')

    def setup_runtime(self,backend,progress,cancelled,repair=False):
        folder=self.runtime_dir(backend);info=self.runtime_info(backend)
        if folder.is_symlink() or folder.is_junction():raise ValueError('Cartella del motore AI collegata: riparazione non consentita.')
        if not repair and folder.exists():
            self.verify_runtime(folder,info)
            return folder
        self.root.mkdir(parents=True,exist_ok=True)
        # Stage and verify the whole runtime before touching the installed one.
        with tempfile.TemporaryDirectory(prefix='prepare-runtime-',dir=self.root) as work:
            work=Path(work);archive=work/'download.zip';staged=work/'runtime';staged.mkdir()
            self.download(info,archive,progress,cancelled)
            with zipfile.ZipFile(archive) as z:
                seen=set()
                for entry in z.infolist():
                    name=Path(entry.filename).name
                    if entry.is_dir() or Path(name).suffix.lower() not in ('.exe','.dll','.txt','.md'):continue
                    if name in seen:raise ValueError('Archivio AI con nomi duplicati.')
                    if entry.file_size>512*1024*1024:raise ValueError('Componente AI troppo grande.')
                    seen.add(name)
                    with z.open(entry) as source,(staged/name).open('xb') as target:
                        while chunk:=source.read(1024*1024):
                            if cancelled.is_set():raise ValueError('Preparazione annullata: il motore precedente è conservato.')
                            target.write(chunk)
            self.verify_runtime(staged,info)
            if cancelled.is_set():raise ValueError('Preparazione annullata: il motore precedente è conservato.')
            backup=self.root/(folder.name+'-precedente-'+secrets.token_hex(6))
            existed=folder.exists()
            if existed:folder.rename(backup)
            try:staged.rename(folder)
            except Exception:
                if existed:backup.rename(folder)
                raise
        return folder

    def repair(self,progress,cancelled,backend=None):
        with self.lock:
            backend=backend or self.backend
            if backend not in ('cpu','vulkan') or (backend=='vulkan' and self.arch not in self.manifest.get('vulkanRuntime',{})):
                raise ValueError('Motore non disponibile per questo PC.')
            self.root.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(self.root).free<max(128*1024*1024,self.runtime_info(backend).get('bytes',0)*6):
                raise ValueError('Spazio insufficiente per preparare e verificare il motore AI.')
            self.stop()
            self.setup_runtime(backend,progress,cancelled,repair=True)
            return self.status()

    def download(self, info, dest, progress, cancelled):
        dest.parent.mkdir(parents=True,exist_ok=True);part=dest.with_suffix(dest.suffix+'.part');digest=hashlib.sha256()
        try:
            with urllib.request.urlopen(info['url'],timeout=60) as response,part.open('wb') as out:
                total=int(response.headers.get('Content-Length',info.get('bytes',0)));count=0
                while chunk:=response.read(1024*1024):
                    if cancelled.is_set():raise ValueError('Scaricamento annullato.')
                    out.write(chunk);digest.update(chunk);count+=len(chunk);progress({'label':'Scaricamento componente AI: '+dest.name,'percent':int(count*100/total) if total else -1})
            if digest.hexdigest()!=info['sha256']:raise ValueError('Il componente AI non supera il controllo SHA-256.')
            part.replace(dest)
        finally:part.unlink(missing_ok=True)

    def setup(self, progress, cancelled, backend=None):
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            required=128*1024*1024 if self.trained_files() or self.model.is_file() else self.manifest['model']['bytes']+512*1024*1024
            if shutil.disk_usage(self.root).free < required:raise ValueError('Spazio insufficiente per preparare i componenti AI mancanti.')
            backend=backend or self.backend
            if backend not in ('cpu','vulkan') or (backend=='vulkan' and self.arch not in self.manifest.get('vulkanRuntime',{})):
                raise ValueError('Accelerazione non disponibile per questo PC.')
            self.stop()
            self.setup_runtime('cpu',progress,cancelled)
            self.runtime=self.setup_runtime(backend,progress,cancelled) if backend=='vulkan' else self.runtime_dir('cpu')
            self.backend=backend;self.backend_note=''
            (self.root/'accelerator.json').write_text(json.dumps({'backend':backend}),encoding='utf8')
            trained=self.trained_files()
            if trained:
                for path,key in zip(trained,('base','adapter')):self.verify(path,self.manifest['trained'][key])
            elif not self.model.is_file():self.download(self.manifest['model'],self.model,progress,cancelled)
            return self.status()

    def stop(self):
        process=self.process;self.process=None
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if self.log:self.log.close();self.log=None
        self.active_profile=None

    def start(self, cancelled, trained=False):
        try:
            return self._start(cancelled,trained)
        except RuntimeError:
            self.stop()
            if self.backend!='vulkan' or cancelled.is_set():raise ValueError('Il motore AI non riesce ad avviarsi. Consulta ai/runtime.log.')
            if (self.root/'runtime.log').exists():shutil.copy2(self.root/'runtime.log',self.root/'runtime-gpu-last.log')
            self.backend='cpu';self.runtime=self.runtime_dir('cpu')
            self.backend_note='GPU non disponibile: AI avviata con il processore.'
            (self.root/'accelerator.json').write_text(json.dumps({'backend':'cpu'}),encoding='utf8')
            try:return self._start(cancelled,trained)
            except RuntimeError as error:raise ValueError('Avvio AI non riuscito anche con il processore. Consulta ai/runtime.log.') from error

    def _start(self, cancelled, trained=False):
        if not self.status()['ready']:raise ValueError('Scarica prima i componenti AI dalla sezione Assistente locale.')
        files=self.trained_files()
        if trained and not files:raise ValueError('Per il suggeritore addestrato estrai il pacchetto AI accanto a CoraliLab.exe. I calcoli manuali funzionano anche senza AI.')
        profile='operations' if trained else 'chat'
        if self.process and self.process.poll() is None and self.active_profile==profile:return
        self.stop()
        self.verify_runtime(self.runtime,self.runtime_info(self.backend))
        model=files[0] if files else self.model
        self.verify(model,self.manifest['trained']['base'] if files else self.manifest['model'])
        if trained:self.verify(files[1],self.manifest['trained']['adapter'])
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.origin='http://127.0.0.1:'+str(port)
        args=[str(self.runtime/'llama-server.exe'),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--api-key',self.key,'-c','4096','-t',str(max(1,min(6,(os.cpu_count() or 4)-2))),'-np','1','--offline','--no-webui']
        args+=['-ngl','99' if self.backend=='vulkan' else '0']
        if trained:args+=['--lora',str(files[1])]
        self.log=(self.root/'runtime.log').open('wb')
        try:self.process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log,cwd=str(self.runtime),creationflags=0x08000000 if os.name=='nt' else 0)
        except OSError as error:raise RuntimeError('Avvio del processo AI fallito.') from error
        for _ in range(180):
            if cancelled.is_set():self.stop();raise ValueError('Avvio AI annullato.')
            if self.process.poll() is not None:raise RuntimeError('Il motore AI si è fermato durante l’avvio.')
            try:
                r=self.http.open(urllib.request.Request(self.origin+'/health',headers={'Authorization':'Bearer '+self.key}),timeout=1)
                if r.status==200:
                    if self.backend=='vulkan':
                        self.log.flush()
                        log=(self.root/'runtime.log').read_text('utf8',errors='replace')
                        import re
                        if not re.search(r'offloaded [1-9][0-9]*/[0-9]+ layers to GPU',log):raise RuntimeError('Nessun livello del modello caricato sulla GPU.')
                    self.active_profile=profile;return
            except RuntimeError:raise
            except Exception:pass
            time.sleep(.5)
        self.stop();raise RuntimeError('Avvio AI oltre il tempo previsto.')

    def suggest(self,prompt,data,cancelled):
        if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=4000:raise ValueError('Scrivi una richiesta fino a 4000 caratteri.')
        if type(data) is not dict or len(json.dumps(data))>200000:raise ValueError('Dati non validi o troppo grandi.')
        if not requires_router(data):raise ValueError('Compila prima almeno un campo: celle, intervallo o importo.')
        with self.lock:
            try:
                self.start(cancelled,trained=True)
                payload={'messages':messages(prompt,data),'temperature':0,'seed':32806,'max_tokens':48,'stream':False,'cache_prompt':False}
                request=urllib.request.Request(self.origin+'/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+self.key})
                with self.http.open(request,timeout=90) as response:answer=json.load(response)['choices'][0]
                if cancelled.is_set():raise ValueError('Richiesta annullata.')
                if answer.get('finish_reason')=='length':raise NeedsReview('Suggerimento incompleto: scegli manualmente l’operazione.')
                action=parse_action(answer['message'].get('content',''))
                return {'action':action,'experimental':True,'requiresConfirmation':True,'applied':False,'method':'trained-local-router','message':'Suggerimento sperimentale: verifica o cambia l’operazione prima di calcolare.'}
            except NeedsReview as error:raise ValueError('L’AI non ha identificato una operazione valida. Sceglila manualmente.') from error
            finally:self.stop()

    def ask(self, prompt, context, mode, cancelled):
        if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=4000:raise ValueError('Scrivi una richiesta fino a 4000 caratteri.')
        if not isinstance(context,str) or len(context)>10000:raise ValueError('Usa un estratto del documento fino a 10000 caratteri.')
        checked=verified_answer(prompt,context)
        if checked is not None:
            return {'text':checked,'local':True,'model':None,'method':'verified-local-rule','applied':False,'incomplete':False}
        with self.lock:
            self.start(cancelled)
            payload={'messages':document_messages(prompt,context,mode),'temperature':.1,'seed':42,'max_tokens':700,'stream':False}
            request=urllib.request.Request(self.origin+'/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+self.key})
            try:
                with self.http.open(request,timeout=180) as response:result=json.load(response)
            except Exception as error:raise ValueError('Il motore AI locale non ha completato la risposta. Riprova con un testo più breve.') from error
            if cancelled.is_set():raise ValueError('Richiesta annullata.')
            choice=result['choices'][0];answer=choice['message'].get('content','')
            if not isinstance(answer,str) or not answer.strip():raise ValueError('L’assistente non ha prodotto una risposta. Riformula la richiesta.')
            incomplete=choice.get('finish_reason')=='length'
            if incomplete:answer+='\n\nRisposta interrotta per limite di lunghezza: chiedi un passaggio alla volta prima di applicarla.'
            return {'text':answer,'local':True,'model':self.manifest['model']['name'],'applied':False,'incomplete':incomplete,'requiresReview':True,'method':'local-generative'}
