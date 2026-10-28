"""Narrow, explicit local operations. Ambiguous requests return to the model."""
import re

def verified_answer(prompt, context):
    request=prompt.casefold()
    if re.search(r'\bnon\s+(?:contare|conteggiare)|\b(?:oppure|tranne|escluso|eccetto|moltiplica|dividi|sottrai)\b',request):return None
    # Single-condition exact equality only. Never guess ranges or composite rules.
    if 'formula' in request and re.search(r'conta|contegg',request):
        ranges=re.findall(r'\b\$?[A-Z]{1,3}\$?[1-9][0-9]*:\$?[A-Z]{1,3}\$?[1-9][0-9]*\b',prompt+' '+context)
        criteria=re.findall(r'uguali?\s+(?:ad?\s+)?["\x27]?([A-Za-z])["\x27]?(?=[\s,.!?;]|$)',prompt)
        if len(set(ranges))==1 and len(criteria)==1 and not re.search(r'maggiore|minore|divers|oppure|almeno|somma|percent| e (?:a|p|r|u|m)\b',request):
            return 'Formula verificata con una regola locale:\n=COUNTIF('+ranges[0]+',"'+criteria[0].upper()+'")\nConta solo le celle uguali alla sigla indicata; le celle vuote sono escluse.'
    # Count one explicitly supplied list only. Refuse duplicate day numbers and prose instructions.
    if not re.search(r'quante|contegg|conta|presenze esplicite',request) or re.search(r'\b[ARUM]\b',prompt):return None
    entries=re.findall(r'(?<!\d)(\d{2})\s*=\s*(P|A|R|U|M|vuoto)(?!\w)',context,re.I)
    if not entries or len({d for d,_ in entries})!=len(entries):return None
    if any(not 1<=int(d)<=31 for d,_ in entries):return None
    remainder=re.sub(r'(?<!\d)\d{2}\s*=\s*(?:P|A|R|U|M|vuoto)(?!\w)','',context,flags=re.I)
    declared=re.findall(r'Totale\s+P\s+(?:dichiarato\s*|nel PDF\s*)?=\s*(\d+)\b',remainder,re.I)
    remainder=re.sub(r'Totale\s+P\s+(?:dichiarato\s*|nel PDF\s*)?=\s*\d+\b','',remainder,flags=re.I)
    if re.sub(r'[\s,.;:]+','',remainder) or len(declared)>1:return None
    if not re.search(r'\bP\b|presenze',prompt,re.I):return None
    days=[d for d,v in entries if v.upper()=='P'];blanks=sum(v.lower()=='vuoto' for _,v in entries)
    answer='Conteggio verificato con una regola locale: '+str(len(days))+' presenze P esplicite.'
    if days:answer+=' Giorni: '+', '.join(days)+'.'
    answer+=' Celle vuote: '+str(blanks)+', escluse dal conteggio.'
    if declared:
        total=int(declared[0]);answer+=' Totale P dichiarato: '+str(total)+'.'
        answer+=(' Coincide con le sigle esplicite.' if total==len(days) else ' Non coincide: differenza '+str(total-len(days))+' (dichiarato meno conteggiato). Il totale originale resta invariato.')
    return answer
