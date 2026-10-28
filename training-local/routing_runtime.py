"""Authenticated loopback runtime for the routing experiment; no cloud service."""
import json,secrets,socket,subprocess,time,urllib.request
from pathlib import Path

class LocalModel:
    def __init__(self,base,adapters,log_path,threads=4):
        self.base=Path(base).resolve();self.adapters={k:Path(v).resolve() for k,v in adapters.items()}
        self.ids={key:i for i,key in enumerate(self.adapters)};self.log_path=Path(log_path);self.threads=threads
        self.key=secrets.token_urlsafe(32);self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(self,path,payload=None):
        request=urllib.request.Request(self.origin+path,None if payload is None else json.dumps(payload).encode(),
            {'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        with self.http.open(request,timeout=120) as response:return json.load(response)
    def __enter__(self):
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        self.origin='http://127.0.0.1:'+str(port)
        runtime=Path.home()/'CoraliLab/ai/runtime-b11936-arm64/llama-server.exe'
        self.log=self.log_path.open('wb')
        self.process=subprocess.Popen([str(runtime),'-m',str(self.base),'--lora',','.join(str(v) for v in self.adapters.values()),
            '--lora-init-without-apply','--host','127.0.0.1','--port',str(port),'--api-key',self.key,'-c','2048','-t',str(self.threads),
            '-np','1','--offline','--no-webui'],stdout=self.log,stderr=self.log,creationflags=0x08000000)
        try:
            for _ in range(120):
                if self.process.poll() is not None:raise RuntimeError('Local runtime stopped.')
                try:
                    if self.request('/health')['status']=='ok':break
                except Exception:time.sleep(.5)
            else:raise RuntimeError('Local runtime startup timed out.')
            loaded=self.request('/lora-adapters')
            assert len(loaded)==len(self.adapters)
            assert all(x['id']==i and Path(x['path']).resolve()==path for i,(x,path) in enumerate(zip(loaded,self.adapters.values())))
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def answer(self,messages,mode='base',max_tokens=48):
        if mode!='base' and mode not in self.ids:raise ValueError('Unknown adapter')
        active=self.ids.get(mode)
        scales=[{'id':i,'scale':1.0 if i==active else 0.0} for i in range(len(self.ids))]
        self.request('/lora-adapters',scales)
        actual={x['id']:x['scale'] for x in self.request('/lora-adapters')}
        assert all(actual[x['id']]==x['scale'] for x in scales)
        response=self.request('/v1/chat/completions',{'messages':messages,'temperature':0,'seed':32806,
            'max_tokens':max_tokens,'cache_prompt':False,'lora':scales,'stream':False})
        return response['choices'][0]['message']['content']
    def __exit__(self,*_):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.log.close()
