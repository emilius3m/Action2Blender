"""Run with: blender --background --factory-startup --python tests/blender_stabilization_smoke.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

import bpy
import action2blender
from action2blender.blender import _process_event


action2blender.register()
scene = bpy.context.scene
scene.render.fps = 24
assert scene.a2b_auto_stabilize
camera = scene.camera
assert camera is not None
camera.animation_data_clear()
identity = [0, 0, 0, 1]

_process_event(scene, {"type": "recenter", "p": [0, 0, 0], "q": identity})
_process_event(scene, {"type": "record_start", "p": [0, 0, 0], "q": identity})
_process_event(scene, {
    "type": "take", "id": "stabilization-smoke",
    "events": [
        {"t": index / 24, "p": [0.15 if index == 12 else 0, 0, 0], "q": identity}
        for index in range(25)
    ],
})

assert len(scene.a2b_takes) == 2
original, stabilized = scene.a2b_takes
assert not original.is_stabilized and stabilized.is_stabilized
assert original.action_name != stabilized.action_name
assert bpy.data.actions[original.action_name].use_fake_user
assert bpy.data.actions[stabilized.action_name].use_fake_user

scene.a2b_take_index = 0
scene.frame_set(original.start_frame)
base_x = camera.location.x
scene.frame_set(original.start_frame + 12)
raw_x = camera.location.x - base_x
scene.a2b_take_index = 1
scene.frame_set(stabilized.start_frame + 12)
smooth_x = camera.location.x - base_x
assert raw_x > 0.10, raw_x
assert abs(smooth_x) < raw_x * 0.5, (raw_x, smooth_x)
assert camera.animation_data.action.name == stabilized.action_name

scene.a2b_stabilization_strength = 0.8
assert bpy.ops.a2b.stabilize_take() == {"FINISHED"}
assert len(scene.a2b_takes) == 3
new_version = scene.a2b_takes[2]
assert new_version.is_stabilized
assert new_version.source_action_name == original.action_name
assert new_version.action_name not in (original.action_name, stabilized.action_name)
assert new_version.action_name.startswith("A2B Take 001 - Stabilized")
assert scene.a2b_take_index == 2
assert bpy.data.actions.get(original.action_name) is not None
print("A2B_STABILIZATION_SMOKE_OK", raw_x, smooth_x)
action2blender.unregister()
