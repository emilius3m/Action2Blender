"""A take with its own snapshot can be replayed without an active recording session."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender import blender as addon
from action2blender.blender import _camera_uuid, _process_event


action2blender.register()
scene = bpy.context.scene
scene.a2b_auto_stabilize = False
take_id = "11111111-2222-4333-8444-555555555555"
snapshot = {
    "format": 2, "id": take_id,
    "scene": {"name": scene.name, "take_start_frame": 10,
              "playback_end_frame": 40, "fps": 24, "fps_base": 1},
    "camera": {"source_uuid": "missing-source", "name": "Missing camera",
               "position": [0, 0, 5], "rotation_xyzw": [0, 0, 0, 1],
               "lens_mm": 50, "focus_distance_bu": 10, "fstop": 2.8,
               "sensor_fit": "AUTO", "sensor_width_mm": 36, "sensor_height_mm": 24},
    "tracking": {"phone_anchor": {"p": [0, 0, 0], "q": [0, 0, 0, 1]}, "scale": 1},
}
take = {
    "type": "take", "id": take_id, "snapshot": snapshot,
    "events": [
        {"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1],
         "lens": 50, "focus_distance": 10, "fstop": 2.8},
        {"t": 1, "p": [1, 0, 0], "q": [0, 0, 0, 1],
         "lens": 100, "focus_distance": 5, "fstop": 4},
    ],
    "frame_markers": [{"frame": 10, "t": 0}, {"frame": 34, "t": 1}],
}
_process_event(scene, take)
assert len(scene.a2b_takes) == 1
item = scene.a2b_takes[0]
camera = scene.camera
assert camera.get("a2b_take_id") == take_id
assert item.start_frame == 10 and item.end_frame == 34
assert item.lens_action_name in bpy.data.actions
scene.frame_set(34)
assert abs(camera.data.lens - 100) < 0.01, camera.data.lens
assert abs(camera.data.dof.focus_distance - 5) < 0.01
assert abs(camera.data.dof.aperture_fstop - 4) < 0.01
_process_event(scene, take)
assert len(scene.a2b_takes) == 1

source_lens = bpy.data.cameras.new("Source Lens")
source_lens.lens = 35
source = bpy.data.objects.new("Animated Source", source_lens)
scene.collection.objects.link(source)
source.location = (2, 0, 5)
source.keyframe_insert(data_path="location", frame=10)
source_lens.keyframe_insert(data_path="lens", frame=10)
source_action = source.animation_data.action
source_lens_action = source_lens.animation_data.action
second_id = "22222222-3333-4444-8555-666666666666"
second_snapshot = {
    **snapshot, "id": second_id,
    "camera": {**snapshot["camera"], "source_uuid": _camera_uuid(source),
               "name": source.name, "position": [2, 0, 5], "lens_mm": 35},
}
second_take = {
    **take, "id": second_id, "snapshot": second_snapshot, "partial": True,
    "frame_markers": [{"frame": 34, "t": 1}],
    "events": [{**event, "lens": 35 if index == 0 else 70}
               for index, event in enumerate(take["events"])],
}
_process_event(scene, second_take)
assert len(scene.a2b_takes) == 2
assert scene.a2b_takes[1].is_partial
second_camera = scene.camera
assert second_camera is not source and second_camera.data is not source_lens
assert source.animation_data.action is source_action
assert source_lens.animation_data.action is source_lens_action
assert source_lens.lens == 35
scene.a2b_take_index = 0
scene.frame_set(34)
assert scene.camera is camera and abs(scene.camera.data.lens - 100) < 0.01
scene.a2b_take_index = 1
scene.frame_set(34)
assert scene.camera is second_camera and abs(scene.camera.data.lens - 70) < 0.01

# A take left pending on the phone arrives while another take is recording (e.g. after a
# Wi-Fi reconnect): it is imported, but the running recording, camera and timeline stay put.
recording_id = "33333333-4444-4555-8666-777777777777"
recording_camera = bpy.data.objects.new("Recording camera", bpy.data.cameras.new("Recording lens"))
scene.collection.objects.link(recording_camera)
scene.camera = recording_camera
scene.frame_set(20)
recording_state = {"id": recording_id, "scene": scene, "camera": recording_camera,
                   "source": source, "snapshot": {"scene": {"playback_end_frame": 40}},
                   "active": True, "end_frame": None, "started_ns": 0}
addon._record_state = recording_state
selected_before = scene.a2b_take_index
late_id = "44444444-5555-4666-8777-888888888888"
_process_event(scene, {**take, "id": late_id, "snapshot": {**snapshot, "id": late_id}})
assert any(item.take_id == late_id for item in scene.a2b_takes)
assert addon._record_state is recording_state, "pending take import cleared the recording"
assert scene.camera is recording_camera, scene.camera
assert scene.frame_current == 20 and scene.a2b_take_index == selected_before
addon._record_state = None

# Build 15 phones could send a lens-change sample before a slightly older tracking sample,
# and a frame time a little behind the previous one: the take is imported, not rejected.
jumbled_id = "55555555-6666-4777-8888-999999999999"
jumbled = {**take, "id": jumbled_id, "snapshot": {**snapshot, "id": jumbled_id}, "events": [
    {"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1], "lens": 50, "focus_distance": 10, "fstop": 2.8},
    {"t": 0.52, "p": [0.52, 0, 0], "q": [0, 0, 0, 1], "lens": 80, "focus_distance": 10, "fstop": 2.8},
    {"t": 0.50, "p": [0.50, 0, 0], "q": [0, 0, 0, 1], "lens": 50, "focus_distance": 10, "fstop": 2.8},
    {"t": 1, "p": [1, 0, 0], "q": [0, 0, 0, 1], "lens": 80, "focus_distance": 10, "fstop": 2.8},
], "frame_markers": [{"frame": 10, "t": 0}, {"frame": 22, "t": 0.51}, {"frame": 23, "t": 0.505},
                     {"frame": 34, "t": 1}]}
_process_event(scene, jumbled)
jumbled_item = next(item for item in scene.a2b_takes if item.take_id == jumbled_id)
assert (jumbled_item.start_frame, jumbled_item.end_frame) == (10, 34)

invalid = {**second_take, "id": "invalid-new", "snapshot": {
    **second_snapshot, "id": "invalid-new",
    "tracking": {**second_snapshot["tracking"], "scale": float("nan")},
}}
before = len(bpy.data.objects)
try:
    _process_event(scene, invalid)
except ValueError:
    pass
else:
    raise AssertionError("Invalid snapshot accepted")
assert len(bpy.data.objects) == before
print("A2B_RECORDING_V2_SMOKE_OK", camera.name, item.lens_action_name)
action2blender.unregister()
