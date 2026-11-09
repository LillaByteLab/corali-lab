(function(){
    'use strict';
    const token=window.CORALI_CHANNEL;
    const send=(type,detail)=>parent.postMessage({corali:token,type,detail},'*');
    function ready(){
        const odr=window.odr;
        if(!odr){send('error',{message:'Il visualizzatore non ha inizializzato i comandi.'});return;}
        for(const [name,event]of Object.entries({onEditChange:'change',onEditRefused:'refused',onEditModeChange:'mode',onCellsStale:'stale',onSelectionChange:'selection',onSearchChange:'search'}))odr[name]=detail=>send(event,detail);
        odr.onZoomChange=(zoom,followsFit)=>send('zoom',{zoom,followsFit});odr.onError=(code,message)=>send('error',{code,message});
        send('ready',{editable:!!odr.editing?.isEditable()});
    }
    document.addEventListener('click',event=>{if(event.target.closest?.('a[href]')){event.preventDefault();send('link',{message:'I collegamenti esterni restano disattivati nel lettore offline.'});}},true);
    window.addEventListener('message',event=>{
        const m=event.data;if(event.source!==parent||!m||m.corali!==token||m.type!=='command')return;
        const reply=(value,error)=>send('reply',{id:m.id,value,error});
        const run=()=>{try{const odr=window.odr,e=odr.editing;let value;
            switch(m.cmd){
                case 'operations':value=e.getOperations();break;
                case 'assistantContext':{
                    const selection=window.getSelection(),element=selection?.anchorNode?.nodeType===1?selection.anchorNode:selection?.anchorNode?.parentElement;
                    const run=element?.closest?.('x-s[data-odr-id]');
                    value={text:(selection?.toString()||document.body.innerText).slice(0,10000),runId:run?Number(run.dataset.odrId):null,runText:run?.textContent||''};break;
                }
                case 'assistantTarget':value=document.querySelector('x-s[data-odr-id="'+Number(m.arg)+'"]')?.textContent??null;break;
                case 'enable':value=e.enable();break;case 'disable':value=e.disable();break;
                case 'committed':value=e.committed();break;
                case 'undo':value=e.undo();break;case 'redo':value=e.redo();break;
                case 'toggle':if(!['bold','italic','underline','strikethrough'].includes(m.arg))throw Error('Formato non valido.');value=e.toggle(m.arg);break;
                case 'format':value=e.format(m.arg);break;
                case 'insertRows':value=e.insertRows(m.arg);break;case 'deleteRows':value=e.deleteRows();break;
                case 'insertColumns':value=e.insertColumns(m.arg);break;case 'deleteColumns':value=e.deleteColumns();break;
                case 'search':value=odr.search(m.arg);break;case 'nextMatch':value=odr.searchNext();break;case 'previousMatch':value=odr.searchPrevious();break;
                case 'zoomIn':value=odr.adjustZoom(1.2);break;case 'zoomOut':value=odr.adjustZoom(1/1.2);break;case 'fit':value=odr.resetZoom();break;
                default:throw Error('Comando non disponibile.');
            }reply(value);
        }catch(error){reply(null,error.message||String(error));}};
        if(m.cmd==='operations'){const active=document.activeElement;if(active&&/^(INPUT|TEXTAREA)$/.test(active.tagName))active.blur();setTimeout(run,0);}else run();
    });
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready();
})();
