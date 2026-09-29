# Action2Blender — progetto tecnico delle prossime riprese

Stato: **proposta da rivedere, non implementata**. Base analizzata: app e add-on 0.2.0, protocollo `camera_control: 3`.

## Obiettivo e confini

Durante **Rec**, Blender riproduce l'animazione della scena e il telefono guida una camera dedicata alla take. L'anteprima sul telefono mostra il frame corrente. La take conserva movimento, focale, fuoco, diaframma e i dati necessari a ricostruire la camera anche se la conferma di salvataggio o lo stato temporaneo di Blender vanno perduti. Una caduta della rete non cancella la ripresa già acquisita sul telefono.

Una take può ricostruire **la camera**, non gli oggetti, le texture o l'animazione della scena: per rivedere lo stesso mondo serve conservare il file `.blend` e i suoi asset. Se la scena originale non è disponibile, il recupero crea la camera nel progetto aperto e segnala che lo sfondo può essere diverso.

### Punto di partenza nel codice 0.2.0

| Parte | Comportamento attuale | Modifica richiesta |
| --- | --- | --- |
| `addon/action2blender/blender.py` | `record_start` conserva posa e frame in `_record_state`; la timeline non parte. `_save_take` usa quello stato volatile e crea solo Action per l'oggetto camera. | Sessione di ripresa con ID e frame sync; camera della take; salvataggio da snapshot anche dopo riavvio. |
| `android/.../TakeRecorder.kt` e `MainActivity.kt` | I campioni restano in memoria; `pending_<id>.json` appare solo dopo Stop. | Diario persistente fin dall'avvio, chiusura atomica e ripresa di file parziali. |
| `android/.../BridgeClient.kt` e `addon/action2blender/transport.py` | Una connessione manuale; nessun ping, trasferimento della take in una riga JSON con limite di 8 MiB. | Stato di sessione, ping/pong, riconnessione e blocchi confermati. |
| `lib/main.dart` | Rec/Stop e anteprima, senza countdown né controlli dell'obiettivo. | Stati espliciti, timer/frame visibili, pinch e slider per fuoco e diaframma. |

Queste sono modifiche congiunte a telefono, protocollo e add-on. App e add-on di versioni incompatibili devono rifiutare la connessione con un messaggio chiaro; la nuova coppia dichiara una versione di capacità distinta dal vecchio `camera_control: 3`.

## Esperienza proposta

1. In Blender si seleziona la camera di partenza e si porta la timeline al frame desiderato. La camera può essere già animata: la sua Action resta intatta.
2. Sul telefono si sceglie un conto alla rovescia **Off / 3 s / 5 s** (Off predefinito, scelta ricordata). **Rec** chiede a Blender di preparare una take e blocca il frame iniziale. Il conto inizia solo dopo la risposta **Pronto** di Blender. Durante il conto la timeline è ferma.
3. Alla fine del conto Blender crea e attiva una **camera della take** nella collezione Action2Blender, poi avvia la timeline. Il telefono registra dal messaggio di avvio confermato. Mostra tempo e frame; il movimento fisico e i controlli virtuali continuano a funzionare.
4. Il gesto a due dita sull'area libera dell'anteprima cambia la focale. Una fascia compatta mostra **mm**, **distanza di fuoco** e **f/**; fuoco e diaframma hanno slider accessibili anche durante Rec. Un dito non modifica la focale. I controlli non coprono il centro dell'inquadratura in orizzontale.
5. **Stop** ferma la riproduzione avviata dall'add-on, chiude il diario della take sul telefono e invia la take a Blender. Se la timeline arriva all'ultimo frame dell'intervallo di anteprima attivo, oppure al `frame_end` della scena quando non c'è un intervallo di anteprima, la ripresa si ferma automaticamente, senza ripartire dall'inizio. Per una take più lunga si estende prima l'intervallo.
6. Se cade la rete o si perde il tracking, Rec entra in **Pausa**, il materiale già acquisito resta sul telefono e la timeline si ferma. La connessione di rete torna automaticamente quando possibile; **Riprendi** richiede un tocco e crea un riferimento nuovo, senza salto della camera. Dopo un riavvio dell'app, una ripresa interrotta compare come **Take da recuperare** con durata e data, da inviare o eliminare esplicitamente.

## Timeline: Blender è il riferimento dei frame

L'add-on prepara la take sul thread principale di Blender, con `take_id`, camera sorgente, `start_frame`, `frame_end`, FPS numeratore/denominatore e stato della riproduzione precedente. Se non esiste una finestra/schermata adatta ad avviare la timeline, risponde con un errore prima di attivare Rec sul telefono. Se Blender stava già riproducendo, la proposta è **fermarlo e ripartire dal frame scelto** per avere un inizio ripetibile.

Il timer dell'add-on avvia `bpy.ops.screen.animation_play(sync=True)` solo dopo il conto; controlla `Screen.is_animation_playing`, `scene.frame_current` e gli eventi di fine riproduzione. **Stop** ferma solo la riproduzione che appartiene alla take, senza riportare la scena al frame iniziale. Il frame finale viene catturato prima di salvare le Action. I messaggi di avanzamento della timeline includono `take_id`, frame e tempo monotono di Blender. Il telefono conserva questi riferimenti accanto ai campioni di posa. La conversione dei tempi del telefono verso il tempo di Blender usa scambi ping/pong con stima dell'offset e dei tempi di andata/ritorno; per ogni frame della take si interpola la posa corrispondente. Il tempo della take non deriva semplicemente dal numero di campioni, perché Blender può saltare frame quando la scena è pesante.

### Comandi e stati di una ripresa

| Passaggio | Telefono | Blender | Risposta attesa |
| --- | --- | --- | --- |
| Preparazione | `record_prepare` con `take_id` | Verifica camera prospettica, frame, finestra e capacità di playback; restituisce lo snapshot | `record_ready` con camera, frame, FPS e dati obiettivo |
| Conteggio | Stato `COUNTDOWN`, diario già creato | Timeline ferma; camera sorgente intatta | Annullamento possibile senza take vuota |
| Avvio | `record_go` con lo stesso ID | Crea camera della take, attiva playback e marcatore iniziale | `record_started`; solo ora UI in `RECORDING` |
| Durante Rec | Campioni nel diario e pose live, comandi ottici | Aggiorna camera e anteprima, invia `frame_tick` e conferme dell'obiettivo | Frame e latenza mostrati sul telefono |
| Stop/fine timeline | `record_stop` oppure evento di fine | Ferma playback, congela il frame finale | `record_stopped`; telefono finalizza e invia i blocchi |
| Salvataggio | Ritrasmette blocchi mancanti | Verifica hash/ID, crea Action e voce della take | `take_saved` con lo stesso ID; solo allora si elimina il file locale |

Stati del telefono: `READY → COUNTDOWN → STARTING → RECORDING ↔ PAUSED → FINALIZING → PENDING_ACK → SAVED`. Dopo crash o perdita definitiva della sessione, `RECORDING` e `PAUSED` diventano `RECOVERABLE` al riavvio. Tutte le transizioni hanno `take_id` e numero di sequenza; una risposta ritardata di una take precedente non altera quella corrente. Il telefono non registra campioni prima di `record_started`; se l'avvio fallisce, il diario di preparazione si chiude senza diventare una take. `record_prepare`, `record_go`, `record_stop` e `take_saved` sono idempotenti per ID.

Il traguardo da misurare su LAN è **scarto massimo di un frame** fra la posa animata salvata e il frame visto nell'anteprima in una scena di prova a 24/30 FPS. Non si promette questo scarto per scene che non riproducono in tempo reale: l'interfaccia deve mostrare frame persi e latenza. La scelta `sync=True` permette a Blender di saltare frame per mantenere il tempo; la take registra i frame effettivamente attraversati. Le API Blender 5.2 espongono [riproduzione e arresto](https://docs.blender.org/api/5.2/bpy.ops.screen.html), [stato della schermata](https://docs.blender.org/api/5.2/bpy.types.Screen.html) e [handler di avanzamento/fine](https://docs.blender.org/api/5.2/bpy.app.handlers.html). I callback non devono fare scritture pesanti o modificare la scena mentre la viewport la legge: accodano solo i riferimenti temporali, che il timer dell'add-on elabora sul thread principale.

Se l'utente ferma manualmente la timeline in Blender, l'add-on invia `record_stopped` e il telefono finalizza la take al frame raggiunto. Durante Rec, cambio di scena, FPS o camera attiva non viene accettato senza chiudere prima la take: il pannello lo segnala e il diario conserva lo snapshot iniziale. Se l'app va in background o ARCore perde il tracking, il diario viene sincronizzato e Rec va in pausa; la ripresa non si considera salvata finché il telefono non ha un file recuperabile.

## Camera e obiettivo per ogni take

All'avvio l'add-on duplica la camera scelta e i suoi dati obiettivo in una nuova camera **A2B Take Camera**, senza Action dell'oggetto, parent o vincoli. Conserva la posa valutata al frame iniziale e assegna UUID permanenti alla take e alla camera. La camera originale resta disponibile e non perde animazioni o impostazioni. La copia impedisce alla timeline di sovrascrivere la posa impartita dal telefono. Quando si seleziona una take, Blender riattiva la sua camera e le sue due Action, una per posizione/rotazione e una per l'obiettivo.

La focale si misura in **mm** e modifica `Camera.lens`; il pinch usa un rapporto moltiplicativo (`focale_iniziale × scala_del_gesto`). L'intervallo suggerito per il gesto è 12–200 mm, configurabile; un valore iniziale esterno all'intervallo non viene cambiato all'avvio di Rec. Fuoco e diaframma modificano `Camera.dof.focus_distance` e `Camera.dof.aperture_fstop`, con DOF abilitata nella copia. I valori iniziali vengono letti dalla camera sorgente. Se la sorgente usa un oggetto di messa a fuoco, la copia prende la distanza valutata al frame iniziale e svincola quell'oggetto, così il controllo manuale funziona. Le unità della distanza sono esplicitate nell'app in base alla scala della scena; nel file della take si usano unità Blender. Le camere ortografiche o panoramiche non offrono lo stesso zoom in millimetri: per questa fase si richiede una camera prospettica e si mostra un errore chiaro prima di Rec.

Ogni cambiamento dell'obiettivo porta un numero di sequenza e un tempo della take; il telefono aggiorna immediatamente il valore mostrato e Blender conferma quello applicato. Le modifiche sono accorpate a circa 20 aggiornamenti al secondo per non saturare la connessione, ma il diario locale conserva i valori necessari all'animazione. In Blender i valori vengono campionati ai frame della timeline e inseriti nella Action dei dati camera (`lens`, `dof.focus_distance`, `dof.aperture_fstop`). L'anteprima corrente deve mostrare subito **l'inquadratura** della nuova focale; la resa visiva della profondità di campo dipende dalla modalità di anteprima della scena e va verificata separatamente prima di prometterla nell'app. Le proprietà dell'obiettivo e della DOF sono nell'[API Camera di Blender 5.2](https://docs.blender.org/api/5.2/bpy.types.Camera.html) e nell'[API DOF](https://docs.blender.org/api/5.2/bpy.types.CameraDOFSettings.html).

## Formato della take autosufficiente

Una nuova versione del protocollo e del formato locale evita di interpretare un file 0.2 con regole nuove. Il formato finale resta leggibile come JSON; durante Rec si usa un diario append-only JSON Lines. Testata proposta:

```json
{
  "format": 2,
  "id": "uuid",
  "scene": {"name": "Scene", "uuid": "uuid", "take_start_frame": 42, "playback_end_frame": 250,
            "fps": 24, "fps_base": 1, "resolution": [1920, 1080], "pixel_aspect": [1, 1]},
  "camera": {"source_uuid": "uuid", "take_uuid": "uuid", "name": "A2B Take Camera",
             "position": [0, 0, 5], "rotation_xyzw": [0, 0, 0, 1],
             "lens_mm": 50, "focus_distance_bu": 10, "fstop": 2.8,
             "sensor_fit": "AUTO", "sensor_width_mm": 36, "sensor_height_mm": 24},
  "tracking": {"phone_anchor": {"p": [0, 0, 0], "q": [0, 0, 0, 1]}, "scale": 1},
  "events": [],
  "frame_markers": []
}
```

Gli eventi conservano campioni di posa, navigazione virtuale, rebase, cambi di obiettivo, pause/riprese e tempi monotoni relativi. Un evento `complete` chiude il diario. Nessuna dipendenza da `_record_state` volatile è necessaria per importare la take: Blender usa snapshot iniziale, anchor e scala nel file. Se la camera con UUID esiste la riusa; se è stata rinominata la ritrova comunque; se manca crea una camera di recupero nella collezione Action2Blender senza sostituire in silenzio un'altra camera. L'ID della take rende il reinvio idempotente, anche dopo riavvio e salvataggio del `.blend`. L'app elimina il file locale solo dopo `take_saved` con lo stesso ID.

## Resilienza del collegamento e del salvataggio

- **Ping/pong:** ogni 2 s, risposta immediata dal server di rete; dopo circa 6 s senza risposta la connessione è persa. Ping porta ID e tempi monotoni per misurare latenza e offset dei due orologi. Non aspetta il timer principale di Blender per rispondere, ma i comandi che modificano la scena continuano a passare dal thread principale.
- **Riconnessione:** tentativi con attesa crescente 1/2/4/8/15 s, senza aprire più socket contemporaneamente. Il server include un `session_id` nel saluto: il telefono riusa il codice temporaneo solo nella sessione dell'app e dello stesso server Blender. Dopo riavvio dell'app o del server, si scansiona un nuovo QR; le take locali rimangono disponibili e vengono inviate dopo il nuovo abbinamento. Non si salva il codice temporaneo in chiaro nelle preferenze.
- **Diario progressivo:** un solo writer in background aggiunge campioni a un file privato `recording_<id>.jsonl`, sincronizzando su memoria stabile almeno ogni secondo e immediatamente per start, pausa, resume e Stop. Una chiusura improvvisa può perdere al massimo l'ultimo intervallo non sincronizzato; il resto viene recuperato. Si scarta solo un'ultima riga troncata, mai l'intera take. Le scritture non avvengono nel callback ARCore o nel thread UI.
- **Finalizzazione:** Stop produce un file finale `pending_<id>.json` mediante scrittura temporanea e sostituzione atomica. Scrittura e lettura vengono serializzate. Su Android si può usare [`AtomicFile`](https://developer.android.com/reference/android/util/AtomicFile) per il file finale; per il diario append-only servono flush/sync e un parser che tolleri la sola riga finale incompleta. I file `pending_` già esistenti della 0.2 restano leggibili e non vengono migrati distruttivamente.
- **Interruzioni:** perdita del Wi-Fi o del tracking mette in pausa la ripresa e la timeline; il diario resta sul telefono. Nel breve intervallo prima che entrambi rilevino la caduta, i campioni fisici restano nel diario ma possono mancare riferimenti certi ai frame: quel tratto viene segnalato come **non sincronizzato** e non viene interpolato silenziosamente sull'animazione della scena. Se Blender si chiude, l'app marca la take **Recuperabile** e non prova a continuare una timeline inesistente. La nuova connessione importa il file completo o parziale usando lo snapshot iniziale. Una take parziale è etichettata come tale nell'elenco Blender.
- **Limiti:** il formato v2 evita il limite attuale della singola riga JSON di 8 MiB mediante invio a blocchi con ID e indice, conferma di ogni blocco e conferma finale. Il server deduplica i blocchi e valida lunghezza, ordine, hash finale e numero massimo di campioni. Riprende dal primo blocco non confermato dopo la riconnessione. Il telefono non elimina mai il diario o il file finale prima della conferma finale di Blender.

## Ordine di sviluppo e verifiche di accettazione

| Fase | Risultato verificabile |
| --- | --- |
| 1. Protocollo e diario | Formato v2, ID e snapshot, import idempotente senza `record_start`, recupero di file troncato e trasferimento a blocchi. File 0.2 ancora importabili. |
| 2. Timeline | Rec attende conferma, conto opzionale, playback dal frame corrente, Stop al frame corrente/finale, pause su rete/tracking, frame markers nel diario. Una scena con personaggio animato avanza nell'anteprima durante Rec. |
| 3. Obiettivo | Camera della take indipendente; pinch per mm, slider per fuoco e f/, anteprima aggiornata e Action separata per obiettivo. Selezionando due take restano corretti entrambi gli obiettivi. |
| 4. Robustezza e dispositivi | Ping/pong, riconnessione, invio a blocchi e recupero verificati su Galaxy S25 Ultra con Wi-Fi interrotto, chiusura forzata dell'app e riavvio di Blender. Test di layout su tablet e prova reale quando disponibile. |

Verifiche obbligatorie: nessun salto al frame iniziale o dopo Resume; la timeline non riparte in loop; una take inviata due volte non crea nuove Action; cambi di focale, fuoco e diaframma sopravvivono a Stop, salvataggio/riapertura del `.blend` e selezione di un'altra take; una camera sorgente animata resta intatta; file locale non cancellato senza conferma; una scena lenta segnala frame persi. Test puri per formato/tempi/protocollo, prove headless Blender per Action e recupero, widget test per gesto e countdown, test Kotlin per diario e riconnessione, poi prova reale sul telefono. La release 0.2.0 resta installabile finché la nuova coppia app/add-on non supera queste verifiche.

## Scelte da approvare prima del codice

1. **Fine timeline:** raccomandazione: Stop automatico al frame finale, senza loop.
2. **Camera sorgente già animata:** raccomandazione: creare una camera dedicata per la take e non alterare quella sorgente.
3. **Riconnessione dopo riavvio completo:** raccomandazione: nuovo QR; auto-riconnessione solo per interruzioni di rete nella stessa sessione. Le take restano sul telefono fino alla conferma.
