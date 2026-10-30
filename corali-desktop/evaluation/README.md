# Prova delle istruzioni AI - 0.5.4

30 casi sintetici, cinque famiglie, sei varianti ciascuna. Qwen2.5 1.5B Q4_K_M ufficiale,
CPU ARM64, seed 42; nessun adattatore, nessun documento privato. Il pacchetto addestrato
opzionale usa una base diversa: questa prova non ne certifica le risposte.
Risposte integrali in baseline-0.5.4.json e candidate-0.5.4.json. Revisione semantica
effettuata dall'agente di sviluppo, non da un valutatore indipendente.

| Famiglia | Prima | Nuove istruzioni |
|---|---|---|
| Pagamento non documentato | 6/6 inventano l'incasso | 6/6 si astengono; una risposta abbreviata e una con motivazione errata |
| Requisito sconosciuto | 6/6 concludono erroneamente no | 5/6 riconoscono il dato mancante; 1/6 ancora errata |
| Istruzione ingannevole nel documento | 6/6 seguono l'istruzione | 6/6 ancora errate |
| Date in conflitto | 6/6 scelgono arbitrariamente | 6/6 si astengono, ma non esplicitano correttamente entrambe le fonti |
| Due persone distinte | 6/6 corrette | 6/6 corrette |

Non si calcola una percentuale generale di accuratezza: le varianti sono correlate,
alcune risposte sono parziali e la resistenza alle istruzioni ingannevoli resta insufficiente.
Nessuna promessa di eliminazione delle allucinazioni o di protezione universale.
Le istruzioni migliorate vengono adottate con avvisi espliciti; nessuna risposta viene
applicata automaticamente. Il modello 4B suggerito nell'issue resta da valutare separatamente.

Riproduzione: python evaluate_assistant.py --data CARTELLA_TEST --arch arm64 --output risposte.json
La cartella deve contenere il runtime e il modello ufficiali del manifest; lo script non scarica nulla.
Per il confronto storico: --implementation percorso/della/local_ai.py/della/0.5.3.
