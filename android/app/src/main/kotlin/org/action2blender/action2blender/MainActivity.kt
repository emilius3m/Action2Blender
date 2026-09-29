package org.action2blender.action2blender

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
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
    private val recorder = TakeRecorder()
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
        stabilizationStrength = getSharedPreferences("action2blender", MODE_PRIVATE)
            .getFloat("live_stabilization", 0.25f).coerceIn(0f, 1f)
        bridge = BridgeClient(
            onState = { connected, text ->
                if (connected) {
                    centered = false
                    recenterPending = false
                    bridgeIssue = null
                    navigation.stop()
                    sendScale()
                    resendPendingTakes()
                } else {
                    centered = false
                    recenterPending = false
                    bridgeIssue = text
                    navigation.stop()
                }
                publish(text)
            },
            onTakeAcknowledged = { id ->
                File(filesDir, "pending_$id.json").delete()
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
                if (command != "take") {
                    centered = false
                    recenterPending = false
                }
                val issue = "Blender: $message"
                bridgeIssue = issue
                publish(issue)
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
                        synchronized(commandLock) {
                            navigation.stop()
                            val now = System.nanoTime()
                            val pose = navigation.reset(now, tracked)
                            latestPose.set(pose)
                            recorder.start(now, pose)
                            bridge.send(pose.message("record_start").put("scale", movementScale))
                        }
                        publish(uiText("Registrazione in corso", "Recording in progress"))
                        result.success(null)
                    }
                    "stopRecording" -> {
                        val take = recorder.stop() ?: error(uiText("Nessuna ripresa attiva", "No active recording"))
                        val id = take.getString("id")
                        File(filesDir, "pending_$id.json").writeText(take.toString())
                        if (bridge.connected) bridge.send(take)
                        publish(if (bridge.connected) uiText("Invio take a Blender…", "Sending take to Blender…") else uiText("Take salvata sul telefono; riconnettiti", "Take saved on phone; reconnect"))
                        result.success(id)
                    }
                    "resumeRecording" -> {
                        val tracked = latestPose.get() ?: error(uiText("Tracciamento non disponibile", "Tracking unavailable"))
                        synchronized(commandLock) {
                            navigation.stop()
                            val now = System.nanoTime()
                            val pose = navigation.reset(now, tracked)
                            latestPose.set(pose)
                            if (!tracking || !recorder.resume(now, pose)) error(uiText("La take non è in pausa", "The take is not paused"))
                            if (bridge.connected) bridge.send(pose.message("resume"))
                        }
                        publish(uiText("Registrazione ripresa senza salto", "Recording resumed without a jump"))
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
                try { bridge.send(JSONObject(file.readText())) }
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
