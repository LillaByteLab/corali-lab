# Addestramento del suggeritore di operazioni

Questa cartella contiene dati sintetici, script, valutazioni e adattatori PEFT della beta 0.5.2. Vedere [MODEL-CARD](../docs/MODEL-CARD.txt) per modello base, revisione, licenza degli adattatori e limiti.

Il checkpoint finale è `round3b/run/epoch-2`. L'addestramento prosegue da round2 a round3 e round3b. I dati reali di collaudo non sono inclusi.

`releaseAllowed: false` nei manifest storici indica che il criterio per affidare operazioni autonome al suggeritore non è stato superato. Questi risultati sono conservati senza alterazioni. L'integrazione beta consente soltanto una proposta da confermare: l'utente sceglie l'operazione, controlla gli input e l'anteprima. I calcoli sono eseguiti da funzioni deterministiche.

Le dipendenze del training sono in `requirements-tested-arm64.txt`; non servono per usare l'app. Il modello base e i runtime non sono inclusi nel repository. Gli adattatori PEFT richiedono la revisione del modello base indicata nella scheda; non vanno combinati con pesi differenti.
