import {OfficeSession} from './session.js';
const sessionPromise=OfficeSession.create();
self.onmessage=async({data})=>{
    const {id,cmd}=data;
    try{
        const session=await sessionPromise;let result;
        switch(cmd){
            case 'open':result=session.open(new Uint8Array(data.bytes),data.name,data.options);break;
            case 'decrypt':result=session.decrypt(data.password);break;
            case 'render':result=session.render(data.index);break;
            case 'apply':result=session.apply(data.diff);break;
            case 'assistantApply':result=session.assistantApply(data.diff);break;
            case 'assistantUndo':result=session.assistantUndo();break;
            case 'recalculate':result=session.recalculate();break;
            case 'save':result=session.save();break;
            case 'markSaved':result=session.markSaved();break;
            case 'close':session.close();result={};break;
            default:throw Error('Comando del motore non disponibile.');
        }
        const transfer=result?.bytes instanceof Uint8Array?[result.bytes.buffer]:[];
        self.postMessage({id,ok:true,data:result},transfer);
    }catch(error){self.postMessage({id,ok:false,error:error.message||String(error),name:error.name,code:error.code});}
};
