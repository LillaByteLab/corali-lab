/* AI proposes an operation; only an explicit user selection produces a preview. */
import {dictation} from './dictation.js';
export function operationPanel(host,accept){
 if(!document.querySelector('link[data-operation-style]')){const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('./operation-panel.css',import.meta.url);link.dataset.operationStyle='true';document.head.append(link);}
 const root=document.createElement('details');root.className='panel operation-panel';root.innerHTML=`<summary>Calcoli e formule verificati</summary>
 <p>Compila i dati e scegli l’operazione. L’AI può suggerirla, ma devi confermarla. Nessuna modifica automatica al documento.</p>
 <label class="field">Richiesta, anche dettata<textarea data-field="question" maxlength="4000" rows="2" placeholder="Vorrei la formula che conta le P"></textarea></label>
 <button data-button="voice" type="button">● Detta la richiesta</button>
 <label class="field">Intervallo Excel<input data-field="range" placeholder="B2:AF2" maxlength="30"></label>
 <label class="field">Sigla da contare nella formula<input data-field="criterion" placeholder="P" maxlength="8"></label>
 <label class="field">Celle del registro: separa con punto e virgola o incolla da Excel<textarea data-field="cells" maxlength="30000" rows="3" placeholder="P;A;;P;M"></textarea></label>
 <p>Una sigla per cella: P, A, R, U, M. Due separatori consecutivi indicano una cella vuota. Il conteggio immediato conta soltanto le P.</p>
 <label class="field">Totale P dichiarato, facoltativo<input data-field="declared" inputmode="numeric" maxlength="5"></label>
 <label class="field">Importo iniziale<input data-field="amount" inputmode="decimal" maxlength="12" placeholder="100,00"></label>
 <label class="field">Sconto percentuale<input data-field="percent" inputmode="decimal" maxlength="6" placeholder="20"></label>
 <button data-button="suggest" type="button">Suggerisci con l’AI addestrata · sperimentale</button>
 <label class="field">Operazione da confermare<select data-field="action"><option value="">Scegli un’operazione…</option><option value="count">Conta le presenze P adesso</option><option value="count_formula">Crea formula COUNTIF</option><option value="sum_formula">Crea formula SUM</option><option value="discount">Calcola importo scontato</option><option value="clarify">Chiedi la regola mancante</option><option value="chat">Richiesta di conversazione</option></select></label>
 <button data-button="preview" type="button">Conferma operazione e calcola anteprima</button>
 <p data-output="message" role="status"></p><pre data-output="result" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>
 <button data-button="accept" type="button" disabled>Usa questa anteprima nella proposta</button>`;
 host.append(root);const field=n=>root.querySelector(`[data-field="${n}"]`),button=n=>root.querySelector(`[data-button="${n}"]`),output=n=>root.querySelector(`[data-output="${n}"]`);
 let preview=null,busy=false,revision=0;
 function clear(){revision++;preview=null;button('accept').disabled=true;output('result').textContent='';output('message').textContent='Dati aggiornati: ricalcola l’anteprima.';}
 root.querySelectorAll('input,textarea,select').forEach(el=>el.addEventListener('input',clear));
 function data(){
  const values={};for(const name of ['range','criterion','amount','percent'])if(field(name).value.trim())values[name]=field(name).value.trim();
  if(field('cells').value.length)values.cells=field('cells').value.replace(/\r\n?/g,'\n').split(/[;\t\n]/).map(x=>x.trim().toUpperCase());
  if(field('declared').value.trim()){if(!/^\d{1,5}$/.test(field('declared').value.trim()))throw Error('Il totale dichiarato deve essere un numero intero.');values.declared=Number(field('declared').value);}
  return values;
 }
 async function run(fn){if(busy)return;busy=true;button('suggest').disabled=button('preview').disabled=true;try{await fn();}catch(e){output('message').textContent=e.message;}finally{busy=false;button('suggest').disabled=button('preview').disabled=false;}}
 button('voice').onclick=dictation(text=>{field('question').value=text;clear();},(text,active)=>{button('voice').textContent=active?'■ Ferma dettatura':'● Detta la richiesta';output('message').textContent=text;});
 button('suggest').onclick=()=>run(async()=>{
  clear();const stamp=revision;output('message').textContent='Suggerimento sul PC…';
  const r=await window.desktopRequest('/rpc',{cmd:'aiSuggestOperation',prompt:field('question').value,data:data()});
  if(stamp!==revision)throw Error('I dati sono cambiati durante la richiesta: ripeti il suggerimento.');
  field('action').value=r.action;output('message').textContent=r.message+' Operazione proposta: '+field('action').selectedOptions[0].textContent;
 });
 button('preview').onclick=()=>run(async()=>{
  clear();const stamp=revision,action=field('action').value;if(!action)throw Error('Scegli prima l’operazione.');
  const r=await window.desktopRequest('/rpc',{cmd:'operationPreview',action,data:data()});
  if(stamp!==revision)throw Error('I dati sono cambiati: ricalcola l’anteprima.');
  const value=r.result;let text='';
  if(value.kind==='count')text=`Presenze P: ${value.presenze_esplicite}\nCelle vuote: ${value.celle_vuote}\nPosizioni P: ${value.posizioni_P.join(', ')||'nessuna'}${value.totale_dichiarato===null?'':`\nTotale dichiarato: ${value.totale_dichiarato}\nDifferenza (dichiarato meno conteggiato): ${value.differenza}`}`;
  else if(value.kind==='formula')text=value.formula;
  else if(value.kind==='discount')text='Importo dopo lo sconto: '+value.amount;
  else if(value.kind==='clarification')text=value.question;
  else text='Per questa richiesta usa il pannello di conversazione dell’assistente.';
  preview={text,formula:value.kind==='formula'?value.formula:'',value};output('result').textContent=text;
  output('message').textContent='Anteprima calcolata sul PC. Controlla dati e operazione; il documento non è stato modificato.';button('accept').disabled=false;
 });
 button('accept').onclick=()=>{if(!preview)return;accept(preview);output('message').textContent='Anteprima trasferita nella proposta. Nessuna modifica applicata al documento.';};
 return root;
}
