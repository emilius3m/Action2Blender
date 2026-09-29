package org.action2blender.action2blender

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

class PoseStabilizerTest {
    private val identity = floatArrayOf(0f, 0f, 0f, 1f)

    private fun pose(x: Float = 0f, angle: Double = 0.0): PhonePose = PhonePose(
        floatArrayOf(x, 0f, 0f),
        floatArrayOf(0f, 0f, sin(angle / 2).toFloat(), cos(angle / 2).toFloat()),
    )

    @Test fun removesSmallHandJitterFromPositionAndRotation() {
        val filter = PoseStabilizer()
        filter.reset(0L, PhonePose(floatArrayOf(0f, 0f, 0f), identity))
        var result = pose()
        for (index in 1..40) {
            result = filter.update(
                index * 16_666_667L,
                pose(if (index % 2 == 0) 0.01f else -0.01f,
                     if (index % 2 == 0) 0.08 else -0.08),
                0.5f,
            )
        }
        assertTrue(abs(result.position[0]) < 0.005f)
        assertTrue(abs(result.rotation[2]) < 0.02f)
    }

    @Test fun followsLargeIntentionalMoveQuickly() {
        val filter = PoseStabilizer()
        filter.reset(0L, pose())
        val result = filter.update(16_666_667L, pose(0.5f), 0.5f)
        assertTrue(result.position[0] > 0.45f)
    }

    @Test fun equivalentQuaternionSignsDoNotCauseFlip() {
        val filter = PoseStabilizer()
        filter.reset(0L, pose(angle = 0.4))
        val sameOrientation = pose(angle = 0.4)
        val negative = sameOrientation.rotation.map { -it }.toFloatArray()
        val result = filter.update(16_666_667L,
            PhonePose(floatArrayOf(0f, 0f, 0f), negative), 0.5f)
        assertEquals(sameOrientation.rotation[2].toDouble(), result.rotation[2].toDouble(), 1e-5)
        assertEquals(1.0, result.rotation.sumOf { it.toDouble() * it.toDouble() }, 1e-5)
    }

    @Test fun zeroStrengthReturnsMeasuredPose() {
        val filter = PoseStabilizer()
        filter.reset(0L, pose())
        val result = filter.update(16_666_667L, pose(0.01f), 0f)
        assertEquals(0.01, result.position[0].toDouble(), 1e-6)
    }
}
