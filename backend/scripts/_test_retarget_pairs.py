"""Standalone test for pair_bones_by_mixamo. No Blender. Run from backend/:
    python scripts/_test_retarget_pairs.py
"""
import importlib.util
import sys
from pathlib import Path

stub_mu = type(sys)("mathutils")
stub_mu.Vector = tuple
stub_mu.Quaternion = object
stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

# blender_retarget imports canonical_mixamo_name from blender_autorig; make
# both importable from the scripts dir.
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location(
    "blender_retarget", Path(__file__).parent / "blender_retarget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

bone_mapping = {"Hips": "DEF-spine", "LeftArm": "DEF-upper_arm.L", "Head": "DEF-spine.005"}
source_bones = ["mixamorig:Hips", "mixamorig:LeftArm", "mixamorig:Head", "mixamorig:Spine"]
pairs = mod.pair_bones_by_mixamo(bone_mapping, source_bones)
got = dict(pairs)
assert got == {"DEF-spine": "mixamorig:Hips",
               "DEF-upper_arm.L": "mixamorig:LeftArm",
               "DEF-spine.005": "mixamorig:Head"}, got
assert all(s != "mixamorig:Spine" for _, s in pairs)
print("pair_bones_by_mixamo: OK")
