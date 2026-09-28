"""Action2Blender: live Android camera control and non-destructive takes."""

import queue
import secrets
import socket

import bpy
from bpy.props import CollectionProperty, FloatProperty, IntProperty, StringProperty

from .core import Pose, PoseMapper, sample_take
from .transport import PoseServer


_server: PoseServer | None = None
_mapper: PoseMapper | None = None
_last_phone: Pose | None = None
_record_state: tuple[Pose, Pose, float, int] | None = None
_saved_take_ids: set[str] = set()


def _camera_pose(camera: bpy.types.Object) -> Pose:
    position, rotation, _ = camera.matrix_world.decompose()
    return Pose(tuple(position), (rotation.x, rotation.y, rotation.z, rotation.w))


def _apply_pose(camera: bpy.types.Object, pose: Pose) -> None:
    camera.location = pose.position
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = (pose.rotation[3], *pose.rotation[:3])


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


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
    camera.animation_data.action = action
    if len(action.slots):
        camera.animation_data.action_slot = action.slots[0]
    scene.camera = camera
    scene.frame_set(item.start_frame)
    scene.a2b_status = f"Selected {item.name}"


def _take_index_changed(scene: bpy.types.Scene, _context: bpy.types.Context) -> None:
    _select_take(scene, scene.a2b_take_index)


def _save_take(scene: bpy.types.Scene, message: dict) -> None:
    global _record_state
    if _record_state is None:
        raise ValueError("No recording start received")
    if message["id"] in _saved_take_ids:
        scene.a2b_status = "Take already received"
        return
    camera = scene.camera
    if camera is None:
        raise ValueError("Select a scene camera")
    anchor, initial, scale, start_frame = _record_state
    fps = scene.render.fps / scene.render.fps_base
    sampled = sample_take(message["events"], PoseMapper(anchor, initial, scale), fps)
    action = bpy.data.actions.new(name=f"A2B Take {len(scene.a2b_takes) + 1:03d}")
    action.use_fake_user = True
    camera.animation_data_create()
    camera.animation_data.action = action
    for offset, pose in sampled:
        _apply_pose(camera, pose)
        camera.keyframe_insert(data_path="location", frame=start_frame + offset, group="Action2Blender")
        camera.keyframe_insert(data_path="rotation_quaternion", frame=start_frame + offset, group="Action2Blender")
    item = scene.a2b_takes.add()
    item.name = action.name
    item.action_name = action.name
    item.camera_name = camera.name
    item.start_frame = start_frame
    item.end_frame = start_frame + sampled[-1][0]
    scene.a2b_take_index = len(scene.a2b_takes) - 1
    scene.frame_end = max(scene.frame_end, item.end_frame)
    _saved_take_ids.add(message["id"])
    _record_state = None
    scene.a2b_status = f"Saved {item.name} ({len(sampled)} frames)"


def _process_event(scene: bpy.types.Scene, message: dict) -> None:
    global _mapper, _last_phone, _record_state
    camera = scene.camera
    if camera is None:
        raise ValueError("Select a scene camera first")
    if camera.parent is not None:
        raise ValueError("Version 0.1 needs a camera without a parent")
    kind = message["type"]
    if kind in {"pose", "recenter", "resume"}:
        phone = Pose.from_json(message)
        _last_phone = phone
        if kind == "recenter" or _mapper is None:
            _mapper = PoseMapper(phone, _camera_pose(camera), scene.a2b_scale)
            scene.a2b_status = "Camera centered"
        elif kind == "resume":
            _mapper.reanchor(phone)
            scene.a2b_status = "Tracking resumed"
        else:
            _mapper.scale = scene.a2b_scale
            _apply_pose(camera, _mapper.map(phone))
    elif kind == "scale":
        scene.a2b_scale = float(message["value"])
    elif kind == "record_start":
        phone = Pose.from_json(message)
        _last_phone = phone
        scene.a2b_scale = float(message.get("scale", scene.a2b_scale))
        _record_state = (phone, _camera_pose(camera), scene.a2b_scale, scene.frame_current)
        scene.a2b_status = "Recording on phone"
    elif kind == "pause":
        scene.a2b_status = "Tracking lost: recording paused"
    elif kind == "take":
        _save_take(scene, message)


def _poll_events() -> float | None:
    if _server is None:
        return None
    scene = bpy.context.scene
    if scene is None:
        return 0.04
    for _ in range(80):
        try:
            message = _server.events.get_nowait()
        except queue.Empty:
            break
        response_queue = message.pop("_response", None)
        try:
            _process_event(scene, message)
            if response_queue is not None:
                response_queue.put({"type": "take_saved", "id": message["id"]})
        except (ValueError, KeyError, TypeError) as exc:
            scene.a2b_status = f"Action2Blender: {exc}"
            if response_queue is not None:
                response_queue.put({"type": "error", "message": str(exc)[:160]})
    return 0.04


class A2B_Take(bpy.types.PropertyGroup):
    action_name: StringProperty()
    camera_name: StringProperty()
    start_frame: IntProperty()
    end_frame: IntProperty()


class A2B_OT_start(bpy.types.Operator):
    bl_idname = "a2b.start"
    bl_label = "Start phone connection"

    def execute(self, context: bpy.types.Context):
        global _server, _mapper, _last_phone, _record_state
        if _server is not None:
            return {"CANCELLED"}
        scene = context.scene
        if scene.camera is None:
            self.report({"ERROR"}, "Select a scene camera first")
            return {"CANCELLED"}
        token = secrets.token_hex(4)
        try:
            _server = PoseServer("0.0.0.0", scene.a2b_port, token)
            _server.start()
        except OSError as exc:
            self.report({"ERROR"}, str(exc))
            _server = None
            return {"CANCELLED"}
        _mapper = None
        _last_phone = None
        _record_state = None
        scene.a2b_token = token
        scene.a2b_host = _local_ip()
        scene.a2b_status = "Waiting for phone"
        bpy.app.timers.register(_poll_events, first_interval=0.04)
        return {"FINISHED"}


class A2B_OT_stop(bpy.types.Operator):
    bl_idname = "a2b.stop"
    bl_label = "Stop phone connection"

    def execute(self, context: bpy.types.Context):
        global _server
        if _server is not None:
            _server.stop()
            _server = None
        context.scene.a2b_token = ""
        context.scene.a2b_status = "Connection stopped"
        return {"FINISHED"}


class A2B_OT_select_take(bpy.types.Operator):
    bl_idname = "a2b.select_take"
    bl_label = "Select take"

    index: IntProperty()

    def execute(self, context: bpy.types.Context):
        context.scene.a2b_take_index = self.index
        return {"FINISHED"}


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
        layout.prop(scene, "a2b_scale", text="Movement scale")
        layout.prop(scene, "a2b_port", text="Port")
        if _server is None:
            layout.operator("a2b.start", icon="PLAY")
        else:
            layout.operator("a2b.stop", icon="PAUSE")
            layout.label(text=f"IP: {scene.a2b_host}")
            layout.label(text=f"Pairing code: {scene.a2b_token}")
        layout.label(text=scene.a2b_status[:60])
        layout.separator()
        layout.label(text="Recorded takes")
        for index, take in enumerate(scene.a2b_takes):
            row = layout.row()
            row.operator("a2b.select_take", text=take.name, depress=index == scene.a2b_take_index).index = index
            row.label(text=f"{take.start_frame}–{take.end_frame}")


_CLASSES = (A2B_Take, A2B_OT_start, A2B_OT_stop, A2B_OT_select_take, A2B_PT_panel)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.a2b_takes = CollectionProperty(type=A2B_Take)
    bpy.types.Scene.a2b_take_index = IntProperty(default=-1, update=_take_index_changed)
    bpy.types.Scene.a2b_port = IntProperty(default=45767, min=1024, max=65535)
    bpy.types.Scene.a2b_scale = FloatProperty(default=1.0, min=0.01, max=100.0)
    bpy.types.Scene.a2b_token = StringProperty(default="")
    bpy.types.Scene.a2b_host = StringProperty(default="")
    bpy.types.Scene.a2b_status = StringProperty(default="Not connected")


def unregister() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None
    for name in ("a2b_status", "a2b_host", "a2b_token", "a2b_scale", "a2b_port", "a2b_take_index", "a2b_takes"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
