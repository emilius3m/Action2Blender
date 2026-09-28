# Action2Blender

Action2Blender usa un telefono Android compatibile con ARCore per muovere e registrare una camera di Blender. L'interfaccia del telefono è in Flutter; il tracciamento ARCore e la comunicazione locale sono in Kotlin; l'add-on Blender è in Python.

## Stato

Questo repository contiene un **prototipo da provare sul dispositivo**. Il movimento, la conversione delle pose, il protocollo e la creazione di take separate sono verificati con test automatici e con Blender 5.2. L'acquisizione ARCore sul telefono e la stabilità della connessione Wi-Fi richiedono ancora una prova fisica. Non distribuire l'APK di debug come beta pubblica.

## Uso del prototipo

1. Installa l'add-on da `dist/Action2Blender-addon-0.1.0.zip` usando **Blender > Preferences > Add-ons > Install from Disk**. Se parti dal codice sorgente, crea uno ZIP con `addon/action2blender` come cartella principale `action2blender/`.
2. In Blender 5.2, seleziona la camera della scena. Nel pannello **Action2Blender** della Sidebar della vista 3D, premi **Start phone connection**. Annota IP, porta e codice di abbinamento. Il firewall di Windows potrebbe chiedere di consentire la connessione sulla rete privata.
3. Installa l'APK di prova da `build/app/outputs/flutter-apk/app-debug.apk` sul telefono Android compatibile con ARCore. Telefono e PC devono essere sulla stessa rete locale. Apri l'app, concedi il permesso alla fotocamera e inserisci IP, porta e codice.
4. Quando l'app mostra **Tracking attivo**, premi **Azzera** per mantenere l'inquadratura corrente come punto di partenza. Regola la scala dello spostamento.
5. Premi **Rec**, muovi il telefono, poi **Stop**. La take appare nell'elenco del pannello Blender. Se il tracking si perde, la take entra in pausa; quando torna, premi **Riprendi senza salto**.

Ogni take è una Action distinta sulla stessa camera. I campioni sono conservati sul telefono fino alla conferma di salvataggio in Blender. Durante una breve interruzione della rete, la registrazione locale continua e la take viene ritrasmessa quando la connessione torna. Il telefono mostra i controlli e lo stato del tracking; la scena si guarda sul monitor del PC.

La prima versione usa IP e codice inseriti a mano. L'abbinamento QR e lo streaming del viewport sul telefono sono previsti dopo la verifica del collegamento e del movimento reale.

## Sviluppo

- `flutter analyze` e `flutter test` verificano l'interfaccia Flutter.
- `python -m unittest discover -s tests -v` verifica pose, take e protocollo.
- Da una shell nella cartella di Blender: `blender --background --factory-startup --python Action2Blender/tests/blender_smoke.py` verifica la creazione e selezione di due take.
- `python scripts/package_addon.py` crea lo ZIP installabile dell'add-on.
- `flutter build apk --debug --target-platform android-arm64` crea un APK di prova per telefoni arm64. Una beta pubblica richiede firma di release e test su dispositivi Android reali.

Il progetto originale è distribuito sotto [licenza MIT](LICENSE). Il codice di ARCore e delle dipendenze mantiene le rispettive licenze.
