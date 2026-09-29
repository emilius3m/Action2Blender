# Action2Blender

Usa un telefono Android come camera virtuale per Blender: muovi l'inquadratura a mano libera o con i comandi sullo schermo, guarda l'anteprima sul telefono e registra ogni ripresa come take separata.

> **Versione attuale: 0.2.0 beta 1.** Scarica l'APK e lo ZIP dell'add-on dalla [pagina Releases](https://github.com/emilius3m/Action2Blender/releases). Usa sempre app e add-on della **stessa release**: la 0.2 non si collega all'add-on 0.1 e viceversa.

## Occorrente

- Blender 5.2 (provato con 5.2.1) su un PC.
- Un telefono Android compatibile con ARCore ([elenco dei dispositivi](https://developers.google.com/ar/devices)). Finora è stato provato un Samsung Galaxy S25 Ultra.
- PC e telefono sulla stessa rete locale, con la connessione consentita dal firewall del PC sulla rete privata.

## Installazione

1. Scarica dalla pagina Releases `Action2Blender-addon-0.2.0.zip` e `Action2Blender-0.2.0-beta.1.apk`.
2. In Blender apri **Edit → Preferences → Add-ons**, dal menu **⌄** in alto a destra scegli **Install from Disk**, seleziona lo ZIP e abilita **Action2Blender**. Il pannello si trova in **Vista 3D → barra laterale (N) → Action2Blender**. Se stai aggiornando da una versione precedente, salva la scena e riavvia Blender.
3. Installa l'APK sul telefono, apri **Action2Blender** e concedi l'accesso alla fotocamera. Android potrebbe chiedere di installare o aggiornare i servizi Google Play per AR.

Se Android rifiuta l'aggiornamento perché l'app installata ha una firma diversa, **non disinstallarla finché ci sono take non ancora confermate da Blender**: sono conservate solo nell'area privata dell'app.

L'app è in italiano sui telefoni in italiano e in inglese negli altri casi; il pannello di Blender è in inglese. Questa guida usa le etichette italiane dell'app.

## Collega il telefono

1. Apri la scena in Blender. Per usare una camera esistente, sceglila nel campo **Camera** del pannello Action2Blender. La camera non deve avere un oggetto padre né vincoli attivi. Puoi anche crearne una nuova dall'app dopo il collegamento.
2. L'opzione **16:9 framing** è attiva per impostazione predefinita e porta la risoluzione della scena a 16:9 all'avvio della connessione; disattivala se vuoi mantenere il formato della scena. Premi **Start phone connection**: il pannello mostra un QR, l'IP del PC, la porta e un codice di abbinamento temporaneo.
3. Nell'app premi **Scansiona QR di Blender**; il lettore è incluso nell'app. In alternativa inserisci IP, porta e codice e premi **Connetti**. Se il PC ha più connessioni di rete, controlla che l'IP nel pannello sia quello raggiungibile dal telefono.
4. Attendi **Tracciamento attivo**. Per partire dalla camera scelta premi **Azzera**: la sua inquadratura attuale diventa il punto di partenza. Oppure, nella scheda **Nuova camera**, scegli **Dalla vista 3D di Blender** o **Inquadra oggetto selezionato**. Aspetta **Camera pronta** prima di registrare.

## Muovi e registra la camera

- **Movimento fisico.** Muovi e ruota il telefono: la camera segue. La verticale del telefono coincide con quella di Blender, quindi una panoramica mantiene l'orizzonte dritto e camminare sposta la camera in orizzontale anche se è inclinata. **Scala** moltiplica solo gli spostamenti (1× = un metro reale per un'unità di Blender), non le rotazioni.
- **Comandi sullo schermo.** Dopo **Camera pronta** compaiono **Sposta** (avanti, indietro e di lato, sempre in orizzontale), **Ruota** (panoramica e inclinazione) e i pulsanti per salire e scendere. Si sommano al movimento fisico, funzionano anche con il telefono fermo su un supporto e vengono registrati nella take.
- **Anteprima.** Il telefono mostra la vista della camera generata da Blender. In orizzontale occupa lo schermo, con i comandi sopra il video; su tablet i comandi stanno a lato.
- **Registrazione.** Premi **Rec** per iniziare e **Stop** per terminare. Durante il tracciamento lo schermo resta acceso. La take compare in **Recorded takes** nel pannello di Blender come Action separata, partendo dal fotogramma corrente: le take precedenti non vengono sovrascritte. Selezionane una nel pannello e salva il file `.blend`.
- **Perdita del tracciamento.** Se ARCore perde il tracciamento o l'app va in pausa, la take si sospende. Quando il tracciamento torna, premi **Riprendi senza salto**.
- **Rete.** Dopo **Stop** la take resta sul telefono finché Blender non ne conferma il salvataggio. Se il Wi-Fi si interrompe, premi di nuovo **Connetti** (o scansiona il QR): la take viene ritrasmessa. Potrebbe servire premere di nuovo **Azzera**.

### Stabilizzazione

Ci sono due filtri separati; se li attivi entrambi, la take viene levigata due volte.

- **Stabilizzazione live** (nell'app, 25% all'inizio): filtra la posa del telefono prima dell'anteprima e della registrazione. Valori alti rendono la risposta ai movimenti voluti un po' più lenta. Si regola solo fuori da Rec; 0% la disattiva.
- **Stabilize after Stop** (in Blender, attivo con **Strength** 0,5): dopo Stop crea una seconda Action stabilizzata accanto all'originale, che non viene mai modificata. **Stabilize selected take** crea una nuova versione stabilizzata di una take già registrata.

## Se qualcosa non funziona

| Problema | Controllo rapido |
| --- | --- |
| Il telefono non si collega | PC e telefono sulla stessa rete, IP corretto nel pannello, connessione consentita dal firewall sulla rete privata. |
| "Aggiorna l'app Action2Blender sul telefono" o "Aggiorna o ricarica l'add-on Action2Blender" | App e add-on provengono da release diverse: installa entrambi dalla stessa release e riavvia Blender. |
| La camera non si muove o Rec è disabilitato | Attendi il tracciamento e **Camera pronta**. Con una camera esistente, sceglila nel pannello e premi **Azzera**. Niente oggetto padre né vincoli attivi sulla camera. |
| La take selezionata non si vede in riproduzione | Se nella Timeline ci sono marker collegati a camere, sono loro a scegliere la camera attiva durante la riproduzione. |
| L'anteprima non arriva | Tieni aperta una Vista 3D in Blender e controlla il firewall: l'anteprima usa una seconda porta locale oltre alla porta di collegamento. |
| I comandi non rispondono dopo aver aperto un altro file | Premi **Stop phone connection** e poi **Start phone connection**, quindi ricollega il telefono. |
| Dopo Stop la take non compare | Controlla il messaggio nell'app e aspetta la conferma di Blender. Non disinstallare l'app finché una take è in attesa. |

## Limiti noti di questa beta

- Anteprima, joystick, creazione della camera dall'app e nuova mappatura della verticale sono stati verificati con prove automatiche e in Blender; la prova completa sul telefono è ancora in corso. Altri telefoni Android non sono ancora stati provati.
- Aprire un altro file `.blend` con la connessione attiva ferma l'elaborazione dei comandi finché non riavvii la connessione dal pannello.
- Una take in attesa sul telefono non può più essere salvata se nel frattempo Blender viene riavviato o la connessione viene riavviata dal pannello.
- Il telefono non si ricollega da solo dopo un'interruzione della rete.
- Take molto lunghe (oltre circa 15 minuti) possono superare il limite di dimensione del messaggio.
- Dopo aver ruotato la camera con il joystick, gli spostamenti fisici seguono ancora la direzione del momento di **Azzera**.
- Le take animano posizione e rotazione, non la focale. Parent e vincoli della camera non sono supportati.

## Sviluppo

Il codice è diviso in tre parti: interfaccia Flutter (`lib/`), tracciamento ARCore e collegamento in Kotlin (`android/app/src/main/kotlin/`), add-on Blender in Python (`addon/action2blender/`). Per le verifiche, la compilazione e lo stato dello sviluppo vedi [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md); le scelte di progetto della camera sono in [CAMERA_DESIGN.md](CAMERA_DESIGN.md).

Il codice originale è distribuito con [licenza MIT](LICENSE). ARCore e le altre dipendenze mantengono le rispettive licenze; vedi [THIRD_PARTY.md](THIRD_PARTY.md).
