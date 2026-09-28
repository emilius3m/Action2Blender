"""Run with: blender --background --factory-startup --python tests/blender_smoke.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

import bpy
import action2blender
from action2blender.blender import _pairing_icon, _process_event


action2blender.register()
scene = bpy.context.scene
camera = bpy.data.objects.new("A2B Test Camera", bpy.data.cameras.new("A2B Lens"))
scene.collection.objects.link(camera)
scene.camera = camera
scene.frame_set(10)
identity = [0, 0, 0, 1]

_process_event(scene, {"type": "pose", "p": [3, 0, 0], "q": identity})
assert abs(camera.location.x) < 1e-6
try:
    _process_event(scene, {"type": "record_start", "p": [3, 0, 0], "q": identity})
except ValueError as exc:
    assert "Azzera" in str(exc)
else:
    raise AssertionError("Recording was allowed before Azzera")

scene.a2b_host = "192.168.1.3"
scene.a2b_token = "12345678"
assert _pairing_icon(scene) >= 0  # Background Blender has no UI icon atlas.
from action2blender import blender as addon_ui
assert addon_ui._qr_path is not None and addon_ui._qr_path.is_file()

_process_event(scene, {"type": "recenter", "p": [0, 0, 0], "q": identity})
_process_event(scene, {"type": "pose", "p": [1, 0, 0], "q": identity})
assert abs(camera.location.x - 1) < 1e-6
_process_event(scene, {"type": "record_start", "p": [1, 0, 0], "q": identity})
_process_event(
    scene,
    {
        "type": "take",
        "id": "first",
        "events": [
            {"t": 0, "p": [1, 0, 0], "q": identity},
            {"t": 0.5, "p": [2, 0, 0], "q": identity},
        ],
    },
)
assert len(scene.a2b_takes) == 1
first_action = camera.animation_data.action
assert first_action is not None and len(first_action.slots) == 1
assert scene.a2b_takes[0].start_frame == 10

other_camera = bpy.data.objects.new("Other camera", bpy.data.cameras.new("Other lens"))
scene.collection.objects.link(other_camera)
scene.camera = other_camera
_process_event(scene, {"type": "pose", "p": [5, 0, 0], "q": identity})
assert abs(other_camera.location.x) < 1e-6
scene.camera = camera

scene.frame_set(30)
_process_event(scene, {"type": "record_start", "p": [2, 0, 0], "q": identity})
_process_event(
    scene,
    {
        "type": "take",
        "id": "second",
        "events": [
            {"t": 0, "p": [2, 0, 0], "q": identity},
            {"t": 0.25, "p": [3, 0, 0], "q": identity},
        ],
    },
)
assert len(scene.a2b_takes) == 2
assert camera.animation_data.action != first_action
scene.a2b_take_index = 0
assert camera.animation_data.action == first_action

print("A2B_BLENDER_SMOKE_OK", len(scene.a2b_takes), len(first_action.slots))
action2blender.unregister()
