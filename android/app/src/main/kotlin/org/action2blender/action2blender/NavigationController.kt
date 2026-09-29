package org.action2blender.action2blender

import java.util.concurrent.atomic.AtomicReference
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

data class NavigationPose(val translation: FloatArray, val look: FloatArray) {
    companion object {
        fun zero() = NavigationPose(FloatArray(3), FloatArray(2))
    }
}

private data class NavigationInput(
    val moveX: Float = 0f,
    val moveY: Float = 0f,
    val lookX: Float = 0f,
    val lookY: Float = 0f,
    val lift: Float = 0f,
)

/**
 * Integrates screen controls in ARCore world axes (Y up): yaw turns about gravity, travel stays
 * on the horizontal plane toward the camera heading, and lift is vertical. Blender turns these
 * axes onto the camera's heading, so a tilted camera neither rolls nor sinks.
 */
class NavigationController {
    private val input = AtomicReference(NavigationInput())
    private var anchored = false
    private val translation = FloatArray(3)
    private var yaw = 0.0
    private var pitch = 0.0
    private var lastAt = 0L

    fun setInput(moveX: Float, moveY: Float, lookX: Float, lookY: Float, lift: Float) {
        input.set(NavigationInput(
            moveX.coerceIn(-1f, 1f), moveY.coerceIn(-1f, 1f),
            lookX.coerceIn(-1f, 1f), lookY.coerceIn(-1f, 1f), lift.coerceIn(-1f, 1f),
        ))
    }

    fun stop() { input.set(NavigationInput()) }

    @Synchronized fun reset(now: Long, phone: PhonePose): PhonePose {
        anchored = true
        translation.fill(0f)
        yaw = 0.0
        pitch = 0.0
        lastAt = now
        return phone.copy(navigation = snapshot())
    }

    @Synchronized fun advance(now: Long, phone: PhonePose): PhonePose {
        if (!anchored) return phone.copy(navigation = NavigationPose.zero())
        val elapsed = if (lastAt == 0L) 0.0 else ((now - lastAt) / 1_000_000_000.0).coerceIn(0.0, 0.1)
        lastAt = now
        val control = input.get()
        yaw -= control.lookX * 1.5 * elapsed
        if (yaw > PI) yaw -= 2 * PI
        if (yaw < -PI) yaw += 2 * PI
        pitch = (pitch - control.lookY * 1.5 * elapsed).coerceIn(-1.4, 1.4)

        val facing = multiply(floatArrayOf(0f, sin(yaw / 2).toFloat(), 0f, cos(yaw / 2).toFloat()), phone.rotation)
        val forward = rotate(facing, floatArrayOf(0f, 0f, -1f))
        val up = rotate(facing, floatArrayOf(0f, 1f, 0f))
        // Same heading as the add-on's: forward and up combined stay valid when pointing straight down.
        var headingX = forward[0] - forward[1] * up[0]
        var headingZ = forward[2] - forward[1] * up[2]
        val length = sqrt(headingX * headingX + headingZ * headingZ)
        if (length > 1e-6f) {
            headingX /= length
            headingZ /= length
        }
        val distance = (2.0 * elapsed).toFloat() // Blender units per second, independent of AR scale.
        translation[0] += distance * (-headingZ * control.moveX + headingX * control.moveY)
        translation[1] += distance * control.lift
        translation[2] += distance * (headingX * control.moveX + headingZ * control.moveY)
        return phone.copy(navigation = snapshot())
    }

    private fun snapshot() = NavigationPose(
        translation.copyOf(), floatArrayOf(yaw.toFloat(), pitch.toFloat()),
    )

    private fun inverse(q: FloatArray) = floatArrayOf(-q[0], -q[1], -q[2], q[3])

    private fun multiply(a: FloatArray, b: FloatArray): FloatArray {
        val (ax, ay, az, aw) = a
        val (bx, by, bz, bw) = b
        return floatArrayOf(
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        )
    }

    private fun rotate(q: FloatArray, vector: FloatArray): FloatArray {
        val result = multiply(multiply(q, floatArrayOf(vector[0], vector[1], vector[2], 0f)), inverse(q))
        return result.copyOfRange(0, 3)
    }
}
