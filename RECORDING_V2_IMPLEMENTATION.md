# Action2Blender 0.3.0-dev.1 — sviluppo locale

Aggiornato il 29 settembre 2026. Questa versione non è pubblicata. La release scaricabile e descritta nei README resta la 0.2.0 beta 1. L'app 0.3 e l'add-on 0.3 devono essere usati insieme (`camera_control: 4`). Non pubblicare APK, ZIP o codice senza richiesta espressa dell'utente.

## Cosa è implementato

- **Rec con timeline:** `record_prepare` acquisisce camera, frame iniziale, FPS e impostazioni della scena. Il telefono attende la conferma, esegue il conto opzionale Off/3/5 secondi e invia `record_go`. Blender duplica la camera, avvia la timeline e invia i frame attraversati. Stop, fine dell'intervallo e interruzione del collegamento fermano la riproduzione. La camera sorgente e le sue Action restano intatte.
- **Obiettivo nella take:** pinch a due dita per la focale, slider per focale, distanza di fuoco e diaframma. L'add-on applica i valori in diretta e salva una Action separata sui dati della camera. La distanza di un eventuale oggetto di fuoco della camera sorgente è fissata all'inizio della take.
- **Take autosufficienti:** il file conserva ID, camera sorgente, posa e ottica iniziali, scala, frame, FPS, eventi di movimento/obiettivo e riferimenti ai frame di Blender. Può essere importato senza lo stato volatile `record_start`; se la camera non esiste più, Blender ne crea una di recupero. Lo stesso ID non crea due Action.
- **Persistenza e rete:** il telefono scrive i campioni in `recording_<id>.jsonl` e sincronizza il file almeno ogni secondo. A Stop crea atomicamente `pending_<id>.json`; lo elimina solo dopo `take_saved`. Una ripresa interrotta diventa una take parziale da inviare con comando esplicito. Il collegamento usa ping/pong, riconnessione automatica nella stessa sessione, trasferimento a blocchi da 48 KiB con hash e ripresa dal blocco mancante. I tempi dei frame sono corretti con una stima dell'offset fra gli orologi del PC e del telefono.
- **Interfaccia:** il frame e i valori ottici appaiono durante Rec anche in orizzontale; una take parziale è indicata nel pannello Blender.

## Correzioni successive (29 settembre)

- Una take in attesa importata durante un'altra registrazione non azzera più quella registrazione, non cambia la camera attiva e non sposta la timeline (`tests/blender_recording_v2_smoke.py`).
- Aprire un altro `.blend` con la connessione attiva non ferma più i comandi: timer persistente, handler `load_pre`/`load_post`. Una ripresa in corso viene fermata come parziale e il telefono ne riceve l'avviso; dopo il caricamento serve di nuovo Azzera (`tests/blender_file_load_smoke.py`).
- La posa dal vivo rispetta il modo di rotazione della camera (Euler, quaternione, asse-angolo): le chiavi dell'utente continuano a funzionare. Un'Action sostituita da una take riceve il fake user e non sparisce al salvataggio.
- Rete: prima dell'abbinamento Blender accetta righe di al massimo 4 KB, dopo al massimo 256 KB; un client abbinato silenzioso per 30 s viene chiuso. Sul telefono le pose dal vivo in coda sono al massimo una: le più recenti sostituiscono quella in attesa (`tests/test_transport.py`).

## Percorsi principali

| Parte | File |
| --- | --- |
| Protocollo e import | `addon/action2blender/transport.py`, `blender.py`, `core.py` |
| Diario e cattura | `android/app/src/main/kotlin/org/action2blender/action2blender/TakeJournal.kt`, `TakeRecorder.kt`, `MainActivity.kt` |
| Connessione | `android/app/src/main/kotlin/org/action2blender/action2blender/BridgeClient.kt` |
| Comandi | `lib/main.dart` |
| Test | `tests/test_core.py`, `tests/test_transport.py`, `tests/blender_recording_v2_smoke.py`, `test/widget_test.dart` |

## Verifiche ripetibili

Da questa cartella, in PowerShell:

```powershell
python -m unittest discover -s tests -q
& '..\blender.exe' --background --factory-startup --python 'tests\blender_recording_v2_smoke.py'
& 'C:\flutter\bin\flutter.bat' analyze
& 'C:\flutter\bin\flutter.bat' test
Push-Location android
& '.\gradlew.bat' compileDebugKotlin testDebugUnitTest --no-daemon
Pop-Location
python scripts/package_addon.py
& '.\scripts\build_release.ps1'
```

La build firmata usa la chiave privata già presente sul PC. Un APK debug ha firma diversa e non può aggiornare la beta installata senza rimuoverla, operazione che cancellerebbe le take private non ancora confermate. I pacchetti di sviluppo locali sono `dist/Action2Blender-addon-0.3.0-dev.1.zip` e `build/app/outputs/flutter-apk/app-release.apk`.

## Prova sul dispositivo

Il 29 settembre la build 0.3.0-dev.1 firmata è stata installata sopra la 0.2.0+13 sul Galaxy S25 Ultra, conservando i dati. L'add-on 0.3 è stato copiato nella cartella add-on di Blender 5.2.1. Sono stati osservati collegamento via QR, tracking attivo, anteprima Wi-Fi, frame in avanzamento durante Rec e conferma **Take salvata in Blender** dopo la fine della timeline. Questa è una prova breve in una scena di test; non misura ancora sincronizzazione e qualità del movimento. Dopo ulteriori modifiche locali, i file dell'add-on su disco sono stati aggiornati: un Blender GUI già aperto può mantenere il modulo precedente in memoria fino a ricarica o riavvio.

### Prova del 29 settembre pomeriggio (app build 15, add-on con le correzioni di `de5226a`)

Scena di prova: cubo animato sui frame 1–96, camera con chiave Euler, 24 fps. Comandi sul telefono in parte da USB (`adb input`), in parte a mano. Dal pomeriggio Blender registra ogni messaggio ricevuto dal telefono, con ora e ID, per ricostruire le sequenze.

Funziona:

- collegamento con codice inserito a mano; camera creata dal telefono nella collezione **Action2Blender**;
- Rec e Stop manuale: take su una **copia** della camera, Action Original + Stabilized + Lens; la camera sorgente non cambia;
- conto alla rovescia di 3 s, con **Annulla** durante il conto; durata della take coerente con il momento di Stop (7,9 s registrati, Stop a 7,95 s dall'avvio);
- stop automatico alla fine della timeline;
- joystick **Sposta** con camera inclinata verso il basso: movimento orizzontale a quota costante; il movimento compare nei frame 83–112 (3,5–4,7 s) per una spinta di 3,2–4,9 s, quindi posa e timeline sono sincronizzate;
- pausa automatica alla perdita del tracking; Opzioni aperto durante Rec mantiene la registrazione e abilita gli slider dell'obiettivo.

Problemi trovati:

1. **Take con cambi di obiettivo rifiutata da Blender** ("Take timestamps must be finite and ordered"). Il tracking aggiunge i campioni con l'ora di inizio del frame ARCore, i cambi di obiettivo con l'ora del momento: un pinch fra i due inserisce campioni con tempo decrescente. Blender rifiuta l'intera take, resta in attesa di quell'ID e blocca nuove riprese e nuove camere finché non si riavvia la connessione; il telefono la ritrasmette a ogni ricollegamento. Take di prova conservata sul telefono: `12be1425`.
2. **IP sbagliato nel QR con una VPN attiva**: il pannello propone l'indirizzo della VPN (`10.96.241.40`) invece di quello Wi-Fi (`192.168.1.224`). Il campo IP va corretto a mano.
3. **App fuori passo rispetto a Blender (intermittente)**: in alcune prove l'app è uscita dallo stato di registrazione mentre Blender continuava; Stop non raggiungeva Blender e un tocco sul pulsante rimasto su **Annulla** poteva avviare una nuova ripresa. In un caso l'app ha poi inviato la take da sola. Causa non chiarita; tocchi manuali e automatici si sono sovrapposti in parte delle prove.
4. **Nessun limite di tempo nello stato di preparazione**: se la conferma di avvio si perde, l'app resta su **Annulla** senza uscita automatica.

Da non confondere con difetti dell'app: `uiautomator dump` si blocca durante Rec perché l'interfaccia si aggiorna di continuo, e leggere una take con `frame_set` sposta il frame corrente della scena.

## Prove ancora necessarie

Correggere il problema 1 e importare la take `12be1425` per verificare pinch, fuoco e diaframma nella Action dell'obiettivo. Poi: pausa e ripresa dopo perdita del Wi-Fi; importazione dopo riavvio di Blender (o riavvio della connessione durante Rec); recupero dopo chiusura forzata dell'app; cambio take; conto di 5 secondi. Chiarire il problema 3 con un registro degli eventi sul telefono. Misurare lo scarto fra frame mostrato e posa salvata in una scena lenta. Ripetere il layout su un tablet reale quando disponibile.

Le prove automatiche non sostituiscono questa verifica con Blender GUI e ARCore. Finché non è conclusa, considerare la 0.3 una build di sviluppo locale.
