"""Shared types for landmark vision providers."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisionRequest:
    rig_id: str
    views: dict          # {"front": {"path": str, "image_size": [w,h], "ortho_scale": float, ...}, ...}
    mesh_objects: list   # [{"name": str, "vertex_count": int, "bbox_world": [[],[]]}, ...]
    world_aabb: tuple    # ((xmin,ymin,zmin), (xmax,ymax,zmax))


@dataclass
class VisionResponse:
    landmarks: dict           # {view: {key: [px, py] | None}}
    mesh_object_labels: dict  # {name: "body"|"hat"|"accessory_held_left"|...}
    notes: str = ""
    raw: Any = None           # original parsed JSON for audit
