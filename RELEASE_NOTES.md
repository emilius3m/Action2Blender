# Action2Blender 0.1.0 beta 1

Prima beta di Action2Blender: un telefono Android compatibile con ARCore controlla e registra una camera esistente in Blender 5.2.

## Scarica e installa

- **Action2Blender-0.1.0-beta.1-universal.apk**: app Android. Concedi il permesso alla fotocamera; telefono e PC devono essere sulla stessa rete Wi-Fi.
- **Action2Blender-addon-0.1.0.zip**: in Blender vai a **Edit > Preferences > Add-ons > Install from Disk**, installa lo ZIP e abilita **Action2Blender**. Se Blender era già aperto, riavvialo. Il pannello è nella **Vista 3D > barra laterale (N) > Action2Blender**.

Seleziona una camera in Blender, avvia la connessione dal pannello e inserisci IP, porta e codice nell'app. Quando compare **Tracking attivo**, premi **Azzera**, scegli la scala, quindi usa **Rec** e **Stop**. Ogni ripresa viene conservata come Action separata sulla stessa camera. In questa beta la scena resta sul monitor di Blender.

## Verifiche e limiti della beta

Il movimento ARCore, il collegamento Wi-Fi e il salvataggio di take reali sono stati provati su Samsung Galaxy S25 Ultra con Android 16 e Blender 5.2. L'APK di release è firmato e la sua firma è stata verificata; la build firmata non è stata reinstallata sul telefono. Gli altri dispositivi compatibili con ARCore devono ancora essere provati. Il collegamento usa IP e codice inseriti a mano; non c'è ancora lo streaming della scena sul telefono.

Codice sorgente: [GitHub](https://github.com/emilius3m/Action2Blender). Licenza del codice originale: MIT.
