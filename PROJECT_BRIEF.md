# Action2Blender — brief della beta

## Decisioni confermate

- App Android e add-on per Blender, progettati fin dall'inizio per altri utenti Android oltre al Samsung Galaxy S25 Ultra usato per le prime prove.
- Tracciamento della posizione e della rotazione del telefono per muovere una camera già presente nella scena di Blender.
- Comando **Azzera**: il movimento del telefono diventa relativo alla posizione iniziale della camera selezionata.
- Uso a mano libera o con il telefono montato su un supporto.
- Controllo della scala dello spostamento fisico rispetto allo spostamento nella scena.
- Registrazione avviata con **Rec** e conclusa con **Stop**; ogni ripresa resta disponibile come take separata.
- Le take si selezionano sulla stessa camera dal pannello dell'add-on, senza sovrascrivere le riprese precedenti.
- Se il telefono perde il tracciamento, la registrazione entra automaticamente in pausa e mostra un avviso. Il recupero non deve produrre uno scatto nella camera.
- Priorità della prima beta: movimento e registrazione affidabili. La scena si guarda sul monitor di Blender; sul telefono compaiono comandi e stato del tracciamento. Lo streaming del viewport al telefono è previsto per una versione successiva.
- Prima distribuzione tramite APK scaricabile e pacchetto dell'add-on. Anche il codice sorgente sarà pubblico su GitHub.
- Nome del progetto: **Action2Blender**. Licenza del codice originale: **MIT**.

## Impostazione tecnica proposta

- Usare ARCore per stimare il movimento del telefono e verificare la compatibilita del dispositivo all'avvio. Il Galaxy S25 Ultra compare nell'elenco dei dispositivi supportati da Google: https://developers.google.com/ar/devices
- Interfaccia Android in **Flutter**, con acquisizione ARCore e comunicazione locale in **Kotlin**; add-on Blender in **Python**.
- Collegare telefono e add-on sulla rete locale con un abbinamento semplice, per esempio un codice QR.
- Inviare la posa in tempo reale per muovere la camera in Blender. Durante la registrazione, conservare anche i campioni sul telefono e inviare la take completa dopo **Stop**, così una breve perdita di rete non crea buchi nei dati registrati.
- Applicare la scala alla traslazione; mantenere la rotazione del telefono diretta. Conservare la traiettoria originale e rendere regolabile la stabilizzazione della take.
- Usare Blender 5.2 come primo ambiente di verifica, mantenendo separato il protocollo di comunicazione dall'integrazione con Blender.

## Comportamento fissato nel primo prototipo

- Le take sono Action Blender separate e selezionabili sulla stessa camera.
- La take parte dal fotogramma corrente e viene campionata al frame rate della scena al momento del salvataggio.
- Dopo una perdita del tracciamento, **Riprendi** ancora la nuova posa del telefono all'ultima posa virtuale valida, evitando salti.
- La beta iniziale usa IP e codice di abbinamento inseriti a mano; il QR è previsto in seguito.

## Da completare prima della beta pubblica

- Provare l'acquisizione ARCore, i permessi e la connessione su un telefono Android reale.
- Verificare l'andamento delle take in scene Blender reali e aggiungere gli interventi di stabilizzazione necessari.
- Firmare l'APK di release con una chiave dedicata e definire come custodirla.

## Nota sulla distribuzione

La prima beta sarà distribuita tramite GitHub. La piattaforma ufficiale Blender Extensions richiede GPL-3.0-or-later per gli add-on: un'eventuale pubblicazione anche lì richiederà una valutazione separata della licenza e del pacchetto.

## Criteri per una prima prova riuscita

1. Il telefono si abbina a Blender sulla rete locale.
2. **Azzera** mantiene l'inquadratura iniziale e il movimento fisico controlla posizione e rotazione della camera.
3. La scala cambia lo spostamento senza alterare la rotazione.
4. **Rec/Stop** crea una take riproducibile in Blender senza cancellare le take precedenti.
5. Una breve interruzione della rete non corrompe la take conservata sul telefono.
6. La perdita del tracciamento mette in pausa la registrazione e viene segnalata chiaramente sul telefono.
