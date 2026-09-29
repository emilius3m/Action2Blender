# Action2Blender 0.2.0 beta 1

Il telefono diventa una camera virtuale completa: anteprima della scena sullo schermo, comandi per muovere la camera anche da fermi, nuove camere create dall'app e stabilizzazione delle riprese.

## Novità

- **Anteprima sul telefono.** Blender invia al telefono la vista della camera sulla rete locale, con un collegamento autenticato separato dai dati di movimento. In orizzontale l'anteprima 16:9 occupa lo schermo con i comandi sopra il video; su tablet i comandi stanno a lato.
- **Nuova camera dall'app.** **Dalla vista 3D di Blender** crea una camera dove stai guardando nella Vista 3D; **Inquadra oggetto selezionato** la posiziona in modo da contenere l'oggetto selezionato.
- **Comandi sullo schermo.** I joystick **Sposta** e **Ruota** e i pulsanti su/giù muovono la camera anche con il telefono fermo su un supporto. Si sommano al movimento fisico e vengono registrati nella take.
- **Orizzonte sempre dritto.** La verticale del telefono coincide con quella di Blender: una panoramica con una camera inclinata non storce più l'orizzonte e camminare la sposta in orizzontale.
- **Stabilizzazione.** Nell'app, **Stabilizzazione live** regolabile; in Blender, **Stabilize after Stop** crea una versione stabilizzata di ogni take conservando l'originale, e **Stabilize selected take** la applica alle take già registrate.
- **Riprese più affidabili.** Lo schermo resta acceso durante il tracciamento, una take ricevuta due volte non viene duplicata e i messaggi di errore di Blender compaiono sul telefono.
- **Lingua.** L'app è in italiano sui telefoni in italiano e in inglese negli altri casi; il pannello di Blender è in inglese.

## Scarica e installa

- **Action2Blender-addon-0.2.0.zip**: in Blender apri **Edit → Preferences → Add-ons → Install from Disk**, scegli lo ZIP e abilita **Action2Blender**. Se aggiorni da una versione precedente, salva la scena e riavvia Blender.
- **Action2Blender-0.2.0-beta.1.apk**: installalo su un telefono Android compatibile con ARCore. Telefono e PC devono essere sulla stessa rete.

**Aggiorna insieme app e add-on**: la 0.2 non si collega alla 0.1 e ciascuno dei due chiede di aggiornare l'altro. L'APK ha la stessa firma della 0.1.1 e si installa sopra senza disinstallarla. Istruzioni complete nel [README in italiano](https://github.com/emilius3m/Action2Blender/blob/main/README.it.md) ([English](https://github.com/emilius3m/Action2Blender#readme)).

## Verifiche e limiti

Verificato con test Flutter, Kotlin e Python e con prove automatiche in Blender 5.2.1 (collegamento, anteprima, creazione della camera, movimento con camera inclinata, take e stabilizzazione). La build di sviluppo precedente è stata installata sul Samsung Galaxy S25 Ultra, ma la prova completa di queste funzioni sul telefono non è ancora conclusa, e altri dispositivi non sono stati provati.

Limiti noti: aprire un altro file `.blend` con la connessione attiva richiede di riavviare la connessione dal pannello; una take in attesa non può essere salvata se nel frattempo Blender viene riavviato; il telefono non si ricollega da solo dopo un'interruzione della rete; take oltre circa 15 minuti possono superare il limite di dimensione. L'elenco completo è nel [README](https://github.com/emilius3m/Action2Blender/blob/main/README.it.md).
