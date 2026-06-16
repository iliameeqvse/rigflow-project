"""Server-side animation retarget + bake. Runs inside Blender:

    blender --background --python blender_retarget.py -- --rig <glb> \
        --clips <json> --output <glb> --bone-map <json> --report-out <json>

Loads the rigged GLB and each animation clip, transfers each source bone's
motion as a DELTA FROM ITS OWN REST onto the target bone's rest (rest-pose
correct — this is what the browser retarget gets wrong), bakes keyframes, and
exports a GLB with animations.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix  # noqa: F401  (used by the bake in Task 2)

# Reuse the canonical-name resolver from the autorig script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_autorig import canonical_mixamo_name  # noqa: E402


def log(msg):
    print(f"[RigFlow-Retarget] {msg}")


def pair_bones_by_mixamo(bone_mapping, source_bone_names):
    """Return a list of (target_bone_name, source_bone_name) pairs.

    bone_mapping is {MixamoName: targetBoneName} (the rig's saved map). Each
    source bone is resolved to a canonical Mixamo name; when that Mixamo name
    is in bone_mapping, the source pairs to that target bone. First source per
    Mixamo name wins; targets with no matching source are skipped."""
    src_by_mixamo = {}
    for s in source_bone_names:
        mx = canonical_mixamo_name(s)
        if mx and mx not in src_by_mixamo:
            src_by_mixamo[mx] = s
    pairs = []
    for mixamo, target_bone in bone_mapping.items():
        src = src_by_mixamo.get(mixamo)
        if src:
            pairs.append((target_bone, src))
    return pairs
