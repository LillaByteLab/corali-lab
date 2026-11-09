'use strict';const $=id=>document.getElementById(id),sid=new URLSearchParams(location.search).get('sid');let view=null,start=0,changes=new Map(),dirty=false,working=false;
const rpc=p=>desktopRequest('/csv-rpc?sid='+encodeURIComponent(sid),p);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function pending(){document.activeElement?.blur();return [...changes.values()];}
function column(i){let s='';for(i++;i>0;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s;}
function render(v){view=v;start=v.start;dirty=v.dirty||dirty;changes.clear();$('name').textContent=v.name;$('delimiter').value=v.delimiter;if(!$('encoding').dataset.chosen)$('encoding').value=v.encoding;$('count').textContent=`Righe ${v.count?start+1:0}–${Math.min(start+v.rows.length,v.count)} di ${v.count} · ${v.columns} colonne`;$('previous').disabled=start===0;$('next').disabled=start+50>=v.count;
 $('table').innerHTML='<thead><tr><th>#</th>'+Array.from({length:v.columns},(_,i)=>'<th>'+column(i)+'</th>').join('')+'</tr></thead><tbody>'+v.rows.map((row,n)=>'<tr><th>'+(start+n+1)+'</th>'+Array.from({length:v.columns},(_,c)=>`<td contenteditable="plaintext-only" role="textbox" aria-label="Riga ${start+n+1}, colonna ${column(c)}" data-row="${start+n}" data-column="${c}">${escape(row[c]||'')}</td>`).join('')+'</tr>').join('')+'</tbody>';
 $('table').querySelectorAll('td').forEach(cell=>{cell.oninput=()=>{const row=Number(cell.dataset.row),column=Number(cell.dataset.column);changes.set(row+':'+column,{row,column,value:cell.innerText.replace(/\r\n/g,'\n')});cell.classList.add('changed');dirty=true;message('● Modifiche da salvare');};});if(!dirty)message('Lettura e modifica locale. Il file originale è conservato.');}
function message(text){$('message').textContent=text;}
async function run(fn){if(working)return;working=true;document.body.classList.add('busy');try{await fn();}catch(e){message(e.message);}finally{working=false;document.body.classList.remove('busy');}}
async function apply(){if(changes.size){await rpc({cmd:'apply',changes:pending(),start});changes.clear();}}
async function move(next){await apply();render(await rpc({cmd:'view',start:next}));}
async function save(){const result=await rpc({cmd:'save',changes:pending(),encoding:$('encoding').value});changes.clear();dirty=false;render(await rpc({cmd:'view',start}));message('Copia pronta: '+result.name);$('export').hidden=false;$('reveal').hidden=false;return await exportCopy();}
$('save').onclick=()=>run(save);$('previous').onclick=()=>run(()=>move(Math.max(0,start-50)));$('next').onclick=()=>run(()=>move(start+50));
for(const [id,what]of [['addRow','row'],['addColumn','column']])$(id).onclick=()=>run(async()=>{render(await rpc({cmd:'add',what,changes:pending(),start}));dirty=true;message('● Modifiche da salvare');});
$('undo').onclick=()=>run(async()=>{changes.clear();render(await rpc({cmd:'view',start}));dirty=view.dirty;message(dirty?'Le modifiche delle altre pagine restano da salvare.':'Modifiche della pagina annullate.');});
$('delimiter').onchange=()=>run(async()=>{if(dirty||changes.size){$('delimiter').value=view.delimiter;throw Error('Salva prima la copia aperta.');}render(await rpc({cmd:'separator',delimiter:$('delimiter').value}));});$('encoding').onchange=()=>$('encoding').dataset.chosen='true';
async function exportCopy(){const result=await rpc({cmd:'export'});message(result.saved?'Copia salvata in: '+(result.path||'cartella scelta'):'Scelta cartella annullata. La copia resta nei Risultati.');return result.saved;}
$('export').onclick=()=>run(exportCopy);$('reveal').onclick=()=>run(()=>rpc({cmd:'share'}));
async function closeEditor(discard=false){await rpc({cmd:'close',discard});dirty=false;changes.clear();view=null;$('table').replaceChildren();location.href='/';}
$('back').onclick=()=>{if(working)return;if(dirty||changes.size)$('unsaved').showModal();else run(()=>closeEditor());};$('continue').onclick=()=>$('unsaved').close();$('discard').onclick=()=>run(()=>closeEditor(true));$('saveClose').onclick=()=>run(async()=>{if(await save()===false)return;await closeEditor();});
addEventListener('beforeunload',e=>{if(dirty||changes.size){e.preventDefault();e.returnValue='';}});
run(async()=>render(await rpc({cmd:'view'})));

window.coraliAssistantContext=async()=>({text:document.getElementById('table').innerText.slice(0,10000)});
import('../assistant-widget.js');
