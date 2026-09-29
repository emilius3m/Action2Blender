package org.action2blender.action2blender

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.max
import kotlin.math.sqrt

data class PhonePose(
    val position: FloatArray,
    val rotation: FloatArray,
    val navigation: NavigationPose = NavigationPose.zero(),
) {
    fun hasAbruptChangeFrom(previous: PhonePose, elapsedSeconds: Double): Boolean {
        if (elapsedSeconds <= 0.0 || elapsedSeconds > 0.5) return false
        val distance = sqrt(position.indices.sumOf { index ->
            val delta = (position[index] - previous.position[index]).toDouble()
            delta * delta
        })
        val dot = abs(rotation.indices.sumOf { index ->
            rotation[index].toDouble() * previous.rotation[index].toDouble()
        }).coerceIn(0.0, 1.0)
        val angleDegrees = Math.toDegrees(2.0 * acos(dot))
        return distance > max(0.15, elapsedSeconds * 3.0) ||
            angleDegrees > max(45.0, elapsedSeconds * 360.0)
    }

    fun message(type: String, timeSeconds: Double? = null): JSONObject = JSONObject().apply {
        put("type", type)
        if (type == "sample" || type == "rebase") put("kind", type)
        if (timeSeconds != null) put("t", timeSeconds)
        put("p", JSONArray(position.map { it.toDouble() }))
        put("q", JSONArray(rotation.map { it.toDouble() }))
        put("v", JSONArray(navigation.translation.map { it.toDouble() }))
        put("look", JSONArray(navigation.look.map { it.toDouble() }))
    }
}

/** Keeps every measured pose locally until Blender acknowledges the complete take. */
class TakeRecorder(directory: File) {
    private val journal = TakeJournal(directory)
    private val events = mutableListOf<JSONObject>()
    private val frameMarkers = mutableListOf<JSONObject>()
    private var id = ""
    private var snapshot = JSONObject()
    private var lens = 50.0
    private var focusDistance = 10.0
    private var fstop = 2.8
    private var startedAt = 0L
    private var pausedAt = 0L
    private var pausedDuration = 0L
    private var active = false
    private var waitingForResume = false

    @Synchronized fun isRecording(): Boolean = active
    @Synchronized fun isPaused(): Boolean = waitingForResume

    @Synchronized fun start(now: Long, pose: PhonePose, takeId: String = UUID.randomUUID().toString(),
                            takeSnapshot: JSONObject = JSONObject()) {
        events.clear()
        frameMarkers.clear()
        id = takeId
        snapshot = takeSnapshot
        val camera = snapshot.optJSONObject("camera")
        lens = camera?.optDouble("lens_mm", 50.0) ?: 50.0
        focusDistance = camera?.optDouble("focus_distance_bu", 10.0) ?: 10.0
        fstop = camera?.optDouble("fstop", 2.8) ?: 2.8
        startedAt = now
        pausedAt = 0L
        pausedDuration = 0L
        journal.start(id, snapshot)
        active = true
        waitingForResume = false
        addSample(now, pose)
    }

    @Synchronized fun addSample(now: Long, pose: PhonePose) {
        if (active && !waitingForResume) {
            val event = withOptics(pose.message("sample", elapsed(now)))
            events.add(event)
            journal.append("sample", event)
        }
    }

    private fun withOptics(event: JSONObject): JSONObject = event
        .put("lens", lens).put("focus_distance", focusDistance).put("fstop", fstop)

    @Synchronized fun setOptics(focal: Double, focus: Double, aperture: Double) {
        require(focal.isFinite() && focal in 1.0..500.0)
        require(focus.isFinite() && focus in 0.01..100000.0)
        require(aperture.isFinite() && aperture in 0.1..64.0)
        lens = focal
        focusDistance = focus
        fstop = aperture
    }

    @Synchronized fun addFrameMarker(now: Long, frame: Int) {
        if (!active || waitingForResume) return
        if (frameMarkers.isNotEmpty() && frame <= frameMarkers.last().getInt("frame")) return
        val marker = JSONObject().put("frame", frame).put("t", elapsed(now))
        frameMarkers.add(marker)
        journal.append("frame", marker)
    }

    @Synchronized fun pause(now: Long): Boolean {
        if (!active || waitingForResume) return false
        waitingForResume = true
        pausedAt = now
        journal.append("pause", JSONObject().put("t", elapsed(now)), true)
        return true
    }

    @Synchronized fun resume(now: Long, pose: PhonePose): Boolean {
        if (!active || !waitingForResume) return false
        pausedDuration += now - pausedAt
        waitingForResume = false
        val rebase = withOptics(pose.message("rebase", elapsed(now)))
        events.add(rebase)
        journal.append("sample", rebase, true)
        addSample(now, pose)
        return true
    }

    @Synchronized fun rebase(now: Long, pose: PhonePose) {
        if (!active || waitingForResume) return
        val rebase = withOptics(pose.message("rebase", elapsed(now)))
        events.add(rebase)
        journal.append("sample", rebase, true)
        addSample(now, pose)
    }

    @Synchronized fun stop(partial: Boolean = false): JSONObject? {
        if (!active) return null
        active = false
        waitingForResume = false
        journal.finish(id)
        val take = JSONObject().apply {
            put("type", "take")
            put("id", id)
            if (snapshot.length() > 0) put("snapshot", snapshot)
            put("events", JSONArray(events))
            put("frame_markers", JSONArray(frameMarkers))
            if (partial) put("partial", true)
        }
        journal.savePending(take)
        return take
    }

    fun recover(): List<JSONObject> = journal.recover()

    fun saveRecovered(take: JSONObject): File = journal.savePending(take)

    fun close() = journal.close()

    private fun elapsed(now: Long): Double =
        (now - startedAt - pausedDuration).coerceAtLeast(0L) / 1_000_000_000.0
}
