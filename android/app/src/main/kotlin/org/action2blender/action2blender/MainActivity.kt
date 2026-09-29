package org.action2blender.action2blender

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import android.widget.FrameLayout
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.zxing.integration.android.IntentIntegrator
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/** Flutter UI + native ARCore pose capture. No video or scene data leaves the LAN. */
class MainActivity : FlutterActivity(), GLSurfaceView.Renderer {
    private val sessionLock = Any()
    private val commandLock = Any()
    @Volatile private var session: Session? = null
    @Volatile private var tracking = false
    @Volatile private var surfaceWidth = 1
    @Volatile private var surfaceHeight = 1
    private lateinit var glView: GLSurfaceView
    private lateinit var bridge: BridgeClient
    private lateinit var recorder: TakeRecorder
    private val countdownHandler = Handler(Looper.getMainLooper())
    private val ioExecutor = Executors.newSingleThreadExecutor()
    private var countdownSeconds = 0
    private var countdownRemaining = 0
    private var pendingTakeId: String? = null
    @Volatile private var resumePending = false
    @Volatile private var finalizing = false
    private var currentFrame = 0
    private var lensMm = 50.0
    private var focusDistance = 10.0
    private var fstop = 2.8
    private var recoverableTakes = 0
    private var lastSessionId = ""
    private val navigation = NavigationController()
    private val poseStabilizer = PoseStabilizer()
    private val latestPose = AtomicReference<PhonePose?>()
    private var eventSink: EventChannel.EventSink? = null
    private var installRequested = false
    private var textureId = 0
    private var lastSentAt = 0L
    private var lastStatusAt = 0L
    private var lastRawPose: PhonePose? = null
    private var lastRawAt = 0L
    private var statusText = uiText("Avvio del tracciamento…", "Starting tracking…")
    @Volatile private var bridgeIssue: String? = null
    @Volatile private var recenterPending = false
    private var movementScale = 1.0
    @Volatile private var stabilizationStrength = 0.25f
    @Volatile private var centered = false
    @Volatile private var qrScannerActive = false
    @Volatile private var activityResumed = false
    private var qrResult: MethodChannel.Result? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        recorder = TakeRecorder(filesDir)
        countdownSeconds = getSharedPreferences("action2blender", MODE_PRIVATE)
            .getInt("countdown_seconds", 0).takeIf { it in setOf(0, 3, 5) } ?: 0
        recoverableTakes = filesDir.listFiles { file ->
            file.name.startsWith("pending_") && file.name.endsWith(".json") &&
                runCatching { JSONObject(file.readText()).optBoolean("partial") }.getOrDefault(false)
        }?.size ?: 0
        stabilizationStrength = getSharedPreferences("action2blender", MODE_PRIVATE)
            .getFloat("live_stabilization", 0.25f).coerceIn(0f, 1f)
        bridge = BridgeClient(
            onState = { connected, text ->
                if (connected) {
                    val sameSession = bridge.sessionId == lastSessionId
                    centered = recorder.isPaused() && sameSession
                    if (!sameSession && recorder.isRecording()) {
                        recorder.pause(System.nanoTime())
                        finishRecording(partial = true)
                    } else if (pendingTakeId != null && !recorder.isRecording()) {
                        bridge.send(JSONObject().put("type", "record_cancel").put("id", pendingTakeId))
                        pendingTakeId = null
                        countdownRemaining = 0
                    }
                    lastSessionId = bridge.sessionId
                    recenterPending = false
                    bridgeIssue = null
                    navigation.stop()
                    sendScale()
                    resendPendingTakes()
                } else {
                    resumePending = false
                    if (recorder.pause(System.nanoTime())) {
                        publish(uiText("Rete persa: ripresa in pausa", "Network lost: recording paused"))
                    }
                    centered = false
                    recenterPending = false
                    bridgeIssue = text
                    navigation.stop()
                }
                publish(text)
            },
            onTakeAcknowledged = { id ->
                val file = File(filesDir, "pending_$id.json")
                if (file.exists() && runCatching { JSONObject(file.readText()).optBoolean("partial") }.getOrDefault(false)) {
                    recoverableTakes = (recoverableTakes - 1).coerceAtLeast(0)
                }
                file.delete()
                bridgeIssue = null
                publish(uiText("Take salvata in Blender", "Take saved in Blender"))
            },
            onRecenterAcknowledged = { camera ->
                centered = true
                recenterPending = false
                bridgeIssue = null
                publish(uiText("Camera pronta: $camera", "Camera ready: $camera"))
            },
            onCommandError = { command, message ->
                if (command in setOf("record_prepare", "record_go")) {
                    pendingTakeId = null
                    countdownRemaining = 0
                }
                if (command == "resume") resumePending = false
                if (command !in setOf("take", "record_prepare", "record_go", "record_stop", "resume")) {
                    centered = false
                    recenterPending = false
                }
                val issue = "Blender: $message"
                bridgeIssue = issue
                publish(issue)
            },
            onRecordingReady = { response ->
                val id = response.optString("id")
                if (id == pendingTakeId) {
                    val camera = response.optJSONObject("snapshot")?.optJSONObject("camera")
                    lensMm = camera?.optDouble("lens_mm", 50.0) ?: 50.0
                    focusDistance = camera?.optDouble("focus_distance_bu", 10.0) ?: 10.0
                    fstop = camera?.optDouble("fstop", 2.8) ?: 2.8
                    runOnUiThread { beginCountdown(id) }
                }
            },
            onRecordingStarted = { response ->
                val id = response.optString("id")
                val pose = latestPose.get()
                if (id == pendingTakeId && (!activityResumed || !tracking || pose == null)) {
                    bridge.send(JSONObject().put("type", "record_cancel").put("id", id))
                    pendingTakeId = null
                    countdownRemaining = 0
                    publish(uiText("Avvio ripresa annullato", "Recording start cancelled"))
                } else if (id == pendingTakeId && pose != null) {
                    try {
                        val now = bridge.phoneTimeForServer(response.optLong("server_time_ns"))
                        recorder.start(now, pose, id, response.getJSONObject("snapshot"))
                        currentFrame = response.optInt("frame")
                        recorder.addFrameMarker(now, currentFrame)
                        centered = true
                        publish(uiText("Registrazione e timeline in corso", "Recording with timeline playback"))
                    } catch (exc: Exception) {
                        bridge.send(JSONObject().put("type", "record_cancel").put("id", id))
                        pendingTakeId = null
                        publish(uiText("Impossibile salvare la ripresa sul telefono", "Could not save recording on phone"))
                    }
                }
            },
            onRecordingStopped = { response ->
                val id = response.optString("id")
                if (id == pendingTakeId) {
                    recorder.addFrameMarker(bridge.phoneTimeForServer(response.optLong("server_time_ns")),
                        response.optInt("frame", currentFrame))
                    finishRecording(partial = response.optBoolean("partial"))
                }
            },
            onRecordingResumed = { response ->
                if (resumePending && response.optString("id") == pendingTakeId) {
                    resumePending = false
                    val pose = latestPose.get()
                    val now = bridge.phoneTimeForServer(response.optLong("server_time_ns"))
                    if (pose != null && recorder.resume(now, pose)) {
                        currentFrame = response.optInt("frame", currentFrame)
                        recorder.addFrameMarker(now, currentFrame)
                        publish(uiText("Registrazione ripresa senza salto", "Recording resumed without a jump"))
                    }
                }
            },
            onFrameTick = { response ->
                if (response.optString("id") == pendingTakeId && recorder.isRecording()) {
                    currentFrame = response.optInt("frame")
                    recorder.addFrameMarker(bridge.phoneTimeForServer(response.optLong("server_time_ns")), currentFrame)
                    publish(statusText)
                }
            },
        )
        glView = GLSurfaceView(this).apply {
            setEGLContextClientVersion(2)
            preserveEGLContextOnPause = true
            setRenderer(this@MainActivity)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        findViewById<FrameLayout>(android.R.id.content).addView(
            glView,
            FrameLayout.LayoutParams(2, 2, Gravity.BOTTOM or Gravity.END),
        )
        ioExecutor.execute {
            try {
                recorder.recover().forEach { take ->
                    if (!File(filesDir, "pending_${take.getString("id")}.json").exists()) {
                        recorder.saveRecovered(take)
                    }
                }
                recoverableTakes = filesDir.listFiles { file ->
                    file.name.startsWith("pending_") && file.name.endsWith(".json") &&
                        runCatching { JSONObject(file.readText()).optBoolean("partial") }.getOrDefault(false)
                }?.size ?: 0
                publish(statusText)
            } catch (_: Exception) {
                publish(uiText("Recupero di una take non riuscito", "Could not recover a take"))
            }
        }
    }

    private fun beginCountdown(id: String) {
        countdownRemaining = countdownSeconds
        fun tick() {
            if (pendingTakeId != id) return
            if (!bridge.connected || !tracking || !activityResumed) {
                if (bridge.connected) bridge.send(JSONObject().put("type", "record_cancel").put("id", id))
                pendingTakeId = null
                countdownRemaining = 0
                publish(uiText("Avvio ripresa annullato", "Recording start cancelled"))
                return
            }
            if (countdownRemaining > 0) {
                publish(uiText("Ripresa tra $countdownRemaining…", "Recording in $countdownRemaining…"))
                countdownRemaining -= 1
                countdownHandler.postDelayed({ tick() }, 1000)
            } else {
                val pose = latestPose.get()
                if (pose == null) {
                    bridge.send(JSONObject().put("type", "record_cancel").put("id", id))
                    pendingTakeId = null
                    publish(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                } else {
                    bridge.send(pose.message("record_go").put("id", id))
                    publish(uiText("Avvio timeline…", "Starting timeline…"))
                }
            }
        }
        tick()
    }

    private fun finishRecording(partial: Boolean = false) {
        if (finalizing) return
        finalizing = true
        pendingTakeId = null
        countdownRemaining = 0
        ioExecutor.execute {
            try {
                val take = recorder.stop(partial) ?: return@execute
                val file = File(filesDir, "pending_${take.getString("id")}.json")
                if (partial) recoverableTakes += 1
                if (bridge.connected && !partial) bridge.sendTake(file)
                publish(if (partial) uiText("Take parziale da recuperare", "Partial take ready to recover")
                    else if (bridge.connected) uiText("Invio take a Blender…", "Sending take to Blender…")
                    else uiText("Take conservata sul telefono", "Take kept on phone"))
            } catch (_: Exception) {
                publish(uiText("Salvataggio take non riuscito; diario conservato", "Could not finalize take; journal kept"))
            } finally {
                finalizing = false
            }
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        EventChannel(messenger, "org.action2blender/events").setStreamHandler(object : EventChannel.StreamHandler {
            override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                eventSink = events
                publish(statusText)
            }
            override fun onCancel(arguments: Any?) { eventSink = null }
        })
        MethodChannel(messenger, "org.action2blender/control").setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "getConnectionSettings" -> {
                        val saved = getSharedPreferences("action2blender", MODE_PRIVATE)
                        result.success(mapOf(
                            "host" to saved.getString("connection_host", ""),
                            "port" to saved.getInt("connection_port", 45767),
                            "countdown" to countdownSeconds,
                        ))
                    }
                    "scanQr" -> {
                        if (recorder.isRecording()) error(uiText("Ferma Rec prima di scansionare il QR", "Stop recording before scanning the QR code"))
                        if (qrScannerActive) error(uiText("Lettore QR già aperto", "QR scanner is already open"))
                        qrScannerActive = true
                        try {
                            // ARCore owns the camera while tracking. Release it before opening the scanner.
                            pauseArForQr()
                            qrResult = result
                            publish(uiText("Inquadra il QR mostrato in Blender", "Scan the QR code shown in Blender"))
                            IntentIntegrator(this)
                                .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                                .setPrompt(uiText("Inquadra il QR mostrato in Blender", "Scan the QR code shown in Blender"))
                                .setBeepEnabled(false)
                                .setOrientationLocked(false)
                                .initiateScan()
                        } catch (exc: Exception) {
                            Log.e("Action2BlenderQr", "Scanner could not start", exc)
                            qrResult = null
                            qrScannerActive = false
                            if (activityResumed) startAr()
                            throw exc
                        }
                    }
                    "connect" -> {
                        val host = call.argument<String>("host")?.trim() ?: error(uiText("IP mancante", "IP address missing"))
                        val port = call.argument<Int>("port") ?: error(uiText("Porta mancante", "Port missing"))
                        val token = call.argument<String>("token") ?: error(uiText("Codice mancante", "Pairing code missing"))
                        if (host.isEmpty() || port !in 1..65535) error(uiText("IP o porta non validi", "Invalid IP address or port"))
                        getSharedPreferences("action2blender", MODE_PRIVATE).edit()
                            .putString("connection_host", host)
                            .putInt("connection_port", port)
                            .apply()
                        centered = false
                        recenterPending = false
                        bridgeIssue = null
                        navigation.stop()
                        bridge.connect(host, port, token)
                        publish(uiText("Connessione…", "Connecting…"))
                        result.success(null)
                    }
                    "setScale" -> {
                        movementScale = (call.argument<Double>("value") ?: 1.0).coerceIn(0.1, 10.0)
                        sendScale()
                        result.success(null)
                    }
                    "setCountdown" -> {
                        val value = call.argument<Int>("seconds") ?: 0
                        if (value !in setOf(0, 3, 5)) error(uiText("Conto alla rovescia non valido", "Invalid countdown"))
                        countdownSeconds = value
                        getSharedPreferences("action2blender", MODE_PRIVATE).edit()
                            .putInt("countdown_seconds", value).apply()
                        result.success(null)
                    }
                    "setOptics" -> {
                        val focal = call.argument<Double>("lens") ?: lensMm
                        val focus = call.argument<Double>("focus_distance") ?: focusDistance
                        val aperture = call.argument<Double>("fstop") ?: fstop
                        if (!recorder.isRecording()) error(uiText("Avvia Rec prima di regolare l'obiettivo", "Start Rec before adjusting the lens"))
                        recorder.setOptics(focal, focus, aperture)
                        lensMm = focal
                        focusDistance = focus
                        fstop = aperture
                        bridge.send(JSONObject().put("type", "optics").put("lens", focal)
                            .put("focus_distance", focus).put("fstop", aperture))
                        latestPose.get()?.let { recorder.addSample(System.nanoTime(), it) }
                        publish(statusText)
                        result.success(null)
                    }
                    "sendRecoveredTakes" -> {
                        if (!bridge.connected) error(uiText("Connetti Blender prima di inviare", "Connect to Blender before sending"))
                        filesDir.listFiles { file -> file.name.startsWith("pending_") && file.name.endsWith(".json") }
                            ?.forEach { file ->
                                val take = JSONObject(file.readText())
                                if (take.optBoolean("partial")) bridge.sendTake(file)
                            }
                        result.success(null)
                    }
                    "setStabilization" -> {
                        val value = call.argument<Double>("value") ?: error(uiText("Intensità mancante", "Stabilization strength missing"))
                        if (!value.isFinite() || value !in 0.0..1.0) error(uiText("Intensità non valida", "Invalid stabilization strength"))
                        if (recorder.isRecording()) error(uiText("Ferma Rec prima di cambiare stabilizzazione", "Stop recording before changing stabilization"))
                        stabilizationStrength = value.toFloat()
                        getSharedPreferences("action2blender", MODE_PRIVATE).edit()
                            .putFloat("live_stabilization", stabilizationStrength).apply()
                        publish(if (value == 0.0) uiText("Stabilizzazione live spenta", "Live stabilization off") else uiText("Stabilizzazione live: ${(value * 100).toInt()}%", "Live stabilization: ${(value * 100).toInt()}%"))
                        result.success(null)
                    }
                    "recenter" -> {
                        val tracked = latestPose.get() ?: error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                        if (!bridge.connected || !tracking || recorder.isRecording()) error(uiText("Attendi il tracciamento e connetti Blender", "Wait for tracking and connect to Blender"))
                        if (recenterPending) error(uiText("Attendi la conferma di Blender", "Wait for Blender to confirm"))
                        synchronized(commandLock) {
                            navigation.stop()
                            val pose = navigation.reset(System.nanoTime(), tracked)
                            latestPose.set(pose)
                            centered = false
                            recenterPending = true
                            bridgeIssue = null
                            bridge.send(pose.message("recenter"))
                        }
                        publish(uiText("Attendo conferma della camera da Blender…", "Waiting for Blender to confirm the camera…"))
                        result.success(null)
                    }
                    "createCamera" -> {
                        val tracked = latestPose.get() ?: error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                        if (!bridge.connected || !tracking || recorder.isRecording()) error(uiText("Connetti Blender e attendi il tracciamento", "Connect to Blender and wait for tracking"))
                        if (recenterPending) error(uiText("Attendi la conferma di Blender", "Wait for Blender to confirm"))
                        val mode = call.argument<String>("mode") ?: "view"
                        if (mode != "view" && mode != "subject") error(uiText("Modalità camera non valida", "Invalid camera mode"))
                        synchronized(commandLock) {
                            navigation.stop()
                            val pose = navigation.reset(System.nanoTime(), tracked)
                            latestPose.set(pose)
                            centered = false
                            recenterPending = true
                            bridgeIssue = null
                            bridge.send(pose.message("create_camera").put("mode", mode))
                        }
                        publish(uiText("Blender sta creando la camera…", "Blender is creating the camera…"))
                        result.success(null)
                    }
                    "setNavigation" -> {
                        if (!bridge.connected || !tracking || !centered || recorder.isPaused()) {
                            navigation.stop()
                        } else {
                            navigation.setInput(
                                (call.argument<Double>("moveX") ?: 0.0).toFloat(),
                                (call.argument<Double>("moveY") ?: 0.0).toFloat(),
                                (call.argument<Double>("lookX") ?: 0.0).toFloat(),
                                (call.argument<Double>("lookY") ?: 0.0).toFloat(),
                                (call.argument<Double>("lift") ?: 0.0).toFloat(),
                            )
                        }
                        result.success(null)
                    }
                    "startRecording" -> {
                        val tracked = latestPose.get() ?: error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                        if (!bridge.connected || !tracking) error(uiText("Connetti Blender e attendi ARCore", "Connect to Blender and wait for ARCore"))
                        if (!centered) error(uiText("Premi Azzera prima di registrare", "Press Recenter before recording"))
                        if (recorder.isRecording() || pendingTakeId != null || finalizing) error(uiText("Ripresa già in corso", "Recording already in progress"))
                        synchronized(commandLock) {
                            navigation.stop()
                            val now = System.nanoTime()
                            val pose = navigation.reset(now, tracked)
                            latestPose.set(pose)
                            val id = UUID.randomUUID().toString()
                            pendingTakeId = id
                            bridge.send(pose.message("record_prepare").put("id", id).put("scale", movementScale))
                        }
                        publish(uiText("Preparazione ripresa…", "Preparing recording…"))
                        result.success(null)
                    }
                    "stopRecording" -> {
                        val id = pendingTakeId ?: error(uiText("Nessuna ripresa attiva", "No active recording"))
                        if (!recorder.isRecording()) {
                            if (bridge.connected) bridge.send(JSONObject().put("type", "record_cancel").put("id", id))
                            pendingTakeId = null
                            countdownRemaining = 0
                            publish(uiText("Avvio ripresa annullato", "Recording start cancelled"))
                        } else if (bridge.connected) {
                            bridge.send(JSONObject().put("type", "record_stop").put("id", id))
                            publish(uiText("Arresto timeline…", "Stopping timeline…"))
                        } else {
                            finishRecording(partial = true)
                        }
                        result.success(id)
                    }
                    "resumeRecording" -> {
                        if (!bridge.connected || !centered) error(uiText("Ricollega Blender prima di riprendere", "Reconnect Blender before resuming"))
                        val id = pendingTakeId ?: error(uiText("Nessuna ripresa attiva", "No active recording"))
                        if (!recorder.isPaused() || resumePending) error(uiText("La take non è in pausa", "The take is not paused"))
                        val tracked = latestPose.get() ?: error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                        synchronized(commandLock) {
                            navigation.stop()
                            val now = System.nanoTime()
                            val pose = navigation.reset(now, tracked)
                            latestPose.set(pose)
                            if (!tracking) error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                            resumePending = true
                            bridge.send(pose.message("resume").put("id", id))
                        }
                        publish(uiText("Riavvio timeline…", "Resuming timeline…"))
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            } catch (exc: Exception) {
                result.error("ACTION2BLENDER", exc.message ?: uiText("Errore", "Error"), null)
            }
        }
    }

    private fun publish(text: String) {
        statusText = text
        runOnUiThread {
            eventSink?.success(mapOf(
                "status" to statusText,
                "tracking" to tracking,
                "connected" to bridge.connected,
                "centered" to centered,
                "recenterPending" to recenterPending,
                "cameraError" to (bridgeIssue != null),
                "viewportPort" to bridge.viewportPort,
                "recording" to recorder.isRecording(),
                "paused" to recorder.isPaused(),
                "stabilization" to stabilizationStrength.toDouble(),
                "countdown" to countdownRemaining,
                "countdownSetting" to countdownSeconds,
                "preparing" to (pendingTakeId != null && !recorder.isRecording()),
                "frame" to currentFrame,
                "lens" to lensMm,
                "focusDistance" to focusDistance,
                "fstop" to fstop,
                "recoverableTakes" to recoverableTakes,
            ))
        }
    }

    private fun sendScale() {
        if (bridge.connected) bridge.send(JSONObject().put("type", "scale").put("value", movementScale))
    }

    private fun resendPendingTakes() {
        filesDir.listFiles { file -> file.name.startsWith("pending_") && file.name.endsWith(".json") }
            ?.sortedBy { it.name }
            ?.forEach { file ->
                try {
                    val take = JSONObject(file.readText())
                    if (!take.optBoolean("partial")) bridge.sendTake(file)
                }
                catch (_: Exception) { publish(uiText("Una take salvata non può essere letta", "A saved take could not be read")) }
            }
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        if (!qrScannerActive) startAr()
    }

    private fun pauseArForQr() {
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        tracking = false
        navigation.stop()
        if (::glView.isInitialized) glView.onPause()
        synchronized(sessionLock) { session?.pause() }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != IntentIntegrator.REQUEST_CODE || !qrScannerActive) return
        val scanned = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        qrScannerActive = false
        val pending = qrResult
        qrResult = null
        if (activityResumed) startAr()
        pending?.success(scanned?.contents)
    }

    private fun startAr() {
        if (!::glView.isInitialized) return
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 7)
            return
        }
        try {
            if (session == null) {
                when (ArCoreApk.getInstance().requestInstall(this, !installRequested)) {
                    ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                        installRequested = true
                        return
                    }
                    ArCoreApk.InstallStatus.INSTALLED -> session = Session(this)
                }
            }
            synchronized(sessionLock) { session?.resume() }
            glView.onResume()
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            publish(uiText("Muovi lentamente il telefono per iniziare il tracciamento", "Move the phone slowly to start tracking"))
        } catch (exc: Exception) {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            publish(uiText("ARCore non disponibile", "ARCore unavailable"))
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 7 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startAr()
        else publish(uiText("Autorizza la fotocamera per usare ARCore", "Allow camera access to use ARCore"))
    }

    override fun onPause() {
        activityResumed = false
        if (recorder.pause(System.nanoTime())) bridge.send(JSONObject().put("type", "pause"))
        pauseArForQr()
        super.onPause()
    }

    override fun onDestroy() {
        bridge.close()
        ioExecutor.execute { recorder.close() }
        ioExecutor.shutdown()
        synchronized(sessionLock) { session?.close(); session = null }
        super.onDestroy()
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        val ids = IntArray(1)
        GLES20.glGenTextures(1, ids, 0)
        textureId = ids[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glClearColor(0f, 0f, 0f, 1f)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        surfaceWidth = width
        surfaceHeight = height
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        val current = session ?: return
        val now = System.nanoTime()
        try {
            val rawPose = synchronized(sessionLock) {
                current.setCameraTextureName(textureId)
                current.setDisplayGeometry(windowManager.defaultDisplay.rotation, surfaceWidth, surfaceHeight)
                val camera = current.update().camera
                if (camera.trackingState != TrackingState.TRACKING) null else {
                    val position = FloatArray(3)
                    val orientation = FloatArray(4)
                    val pose = camera.displayOrientedPose
                    pose.getTranslation(position, 0)
                    pose.getRotationQuaternion(orientation, 0)
                    PhonePose(position, orientation)
                }
            }
            val wasTracking = tracking
            tracking = rawPose != null
            if (rawPose == null) {
                navigation.stop()
                if (recorder.pause(now)) {
                    bridge.send(JSONObject().put("type", "pause"))
                    publish(uiText("Tracciamento perso: take in pausa. Quando ritorna premi Riprendi", "Tracking lost: take paused. Press Resume when it returns"))
                } else if (now - lastStatusAt > 1_000_000_000L) {
                    lastStatusAt = now
                    publish(bridgeIssue ?: if (recenterPending) uiText("Attendo conferma da Blender…", "Waiting for Blender…") else uiText("In attesa del tracciamento ARCore", "Waiting for ARCore tracking"))
                }
                return
            }
            synchronized(commandLock) {
                val previousRaw = lastRawPose
                val abrupt = previousRaw != null &&
                    rawPose.hasAbruptChangeFrom(previousRaw, (now - lastRawAt) / 1_000_000_000.0)
                val recovered = !wasTracking && previousRaw != null
                val filteredPose = if (abrupt || recovered) poseStabilizer.reset(now, rawPose)
                    else poseStabilizer.update(now, rawPose, stabilizationStrength)
                var phonePose = navigation.advance(now, filteredPose)
                if (!recorder.isPaused() && (abrupt || recovered)) {
                    navigation.stop()
                    phonePose = navigation.reset(now, phonePose)
                    if (abrupt) recorder.rebase(now, phonePose)
                    if (bridge.connected) bridge.send(phonePose.message("resume"))
                    if (abrupt) publish(uiText("Tracciamento corretto senza salto", "Tracking corrected without a jump"))
                }
                lastRawPose = rawPose
                lastRawAt = now
                latestPose.set(phonePose)
                if (!abrupt) recorder.addSample(now, phonePose)
                if (bridge.connected && !recorder.isPaused() && now - lastSentAt > 50_000_000L) {
                    lastSentAt = now
                    bridge.send(phonePose.message("pose"))
                }
            }
            if (now - lastStatusAt > 1_000_000_000L && !recorder.isPaused()) {
                lastStatusAt = now
                publish(bridgeIssue ?: if (recenterPending) uiText("Attendo conferma da Blender…", "Waiting for Blender…") else if (recorder.isRecording()) uiText("Rec: tracciamento attivo", "Rec: tracking active") else uiText("Tracciamento attivo", "Tracking active"))
            }
        } catch (exc: Exception) {
            tracking = false
            if (now - lastStatusAt > 1_000_000_000L) {
                lastStatusAt = now
                publish(uiText("Errore ARCore", "ARCore error"))
            }
        }
    }
}
