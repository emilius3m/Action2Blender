import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from action2blender.core import Pose, PoseMapper, _mul, _rotate, map_navigation, sample_optics, sample_take, stabilize_take
from action2blender.transport import validate_message


IDENTITY = (0.0, 0.0, 0.0, 1.0)


def turn(axis, degrees):
    half = math.radians(degrees) / 2
    return tuple(value * math.sin(half) for value in axis) + (math.cos(half),)


# Phone held upright and level (ARCore identity); Blender cameras built from a level one facing +Y.
LEVEL_CAMERA = turn((1, 0, 0), 90)
TILTED_CAMERA = _mul(LEVEL_CAMERA, turn((1, 0, 0), -30))  # looking 30 degrees down
LEVEL_PHONE = Pose((0, 0, 0), IDENTITY)


def axis_of(rotation, local):
    return _rotate(rotation, local)


class PoseMappingTests(unittest.TestCase):
    def assertVectorAlmostEqual(self, actual, expected, places=6):
        for value, target in zip(actual, expected, strict=True):
            self.assertAlmostEqual(value, target, places=places)

    def assertPoseAlmostEqual(self, actual, expected):
        self.assertVectorAlmostEqual(actual.position, expected.position)
        self.assertAlmostEqual(abs(sum(a * b for a, b in zip(actual.rotation, expected.rotation))), 1, places=6)

    def test_recenter_keeps_selected_camera_pose(self):
        for camera in (IDENTITY, LEVEL_CAMERA, TILTED_CAMERA, turn((0.6, 0.0, 0.8), 70)):
            initial = Pose((5, 8, 2), camera)
            phone = Pose((12, -3, 4), turn((0.3, 0.9, 0.3), 40))
            self.assertPoseAlmostEqual(PoseMapper(phone, initial, 2).map(phone), initial)

    def test_scale_changes_translation_only(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((1, 2, 3), LEVEL_CAMERA), 3)
        result = mapper.map(Pose((0, 1, 0), IDENTITY))  # phone raised by 1 m
        self.assertVectorAlmostEqual(result.position, (1, 2, 6))
        self.assertPoseAlmostEqual(result, Pose(result.position, LEVEL_CAMERA))

    def test_phone_axes_follow_blender_camera_heading(self):
        facing_minus_x = _mul(turn((0, 0, 1), 90), LEVEL_CAMERA)
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), facing_minus_x), 1)
        self.assertVectorAlmostEqual(mapper.map(Pose((1, 0, 0), IDENTITY)).position, (0, 1, 0))  # step right
        self.assertVectorAlmostEqual(mapper.map(Pose((0, 0, -1), IDENTITY)).position, (-1, 0, 0))  # step forward

    def test_panning_a_tilted_camera_keeps_the_horizon_level(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), TILTED_CAMERA), 1)
        for degrees in (20, 45, 90, 180):
            rotation = mapper.map(Pose((0, 0, 0), turn((0, 1, 0), degrees))).rotation
            self.assertAlmostEqual(axis_of(rotation, (1, 0, 0))[2], 0, places=6)
            self.assertAlmostEqual(axis_of(rotation, (0, 0, -1))[2], -0.5, places=6)  # still 30° down

    def test_walking_with_a_tilted_camera_stays_at_the_same_height(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 1.6), TILTED_CAMERA), 1)
        self.assertVectorAlmostEqual(mapper.map(Pose((0, 0, -1), IDENTITY)).position, (0, 1, 1.6))

    def test_tilting_the_phone_tilts_the_camera_from_its_own_framing(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), TILTED_CAMERA), 1)
        rotation = mapper.map(Pose((0, 0, 0), turn((1, 0, 0), 30))).rotation  # phone tilted up 30°
        self.assertPoseAlmostEqual(Pose((0, 0, 0), rotation), Pose((0, 0, 0), LEVEL_CAMERA))

    def test_camera_looking_straight_down_keeps_its_heading(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), IDENTITY), 1)  # Blender identity looks down, top toward +Y
        self.assertVectorAlmostEqual(mapper.map(Pose((0, 0, -1), IDENTITY)).position, (0, 1, 0))

    def test_joystick_moves_and_turns_independently_of_physical_scale(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((4, 0, 0), LEVEL_CAMERA), 10)
        moved = map_navigation(mapper, LEVEL_PHONE, {"v": [1, 2, -3], "look": [math.pi / 2, 0]})
        self.assertVectorAlmostEqual(moved.position, (5, 3, 2))  # right, forward, up
        self.assertVectorAlmostEqual(axis_of(moved.rotation, (0, 0, -1)), (-1, 0, 0))  # turned left
        self.assertEqual(mapper.current, moved)

    def test_joystick_turn_and_pitch_keep_a_tilted_horizon_level(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), TILTED_CAMERA), 1)
        for yaw, pitch in ((0.8, 0), (-2.0, 0.4), (1.2, -0.6)):
            moved = map_navigation(mapper, LEVEL_PHONE, {"look": [yaw, pitch]})
            self.assertAlmostEqual(axis_of(moved.rotation, (1, 0, 0))[2], 0, places=6)

    def test_take_replays_virtual_motion_between_frames(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), LEVEL_CAMERA), 1)
        frames = sample_take([
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY, "v": [0, 0, 0]},
            {"t": 1, "p": [0, 0, 0], "q": IDENTITY, "v": [0, 0, -2]},
        ], mapper, 2)
        self.assertVectorAlmostEqual([pose.position[1] for _, pose in frames], [0, 1, 2])

    def test_blender_frame_markers_determine_pose_and_optics_keys(self):
        events = [
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY,
             "lens": 50, "focus_distance": 2, "fstop": 2.8},
            {"t": 1, "p": [0, 1, 0], "q": IDENTITY,
             "lens": 100, "focus_distance": 4, "fstop": 5.6},
        ]
        markers = [(0, 0.0), (5, 0.25), (12, 1.0)]
        poses = sample_take(events, PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), LEVEL_CAMERA), 1),
                            24, markers)
        optics = sample_optics(events, 24, (50, 2, 2.8), markers)
        self.assertEqual([frame for frame, _ in poses], [0, 5, 12])
        self.assertAlmostEqual(poses[1][1].position[2], 0.25)
        self.assertEqual(optics[1][1], (62.5, 2.5, 3.5))

    def test_tracking_rebase_preserves_virtual_camera_position(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), TILTED_CAMERA), 1)
        before = map_navigation(mapper, LEVEL_PHONE, {"v": [2, 0, -3], "look": [0.5, 0.2]})
        mapper.reanchor(Pose((50, 0, 0), turn((0, 1, 0), 40)))
        after = map_navigation(mapper, Pose((50, 0, 0), turn((0, 1, 0), 40)), {"v": [0, 0, 0]})
        self.assertPoseAlmostEqual(after, before)

    def test_reanchor_has_no_pose_jump(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), LEVEL_CAMERA), 1)
        before = mapper.map(Pose((1, 0, 0), IDENTITY))
        mapper.reanchor(Pose((100, 100, 100), IDENTITY))
        self.assertPoseAlmostEqual(mapper.map(Pose((100, 100, 100), IDENTITY)), before)
        self.assertVectorAlmostEqual(mapper.map(Pose((101, 100, 100), IDENTITY)).position, (2, 0, 0))

    def test_take_resamples_on_scene_frames(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), LEVEL_CAMERA), 1)
        events = [
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY},
            {"t": 1, "p": [1, 0, 0], "q": IDENTITY},
        ]
        frames = sample_take(events, mapper, 2)
        self.assertEqual([frame for frame, _ in frames], [0, 1, 2])
        self.assertVectorAlmostEqual([pose.position[0] for _, pose in frames], [0, 0.5, 1])

    def test_tracking_rebase_preserves_take_continuity(self):
        mapper = PoseMapper(LEVEL_PHONE, Pose((0, 0, 0), LEVEL_CAMERA), 1)
        events = [
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY},
            {"t": 1, "p": [1, 0, 0], "q": IDENTITY},
            {"t": 1, "kind": "rebase", "p": [100, 0, 0], "q": IDENTITY},
            {"t": 1.5, "p": [100.5, 0, 0], "q": IDENTITY},
        ]
        frames = sample_take(events, mapper, 2)
        self.assertVectorAlmostEqual([pose.position[0] for _, pose in frames], [0, 0.5, 1, 1.5])

    def test_rejects_invalid_scale_and_event_order(self):
        with self.assertRaises(ValueError):
            validate_message({"type": "scale", "value": -1})
        with self.assertRaises(ValueError):
            sample_take(
                [
                    {"t": 1, "p": [0, 0, 0], "q": IDENTITY},
                    {"t": 0, "p": [1, 0, 0], "q": IDENTITY},
                ],
                PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((0, 0, 0), IDENTITY), 1),
                24,
            )

    def test_stabilization_reduces_jitter_and_preserves_endpoints(self):
        samples = [
            (index, Pose((index / 24 + (0.12 if index % 2 else -0.12), 0, 0), IDENTITY))
            for index in range(25)
        ]
        result = stabilize_take(samples, 24, 0.5)
        self.assertEqual([frame for frame, _ in result], list(range(25)))
        self.assertEqual(result[0], samples[0])
        self.assertEqual(result[-1], samples[-1])
        self.assertLess(abs(result[12][1].position[0] - 12 / 24), 0.03)
        self.assertEqual(stabilize_take(samples, 24, 0), samples)

    def test_stabilization_handles_equivalent_quaternion_signs(self):
        turn = (0, 0, math.sin(0.2), math.cos(0.2))
        samples = [
            (index, Pose((0, 0, 0), turn if index % 2 else tuple(-value for value in turn)))
            for index in range(9)
        ]
        result = stabilize_take(samples, 24, 0.7)
        for _, pose in result:
            self.assertAlmostEqual(sum(value * value for value in pose.rotation), 1, places=6)
            self.assertAlmostEqual(abs(sum(a * b for a, b in zip(pose.rotation, turn))), 1, places=6)
        for (_, previous), (_, current) in zip(result, result[1:]):
            self.assertGreater(sum(a * b for a, b in zip(previous.rotation, current.rotation)), 0)

    def test_stabilization_reduces_small_rotation_jitter(self):
        samples = [
            (index, Pose((0, 0, 0), (0, 0, math.sin(0.08 if index % 2 else -0.08),
                                      math.cos(0.08))))
            for index in range(25)
        ]
        result = stabilize_take(samples, 24, 0.5)
        self.assertLess(abs(result[12][1].rotation[2]), 0.025)
        self.assertEqual(result[0][1].rotation, samples[0][1].rotation)

    def test_stabilization_rejects_invalid_strength(self):
        with self.assertRaises(ValueError):
            stabilize_take([], 24, float("nan"))
        with self.assertRaises(ValueError):
            stabilize_take([], 0, 0.5)


if __name__ == "__main__":
    unittest.main()
