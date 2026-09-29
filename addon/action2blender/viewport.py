"""Authenticated, latest-frame viewport delivery over the local network."""

from __future__ import annotations

import struct
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))


def encode_rgba_png(width: int, height: int, bottom_up_rgba: bytes) -> bytes:
    """Encode GPU RGBA8 pixels; OpenGL's first row is the image bottom."""
    stride = width * 4
    if width < 1 or height < 1 or len(bottom_up_rgba) != stride * height:
        raise ValueError("Invalid viewport pixels")
    rows = bytearray()
    for y in range(height - 1, -1, -1):
        rows.append(0)
        rows.extend(bottom_up_rgba[y * stride : (y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows, level=1))
        + _png_chunk(b"IEND", b"")
    )


class FrameStore:
    """One frame slot: a slow viewer skips old frames instead of building a queue."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame = b""
        self._sequence = 0
        self._requested_at = 0.0
        self._width = 640
        self._error = ""

    def request(self, width: int) -> None:
        with self._condition:
            self._requested_at = time.monotonic()
            self._width = width

    def active_width(self) -> int | None:
        with self._condition:
            if time.monotonic() - self._requested_at > 3.0:
                return None
            return self._width

    def put(self, frame: bytes) -> None:
        with self._condition:
            self._frame = frame
            self._sequence += 1
            self._error = ""
            self._condition.notify_all()

    def set_error(self, message: str) -> None:
        with self._condition:
            self._error = message[:120]
            self._condition.notify_all()

    def next(self, since: int, timeout: float = 1.5) -> tuple[int, bytes, str]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > since or bool(self._error), timeout=timeout
            )
            if self._error:
                return self._sequence, b"", self._error
            if self._sequence <= since:
                return self._sequence, b"", ""
            return self._sequence, self._frame, ""


class _FrameHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        server: "ViewportServer" = self.server  # type: ignore[assignment]
        if self.headers.get("X-Action2Blender-Token") != server.token:
            self._send(403, b"Pairing code rejected", "text/plain")
            return
        url = urlsplit(self.path)
        if url.path != "/frame":
            self._send(404, b"Not found", "text/plain")
            return
        try:
            query = parse_qs(url.query, strict_parsing=True)
            if set(query) != {"since", "width"}:
                raise ValueError("Invalid viewport request")
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Invalid viewport request")
            since = int(query["since"][0])
            width = int(query["width"][0])
            if since < 0 or width not in (640, 960):
                raise ValueError("Invalid viewport request")
        except (KeyError, ValueError, IndexError):
            self._send(400, b"Invalid viewport request", "text/plain")
            return
        server.frames.request(width)
        sequence, frame, error = server.frames.next(since)
        if error:
            self._send(503, error.encode("utf-8"), "text/plain")
        elif not frame:
            self._send(204, b"", "image/png", sequence)
        else:
            self._send(200, frame, "image/png", sequence)

    def _send(self, code: int, body: bytes, content_type: str, sequence: int = 0) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Seq", str(sequence))
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except OSError:
                pass  # The viewer may have closed while a frame was in flight.

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class ViewportServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, token: str):
        self.token = token
        self.frames = FrameStore()
        super().__init__((host, 0), _FrameHandler)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.serve_forever, name="Action2Blender viewport", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
