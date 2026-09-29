# Action2Blender — camera virtuale utilizzabile

Questo documento unisce il problema iniziale e la direzione progettuale. Per le funzioni già presenti nella build locale 0.2.0-dev+11 e le prove ancora necessarie, vedere [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md). Le sezioni “Esperienza proposta” e “Verifiche che devono passare” includono funzioni future.

## Problema osservato

Il primo prototipo prendeva una camera già piazzata in Blender. **Azzera** ne fissava la posa iniziale e applicava soltanto il movimento fisico del telefono, moltiplicato per la scala. Prima di Azzera la camera restava ferma per scelta del prototipo. Mancavano comandi per piazzarla, attraversare una scena grande o cambiare focale. Il telefono poteva inoltre mostrare la calibrazione come riuscita prima che Blender l'avesse applicata: la conferma è stata corretta nel codice locale, ma manca ancora la prova sul dispositivo.

Una prova isolata in Blender sposta la camera di circa un'unità quando arriva uno spostamento del telefono di un metro, anche se la camera ha un'animazione assegnata. La causa del blocco visto nella sessione reale richiede una verifica con telefono connesso e stato della camera corrente.

## Stato dello sviluppo locale

L'app locale 0.2.0-dev+11 include il comando **Nuova camera** dalla vista 3D o dall'oggetto selezionato, due joystick per spostamento e rotazione, due pulsanti per alzare o abbassare la camera e una stabilizzazione live regolabile della posa fisica ARCore. Il movimento virtuale si combina con la posa filtrata e viene conservato nei campioni della take. Durante la sessione ARCore attiva, lo schermo resta acceso anche senza tocchi. L'add-on locale 0.2.3 raccoglie le nuove camere nella collezione **Action2Blender**, applica una seconda stabilizzazione dopo Stop e riconosce i reinvii di take già salvate tramite ID. Le prove automatiche e isolate in Blender sono riuscite, mentre la ripresa completa sul telefono richiede ancora verifica. Dolly e focale restano da realizzare.

## Esperienza proposta

### 1. Piazzare la camera

- In Blender si sceglie una camera esistente oppure se ne crea una nuova. Un oggetto della scena può diventare il **soggetto** della ripresa.
- **Inquadra soggetto** mette la camera a una distanza calcolata dai limiti reali dell'oggetto, dal rapporto 16:9 e dal campo visivo dell'obiettivo, puntata verso il suo centro. È un punto di partenza modificabile, non un vincolo permanente.
- **Orbita** mantiene il soggetto al centro mentre l'operatore cambia angolo e distanza. **Libera** permette di lasciare il soggetto e navigare nel mondo. Il cambio di modalità conserva la posa corrente.
- Il pulsante **Azzera** sincronizza telefono e camera senza spostare bruscamente l'inquadratura. Se premuto di nuovo, usa la posa virtuale corrente come nuova base: non torna alla posizione iniziale. Il telefono conferma “Pronta” solo dopo la risposta di Blender.

### 2. Muoverla

- Il movimento fisico del telefono controlla posizione e orientamento su sei assi nella zona in cui si può camminare. La **scala fisica** moltiplica solo lo spostamento, non la rotazione.
- Controlli virtuali sul video permettono di **avanzare/arretrare**, **spostarsi di lato**, **salire/scendere** e **ruotare/inclinare** la camera anche con il telefono fermo su un supporto. La velocità virtuale è separata dalla scala fisica. Quando si rilascia il controllo, la camera si ferma.
- Il controllo di movimento usa la direzione corrente della camera: “avanti” procede dove la camera guarda. Un comando esplicito **Torna alla posa iniziale** è disponibile fuori dalla registrazione; gli offset non spariscono durante una take.
- Rotazione del display, perdita del tracking e ripresa della sessione non devono introdurre salti nella camera.

### 3. Focale e distanza

- **Zoom ottico / Focale** cambia i millimetri dell'obiettivo: il campo visivo si stringe o si allarga, ma la prospettiva non cambia.
- **Dolly** sposta la camera verso o lontano dal soggetto: cambia la prospettiva e la parallasse. I due controlli devono essere distinti e avere valori visibili.
- Durante una take si salvano posizione, rotazione e focale. Riproducendo la take in Blender, l'inquadratura deve coincidere con quella vista sul telefono. Ogni take conserva anche la propria animazione della focale.

### 4. Interfaccia sul telefono

- La vista 16:9 rimane intera sullo schermo orizzontale. Eventuali margini dello schermo ospitano i controlli, senza tagliare l'immagine della ripresa.
- Stati persistenti e leggibili: **Blender connesso**, **Tracking valido**, **Camera pronta**, **Registrazione**, **Take salvata**. Gli errori di Blender non vengono sostituiti subito dal normale messaggio di tracking.
- Modalità **Piazza**: soggetto, orbita, dolly, movimento e rotazione virtuali, focale.
- Modalità **Gira**: anteprima pulita con Rec/Stop, Azzera, scala, dolly e focale accessibili; i comandi aggiuntivi si possono nascondere.
- Sul supporto sono utilizzabili gli stessi controlli senza dover muovere fisicamente il telefono.

## Modello tecnico

La posa finale deriva da quattro livelli distinti: camera iniziale scelta in Blender, navigazione virtuale accumulata, delta fisico ARCore dall'ultimo Azzera e impostazioni dell'obiettivo. Per il movimento fisico si misura il delta nelle coordinate locali del telefono al momento di Azzera e lo si ruota secondo la camera virtuale iniziale. La navigazione virtuale si accumula nello spazio 3D usando l'orientamento corrente della camera. Questo evita che cambiare la scala fisica alteri un movimento virtuale già fatto. Il soggetto è un riferimento opzionale per piazzamento e orbita; la camera rimane un normale oggetto Blender, modificabile anche dopo la take.

I campioni della take devono includere lo stato completo necessario a ricostruire la ripresa dopo una disconnessione: posa fisica, navigazione virtuale, focale e tempi. Il salvataggio crea una Action per la posa dell'oggetto camera e una distinta Action per la focale nei dati della camera. L'elenco delle take conserva entrambe le associazioni, così una selezione non sovrascrive la precedente. Se i dati dell'obiettivo sono condivisi con altre camere, l'add-on deve renderli indipendenti prima di animarli oppure chiedere esplicitamente di farlo.

## Verifiche che devono passare

1. Con soggetto selezionato, **Inquadra soggetto** lo porta interamente nell'anteprima 16:9.
2. Dopo **Azzera**, camminare lateralmente e ruotare il telefono produce movimento coerente della camera in Blender e sul telefono.
3. Con telefono immobile sul supporto, i controlli virtuali attraversano una stanza 3D e cambiano direzione; la velocità non dipende dalla scala fisica.
4. Dolly e focale producono inquadrature visibilmente diverse, con valori numerici mostrati.
5. Rec/Stop salva una take che riproduce posizione, rotazione e focale; una seconda take non cancella la prima.
6. Camera con parent o vincoli incompatibili, tracking assente e connessione persa generano messaggi espliciti prima di mostrare “Pronta”.
7. Ruotare il telefono e recuperare il tracking non provoca uno scatto della camera durante una take.

## Ordine di realizzazione

1. Rendere affidabili conferma di Azzera, stato della camera e diagnosi del collegamento reale.
2. Aggiungere piazzamento su soggetto e navigazione virtuale, con anteprima coerente.
3. Aggiungere focale e dolly distinti; registrare entrambi nella take.
4. Rifinire stabilizzazione, velocità e comandi sul video con una prova di ripresa completa.

I joystick di spostamento e rotazione sono ora presenti nella build locale; velocità regolabile, dolly e zoom restano scelte aperte.
