/* Recording is explicit, local and limited to sixty seconds. */
export function spokenText(raw){
 const value=String(raw||''),start=value.search(/\[?\d{2}:\d{2}:\d{2}\]?/);
 return (start>=0?value.slice(start):value).replace(/\[?\d{2}:\d{2}:\d{2}\]?/g,'').trim();
}
export function dictation(onText,onState){
 let recorder=null,stream=null,timer=null,processing=false;
 const stop=()=>{if(recorder?.state==='recording')recorder.stop();};
 window.addEventListener('pagehide',()=>{clearTimeout(timer);stream?.getTracks().forEach(t=>t.stop());});
 return async()=>{
  if(recorder?.state==='recording'){stop();return;}
  if(processing)return;
  try{
   stream=await navigator.mediaDevices.getUserMedia({audio:true});const chunks=[];recorder=new MediaRecorder(stream);
   recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
   recorder.onstop=async()=>{
    processing=true;clearTimeout(timer);stream.getTracks().forEach(t=>t.stop());onState('Trascrizione locale in corso…',false);
    try{
     const response=await fetch('/import',{method:'POST',headers:{'X-Corali-Token':sessionStorage.getItem('corali-desktop-token')||'','X-Filename':'Richiesta%20vocale.webm'},body:new Blob(chunks,{type:recorder.mimeType})});const result=await response.json();if(!result.ok)throw Error(result.error);
     const r=await desktopRequest('/rpc',{cmd:'voiceText',id:result.data.id});onText(spokenText(r.text).slice(0,4000));onState('Dettatura pronta: controlla il testo, poi genera la proposta.',false);
    }catch(e){onState(e.message,false);}finally{processing=false;}
   };
   recorder.start();onState('Microfono attivo. Premi Ferma quando hai finito.',true);timer=setTimeout(stop,60000);
  }catch(e){stream?.getTracks().forEach(t=>t.stop());onState('Microfono non disponibile: '+e.message,false);}
 };
}
