"""Pose conversion and take timing, independent of Blender's Python API."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, cos, isfinite, sin, sqrt
from typing import Iterable


Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # x, y, z, w (ARCore order)


def _vec(values: Iterable[float], length: int) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != length or not all(isfinite(value) for value in result):
        raise ValueError(f"Expected {length} finite numbers")
    return result


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Vec3, factor: float) -> Vec3:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def _dot(a: Quat, b: Quat) -> float:
    return sum(x * y for x, y in zip(a, b))


def _normalize(q: Quat) -> Quat:
    length = sqrt(_dot(q, q))
    if length < 1e-9:
        raise ValueError("Zero length quaternion")
    return tuple(value / length for value in q)  # type: ignore[return-value]


def _mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _inverse(q: Quat) -> Quat:
    x, y, z, w = q
    return (-x, -y, -z, w)


def _rotate(q: Quat, v: Vec3) -> Vec3:
    x, y, z, _ = _mul(_mul(q, (v[0], v[1], v[2], 0.0)), _inverse(q))
    return (x, y, z)


def _slerp(a: Quat, b: Quat, alpha: float) -> Quat:
    dot = _dot(a, b)
    if dot < 0.0:
        b = tuple(-value for value in b)  # type: ignore[assignment]
        dot = -dot
    if dot > 0.9995:
        return _normalize(tuple(x + alpha * (y - x) for x, y in zip(a, b)))
    theta = acos(max(-1.0, min(1.0, dot)))
    a_weight = sin((1.0 - alpha) * theta) / sin(theta)
    b_weight = sin(alpha * theta) / sin(theta)
    return tuple(a_weight * x + b_weight * y for x, y in zip(a, b))  # type: ignore[return-value]


@dataclass(frozen=True)
class Pose:
    position: Vec3
    rotation: Quat

    @classmethod
    def from_json(cls, value: dict) -> "Pose":
        return cls(_vec(value["p"], 3), _normalize(_vec(value["q"], 4)))  # type: ignore[arg-type]


class PoseMapper:
    """Map ARCore camera-local changes onto a Blender camera's initial pose.

    Both ARCore's physical camera and Blender's camera use X right, Y up, -Z
    forward locally. Computing the delta in that local basis avoids a global
    Y-up to Z-up conversion and preserves the selected Blender camera heading.
    """

    def __init__(self, phone_anchor: Pose, blender_anchor: Pose, scale: float):
        if not isfinite(scale) or scale <= 0:
            raise ValueError("Movement scale must be positive and finite")
        self.phone_anchor = phone_anchor
        self.blender_anchor = blender_anchor
        self.scale = scale
        self.current = blender_anchor

    def map(self, phone: Pose) -> Pose:
        anchor_inverse = _inverse(self.phone_anchor.rotation)
        local_offset = _rotate(anchor_inverse, _sub(phone.position, self.phone_anchor.position))
        local_rotation = _mul(anchor_inverse, phone.rotation)
        result = Pose(
            _add(self.blender_anchor.position, _rotate(self.blender_anchor.rotation, _scale(local_offset, self.scale))),
            _normalize(_mul(self.blender_anchor.rotation, local_rotation)),
        )
        self.current = result
        return result

    def reanchor(self, phone: Pose) -> None:
        """Continue from the last virtual pose after ARCore relocalizes."""
        self.phone_anchor = phone
        self.blender_anchor = self.current


def sample_take(events: list[dict], mapper: PoseMapper, fps: float) -> list[tuple[int, Pose]]:
    """Return one camera pose per scene frame from active-time phone samples."""
    if not isfinite(fps) or fps <= 0:
        raise ValueError("Frame rate must be positive")
    samples: list[tuple[float, Pose]] = []
    last_time = -1.0
    for event in events:
        moment = float(event["t"])
        if not isfinite(moment) or moment < last_time or moment < 0:
            raise ValueError("Take timestamps must be finite and ordered")
        last_time = moment
        phone = Pose.from_json(event)
        if event.get("kind") == "rebase":
            mapper.reanchor(phone)
        elif event.get("kind", "sample") == "sample":
            mapped = mapper.map(phone)
            if samples and moment == samples[-1][0]:
                samples[-1] = (moment, mapped)
            else:
                samples.append((moment, mapped))
        else:
            raise ValueError("Unknown take event")
    if not samples:
        raise ValueError("Take has no tracked samples")
    last_frame = round(samples[-1][0] * fps)
    result: list[tuple[int, Pose]] = []
    next_sample = 1
    for frame in range(last_frame + 1):
        moment = frame / fps
        while next_sample < len(samples) and samples[next_sample][0] < moment:
            next_sample += 1
        if moment <= samples[0][0]:
            pose = samples[0][1]
        elif next_sample >= len(samples):
            pose = samples[-1][1]
        else:
            left_time, left_pose = samples[next_sample - 1]
            right_time, right_pose = samples[next_sample]
            alpha = (moment - left_time) / (right_time - left_time)
            pose = Pose(
                _add(left_pose.position, _scale(_sub(right_pose.position, left_pose.position), alpha)),
                _slerp(left_pose.rotation, right_pose.rotation, alpha),
            )
        result.append((frame, pose))
    return result
