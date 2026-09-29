"""A lost take_saved reply must not create an endless pending-take retry loop."""

import queue
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

import bpy
import action2blender
from action2blender import blender as addon


def phone(kind, position):
    return {"type": kind, "p": position, "q": [0, 0, 0, 1]}


def send_with_reply(scene, message):
    replies = queue.Queue()
    addon._server = SimpleNamespace(events=queue.Queue())
    addon._server.events.put({**message, "_response": replies})
    addon._poll_events()
    addon._server = None
    return replies.get_nowait()


action2blender.register()
scene = bpy.context.scene
addon._process_event(scene, phone("recenter", [0, 0, 0]))
addon._process_event(scene, phone("record_start", [0, 0, 0]))
first = {
    "type": "take", "id": "lost-ack-take",
    "events": [
        {"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1]},
        {"t": 0.5, "p": [1, 0, 0], "q": [0, 0, 0, 1]},
    ],
}
addon._process_event(scene, first)
saved_count = len(scene.a2b_takes)
assert saved_count >= 1
assert all(item.take_id == first["id"] for item in scene.a2b_takes)
assert addon._record_state is None

# The first reply is lost. A duplicate still receives take_saved without record_start.
assert send_with_reply(scene, first) == {"type": "take_saved", "id": first["id"]}
assert len(scene.a2b_takes) == saved_count

# A scene switch must still recognize the take saved in the original scene.
other_scene = bpy.data.scenes.new("Another scene")
addon._process_event(other_scene, first)
assert len(other_scene.a2b_takes) == 0

# Even while a new recording is active, the old retry must not consume its state.
addon._process_event(scene, phone("record_start", [0, 0, 0]))
record_state = addon._record_state
assert send_with_reply(scene, first) == {"type": "take_saved", "id": first["id"]}
assert addon._record_state == record_state
assert len(scene.a2b_takes) == saved_count

second = {**first, "id": "next-take"}
addon._process_event(scene, second)
assert len(scene.a2b_takes) > saved_count

# The ID lives in the .blend scene, so it survives reopening a saved project.
with tempfile.TemporaryDirectory() as directory:
    project = str(Path(directory) / "duplicate-take.blend")
    bpy.ops.wm.save_as_mainfile(filepath=project)
    bpy.ops.wm.open_mainfile(filepath=project)
    reopened = bpy.context.scene
    count_after_reload = len(reopened.a2b_takes)
    assert send_with_reply(reopened, first) == {"type": "take_saved", "id": first["id"]}
    assert len(reopened.a2b_takes) == count_after_reload

    # A stale list entry without any surviving Action must not delete the phone copy.
    for item in reopened.a2b_takes:
        if item.take_id == first["id"]:
            action = bpy.data.actions.get(item.action_name)
            if action is not None:
                bpy.data.actions.remove(action)
    try:
        addon._process_event(reopened, first)
    except ValueError as exc:
        assert str(exc) == "No recording start received"
    else:
        raise AssertionError("A missing saved Action was incorrectly acknowledged")

print("A2B_DUPLICATE_TAKE_OK", saved_count)
action2blender.unregister()
