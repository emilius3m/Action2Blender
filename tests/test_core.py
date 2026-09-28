import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from action2blender.core import Pose, PoseMapper, sample_take
from action2blender.transport import validate_message


IDENTITY = (0.0, 0.0, 0.0, 1.0)


class PoseMappingTests(unittest.TestCase):
    def test_recenter_keeps_selected_camera_pose(self):
        initial = Pose((5, 8, 2), IDENTITY)
        phone = Pose((12, -3, 4), IDENTITY)
        self.assertEqual(PoseMapper(phone, initial, 2).map(phone), initial)

    def test_scale_changes_translation_only(self):
        mapper = PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((1, 2, 3), IDENTITY), 3)
        result = mapper.map(Pose((0, 1, 0), IDENTITY))
        self.assertEqual(result.position, (1, 5, 3))
        self.assertEqual(result.rotation, IDENTITY)

    def test_phone_local_axes_follow_blender_camera_heading(self):
        half_turn = (0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4))
        mapper = PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((0, 0, 0), half_turn), 1)
        result = mapper.map(Pose((1, 0, 0), IDENTITY))
        self.assertAlmostEqual(result.position[0], 0, places=6)
        self.assertAlmostEqual(result.position[1], 1, places=6)

    def test_reanchor_has_no_pose_jump(self):
        mapper = PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((0, 0, 0), IDENTITY), 1)
        before = mapper.map(Pose((1, 0, 0), IDENTITY))
        mapper.reanchor(Pose((100, 100, 100), IDENTITY))
        self.assertEqual(mapper.map(Pose((100, 100, 100), IDENTITY)), before)
        self.assertEqual(mapper.map(Pose((101, 100, 100), IDENTITY)).position, (2, 0, 0))

    def test_take_resamples_on_scene_frames(self):
        mapper = PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((0, 0, 0), IDENTITY), 1)
        events = [
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY},
            {"t": 1, "p": [1, 0, 0], "q": IDENTITY},
        ]
        frames = sample_take(events, mapper, 2)
        self.assertEqual([frame for frame, _ in frames], [0, 1, 2])
        self.assertEqual([pose.position[0] for _, pose in frames], [0, 0.5, 1])

    def test_tracking_rebase_preserves_take_continuity(self):
        mapper = PoseMapper(Pose((0, 0, 0), IDENTITY), Pose((0, 0, 0), IDENTITY), 1)
        events = [
            {"t": 0, "p": [0, 0, 0], "q": IDENTITY},
            {"t": 1, "p": [1, 0, 0], "q": IDENTITY},
            {"t": 1, "kind": "rebase", "p": [100, 0, 0], "q": IDENTITY},
            {"t": 1.5, "p": [100.5, 0, 0], "q": IDENTITY},
        ]
        frames = sample_take(events, mapper, 2)
        self.assertEqual([pose.position[0] for _, pose in frames], [0, 0.5, 1, 1.5])

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


if __name__ == "__main__":
    unittest.main()
