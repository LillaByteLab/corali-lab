# Coralì Lab

## Componenti open source

Coralì Lab incorpora [Cedro](https://github.com/realfulvio/cedro) **0.26.10**, componente open source con licenza MIT per conversioni, OCR e trascrizioni. [Release originale](https://github.com/realfulvio/cedro/releases/tag/v0.26.10). Coralì Lab è un progetto indipendente; copyright, licenze e sorgenti dei componenti sono conservati e distribuiti con il programma.

Un laboratorio locale per PDF, documenti, fogli di calcolo, trascrizioni e assistenza AI, con un'interfaccia in italiano. È uno strumento di supporto: la compatibilità non equivale a quella di una suite Office completa.

**Versione 0.5.10 beta per Windows.** Scarica il pacchetto x64 per Intel o AMD oppure ARM64 per un Surface con Snapdragon. Estrai tutto lo ZIP, apri la cartella CoraliLab e avvia CoraliLab.exe. [Pacchetti, sorgenti e impronte SHA-256](https://github.com/LillaByteLab/corali-lab/releases/tag/v0.5.10-beta).

## Edizione 0.5.10

Conversione in MP3, estrazione audio e trascrizione partono da un file sul dispositivo. Il motore Cedro incorporato è compilato per operazioni su file locali. [Istruzioni](corali-desktop/RELEASE-0.5.10.txt).

## Aggiornamento 0.5.9

In **Assistente e strumenti → Presenze mensa** trovi il confronto per corso, il riepilogo Excel e il CSV mensile. Il foglio di verifica si chiama **Confronto modello**.

## Aggiornamento 0.5.8

In **Presenze mensa** puoi ora scegliere **Converti i totali mensili in X**. Con 4 pasti il programma inserisce 4 X nelle prime 4 colonne giornaliere, in ordine cronologico. Queste posizioni sono convenzionali. Se il prospetto contiene le date effettive, il programma le conserva. Puoi controllare la griglia e i conteggi per alunno prima di salvare.

Le identità discordanti sono segnalate con la riga da verificare. Quando è disponibile una bozza parziale, il programma lascia vuote le righe da chiarire. L’importazione finale nel gestionale è manuale. [Guida alla versione](corali-desktop/RELEASE-0.5.8.txt).

## Aggiornamento 0.5.7

Lo strumento **Presenze mensa** prepara un riepilogo Excel dal prospetto unico della scuola e lo confronta con la stampa mensile del gestionale per corso e alunno. Con i soli totali mensili genera il riepilogo. Per preparare il CSV servono date documentate e abbinamenti verificati. L’importazione nel gestionale resta manuale. Il profilo **Da PDF a Excel** conserva le sigle composte dei registri mensili e segnala le differenze fra conteggi e totali stampati.

105 test automatici superati su ARM64 e 105 su x64 in emulazione. La compatibilità dell’importazione nel gestionale e il funzionamento su hardware Intel/AMD fisico restano da verificare. [Guida alla versione](corali-desktop/RELEASE-0.5.7.txt).

## Aggiornamento 0.5.5

Trasferimenti a blocchi, indice incrementale in memoria, cache dei cataloghi basata anche sul contenuto, trascrizioni in coda, salvataggi completi e recupero prudente dei file interrotti. Pulizia automatica facoltativa nel cestino. Assistente locale disattivabile, caricamento iniziale facoltativo, rilascio dopo inattività e prova di velocità.

**Qwen3 4B è un download facoltativo di circa 2,5 GB**, verificato tramite hash e revisione fissata: almeno 3 GB di RAM libera per avviarlo. Il profilo leggero resta predefinito. Il suggeritore con LoRA resta separato. L'AI può sbagliare: proposte da verificare, mai applicate automaticamente. Nessun nuovo addestramento dei pesi.

98 test ARM64 e 98 x64 in emulazione; risultati dei pacchetti in `docs/COLLAUDO-PACCHETTI-0.5.5.json`. Risposte AI integrali e limiti in `corali-desktop/evaluation/REVIEW-0.5.5.md`. Il collaudo non certifica tutte le impaginazioni Office, il microfono fisico, Intel/AMD fisico o accelerazione GPU.

## Aggiornamento 0.5.4

Chiusura delle sessioni Office/CSV, annullamento PDF, lotti che proseguono dopo un file mancante, riparazione verificata del motore AI e minore memoria per hash/scansione dei file. Cedro incorporato resta 0.26.10.

80 test su ARM64 e 80 su x64 in emulazione; collaudo dei pacchetti e riparazione reale del runtime. **AI ancora sperimentale:** le 30 prove sintetiche mostrano miglioramenti parziali e persistenti errori con istruzioni ingannevoli. Nessun nuovo addestramento o modello 4B. Vedi le note e le risposte integrali nella cartella `corali-desktop/evaluation` del repository.

## Aggiornamento 0.5.3

Cedro **0.26.10** e worker ufficiali ARM64/x64, con verifica SHA-256. Correzione del riconoscimento AI x64 su host ARM. Verifica dei file EXE/DLL del runtime AI prima dell’avvio. Pulizia delle copie con anteprima, cestino e ripristino; nessuna cancellazione automatica. Vulkan è una prova facoltativa con ritorno alla CPU.

Il modello e l’adattatore non sono stati riaddestrati in questo aggiornamento. [Note](corali-desktop/RELEASE-0.5.3.txt), [collaudo dei pacchetti](docs/COLLAUDO-PACCHETTI-0.5.3.json).

## Quale pacchetto scegliere

| PC | Pacchetto da scaricare |
| --- | --- |
| Windows 11, Snapdragon / ARM64 | [CoraliLab-0.5.10-Windows-arm64.zip](https://github.com/LillaByteLab/corali-lab/releases/download/v0.5.10-beta/CoraliLab-0.5.10-Windows-arm64.zip) più [CoraliLab-AI-locale-v1.zip](https://github.com/LillaByteLab/corali-lab/releases/download/modelli-ai-v1/CoraliLab-AI-locale-v1.zip) solo per il suggeritore di operazioni; l'assistente generale si prepara dall'app |
| Intel/AMD, solo app | [CoraliLab-0.5.10-Windows-x64.zip](https://github.com/LillaByteLab/corali-lab/releases/download/v0.5.10-beta/CoraliLab-0.5.10-Windows-x64.zip); modello AI facoltativo e separato |

Estrarre lo ZIP prima di avviare `CoraliLab/CoraliLab.exe`. `Installa.cmd` crea l'installazione per il proprio utente e il collegamento sul Desktop. I dati sono separati dall'installazione; le elaborazioni e il comando Salva copia conservano gli originali.

- [Inizia qui: ARM64 e Intel/AMD](docs/INIZIA-QUI.txt)
- [Installazione e AI locale, entrambe le architetture](docs/ISTRUZIONI-SEMPLICI.txt)
- [Prova guidata](docs/PROVA-GUIDATA.txt)
- [Impronte SHA-256 degli archivi preparati](https://github.com/LillaByteLab/corali-lab/releases/download/v0.5.10-beta/SHA256.txt)

Requisiti: Windows 11 a 64 bit, WebView2 e .NET Framework 4.8.1. Prevedere circa 4 GB liberi per app, modelli e primi dati. Le prove sono state eseguite con 16 GB di RAM; le prestazioni su altri PC devono essere verificate. Questa beta non dispone di firma digitale del produttore.

## Funzioni

- Apertura e modifica dei formati documentali supportati dal motore Office; salvataggio di copie e strumenti per CSV e fogli di calcolo.
- Strumenti PDF: pagine, conversioni, compressione e modifiche supportate; l'efficacia dipende dal documento.
- PDF → Excel: registri mensili riconosciuti, una persona per riga, mesi separati e nessuna cella unita. I totali incoerenti rimangono segnalati. Le tabelle generiche e le scansioni hanno limiti diversi: il profilo registri non interpreta scansioni arbitrarie.
- Trascrizioni locali, revisione del testo con ascolto e segnalazione di ripetizioni sospette.
- Assistente AI per proposte di testo e formule. Conteggi, somme e riduzioni con dati espliciti, anteprima e conferma.

La [guida alle funzioni](corali-desktop/README.md) specifica i limiti dei singoli percorsi.

## AI locale e riservatezza

Il modello Qwen2.5-1.5B-Instruct viene eseguito sul PC attraverso llama.cpp. L'adattatore sperimentale propone una delle operazioni ammesse; non effettua il calcolo numerico e non modifica automaticamente i documenti. La conversazione generale usa il modello base senza adattatore. Le risposte vanno controllate.

Il modello AI è separato e invariato rispetto alla 0.5.2: estrarre [CoraliLab-AI-locale-v1.zip](https://github.com/LillaByteLab/corali-lab/releases/download/modelli-ai-v1/CoraliLab-AI-locale-v1.zip) e mettere `ai-pack` accanto all'eseguibile. Il pulsante **Prepara i componenti AI** prepara il runtime della propria architettura. Internet serve per i download iniziali; prompt e documenti elaborati dall'AI locale non vengono inviati a un servizio AI cloud.

L'addestramento usa dati sintetici. Risultato del suggeritore: **56/60 casi di test**, con varietà limitata delle frasi. Non è una misura di affidabilità generale. I manifest storici del training riportano `releaseAllowed: false` perché il criterio per l'esecuzione autonoma non è stato superato: nella beta l'uso è limitato alle proposte con conferma. [Scheda del modello](docs/MODEL-CARD.txt).

## Cosa è stato verificato

- 98 test Python su ARM64 e 98 su x64 in emulazione Windows ARM.
- Pacchetti confezionati: conversione Cedro PDF → testo, PDF → Excel sintetico, trascrizione WAV → Word/TXT, AI locale, proposta di formula, registrazione locale → MP3 e ripristino dal cestino con hash invariati.
- Interfaccia e formule: anteprima, applicazione, ricalcolo, salvataggio e annullamento.

**Restano da verificare su dispositivo reale:** avvio e prestazioni su un PC Intel/AMD fisico; acquisizione dal microfono; accelerazione GPU (sul Surface è stato verificato il ritorno alla CPU). Provare prima i PDF sintetici inclusi e confrontare i risultati dei propri documenti. I [rapporti storici della 0.5.2](docs/COLLAUDO-COMPLESSIVO.json) sono fotografie del collaudo precedente alla pubblicazione: i loro campi `published` non descrivono lo stato corrente di GitHub.

## Sorgenti, build e licenze

- Applicazione: [corali-desktop](corali-desktop), [istruzioni di build](corali-desktop/BUILD.txt).
- Addestramento: [training-local](training-local), dati sintetici, script, valutazioni e adattatori PEFT.
- Codice originale desktop: [AGPL-3.0-only](LICENSE). Le dipendenze mantengono le proprie licenze. Gli adattatori del modello sono Apache-2.0, come specificato nella scheda del modello.
- [Attribuzioni e sorgenti di terze parti](corali-desktop/THIRD-PARTY-SOURCES.txt), [URL e hash degli archivi upstream](corali-desktop/upstream-sources.json).

Il pacchetto [CoraliLab-0.5.5-sorgenti.zip](https://github.com/LillaByteLab/corali-lab/releases/download/v0.5.10-beta/CoraliLab-0.5.5-sorgenti.zip), disponibile tra gli allegati della release, include anche gli archivi sorgente di PyMuPDF, MuPDF e Pillow. Non sono duplicati nella cronologia Git. FFmpeg non è incluso negli archivi binari: viene scaricato dal produttore al primo utilizzo che lo richiede, con controllo SHA-256.

## Segnalazioni

Nelle Issues indicare versione, architettura del PC, operazione, messaggio di errore e risultato atteso. Usare gli esempi sintetici per riprodurre il problema: **non pubblicare documenti riservati, registri scolastici, nomi di persone o credenziali**.
