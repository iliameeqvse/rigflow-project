"""Standalone test for build_view_ortho_scales — no Blender runtime needed.

Run with:  python backend/scripts/_test_ai_ortho_scale.py
"""
import importlib.util
import sys
from pathlib import Path


# Minimal mathutils.Vector stub so blender_autorig.py imports under plain
# Python. build_view_ortho_scales never touches Vector, but the module must
# still import cleanly. Mirrors backend/scripts/_test_pixel_to_world.py.
class _Vec:
    def __init__(self, xyz):
        self.x, self.y, self.z = float(xyz[0]), float(xyz[1]), float(xyz[2])

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
build_view_ortho_scales = mod.build_view_ortho_scales

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok: {label}")


# 1. All four per-view scales present → returned verbatim.
resp = {"views": {
    "front": {"ortho_scale": 2.0},
    "back":  {"ortho_scale": 2.0},
    "left":  {"ortho_scale": 3.5},
    "right": {"ortho_scale": 3.5},
}}
check("per-view scales used",
      build_view_ortho_scales(resp, fallback=9.9),
      {"front": 2.0, "back": 2.0, "left": 3.5, "right": 3.5})

# 2. No `views` key → fallback for every view.
check("missing views → fallback",
      build_view_ortho_scales({"landmarks": {}}, fallback=4.2),
      {"front": 4.2, "back": 4.2, "left": 4.2, "right": 4.2})

# 3. Partial: only side views carry a scale → others fall back.
resp_partial = {"views": {
    "left":  {"ortho_scale": 3.0},
    "right": {"ortho_scale": 3.0},
}}
check("partial views fill from fallback",
      build_view_ortho_scales(resp_partial, fallback=1.0),
      {"front": 1.0, "back": 1.0, "left": 3.0, "right": 3.0})

# 4. Garbage scale value → fallback for that view.
resp_bad = {"views": {"front": {"ortho_scale": "nonsense"}}}
check("garbage scale → fallback (front)",
      build_view_ortho_scales(resp_bad, fallback=5.0)["front"], 5.0)

# 5. None response → all fallback.
check("None response → fallback",
      build_view_ortho_scales(None, fallback=7.0),
      {"front": 7.0, "back": 7.0, "left": 7.0, "right": 7.0})

if failures:
    print("\nFAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("\nAll build_view_ortho_scales checks passed.")
