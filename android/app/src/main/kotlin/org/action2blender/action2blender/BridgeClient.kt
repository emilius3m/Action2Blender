package org.action2blender.action2blender

import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors

/** Gravity-aligned mapping; joystick travel in ARCore world axes. Must match the add-on. */
private const val CAMERA_CONTROL_VERSION = 3

/** Ordered JSON-lines transport. The Blender server requires a pairing token. */
class BridgeClient(
    private val onState: (Boolean, String) -> Unit,
    private val onTakeAcknowledged: (String) -> Unit,
    private val onRecenterAcknowledged: (String) -> Unit,
    private val onCommandError: (String, String) -> Unit,
) {
    private val writerExecutor = Executors.newSingleThreadExecutor()
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: BufferedWriter? = null
    @Volatile var connected = false
        private set
    @Volatile var viewportPort = 0
        private set

    fun connect(host: String, port: Int, token: String) {
        writerExecutor.execute {
            try {
                socket?.close()
                connected = false
                viewportPort = 0
                val opened = Socket()
                opened.connect(InetSocketAddress(host, port), 5000)
                opened.soTimeout = 10000
                val input = BufferedReader(InputStreamReader(opened.getInputStream(), Charsets.UTF_8))
                val output = BufferedWriter(OutputStreamWriter(opened.getOutputStream(), Charsets.UTF_8))
                val hello = JSONObject().put("type", "hello").put("version", 1).put("token", token)
                    .put("camera_control", CAMERA_CONTROL_VERSION)
                output.write(hello.toString() + "\n")
                output.flush()
                val response = JSONObject(input.readLine() ?: error("Blender closed the connection"))
                if (response.optString("type") != "hello_ok") {
                    opened.close()
                    error(response.optString("message").ifEmpty { "Pairing failed" })
                }
                if (response.optInt("camera_control", 0) != CAMERA_CONTROL_VERSION) {
                    opened.close()
                    error("Update or reload the Action2Blender add-on in Blender")
                }
                viewportPort = response.optInt("viewport_port", 0).coerceIn(0, 65535)
                opened.soTimeout = 0
                socket = opened
                writer = output
                connected = true
                onState(true, uiText("Connesso a Blender", "Connected to Blender"))
                Thread({ readReplies(opened, input) }, "Action2Blender replies").start()
            } catch (exc: Exception) {
                connected = false
                viewportPort = 0
                writer = null
                onState(false, uiText(
                    when (exc.message) {
                        "Pairing failed" -> "Abbinamento non riuscito"
                        "Update the Action2Blender app on your phone" -> "Aggiorna l'app Action2Blender sul telefono"
                        "Update or reload the Action2Blender add-on in Blender" -> "Aggiorna o ricarica l'add-on Action2Blender in Blender"
                        else -> "Connessione a Blender non riuscita"
                    },
                    exc.message ?: "Connection failed",
                ))
            }
        }
    }

    fun send(message: JSONObject) {
        writerExecutor.execute {
            try {
                val output = writer ?: return@execute
                output.write(message.toString() + "\n")
                output.flush()
            } catch (exc: Exception) {
                connected = false
                viewportPort = 0
                writer = null
                socket?.close()
                onState(false, uiText("Connessione persa", exc.message ?: "Connection lost"))
            }
        }
    }

    private fun readReplies(opened: Socket, input: BufferedReader) {
        try {
            while (!opened.isClosed) {
                val line = input.readLine() ?: break
                val message = JSONObject(line)
                if (message.optString("type") == "take_saved") {
                    onTakeAcknowledged(message.optString("id"))
                } else if (message.optString("type") == "recenter_ok") {
                    onRecenterAcknowledged(message.optString("camera"))
                } else if (message.optString("type") == "error") {
                    onCommandError(
                        message.optString("message_type"),
                        blenderErrorText(message.optString("message", "Blender rejected a command")),
                    )
                }
            }
        } catch (_: Exception) {
            // A closed socket is reported below.
        } finally {
            if (socket === opened) {
                connected = false
                viewportPort = 0
                writer = null
                socket = null
                onState(false, uiText("Connessione chiusa", "Connection closed"))
            }
            opened.close()
        }
    }

    fun close() {
        connected = false
        viewportPort = 0
        socket?.close()
        writerExecutor.shutdownNow()
    }
}
