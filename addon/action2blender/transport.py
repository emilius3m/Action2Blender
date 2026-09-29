"""Small authenticated JSON-lines server for the local Android connection."""

from __future__ import annotations

import json
import math
import queue
import socketserver
import threading
from typing import Any


PROTOCOL_VERSION = 1
CAMERA_CONTROL_VERSION = 3  # 3: gravity-aligned mapping, joystick travel in ARCore world axes
MAX_MESSAGE_BYTES = 8 * 1024 * 1024  # full takes are sent after Stop
MAX_TAKE_EVENTS = 100_000


def _validate_scale(value: Any) -> float:
    scale = float(value)
    if not math.isfinite(scale) or not 0.01 <= scale <= 100.0:
        raise ValueError("Invalid movement scale")
    return scale


def validate_message(message: Any) -> dict:
    if not isinstance(message, dict):
        raise ValueError("Message must be an object")
    kind = message.get("type")
    if kind in {"pose", "recenter", "resume", "record_start", "create_camera"}:
        from .core import Pose, navigation_from_json

        Pose.from_json(message)
        navigation_from_json(message)
        if kind == "create_camera" and message.get("mode") not in {"view", "subject"}:
            raise ValueError("Invalid camera placement mode")
        if kind == "record_start" and "scale" in message:
            _validate_scale(message["scale"])
    elif kind == "take":
        events = message.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= MAX_TAKE_EVENTS:
            raise ValueError("Invalid take length")
        if not isinstance(message.get("id"), str) or not 1 <= len(message["id"]) <= 100:
            raise ValueError("Invalid take ID")
    elif kind == "scale":
        _validate_scale(message.get("value"))
    elif kind != "pause":
        raise ValueError("Unknown message type")
    return message


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: "PoseServer" = self.server  # type: ignore[assignment]
        authenticated = False
        self.request.settimeout(15)
        while True:
            line = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
            if not line:
                return
            if len(line) > MAX_MESSAGE_BYTES or not line.endswith(b"\n"):
                self._reply({"type": "error", "message": "Message too large"})
                return
            try:
                message = json.loads(line)
                if not authenticated:
                    if (
                        not isinstance(message, dict)
                        or message.get("type") != "hello"
                        or message.get("version") != PROTOCOL_VERSION
                        or message.get("token") != server.token
                    ):
                        self._reply({"type": "error", "message": "Pairing failed"})
                        return
                    if message.get("camera_control") != CAMERA_CONTROL_VERSION:
                        # Older apps send joystick travel in another frame; mixing them would misplace takes.
                        self._reply({"type": "error", "message": "Update the Action2Blender app on your phone"})
                        return
                    authenticated = True
                    self.request.settimeout(None)
                    self._reply({
                        "type": "hello_ok",
                        "version": PROTOCOL_VERSION,
                        "viewport_port": server.viewport_port,
                        "recenter_ack": True,
                        "camera_control": CAMERA_CONTROL_VERSION,
                    })
                    continue
                validated = validate_message(message)
                response_queue = None
                if validated["type"] in {"take", "recenter", "create_camera"}:
                    response_queue = queue.Queue(maxsize=1)
                    validated["_response"] = response_queue
                if validated["type"] == "pose":
                    try:
                        server.events.put_nowait(validated)
                    except queue.Full:
                        pass  # live poses may be dropped; the final take remains on the phone
                else:
                    server.events.put(validated, timeout=2)
                if response_queue is None:
                    self._reply({"type": "ack", "message_type": validated["type"]})
                else:
                    try:
                        response = response_queue.get(timeout=120 if validated["type"] == "take" else 10)
                    except queue.Empty:
                        response = {
                            "type": "error",
                            "message_type": validated["type"],
                            "message": "Blender did not confirm the command",
                        }
                    self._reply(response)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, queue.Full, queue.Empty) as exc:
                self._reply({"type": "error", "message": str(exc)[:160]})

    def _reply(self, value: dict) -> None:
        self.wfile.write(json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n")


class PoseServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, token: str):
        if not token:
            raise ValueError("Pairing token required")
        self.token = token
        self.viewport_port = 0
        self.events: queue.Queue[dict] = queue.Queue(maxsize=1024)
        super().__init__((host, port), _Handler)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, name="Action2Blender socket", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
