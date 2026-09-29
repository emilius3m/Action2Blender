# Action2Blender

Usa un telefono Android come camera virtuale per Blender: muovi l'inquadratura a mano libera o con i comandi sullo schermo, guarda l'anteprima sul telefono e registra ogni ripresa come take separata.

> **Quale versione installare:** questa guida descrive l'app **0.2.0-dev+11** insieme all'add-on Blender **0.2.3**. Sono pacchetti locali di sviluppo e **non sono ancora disponibili nella pagina Releases di GitHub**. La release pubblica 0.1.1 è precedente e non va abbinata a questi pacchetti.

## Occorrente

- Blender 5.2 (provato con 5.2.1) su un PC e un telefono Android compatibile con ARCore.
- PC e telefono sulla stessa rete locale, con il traffico consentito dal firewall del PC.
- I due pacchetti della versione indicata sopra: lo ZIP dell'add-on e l'APK Android. Nel checkout locale si trovano rispettivamente in `dist/Action2Blender-addon-0.2.3-dev.zip` e `build/app/outputs/flutter-apk/app-release.apk`. La cartella `build/` viene generata compilando l'app e non è inclusa nel codice su GitHub.

## Installazione

1. In Blender apri **Edit → Preferences → Add-ons → Install from Disk**, scegli lo ZIP dell'add-on e abilita **Action2Blender**. Il pannello appare nella **Vista 3D → barra laterale (N) → Action2Blender**. Se Blender era già aperto con una versione precedente, salva la scena e ricarica l'add-on o riavvia Blender.
2. Installa l'APK sul telefono, apri **Action2Blender** e concedi l'accesso alla fotocamera. Android potrebbe chiedere di installare o aggiornare i servizi AR di Google.

Se Android rifiuta l'aggiornamento perché l'app esistente ha una firma diversa, **non disinstallarla finché hai take non ancora confermate da Blender**: i file in attesa sono conservati nell'area privata dell'app.

## Collega il telefono

1. Apri la scena in Blender. Per partire da una camera esistente, sceglila nel campo **Camera** del pannello Action2Blender. Puoi anche creare una camera dall'app dopo il collegamento.
2. Nel pannello, scegli se mantenere **Inquadratura 16:9**: è attiva per impostazione predefinita e modifica la risoluzione della scena quando avvii la connessione. Premi **Start phone connection**. Blender mostra un QR, l'IP del PC, la porta e un codice di abbinamento.
3. Nell'app premi **Scansiona QR di Blender**. Il lettore è incluso nell'app: non serve uno scanner esterno. Se non riesci a leggere il QR, inserisci IP, porta e codice nei campi dell'app e premi **Connetti**. Se il PC ha più connessioni di rete, controlla che l'IP mostrato da Blender sia quello raggiungibile dal telefono.
4. Attendi **Tracking attivo**. Per usare la camera esistente premi **Azzera**: la sua posizione attuale diventa il punto di partenza. In alternativa, usa **Nuova camera → Dalla vista 3D di Blender** oppure **Inquadra oggetto selezionato**. Attendi la conferma **Camera pronta** prima di registrare.

## Muovi e registra la camera

- Muovi e ruota il telefono per spostare la camera. I controlli **Sposta**, **Ruota** e salita/discesa aggiungono movimento virtuale. Regola **Scala** e **Stabilizzazione live** prima di premere Rec. In orizzontale l'anteprima occupa lo schermo, con i comandi sopra il video.
- Premi **Rec** per iniziare e **Stop** per terminare. La take compare nell'elenco **Recorded takes** in Blender. Con **Stabilizza dopo Stop** attivo, l'add-on conserva sia l'Action originale sia una versione stabilizzata. Seleziona la take desiderata nel pannello e salva il file `.blend` per conservarla nel progetto.
- Se ARCore perde il tracciamento o l'app va in pausa, la take si sospende; quando il tracking torna, premi **Riprendi senza salto**. Durante la sessione ARCore attiva lo schermo resta acceso senza doverlo toccare. Dopo **Stop**, la take rimane sul telefono fino alla conferma di Blender; se il Wi-Fi si interrompe, viene ritrasmessa alla riconnessione. Potrebbe essere necessario premere di nuovo **Azzera**.

## Se qualcosa non funziona

| Problema | Controllo rapido |
| --- | --- |
| Il telefono non si collega | Verifica che PC e telefono siano sulla stessa rete, controlla l'IP nel pannello Blender e consenti la connessione nel firewall della rete privata. |
| Il QR non viene letto | Usa **Scansiona QR di Blender** dentro Action2Blender, concedi il permesso alla fotocamera oppure inserisci IP, porta e codice a mano. |
| La camera non si muove o Rec è disabilitato | Attendi il tracking e **Camera pronta**. Se usi una camera esistente, sceglila nel pannello e premi **Azzera**. La camera non deve avere un oggetto padre o vincoli attivi. |
| L'anteprima non arriva | Tieni aperta una Vista 3D in Blender e controlla il firewall: l'anteprima usa una seconda porta locale oltre alla porta di collegamento. |
| Dopo Stop la take non compare | Aspetta la conferma di salvataggio in Blender e controlla il messaggio nell'app. Non disinstallare l'app finché una take è in attesa. |

Questa build locale non è ancora stata provata sul telefono con tutte le funzioni recenti. Per lo stato delle verifiche e per riprendere lo sviluppo, vedi [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md). Il codice originale è distribuito con [licenza MIT](LICENSE); le dipendenze mantengono le rispettive licenze.
