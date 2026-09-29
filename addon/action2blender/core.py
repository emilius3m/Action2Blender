"""Pose conversion and take timing, independent of Blender's Python API."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, atan2, ceil, cos, exp, isfinite, sin, sqrt
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


# ARCore's world is Y-up and Blender's is Z-up: +90 degrees about X maps one onto the other.
_BLENDER_FROM_ARCORE: Quat = (sqrt(0.5), 0.0, 0.0, sqrt(0.5))


def _heading(rotation: Quat) -> float:
    """Angle about Blender's Z axis that a camera faces, defined even when it looks straight down."""
    forward = _rotate(rotation, (0.0, 0.0, -1.0))
    up = _rotate(rotation, (0.0, 1.0, 0.0))
    # Pitched by a, a roll-free camera has forward_xy = cos(a)·h and up_xy = -sin(a)·h,
    # so this sum points along the heading h for every pitch, including ±90 degrees.
    return atan2(forward[1] - forward[2] * up[1], forward[0] - forward[2] * up[0])


def navigation_from_json(value: dict) -> tuple[Vec3, tuple[float, float]]:
    """Virtual travel is in ARCore world axes (Y up); look is yaw about the vertical and camera pitch, in radians."""
    offset = _vec(value.get("v", (0, 0, 0)), 3)
    look = _vec(value.get("look", (0, 0)), 2)
    if any(abs(angle) > 1000 for angle in look):
        raise ValueError("Invalid virtual look angle")
    return offset, look  # type: ignore[return-value]


def map_navigation(mapper: "PoseMapper", phone: "Pose", value: dict) -> "Pose":
    """Combine phone tracking with the virtual joystick pose without scaling joystick travel."""
    offset, (yaw, pitch) = navigation_from_json(value)
    return mapper.map(phone, offset, yaw, pitch)


@dataclass(frozen=True)
class Pose:
    position: Vec3
    rotation: Quat

    @classmethod
    def from_json(cls, value: dict) -> "Pose":
        return cls(_vec(value["p"], 3), _normalize(_vec(value["q"], 4)))  # type: ignore[arg-type]


class PoseMapper:
    """Map ARCore phone motion onto a Blender camera with both worlds' gravity aligned.

    At Azzera the phone's heading is turned onto the camera's heading about the
    vertical axis; the remaining tilt and roll difference is kept as a fixed
    offset in the camera's own frame. Panning the phone then turns the camera
    about Blender's Z axis and walking moves it horizontally, however tilted the
    camera is, while the camera pose at Azzera is reproduced exactly. ARCore's
    display-oriented camera and Blender's camera both use X right, Y up and
    -Z forward locally.
    """

    def __init__(self, phone_anchor: Pose, blender_anchor: Pose, scale: float):
        if not isfinite(scale) or scale <= 0:
            raise ValueError("Movement scale must be positive and finite")
        self.scale = scale
        self._anchor(phone_anchor, blender_anchor)

    def _anchor(self, phone: Pose, blender: Pose) -> None:
        self.phone_anchor = phone
        self.blender_anchor = blender
        self.current = blender
        turn = _heading(blender.rotation) - _heading(_mul(_BLENDER_FROM_ARCORE, phone.rotation))
        # ARCore world to Blender world, with the phone's heading turned onto the camera's.
        self._world = _mul((0.0, 0.0, sin(turn / 2), cos(turn / 2)), _BLENDER_FROM_ARCORE)
        self._offset = _mul(_inverse(_mul(self._world, phone.rotation)), blender.rotation)

    def map(self, phone: Pose, virtual_offset: Vec3 = (0.0, 0.0, 0.0),
            yaw: float = 0.0, pitch: float = 0.0) -> Pose:
        """Physical travel is scaled; the virtual offset (ARCore world axes) and look angles are not."""
        travel = _add(_scale(_sub(phone.position, self.phone_anchor.position), self.scale), virtual_offset)
        yaw_rotation = (0.0, sin(yaw / 2), 0.0, cos(yaw / 2))  # about ARCore's vertical axis
        pitch_rotation = (sin(pitch / 2), 0.0, 0.0, cos(pitch / 2))  # about the camera's X axis
        rotation = _mul(_mul(self._world, _mul(yaw_rotation, phone.rotation)),
                        _mul(self._offset, pitch_rotation))
        result = Pose(_add(self.blender_anchor.position, _rotate(self._world, travel)), _normalize(rotation))
        self.current = result
        return result

    def reanchor(self, phone: Pose) -> None:
        """Continue from the last virtual pose after ARCore relocalizes."""
        self._anchor(phone, self.current)


def sample_take(events: list[dict], mapper: PoseMapper, fps: float,
                frame_times: list[tuple[int, float]] | None = None) -> list[tuple[int, Pose]]:
    """Return camera poses on scene frames; supplied frame times follow Blender playback."""
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
            mapped = map_navigation(mapper, phone, event)
            if samples and moment == samples[-1][0]:
                samples[-1] = (moment, mapped)
            else:
                samples.append((moment, mapped))
        else:
            raise ValueError("Unknown take event")
    if not samples:
        raise ValueError("Take has no tracked samples")
    targets = frame_times if frame_times else [
        (frame, frame / fps) for frame in range(round(samples[-1][0] * fps) + 1)
    ]
    result: list[tuple[int, Pose]] = []
    next_sample = 1
    for frame, moment in targets:
        if not isfinite(moment) or moment < 0:
            raise ValueError("Invalid frame timestamp")
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


def sample_optics(events: list[dict], fps: float,
                  initial: tuple[float, float, float],
                  frame_times: list[tuple[int, float]] | None = None) -> list[tuple[int, tuple[float, float, float]]]:
    """Interpolate focal length, focus distance and f-stop onto recorded frames."""
    if not isfinite(fps) or fps <= 0:
        raise ValueError("Frame rate must be positive")
    if not all(isfinite(value) and value > 0 for value in initial):
        raise ValueError("Invalid initial optics")
    samples: list[tuple[float, tuple[float, float, float]]] = [(0.0, initial)]
    last_time = -1.0
    for event in events:
        moment = float(event["t"])
        if not isfinite(moment) or moment < last_time or moment < 0:
            raise ValueError("Take timestamps must be finite and ordered")
        last_time = moment
        values = tuple(float(event.get(key, samples[-1][1][index]))
                       for index, key in enumerate(("lens", "focus_distance", "fstop")))
        if not all(isfinite(value) and value > 0 for value in values):
            raise ValueError("Invalid take optics")
        if moment == samples[-1][0]:
            samples[-1] = (moment, values)
        else:
            samples.append((moment, values))
    targets = frame_times if frame_times else [
        (frame, frame / fps) for frame in range(round(last_time * fps) + 1)
    ]
    result = []
    next_sample = 1
    for frame, moment in targets:
        if not isfinite(moment) or moment < 0:
            raise ValueError("Invalid frame timestamp")
        while next_sample < len(samples) and samples[next_sample][0] < moment:
            next_sample += 1
        if moment <= samples[0][0]:
            values = samples[0][1]
        elif next_sample >= len(samples):
            values = samples[-1][1]
        else:
            left_time, left_values = samples[next_sample - 1]
            right_time, right_values = samples[next_sample]
            alpha = (moment - left_time) / (right_time - left_time)
            values = tuple(left + (right - left) * alpha
                           for left, right in zip(left_values, right_values))
        result.append((frame, values))
    return result


def stabilize_take(samples: list[tuple[int, Pose]], fps: float, strength: float) -> list[tuple[int, Pose]]:
    """Smooth a sampled camera path while keeping its timing and end poses.

    Positions use a symmetric Gaussian window. Rotations use a sign-aligned,
    normalized quaternion average so q and -q never cancel one another.
    """
    if not isfinite(fps) or fps <= 0:
        raise ValueError("Frame rate must be positive")
    if not isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("Stabilization strength must be between zero and one")
    if len(samples) < 3 or strength == 0:
        return list(samples)

    sigma = (0.02 + 0.18 * strength) * fps
    radius = min(len(samples) - 1, ceil(3 * sigma))
    weights = [exp(-0.5 * (distance / sigma) ** 2) for distance in range(radius + 1)]
    result: list[tuple[int, Pose]] = []
    previous_rotation: Quat | None = None
    for index, (frame, center) in enumerate(samples):
        if index in (0, len(samples) - 1):
            position = center.position
            rotation = _normalize(center.rotation)
        else:
            position_sum = [0.0, 0.0, 0.0]
            rotation_sum = [0.0, 0.0, 0.0, 0.0]
            weight_sum = 0.0
            reference = _normalize(center.rotation)
            for other in range(max(0, index - radius), min(len(samples), index + radius + 1)):
                weight = weights[abs(other - index)]
                pose = samples[other][1]
                for axis in range(3):
                    position_sum[axis] += weight * pose.position[axis]
                quaternion = _normalize(pose.rotation)
                sign = -1 if _dot(reference, quaternion) < 0 else 1
                for axis in range(4):
                    rotation_sum[axis] += weight * sign * quaternion[axis]
                weight_sum += weight
            position = tuple(value / weight_sum for value in position_sum)
            rotation = _normalize(tuple(rotation_sum))
        if previous_rotation is not None and _dot(previous_rotation, rotation) < 0:
            rotation = tuple(-value for value in rotation)
        result.append((frame, Pose(position, rotation)))
        previous_rotation = rotation
    return result
