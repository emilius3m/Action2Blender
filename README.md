# Action2Blender

Action2Blender usa un telefono Android compatibile con ARCore per muovere e registrare una camera di Blender. L'interfaccia del telefono è in Flutter; il tracciamento ARCore e la comunicazione locale sono in Kotlin; l'add-on Blender è in Python.

## Stato

La prima beta è stata provata sul **Samsung Galaxy S25 Ultra** con Android 16 e Blender 5.2. L'acquisizione ARCore, il collegamento USB e Wi-Fi e il salvataggio di take reali sono stati verificati con l'APK di debug. L'APK di release è firmato e verificato, ma non è stato reinstallato sul telefono dopo la firma. Altri dispositivi Android richiedono prove.

## Uso della beta

1. Scarica lo ZIP dell'add-on dalla [pagina Releases](https://github.com/emilius3m/Action2Blender/releases). In Blender 5.2 usa **Edit > Preferences > Add-ons > Install from Disk**, seleziona lo ZIP e abilita la casella **Action2Blender**. Se Blender era già aperto durante l'installazione, riavvialo. Il pannello si trova nella **Vista 3D > barra laterale (N) > Action2Blender**.
2. Seleziona la camera della scena. Nel pannello **Action2Blender**, premi **Start phone connection**. Annota IP, porta e codice di abbinamento. Il firewall di Windows potrebbe chiedere di consentire la connessione sulla rete privata.
3. Scarica l'APK dalla [pagina Releases](https://github.com/emilius3m/Action2Blender/releases) e installalo su un telefono Android compatibile con ARCore. Telefono e PC devono essere sulla stessa rete locale. Apri l'app, concedi il permesso alla fotocamera e inserisci IP, porta e codice.
4. Quando l'app mostra **Tracking attivo**, premi **Azzera** per mantenere l'inquadratura corrente come punto di partenza. Regola la scala dello spostamento prima di iniziare una take.
5. Premi **Rec**, muovi il telefono, poi **Stop**. La take appare nell'elenco del pannello Blender. Se il tracking si perde, la take entra in pausa; quando torna, premi **Riprendi senza salto**.

Ogni take è una Action distinta sulla stessa camera. I campioni sono conservati sul telefono fino alla conferma di salvataggio in Blender. Durante una breve interruzione della rete, la registrazione locale continua e la take viene ritrasmessa quando la connessione torna. Il telefono mostra i controlli e lo stato del tracking; la scena si guarda sul monitor del PC.

La prima versione usa IP e codice inseriti a mano. L'abbinamento QR e lo streaming del viewport sul telefono sono previsti per versioni successive.

## Sviluppo

- `flutter analyze` e `flutter test` verificano l'interfaccia Flutter.
- `python -m unittest discover -s tests -v` verifica pose, take e protocollo.
- Da una shell nella cartella di Blender: `blender --background --factory-startup --python Action2Blender/tests/blender_smoke.py` verifica la creazione e selezione di due take.
- `python scripts/package_addon.py` crea lo ZIP installabile dell'add-on.
- `flutter build apk --debug --target-platform android-arm64` crea un APK di prova per telefoni arm64.
- Su Windows, `scripts/create_release_key.ps1` crea una chiave di firma privata fuori dal repository; `scripts/build_release.ps1` crea l'APK di release. La password è cifrata per l'account Windows corrente: conserva una copia sicura della chiave e della password per poter pubblicare aggiornamenti futuri.

Il progetto originale è distribuito sotto [licenza MIT](LICENSE). Il codice di ARCore e delle dipendenze mantiene le rispettive licenze.
