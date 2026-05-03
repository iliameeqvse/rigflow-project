import subprocess
import time
import json
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


def _run_rig_pipeline(rig_id: str, extra_args: list = None) -> dict:
    """
    Plain function — NOT a Celery task — so it can be called directly from
    views and background threads without bind/self injection issues.
    extra_args: additional CLI flags forwarded to blender_autorig.py
    """
    from .models import RiggedModel

    start_time = time.time()
    rig = RiggedModel.objects.select_related("user__user").get(id=rig_id)
    user_id = str(rig.user.user.id)

    rig.status = RiggedModel.STATUS_PROCESSING
    rig.save(update_fields=["status"])

    try:
        push_ws(user_id, {"rig_id": rig_id, "step": "Downloading model...", "pct": 5})

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path     = Path(tmpdir) / f"input.{rig.original_format}"
            glb_output     = Path(tmpdir) / "rigged.glb"
            bone_data_path = Path(tmpdir) / "bones.json"
            pose_data_path = Path(tmpdir) / "pose.json"

            with rig.original_file.open("rb") as f:
                input_path.write_bytes(f.read())

            push_ws(user_id, {"rig_id": rig_id, "step": "Auto-rigging with Blender...", "pct": 20})

            blender_path = settings.BLENDER_EXECUTABLE
            failure_reason: str | None = None

            if not Path(blender_path).is_file():
                failure_reason = (
                    f"Blender executable not found at '{blender_path}'. "
                    "Set the BLENDER_PATH environment variable so Django can find it."
                )
            else:
                try:
                    cmd = [
                        blender_path, "--background", "--python",
                        str(settings.BLENDER_SCRIPTS_DIR / "blender_autorig.py"),
                        "--",
                        "--input",  str(input_path),
                        "--output", str(glb_output),
                        "--bones",  str(bone_data_path),
                        "--pose",   str(pose_data_path),
                        "--format", rig.original_format,
                    ]
                    if extra_args:
                        cmd.extend(extra_args)

                    logger.info("Running Blender: %s", " ".join(cmd))
                    # UTF-8 + replace on undecodable bytes. Blender emits
                    # UTF-8, but on Windows subprocess defaults to cp1252
                    # and the reader thread crashes on any non-ASCII byte
                    # (e.g. Rigify's "×" in log lines), silently truncating
                    # captured stdout.
                    result = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        timeout=600, cwd=str(settings.BLENDER_SCRIPTS_DIR.parent),
                    )
                    rig.rig_log = (result.stdout or "")[-8000:]

                    if result.returncode != 0:
                        rig.rig_log += f"\nSTDERR: {(result.stderr or '')[-2000:]}"
                        failure_reason = (
                            f"Blender exited with code {result.returncode}. "
                            "See rig log for Rigify / pipeline errors."
                        )
                    elif not glb_output.exists():
                        failure_reason = "Blender finished cleanly but produced no GLB output."

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
                ])
                push_ws(user_id, {
                    "rig_id": rig_id,
                    "status": "failed",
                    "error": failure_reason,
                })
                logger.error("Rig failed %s: %s", rig_id, failure_reason)
                return {"status": "failed", "rig_id": rig_id}

            push_ws(user_id, {"rig_id": rig_id, "step": "Saving rigged model...", "pct": 80})

            with open(glb_output, "rb") as f:
                rig.rigged_glb.save(
                    f"{rig.id}_rigged.glb", File(f), save=False
                )

            if bone_data_path.exists():
                rig.bone_mapping = json.loads(bone_data_path.read_text())

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


# Keep Celery tasks for production (worker-based) deployments
@shared_task(name="rigging.auto_rig_model")
def auto_rig_model(rig_id: str, extra_args: list = None) -> dict:
    return _run_rig_pipeline(rig_id, extra_args=extra_args)


@shared_task(name="rigging.auto_rig_model_with_landmarks")
def auto_rig_model_with_landmarks(rig_id: str, landmarks: dict) -> dict:
    return _run_rig_pipeline(
        rig_id,
        extra_args=["--landmarks", json.dumps(landmarks)],
    )