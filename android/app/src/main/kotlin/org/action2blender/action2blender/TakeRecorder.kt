package org.action2blender.action2blender

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class PhonePose(val position: FloatArray, val rotation: FloatArray) {
    fun message(type: String, timeSeconds: Double? = null): JSONObject = JSONObject().apply {
        put("type", type)
        if (type == "sample" || type == "rebase") put("kind", type)
        if (timeSeconds != null) put("t", timeSeconds)
        put("p", JSONArray(position.map { it.toDouble() }))
        put("q", JSONArray(rotation.map { it.toDouble() }))
    }
}

/** Keeps every measured pose locally until Blender acknowledges the complete take. */
class TakeRecorder {
    private val events = mutableListOf<JSONObject>()
    private var startedAt = 0L
    private var pausedAt = 0L
    private var pausedDuration = 0L
    private var active = false
    private var waitingForResume = false

    @Synchronized fun isRecording(): Boolean = active
    @Synchronized fun isPaused(): Boolean = waitingForResume

    @Synchronized fun start(now: Long, pose: PhonePose) {
        events.clear()
        startedAt = now
        pausedAt = 0L
        pausedDuration = 0L
        active = true
        waitingForResume = false
        events.add(pose.message("sample", 0.0))
    }

    @Synchronized fun addSample(now: Long, pose: PhonePose) {
        if (active && !waitingForResume) events.add(pose.message("sample", elapsed(now)))
    }

    @Synchronized fun pause(now: Long): Boolean {
        if (!active || waitingForResume) return false
        waitingForResume = true
        pausedAt = now
        return true
    }

    @Synchronized fun resume(now: Long, pose: PhonePose): Boolean {
        if (!active || !waitingForResume) return false
        pausedDuration += now - pausedAt
        waitingForResume = false
        events.add(pose.message("rebase", elapsed(now)))
        events.add(pose.message("sample", elapsed(now)))
        return true
    }

    @Synchronized fun stop(): JSONObject? {
        if (!active) return null
        active = false
        waitingForResume = false
        return JSONObject().apply {
            put("type", "take")
            put("id", UUID.randomUUID().toString())
            put("events", JSONArray(events))
        }
    }

    private fun elapsed(now: Long): Double =
        (now - startedAt - pausedDuration).coerceAtLeast(0L) / 1_000_000_000.0
}
