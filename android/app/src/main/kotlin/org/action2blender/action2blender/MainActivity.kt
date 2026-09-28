package org.action2blender.action2blender

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.Gravity
import android.widget.FrameLayout
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
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
    @Volatile private var session: Session? = null
    @Volatile private var tracking = false
    @Volatile private var surfaceWidth = 1
    @Volatile private var surfaceHeight = 1
    private lateinit var glView: GLSurfaceView
    private lateinit var bridge: BridgeClient
    private val recorder = TakeRecorder()
    private val latestPose = AtomicReference<PhonePose?>()
    private var eventSink: EventChannel.EventSink? = null
    private var installRequested = false
    private var textureId = 0
    private var lastSentAt = 0L
    private var lastStatusAt = 0L
    private var statusText = "Avvio del tracciamento…"
    private var movementScale = 1.0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        bridge = BridgeClient(
            onState = { connected, text ->
                publish(text)
                if (connected) {
                    sendScale()
                    resendPendingTakes()
                }
            },
            onTakeAcknowledged = { id ->
                File(filesDir, "pending_$id.json").delete()
                publish("Take salvata in Blender")
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
                    "connect" -> {
                        val host = call.argument<String>("host") ?: error("IP mancante")
                        val port = call.argument<Int>("port") ?: error("Porta mancante")
                        val token = call.argument<String>("token") ?: error("Codice mancante")
                        bridge.connect(host, port, token)
                        publish("Connessione…")
                        result.success(null)
                    }
                    "setScale" -> {
                        movementScale = (call.argument<Double>("value") ?: 1.0).coerceIn(0.1, 10.0)
                        sendScale()
                        result.success(null)
                    }
                    "recenter" -> {
                        val pose = latestPose.get() ?: error("Tracking non disponibile")
                        if (!bridge.connected || recorder.isRecording()) error("Ferma Rec e connetti Blender")
                        bridge.send(pose.message("recenter"))
                        publish("Camera riallineata")
                        result.success(null)
                    }
                    "startRecording" -> {
                        val pose = latestPose.get() ?: error("Tracking non disponibile")
                        if (!bridge.connected || !tracking) error("Connetti Blender e attendi ARCore")
                        recorder.start(System.nanoTime(), pose)
                        bridge.send(pose.message("record_start"))
                        publish("Registrazione in corso")
                        result.success(null)
                    }
                    "stopRecording" -> {
                        val take = recorder.stop() ?: error("Nessuna ripresa attiva")
                        val id = take.getString("id")
                        File(filesDir, "pending_$id.json").writeText(take.toString())
                        if (bridge.connected) bridge.send(take)
                        publish(if (bridge.connected) "Invio take a Blender…" else "Take salvata sul telefono; riconnettiti")
                        result.success(id)
                    }
                    "resumeRecording" -> {
                        val pose = latestPose.get() ?: error("Tracking non disponibile")
                        if (!tracking || !recorder.resume(System.nanoTime(), pose)) error("La take non è in pausa")
                        if (bridge.connected) bridge.send(pose.message("resume"))
                        publish("Registrazione ripresa senza salto")
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            } catch (exc: Exception) {
                result.error("ACTION2BLENDER", exc.message ?: "Errore", null)
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
                "recording" to recorder.isRecording(),
                "paused" to recorder.isPaused(),
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
                catch (_: Exception) { publish("Una take salvata non può essere letta") }
            }
    }

    override fun onResume() {
        super.onResume()
        startAr()
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
            publish("Muovi lentamente il telefono per iniziare il tracciamento")
        } catch (exc: Exception) {
            publish("ARCore non disponibile: ${exc.message}")
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 7 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startAr()
        else publish("Autorizza la fotocamera per usare ARCore")
    }

    override fun onPause() {
        if (recorder.pause(System.nanoTime())) bridge.send(JSONObject().put("type", "pause"))
        if (::glView.isInitialized) glView.onPause()
        synchronized(sessionLock) { session?.pause() }
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
            val phonePose = synchronized(sessionLock) {
                current.setCameraTextureName(textureId)
                current.setDisplayGeometry(windowManager.defaultDisplay.rotation, surfaceWidth, surfaceHeight)
                val camera = current.update().camera
                if (camera.trackingState != TrackingState.TRACKING) null else {
                    val position = FloatArray(3)
                    val orientation = FloatArray(4)
                    camera.displayOrientedPose.getTranslation(position, 0)
                    camera.displayOrientedPose.getRotationQuaternion(orientation, 0)
                    PhonePose(position, orientation)
                }
            }
            tracking = phonePose != null
            if (phonePose == null) {
                if (recorder.pause(now)) {
                    bridge.send(JSONObject().put("type", "pause"))
                    publish("Tracking perso: take in pausa. Quando ritorna premi Riprendi")
                } else if (now - lastStatusAt > 1_000_000_000L) {
                    lastStatusAt = now
                    publish("In attesa del tracciamento ARCore")
                }
                return
            }
            latestPose.set(phonePose)
            recorder.addSample(now, phonePose)
            if (bridge.connected && !recorder.isPaused() && now - lastSentAt > 50_000_000L) {
                lastSentAt = now
                bridge.send(phonePose.message("pose"))
            }
            if (now - lastStatusAt > 1_000_000_000L && !recorder.isPaused()) {
                lastStatusAt = now
                publish(if (recorder.isRecording()) "Rec: tracking attivo" else "Tracking attivo")
            }
        } catch (exc: Exception) {
            tracking = false
            if (now - lastStatusAt > 1_000_000_000L) {
                lastStatusAt = now
                publish("ARCore: ${exc.message}")
            }
        }
    }
}
