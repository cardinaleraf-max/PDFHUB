# Verifiche di PDFHub per Windows

Il catalogo comprende 37 strumenti. La suite ha eseguito 44 casi attraverso ciascuno dei tre percorsi seguenti.

| Percorso | Risultati salvati e riaperti | Dipendenza assente gestita |
| --- | ---: | ---: |
| Studio, selezione delle opzioni, trascinamento, conversione e download su disco | 41 | 3 |
| Controlli WPF, settori della ruota compatibili, editor e salvataggio su disco | 41 | 3 |
| Processo di conversione richiamato dall’editor Windows | 41 | 3 |

La suite nativa seleziona la destinazione di prova automaticamente. Una prova distinta avvia il collegamento Windows con un PDF il cui nome contiene spazi, seleziona **Esporta → Estrai testo**, conferma il pulsante **Salva** nella finestra di Windows e controlla il contenuto del TXT su disco. Sono stati verificati anche il ritorno alla ruota alla chiusura dell’editor e il caricamento dell’interfaccia nativa di riserva al doppio clic.

Le varianti coprono rotazioni di 90°, 180° e 270°, intervallo di pagine e ZIP per pagina, compressione normale ed elevata, esportazione JPG e PNG, lettura con password, riassunto estrattivo e modalità con modello. Il controllo dei risultati include numero e ordine delle pagine, valori dei campi, testo inserito o rimosso, riconoscimento OCR, dimensioni, immagini, archivi e struttura dei file Office.

Altri **19 test** coprono intervalli fuori limite, rotazioni e margini non validi, posizione della scritta, campi assenti, password errate, file mancanti, recupero di un PDF con indice danneggiato, importazione BMP/TIFF e integrazioni con dispositivi e servizi simulati.

## Limiti delle prove

- **Acquisizione fisica.** Windows esponeva zero scanner WIA. È stato verificato il messaggio all’utente. Un test distinto simula l’immagine restituita dal driver e verifica la conversione in PDF.
- **Modelli linguistici.** La traduzione e la modalità Ollama del riassunto hanno segnalato l’assenza del servizio locale. Un server di prova ha verificato richiesta, selezione della lingua e creazione del PDF dalla risposta. La qualità linguistica richiede una prova con un modello reale.
- **Office.** La sessione di test ha impedito l’avvio di Office tramite COM. Le prove sui formati Word, Excel e PowerPoint in ingresso hanno verificato il motore di riserva. L’impaginazione dell’esportazione nativa di Office richiede una sessione Windows che consenta l’automazione.
- **PDF/A.** Sono stati verificati riapertura, pagine raster, dichiarazione XMP PDF/A-2b e profilo colore. La conformità integrale richiede una validazione indipendente, ad esempio con veraPDF.

## Ripetere le prove

Per i test servono anche `pytest` e `pypdf`. La prova Studio usa Chrome con un profilo temporaneo e Node.js con WebSocket integrato. Le prove creano documenti sintetici locali.

```powershell
python -B tests/check_suite.py
python -B tests/check_suite.py --browser
python -B tests/check_suite.py --native
python -B -m pytest -p no:cacheprovider -q tests/test_edges.py
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File tests/shell.ps1
```
