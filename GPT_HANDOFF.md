# RigFlow GPT Handoff

Date: 2026-05-13

## Repo / Environment

- Source root: `/home/dev/projects/rigflow-project/rigflow-project`
- Backend root: `/home/dev/projects/rigflow-project/rigflow-project/backend`
- Local dev does not require Docker.
- Django local settings load `backend/.env`.
- `get_provider()` currently resolves to `ClaudeProvider`, so the Anthropic key/provider wiring is active.
- Do not print or commit the actual API key from `backend/.env`.

Useful local checks:

```bash
cd /home/dev/projects/rigflow-project/rigflow-project/backend
python manage.py shell -c "from apps.rigging.landmark_vision import get_provider; print(type(get_provider()).__name__)"
python manage.py shell -c "from apps.rigging.models import RiggedModel; r=RiggedModel.objects.latest('created_at'); print(r.detection_method); print(bool(r.vision_response_raw)); print(r.rig_log[:1200])"
```

## What Was Fixed

### 1. Claude prompt formatting crash

File: `backend/apps/rigging/landmark_vision/claude_provider.py`

The prompt contains JSON braces. The old code used:

```python
VISION_PROMPT_TEMPLATE.format(...)
```

That treated JSON keys like `"landmarks"` as format fields and crashed with:

```text
AI phase error: '\n  "landmarks"'; using geometry
```

Fix: use `.replace("{mesh_object_names}", mesh_object_names)` instead.

### 2. Rig logs now show AI fallback reasons

File: `backend/apps/rigging/tasks.py`

The rig log now includes:

- selected vision provider
- ortho render exit code/stdout/stderr
- whether Claude returned landmarks
- whether AI sanity failed and which failure codes triggered fallback

This made it obvious when the run was `ClaudeProvider -> AI landmarks -> sanity fallback`.

### 3. Docker env passthrough

File: `docker/docker-compose.yml`

Added:

```yaml
env_file:
  - ../backend/.env
```

to `web` and `celery`, so Docker runs can receive `ANTHROPIC_API_KEY` and `LANDMARK_VISION_PROVIDER`. User currently cannot run Docker, but this closes the production/container gap.

### 4. Sanity check was too strict for stylized characters

Files:

- `backend/apps/rigging/sanity.py`
- `backend/apps/rigging/tests/test_sanity.py`

The Freddy model has a low chin / large head shape, so AI produced:

```text
chin.y ~= 1.50
shoulder.y ~= 1.68
```

The previous sanity rule rejected this as `order_shoulder_above_chin`, causing geometry fallback even though AI was usable.

Fix: keep strict ordering through:

```text
ankle < knee < hip <= groin < shoulder
```

but no longer require `shoulder <= chin`.

### 5. AI left/right side normalization

File: `backend/scripts/blender_autorig.py`

Claude sometimes labels front-view left/right from viewer perspective. RigFlow expects character-left to be positive X in the landmark coordinates.

Added:

```python
normalize_bilateral_landmark_sides()
```

After AI+geometry merge, each left/right pair is normalized so:

```text
left.x > right.x
```

This fixed the crossed skeleton issue.

### 6. T-pose wrist override

File: `backend/scripts/blender_autorig.py`

After side normalization, arms still bent down because Claude's wrist points landed too close to inner forearms/hands. For confident T-poses, geometry extremities are better for wrists.

Added:

```text
T-pose AI refine: using geometry extremities for wrists
```

Behavior: keep AI landmarks for body/limbs, but replace `left_wrist` and `right_wrist` with geometry T-pose extremities when pose is confidently `t_pose`.

## Current User-Observed State

Latest screenshots/logs showed:

- AI path is active.
- UI shows `AI vision`.
- `detection_method` should now remain `llm_vision` unless a new sanity rule fails.
- Side crossing improved after normalization.
- Remaining expected issue: deformation/weighting quality may still be poor.

Known recurring warnings:

```text
Bone Heat Weighting: failed to find solution for one or more bones
Patched 43067 orphan verts in Body_Geo_Attack
Patched 43067 orphan verts in Body_Geo_Workshop
Skinning fallback: patched 86134 orphan vertices total
```

This is separate from the AI wiring. It means Blender auto-weighting failed for many vertices and the fallback patched orphan weights. Static skeleton placement can be correct while animation/deformation still looks bad.

## Verification Already Run

From backend root:

```bash
python -m py_compile scripts/blender_autorig.py apps/rigging/sanity.py apps/rigging/tasks.py apps/rigging/landmark_vision/claude_provider.py
python manage.py test apps.rigging.tests.test_sanity apps.rigging.tests.test_landmark_vision
```

Result:

```text
Ran 18 tests ... OK
```

One expected test log line appears during tests:

```text
Claude response unparseable: Expecting value: line 1 column 1 (char 0)
```

That is from a parser negative test, not a failure.

## Next Steps

1. Restart backend after code changes.
2. Re-rig the Freddy FBX.
3. Confirm the new rig log contains:

```text
Vision model returned landmarks
Mode: AI
Normalized AI landmark side labels: ...
T-pose AI refine: using geometry extremities for wrists
```

4. Confirm latest rig:

```bash
python manage.py shell -c "from apps.rigging.models import RiggedModel; r=RiggedModel.objects.latest('created_at'); print(r.detection_method); print(bool(r.vision_response_raw))"
```

Expected:

```text
llm_vision
True
```

5. If skeleton placement looks sane but animation still deforms badly, investigate skinning/weights next, not AI:

- `bind_auto_weights()`
- `patch_orphan_vertex_weights()`
- whether this FBX has duplicate body meshes (`Body_Geo_Attack`, `Body_Geo_Workshop`)
- whether non-visible/duplicate meshes should be excluded before binding/export

## Modified Files In This Session

- `backend/apps/rigging/landmark_vision/claude_provider.py`
- `backend/apps/rigging/tasks.py`
- `backend/apps/rigging/sanity.py`
- `backend/apps/rigging/tests/test_sanity.py`
- `backend/scripts/blender_autorig.py`
- `docker/docker-compose.yml`
- `GPT_HANDOFF.md`

`backend/.env` is modified in the worktree but should be treated as local secret/config state.
