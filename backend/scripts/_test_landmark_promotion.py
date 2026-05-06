"""Standalone smoke test for _promote_legacy_landmarks. Run with:
    python backend/scripts/_test_landmark_promotion.py
No Blender dependency — uses tuples instead of mathutils.Vector."""
import importlib.util
import sys
from pathlib import Path

# Load the function under test without importing bpy. We monkey-load just
# the symbols we need from blender_autorig.py.
src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
module = importlib.util.module_from_spec(spec)

# Stub out bpy / mathutils so the script can be imported in plain Python.
class _StubVec(tuple):
    def __new__(cls, xyz):
        v = tuple.__new__(cls, xyz)
        return v
    @property
    def x(self): return self[0]
    @property
    def y(self): return self[1]
    @property
    def z(self): return self[2]
    def __sub__(self, other): return _StubVec((self[0]-other[0], self[1]-other[1], self[2]-other[2]))
    def __add__(self, other): return _StubVec((self[0]+other[0], self[1]+other[1], self[2]+other[2]))
    def __mul__(self, s): return _StubVec((self[0]*s, self[1]*s, self[2]*s))

stub_mathutils = type(sys)("mathutils")
stub_mathutils.Vector = _StubVec
stub_mathutils.Quaternion = object
stub_mathutils.Matrix = object
sys.modules["mathutils"] = stub_mathutils
sys.modules["bpy"] = type(sys)("bpy")

spec.loader.exec_module(module)

# Test: 6-key dict gets promoted to 14 keys with sensible derived values.
six = {
    "chin":         _StubVec((0.0, 0.0, 1.6)),
    "groin":        _StubVec((0.0, 0.0, 0.9)),
    "left_wrist":   _StubVec((0.7, 0.0, 1.4)),
    "right_wrist":  _StubVec((-0.7, 0.0, 1.4)),
    "left_ankle":   _StubVec((0.1, 0.0, 0.0)),
    "right_ankle":  _StubVec((-0.1, 0.0, 0.0)),
}
out = module._promote_legacy_landmarks(six)

assert set(out.keys()) == set(module.LANDMARK_KEYS), f"got {set(out.keys())}"
# Spot-check shoulder z = groin.z + body_h * 0.82, body_h = chin.z - groin.z = 0.7
expected_shoulder_z = 0.9 + 0.7 * 0.82  # 1.474
assert abs(out["left_shoulder"].z - expected_shoulder_z) < 1e-6, out["left_shoulder"]
# Hip x equals ankle x (both signs)
assert out["left_hip"].x == 0.1 and out["right_hip"].x == -0.1
# Knee z is midway between groin and ankle plus 0.02 offset
assert abs(out["left_knee"].z - ((0.9 + 0.0) / 2 + 0.02)) < 1e-6
print("_promote_legacy_landmarks smoke test: OK")
