# Coralì Lab 0.5.2 beta

## Origini e riconoscimenti

Coralì Lab è nato a partire da [Cedro](https://github.com/realfulvio/cedro), creato da **Luca Accorsi ([realfulvio](https://github.com/realfulvio))** e distribuito con licenza MIT. Cedro ha fornito la base iniziale del progetto e il motore per le conversioni, l’OCR e le trascrizioni integrate. A questo lavoro Coralì Lab affianca la propria interfaccia e le funzioni aggiuntive per documenti, fogli di calcolo e AI locale. Grazie a Luca per aver condiviso il suo lavoro come software open source.

La beta 0.5.2 incorpora **Cedro 0.21.2**: [release originale](https://github.com/realfulvio/cedro/releases/tag/v0.21.2). Coralì Lab è un progetto indipendente; le licenze e i riconoscimenti dei componenti originali sono conservati.

## Collaudo aggiuntivo del 28 ottobre 2026

16 PDF con dati inventati: mesi di 28–31 giorni, tre scale di pagina, giorni mancanti o duplicati, scansione e totale incoerente. Le intestazioni incomplete vengono rifiutate; gli scostamenti nei totali restano segnalati. I registri reali già verificati conservano gli stessi risultati.

L'assistente usa regole locali esplicite per riconoscere alcune richieste semplici di COUNTIF e conteggiare liste giornaliere esplicite. La risposta indica quando proviene da una regola verificata. Le altre richieste restano affidate al modello generativo e richiedono controllo: nei test il modello da solo ha sbagliato conteggi e formule. Il suggeritore opzionale 0.5.2 è stato addestrato con LoRA; propone soltanto una operazione che richiede conferma. La conversazione generale non usa questo adattatore. Le risposte interrotte per lunghezza vengono segnalate.

Applicazione Windows di supporto per PDF, documenti, fogli di calcolo, CSV, trascrizioni e assistenza AI locale. Versioni ARM64 e x64 con gli stessi sorgenti e le stesse funzioni. Progetto open source; vedere il README nella radice per lo stato della distribuzione. Il collaudo x64 su un PC fisico rimane da eseguire.

## Avvio e dati

Aprire Coralì Lab dall’icona sul Desktop oppure CoraliLab.exe nel pacchetto estratto. I dati rimangono in USERPROFILE/CoraliLab, separati dall’installazione. Le importazioni sono copie; le elaborazioni creano nuovi risultati. Le versioni precedenti sono conservate per ripristino.

Requisiti del pacchetto: Windows 11 a 64 bit, .NET Framework 4.8.1 e WebView2. L’AI è stata provata su un Surface ARM64 con circa 16 GB di RAM. Modello facoltativo di circa 1,1 GB, caricato soltanto alla prima richiesta; il consumo effettivo osservato del processo AI era circa 2 GB. Prestazioni non garantite su qualsiasi PC. Il pulsante Scarica il modello dalla RAM ferma il servizio senza cancellare il modello dal disco.

## Assistente e strumenti

Dalla schermata iniziale aprire Assistente e strumenti.

- Assistente AI: contesto opzionale da un documento, richiesta scritta, risposta modificabile e copie Word/TXT. Il modello compatto può sbagliare: le risposte sono proposte, non risultati certificati.
- Dettatura: pulsante Detta la richiesta, Ferma per terminare, massimo 60 secondi. La voce è trascritta sul PC; controllare la richiesta prima di inviarla all’AI. Il flusso WebM è verificato; la cattura dal microfono reale è da provare con l’utente.
- Editor documenti e fogli: pulsante AI locale. Caricare selezione o vista corrente. Nel foglio indicare esplicitamente cella e valore/formula da applicare; nel documento selezionare un segmento di testo. Anteprima e conferma prima della sostituzione. Annulla applicazione AI ripristina l’ultima applicazione se non ci sono modifiche successive. Salva copia conserva l’originale. Formule limitate a riferimenti locali e funzioni di calcolo ammesse; niente esecuzione di codice o macro.
- Tariffe e riduzioni: anteprima con aritmetica decimale, riduzione percentuale esplicita, arrotondamento al centesimo metà verso l’alto; Excel con formula ROUND. Non deduce automaticamente regolamenti, decorrenze o tariffe mancanti. La regola configurata va verificata dall’utente.
- Da PDF a Excel: profilo Registri presenze per registri mensili con struttura riconoscibile; una persona per riga, nessuna cella unita, mesi separati, sigle giornaliere e totali originali. Le differenze tra sigle e totali rimangono segnalate nella colonna Controllo. Profilo Tabelle generiche per tabelle native riconosciute da PyMuPDF. Non è un convertitore universale di scansioni o tabelle arbitrarie. I casi non riconosciuti vengono fermati senza inventare dati.
- Pagine PDF: miniature in gruppi di 12, trascinamento o frecce, copia con nuovo ordine e confronto affiancato delle pagine sorgente/risultato. Per eliminazione, estrazione e rotazione sono disponibili gli strumenti PDF principali.
- Rivedi trascrizioni: scegliere audio/video e testo TXT/Word, riascoltare dai riferimenti temporali, modificare e salvare nuove copie. Le ripetizioni sospette vengono segnalate, mai eliminate automaticamente. Le revisioni oltre 40000 caratteri mostrano un avviso: viene salvato solo l’estratto mostrato.
- Operazioni in serie: compressione PDF o conversione, esito per file, annullamento della coda. Usare documenti dello stesso formato per una conversione comune.
- Percorsi guidati: PDF/scansione verso Word tramite Cedro, apertura nell’editor e salvataggio; compressione separata del PDF originale. Le modifiche Word non vengono reinserite automaticamente nel PDF.
- Preferenze: cartella esistente di salvataggio e opzione di salvataggio diretto. Senza tale opzione viene chiesto dove salvare. I file già presenti non vengono sovrascritti dal salvataggio diretto.

I miei file e Risultati includono ricerca, filtro, ordinamento e creazione di copie con nomi personalizzati.

## Riservatezza e AI

Qwen2.5 1.5B Instruct Q4_K_M e llama.cpp b11936, con URL e digest fissati in ai-manifest.json. Internet serve per scaricare i componenti, non per inviare prompt o documenti. L’inferenza usa un processo locale vincolato a 127.0.0.1 con chiave casuale e opzioni offline/no-webui; nessun ripiego cloud. Il testo dei documenti non può avviare azioni o eseguire comandi. Il primo download è separato dal pacchetto per non imporre il modello a chi non usa l’AI.

Servizio Coralì su loopback e token di sessione. Documenti Office in iframe con origine opaca, senza accesso al servizio e con risorse esterne bloccate. Il microfono è consentito solo alla pagina locale principale quando richiesto dall’app.

I documenti reali di collaudo, email, risultati e cache non appartengono agli esempi pubblici. Gli esempi distribuiti devono essere interamente sintetici. La beta pubblicata include gli esiti delle verifiche di licenze e degli audit di dati, sorgenti e pacchetti. Il collaudo x64 fisico resta da eseguire. I componenti mantengono le proprie licenze; il codice originale desktop è distribuito sotto AGPL-3.0-only; vedere LICENSE e THIRD-PARTY-SOURCES.txt.

## Funzioni precedenti

PDF: unione, separazione, estrazione, eliminazione, riordino, rotazione, compressione, testo/annotazioni/immagini, sostituzione di testo nativo compatibile, moduli, filigrana, numeri di pagina e password. Una firma disegnata è un segno grafico, non una firma digitale certificata. Le scansioni richiedono OCR.

Documenti: apertura e modifica compatibile di DOCX, XLSX, PPTX e OpenDocument. Macro, firme e restrizioni in sola lettura. La compatibilità e l’impaginazione dipendono dal documento. CSV con valori come testo, zeri iniziali e codifica conservati; non esegue formule.

Trascrizioni Cedro in Word e TXT con modelli locali. Download e avanzamento visibili, ripiego CPU per alcuni errori GPU. La qualità va controllata: il collaudo di un estratto non certifica l’accuratezza di ogni audio.

Conversioni, OCR e operazioni CLI Cedro integrate. Video web con yt-dlp e FFmpeg; richiede internet e non garantisce ogni sito. FFmpeg x64 viene scaricato direttamente dal produttore al primo utilizzo video, con verifica SHA-256; su ARM usa la compatibilità Windows.

## Sorgenti e verifiche

app.py: servizio autenticato e gestione documenti; NativeHost.cs: finestra nativa e salvataggio; advanced.py: percorsi avanzati; local_ai.py: componenti AI e inferenza locale; workspace_tools.py: registri, esportazione OOXML e calcoli decimali; assets/: interfaccia, editor Office e motore WASM; pdf_tools.py e csv_tools.py: strumenti base. Le specifiche PyInstaller separate scelgono il motore Cedro corrispondente all’architettura. Il modello AI è esterno al pacchetto.

50 test Python superati sia con Python ARM64 sia con Python x64 in emulazione Windows ARM. Test Office: formula, ricalcolo, salvataggio e annullamento; generazione Word/XLSX e verifica nei motori reali. Collaudo del backend ARM64 confezionato: inferenza reale, tariffe, contesto documenti, registro con avvisi, trascrizione WebM e accesso audio per intervalli. Backend x64 confezionato avviato e verificato in emulazione, comprese conversioni Cedro PDF-testo. Questo non sostituisce il collaudo su hardware x64.

Eseguire i test con python -m unittest discover -s corali-desktop -p "test_*.py" dalla radice del progetto. I rapporti di collaudo descrivono lo stato prima della pubblicazione; vedere il README nella radice.

## Novità 0.5.2 beta

Calcoli e formule verificati è disponibile nel laboratorio e nel pannello Office. Conteggi, COUNTIF, SUM e sconti hanno dati espliciti, anteprima e conferma. La proposta AI sperimentale è facoltativa; non esegue operazioni automaticamente. I modelli del pacchetto ai-pack vengono verificati con SHA-256 prima di caricarli. Il suggeritore libera la memoria dopo ogni risposta.

Leggere INSTALLAZIONE.txt per la prova, RELEASE-0.5.2.txt per risultati e limiti e BUILD.txt per ricostruire l’app. FFmpeg non è incluso nei pacchetti: viene scaricato direttamente dal produttore quando serve per un video web. Le attribuzioni e i sorgenti di terze parti sono indicati in THIRD-PARTY-SOURCES.txt.
