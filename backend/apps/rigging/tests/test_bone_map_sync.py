"""Regression guard: the backend RIGIFY_TO_MIXAMO table and the frontend
FALLBACK_MIXAMO_TO_DEF table must stay exact inverses of each other.

These two maps are hand-maintained copies in different languages
(backend/scripts/blender_autorig.py and
frontend/src/lib/boneMap.ts). Adding a bone to one without
the other silently breaks animation retargeting for rigs whose bone_mapping
field is empty. This test makes that desync a hard failure.

Only the explicit spine / leg / arm entries are compared. The frontend
additionally generates finger-bone entries that have no backend counterpart
(build_bone_map emits only bones present in RIGIFY_TO_MIXAMO), so the finger
block is intentionally excluded.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

# test file: backend/apps/rigging/tests/test_bone_map_sync.py
# parents:   [0]=tests [1]=rigging [2]=apps [3]=backend [4]=<repo root>
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_SRC = _REPO_ROOT / "backend" / "scripts" / "blender_autorig.py"
_FRONTEND_SRC = _REPO_ROOT / "frontend" / "src" / "lib" / "boneMap.ts"


def _backend_rigify_to_mixamo() -> dict:
    """Parse RIGIFY_TO_MIXAMO = { "DEF-bone": "Mixamo", ... } as text."""
    text = _BACKEND_SRC.read_text(encoding="utf-8")
    block = re.search(r"RIGIFY_TO_MIXAMO\s*=\s*\{(.*?)\}", text, re.S)
    assert block, "RIGIFY_TO_MIXAMO block not found in blender_autorig.py"
    pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', block.group(1))
    return {def_bone: mixamo for def_bone, mixamo in pairs}


def _frontend_mixamo_to_def() -> dict:
    """Parse the explicit (non-finger) entries of FALLBACK_MIXAMO_TO_DEF.

    The block runs from the const declaration to the `// Mixamo finger
    naming` comment that introduces the generated finger entries.
    """
    text = _FRONTEND_SRC.read_text(encoding="utf-8")
    block = re.search(
        r"FALLBACK_MIXAMO_TO_DEF[^{]*\{(.*?)//\s*Mixamo finger naming",
        text, re.S,
    )
    assert block, "explicit FALLBACK_MIXAMO_TO_DEF block not found in AnimationPlayer.tsx"
    pairs = re.findall(r'(\w+)\s*:\s*"([^"]+)"', block.group(1))
    return {mixamo: def_bone for mixamo, def_bone in pairs}


class BoneMapSyncTests(SimpleTestCase):
    def test_backend_map_has_expected_entry_count(self):
        self.assertEqual(len(_backend_rigify_to_mixamo()), 22)

    def test_frontend_explicit_map_has_expected_entry_count(self):
        self.assertEqual(len(_frontend_mixamo_to_def()), 22)

    def test_maps_are_exact_inverses(self):
        backend = _backend_rigify_to_mixamo()    # {DEF-bone: Mixamo}
        frontend = _frontend_mixamo_to_def()     # {Mixamo: DEF-bone}
        backend_inverted = {mixamo: def_bone for def_bone, mixamo in backend.items()}
        self.assertEqual(
            backend_inverted, frontend,
            "RIGIFY_TO_MIXAMO (backend) and FALLBACK_MIXAMO_TO_DEF (frontend) "
            "have drifted apart — update both copies in the same change.",
        )
