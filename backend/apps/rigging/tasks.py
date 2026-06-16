import subprocess
import time
import json
import hashlib
import tempfile
from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files import File

logger = get_task_logger(__name__)


def push_ws(user_id: str, data: dict):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}", {"type": "task.update", "data": data}
        )
    except Exception as e:
        logger.warning(f"WebSocket push failed: {e}")


def _blender_call(cmd, timeout=600, cwd=None):
    """Run a Blender subprocess, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout, cwd=cwd,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def _extract_rotation_args(extra_args: list | None) -> list:
    """Return only the --initial-rotation-* flags *with their values*.

    extra_args is a flat, interleaved list:
        ["--initial-rotation-x", "15.0", "--initial-rotation-y", "0.0", ...]
    A naive flag-name filter keeps "--initial-rotation-x" but drops "15.0",
    which makes argparse fail in the ortho-render subprocess. Keep each
    recognised flag together with the token that follows it.
    """
    if not extra_args:
        return []
    out: list = []
    i = 0
    while i < len(extra_args):
        token = extra_args[i]
        if token.startswith("--initial-rotation") and i + 1 < len(extra_args):
            out.append(token)
            out.append(extra_args[i + 1])
            i += 2
        else:
            i += 1
    return out


def _run_rig_pipeline(rig_id: str, extra_args: list = None) -> dict:
    """
    Plain function — NOT a Celery task — so it can be called directly from
    views and background threads without bind/self injection issues.
    extra_args: additional CLI flags forwarded to blender_autorig.py
    """
    from .models import RiggedModel
    from .landmark_vision import get_provider
    from .landmark_vision.base import VisionRequest

    start_time = time.time()
    rig = RiggedModel.objects.select_related("user__user").get(id=rig_id)
    user_id = str(rig.user.user.id)

    rig.status = RiggedModel.STATUS_PROCESSING
    rig.save(update_fields=["status"])

    # Determine whether this call is user-supplied-landmarks (skip AI).
    user_landmarks = extra_args and "--landmarks" in extra_args

    try:
        push_ws(user_id, {"rig_id": rig_id, "step": "Downloading model...", "pct": 5})

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path     = tmp / f"input.{rig.original_format}"
            glb_output     = tmp / "rigged.glb"
            bone_data_path = tmp / "bones.json"
            pose_data_path = tmp / "pose.json"
            landmarks_path = tmp / "landmarks.json"
            pixels_path    = tmp / "landmark_pixels.json"

            with rig.original_file.open("rb") as f:
                input_path.write_bytes(f.read())

            blender_path = settings.BLENDER_EXECUTABLE
            script_path  = settings.BLENDER_SCRIPTS_DIR / "blender_autorig.py"
            cwd          = str(settings.BLENDER_SCRIPTS_DIR.parent)
            failure_reason: str | None = None

            if not Path(blender_path).is_file():
                failure_reason = (
                    f"Blender executable not found at '{blender_path}'. "
                    "Set the BLENDER_PATH environment variable."
                )
            else:
                # --- Phase 1: ortho-render + AI landmark detection ---
                ai_response_path: Path | None = None
                ai_phase_log: list[str] = []

                if not user_landmarks:
                    provider = get_provider()
                    ai_phase_log.append(
                        f"[RigFlow] Vision provider: {type(provider).__name__}"
                    )
                    request_path = tmp / "ai_request.json"
                    ortho_dir    = tmp / "ortho"

                    # Build base rotation flags from extra_args (if any).
                    # Keep each flag with its value — see _extract_rotation_args.
                    rotation_args = _extract_rotation_args(extra_args)

                    render_cmd = [
                        blender_path, "--background", "--python", str(script_path), "--",
                        "--input",  str(input_path),
                        "--output", "/dev/null",
                        "--bones",  "/dev/null",
                        "--format", rig.original_format,
                        "--render-ortho-views",
                        "--ortho-render-dir", str(ortho_dir),
                        "--ai-request-out",   str(request_path),
                    ] + rotation_args

                    push_ws(user_id, {"rig_id": rig_id,
                                      "step": "Rendering character views…", "pct": 20})
                    try:
                        rc, out, err = _blender_call(render_cmd, timeout=120, cwd=cwd)
                        ai_phase_log.append(
                            f"[RigFlow] Ortho render exited with code {rc}"
                        )
                        if out:
                            ai_phase_log.append(
                                "[RigFlow] Ortho render stdout:\n" + out[-4000:]
                            )
                        if err:
                            ai_phase_log.append(
                                "[RigFlow] Ortho render stderr:\n" + err[-2000:]
                            )
                        if rc != 0:
                            logger.warning(
                                "Ortho render exited %d for rig %s; skipping AI phase.\n%s",
                                rc, rig_id, err[-1000:],
                            )
                        elif request_path.exists():
                            request_data = json.loads(request_path.read_text())
                            if request_data.get("already_rigged"):
                                # The upload already has a skeleton skinning the
                                # mesh — the keep-rig branch will preserve it, so
                                # skip the vision call entirely (no landmarks).
                                ai_phase_log.append(
                                    "[RigFlow] Upload already rigged — skipping "
                                    "vision; preserving existing skeleton."
                                )
                                rig.used_existing_rig = True
                                rig.detection_method = "preserved"
                            else:
                                vision_req = VisionRequest(
                                    rig_id=str(rig.id),
                                    views=request_data["views"],
                                    mesh_objects=request_data["mesh_objects"],
                                    world_aabb=tuple(
                                        tuple(c) for c in request_data["world_aabb"]
                                    ),
                                )
                                push_ws(user_id, {"rig_id": rig_id,
                                                  "step": "Calling vision model…", "pct": 35})
                                vision_resp = provider.detect(vision_req)
                                if vision_resp is not None:
                                    ai_phase_log.append(
                                        "[RigFlow] Vision model returned landmarks"
                                    )
                                    ai_response_path = tmp / "ai_response.json"
                                    ai_response_path.write_text(json.dumps({
                                        "landmarks":    vision_resp.landmarks,
                                        "mesh_objects": vision_resp.mesh_object_labels,
                                        "notes":        vision_resp.notes,
                                        # Forward phase-1 per-view camera params so
                                        # the full-rig pass can raycast each view
                                        # with its own ortho_scale.
                                        "views":        request_data.get("views", {}),
                                    }, indent=2))
                                    rig.vision_response_raw = vision_resp.raw
                                    rig.detection_method = "llm_vision"
                                else:
                                    ai_phase_log.append(
                                        "[RigFlow] Vision model returned no landmarks; using geometry"
                                    )
                                    logger.warning(
                                        "Vision provider %s returned no landmarks for rig %s; using geometry",
                                        type(provider).__name__, rig_id,
                                    )
                                    rig.detection_method = "geometry"
                        else:
                            ai_phase_log.append(
                                "[RigFlow] Ortho render produced no AI request; using geometry"
                            )
                    except subprocess.TimeoutExpired:
                        ai_phase_log.append(
                            "[RigFlow] Ortho render timed out; using geometry"
                        )
                        logger.warning("Ortho render timed out for rig %s; "
                                       "skipping AI phase.", rig_id)
                    except Exception as e:
                        ai_phase_log.append(
                            f"[RigFlow] AI phase error: {e}; using geometry"
                        )
                        logger.exception("AI phase error for rig %s: %s", rig_id, e)
                        rig.detection_method = "geometry"
                else:
                    rig.detection_method = "user_landmarks"

                # --- Phase 2: full rig pipeline ---
                push_ws(user_id, {"rig_id": rig_id,
                                  "step": "Auto-rigging with Blender…", "pct": 50})

                rig_cmd = [
                    blender_path, "--background", "--python", str(script_path), "--",
                    "--input",          str(input_path),
                    "--output",         str(glb_output),
                    "--bones",          str(bone_data_path),
                    "--landmarks-out",  str(landmarks_path),
                    "--pose",           str(pose_data_path),
                    "--format",         rig.original_format,
                ]
                if extra_args:
                    rig_cmd.extend(extra_args)
                if ai_response_path is not None:
                    rig_cmd.extend(["--landmarks-from-ai", str(ai_response_path)])
                    rig_cmd.extend([
                        "--landmark-pixels-out", str(pixels_path),
                        "--camera-params",       str(request_path),
                    ])

                try:
                    rc, out, err = _blender_call(rig_cmd, timeout=600, cwd=cwd)
                    rig.rig_log = "\n".join(ai_phase_log + [out[-8000:]])

                    if rc != 0:
                        rig.rig_log += f"\nSTDERR: {err[-2000:]}"
                        failure_reason = (
                            f"Blender exited with code {rc}. "
                            "See rig log for Rigify / pipeline errors."
                        )
                    elif not glb_output.exists():
                        failure_reason = "Blender finished cleanly but produced no GLB."

                except subprocess.TimeoutExpired:
                    failure_reason = "Blender timed out after 10 minutes."
                except Exception as e:
                    failure_reason = f"Blender subprocess raised: {e}"
                    logger.warning("Blender failed (%s)", e)

            if failure_reason:
                rig.status = RiggedModel.STATUS_FAILED
                rig.error_message = failure_reason
                rig.processing_time_s = time.time() - start_time
                rig.save(update_fields=[
                    "status", "error_message", "rig_log", "processing_time_s",
                    "detection_method",
                ])
                push_ws(user_id, {
                    "rig_id": rig_id,
                    "status": "failed",
                    "error": failure_reason,
                })
                logger.error("Rig failed %s: %s", rig_id, failure_reason)
                return {"status": "failed", "rig_id": rig_id}

            # --- Sanity-check cascade ---
            # Validate the landmarks Blender wrote.  When AI seeds fail the
            # anatomical rules, re-run geometry-only so the rig is still
            # valid.  Failures cascade: AI → geometry → AABB defaults (always
            # produces a done rig, never a hard failure).
            _LOOSE_AABB = ((-2.0, -0.5, -2.0), (2.0, 2.5, 2.0))

            # Preserved rigs have no Rigify landmarks to validate — skip the
            # whole cascade so detection_method stays "preserved".
            if not rig.used_existing_rig and landmarks_path.exists():
                from .sanity import check_landmarks
                _candidate = json.loads(landmarks_path.read_text())
                _sr = check_landmarks(_candidate, world_aabb=_LOOSE_AABB)

                if not _sr.ok and ai_response_path is not None:
                    _failure_codes = [f.code for f in _sr.failures]
                    rig.rig_log += (
                        "\n[RigFlow] AI landmark sanity failed "
                        f"({_failure_codes}); running geometry fallback"
                    )
                    logger.warning(
                        "AI landmark sanity failed for rig %s (%s); running geometry fallback",
                        rig_id, _failure_codes,
                    )
                    push_ws(user_id, {"rig_id": rig_id,
                                      "step": "AI landmarks failed; re-running geometry…",
                                      "pct": 65})

                    _geo_glb    = tmp / "rigged_geo.glb"
                    _geo_bones  = tmp / "bones_geo.json"
                    _geo_lm     = tmp / "landmarks_geo.json"
                    _geo_pose   = tmp / "pose_geo.json"
                    _geo_pixels = tmp / "landmark_pixels_geo.json"
                    _geo_cmd    = [
                        blender_path, "--background", "--python", str(script_path), "--",
                        "--input",               str(input_path),
                        "--output",              str(_geo_glb),
                        "--bones",               str(_geo_bones),
                        "--landmarks-out",       str(_geo_lm),
                        "--pose",                str(_geo_pose),
                        "--format",              rig.original_format,
                        "--landmark-pixels-out", str(_geo_pixels),
                        "--camera-params",       str(request_path),
                    ]
                    _geo_cmd.extend(_extract_rotation_args(extra_args))

                    try:
                        _rc_g, _out_g, _err_g = _blender_call(_geo_cmd, timeout=600, cwd=cwd)
                        rig.rig_log += f"\n[GEO FALLBACK] {_out_g[-4000:]}"
                        if _rc_g == 0 and _geo_glb.exists():
                            glb_output     = _geo_glb
                            bone_data_path = _geo_bones
                            landmarks_path = _geo_lm
                            pose_data_path = _geo_pose
                            pixels_path    = _geo_pixels
                            if _geo_lm.exists():
                                _candidate_g = json.loads(_geo_lm.read_text())
                                _sr_g = check_landmarks(_candidate_g, world_aabb=_LOOSE_AABB)
                                rig.detection_method = (
                                    "geometry" if _sr_g.ok else "failed"
                                )
                            else:
                                rig.detection_method = "failed"
                        else:
                            rig.detection_method = "failed"
                    except Exception as _exc:
                        logger.exception("Geo fallback crashed for rig %s: %s", rig_id, _exc)
                        rig.detection_method = "failed"

                elif not _sr.ok:
                    _failure_codes = [f.code for f in _sr.failures]
                    rig.rig_log += (
                        "\n[RigFlow] Geometry landmark sanity failed "
                        f"({_failure_codes})"
                    )
                    logger.warning(
                        "Geometry landmark sanity failed for rig %s (%s)",
                        rig_id, _failure_codes,
                    )
                    rig.detection_method = "failed"

            push_ws(user_id, {"rig_id": rig_id, "step": "Saving rigged model…", "pct": 80})

            with open(glb_output, "rb") as f:
                rig.rigged_glb.save(f"{rig.id}_rigged.glb", File(f), save=False)

            if bone_data_path.exists():
                rig.bone_mapping = json.loads(bone_data_path.read_text())

            if landmarks_path.exists():
                rig.landmarks = json.loads(landmarks_path.read_text())

            # Landmark debug photo — best-effort, llm_vision path only.
            if ai_response_path is not None and pixels_path.exists():
                try:
                    from .debug_photo import build_landmark_debug_photo
                    _ai_picks = json.loads(
                        ai_response_path.read_text()
                    ).get("landmarks", {})
                    _final_px = json.loads(pixels_path.read_text())
                    _photo = tmp / "landmark_debug.png"
                    if build_landmark_debug_photo(
                        tmp / "ortho", _ai_picks, _final_px, _photo
                    ):
                        with open(_photo, "rb") as f:
                            rig.landmark_debug_image.save(
                                f"{rig.id}_landmarks.png", File(f), save=False
                            )
                except Exception as e:
                    logger.warning(
                        "Landmark debug photo failed for rig %s: %s", rig_id, e
                    )

            if pose_data_path.exists():
                try:
                    pose_info = json.loads(pose_data_path.read_text())
                    cls = pose_info.get("classification", "unclear")
                    valid = {c[0] for c in RiggedModel.POSE_CHOICES}
                    rig.detected_pose = cls if cls in valid else RiggedModel.POSE_UNCLEAR
                    angle = pose_info.get("angle_deg")
                    rig.pose_angle_deg = float(angle) if angle is not None else None
                    rig.pose_confidence = float(pose_info.get("confidence", 0.0))
                except (ValueError, TypeError) as e:
                    logger.warning("Pose JSON malformed: %s", e)

        rig.status = RiggedModel.STATUS_DONE
        rig.processing_time_s = time.time() - start_time
        rig.save()

        push_ws(user_id, {
            "rig_id": rig_id, "status": "done", "pct": 100,
            "rigged_glb_url": rig.rigged_glb.url if rig.rigged_glb else None,
        })
        logger.info("Rig complete %s in %.1fs", rig_id, rig.processing_time_s)
        return {"status": "done", "rig_id": rig_id}

    except Exception as e:
        rig.status = RiggedModel.STATUS_FAILED
        rig.error_message = str(e)
        rig.save(update_fields=["status", "error_message", "rig_log"])
        push_ws(user_id, {"rig_id": rig_id, "status": "failed", "error": str(e)})
        logger.error("Rig failed %s: %s", rig_id, e)
        return {"status": "failed", "rig_id": rig_id}


@shared_task(name="rigging.auto_rig_model")
def auto_rig_model(rig_id: str, extra_args: list = None) -> dict:
    return _run_rig_pipeline(rig_id, extra_args=extra_args)


@shared_task(name="rigging.auto_rig_model_with_landmarks")
def auto_rig_model_with_landmarks(rig_id: str, landmarks: dict) -> dict:
    return _run_rig_pipeline(
        rig_id,
        extra_args=["--landmarks", json.dumps(landmarks)],
    )


# ---------------------------------------------------------------------------
# Animation export (server-side bake)
# ---------------------------------------------------------------------------

def make_export_cache_key(rig, animation_ids, fmt):
    """Stable key for (rig + ordered animations + format + rig version) so an
    identical re-export returns the cached result instead of re-baking."""
    rig_stamp = rig.updated_at.isoformat() if rig.updated_at else ""
    raw = f"{rig.id}|{sorted(map(str, animation_ids))}|{fmt}|{rig_stamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _run_bake_pipeline(export_id: str) -> dict:
    """Bake the selected animations onto the rig via blender_retarget.py and
    save the animated GLB onto the AnimationExport row. Reuses the Blender
    subprocess harness + WS progress used by the rig pipeline."""
    from .models import AnimationExport
    from apps.animations.models import Animation

    exp = AnimationExport.objects.select_related("rig", "rig__user__user").get(id=export_id)
    rig = exp.rig
    user_id = str(rig.user.user.id) if (rig.user and rig.user.user) else ""

    exp.status = AnimationExport.STATUS_PROCESSING
    exp.save(update_fields=["status"])
    push_ws(user_id, {"export_id": export_id, "step": "Baking animation...", "pct": 20})

    try:
        if not rig.rigged_glb:
            raise RuntimeError("Rig has no rigged GLB to animate")
        anims = list(Animation.objects.filter(id__in=exp.animation_ids))
        order = {str(a): i for i, a in enumerate(exp.animation_ids)}
        anims.sort(key=lambda a: order.get(str(a.id), 0))
        if not anims:
            raise RuntimeError("No valid animations selected")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            rig_path = tmp / "rig.glb"
            with rig.rigged_glb.open("rb") as f:
                rig_path.write_bytes(f.read())
            bone_map_path = tmp / "bone_map.json"
            bone_map_path.write_text(json.dumps(rig.bone_mapping or {}))

            clips = []
            for a in anims:
                ext = a.gltf_file.name.split(".")[-1].lower()
                cp = tmp / f"clip_{a.id}.{ext}"
                with a.gltf_file.open("rb") as f:
                    cp.write_bytes(f.read())
                clips.append({"id": str(a.id), "name": a.name,
                              "path": str(cp), "format": ext})
            clips_path = tmp / "clips.json"
            clips_path.write_text(json.dumps(clips))

            out_path = tmp / "animated.glb"
            report_path = tmp / "report.json"
            script = settings.BLENDER_SCRIPTS_DIR / "blender_retarget.py"
            cmd = [
                settings.BLENDER_EXECUTABLE, "--background", "--python", str(script), "--",
                "--rig", str(rig_path), "--clips", str(clips_path),
                "--output", str(out_path), "--bone-map", str(bone_map_path),
                "--report-out", str(report_path),
            ]
            rc, out, err = _blender_call(
                cmd, timeout=600, cwd=str(settings.BLENDER_SCRIPTS_DIR.parent))
            if rc != 0 or not out_path.exists():
                raise RuntimeError(f"Bake failed (rc={rc}). {(err or out)[-500:]}")

            with open(out_path, "rb") as f:
                exp.output_file.save(f"{exp.id}.glb", File(f), save=False)
            if report_path.exists():
                exp.report = json.loads(report_path.read_text())

        exp.status = AnimationExport.STATUS_DONE
        exp.save()
        push_ws(user_id, {"export_id": export_id, "step": "Done", "pct": 100})
        return {"status": "done", "export_id": export_id}
    except Exception as e:
        logger.exception("Bake failed for export %s: %s", export_id, e)
        exp.status = AnimationExport.STATUS_FAILED
        exp.error_message = str(e)[:2000]
        exp.save()
        push_ws(user_id, {"export_id": export_id, "status": "failed", "error": str(e)})
        return {"status": "failed", "export_id": export_id}


@shared_task(name="rigging.bake_animation_export")
def bake_animation_export(export_id: str) -> dict:
    return _run_bake_pipeline(export_id)
