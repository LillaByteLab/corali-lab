"""Local PDF operations. Every result is a new file; no source is saved in place."""
from pathlib import Path
import base64
import io
import math
import pymupdf as pdf
from PIL import Image


def pages(spec, count):
    if not str(spec).strip():
        return list(range(count))
    result=[]
    for part in str(spec).replace(' ', '').split(','):
        if not part: raise ValueError('Intervallo di pagine non valido.')
        bits=part.split('-')
        if len(bits)>2: raise ValueError('Intervallo di pagine non valido.')
        start=int(bits[0]); end=int(bits[-1])
        if start<1 or end>count or end<start: raise ValueError('Le pagine indicate non sono presenti nel PDF.')
        result.extend(range(start-1,end))
    return result


def load(path, params, modify=False, owner=False):
    doc=pdf.open(path)
    auth=doc.authenticate(params.get('password','')) if doc.needs_pass else 6
    if not auth:
        doc.close();raise ValueError('Password del PDF mancante o errata.')
    if owner and not auth & 4:
        doc.close();raise ValueError('Serve la password del proprietario per rimuovere la protezione.')
    if modify and doc.is_encrypted and not (auth & 4 or doc.permissions & pdf.PDF_PERM_MODIFY):
        doc.close();raise ValueError('Questa password non autorizza la modifica del PDF.')
    if not len(doc): doc.close();raise ValueError('Il PDF non contiene pagine.')
    return doc


def info(path, params):
    with load(path,params) as doc:
        index=max(0,min(int(params.get('page',0)),len(doc)-1));page=doc[index]
        scale=min(2,1400/max(page.rect.width,page.rect.height))
        image=page.get_pixmap(matrix=pdf.Matrix(scale,scale),alpha=False).tobytes('png')
        fields=[{'name':w.field_name,'value':str(w.field_value or ''),'type':str(w.field_type_string)} for p in doc for w in (p.widgets() or [])]
        return {'pages':len(doc),'page':index,'text':page.get_text(),'width':page.rect.width,'height':page.rect.height,'preview':'data:image/png;base64,'+base64.b64encode(image).decode(),'fields':fields}


def color(value):
    text=str(value or '#174b58').lstrip('#')
    if len(text)!=6: raise ValueError('Colore non valido.')
    return tuple(int(text[i:i+2],16)/255 for i in (0,2,4))


def point(page,x,y):
    return pdf.Point(float(x)*page.rect.width,float(y)*page.rect.height)*page.derotation_matrix


def replace_text(page, old, new, font_file):
    hits=page.search_for(old)
    if not hits:return 0
    font=pdf.Font(fontfile=str(font_file));spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
    placements=[]
    for rect in hits:
        size=next((s['size'] for s in spans if pdf.Rect(s['bbox']).intersects(rect)),11)
        if '\n' in new or font.text_length(new,fontsize=size)>page.rect.width-rect.x0-10:
            raise ValueError('Il nuovo testo non entra nella riga. Usa una frase più corta o converti il documento in Word.')
        placements.append((rect,size))
        page.add_redact_annot(rect,fill=(1,1,1),cross_out=False)
    page.apply_redactions(images=0,graphics=0)
    page.insert_font(fontname='Corali',fontfile=str(font_file))
    for rect,size in placements:
        page.insert_text((rect.x0,rect.y1-size*.2),new,fontname='Corali',fontsize=size,color=(0,0,0))
    return len(placements)


def check_cancel(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError('Operazione annullata. Nessun risultato incompleto pubblicato.')


def compress_images(doc, mode, cancelled=None):
    if mode=='lossless':return
    limit,quality=(1200,48) if mode=='strong' else (2000,76)
    visited=set()
    for page in doc:
        check_cancel(cancelled)
        for item in page.get_images(full=True):
            check_cancel(cancelled)
            xref,smask=item[:2]
            if xref in visited or smask:continue
            visited.add(xref)
            try:
                raw=doc.extract_image(xref)['image']
                with Image.open(io.BytesIO(raw)) as image:
                    if 'A' in image.getbands() or image.width*image.height<100000:continue
                    image=image.convert('RGB');image.thumbnail((limit,limit))
                    output=io.BytesIO();image.save(output,'JPEG',quality=quality,optimize=True)
                if len(output.getvalue())<len(raw):page.replace_image(xref,stream=output.getvalue())
            except (ValueError,OSError):continue


def run(action,sources,params,dest,font_file,resolve,cancelled=None):
    check_cancel(cancelled)
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);output=dest/('documento-'+action+'.pdf')
    if action=='merge':
        if len(sources)<2:raise ValueError('Scegli almeno due PDF nell’ordine desiderato.')
        with pdf.open() as result:
            for source in sources:
                check_cancel(cancelled)
                with load(source,params) as doc:
                    # Keep whole-document insertion to preserve cross-page links.
                    # This native call completes before cancellation is observed.
                    result.insert_pdf(doc,widgets=True)
                check_cancel(cancelled)
            check_cancel(cancelled)
            result.save(output,garbage=4,deflate=True)
            check_cancel(cancelled)
        return [output]
    with load(sources[0],params,modify=True,owner=action=='unlock') as doc:
        selected=pages(params.get('pages',''),len(doc))
        if action in ('extract','organize','delete','split'):
            if action=='delete':selected=[n for n in range(len(doc)) if n not in selected]
            if not selected:raise ValueError('Il risultato deve contenere almeno una pagina.')
            outputs=[]
            groups=[[n] for n in selected] if action=='split' else [selected]
            for number,group in enumerate(groups):
                check_cancel(cancelled)
                path=dest/(f'pagina-{group[0]+1}-{number+1}.pdf' if action=='split' else output.name)
                with pdf.open() as result:
                    for n in group:
                        check_cancel(cancelled)
                        result.insert_pdf(doc,from_page=n,to_page=n,widgets=True)
                    check_cancel(cancelled)
                    result.save(path,garbage=4,deflate=True)
                    check_cancel(cancelled)
                outputs.append(path)
            return outputs
        if action=='rotate':
            degrees=int(params.get('degrees',90))
            if degrees%90:raise ValueError('La rotazione deve essere un multiplo di 90°.')
            for n in selected:
                check_cancel(cancelled)
                doc[n].set_rotation((doc[n].rotation+degrees)%360)
        elif action=='compress':compress_images(doc,params.get('mode','balanced'),cancelled)
        elif action=='replace':
            old=params.get('find','')
            if not old:raise ValueError('Scrivi il testo da cercare.')
            changes=0
            for n in selected:
                check_cancel(cancelled)
                changes+=replace_text(doc[n],old,params.get('replacement',''),font_file)
            if not changes:raise ValueError('Il testo non è stato trovato. Le scansioni richiedono prima il riconoscimento OCR.')
        elif action=='numbers':
            for n,page in enumerate(doc):
                check_cancel(cancelled)
                page.insert_text(point(page,.48,.96),str(n+1),fontsize=10,color=color('#174b58'))
        elif action=='watermark':
            text=params.get('text','').strip()
            if not text:raise ValueError('Scrivi il testo della filigrana.')
            for page in doc:
                check_cancel(cancelled)
                page.insert_font(fontname='Corali',fontfile=str(font_file))
                page.insert_text(point(page,.12,.5),text,fontname='Corali',fontsize=30,color=color('#174b58'),fill_opacity=.22)
        elif action=='form':
            values=params.get('fields',{});found=0
            for page in doc:
                check_cancel(cancelled)
                for widget in page.widgets() or []:
                    if widget.field_name in values:
                        if widget.field_type==pdf.PDF_WIDGET_TYPE_SIGNATURE:continue
                        widget.field_value=values[widget.field_name];widget.update();found+=1
            if not found:raise ValueError('Nessun campo compilabile trovato.')
        elif action=='annotate':
            for edit in params.get('edits',[]):
                check_cancel(cancelled)
                index=int(edit.get('page',0))
                if index<0 or index>=len(doc):raise ValueError('Pagina dell’annotazione non valida.')
                page=doc[index];kind=edit.get('type');ink=color(edit.get('color'))
                x,y=float(edit.get('x',0)),float(edit.get('y',0))
                if kind=='text':
                    size=float(edit.get('size',14))
                    if not 4<=size<=96:raise ValueError('Dimensione del testo non valida.')
                    page.insert_font(fontname='Corali',fontfile=str(font_file));page.insert_text(point(page,x,y),str(edit.get('text','')),fontsize=size,fontname='Corali',color=ink)
                elif kind=='highlight':
                    start=point(page,x,y-float(edit.get('height',.025)));end=point(page,x+float(edit.get('width',.3)),y)
                    page.draw_rect(pdf.Rect(start,end).normalize(),color=None,fill=(1,.8,.25),fill_opacity=.35,overlay=True)
                elif kind=='draw':
                    points=[point(page,*p) for p in edit.get('points',[])]
                    if len(points)>1:page.draw_polyline(points,color=ink,width=float(edit.get('size',2)),lineCap=1,lineJoin=1,overlay=True)
                elif kind=='image':
                    image_path=resolve(edit.get('imageId',''))
                    with Image.open(image_path) as im:ratio=im.height/im.width
                    width=float(edit.get('width',.3))*page.rect.width
                    rect=pdf.Rect(x*page.rect.width,y*page.rect.height,x*page.rect.width+width,y*page.rect.height+width*ratio)*page.derotation_matrix
                    page.insert_image(rect,filename=str(image_path),keep_proportion=True)
                else:raise ValueError('Tipo di annotazione non supportato.')
        elif action not in ('protect','unlock'):raise ValueError('Strumento PDF non disponibile.')
        options={'garbage':4,'deflate':True,'use_objstms':1,'encryption':pdf.PDF_ENCRYPT_KEEP}
        if action=='protect':
            password=params.get('newPassword','')
            if not 4<=len(password)<=40:raise ValueError('Scegli una password da 4 a 40 caratteri.')
            options.update(encryption=pdf.PDF_ENCRYPT_AES_256,owner_pw=password,user_pw=password,permissions=pdf.PDF_PERM_ACCESSIBILITY|pdf.PDF_PERM_PRINT|pdf.PDF_PERM_COPY|pdf.PDF_PERM_MODIFY|pdf.PDF_PERM_ANNOTATE|pdf.PDF_PERM_FORM)
        elif action=='unlock':options['encryption']=pdf.PDF_ENCRYPT_NONE
        check_cancel(cancelled)
        doc.save(output,**options)
        check_cancel(cancelled)
    return [output]
