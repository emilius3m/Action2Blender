package org.action2blender.action2blender

import java.util.Locale

internal fun uiText(italian: String, english: String): String =
    if (Locale.getDefault().language == "it") italian else english

/** Blender's panel speaks English; translate its known protocol errors for Italian phones. */
internal fun blenderErrorText(message: String): String = uiText(
    when (message) {
        "Pairing failed" -> "Abbinamento non riuscito"
        "Update the Action2Blender app on your phone" -> "Aggiorna l'app Action2Blender sul telefono"
        "Select an object in the Blender scene" -> "Seleziona un oggetto nella scena di Blender"
        "Switch Blender to Perspective View before creating the camera" -> "Passa alla vista Prospettiva in Blender prima di creare la camera"
        "Wait for the take to be saved before creating a camera" -> "Attendi che la take sia salvata prima di creare una camera"
        "Select a camera in the Action2Blender panel" -> "Scegli una camera nel pannello Action2Blender"
        "The camera has a parent object; choose a free camera" -> "La camera ha un oggetto padre: scegline una libera"
        "The camera has active constraints; disable them or choose a free camera" -> "La camera ha vincoli attivi: disattivali o scegli una camera libera"
        "Press Recenter before recording" -> "Premi Azzera prima di registrare"
        "No recording start received" -> "Inizio registrazione non ricevuto"
        "Blender did not confirm the command" -> "Blender non ha confermato il comando"
        "Invalid movement scale" -> "Scala del movimento non valida"
        "Invalid camera placement mode" -> "Modalità camera non valida"
        "Invalid take length" -> "Durata della take non valida"
        "Invalid take ID" -> "Identificativo della take non valido"
        "Message too large" -> "Messaggio troppo grande"
        "Unknown message type" -> "Comando sconosciuto"
        "Take has no tracked samples" -> "La take non contiene campioni validi"
        else -> "Blender ha rifiutato il comando"
    },
    message,
)
