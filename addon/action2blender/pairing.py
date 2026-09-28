"""Compact local pairing URI and dependency-free QR PNG creation."""

from __future__ import annotations

import ipaddress
import re
import struct
import zlib

from ._qrcodegen import QrCode


def pairing_uri(host: str, port: int, token: str) -> str:
    parsed = ipaddress.IPv4Address(host.strip())
    address = str(parsed)
    if parsed.is_loopback or parsed.is_unspecified or parsed.is_multicast or parsed.is_reserved:
        raise ValueError("Enter an IPv4 address reachable from the phone")
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token):
        raise ValueError("Invalid pairing code")
    return f"a2b://{address}:{port}?v=1&t={token}"


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def qr_png(payload: str, module_pixels: int = 8, border: int = 4) -> bytes:
    if not 2 <= module_pixels <= 20 or border < 4:
        raise ValueError("Invalid QR dimensions")
    qr = QrCode.encode_text(payload, QrCode.Ecc.MEDIUM)
    modules = qr.get_size() + 2 * border
    pixels = modules * module_pixels
    raw = bytearray()
    for y in range(modules):
        module_row = bytes(
            (0 if qr.get_module(x - border, y - border) else 255)
            for x in range(modules)
        )
        row = b"\x00" + b"".join(bytes((value,)) * module_pixels for value in module_row)
        raw.extend(row * module_pixels)
    header = struct.pack(">IIBBBBB", pixels, pixels, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, level=9))
        + _chunk(b"IEND", b"")
    )
