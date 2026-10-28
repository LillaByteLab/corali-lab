"""Pure, bounded local operations. Model output selects a tool, never its data.

Prototype for training/evaluation, not yet connected to the installed app.
No file access, writes, networking, eval, or execution of model-generated code.
"""
import json,re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ACTIONS=('count','count_formula','sum_formula','discount','clarify','chat')
SYSTEM='Scegli una azione JSON: count (conta presenze), count_formula (formula di conteggio), sum_formula (formula somma), discount (sconto con percentuale), clarify (manca la regola), chat (altro). Rispondi solo con {"action":"nome"}. Non calcolare numeri.'

class NeedsReview(ValueError):pass

def requires_router(context):
    if type(context) is not dict:raise NeedsReview('Contesto non valido.')
    return any(key in context for key in ('cells','range','amount'))

def messages(question,context):
    # Raw document text/notes and actual cell values cannot instruct the router.
    flags={key:key in context for key in ('cells','range','criterion','amount','percent')}
    return [{'role':'system','content':SYSTEM},{'role':'user','content':question+'\nCampi disponibili: '+json.dumps(flags,separators=(',',':'))}]

def parse_action(text):
    if not isinstance(text,str) or len(text)>256:raise NeedsReview('Risposta AI non valida.')
    fenced=re.fullmatch(r'\s*```(?:json)?\s*([\s\S]+?)\s*```\s*',text)
    if fenced:text=fenced.group(1)
    try:obj=json.loads(text)
    except (ValueError,TypeError) as exc:raise NeedsReview('Risposta AI non valida.') from exc
    if type(obj) is not dict or set(obj)!= {'action'} or obj['action'] not in ACTIONS:
        raise NeedsReview('Operazione AI non riconosciuta.')
    return obj['action']

def checked_range(value):
    if not isinstance(value,str):raise NeedsReview('Intervallo mancante.')
    match=re.fullmatch(r'(\$?[A-Z]{1,3})(\$?[1-9][0-9]{0,6}):(\$?[A-Z]{1,3})(\$?[1-9][0-9]{0,6})',value)
    if not match:raise NeedsReview('Intervallo non valido.')
    def column(s):
        total=0
        for ch in s.replace('$',''):total=total*26+ord(ch)-64
        return total
    a,b,c,d=match.groups();coordinates=(column(a),int(b.replace('$','')),column(c),int(d.replace('$','')))
    x,y,z,w=coordinates
    if not (1<=x<=z<=16384 and 1<=y<=w<=1048576):raise NeedsReview('Intervallo fuori limite o invertito.')
    return value

def decimal(value):
    if type(value) not in (str,int):raise NeedsReview('Numero non verificato.')
    raw=str(value)
    if not re.fullmatch(r'\d{1,9}(?:[.,]\d{1,2})?',raw):raise NeedsReview('Formato numerico non valido.')
    try:return Decimal(raw.replace(',','.'))
    except InvalidOperation as exc:raise NeedsReview('Numero non valido.') from exc

def execute(action,context):
    if action not in ACTIONS or type(context) is not dict:raise NeedsReview('Richiesta non valida.')
    if action=='chat':return {'kind':'chat'}
    if action=='clarify':return {'kind':'clarification','question':'Quale percentuale o regola di riduzione devo applicare?'}
    if action=='count':
        cells=context.get('cells')
        if type(cells) is not list or not 1<=len(cells)<=10000:raise NeedsReview('Celle mancanti o troppo numerose.')
        if any(v not in ('P','A','R','U','M','',None) for v in cells):raise NeedsReview('Sigla non riconosciuta: controllare il documento.')
        declared=context.get('declared')
        if declared is not None and (type(declared) is not int or not 0<=declared<=10000):raise NeedsReview('Totale dichiarato non valido.')
        days=[i+1 for i,value in enumerate(cells) if value=='P'];blanks=sum(value in ('',None) for value in cells)
        return {'kind':'count','presenze_esplicite':len(days),'celle_vuote':blanks,'totale_dichiarato':declared,
                'differenza':None if declared is None else declared-len(days),'posizioni_P':days}
    if action in ('count_formula','sum_formula'):
        area=checked_range(context.get('range'))
        if action=='sum_formula':return {'kind':'formula','formula':f'=SUM({area})'}
        criterion=context.get('criterion')
        if not isinstance(criterion,str) or not re.fullmatch(r'[A-Za-z]{1,8}',criterion):raise NeedsReview('Criterio non verificato.')
        return {'kind':'formula','formula':f'=COUNTIF({area},"{criterion}")'}
    if 'percent' not in context:return execute('clarify',context)
    amount=decimal(context.get('amount'));percent=decimal(context['percent'])
    if not 0<=percent<=100:raise NeedsReview('Percentuale fuori limite.')
    result=(amount*(Decimal(100)-percent)/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return {'kind':'discount','amount':format(result,'.2f')}
