"""Blender entry point; pure pose modules can also run in ordinary Python."""

# Blender reads bl_info from this file's source without importing it, so it must stay a literal here.
bl_info = {
    "name": "Action2Blender",
    "author": "Action2Blender contributors",
    "version": (0, 2, 3),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Action2Blender",
    "description": "Development build: drive, record, and preview a Blender camera from Android",
    "category": "Animation",
}

try:
    import bpy  # noqa: F401
except ModuleNotFoundError:
    pass
else:
    from .blender import register, unregister
