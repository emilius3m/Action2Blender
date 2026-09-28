"""Manual device test: run a Blender receiver until one phone take arrives.

Run from the Blender directory after `adb reverse tcp:45767 tcp:45767`.
The phone connects to 127.0.0.1:45767 with pairing code test1234.
"""

import queue
import os
import sys
import time
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon"))

import action2blender  # noqa: E402
from action2blender import blender as integration  # noqa: E402
from action2blender.transport import PoseServer  # noqa: E402


action2blender.register()
scene = bpy.context.scene
assert scene.camera is not None
host = os.environ.get("A2B_TEST_HOST", "127.0.0.1")
server = PoseServer(host, 45767, "test1234")
server.start()
print(f"A2B_DEVICE_READY {host} 45767 test1234", flush=True)

try:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            message = server.events.get(timeout=0.1)
        except queue.Empty:
            continue
        response_queue = message.pop("_response", None)
        try:
            integration._process_event(scene, message)
            if response_queue is not None:
                response_queue.put({"type": "take_saved", "id": message["id"]})
        except Exception as exc:
            print("A2B_DEVICE_ERROR", type(exc).__name__, str(exc), flush=True)
            if response_queue is not None:
                response_queue.put({"type": "error", "message": str(exc)})
            raise
        if message["type"] in {"recenter", "record_start", "take"}:
            print("A2B_DEVICE_EVENT", message["type"], scene.a2b_status, flush=True)
        if message["type"] == "take":
            assert len(scene.a2b_takes) == 1
            assert scene.camera.animation_data.action is not None
            output = ROOT / "dist" / f"device-test-{int(time.time())}.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(output))
            print("A2B_DEVICE_OK", scene.a2b_takes[0].end_frame, output, flush=True)
            break
    else:
        raise TimeoutError("No take arrived from the phone")
finally:
    server.stop()
    action2blender.unregister()
