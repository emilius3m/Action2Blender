"""Small authenticated JSON-lines server for the local Android connection."""

from __future__ import annotations

import json
import base64
import binascii
import hashlib
import math
import queue
import secrets
import socketserver
import threading
import time
from typing import Any


PROTOCOL_VERSION = 1
CAMERA_CONTROL_VERSION = 4  # 4: timeline, optics and recoverable take metadata
MAX_HELLO_BYTES = 4 * 1024  # before pairing, only a short hello is accepted
MAX_MESSAGE_BYTES = 256 * 1024  # takes travel as take_begin/take_chunk/take_end, not one line
CLIENT_TIMEOUT_SECONDS = 30  # the phone pings every 2 s; silence this long means a dead link
MAX_TAKE_EVENTS = 100_000
MAX_TAKE_BYTES = 64 * 1024 * 1024
MAX_CHUNK_BYTES = 48 * 1024


def _validate_scale(value: Any) -> float:
    scale = float(value)
    if not math.isfinite(scale) or not 0.01 <= scale <= 100.0:
        raise ValueError("Invalid movement scale")
    return scale


def validate_message(message: Any) -> dict:
    if not isinstance(message, dict):
        raise ValueError("Message must be an object")
    kind = message.get("type")
    if kind in {"pose", "recenter", "resume", "record_start", "create_camera", "record_prepare", "record_go"}:
        from .core import Pose, navigation_from_json

        Pose.from_json(message)
        navigation_from_json(message)
        if kind == "create_camera" and message.get("mode") not in {"view", "subject"}:
            raise ValueError("Invalid camera placement mode")
        if kind in {"record_start", "record_prepare"} and "scale" in message:
            _validate_scale(message["scale"])
        if kind in {"record_prepare", "record_go"} and not (
            isinstance(message.get("id"), str) and 1 <= len(message["id"]) <= 100
        ):
            raise ValueError("Take ID required")
    elif kind == "take":
        events = message.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= MAX_TAKE_EVENTS:
            raise ValueError("Invalid take length")
        if not isinstance(message.get("id"), str) or not 1 <= len(message["id"]) <= 100:
            raise ValueError("Invalid take ID")
    elif kind == "scale":
        _validate_scale(message.get("value"))
    elif kind == "optics":
        for key, lower, upper in (("lens", 1, 500), ("focus_distance", 0.01, 100_000),
                                  ("fstop", 0.1, 64)):
            value = float(message.get(key))
            if not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError("Invalid camera optics")
    elif kind in {"record_stop", "record_cancel"}:
        if not isinstance(message.get("id"), str) or not 1 <= len(message["id"]) <= 100:
            raise ValueError("Take ID required")
    elif kind == "take_begin":
        if not isinstance(message.get("id"), str) or not 1 <= len(message["id"]) <= 100:
            raise ValueError("Invalid take ID")
        if not isinstance(message.get("size"), int) or not 1 <= message["size"] <= MAX_TAKE_BYTES:
            raise ValueError("Invalid take size")
        if not isinstance(message.get("sha256"), str) or len(message["sha256"]) != 64:
            raise ValueError("Invalid take checksum")
    elif kind == "take_chunk":
        if not isinstance(message.get("id"), str) or not isinstance(message.get("index"), int):
            raise ValueError("Invalid take chunk")
        if not isinstance(message.get("data"), str) or len(message["data"]) > MAX_CHUNK_BYTES * 2:
            raise ValueError("Invalid take chunk")
    elif kind == "take_end":
        if not isinstance(message.get("id"), str):
            raise ValueError("Invalid take ID")
    elif kind not in {"pause", "ping"}:
        raise ValueError("Unknown message type")
    return message


class _Handler(socketserver.StreamRequestHandler):
    def finish(self) -> None:
        server: "PoseServer" = self.server  # type: ignore[assignment]
        try:
            super().finish()
        finally:
            if server.client is self:
                server.client = None
                try:
                    server.events.put_nowait({"type": "connection_lost"})
                except queue.Full:
                    pass

    def handle(self) -> None:
        server: "PoseServer" = self.server  # type: ignore[assignment]
        self._write_lock = threading.Lock()
        authenticated = False
        self.request.settimeout(15)
        while True:
            limit = MAX_MESSAGE_BYTES if authenticated else MAX_HELLO_BYTES
            try:
                line = self.rfile.readline(limit + 1)
            except OSError:
                return  # silent client: finish() reports the lost connection
            if not line:
                return
            if len(line) > limit or not line.endswith(b"\n"):
                self._reply({"type": "error", "message": "Message too large"})
                return
            message = None
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
                    if server.client is not None and server.client is not self:
                        server.events.put_nowait({"type": "connection_lost"})
                        server.client.request.close()
                    server.client = self
                    self.request.settimeout(CLIENT_TIMEOUT_SECONDS)
                    self._reply({
                        "type": "hello_ok",
                        "version": PROTOCOL_VERSION,
                        "viewport_port": server.viewport_port,
                        "recenter_ack": True,
                        "camera_control": CAMERA_CONTROL_VERSION,
                        "session_id": server.session_id,
                    })
                    continue
                validated = validate_message(message)
                if validated["type"] == "ping":
                    self._reply({"type": "pong", "id": validated.get("id"),
                                 "server_time_ns": time.monotonic_ns()})
                    continue
                if validated["type"] == "take_begin":
                    self._reply({"type": "take_next", "id": validated["id"],
                                 "index": server.begin_take(validated)})
                    continue
                if validated["type"] == "take_chunk":
                    self._reply({"type": "take_next", "id": validated["id"],
                                 "index": server.add_take_chunk(validated)})
                    continue
                if validated["type"] == "take_end":
                    validated = server.complete_take(validated["id"])
                response_queue = None
                if validated["type"] in {"take", "recenter", "create_camera",
                                         "record_prepare", "record_go", "record_stop", "resume"}:
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
                    threading.Thread(target=self._wait_response,
                                     args=(server, response_queue, validated), daemon=True).start()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, queue.Full, queue.Empty) as exc:
                self._reply({"type": "error", "message": str(exc)[:160],
                             "message_type": message.get("type", "") if isinstance(message, dict) else ""})

    def _reply(self, value: dict) -> None:
        with self._write_lock:
            self.wfile.write(json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n")

    def push(self, value: dict) -> None:
        self._reply(value)

    def _wait_response(self, server: "PoseServer", replies: queue.Queue, message: dict) -> None:
        try:
            response = replies.get(timeout=120 if message["type"] == "take" else 10)
        except queue.Empty:
            response = {"type": "error", "message_type": message["type"],
                        "message": "Blender did not confirm the command"}
        try:
            self._reply(response)
        except (OSError, ValueError):
            pass
        if message["type"] == "take" and response.get("type") == "take_saved":
            server.clear_take(message["id"])


class PoseServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, token: str):
        if not token:
            raise ValueError("Pairing token required")
        self.token = token
        self.viewport_port = 0
        self.session_id = secrets.token_hex(8)
        self.client: _Handler | None = None
        self._takes: dict[str, dict] = {}
        self._takes_lock = threading.Lock()
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

    def broadcast(self, value: dict) -> None:
        client = self.client
        if client is not None:
            try:
                client.push(value)
            except (OSError, ValueError):
                if self.client is client:
                    self.client = None

    def begin_take(self, message: dict) -> int:
        with self._takes_lock:
            item = self._takes.get(message["id"])
            if item is None:
                if len(self._takes) >= 4:
                    raise ValueError("Too many pending take transfers")
                item = {"size": message["size"], "sha256": message["sha256"],
                        "data": bytearray(), "next": 0}
                self._takes[message["id"]] = item
            elif item["size"] != message["size"] or item["sha256"] != message["sha256"]:
                raise ValueError("Take ID has different content")
            return item["next"]

    def add_take_chunk(self, message: dict) -> int:
        with self._takes_lock:
            item = self._takes.get(message["id"])
            if item is None:
                raise ValueError("Send take_begin before chunks")
            index = message["index"]
            if index < item["next"]:
                return item["next"]
            if index != item["next"]:
                raise ValueError("Unexpected take chunk index")
            try:
                chunk = base64.b64decode(message["data"], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Invalid take chunk encoding") from exc
            if not 1 <= len(chunk) <= MAX_CHUNK_BYTES:
                raise ValueError("Invalid take chunk size")
            if len(item["data"]) + len(chunk) > item["size"]:
                raise ValueError("Take exceeds declared size")
            item["data"].extend(chunk)
            item["next"] += 1
            return item["next"]

    def complete_take(self, take_id: str) -> dict:
        with self._takes_lock:
            item = self._takes.get(take_id)
            if item is None or len(item["data"]) != item["size"]:
                raise ValueError("Take transfer is incomplete")
            data = bytes(item["data"])
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("Take checksum does not match")
        message = validate_message(json.loads(data))
        if message["type"] != "take" or message["id"] != take_id:
            raise ValueError("Take ID does not match transfer")
        return message

    def clear_take(self, take_id: str) -> None:
        with self._takes_lock:
            self._takes.pop(take_id, None)
