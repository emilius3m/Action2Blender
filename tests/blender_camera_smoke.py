"""Create a free camera from the current view or a selected subject and replay joystick travel."""

import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender.blender import _process_event, _view_matrix


def command(kind, **extra):
    return {"type": kind, "p": [0, 0, 0], "q": [0, 0, 0, 1], **extra}


action2blender.register()
scene = bpy.context.scene
scene.a2b_auto_stabilize = False  # This smoke checks camera placement and one raw joystick take.
original = scene.camera
view_matrix = _view_matrix(scene).copy()
_process_event(scene, command("create_camera", mode="view"))
from_view = scene.camera
camera_collection = next(child for child in scene.collection.children if child.name == "Action2Blender")
assert camera_collection.get("a2b_camera_collection")
assert camera_collection.objects.get(from_view.name) is from_view
assert scene.collection.objects.get(from_view.name) is None
assert from_view != original and from_view.parent is None and len(from_view.constraints) == 0
assert (from_view.matrix_world.translation - view_matrix.translation).length < 1e-5
_process_event(scene, command("pose", v=[0, 0, -2]))
bpy.context.view_layer.update()
assert (from_view.matrix_world.translation - view_matrix.translation).length > 1.9

subject = bpy.data.objects["Cube"]
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.pixel_aspect_x = 1
scene.render.pixel_aspect_y = 1
from_view.rotation_quaternion = (1, 0, 0, 0)
subject.scale = (0.05, 4, 0.05)
bpy.context.view_layer.objects.active = subject
subject.select_set(True)
_process_event(scene, command("create_camera", mode="subject"))
framing = scene.camera
assert camera_collection.objects.get(framing.name) is framing
assert len([child for child in scene.collection.children if child.get("a2b_camera_collection")]) == 1
assert framing != from_view and scene.camera.parent is None
for corner in subject.bound_box:
    pixel = world_to_camera_view(scene, framing, subject.matrix_world @ Vector(corner))
    assert pixel.z > 0 and 0.075 < pixel.x < 0.925 and 0.075 < pixel.y < 0.925, pixel

_process_event(scene, command("pose", v=[1, 0, 0]))
bpy.context.view_layer.update()
before_record = framing.matrix_world.translation.copy()
_process_event(scene, command("record_start"))
_process_event(scene, command("pose", v=[0, 0, 0]))
bpy.context.view_layer.update()
assert (framing.matrix_world.translation - before_record).length < 1e-5
_process_event(scene, {
    "type": "take", "id": "joystick-take", "events": [
        {"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1], "v": [0, 0, 0]},
        {"t": 0.5, "p": [0, 0, 0], "q": [0, 0, 0, 1], "v": [0, 0, -2]},
    ],
})
assert len(scene.a2b_takes) == 1
assert scene.a2b_takes[0].camera_name == framing.name
scene.camera = None
_process_event(scene, command("create_camera", mode="view"))
assert scene.camera is not None and scene.camera.parent is None
assert camera_collection.objects.get(scene.camera.name) is scene.camera
assert len([child for child in scene.collection.children if child.get("a2b_camera_collection")]) == 1
print("A2B_CAMERA_SMOKE_OK", from_view.name, framing.name)
action2blender.unregister()
