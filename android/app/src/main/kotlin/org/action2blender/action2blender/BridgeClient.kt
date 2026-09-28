package org.action2blender.action2blender

import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors

/** Ordered JSON-lines transport. The Blender server requires a pairing token. */
class BridgeClient(
    private val onState: (Boolean, String) -> Unit,
    private val onTakeAcknowledged: (String) -> Unit,
) {
    private val writerExecutor = Executors.newSingleThreadExecutor()
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: BufferedWriter? = null
    @Volatile var connected = false
        private set

    fun connect(host: String, port: Int, token: String) {
        writerExecutor.execute {
            try {
                socket?.close()
                connected = false
                val opened = Socket()
                opened.connect(InetSocketAddress(host, port), 5000)
                opened.soTimeout = 10000
                val input = BufferedReader(InputStreamReader(opened.getInputStream(), Charsets.UTF_8))
                val output = BufferedWriter(OutputStreamWriter(opened.getOutputStream(), Charsets.UTF_8))
                val hello = JSONObject().put("type", "hello").put("version", 1).put("token", token)
                output.write(hello.toString() + "\n")
                output.flush()
                val response = JSONObject(input.readLine() ?: error("Blender closed the connection"))
                if (response.optString("type") != "hello_ok") error("Pairing code rejected")
                opened.soTimeout = 0
                socket = opened
                writer = output
                connected = true
                onState(true, "Connected to Blender")
                Thread({ readReplies(opened, input) }, "Action2Blender replies").start()
            } catch (exc: Exception) {
                connected = false
                writer = null
                onState(false, exc.message ?: "Connection failed")
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
                writer = null
                socket?.close()
                onState(false, exc.message ?: "Connection lost")
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
                } else if (message.optString("type") == "error") {
                    onState(connected, message.optString("message", "Blender rejected a message"))
                }
            }
        } catch (_: Exception) {
            // A closed socket is reported below.
        } finally {
            if (socket === opened) {
                connected = false
                writer = null
                socket = null
                onState(false, "Connection closed")
            }
            opened.close()
        }
    }

    fun close() {
        connected = false
        socket?.close()
        writerExecutor.shutdownNow()
    }
}
