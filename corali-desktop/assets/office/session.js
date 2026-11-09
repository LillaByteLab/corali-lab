import {Odr} from './engine/index.js';
import {normalizeSpreadsheetNamespaces} from './ooxml-compat.js';

/** Engine state shared by the worker and round-trip tests. Original bytes stay immutable. */
export class OfficeSession {
    constructor(engine){this.engine=engine;this.doc=null;this.batches=[];this.logs=[];this.original=null;this.name='';this.allowed=false;this.dirty=false;this.encrypted=false;this.calculation={changed:[],circular:[],unevaluated:[]};}
    static async create(){return new OfficeSession(await Odr.load());}
    options(){return {name:this.name,editable:this.allowed,allowExternalContent:false,embedImages:true,textDocumentMargin:true,keyboardNavigation:true,keyboardShortcuts:true,sheetEditOnClick:true,viewportWidth:this.width,lazyLayout:true,spreadsheetLimit:{rows:100000,columns:500},spreadsheetCellLimit:500000};}
    open(bytes,name,{editable=true,width=390,reason=''}={}){
        this.close();if(bytes.byteLength>50*1024*1024)throw Error('Questa versione apre documenti fino a 50 MB.');
        this.original=new Uint8Array(bytes);this.name=name;this.allowed=editable;this.width=width;this.reason=reason;this.batches=[];this.dirty=false;this.logs=[];this.calculation={changed:[],circular:[],unevaluated:[]};
        this.engine.setLogger((level,message)=>{if(this.logs.length<60&&!this.logs.includes(message))this.logs.push(message);},this.engine.enums.LogLevel.warning);
        const fixed=/\.(xlsx|xlsm|xltx|xltm)$/i.test(name)&&this.original[0]===0x50&&this.original[1]===0x4b?normalizeSpreadsheetNamespaces(this.original):{bytes:this.original,changed:0};
        this.engineBytes=fixed.bytes;this.compatibility={namespaceNormalized:!!fixed.changed,xmlParts:fixed.changed};
        const decode=()=>{
            this.doc=this.engine.open(this.engineBytes,this.options());this.encrypted=this.doc.isPasswordEncrypted();if(this.encrypted){this.allowed=false;this.reason='Documento protetto: aperto in sola lettura per conservarne la protezione.';return {passwordRequired:true,name};}
            if(this.allowed)this.calculation=this.doc.recalculate();
            return this.describe();
        };
        return decode();
    }
    decrypt(password){this.doc.decrypt(password);return this.describe();}
    describe(){let views=this.doc.listViews();const type=this.engine.fileTypes().find(t=>t.fileType===this.doc.fileType);if(views.length>1&&/^(xlsx|xls|ods|pptx|ppt|odp)$/.test(type?.name||''))views=views.filter(v=>v.index!==0);return {name:this.name,type:type?.name||'',views,editable:this.allowed&&this.doc.isEditable()&&this.doc.isSavable(),reason:this.reason,dirty:this.dirty,logs:[...this.logs],calculation:this.calculation,compatibility:this.compatibility,engine:this.engine.version()};}
    apply(diff){
        if(!this.allowed)throw Error(this.reason||'Questo documento è in sola lettura.');const parsed=JSON.parse(diff);if(parsed.version!==2||!Array.isArray(parsed.ops)||parsed.ops.length>100000)throw Error('Modifiche non valide.');if(!parsed.ops.length)return this.describe();
        // The engine can apply part of a failing batch. Replay on a fresh decode so failure is atomic.
        const candidate=this.engine.open(this.engineBytes,this.options());
        try{for(const batch of this.batches)candidate.edit(batch);candidate.edit(diff);}catch(error){candidate.close();throw error;}
        this.doc.close();this.doc=candidate;this.batches.push(diff);this.dirty=true;return this.describe();
    }
    render(index){const views=this.doc.listViews();if(!views.some(v=>v.index===index))throw Error('Pagina o foglio non disponibile.');const content=this.doc.render(index);return {...content,meta:this.describe()};}
    assistantApply(diff){const before=[...this.batches];const result=this.apply(diff);this.assistantBefore=before;this.assistantLength=this.batches.length;return result;}
    assistantUndo(){
        if(!this.assistantBefore||this.batches.length!==this.assistantLength)throw Error('Annulla prima le modifiche successive oppure riapri la copia originale.');
        const candidate=this.engine.open(this.engineBytes,this.options());try{for(const batch of this.assistantBefore)candidate.edit(batch);}catch(e){candidate.close();throw e;}
        this.doc.close();this.doc=candidate;this.batches=this.assistantBefore;this.assistantBefore=null;this.dirty=true;return this.describe();
    }
    recalculate(){this.calculation=this.doc.recalculate();return this.describe();}
    save(){
        if(!this.allowed||!this.doc.isSavable())throw Error(this.reason||'Il salvataggio non è disponibile per questo documento.');
        this.calculation=this.doc.recalculate();const bytes=this.doc.save();
        // Re-open the actual serialized package before returning it to the Android file bridge.
        const check=this.engine.open(bytes,{...this.options(),editable:false});try{if(check.fileType!==this.doc.fileType||check.listViews().length!==this.doc.listViews().length)throw Error('Il controllo del documento salvato non è riuscito.');}finally{check.close();}
        return {bytes,meta:this.describe()};
    }
    markSaved(){this.dirty=false;return this.describe();}
    close(){if(this.doc)this.doc.close();this.doc=null;}
}
