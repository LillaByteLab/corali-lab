import {DOMParser, XMLSerializer, unzipSync, zipSync, strFromU8, strToU8} from './compat/xml-tools.js';

const MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const XMLNS='http://www.w3.org/2000/xmlns/';

/** Equivalent XML names, never rewritten cell values or formula text. The source stays immutable. */
export function normalizeSpreadsheetNamespaces(bytes){
    let expanded=0,count=0;
    const entries=unzipSync(bytes,{filter:entry=>{
        if(++count>30000||entry.originalSize>200*1024*1024||(expanded+=entry.originalSize)>200*1024*1024)throw Error('Il documento supera il limite di memoria Office.');
        return true;
    }});
    let changed=0;
    for(const [name,data] of Object.entries(entries)){
        if(!/^xl\/.+\.xml$/i.test(name))continue;
        const text=strFromU8(data);if(/<!DOCTYPE/i.test(text))throw Error('Il documento contiene una dichiarazione XML non supportata.');
        const doc=new DOMParser({onError:(level,message)=>{if(level!=='warning')throw Error('XML Office non valido: '+message);}}).parseFromString(text,'application/xml');
        const root=doc.documentElement;if(!root||root.namespaceURI!==MAIN)continue;
        let needed=false;
        const inspect=node=>{if(node.nodeType!==1)return;if(node.namespaceURI===MAIN&&node.prefix)needed=true;for(let i=0;i<node.attributes.length;i++){const a=node.attributes.item(i);if(a.namespaceURI===REL&&a.prefix!=='r')needed=true;}for(let child=node.firstChild;child;child=child.nextSibling)inspect(child);};inspect(root);
        if(!needed)continue;
        const target=doc.implementation.createDocument(null,null,null);
        const copy=node=>{
            if(node.nodeType!==1)return target.importNode(node,true);
            const element=target.createElementNS(node.namespaceURI,node.namespaceURI===MAIN?node.localName:node.nodeName);
            for(let i=0;i<node.attributes.length;i++){
                const a=node.attributes.item(i);if(a.namespaceURI===XMLNS&&a.name==='xmlns'&&node.namespaceURI===MAIN)continue;
                element.setAttributeNS(a.namespaceURI,a.namespaceURI===REL?'r:'+a.localName:a.name,a.value);
            }
            if(node===root){element.setAttributeNS(XMLNS,'xmlns',MAIN);element.setAttributeNS(XMLNS,'xmlns:r',REL);}
            for(let child=node.firstChild;child;child=child.nextSibling)element.appendChild(copy(child));
            return element;
        };
        for(let node=doc.firstChild;node;node=node.nextSibling)target.appendChild(copy(node));
        entries[name]=strToU8(new XMLSerializer().serializeToString(target));changed++;
    }
    return {bytes:changed?zipSync(entries,{level:6}):bytes,changed};
}
