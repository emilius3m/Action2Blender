package org.action2blender.action2blender

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt

/** Low-latency filter for the physical ARCore pose, before virtual joystick motion. */
class PoseStabilizer {
    private var previous: PhonePose? = null
    private var previousAt = 0L

    fun reset(now: Long, pose: PhonePose): PhonePose {
        val result = PhonePose(pose.position.copyOf(), normalized(pose.rotation))
        previous = result
        previousAt = now
        return result
    }

    fun update(now: Long, raw: PhonePose, strength: Float): PhonePose {
        require(strength.isFinite() && strength in 0f..1f) { "Invalid live stabilization strength" }
        val before = previous ?: return reset(now, raw)
        val seconds = (now - previousAt) / 1_000_000_000.0
        if (seconds <= 0.0 || seconds > 0.5 || strength == 0f) return reset(now, raw)

        // A small time constant removes hand jitter; large intentional motion catches up faster.
        val tau = 0.02 + 0.16 * strength
        val baseAlpha = seconds / (tau + seconds)
        val distance = sqrt(raw.position.indices.sumOf { axis ->
            val delta = (raw.position[axis] - before.position[axis]).toDouble()
            delta * delta
        })
        val positionAlpha = max(baseAlpha, ((distance - 0.025) / 0.15).coerceIn(0.0, 1.0))
        val targetRotation = normalized(raw.rotation)
        val dot = before.rotation.indices.sumOf { axis ->
            before.rotation[axis].toDouble() * targetRotation[axis]
        }.coerceIn(-1.0, 1.0)
        val angle = 2.0 * acos(kotlin.math.abs(dot))
        val rotationAlpha = max(baseAlpha, ((angle - PI / 90) / (PI / 10)).coerceIn(0.0, 1.0))

        val position = FloatArray(3) { axis ->
            (before.position[axis] + positionAlpha * (raw.position[axis] - before.position[axis])).toFloat()
        }
        val result = PhonePose(position, slerp(before.rotation, targetRotation, rotationAlpha))
        previous = result
        previousAt = now
        return result
    }

    private fun normalized(rotation: FloatArray): FloatArray {
        require(rotation.size == 4) { "Invalid ARCore rotation" }
        val length = sqrt(rotation.sumOf { value -> value.toDouble() * value.toDouble() })
        require(length > 1e-9) { "Invalid ARCore rotation" }
        return FloatArray(4) { index -> (rotation[index] / length).toFloat() }
    }

    private fun slerp(start: FloatArray, end: FloatArray, alpha: Double): FloatArray {
        var dot = start.indices.sumOf { index -> start[index].toDouble() * end[index] }
        val aligned = if (dot < 0) FloatArray(4) { index -> -end[index] } else end
        if (dot < 0) dot = -dot
        if (dot > 0.9995) {
            return normalized(FloatArray(4) { index ->
                (start[index] + alpha * (aligned[index] - start[index])).toFloat()
            })
        }
        val theta = acos(dot.coerceIn(-1.0, 1.0))
        val left = sin((1.0 - alpha) * theta) / sin(theta)
        val right = sin(alpha * theta) / sin(theta)
        return normalized(FloatArray(4) { index ->
            (left * start[index] + right * aligned[index]).toFloat()
        })
    }
}
