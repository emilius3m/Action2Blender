# Action2Blender — riprendere lo sviluppo

Aggiornato il 29 settembre 2026. Questo documento descrive **il codice locale**, non la release scaricabile da GitHub. Dopo una pausa, ricontrollare versioni, percorsi e risultati nel checkout prima di continuare.

## Decisioni confermate

- Nome **Action2Blender**, licenza MIT per il codice originale. App Android in Flutter, acquisizione ARCore e collegamento in Kotlin, add-on Blender in Python.
- Prima piattaforma di prova: Blender 5.2.1 e Samsung Galaxy S25 Ultra. Il progetto è destinato anche ad altri Android compatibili con ARCore, ancora da provare.
- Uso a mano libera o su supporto; camera esistente con **Azzera** o nuova camera creata dall'app; scala del movimento fisico; ogni **Rec/Stop** salva una take distinta.
- Anteprima della scena sul telefono via rete locale, inquadratura 16:9 in orizzontale, comandi sopra il video e interfaccia per tablet.
- **Non pubblicare codice, APK, ZIP o release senza richiesta espressa dell'utente.** Una build o installazione locale non autorizza la pubblicazione.

## Stato al passaggio di consegne

- Repository: `https://github.com/emilius3m/Action2Blender.git`, ramo `main`. Pubblicata su richiesta dell'utente la pre-release **0.2.0 beta 1** (tag `v0.2.0-beta.1`, 29 settembre 2026) con `Action2Blender-0.2.0-beta.1.apk` e `Action2Blender-addon-0.2.0.zip`. Iniziare comunque con `git status --short`.
- Versione app in `pubspec.yaml`: `0.2.0+13`. L'add-on dichiara `(0, 2, 0)` in `addon/action2blender/__init__.py`; le build locali 0.2.1–0.2.3 dell'add-on e `+9`–`+12` dell'app erano sviluppo non pubblicato. `RELEASE_NOTES.md` contiene le note della 0.2.0 beta 1.
- APK release locale: `build/app/outputs/flutter-apk/app-release.apk`. ZIP add-on: `dist/Action2Blender-addon-0.2.0.zip`. Sono artefatti ignorati da Git, rigenerabili. L'APK firmato `0.2.0+13` è stato installato sul Galaxy S25 Ultra il 29 settembre sopra la build `+12`, conservando i dati; la prova completa delle nuove funzioni sul telefono non è ancora conclusa.
- I sorgenti dell'add-on sono copiati anche in `%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\action2blender` e sono allineati alla versione 0.2.0. Il 29 settembre la registrazione dell'add-on installato è stata verificata in Blender 5.2.1 in modalità background. **Blender GUI già aperto può avere il vecchio modulo in memoria**: salvare la scena e riavviare Blender, oppure disattivare l'add-on, rimuovere `action2blender*` da `sys.modules` e riattivarlo.
- Verifiche della 0.2.0: `flutter analyze`, 12 test Flutter, 7 test Kotlin, 28 test Python, prove isolate Blender (add-on, camera, take duplicate, movimento con camera inclinata, anteprima, stabilizzazione) e build release APK firmata. Il 29 settembre sono stati ripetuti con esito positivo `flutter analyze`, 12 test Flutter, i test Kotlin e Python, e la prova Blender dell'inquadratura 16:9; l'APK firmato è stato verificato e installato. Queste verifiche non sostituiscono una ripresa completa sul telefono.
- **Ancora da verificare fisicamente:** nuova camera creata dal telefono, joystick, nuova anteprima sul dispositivo, Rec/Stop e riproduzione di una take che includa questi comandi. Annotare i risultati prima di segnare queste funzioni come confermate.

## Mappa dei file

| Parte | File principali | Ruolo |
| --- | --- | --- |
| Interfaccia Android | `lib/main.dart`, `lib/app_language.dart`, `lib/control_joystick.dart`, `lib/viewport_preview.dart`, `lib/pairing.dart` | Comandi, stati, anteprima, QR, etichette italiane e inglesi |
| Android nativo | `android/app/src/main/kotlin/org/action2blender/action2blender/MainActivity.kt`, `UiLanguage.kt`, `PoseStabilizer.kt` | ARCore, scanner QR incluso, ponte Flutter, filtro live, registrazione, lingua e preferenze di connessione |
| Movimento virtuale | `android/app/src/main/kotlin/org/action2blender/action2blender/NavigationController.kt` | Joystick e salita/discesa |
| Rete e take sul telefono | `BridgeClient.kt`, `TakeRecorder.kt` nella stessa cartella Kotlin | Socket, conferme, campioni |
| Add-on Blender | `addon/action2blender/blender.py`, `core.py`, `transport.py`, `viewport.py`, `pairing.py` | Camera, Action, trasformazioni, protocollo, fotogrammi, QR |
| Verifiche | `test/`, `tests/`, `android/app/src/test/` | Flutter, Python, Kotlin e Blender senza GUI |
| Pacchetti | `scripts/package_addon.py`, `scripts/build_release.ps1` | ZIP e APK firmato |

`README.md` (inglese) e `README.it.md` (italiano) guidano l'installazione e l'uso della release 0.2.0 beta 1: vanno aggiornati insieme; `PROJECT_BRIEF.md` conserva le decisioni iniziali ed è **storico**. `CAMERA_DESIGN.md` contiene anche funzioni ancora da realizzare. `RECORDING_V2_DESIGN.md` propone timeline durante Rec, controlli dell'obiettivo e recupero delle take: **è un progetto tecnico, non codice già presente**. Per lo stato effettivo prevalgono questo documento e il codice.

## Funzioni presenti nel codice locale

1. In Blender l'add-on espone **Vista 3D → N → Action2Blender**. **Start phone connection** avvia un server TCP e mostra IP, porta e QR con codice temporaneo. Telefono e PC devono usare la stessa rete locale. Se il PC ha più interfacce, correggere l'IP mostrato prima della scansione. Il lettore QR è incluso nell'app.
   L'interfaccia Blender e i suoi messaggi sono in inglese. L'app mostra italiano sui telefoni impostati in italiano e inglese negli altri casi, traducendo anche i messaggi noti ricevuti dall'add-on. L'app salva IP e porta dell'ultima connessione nelle preferenze Android e li ripristina all'avvio; il codice temporaneo di abbinamento non viene salvato.
2. ARCore fornisce posizione e orientamento. **Azzera** ancora la posa del telefono alla camera attiva; l'app mostra la camera pronta solo dopo la conferma di Blender. Una camera con parent o qualsiasi vincolo attivo viene rifiutata.
3. **Nuova camera dalla vista 3D** copia posizione e orientamento della prima Vista 3D della scena trovata da Blender; la vista deve essere prospettica. **Nuova camera dall'oggetto selezionato** prende l'orientamento della vista e calcola una distanza per includere il bounding box mondiale dell'oggetto, con un margine del 20%. Usa il fotogramma effettivo dell'obiettivo (`view_frame(scene=scene)`), quindi considera il formato di render 16:9 e il relativo campo visivo verticale. Senza Vista 3D usa la camera corrente come riferimento, se esiste; senza entrambe parte da `(0, 0, 5)`. La nuova camera diventa attiva, ha dati obiettivo propri e non ha parent o vincoli. Viene collegata alla collezione **Action2Blender** della scena, che l'add-on crea o riusa; una camera già esistente non viene spostata. Non evita ostacoli tra camera e soggetto.
4. **Sposta**, **Ruota** e salita/discesa aggiungono movimento virtuale al tracking fisico. Le velocità sono ora fisse nel codice (`NavigationController.kt`: 2 unità Blender/s e 1,5 rad/s), indipendenti dalla scala fisica. Servono connessione, camera pronta e tracking ARCore valido anche sul supporto.
   L'app 0.2.0 applica prima una **Stabilizzazione live** regolabile alla posa fisica ARCore; la stessa posa filtrata guida la camera in diretta ed entra nei campioni della take. Il valore iniziale è 25% e resta memorizzato sul telefono. 0% disattiva il filtro; non si cambia durante Rec. Un grande salto del tracking o il suo recupero azzera lo stato del filtro per evitare un lento trascinamento verso la nuova posa. Quando la sessione ARCore è attiva, `FLAG_KEEP_SCREEN_ON` impedisce lo spegnimento per inattività; il flag viene rimosso all'apertura del lettore QR, in pausa e in caso di errore di avvio ARCore.
5. L'add-on genera fotogrammi della camera fino a circa 10 volte al secondo; l'app li richiede su un secondo server HTTP locale, con lo stesso codice temporaneo. Larghezza richiesta: 640 px sul telefono, 960 px sul tablet. La latenza effettiva non è stata misurata sulla build attuale.
6. All'avvio della connessione, **Inquadratura 16:9** cambia la risoluzione della scena se attiva. Dopo Stop la take viene scritta in `pending_<id>.json` nell'area privata dell'app, ritrasmessa dopo riconnessione e cancellata solo alla risposta `take_saved`. Blender crea una Action originale per posizione e rotazione della camera. Con **Stabilizza dopo Stop** attivo (valore iniziale: attivo, intensità 0,5), crea anche una seconda Action stabilizzata e seleziona quest'ultima. Entrambe compaiono nel pannello. **Stabilizza take selezionata** può generare una nuova versione da una take già presente, usando sempre l'Action originale come fonte. La perdita del tracking sospende Rec; **Riprendi senza salto** riprende da un nuovo riferimento.

   Affidabilità della conferma: l'add-on 0.2.0 salva l'ID della take nelle voci della scena. Un reinvio della stessa take riceve `take_saved` anche senza un nuovo `record_start`; l'Action non viene duplicata e una registrazione successiva non viene consumata dal vecchio reinvio. Il controllo cerca l'ID anche in altre scene del progetto e richiede che almeno un'Action salvata esista ancora. L'ID sopravvive al riavvio di Blender soltanto dopo aver salvato il file `.blend`. Le take create con l'add-on precedente non hanno questo ID: se il loro `take_saved` era già andato perso e l'add-on viene ricaricato, verificare manualmente la take nel progetto e conservare il file in attesa sul telefono; il nuovo codice non può identificarla in modo sicuro. L'app 0.2.0 non azzera la camera pronta per un errore relativo alla conferma della take, ma una vera disconnessione richiede ancora **Azzera** dopo la riconnessione.

## Protocollo e diagnosi del collegamento

- Controllo: JSON per riga su TCP, porta predefinita `45767`, versione protocollo `1`. Il primo messaggio è `hello` con versione, token QR e `camera_control: 3`. `hello_ok` contiene `viewport_port`, `recenter_ack` e `camera_control: 3`.
- `camera_control` 3 allinea la verticale del telefono a quella di Blender: una panoramica ruota la camera attorno all'asse Z del mondo e camminare la sposta in orizzontale, anche se la camera è inclinata. Il joystick invia `v` negli assi del mondo ARCore (Y in alto), `look` è rotazione attorno alla verticale e inclinazione della camera. App e add-on devono avere la stessa versione: l'add-on rifiuta un'app precedente con "Update the Action2Blender app on your phone"; il telefono traduce il messaggio in italiano se necessario. L'app rifiuta un add-on precedente chiedendo di aggiornarlo o ricaricarlo. In quel caso controllare prima se Blender GUI usa ancora il vecchio modulo in memoria: copiare file sul disco non ricarica Python già importato.
- `recenter` e `create_camera` ricevono `recenter_ok` solo quando Blender ha elaborato il comando; in caso contrario torna `error`. Dopo Stop torna `take_saved`. Le pose usano `p`, `q` e, se presente, navigazione virtuale `v` e `look`.
- Anteprima: `GET /frame?since=…&width=640|960` via HTTP con intestazione `X-Action2Blender-Token`. È separata dal controllo. Se manca, controllare sia porta TCP sia porta dinamica HTTP e firewall della rete privata.

## Ricostruire e verificare

Da PowerShell nella cartella `Action2Blender`:

```powershell
git status --short
flutter pub get
flutter analyze
flutter test
Push-Location android
& .\gradlew.bat testDebugUnitTest --no-daemon
Pop-Location
python -m unittest discover -s tests -p 'test_*.py'
..\blender.exe --background --factory-startup --python tests/blender_smoke.py
..\blender.exe --background --factory-startup --python tests/blender_camera_smoke.py
..\blender.exe --background --factory-startup --python tests/blender_motion_smoke.py
..\blender.exe --background --factory-startup --python tests/blender_viewport_smoke.py
..\blender.exe --background --factory-startup --python tests/blender_stabilization_smoke.py
..\blender.exe --background --factory-startup --python tests/blender_duplicate_take_smoke.py
python scripts/package_addon.py
& .\scripts\build_release.ps1
```

La build release richiede chiave privata e password cifrata per l'account Windows corrente in `%USERPROFILE%\.action2blender`. La chiave **non è nel repository**. Conservare un backup sicuro: una nuova chiave non permette di aggiornare direttamente l'app firmata con la precedente. Una build debug si crea con `flutter build apk --debug --target-platform android-arm64`, ma ha firma diversa e non si installa sopra la release senza rimuoverla (rimozione che può cancellare le take non ancora confermate).

Per reinstallare localmente la build firmata, dopo aver collegato e sbloccato il telefono:

```powershell
& 'C:\AndroidSdk\platform-tools\adb.exe' devices -l
& 'C:\AndroidSdk\platform-tools\adb.exe' install -r 'build\app\outputs\flutter-apk\app-release.apk'
```

Installare lo ZIP da `dist/` tramite **Edit → Preferences → Add-ons → Install from Disk**, abilitarlo e cercare il pannello. Se Blender era aperto, salvare prima la scena e ricaricare l'add-on o riavviare Blender. Verificare la versione realmente caricata prima di attribuire un errore al nuovo codice.

## Prima prova reale alla ripresa

1. Salvare una copia di una scena Blender di prova. Annotare versione app, add-on, commit e risultato di `git status --short`.
2. Avviare la connessione nel pannello Blender, scansionare il QR **dall'app Action2Blender** e attendere tracking e conferma camera. Se il QR fallisce, annotare il messaggio esatto e provare IP/porta/codice manuali.
3. Su camera esistente: **Azzera**, movimento fisico e rotazione; controllare direzione in Blender e anteprima 16:9 in orizzontale. Ripetere con telefono sul supporto e controlli virtuali.
4. Creare una camera dalla vista prospettica e una dall'oggetto selezionato. Controllare quale Vista 3D viene usata se ne sono aperte più di una; verificare inquadratura, joystick e salita/discesa.
5. **Rec → movimento fisico + joystick → Stop**. Selezionare e riprodurre la take in Blender; controllare corrispondenza con l'anteprima. Provare una seconda take e una breve interruzione della rete. Annotare salti, lag, clipping ed errori.
6. Provare un tablet Android compatibile con ARCore quando disponibile: il layout e le prestazioni tablet non sono ancora verificati sul dispositivo.

## Rifinire una take a mano libera

I piccoli tremolii del movimento fisico sono possibili. L'app 0.2.0 filtra **in diretta** la posa fisica che Blender mostra e registra; questo migliora anche l'anteprima durante Rec, con un possibile piccolo ritardo nei movimenti voluti. L'add-on 0.2.0 offre inoltre una stabilizzazione regolabile **dopo Stop**: un filtro simmetrico sul movimento e una media di quaternioni normalizzati sull'orientamento; conserva tempi e pose iniziale/finale, oltre all'Action originale. I due filtri possono sommarsi: confrontare la take con l'originale e, se risulta troppo morbida, ridurre una delle intensità. Il filtro dell'add-on non elimina chiavi. Se serve una take più facile da ritoccare, nel **Graph Editor** usare **Key → Decimate** su una copia e ricontrollare il movimento. In alternativa, le curve si possono rifinire manualmente con **Key → Smooth** o **Butterworth Smooth**.

La qualità del filtro va ancora valutata su riprese reali. Le prove automatiche coprono la riduzione di oscillazioni artificiali, la continuità dei quaternioni e la creazione/selezione delle due Action in Blender. In futuro si potranno separare le intensità di posizione e orientamento e aggiungere una riduzione delle chiavi opzionale.

## Limiti e prossime scelte

- La vista usata per creare la camera è la **prima** `VIEW_3D` trovata per la scena, non necessariamente quella guardata dall'utente. Serve una selezione esplicita dell'area giusta.
- Focale/zoom ottico, dolly dedicato, orbita sul soggetto e velocità regolabile dei joystick restano da progettare o implementare. La stabilizzazione ha un'intensità unica per posizione e orientamento, ancora da valutare su riprese vere. Il movimento in avanti del joystick cambia la prospettiva, ma non è un dolly dedicato con valore visibile.
- Le take animano posizione e rotazione, **non la focale**. La Action dell'obiettivo in `CAMERA_DESIGN.md` è progettuale.
- Parent e vincoli delle camere non sono supportati. L'add-on rifiuta qualunque vincolo non disattivato con influenza positiva, anche se innocuo in una scena particolare.
- Soggetti complessi, più Viste 3D, ostruzioni, scene pesanti, latenza Wi-Fi, continuità del tracking in orizzontale e altri dispositivi Android richiedono prove reali.
- Prima di una futura release, allineare README, note di versione, numeri di versione e pacchetti alla build provata. Pubblicare solo su richiesta espressa dell'utente.
