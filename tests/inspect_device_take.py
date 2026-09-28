"""Print movement statistics from a .blend captured with a real phone."""

import math

import bpy


scene = bpy.context.scene
camera = scene.camera
assert camera is not None
assert camera.animation_data is not None
assert camera.animation_data.action is not None
start_frame, end_frame = (round(value) for value in camera.animation_data.action.frame_range)
positions = []
rotations = []
for frame in range(start_frame, end_frame + 1):
    scene.frame_set(frame)
    position, rotation, _ = camera.matrix_world.decompose()
    positions.append(position.copy())
    rotations.append(rotation.copy())

distances = [(right - left).length for left, right in zip(positions, positions[1:])]
angles = [
    math.degrees(2 * math.acos(min(1.0, abs(left.dot(right)))))
    for left, right in zip(rotations, rotations[1:])
]
largest_steps = sorted(
    ((round(step, 4), start_frame + index + 1) for index, step in enumerate(distances)),
    reverse=True,
)[:5]
largest_angles = sorted(
    ((round(step, 3), start_frame + index + 1) for index, step in enumerate(angles)),
    reverse=True,
)[:5]
print("A2B_TAKE_STATS", {
    "frames": len(positions),
    "path_m": round(sum(distances), 4),
    "net_m": round((positions[-1] - positions[0]).length, 4),
    "max_frame_step_m": round(max(distances, default=0), 4),
    "max_frame_angle_deg": round(max(angles, default=0), 3),
    "largest_steps_m_at_frame": largest_steps,
    "largest_angles_deg_at_frame": largest_angles,
    "action": camera.animation_data.action.name,
}, flush=True)
