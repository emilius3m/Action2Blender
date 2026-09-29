"""Run with Blender --background --factory-startup --python this_file.py."""

import sys
import struct
import time
import json
import socket
import urllib.request
from pathlib import Path

import bpy
import gpu

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import action2blender
from action2blender import blender as addon


gpu.init()
action2blender.register()
scene = bpy.context.scene
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with socket.socket() as reserved:
    reserved.bind(("127.0.0.1", 0))
    scene.a2b_port = reserved.getsockname()[1]
assert bpy.ops.a2b.start() == {"FINISHED"}
assert scene.render.resolution_x * 9 == scene.render.resolution_y * 16
with socket.create_connection(("127.0.0.1", scene.a2b_port), timeout=2) as control:
    control.sendall(
        (json.dumps({"type": "hello", "version": 1, "token": scene.a2b_token, "camera_control": 4}) + "\n").encode()
    )
    greeting = json.loads(control.makefile("rb").readline())
assert greeting["type"] == "hello_ok"
assert greeting["viewport_port"] == addon._viewport_server.server_address[1]
addon._viewport_server.frames.request(640)
try:
    started = time.perf_counter()
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
        addon._draw_capture()
    sequence, frame, error = addon._viewport_server.frames.next(0, timeout=0)
    assert not error, error
    assert frame.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", frame[16:24])[0] == 640
    url = f"http://127.0.0.1:{greeting['viewport_port']}/frame?since=0&width=640"
    request = urllib.request.Request(
        url, headers={"X-Action2Blender-Token": scene.a2b_token}
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.read() == frame
    destination = Path(__file__).resolve().parents[1] / "dist" / "viewport-smoke.png"
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(frame)
    first_ms = round((time.perf_counter() - started) * 1000)

    scene.camera.location.x += 1
    bpy.context.view_layer.update()
    addon._viewport_server.frames.request(960)
    addon._last_capture = 0
    started = time.perf_counter()
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
        addon._draw_capture()
    _, tablet_frame, error = addon._viewport_server.frames.next(sequence, timeout=0)
    assert not error, error
    assert struct.unpack(">II", tablet_frame[16:24])[0] == 960
    assert tablet_frame != frame
    tablet_destination = destination.with_name("viewport-smoke-tablet.png")
    tablet_destination.write_bytes(tablet_frame)
    tablet_ms = round((time.perf_counter() - started) * 1000)
    timings = []
    for _ in range(8):
        scene.camera.location.x += 0.05
        bpy.context.view_layer.update()
        addon._last_capture = 0
        started = time.perf_counter()
        with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
            addon._draw_capture()
        timings.append(round((time.perf_counter() - started) * 1000))
    print(
        "A2B_VIEWPORT_SMOKE_OK",
        len(frame), first_ms, len(tablet_frame), tablet_ms,
        "tablet_avg_ms", round(sum(timings) / len(timings)), "tablet_max_ms", max(timings),
    )
finally:
    bpy.ops.a2b.stop()
    action2blender.unregister()
