"""Action2Blender: live Android camera control and non-destructive takes."""

import queue
import secrets
import socket
import tempfile
import time
import uuid
from math import atan, isfinite, sin, tan
from pathlib import Path

import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent
from mathutils import Quaternion, Vector
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, StringProperty

from .core import Pose, PoseMapper, map_navigation, sample_optics, sample_take, stabilize_take
from .pairing import pairing_uri, qr_png
from .transport import PoseServer
from .viewport import ViewportServer, encode_rgba_png


_server: PoseServer | None = None
_viewport_server: ViewportServer | None = None
_capture_handler = None
_offscreen = None
_offscreen_size: tuple[int, int] | None = None
_offscreen_window: int | None = None
_last_capture = 0.0
_capture_interval = 0.10
_capture_busy = False
_mapper: PoseMapper | None = None
_centered_camera: bpy.types.Object | None = None
_last_phone: Pose | None = None
_record_state: tuple[Pose, Pose, float, int, bpy.types.Object] | dict | None = None
_prepared: dict | None = None
_last_frame_tick = -1
_qr_preview = None
_qr_path: Path | None = None
_qr_key: tuple[str, int, str] | None = None


def _camera_pose(camera: bpy.types.Object) -> Pose:
    position, rotation, _ = camera.matrix_world.decompose()
    return Pose(tuple(position), (rotation.x, rotation.y, rotation.z, rotation.w))


def _apply_pose(camera: bpy.types.Object, pose: Pose) -> None:
    """Set the pose in the camera's own rotation mode, so its existing Euler or axis-angle keys keep working."""
    camera.location = pose.position
    rotation = Quaternion((pose.rotation[3], *pose.rotation[:3]))
    if camera.rotation_mode == "QUATERNION":
        camera.rotation_quaternion = rotation
    elif camera.rotation_mode == "AXIS_ANGLE":
        axis, angle = rotation.to_axis_angle()
        camera.rotation_axis_angle = (angle, *axis)
    else:
        camera.rotation_euler = rotation.to_euler(camera.rotation_mode, camera.rotation_euler)


def _camera_uuid(camera: bpy.types.Object) -> str:
    if not camera.get("a2b_camera_uuid"):
        camera["a2b_camera_uuid"] = str(uuid.uuid4())
    return camera["a2b_camera_uuid"]


def _focus_distance(camera: bpy.types.Object) -> float:
    target = camera.data.dof.focus_object
    if target is None:
        return camera.data.dof.focus_distance
    local = camera.matrix_world.inverted() @ target.matrix_world.translation
    return max(0.01, -local.z)


def _snapshot(scene: bpy.types.Scene, camera: bpy.types.Object, phone: Pose,
              scale: float, take_id: str) -> dict:
    pose = _camera_pose(camera)
    lens = camera.data
    return {
        "format": 2, "id": take_id,
        "scene": {"name": scene.name, "take_start_frame": scene.frame_current,
                  "playback_end_frame": scene.frame_preview_end if scene.use_preview_range else scene.frame_end,
                  "fps": scene.render.fps, "fps_base": scene.render.fps_base,
                  "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                  "pixel_aspect": [scene.render.pixel_aspect_x, scene.render.pixel_aspect_y]},
        "camera": {"source_uuid": _camera_uuid(camera), "name": camera.name,
                   "position": list(pose.position), "rotation_xyzw": list(pose.rotation),
                    "lens_mm": lens.lens, "focus_distance_bu": _focus_distance(camera),
                   "fstop": lens.dof.aperture_fstop, "sensor_fit": lens.sensor_fit,
                   "sensor_width_mm": lens.sensor_width, "sensor_height_mm": lens.sensor_height},
        "tracking": {"phone_anchor": {"p": list(phone.position), "q": list(phone.rotation)},
                     "scale": scale},
    }


def _take_camera(scene: bpy.types.Scene, source: bpy.types.Object, take_id: str) -> bpy.types.Object:
    lens = source.data.copy()
    lens.animation_data_clear()
    lens.dof.focus_distance = _focus_distance(source)
    lens.dof.focus_object = None
    camera = bpy.data.objects.new("A2B Take Camera", lens)
    _camera_collection(scene).objects.link(camera)
    camera.matrix_world = source.matrix_world.copy()
    camera.rotation_mode = "QUATERNION"
    camera["a2b_camera_uuid"] = str(uuid.uuid4())
    camera["a2b_take_id"] = take_id
    scene.camera = camera
    return camera


def _playback_window(scene: bpy.types.Scene):
    return next((window for window in bpy.context.window_manager.windows
                 if window.scene == scene), None)


def _start_playback(scene: bpy.types.Scene) -> None:
    window = _playback_window(scene)
    if window is None:
        raise ValueError("Open a Blender window to play the timeline")
    with bpy.context.temp_override(window=window, screen=window.screen):
        if window.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        result = bpy.ops.screen.animation_play(sync=True)
    if "FINISHED" not in result:
        raise ValueError("Blender could not start timeline playback")


def _stop_playback(scene: bpy.types.Scene) -> None:
    window = _playback_window(scene)
    if window is not None and window.screen.is_animation_playing:
        with bpy.context.temp_override(window=window, screen=window.screen):
            bpy.ops.screen.animation_cancel(restore_frame=False)


def _view_space(scene: bpy.types.Scene):
    for window in bpy.context.window_manager.windows:
        if window.scene != scene:
            continue
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                return area.spaces.active
    return None


def _view_matrix(scene: bpy.types.Scene):
    space = _view_space(scene)
    if space is not None:
        return space.region_3d.view_matrix.inverted()
    return scene.camera.matrix_world.copy() if scene.camera is not None else None


def _camera_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    def descendants(parent: bpy.types.Collection):
        for child in parent.children:
            yield child
            yield from descendants(child)

    collections = list(descendants(scene.collection))
    collection = next((item for item in collections if item.get("a2b_camera_collection")), None)
    if collection is None:
        collection = next((item for item in collections if item.name == "Action2Blender"), None)
    if collection is None:
        collection = bpy.data.collections.new("Action2Blender")
        scene.collection.children.link(collection)
    collection["a2b_camera_collection"] = True
    return collection


def _lens_matching_view(scene: bpy.types.Scene, lens: bpy.types.Camera, space) -> float:
    """Focal length that gives the camera the 3D View's horizontal field of view.

    The 3D View's focal length refers to a 72 mm sensor, so copying it into a camera
    (36 mm by default) would frame about half the width the user sees.
    """
    half_fov = atan(1.0 / space.region_3d.window_matrix[0][0])
    render = scene.render
    aspect = (render.resolution_x * render.pixel_aspect_x) / (render.resolution_y * render.pixel_aspect_y)
    if lens.sensor_fit == "VERTICAL":
        sensor_across = lens.sensor_height * aspect
    elif lens.sensor_fit == "AUTO" and aspect < 1:
        sensor_across = lens.sensor_width * aspect
    else:
        sensor_across = lens.sensor_width
    return min(5000.0, max(1.0, sensor_across / (2.0 * tan(half_fov))))


def _create_camera(scene: bpy.types.Scene, mode: str) -> bpy.types.Object:
    if _record_state is not None:
        raise ValueError("Wait for the take to be saved before creating a camera")
    corners = None
    if mode == "subject":
        subject = bpy.context.view_layer.objects.active
        if subject is None or subject.type == "CAMERA" or subject not in bpy.context.selected_objects:
            raise ValueError("Select an object in the Blender scene")
        corners = [subject.matrix_world @ Vector(corner) for corner in subject.bound_box]
    space = _view_space(scene)
    if mode == "view" and space is not None and space.region_3d.view_perspective == "ORTHO":
        raise ValueError("Switch Blender to Perspective View before creating the camera")
    view = _view_matrix(scene)
    lens = scene.camera.data.copy() if scene.camera is not None else bpy.data.cameras.new("Action2Blender Lens")
    lens.animation_data_clear()
    if mode == "view" and space is not None and space.region_3d.view_perspective == "PERSP":
        lens.lens = _lens_matching_view(scene, lens, space)
    camera = bpy.data.objects.new("Action2Blender Camera", lens)
    _camera_collection(scene).objects.link(camera)
    camera.rotation_mode = "QUATERNION"
    if view is not None:
        camera.matrix_world = view
    else:
        camera.location = (0, 0, 5)
    if corners is not None:
        center = sum(corners, Vector()) / len(corners)
        radius = max(0.1, max((corner - center).length for corner in corners))
        frame = lens.view_frame(scene=scene)
        half_fov = max(0.01, min(
            atan(abs(corner.x / corner.z)) for corner in frame
        ))
        half_fov = min(half_fov, max(0.01, min(
            atan(abs(corner.y / corner.z)) for corner in frame
        )))
        distance = radius * 1.2 / sin(half_fov)
        camera.location = center + camera.rotation_quaternion @ Vector((0, 0, distance))
    scene.camera = camera
    return camera


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("1.1.1.1", 80))
            return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def _clear_qr() -> None:
    global _qr_preview, _qr_path, _qr_key
    if _qr_preview is not None:
        bpy.utils.previews.remove(_qr_preview)
        _qr_preview = None
    if _qr_path is not None:
        _qr_path.unlink(missing_ok=True)
        _qr_path = None
    _qr_key = None


def _pairing_icon(scene: bpy.types.Scene) -> int:
    global _qr_preview, _qr_path, _qr_key
    key = (scene.a2b_host, scene.a2b_port, scene.a2b_token)
    if _qr_key == key and _qr_preview is not None:
        return _qr_preview["pairing"].icon_id
    payload = pairing_uri(*key)
    _clear_qr()
    with tempfile.NamedTemporaryFile(prefix="action2blender-", suffix=".png", delete=False) as output:
        output.write(qr_png(payload))
        _qr_path = Path(output.name)
    try:
        _qr_preview = bpy.utils.previews.new()
        _qr_preview.load("pairing", str(_qr_path), "IMAGE")
        _qr_key = key
        return _qr_preview["pairing"].icon_id
    except Exception:
        _clear_qr()
        raise


def _capture_size(scene: bpy.types.Scene, max_side: int) -> tuple[int, int]:
    render = scene.render
    aspect = (render.resolution_x * render.pixel_aspect_x) / (
        render.resolution_y * render.pixel_aspect_y
    )
    if aspect >= 1:
        return max_side, max(1, round(max_side / aspect))
    return max(1, round(max_side * aspect)), max_side


def _free_offscreen() -> None:
    global _offscreen, _offscreen_size, _offscreen_window
    if _offscreen is not None:
        try:
            _offscreen.free()
        except Exception:
            pass  # Its Blender window may already have closed.
    _offscreen = None
    _offscreen_size = None
    _offscreen_window = None


def _draw_capture() -> None:
    global _offscreen, _offscreen_size, _offscreen_window
    global _last_capture, _capture_interval, _capture_busy
    server = _viewport_server
    if server is None or _capture_busy:
        return
    width_limit = server.frames.active_width()
    now = time.monotonic()
    if width_limit is None or now - _last_capture < _capture_interval:
        return
    context = bpy.context
    scene = context.scene
    if (
        scene is None or scene.camera is None or context.region is None
        or context.region.type != "WINDOW" or context.window is None
    ):
        server.frames.set_error("Select a camera in Blender")
        return
    _capture_busy = True
    _last_capture = now
    try:
        import gpu

        width, height = _capture_size(scene, width_limit)
        window_id = context.window.as_pointer()
        if _offscreen_size != (width, height) or _offscreen_window != window_id:
            _free_offscreen()
            _offscreen = gpu.types.GPUOffScreen(width, height)
            _offscreen_size = (width, height)
            _offscreen_window = window_id
        camera = scene.camera
        projection = camera.calc_matrix_camera(
            context.evaluated_depsgraph_get(), x=width, y=height,
        )
        _offscreen.draw_view3d(
            scene, context.view_layer, context.space_data, context.region,
            camera.matrix_world.inverted(), projection, do_color_management=True,
        )
        with _offscreen.bind():
            buffer = gpu.state.active_framebuffer_get().read_color(
                0, 0, width, height, 4, 0, "UBYTE"
            )
        buffer.dimensions = width * height * 4
        server.frames.put(encode_rgba_png(width, height, bytes(buffer)))
    except Exception as exc:
        _free_offscreen()
        server.frames.set_error(f"Blender preview: {exc}")
    finally:
        _capture_interval = max(0.10, (time.monotonic() - now) * 3)
        _capture_busy = False


def _stop_viewport() -> None:
    global _viewport_server, _capture_handler
    if _capture_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_capture_handler, "WINDOW")
        _capture_handler = None
    _free_offscreen()
    if _viewport_server is not None:
        _viewport_server.stop()
        _viewport_server = None


def _select_take(scene: bpy.types.Scene, index: int) -> None:
    if not 0 <= index < len(scene.a2b_takes):
        return
    item = scene.a2b_takes[index]
    camera = bpy.data.objects.get(item.camera_name)
    action = bpy.data.actions.get(item.action_name)
    if camera is None or action is None:
        scene.a2b_status = "Take or camera missing"
        return
    camera.animation_data_create()
    _protect_action(camera.animation_data.action, action)
    camera.animation_data.action = action
    if len(action.slots):
        camera.animation_data.action_slot = action.slots[0]
    if item.lens_action_name:
        lens_action = bpy.data.actions.get(item.lens_action_name)
        if lens_action is not None:
            camera.data.animation_data_create()
            _protect_action(camera.data.animation_data.action, lens_action)
            camera.data.animation_data.action = lens_action
            if len(lens_action.slots):
                camera.data.animation_data.action_slot = lens_action.slots[0]
    scene.camera = camera
    scene.frame_set(item.start_frame)
    scene.a2b_status = f"Selected {item.name}"


def _protect_action(previous: bpy.types.Action | None, replacement: bpy.types.Action) -> None:
    """Keep an Action the user made by hand alive in the .blend once a take replaces it."""
    if previous is not None and previous is not replacement:
        previous.use_fake_user = True


def _take_index_changed(scene: bpy.types.Scene, _context: bpy.types.Context) -> None:
    _select_take(scene, scene.a2b_take_index)


def _write_take_action(camera: bpy.types.Object, name: str, sampled: list[tuple[int, Pose]],
                       start_frame: int) -> bpy.types.Action:
    action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    camera.animation_data_create()
    _protect_action(camera.animation_data.action, action)
    camera.animation_data.action = action
    camera.rotation_mode = "QUATERNION"  # take Actions key rotation_quaternion
    for offset, pose in sampled:
        _apply_pose(camera, pose)
        camera.keyframe_insert(data_path="location", frame=start_frame + offset, group="Action2Blender")
        camera.keyframe_insert(data_path="rotation_quaternion", frame=start_frame + offset, group="Action2Blender")
    return action


def _write_lens_action(camera: bpy.types.Object, name: str,
                       sampled: list[tuple[int, tuple[float, float, float]]],
                       start_frame: int) -> bpy.types.Action:
    action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    lens = camera.data
    lens.animation_data_create()
    _protect_action(lens.animation_data.action, action)
    lens.animation_data.action = action
    lens.dof.use_dof = True
    for offset, (focal, focus, fstop) in sampled:
        frame = start_frame + offset
        lens.lens = focal
        lens.dof.focus_distance = focus
        lens.dof.aperture_fstop = fstop
        lens.keyframe_insert(data_path="lens", frame=frame, group="Action2Blender")
        lens.keyframe_insert(data_path="dof.focus_distance", frame=frame, group="Action2Blender")
        lens.keyframe_insert(data_path="dof.aperture_fstop", frame=frame, group="Action2Blender")
    return action


def _add_take_item(scene: bpy.types.Scene, camera: bpy.types.Object, action: bpy.types.Action,
                   start_frame: int, end_frame: int, stabilized: bool,
                   source_action_name: str = "", take_id: str = "",
                    lens_action_name: str = "", is_partial: bool = False) -> None:
    item = scene.a2b_takes.add()
    item.name = action.name
    item.action_name = action.name
    item.camera_name = camera.name
    item.start_frame = start_frame
    item.end_frame = end_frame
    item.is_stabilized = stabilized
    item.source_action_name = source_action_name
    item.take_id = take_id
    item.lens_action_name = lens_action_name
    item.is_partial = is_partial


def _sample_action(scene: bpy.types.Scene, camera: bpy.types.Object, action: bpy.types.Action,
                   start_frame: int, end_frame: int) -> list[tuple[int, Pose]]:
    """Read a saved camera Action at each scene frame without changing the user's selection."""
    camera.animation_data_create()
    animation = camera.animation_data
    previous_action = animation.action
    previous_slot = animation.action_slot
    previous_frame = scene.frame_current
    samples = []
    try:
        animation.action = action
        if len(action.slots):
            animation.action_slot = action.slots[0]
        for frame in range(start_frame, end_frame + 1):
            scene.frame_set(frame)
            rotation = camera.rotation_quaternion
            pose = Pose(tuple(camera.location),
                        (rotation.x, rotation.y, rotation.z, rotation.w))
            samples.append((frame - start_frame, pose))
    finally:
        animation.action = previous_action
        if previous_action is not None and previous_slot is not None:
            animation.action_slot = previous_slot
        scene.frame_set(previous_frame)
    return samples


def _save_take(scene: bpy.types.Scene, message: dict) -> None:
    global _record_state
    take_id = message["id"]
    if take_id and any(
        item.take_id == take_id and bpy.data.actions.get(item.action_name) is not None
        for saved_scene in bpy.data.scenes for item in saved_scene.a2b_takes
    ):
        scene.a2b_status = "Take already received"
        return
    # A take left pending on the phone may arrive while another one is recording:
    # import it without touching that recording's state, active camera or timeline.
    other_recording = ((isinstance(_record_state, dict) and _record_state["id"] != take_id)
                       or (_prepared is not None and _prepared["id"] != take_id))
    active_cameras = {saved_scene: saved_scene.camera for saved_scene in bpy.data.scenes}
    snapshot = message.get("snapshot")
    if snapshot is not None:
        if snapshot.get("format") != 2 or snapshot.get("id") != take_id:
            raise ValueError("Invalid take snapshot")
        camera_state = snapshot["camera"]
        tracking_state = snapshot["tracking"]
        timeline_state = snapshot["scene"]
        scene = bpy.data.scenes.get(timeline_state.get("name", "")) or scene
        anchor = Pose.from_json(tracking_state["phone_anchor"])
        initial = Pose.from_json({"p": camera_state["position"],
                                  "q": camera_state["rotation_xyzw"]})
        scale = float(tracking_state["scale"])
        start_frame = int(timeline_state["take_start_frame"])
        fps = float(timeline_state["fps"]) / float(timeline_state["fps_base"])
        end_limit = int(timeline_state["playback_end_frame"])
        initial_optics = tuple(float(camera_state[key]) for key in
                               ("lens_mm", "focus_distance_bu", "fstop"))
        sensor_width = float(camera_state.get("sensor_width_mm", 36.0))
        sensor_height = float(camera_state.get("sensor_height_mm", 24.0))
        if (not isfinite(scale) or not 0.01 <= scale <= 100 or
                not isfinite(fps) or not 1 <= fps <= 240 or
                start_frame < 0 or end_limit < start_frame or
                end_limit - start_frame > 120_000 or
                not 1 <= initial_optics[0] <= 500 or
                not 0.01 <= initial_optics[1] <= 100_000 or
                not 0.1 <= initial_optics[2] <= 64 or
                not isfinite(sensor_width) or not 1 <= sensor_width <= 100 or
                not isfinite(sensor_height) or not 1 <= sensor_height <= 100 or
                camera_state.get("sensor_fit", "AUTO") not in {"AUTO", "HORIZONTAL", "VERTICAL"}):
            raise ValueError("Invalid take camera or timeline settings")
        markers = message.get("frame_markers", [])
        if not isinstance(markers, list) or len(markers) > 120_001:
            raise ValueError("Invalid frame markers")
        frame_times = []
        previous_frame = start_frame - 1
        previous_time = -1.0
        for marker in markers:
            frame = int(marker["frame"])
            moment = float(marker["t"])
            if frame <= previous_frame or frame > end_limit or not isfinite(moment) or moment < 0:
                raise ValueError("Frame markers must be ordered and inside the take range")
            # The phone's estimate of Blender's clock can improve mid-take and step back slightly.
            moment = max(moment, previous_time)
            frame_times.append((frame - start_frame, moment))
            previous_frame, previous_time = frame, moment
        if frame_times and frame_times[0][0] > 0:
            frame_times.insert(0, (0, 0.0))
        elif frame_times:
            frame_times[0] = (0, 0.0)
        frame_times = frame_times or None
        if not frame_times and max(float(event["t"]) for event in message["events"]) * fps > 120_000:
            raise ValueError("Take is too long")
        sampled = sample_take(message["events"], PoseMapper(anchor, initial, scale), fps, frame_times)
        optical_samples = sample_optics(message["events"], fps, initial_optics, frame_times)
        camera = next((obj for obj in bpy.data.objects if obj.type == "CAMERA"
                       and obj.get("a2b_take_id") == take_id), None)
        if camera is None:
            source = next((obj for obj in bpy.data.objects if obj.type == "CAMERA"
                           and obj.get("a2b_camera_uuid") == camera_state["source_uuid"]), None)
            if source is None:
                lens = bpy.data.cameras.new("A2B Recovered Lens")
                camera = bpy.data.objects.new("A2B Recovered Camera", lens)
                _camera_collection(scene).objects.link(camera)
                camera["a2b_take_id"] = take_id
                camera["a2b_camera_uuid"] = str(uuid.uuid4())
            else:
                camera = _take_camera(scene, source, take_id)
        _apply_pose(camera, initial)
        lens = camera.data
        lens.lens, lens.dof.focus_distance, lens.dof.aperture_fstop = initial_optics
        lens.sensor_fit = camera_state.get("sensor_fit", "AUTO")
        lens.sensor_width = sensor_width
        lens.sensor_height = sensor_height
        scene.camera = camera
    else:
        if _record_state is None:
            raise ValueError("No recording start received")
        if isinstance(_record_state, dict):
            raise ValueError("Take snapshot required")
        anchor, initial, scale, start_frame, camera = _record_state
        fps = scene.render.fps / scene.render.fps_base
        initial_optics = None
        sampled = sample_take(message["events"], PoseMapper(anchor, initial, scale), fps)
    stabilized = None
    if len(sampled) >= 3 and scene.a2b_auto_stabilize and scene.a2b_stabilization_strength > 0:
        stabilized = stabilize_take(sampled, fps, scene.a2b_stabilization_strength)
    take_number = 1 + sum(not item.is_stabilized for item in scene.a2b_takes)
    name = f"A2B Take {take_number:03d}"
    end_frame = start_frame + sampled[-1][0]
    original_action = _write_take_action(camera, f"{name} - Original", sampled, start_frame)
    lens_action = None
    if initial_optics is not None:
        lens_action = _write_lens_action(camera, f"{name} - Lens", optical_samples, start_frame)
    _add_take_item(scene, camera, original_action, start_frame, end_frame, False,
                   take_id=take_id, lens_action_name=lens_action.name if lens_action else "",
                   is_partial=bool(message.get("partial")))
    if stabilized is not None:
        smooth_action = _write_take_action(camera, f"{name} - Stabilized", stabilized, start_frame)
        _add_take_item(scene, camera, smooth_action, start_frame, end_frame, True,
                       original_action.name, take_id,
                        lens_action.name if lens_action else "", bool(message.get("partial")))
    scene.frame_end = max(scene.frame_end, end_frame)
    if other_recording:
        for saved_scene, active_camera in active_cameras.items():
            saved_scene.camera = active_camera
    else:
        scene.a2b_take_index = len(scene.a2b_takes) - 1  # selects the take and jumps to its start
    if snapshot is None or (isinstance(_record_state, dict) and _record_state["id"] == take_id):
        _record_state = None
    scene.a2b_status = f"Saved {name} ({len(sampled)} frames)"


def _process_event(scene: bpy.types.Scene, message: dict) -> dict | None:
    global _mapper, _centered_camera, _last_phone, _record_state, _prepared, _last_frame_tick
    kind = message["type"]
    if kind == "connection_lost":
        _prepared = None
        if isinstance(_record_state, dict) and _record_state["active"]:
            _stop_playback(_record_state["scene"])
            _record_state["active"] = False
            _record_state["end_frame"] = _record_state["scene"].frame_current
        scene.a2b_status = "Phone disconnected; recording paused"
        return
    if kind == "take":
        _save_take(scene, message)
        return
    if kind == "pause":
        if isinstance(_record_state, dict) and _record_state["active"]:
            _stop_playback(_record_state["scene"])
            _record_state["active"] = False
        scene.a2b_status = "Tracking lost: recording paused"
        return
    if kind == "scale":
        scene.a2b_scale = float(message["value"])
        return
    if kind == "record_stop":
        if not isinstance(_record_state, dict) or _record_state["id"] != message["id"]:
            raise ValueError("Recording ID does not match")
        recorded_scene = _record_state["scene"]
        _stop_playback(recorded_scene)
        _record_state["active"] = False
        _record_state["end_frame"] = recorded_scene.frame_current
        scene.a2b_status = "Recording stopped; waiting for take"
        return {"type": "record_stopped", "id": message["id"], "frame": recorded_scene.frame_current,
                "server_time_ns": time.monotonic_ns()}
    if kind == "record_cancel":
        if _prepared is not None and _prepared["id"] == message["id"]:
            _prepared = None
        elif isinstance(_record_state, dict) and _record_state["id"] == message["id"]:
            recorded_scene = _record_state["scene"]
            _stop_playback(recorded_scene)
            camera = _record_state["camera"]
            recorded_scene.camera = _record_state["source"]
            lens = camera.data
            bpy.data.objects.remove(camera, do_unlink=True)
            bpy.data.cameras.remove(lens, do_unlink=True)
            _record_state = None
            _mapper = None
            _centered_camera = None
        scene.a2b_status = "Recording cancelled"
        return
    if kind == "optics":
        if not isinstance(_record_state, dict):
            raise ValueError("Start recording before changing the lens")
        lens = _record_state["camera"].data
        lens.lens = float(message["lens"])
        lens.dof.focus_distance = float(message["focus_distance"])
        lens.dof.aperture_fstop = float(message["fstop"])
        lens.dof.use_dof = True
        return
    if kind == "record_prepare":
        camera = scene.camera
        if camera is None or camera.type != "CAMERA" or camera.data.type != "PERSP":
            raise ValueError("Select a perspective camera in Blender")
        if camera.parent is not None or any(not constraint.mute and constraint.influence > 0
                                            for constraint in camera.constraints):
            raise ValueError("Choose a camera without a parent or active constraints")
        if _record_state is not None:
            raise ValueError("Finish the current take before recording")
        if _playback_window(scene) is None:
            raise ValueError("Open a Blender window to play the timeline")
        if (scene.frame_preview_end if scene.use_preview_range else scene.frame_end) <= scene.frame_current:
            raise ValueError("Move the timeline before its end frame to record")
        _stop_playback(scene)
        phone = Pose.from_json(message)
        scale = float(message.get("scale", scene.a2b_scale))
        snapshot = _snapshot(scene, camera, phone, scale, message["id"])
        _prepared = {"id": message["id"], "source": camera,
                     "snapshot": snapshot, "scale": scale}
        scene.a2b_status = "Ready for recording countdown"
        return {"type": "record_ready", "id": message["id"], "snapshot": snapshot}
    if kind == "record_go":
        if _prepared is None or _prepared["id"] != message["id"]:
            raise ValueError("Prepare the recording before starting")
        source = _prepared["source"]
        phone = Pose.from_json(message)
        snapshot = _prepared["snapshot"]
        camera = _take_camera(scene, source, message["id"])
        snapshot["tracking"]["phone_anchor"] = {"p": list(phone.position),
                                                   "q": list(phone.rotation)}
        snapshot["camera"]["take_uuid"] = _camera_uuid(camera)
        try:
            _start_playback(scene)
        except Exception:
            scene.camera = source
            lens = camera.data
            bpy.data.objects.remove(camera, do_unlink=True)
            bpy.data.cameras.remove(lens, do_unlink=True)
            raise
        anchor = _camera_pose(camera)
        _mapper = PoseMapper(phone, anchor, _prepared["scale"])
        _centered_camera = camera
        _record_state = {"id": message["id"], "scene": scene, "camera": camera, "source": source,
                         "snapshot": snapshot,
                         "active": True, "end_frame": None,
                         "started_ns": time.monotonic_ns()}
        _last_frame_tick = -1
        _prepared = None
        scene.a2b_status = "Recording with timeline playback"
        return {"type": "record_started", "id": message["id"],
                "snapshot": snapshot, "frame": scene.frame_current,
                "server_time_ns": time.monotonic_ns()}
    if kind == "create_camera":
        phone = Pose.from_json(message)
        camera = _create_camera(scene, message["mode"])
        _last_phone = phone
        _mapper = PoseMapper(phone, _camera_pose(camera), scene.a2b_scale)
        _centered_camera = camera
        scene.a2b_status = f"Camera ready: {camera.name}"
        return
    camera = scene.camera
    if camera is None:
        raise ValueError("Select a camera in the Action2Blender panel")
    if camera.parent is not None:
        raise ValueError("The camera has a parent object; choose a free camera")
    if any(not constraint.mute and constraint.influence > 0 for constraint in camera.constraints):
        raise ValueError("The camera has active constraints; disable them or choose a free camera")
    if kind in {"pose", "recenter", "resume"}:
        phone = Pose.from_json(message)
        _last_phone = phone
        if kind == "recenter":
            _mapper = PoseMapper(phone, _camera_pose(camera), scene.a2b_scale)
            _centered_camera = camera
            scene.a2b_status = "Camera centered"
        elif _mapper is None or camera != _centered_camera:
            scene.a2b_status = "Press Recenter on the phone"
        elif kind == "resume":
            # With an ID this is "Resume" after a pause and restarts the timeline. Without one it is
            # a tracking correction (ARCore relocalized): only realign, whatever the recording state.
            recording = _record_state if isinstance(_record_state, dict) else None
            restart = recording is not None and bool(message.get("id")) and not recording["active"]
            if recording is not None and message.get("id") and message["id"] != recording["id"]:
                raise ValueError("Recording ID does not match")
            if restart and scene is not recording["scene"]:
                raise ValueError("Return to the recording scene before resuming")
            _mapper.reanchor(phone)
            if restart:
                _start_playback(scene)
                recording["active"] = True
            scene.a2b_status = "Tracking resumed"
            return {"type": "record_resumed", "id": message.get("id", ""),
                    "frame": scene.frame_current, "server_time_ns": time.monotonic_ns()}
        else:
            _mapper.scale = scene.a2b_scale
            _apply_pose(camera, map_navigation(_mapper, phone, message))
    elif kind == "record_start":
        if _mapper is None or camera != _centered_camera:
            raise ValueError("Press Recenter before recording")
        phone = Pose.from_json(message)
        _last_phone = phone
        scene.a2b_scale = float(message.get("scale", scene.a2b_scale))
        anchor = _camera_pose(camera)
        _mapper = PoseMapper(phone, anchor, scene.a2b_scale)
        _record_state = (phone, anchor, scene.a2b_scale, scene.frame_current, camera)
        scene.a2b_status = "Recording on phone"


def _poll_events() -> float | None:
    global _last_frame_tick, _record_state
    if _server is None:
        return None
    scene = bpy.context.scene
    if scene is None:
        return 0.04
    if isinstance(_record_state, dict) and _record_state["active"] and scene is not _record_state["scene"]:
        recorded_scene = _record_state["scene"]
        _stop_playback(recorded_scene)
        _record_state["active"] = False
        _record_state["end_frame"] = recorded_scene.frame_current
        _server.broadcast({"type": "record_stopped", "id": _record_state["id"],
                           "frame": recorded_scene.frame_current, "partial": True,
                           "server_time_ns": time.monotonic_ns()})
    if isinstance(_record_state, dict) and _record_state["active"]:
        frame = scene.frame_current
        if frame != _last_frame_tick:
            _last_frame_tick = frame
            _server.broadcast({"type": "frame_tick", "id": _record_state["id"],
                               "frame": frame, "server_time_ns": time.monotonic_ns()})
        end_frame = _record_state["snapshot"]["scene"]["playback_end_frame"]
        window = _playback_window(scene)
        if frame >= end_frame or (window is not None and not window.screen.is_animation_playing):
            _stop_playback(scene)
            _record_state["active"] = False
            _record_state["end_frame"] = frame
            _server.broadcast({"type": "record_stopped", "id": _record_state["id"],
                                "frame": frame, "server_time_ns": time.monotonic_ns()})
    if (
        _viewport_server is not None
        and _viewport_server.frames.active_width() is not None
        and time.monotonic() - _last_capture >= _capture_interval
    ):
        areas = [
            area for window in bpy.context.window_manager.windows
            for area in window.screen.areas if area.type == "VIEW_3D"
        ]
        if areas:
            for area in areas:
                area.tag_redraw()
        else:
            _viewport_server.frames.set_error("Open a 3D View in Blender")
    for _ in range(80):
        try:
            message = _server.events.get_nowait()
        except queue.Empty:
            break
        response_queue = message.pop("_response", None)
        try:
            result = _process_event(scene, message)
            if response_queue is not None:
                if result is not None:
                    response_queue.put(result)
                elif message["type"] in {"recenter", "create_camera"}:
                    response_queue.put({"type": "recenter_ok", "camera": scene.camera.name})
                elif message["type"] == "take":
                    response_queue.put({"type": "take_saved", "id": message["id"]})
                else:
                    response_queue.put({"type": "ack", "message_type": message["type"]})
        except Exception as exc:
            scene.a2b_status = f"Action2Blender: {exc}"
            if (message["type"] == "take" and isinstance(_record_state, dict)
                    and _record_state["id"] == message.get("id")):
                # A take Blender cannot import must not block later recordings: its recording ends here.
                if _record_state["active"]:
                    _stop_playback(_record_state["scene"])
                _record_state = None
                scene.a2b_status = f"Take not imported: {exc}"[:120]
            if response_queue is not None:
                response_queue.put({
                    "type": "error",
                    "message_type": message["type"],
                    "message": str(exc)[:160],
                })
    return 0.04


_carried_pairing: tuple[str, str, int] | None = None


@persistent
def _before_file_load(_filepath) -> None:
    """End a running recording cleanly: its objects belong to the file being closed."""
    global _carried_pairing
    if _server is None:
        return
    scene = bpy.context.scene
    if scene is not None:
        _carried_pairing = (scene.a2b_token, scene.a2b_host, scene.a2b_port)
    if isinstance(_record_state, dict) and _record_state["active"]:
        recorded_scene = _record_state["scene"]
        _stop_playback(recorded_scene)
        _record_state["active"] = False
        _server.broadcast({"type": "record_stopped", "id": _record_state["id"],
                           "frame": recorded_scene.frame_current, "partial": True,
                           "server_time_ns": time.monotonic_ns()})


@persistent
def _after_file_load(_filepath) -> None:
    """Drop references into the closed file and keep the running connection's pairing visible."""
    global _mapper, _centered_camera, _last_phone, _record_state, _prepared, _last_frame_tick
    global _carried_pairing
    if _server is None:
        return
    _mapper = None
    _centered_camera = None
    _last_phone = None
    _record_state = None
    _prepared = None
    _last_frame_tick = -1
    scene = bpy.context.scene
    if scene is not None:
        if _carried_pairing is not None:
            scene.a2b_token, scene.a2b_host, scene.a2b_port = _carried_pairing
        scene.a2b_status = "Another file was opened: press Recenter on the phone"
    _carried_pairing = None


class A2B_Take(bpy.types.PropertyGroup):
    action_name: StringProperty()
    camera_name: StringProperty()
    start_frame: IntProperty()
    end_frame: IntProperty()
    is_stabilized: BoolProperty(default=False)
    source_action_name: StringProperty()
    take_id: StringProperty()
    lens_action_name: StringProperty()
    is_partial: BoolProperty(default=False)


class A2B_OT_start(bpy.types.Operator):
    bl_idname = "a2b.start"
    bl_label = "Start phone connection"

    def execute(self, context: bpy.types.Context):
        global _server, _viewport_server, _capture_handler
        global _mapper, _centered_camera, _last_phone, _record_state, _prepared
        global _last_capture, _capture_interval
        if _server is not None:
            return {"CANCELLED"}
        scene = context.scene
        token = secrets.token_hex(8)
        try:
            _server = PoseServer("0.0.0.0", scene.a2b_port, token)
            _viewport_server = ViewportServer("0.0.0.0", token)
            _server.viewport_port = _viewport_server.server_address[1]
            _capture_handler = bpy.types.SpaceView3D.draw_handler_add(
                _draw_capture, (), "WINDOW", "POST_PIXEL"
            )
            _viewport_server.start()
            _server.start()
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            _stop_viewport()
            if _server is not None:
                _server.server_close()
            _server = None
            return {"CANCELLED"}
        _mapper = None
        _last_capture = 0.0
        _capture_interval = 0.10
        _centered_camera = None
        _last_phone = None
        _record_state = None
        _prepared = None
        if scene.a2b_widescreen:
            width = max(16, round(scene.render.resolution_x / 16) * 16)
            scene.render.resolution_x = width
            scene.render.resolution_y = width * 9 // 16
            scene.render.pixel_aspect_x = 1.0
            scene.render.pixel_aspect_y = 1.0
        scene.a2b_token = token
        scene.a2b_host = _local_ip()
        scene.a2b_status = "Waiting for phone"
        if not bpy.app.timers.is_registered(_poll_events):
            # Persistent: opening another .blend must not silently stop command processing.
            bpy.app.timers.register(_poll_events, first_interval=0.04, persistent=True)
        return {"FINISHED"}


class A2B_OT_stop(bpy.types.Operator):
    bl_idname = "a2b.stop"
    bl_label = "Stop phone connection"

    def execute(self, context: bpy.types.Context):
        global _server, _prepared, _record_state
        if isinstance(_record_state, dict) and _record_state["active"]:
            _stop_playback(_record_state["scene"])
        _prepared = None
        _record_state = None
        if _server is not None:
            _server.stop()
            _server = None
        _stop_viewport()
        context.scene.a2b_token = ""
        _clear_qr()
        context.scene.a2b_status = "Connection stopped"
        return {"FINISHED"}


class A2B_OT_select_take(bpy.types.Operator):
    bl_idname = "a2b.select_take"
    bl_label = "Select take"

    index: IntProperty()

    def execute(self, context: bpy.types.Context):
        context.scene.a2b_take_index = self.index
        return {"FINISHED"}


class A2B_OT_stabilize_take(bpy.types.Operator):
    bl_idname = "a2b.stabilize_take"
    bl_label = "Stabilize selected take"
    bl_description = "Create a stabilized Action while keeping the original recording"

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        index = scene.a2b_take_index
        if not 0 <= index < len(scene.a2b_takes):
            self.report({"ERROR"}, "Select a take first")
            return {"CANCELLED"}
        if scene.a2b_stabilization_strength <= 0:
            self.report({"ERROR"}, "Increase strength above zero")
            return {"CANCELLED"}
        item = scene.a2b_takes[index]
        if item.end_frame - item.start_frame < 2:
            self.report({"ERROR"}, "The take is too short to stabilize")
            return {"CANCELLED"}
        camera = bpy.data.objects.get(item.camera_name)
        source_name = item.source_action_name or item.action_name
        source = bpy.data.actions.get(source_name)
        if camera is None or source is None:
            self.report({"ERROR"}, "Camera or original Action not found")
            return {"CANCELLED"}
        fps = scene.render.fps / scene.render.fps_base
        try:
            samples = _sample_action(scene, camera, source, item.start_frame, item.end_frame)
            smoothed = stabilize_take(samples, fps, scene.a2b_stabilization_strength)
            base_name = source.name.removesuffix(" - Original").removesuffix(" - Originale")
            action = _write_take_action(camera, f"{base_name} - Stabilized",
                                        smoothed, item.start_frame)
            _add_take_item(scene, camera, action, item.start_frame, item.end_frame,
                           True, source.name, item.take_id, item.lens_action_name,
                           item.is_partial)
            scene.a2b_take_index = len(scene.a2b_takes) - 1
            scene.a2b_status = f"Stabilized: {action.name}"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class A2B_PT_panel(bpy.types.Panel):
    bl_label = "Action2Blender"
    bl_idname = "A2B_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Action2Blender"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "camera", text="Camera")
        layout.prop(scene, "a2b_widescreen", text="16:9 framing")
        layout.prop(scene, "a2b_scale", text="Movement scale")
        port_row = layout.row()
        port_row.enabled = _server is None
        port_row.prop(scene, "a2b_port", text="Port")
        if _server is None:
            layout.operator("a2b.start", icon="PLAY")
        else:
            layout.operator("a2b.stop", icon="PAUSE")
            layout.prop(scene, "a2b_host", text="PC IP address")
            layout.label(text=f"Pairing code: {scene.a2b_token}")
            try:
                layout.template_icon(icon_value=_pairing_icon(scene), scale=8.0)
                layout.label(text="Scan with Action2Blender")
            except ValueError:
                layout.label(text="Enter a valid IPv4 address for the QR code", icon="ERROR")
        layout.label(text=scene.a2b_status[:60])
        layout.separator()
        layout.prop(scene, "a2b_auto_stabilize", text="Stabilize after Stop")
        layout.prop(scene, "a2b_stabilization_strength", text="Strength")
        layout.label(text="Recorded takes")
        for index, take in enumerate(scene.a2b_takes):
            row = layout.row()
            label = f"{take.name} (partial)" if take.is_partial else take.name
            row.operator("a2b.select_take", text=label, depress=index == scene.a2b_take_index).index = index
            row.label(text=f"{take.start_frame}–{take.end_frame}")
        stabilize_row = layout.row()
        stabilize_row.enabled = 0 <= scene.a2b_take_index < len(scene.a2b_takes)
        stabilize_row.operator("a2b.stabilize_take", icon="MOD_SMOOTH")


_CLASSES = (A2B_Take, A2B_OT_start, A2B_OT_stop, A2B_OT_select_take,
            A2B_OT_stabilize_take, A2B_PT_panel)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.a2b_takes = CollectionProperty(type=A2B_Take)
    bpy.types.Scene.a2b_take_index = IntProperty(default=-1, update=_take_index_changed)
    bpy.types.Scene.a2b_port = IntProperty(default=45767, min=1024, max=65535)
    bpy.types.Scene.a2b_scale = FloatProperty(default=1.0, min=0.01, max=100.0)
    bpy.types.Scene.a2b_widescreen = BoolProperty(default=True)
    bpy.types.Scene.a2b_auto_stabilize = BoolProperty(default=True)
    bpy.types.Scene.a2b_stabilization_strength = FloatProperty(default=0.5, min=0.0, max=1.0, subtype="FACTOR")
    bpy.types.Scene.a2b_token = StringProperty(default="")
    bpy.types.Scene.a2b_host = StringProperty(default="")
    bpy.types.Scene.a2b_status = StringProperty(default="Not connected")
    bpy.app.handlers.load_pre.append(_before_file_load)
    bpy.app.handlers.load_post.append(_after_file_load)


def unregister() -> None:
    global _server, _prepared, _record_state
    for handlers, handler in ((bpy.app.handlers.load_pre, _before_file_load),
                              (bpy.app.handlers.load_post, _after_file_load)):
        if handler in handlers:
            handlers.remove(handler)
    if isinstance(_record_state, dict) and _record_state["active"]:
        _stop_playback(_record_state["scene"])
    _prepared = None
    _record_state = None
    if _server is not None:
        _server.stop()
        _server = None
    _stop_viewport()
    _clear_qr()
    for name in ("a2b_status", "a2b_host", "a2b_token", "a2b_scale", "a2b_widescreen",
                 "a2b_auto_stabilize", "a2b_stabilization_strength", "a2b_port",
                 "a2b_take_index", "a2b_takes"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
