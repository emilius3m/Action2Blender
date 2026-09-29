package org.action2blender.action2blender

import org.json.JSONObject
import java.io.File
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.security.MessageDigest
import java.util.Base64
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Gravity-aligned mapping; joystick travel in ARCore world axes. Must match the add-on. */
private const val CAMERA_CONTROL_VERSION = 4

/** Ordered JSON-lines transport. The Blender server requires a pairing token. */
class BridgeClient(
    private val onState: (Boolean, String) -> Unit,
    private val onTakeAcknowledged: (String) -> Unit,
    private val onRecenterAcknowledged: (String) -> Unit,
    private val onCommandError: (String, String) -> Unit,
    private val onRecordingReady: (JSONObject) -> Unit,
    private val onRecordingStarted: (JSONObject) -> Unit,
    private val onRecordingStopped: (JSONObject) -> Unit,
    private val onRecordingResumed: (JSONObject) -> Unit,
    private val onFrameTick: (JSONObject) -> Unit,
) {
    private data class Transfer(val file: File, val id: String, val bytes: ByteArray,
                                val sha256: String)
    private val pendingFiles = ArrayDeque<File>()
    private var activeTransfer: Transfer? = null
    private val writerExecutor = Executors.newSingleThreadExecutor()
    private val scheduler = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var endpoint: Triple<String, Int, String>? = null
    @Volatile private var generation = 0
    @Volatile private var closed = false
    @Volatile private var lastPongAt = 0L
    @Volatile private var clockOffsetNs: Long? = null
    @Volatile private var bestRttNs = Long.MAX_VALUE
    private var reconnectAttempt = 0
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: BufferedWriter? = null
    @Volatile var connected = false
        private set
    @Volatile var viewportPort = 0
        private set
    @Volatile var sessionId = ""
        private set

    init {
        scheduler.scheduleAtFixedRate({
            if (connected) {
                if (System.nanoTime() - lastPongAt > 6_000_000_000L) {
                    socket?.close()
                } else {
                    send(JSONObject().put("type", "ping").put("id", System.nanoTime()))
                }
            }
        }, 2, 2, TimeUnit.SECONDS)
    }

    fun connect(host: String, port: Int, token: String) {
        endpoint = Triple(host, port, token)
        closed = false
        generation += 1
        reconnectAttempt = 0
        val current = generation
        writerExecutor.execute { attemptConnect(host, port, token, current) }
    }

    private fun attemptConnect(host: String, port: Int, token: String, current: Int) {
        if (closed || current != generation) return
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
                if (closed || current != generation) {
                    opened.close()
                    return
                }
                viewportPort = response.optInt("viewport_port", 0).coerceIn(0, 65535)
                sessionId = response.optString("session_id")
                opened.soTimeout = 0
                socket = opened
                writer = output
                connected = true
                activeTransfer = null
                pendingFiles.clear()
                reconnectAttempt = 0
                lastPongAt = System.nanoTime()
                clockOffsetNs = null
                bestRttNs = Long.MAX_VALUE
                onState(true, uiText("Connesso a Blender", "Connected to Blender"))
                Thread({ readReplies(opened, input, current) }, "Action2Blender replies").start()
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
                if (exc.message !in setOf("Pairing failed", "Update the Action2Blender app on your phone",
                        "Update or reload the Action2Blender add-on in Blender")) scheduleReconnect(current)
            }
    }

    private fun scheduleReconnect(current: Int) {
        if (closed || current != generation) return
        val target = endpoint ?: return
        val delay = (1 shl reconnectAttempt.coerceAtMost(4)).coerceAtMost(15).toLong()
        reconnectAttempt += 1
        scheduler.schedule({
            if (!closed && current == generation && !connected) {
                writerExecutor.execute { attemptConnect(target.first, target.second, target.third, current) }
            }
        }, delay, TimeUnit.SECONDS)
    }

    fun send(message: JSONObject) {
        writerExecutor.execute {
            try {
                writeNow(message)
            } catch (exc: Exception) {
                connected = false
                viewportPort = 0
                writer = null
                socket?.close()
                onState(false, uiText("Connessione persa", exc.message ?: "Connection lost"))
            }
        }
    }

    private fun writeNow(message: JSONObject) {
        val output = writer ?: return
        output.write(message.toString() + "\n")
        output.flush()
    }

    fun sendTake(file: File) {
        writerExecutor.execute {
            if (!file.exists() || pendingFiles.any { it.absolutePath == file.absolutePath }) return@execute
            pendingFiles.addLast(file)
            if (activeTransfer == null) startNextTake()
        }
    }

    fun phoneTimeForServer(serverTimeNs: Long): Long {
        val offset = clockOffsetNs
        return if (serverTimeNs > 0 && offset != null) serverTimeNs - offset else System.nanoTime()
    }

    private fun startNextTake() {
        if (!connected || activeTransfer != null) return
        while (pendingFiles.isNotEmpty()) {
            val file = pendingFiles.first()
            if (!file.exists()) { pendingFiles.removeFirst(); continue }
            val bytes = try { file.readBytes() } catch (exc: Exception) {
                pendingFiles.removeFirst()
                onCommandError("take", uiText("Take locale non leggibile", "Could not read the saved take"))
                continue
            }
            if (bytes.size > 64 * 1024 * 1024) {
                pendingFiles.removeFirst()
                onCommandError("take", uiText("Take troppo grande per il trasferimento", "Take exceeds transfer limit"))
                continue
            }
            val id = file.name.removePrefix("pending_").removeSuffix(".json")
            val sha = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it.toInt() and 0xff) }
            activeTransfer = Transfer(file, id, bytes, sha)
            writeNow(JSONObject().put("type", "take_begin").put("id", id)
                .put("size", bytes.size).put("sha256", sha))
            return
        }
    }

    private fun sendChunk(index: Int) {
        val transfer = activeTransfer ?: return
        val offset = index * 48 * 1024
        if (offset >= transfer.bytes.size) {
            writeNow(JSONObject().put("type", "take_end").put("id", transfer.id))
            return
        }
        val end = (offset + 48 * 1024).coerceAtMost(transfer.bytes.size)
        val chunk = transfer.bytes.copyOfRange(offset, end)
        writeNow(JSONObject().put("type", "take_chunk").put("id", transfer.id)
            .put("index", index).put("data", Base64.getEncoder().encodeToString(chunk)))
    }

    private fun readReplies(opened: Socket, input: BufferedReader, current: Int) {
        try {
            while (!opened.isClosed) {
                val line = input.readLine() ?: break
                val message = JSONObject(line)
                when (message.optString("type")) {
                "pong" -> {
                    val received = System.nanoTime()
                    lastPongAt = received
                    val sent = message.optLong("id", 0)
                    val serverTime = message.optLong("server_time_ns", 0)
                    val rtt = received - sent
                    if (sent > 0 && serverTime > 0 && rtt in 1..500_000_000L &&
                        (clockOffsetNs == null || rtt <= bestRttNs * 3 / 2)) {
                        clockOffsetNs = serverTime - (sent + rtt / 2)
                        bestRttNs = minOf(bestRttNs, rtt)
                    }
                }
                "take_next" -> writerExecutor.execute {
                    if (message.optString("id") == activeTransfer?.id) {
                        try { sendChunk(message.optInt("index")) }
                        catch (_: Exception) { socket?.close() }
                    }
                }
                "record_ready" -> onRecordingReady(message)
                "record_started" -> onRecordingStarted(message)
                "record_stopped" -> onRecordingStopped(message)
                "record_resumed" -> onRecordingResumed(message)
                "frame_tick" -> onFrameTick(message)
                "take_saved" -> {
                    onTakeAcknowledged(message.optString("id"))
                    writerExecutor.execute {
                        if (activeTransfer?.id == message.optString("id")) {
                            activeTransfer = null
                            if (pendingFiles.isNotEmpty()) pendingFiles.removeFirst()
                            startNextTake()
                        }
                    }
                }
                "recenter_ok" -> {
                    onRecenterAcknowledged(message.optString("camera"))
                }
                "error" -> {
                    if (message.optString("message_type") in setOf("take_begin", "take_chunk", "take_end", "take")) {
                        writerExecutor.execute { activeTransfer = null; pendingFiles.clear() }
                    }
                    onCommandError(
                        message.optString("message_type"),
                        blenderErrorText(message.optString("message", "Blender rejected a command")),
                    )
                }
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
                scheduleReconnect(current)
            }
            opened.close()
        }
    }

    fun close() {
        closed = true
        generation += 1
        connected = false
        viewportPort = 0
        val opened = socket
        socket = null
        writer = null
        opened?.close()
        writerExecutor.shutdownNow()
        scheduler.shutdownNow()
    }
}
