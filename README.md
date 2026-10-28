# Coralì Lab

Un laboratorio locale per PDF, documenti, fogli di calcolo, trascrizioni e assistenza AI, con un'interfaccia in italiano. È uno strumento di supporto: la compatibilità non equivale a quella di una suite Office completa.

**Versione 0.5.2 beta — prova controllata.** I sorgenti sono disponibili in questo repository. Il caricamento dei pacchetti nella sezione [Releases](https://github.com/ericabonamici86-max/corali-lab/releases) è in preparazione: finché non compaiono gli allegati, non c'è un download installabile da questa pagina.

## Quale pacchetto scegliere

| PC | Pacchetto previsto |
| --- | --- |
| Windows 11, Intel o AMD | `CoraliLab-0.5.2-Kit-prova-x64.zip`: app, modello AI, sorgenti e guida, circa 1,27 GB |
| Windows 11, Snapdragon / ARM64 | `CoraliLab-0.5.2-Windows-arm64.zip` più `CoraliLab-AI-locale-v1.zip` se si desidera l'AI |
| Intel/AMD, solo app | `CoraliLab-0.5.2-Windows-x64.zip`; modello AI facoltativo e separato |

Estrarre lo ZIP prima di avviare `CoraliLab/CoraliLab.exe`. `Installa.cmd` crea l'installazione per il proprio utente e il collegamento sul Desktop. I dati sono separati dall'installazione; le elaborazioni e il comando Salva copia conservano gli originali.

- [Inizia qui: kit Intel/AMD](docs/INIZIA-QUI.txt)
- [Installazione e AI locale, entrambe le architetture](docs/ISTRUZIONI-SEMPLICI.txt)
- [Prova guidata](docs/PROVA-GUIDATA.txt)
- [Impronte SHA-256 degli archivi preparati](docs/SHA256.txt)

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

Il kit x64 contiene già il modello. Negli altri pacchetti, estrarre `CoraliLab-AI-locale-v1.zip` e mettere `ai-pack` accanto all'eseguibile. Il pulsante **Scarica i componenti AI** prepara il runtime della propria architettura. Internet serve per i download iniziali e per eventuali contenuti web richiesti; prompt e documenti elaborati dall'AI locale non vengono inviati a un servizio AI cloud.

L'addestramento usa dati sintetici. Risultato del suggeritore: **56/60 casi di test**, con varietà limitata delle frasi. Non è una misura di affidabilità generale. I manifest storici del training riportano `releaseAllowed: false` perché il criterio per l'esecuzione autonoma non è stato superato: nella beta l'uso è limitato alle proposte con conferma. [Scheda del modello](docs/MODEL-CARD.txt).

## Cosa è stato verificato

- 50 test Python su ARM64 e 50 su x64 in emulazione Windows ARM.
- Apertura dei backend confezionati, inferenza AI locale, PDF → Excel e avvisi.
- Interfaccia e formule: anteprima, applicazione, ricalcolo, salvataggio e annullamento.

**Restano da verificare su dispositivo reale:** avvio e prestazioni su un PC Intel/AMD fisico; acquisizione dal microfono. Provare prima i PDF sintetici inclusi e confrontare i risultati dei propri documenti. I [rapporti](docs/COLLAUDO-COMPLESSIVO.json) sono fotografie del collaudo precedente alla pubblicazione: i loro campi `published` non descrivono lo stato corrente di GitHub.

## Sorgenti, build e licenze

- Applicazione: [corali-desktop](corali-desktop), [istruzioni di build](corali-desktop/BUILD.txt).
- Addestramento: [training-local](training-local), dati sintetici, script, valutazioni e adattatori PEFT.
- Codice originale desktop: [AGPL-3.0-only](LICENSE). Le dipendenze mantengono le proprie licenze. Gli adattatori del modello sono Apache-2.0, come specificato nella scheda del modello.
- [Attribuzioni e sorgenti di terze parti](corali-desktop/THIRD-PARTY-SOURCES.txt), [URL e hash degli archivi upstream](corali-desktop/upstream-sources.json).

Il pacchetto `CoraliLab-0.5.2-sorgenti.zip`, previsto tra gli allegati della release, include anche gli archivi sorgente di PyMuPDF, MuPDF e Pillow. Non sono duplicati nella cronologia Git. Il motore Cedro resta un componente distinto, attribuito al suo autore; Coralì Lab è un progetto indipendente. FFmpeg non è incluso negli archivi binari: viene scaricato dal produttore al primo utilizzo che lo richiede, con controllo SHA-256.

## Segnalazioni

Nelle Issues indicare versione, architettura del PC, operazione, messaggio di errore e risultato atteso. Usare gli esempi sintetici per riprodurre il problema: **non pubblicare documenti riservati, registri scolastici, nomi di persone o credenziali**.
