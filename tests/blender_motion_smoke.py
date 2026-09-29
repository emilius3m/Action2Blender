"""Check that live phone poses move the evaluated camera, including after a take."""

import math
import sys
import queue
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender import blender as addon


def phone(kind, position):
    return {"type": kind, "p": position, "q": [0, 0, 0, 1]}


def evaluated_location(camera):
    bpy.context.view_layer.update()
    return camera.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.copy()


action2blender.register()
scene = bpy.context.scene
camera = scene.camera
assert camera is not None
camera.animation_data_clear()
start = evaluated_location(camera)
addon._process_event(scene, phone("recenter", [0, 0, 0]))
addon._process_event(scene, phone("pose", [0, 0, -1]))
after = evaluated_location(camera)
assert (after - start).length > 0.9, (start, after)

camera.keyframe_insert(data_path="location", frame=1)
scene.frame_set(1)
keyed = evaluated_location(camera)
addon._process_event(scene, phone("recenter", [0, 0, 0]))
addon._process_event(scene, phone("pose", [0, 0, -1]))
after_key = evaluated_location(camera)
print("A2B_MOTION_SMOKE", tuple(after - start), tuple(after_key - keyed))
assert (after_key - keyed).length > 0.9, (keyed, after_key)

# The phone must only see "ready" after Blender has processed Azzera.
events = queue.Queue()
responses = queue.Queue()
addon._server = SimpleNamespace(events=events)
events.put({**phone("recenter", [0, 0, 0]), "_response": responses})
addon._poll_events()
assert responses.get_nowait() == {"type": "recenter_ok", "camera": camera.name}

rig = bpy.data.objects.new("Temporary camera rig", None)
scene.collection.objects.link(rig)
camera.parent = rig
events.put({**phone("recenter", [0, 0, 0]), "_response": responses})
addon._poll_events()
rejected = responses.get_nowait()
assert rejected["type"] == "error" and rejected["message_type"] == "recenter", rejected
camera.parent = None

constraint = camera.constraints.new("LIMIT_LOCATION")
events.put({**phone("recenter", [0, 0, 0]), "_response": responses})
addon._poll_events()
rejected = responses.get_nowait()
assert rejected["type"] == "error" and "constraints" in rejected["message"], rejected
camera.constraints.remove(constraint)

# Panning the phone with a camera tilted 30° down must keep the horizon level.
camera.animation_data_clear()
camera.rotation_mode = "XYZ"
camera.rotation_euler = (math.radians(60), 0, math.radians(35))
bpy.context.view_layer.update()  # Azzera reads matrix_world
addon._process_event(scene, phone("recenter", [0, 0, 0]))
for degrees in (30, 75):
    half = math.radians(degrees) / 2
    addon._process_event(scene, {"type": "pose", "p": [0, 0, 0], "q": [0, math.sin(half), 0, math.cos(half)]})
    bpy.context.view_layer.update()
    right = camera.matrix_world.to_3x3().col[0]
    forward = -camera.matrix_world.to_3x3().col[2]
    assert abs(right.z) < 1e-5, ("horizon tilted", degrees, tuple(right))
    assert abs(forward.z + 0.5) < 1e-5, ("camera pitch changed", degrees, tuple(forward))
print("A2B_HORIZON_OK")
addon._server = None
action2blender.unregister()
