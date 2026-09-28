"""Run with: blender --background --factory-startup --python tests/blender_smoke.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

import bpy
import action2blender
from action2blender.blender import _process_event


action2blender.register()
scene = bpy.context.scene
camera = bpy.data.objects.new("A2B Test Camera", bpy.data.cameras.new("A2B Lens"))
scene.collection.objects.link(camera)
scene.camera = camera
scene.frame_set(10)
identity = [0, 0, 0, 1]

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
