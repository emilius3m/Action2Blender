"""Blender entry point; pure pose modules can also run in ordinary Python."""

try:
    import bpy  # noqa: F401
except ModuleNotFoundError:
    pass
else:
    from .blender import bl_info, register, unregister
