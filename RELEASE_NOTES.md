# Action2Blender 0.2.0 beta 1

**English** · [Italiano](#italiano)

The phone becomes a complete virtual camera: a preview of the scene on screen, controls to move the camera even when you stand still, new cameras created from the app, and stabilized shots.

### What's new

- **Preview on the phone.** Blender sends the camera view to the phone over the local network, on an authenticated channel separate from the motion data. In landscape the 16:9 preview fills the screen with the controls over the video; on tablets the controls sit alongside.
- **New camera from the app.** **From Blender 3D View** creates a camera where you are looking in the 3D Viewport; **Frame selected object** places it so the selected object fits in the shot.
- **On-screen controls.** The **Move** and **Rotate** joysticks and the up/down buttons move the camera even with the phone fixed on a mount. They add to the physical movement and are recorded in the take.
- **Level horizon.** The phone's vertical now matches Blender's: panning a tilted camera no longer tilts the horizon, and walking moves it horizontally.
- **Stabilization.** In the app, adjustable **Live stabilization**; in Blender, **Stabilize after Stop** creates a stabilized version of every take while keeping the original, and **Stabilize selected take** applies it to takes already recorded.
- **More reliable recording.** The screen stays on while tracking, a take received twice is not duplicated, and Blender's error messages are shown on the phone.
- **Language.** The app is in Italian on Italian phones and in English otherwise; the Blender panel is in English.

### Download and install

- **Action2Blender-addon-0.2.0.zip**: in Blender open **Edit → Preferences → Add-ons → Install from Disk**, choose the ZIP and enable **Action2Blender**. If you are upgrading from an earlier version, save your scene and restart Blender.
- **Action2Blender-0.2.0-beta.1.apk**: install it on an ARCore-compatible Android phone. Phone and PC must be on the same network.

**Update the app and the add-on together**: 0.2 does not connect to 0.1, and each one asks you to update the other. The APK has the same signature as 0.1.1 and installs over it without uninstalling. Full instructions are in the [README](https://github.com/emilius3m/Action2Blender#readme).

### Testing and limitations

Tested with Flutter, Kotlin and Python tests and with automated checks in Blender 5.2.1 (connection, preview, camera creation, movement with a tilted camera, takes and stabilization). The previous development build was installed on a Samsung Galaxy S25 Ultra, but the full test of these features on the phone is not finished yet, and other devices have not been tested.

Known limitations: opening another `.blend` file while connected requires restarting the connection from the panel; a pending take cannot be saved if Blender is restarted in the meantime; the phone does not reconnect by itself after a network drop; takes longer than about 15 minutes can exceed the size limit. The full list is in the [README](https://github.com/emilius3m/Action2Blender#known-limitations-of-this-beta).

---

## Italiano

Il telefono diventa una camera virtuale completa: anteprima della scena sullo schermo, comandi per muovere la camera anche da fermi, nuove camere create dall'app e stabilizzazione delle riprese.

### Novità

- **Anteprima sul telefono.** Blender invia al telefono la vista della camera sulla rete locale, con un collegamento autenticato separato dai dati di movimento. In orizzontale l'anteprima 16:9 occupa lo schermo con i comandi sopra il video; su tablet i comandi stanno a lato.
- **Nuova camera dall'app.** **Dalla vista 3D di Blender** crea una camera dove stai guardando nella Vista 3D; **Inquadra oggetto selezionato** la posiziona in modo da contenere l'oggetto selezionato.
- **Comandi sullo schermo.** I joystick **Sposta** e **Ruota** e i pulsanti su/giù muovono la camera anche con il telefono fermo su un supporto. Si sommano al movimento fisico e vengono registrati nella take.
- **Orizzonte sempre dritto.** La verticale del telefono coincide con quella di Blender: una panoramica con una camera inclinata non storce più l'orizzonte e camminare la sposta in orizzontale.
- **Stabilizzazione.** Nell'app, **Stabilizzazione live** regolabile; in Blender, **Stabilize after Stop** crea una versione stabilizzata di ogni take conservando l'originale, e **Stabilize selected take** la applica alle take già registrate.
- **Riprese più affidabili.** Lo schermo resta acceso durante il tracciamento, una take ricevuta due volte non viene duplicata e i messaggi di errore di Blender compaiono sul telefono.
- **Lingua.** L'app è in italiano sui telefoni in italiano e in inglese negli altri casi; il pannello di Blender è in inglese.

### Scarica e installa

- **Action2Blender-addon-0.2.0.zip**: in Blender apri **Edit → Preferences → Add-ons → Install from Disk**, scegli lo ZIP e abilita **Action2Blender**. Se aggiorni da una versione precedente, salva la scena e riavvia Blender.
- **Action2Blender-0.2.0-beta.1.apk**: installalo su un telefono Android compatibile con ARCore. Telefono e PC devono essere sulla stessa rete.

**Aggiorna insieme app e add-on**: la 0.2 non si collega alla 0.1 e ciascuno dei due chiede di aggiornare l'altro. L'APK ha la stessa firma della 0.1.1 e si installa sopra senza disinstallarla. Istruzioni complete nel [README in italiano](https://github.com/emilius3m/Action2Blender/blob/main/README.it.md).

### Verifiche e limiti

Verificato con test Flutter, Kotlin e Python e con prove automatiche in Blender 5.2.1 (collegamento, anteprima, creazione della camera, movimento con camera inclinata, take e stabilizzazione). La build di sviluppo precedente è stata installata sul Samsung Galaxy S25 Ultra, ma la prova completa di queste funzioni sul telefono non è ancora conclusa, e altri dispositivi non sono stati provati.

Limiti noti: aprire un altro file `.blend` con la connessione attiva richiede di riavviare la connessione dal pannello; una take in attesa non può essere salvata se nel frattempo Blender viene riavviato; il telefono non si ricollega da solo dopo un'interruzione della rete; take oltre circa 15 minuti possono superare il limite di dimensione. L'elenco completo è nel [README](https://github.com/emilius3m/Action2Blender/blob/main/README.it.md#limiti-noti-di-questa-beta).
