"""Opening another file keeps the connection working, and the user's camera animation survives."""

import math
import queue
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender import blender as addon


def phone(kind, yaw_degrees=0.0):
    half = math.radians(yaw_degrees) / 2
    return {"type": kind, "p": [0, 0, 0], "q": [0, math.sin(half), 0, math.cos(half)]}


def poll(message):
    responses = queue.Queue()
    addon._server.events.put({**message, "_response": responses})
    addon._poll_events()
    return responses.get_nowait()


action2blender.register()
assert bpy.ops.a2b.start() == {"FINISHED"}
server = addon._server
token, host, port = bpy.context.scene.a2b_token, bpy.context.scene.a2b_host, bpy.context.scene.a2b_port

# Opening a file during a recording: the phone is told the take stopped, and nothing
# keeps pointing into the closed file.
sent = []
server.broadcast = sent.append
addon._record_state = {"id": "rec-1", "scene": bpy.context.scene, "camera": bpy.context.scene.camera,
                       "source": bpy.context.scene.camera, "snapshot": {}, "active": True,
                       "end_frame": None, "started_ns": 0}
addon._mapper = object()
bpy.ops.wm.read_homefile(use_empty=True)
assert bpy.app.timers.is_registered(addon._poll_events), "command timer removed by file load"
assert addon._server is server
assert sent and sent[0]["type"] == "record_stopped" and sent[0]["partial"], sent
assert addon._record_state is None and addon._mapper is None and addon._centered_camera is None
scene = bpy.context.scene
assert (scene.a2b_token, scene.a2b_host, scene.a2b_port) == (token, host, port)

# The new file's camera responds to the phone, and keeps its Euler rotation mode and keys.
camera = bpy.data.objects.new("Euler camera", bpy.data.cameras.new("Euler lens"))
scene.collection.objects.link(camera)
scene.camera = camera
camera.rotation_mode = "XYZ"
camera.rotation_euler = (math.radians(80), 0, 0.5)
camera.keyframe_insert(data_path="rotation_euler", frame=1)
hand_made = camera.animation_data.action
scene.frame_set(1)
bpy.context.view_layer.update()
assert poll(phone("recenter"))["type"] == "recenter_ok"
addon._process_event(scene, phone("pose", 30))
assert camera.rotation_mode == "XYZ", camera.rotation_mode
assert abs(camera.rotation_euler.z - (0.5 + math.radians(30))) < 1e-4, tuple(camera.rotation_euler)
scene.frame_set(1)
assert abs(camera.rotation_euler.z - 0.5) < 1e-6, "Euler keys no longer drive the camera"

# Selecting a take on that camera keeps the hand-made Action in the file.
assert not hand_made.use_fake_user
take_action = bpy.data.actions.new("Take on user camera")
item = scene.a2b_takes.add()
item.name = item.action_name = take_action.name
item.camera_name = camera.name
item.start_frame, item.end_frame = 1, 10
scene.a2b_take_index = 0
assert camera.animation_data.action is take_action
assert hand_made.use_fake_user, "hand-made Action would be lost on save"

bpy.ops.a2b.stop()
action2blender.unregister()
print("A2B_FILE_LOAD_OK")
