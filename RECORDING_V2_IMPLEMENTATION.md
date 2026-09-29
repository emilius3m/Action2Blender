# Action2Blender 0.3.0-dev.1 — sviluppo locale

Aggiornato il 29 settembre 2026. Questa versione non è pubblicata. La release scaricabile e descritta nei README resta la 0.2.0 beta 1. L'app 0.3 e l'add-on 0.3 devono essere usati insieme (`camera_control: 4`). Non pubblicare APK, ZIP o codice senza richiesta espressa dell'utente.

## Cosa è implementato

- **Rec con timeline:** `record_prepare` acquisisce camera, frame iniziale, FPS e impostazioni della scena. Il telefono attende la conferma, esegue il conto opzionale Off/3/5 secondi e invia `record_go`. Blender duplica la camera, avvia la timeline e invia i frame attraversati. Stop, fine dell'intervallo e interruzione del collegamento fermano la riproduzione. La camera sorgente e le sue Action restano intatte.
- **Obiettivo nella take:** pinch a due dita per la focale, slider per focale, distanza di fuoco e diaframma. L'add-on applica i valori in diretta e salva una Action separata sui dati della camera. La distanza di un eventuale oggetto di fuoco della camera sorgente è fissata all'inizio della take.
- **Take autosufficienti:** il file conserva ID, camera sorgente, posa e ottica iniziali, scala, frame, FPS, eventi di movimento/obiettivo e riferimenti ai frame di Blender. Può essere importato senza lo stato volatile `record_start`; se la camera non esiste più, Blender ne crea una di recupero. Lo stesso ID non crea due Action.
- **Persistenza e rete:** il telefono scrive i campioni in `recording_<id>.jsonl` e sincronizza il file almeno ogni secondo. A Stop crea atomicamente `pending_<id>.json`; lo elimina solo dopo `take_saved`. Una ripresa interrotta diventa una take parziale da inviare con comando esplicito. Il collegamento usa ping/pong, riconnessione automatica nella stessa sessione, trasferimento a blocchi da 48 KiB con hash e ripresa dal blocco mancante. I tempi dei frame sono corretti con una stima dell'offset fra gli orologi del PC e del telefono.
- **Interfaccia:** il frame e i valori ottici appaiono durante Rec anche in orizzontale; una take parziale è indicata nel pannello Blender.

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

## Prove ancora necessarie

Aprire una scena di prova con un oggetto animato e salvare una copia del `.blend`. Verificare: conto 3/5 secondi; Stop manuale; pinch/fuoco/diaframma nella Action; cambio take; pausa e ripresa dopo perdita del Wi-Fi; importazione dopo riavvio di Blender; recupero dopo chiusura forzata dell'app. Misurare lo scarto fra frame mostrato e posa salvata, soprattutto in una scena lenta. Ripetere il layout su un tablet reale quando disponibile.

Le prove automatiche non sostituiscono questa verifica con Blender GUI e ARCore. Finché non è conclusa, considerare la 0.3 una build di sviluppo locale.
