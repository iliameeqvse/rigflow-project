"""Standalone smoke test for canonical_mixamo_name. No Blender needed.
Run from backend/:  python scripts/_test_canonical_mixamo_name.py
"""
import importlib.util, sys
from pathlib import Path

# Stub bpy / mathutils so blender_autorig imports in plain Python.
stub_mu = type(sys)("mathutils")
stub_mu.Vector = tuple
stub_mu.Quaternion = object
stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.canonical_mixamo_name

cases = {
    "mixamorig:Hips": "Hips",
    "mixamorig:LeftHandIndex1": "LeftHandIndex1",
    "Armature|RightForeArm": "RightForeArm",
    "pelvis": "Hips",
    "spine_01": "Spine1",
    "L_UpperArm": "LeftArm",
    "r_forearm": "RightForeArm",
    "Left_Foot": "LeftFoot",
    "RightUpLeg": "RightUpLeg",
    "clavicle_l": "LeftShoulder",
    # Sided "hip" is the thigh in many game rigs → UpLeg, not the torso Hips.
    "l_hip": "LeftUpLeg",
    "r_hip": "RightUpLeg",
    "hips": "Hips",
    "IK_Hand_L": None,
    "knee_pole_target_R": None,
    "some_random_prop": None,
}
failures = []
for raw, expected in cases.items():
    got = f(raw)
    ok = got == expected
    print(f"  [{'OK' if ok else 'FAIL'}] {raw!r} -> {got!r} (expected {expected!r})")
    if not ok:
        failures.append(raw)

if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("canonical_mixamo_name: OK")
