# Riscontro delle proposte delle issue 1 e 2 — 0.5.5

| Proposta | Stato verificabile |
| --- | --- |
| Provenienza/licenza Cedro, presentazione indipendente | Componenti dedicati; Cedro 0.26.10, copyright e sorgenti conservati |
| URL pubblici, redirect e DNS | Controlli e regressioni mantenuti dalla 0.5.3 |
| Integrità runtime, riparazione DLL | Riparazione in staging verificato e avvio reale di entrambi i pacchetti |
| Versione UI dal backend | Regression test e pacchetti 0.5.5 |
| CPU/Vulkan | Scelta e fallback esistenti; accelerazione GPU reale non certificata |
| Office/CSV chiusi e memoria rilasciata | 50 aperture/chiusure CSV, gestione modifiche e sessioni |
| Hash e firma Office a blocchi | Regressioni mantenute |
| Importazione/invio HTTP a blocchi | Test multi-MB, range e autenticazione; blocchi da 1 MB |
| Scansione e indice incrementale | Scandir, 5.000 più recenti, aggiornamento alle modifiche, riconciliazione ogni 5 s alla richiesta |
| Cache cataloghi | Cache per motore, configurazione e hash contenuto; opzioni specifiche ricalcolate |
| Trascrizioni multiple | Singola invocazione, audio valido/corrotto/valido sui due pacchetti, risultati parziali conservati |
| Pubblicazione completa dei risultati | Helper comune per testo, CSV, Office, tabelle, voce e tariffe; marker pending e scarto su errore |
| Annullamento PDF | PDF 1.500 pagine cancellato su entrambi i pacchetti; nessuna uscita incompleta |
| File mancante nei lotti | Errore del singolo elemento e continuazione |
| Temporanei orfani | Riconoscimento PID/istante processo, quarantena recuperabile; sconosciuti o in uso lasciati intatti |
| CSV bloccato | Messaggio comprensibile, modifiche conservate e successivo salvataggio riuscito |
| Conservazione facoltativa | Disattivata inizialmente; vecchie importazioni nel cestino, risultati/originali preservati |
| Profilo 4B, preferenze e rilascio RAM | Opzione con revisione/hash/licenza, nessun LoRA 1.5B applicato; prove sui pacchetti |
| Ampliare regressioni AI | 30 varianti + 12 casi diversi, entrambi i modelli; errori residui dichiarati nel review |
| Codice più leggibile | Sorgenti Python del progetto formattati con Black 26.10.1; componenti terzi invariati |

I suggerimenti tecnici hanno un'implementazione e prove circoscritte. Restano limiti reali dell'AI, dei formati complessi e dell'hardware non disponibile: nessuna dichiarazione di collaudo universale. Il confronto futuro con Cedro 0.28.1, citato separatamente dall'autore delle segnalazioni, non costituisce un aggiornamento incorporato in questa release.
