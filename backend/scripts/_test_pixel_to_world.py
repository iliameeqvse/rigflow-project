"""Standalone smoke-test for pixel_to_world_ray — no Blender runtime needed.

Run with:  python backend/scripts/_test_pixel_to_world.py
"""
import importlib.util
import sys
from pathlib import Path


# Stub bpy / mathutils so blender_autorig.py loads in plain Python.
class _Vec:
    def __init__(self, xyz):
        self.x, self.y, self.z = float(xyz[0]), float(xyz[1]), float(xyz[2])

    def __repr__(self):
        return f"Vec({self.x:.4f}, {self.y:.4f}, {self.z:.4f})"

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __sub__(self, other):
        return _Vec((self.x - other.x, self.y - other.y, self.z - other.z))

    def __add__(self, other):
        return _Vec((self.x + other.x, self.y + other.y, self.z + other.z))

    def __mul__(self, s):
        return _Vec((self.x * s, self.y * s, self.z * s))

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
pixel_to_world_ray = mod.pixel_to_world_ray

# Scene: X[-1,1], Y[-0.3,0.2], Z[0,2].
AABB = ((-1.0, -0.3, 0.0), (1.0, 0.2, 2.0))
cx, cy, cz = 0.0, -0.05, 1.0
OS = 2.3
IMAGE = 512

failures = []


def check(name, got, expected, tol=1e-4):
    ok = all(abs(g - e) < tol for g, e in zip(got, expected))
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}: got {[round(v,4) for v in got]}, "
          f"expected {[round(v,4) for v in expected]}")
    if not ok:
        failures.append(name)


# 1. Front view centre → ray at (cx, ?, cz) going +Y.
o, d = pixel_to_world_ray("front", IMAGE // 2, IMAGE // 2, IMAGE, OS, AABB)
print("Front centre:")
check("origin_x ≈ cx", [o.x], [cx])
check("origin_z ≈ cz", [o.z], [cz])
check("direction  +Y",  [d.x, d.y, d.z], [0.0, 1.0, 0.0])

# 2. Front view top-left → world x < cx, z > cz.
o2, _ = pixel_to_world_ray("front", 0, 0, IMAGE, OS, AABB)
print("Front top-left:")
check("origin_x < cx", [1.0 if o2.x < cx else 0.0], [1.0])
check("origin_z > cz", [1.0 if o2.z > cz else 0.0], [1.0])

# 3. Back view right edge → world x < cx (mirrored).
o3, d3 = pixel_to_world_ray("back", IMAGE - 1, IMAGE // 2, IMAGE, OS, AABB)
print("Back right edge:")
check("origin_x < cx", [1.0 if o3.x < cx else 0.0], [1.0])
check("direction  -Y",  [d3.y], [-1.0])

# 4. Left view centre → goes toward +X, origin.y ≈ cy.
o4, d4 = pixel_to_world_ray("left", IMAGE // 2, IMAGE // 2, IMAGE, OS, AABB)
print("Left centre:")
check("origin_y ≈ cy",  [o4.y], [cy])
check("direction  +X",  [d4.x, d4.y, d4.z], [1.0, 0.0, 0.0])

# 5. Right view centre → goes toward -X, origin.y ≈ cy.
o5, d5 = pixel_to_world_ray("right", IMAGE // 2, IMAGE // 2, IMAGE, OS, AABB)
print("Right centre:")
check("origin_y ≈ cy",  [o5.y], [cy])
check("direction  -X",  [d5.x, d5.y, d5.z], [-1.0, 0.0, 0.0])

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("All pixel_to_world_ray tests passed.")
