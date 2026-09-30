"""Tracking corrections during Rec, rejected takes and the 3D View focal length."""

import math
import queue
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender import blender as addon


def phone(kind, x=0.0, **extra):
    return {"type": kind, "p": [x, 0, 0], "q": [0, 0, 0, 1], **extra}


def poll(message):
    responses = queue.Queue()
    addon._server.events.put({**message, "_response": responses})
    addon._poll_events()
    return responses.get_nowait()


action2blender.register()
scene = bpy.context.scene
camera = scene.camera
scene.frame_set(1)
addon._server = SimpleNamespace(events=queue.Queue(), broadcast=lambda value: None)
assert poll(phone("recenter"))["type"] == "recenter_ok"


def recording(active):
    return {"id": "rec-1", "scene": scene, "camera": camera, "source": camera,
            "snapshot": {"scene": {"playback_end_frame": 10_000}}, "active": active,
            "end_frame": None, "started_ns": 0}


# ARCore relocalizes during Rec: the phone sends resume without an ID. Blender realigns
# instead of refusing, and does not touch the recording (no timeline restart).
for active in (True, False):  # during the take, and between Stop and the take's arrival
    addon._record_state = recording(active)
    bpy.context.view_layer.update()
    before = camera.matrix_world.translation.copy()
    # Called directly: the event loop would end an "active" take here, because the timeline
    # of the background Blender window is not playing.
    reply = addon._process_event(scene, phone("resume", 5.0))
    assert reply["type"] == "record_resumed", reply
    assert addon._record_state["active"] is active
    addon._process_event(scene, phone("pose", 5.0))
    bpy.context.view_layer.update()
    assert (camera.matrix_world.translation - before).length < 1e-4, "camera jumped after the correction"
# "Resume" for another recording is still refused.
reply = poll(phone("resume", 5.0, id="other"))
assert reply["type"] == "error" and "does not match" in reply["message"], reply

# A take Blender cannot import ends its recording instead of blocking Rec and new cameras.
bad_take = {"type": "take", "id": "rec-1", "events": [{"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1]}],
            "snapshot": {"format": 2, "id": "rec-1", "camera": {}, "tracking": {}, "scene": {}}}
reply = poll(bad_take)
assert reply["type"] == "error", reply
assert addon._record_state is None, "a rejected take kept Blender waiting for it"
assert "not imported" in scene.a2b_status, scene.a2b_status

# "From Blender 3D View": a 3D View at 50 mm shows 71.5° like a 72 mm sensor, so a
# 36 mm camera needs 25 mm to frame the same width.
lens = bpy.data.cameras.new("Check lens")
view = SimpleNamespace(region_3d=SimpleNamespace(window_matrix=[[50 / 36, 0], [0, 1]]))
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
focal = addon._lens_matching_view(scene, lens, view)
assert abs(focal - 25.0) < 1e-6, focal
assert abs(math.degrees(2 * math.atan(lens.sensor_width / (2 * focal))) - 71.5) < 0.1

addon._record_state = None
addon._server = None
action2blender.unregister()
print("A2B_ROBUSTNESS_OK")
