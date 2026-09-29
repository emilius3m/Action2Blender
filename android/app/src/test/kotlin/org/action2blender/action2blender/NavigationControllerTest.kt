package org.action2blender.action2blender

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.cos
import kotlin.math.sin

class NavigationControllerTest {
    private fun tilted(degreesAboutX: Double) = PhonePose(
        FloatArray(3),
        floatArrayOf(sin(Math.toRadians(degreesAboutX) / 2).toFloat(), 0f, 0f,
                     cos(Math.toRadians(degreesAboutX) / 2).toFloat()),
    )

    /** Holds the given input for one second in 50 ms steps and returns the travel in ARCore axes. */
    private fun travel(phone: PhonePose, moveX: Float = 0f, moveY: Float = 0f, lift: Float = 0f): FloatArray {
        val controller = NavigationController()
        val start = 1_000_000_000L // a zero timestamp means "no previous frame" to the controller
        controller.reset(start, phone)
        controller.setInput(moveX, moveY, 0f, 0f, lift)
        var result = phone
        for (step in 1..20) result = controller.advance(start + step * 50_000_000L, phone)
        return result.navigation.translation
    }

    @Test fun forwardStaysHorizontalWhenThePhonePointsDown() {
        val moved = travel(tilted(-60.0), moveY = 1f)
        assertEquals(0f, moved[0], 1e-4f)
        assertEquals(0f, moved[1], 1e-4f)
        assertEquals(-2f, moved[2], 1e-3f)
    }

    @Test fun forwardFollowsTheTopOfAPhoneLookingStraightDown() {
        val moved = travel(tilted(-90.0), moveY = 1f)
        assertEquals(0f, moved[1], 1e-4f)
        assertEquals(-2f, moved[2], 1e-3f)
    }

    @Test fun sidewaysAndLiftUseTheWorldAxes() {
        val sideways = travel(tilted(-45.0), moveX = 1f)
        assertEquals(2f, sideways[0], 1e-3f)
        assertEquals(0f, sideways[1], 1e-4f)
        val lifted = travel(tilted(-45.0), lift = 1f)
        assertEquals(2f, lifted[1], 1e-3f)
        assertTrue(kotlin.math.abs(lifted[0]) + kotlin.math.abs(lifted[2]) < 1e-4f)
    }
}
