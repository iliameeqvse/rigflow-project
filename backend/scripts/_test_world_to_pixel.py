"""Standalone smoke-test for world_to_pixel / project_landmarks_to_pixels.

No Blender runtime needed. Run with:
    python scripts/_test_world_to_pixel.py   (from backend/)
"""
import importlib.util
import sys
from pathlib import Path


# Stub bpy / mathutils so blender_autorig.py imports in plain Python.
class _Vec:
    def __init__(self, xyz):
        self.x, self.y, self.z = float(xyz[0]), float(xyz[1]), float(xyz[2])

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __getitem__(self, i):
        return (self.x, self.y, self.z)[i]


stub_mu = type(sys)("mathutils")
stub_mu.Vector = _Vec
stub_mu.Quaternion = object
stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
world_to_pixel = mod.world_to_pixel
pixel_to_world_ray = mod.pixel_to_world_ray

AABB = ((-1.0, -0.3, 0.0), (1.0, 0.2, 2.0))
OS = 2.3
IMAGE = 512

failures = []


def check(name, cond):
    status = "OK" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        failures.append(name)


# Round-trip: a pixel → world ray origin → back to the same pixel.
for view in ("front", "back", "left", "right"):
    for (px, py) in ((256, 256), (100, 400), (10, 10), (500, 90)):
        origin, _ = pixel_to_world_ray(view, px, py, IMAGE, OS, AABB)
        back = world_to_pixel(view, origin, IMAGE, OS, AABB)
        ok = back is not None and abs(back[0] - px) < 1e-3 and abs(back[1] - py) < 1e-3
        check(f"{view} round-trip ({px},{py})", ok)

# Off-frame point projects to None.
far_origin, _ = pixel_to_world_ray("front", 256, 256, IMAGE, OS, AABB)
far = mod.Vector((far_origin.x + OS * 5, far_origin.y, far_origin.z))
check("front off-frame → None", world_to_pixel("front", far, IMAGE, OS, AABB) is None)

# project_landmarks_to_pixels: mesh_h=2.0 → half=1.0, so three.js (tx,ty,tz)
# maps to world (tx, -tz, ty). Centred AABB, front ortho_scale=2, 512px.
project_landmarks_to_pixels = mod.project_landmarks_to_pixels
cam_params = {
    "world_aabb": [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]],
    "views": {
        v: {"ortho_scale": 2.0, "image_size": [512, 512]}
        for v in ("front", "back", "left", "right")
    },
}
proj = project_landmarks_to_pixels(
    {"chin": [0.0, 0.0, 0.0], "groin": [0.5, 0.0, 0.0]}, 2.0, cam_params
)
check("front chin → image centre",
      proj["front"]["chin"] == [256.0, 256.0])
check("front groin → x shifted right",
      abs(proj["front"]["groin"][0] - 384.0) < 1e-6)
check("all four views projected",
      set(proj) == {"front", "back", "left", "right"})

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("All world_to_pixel tests passed.")
