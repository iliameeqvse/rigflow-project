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

            with rig.original_file.open("rb") as f:
                input_path.write_bytes(f.read())

            push_ws(user_id, {"rig_id": rig_id, "step": "Auto-rigging with Blender...", "pct": 20})

            blender_path   = settings.BLENDER_EXECUTABLE
            blender_ran_ok = False

            if not Path(blender_path).is_file():
                logger.warning("BLENDER_EXECUTABLE '%s' not found — passthrough.", blender_path)
            else:
                try:
                    cmd = [
                        blender_path, "--background", "--python",
                        str(settings.BLENDER_SCRIPTS_DIR / "blender_autorig.py"),
                        "--",
                        "--input",  str(input_path),
                        "--output", str(glb_output),
                        "--bones",  str(bone_data_path),
                        "--format", rig.original_format,
                    ]
                    if extra_args:
                        cmd.extend(extra_args)

                    logger.info("Running Blender: %s", " ".join(cmd))
                    # Force UTF-8 + replace on undecodable bytes. Blender
                    # emits UTF-8, but on Windows subprocess defaults to
                    # cp1252 and the reader thread crashes on any non-ASCII
                    # byte (e.g. Rigify's "×" in log lines). That crash
                    # silently truncates captured output and the pipeline
                    # falls into its passthrough branch with no new GLB.
                    result = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        timeout=600, cwd=str(settings.BLENDER_SCRIPTS_DIR.parent),
                    )
                    rig.rig_log = (result.stdout or "")[-8000:]

                    if result.returncode == 0 and glb_output.exists():
                        blender_ran_ok = True
                    elif result.returncode == 2:
                        # Humanoid-gate rejection — surface to the user and
                        # skip the passthrough that would otherwise save the
                        # original mesh as a "successful" rig.
                        reason = "Uploaded model is not humanoid."
                        for line in (result.stdout or "").splitlines():
                            marker = "[RigFlow] NOT_HUMANOID:"
                            if marker in line:
                                reason = line.split(marker, 1)[1].strip()
                                break
                        raise RuntimeError(reason)
                    else:
                        logger.warning("Blender exit %s", result.returncode)
                        rig.rig_log += f"\nSTDERR: {(result.stderr or '')[-2000:]}"

                except RuntimeError:
                    # Humanoid rejection — bubble up to the outer handler,
                    # which sets status=failed with the human-readable reason.
                    raise
                except Exception as e:
                    logger.warning("Blender failed (%s) — passthrough.", e)

            output_path = glb_output if blender_ran_ok else input_path
            output_ext  = "glb"      if blender_ran_ok else rig.original_format

            push_ws(user_id, {"rig_id": rig_id, "step": "Saving rigged model...", "pct": 80})

            with open(output_path, "rb") as f:
                rig.rigged_glb.save(
                    f"{rig.id}_rigged.{output_ext}", File(f), save=False
                )

            if bone_data_path.exists():
                rig.bone_mapping = json.loads(bone_data_path.read_text())

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
def auto_rig_model(rig_id: str) -> dict:
    return _run_rig_pipeline(rig_id)


@shared_task(name="rigging.auto_rig_model_with_landmarks")
def auto_rig_model_with_landmarks(rig_id: str, landmarks: dict) -> dict:
    return _run_rig_pipeline(
        rig_id,
        extra_args=["--landmarks", json.dumps(landmarks)],
    )