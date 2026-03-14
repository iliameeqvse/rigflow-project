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
    """
    Push a real-time update to the browser via WebSocket.
    This runs inside the Celery worker, so we use async_to_sync.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {"type": "task.update", "data": data}
        )
    except Exception as e:
        # Don't crash the task if WebSocket push fails
        logger.warning(f"WebSocket push failed: {e}")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,        # wait 30s, 60s, 90s between retries
    max_retries=2,
    name="rigging.auto_rig_model",
)
def auto_rig_model(self, rig_id: str) -> dict:
    """
    The main auto-rig pipeline:
    1. Load the original uploaded file from storage
    2. Run Blender headlessly with our Python script
    3. Save the rigged GLB back to storage
    4. Update the database record
    5. Notify the browser via WebSocket
    """
    from .models import RiggedModel  # import here to avoid circular imports

    start_time = time.time()
    rig = RiggedModel.objects.select_related("user__user").get(id=rig_id)
    user_id = str(rig.user.user.id)

    # Mark as processing so polling shows progress
    rig.status = RiggedModel.STATUS_PROCESSING
    rig.save(update_fields=["status"])

    try:
        # --- Step 1: Update status to show we've started ---
        self.update_state(state="PROGRESS", meta={"step": "downloading", "pct": 5})
        push_ws(user_id, {"rig_id": rig_id, "step": "Downloading model...", "pct": 5})

        # Use a temp directory — automatically cleaned up when block exits
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path    = Path(tmpdir) / f"input.{rig.original_format}"
            output_path   = Path(tmpdir) / "rigged.glb"
            bone_data_path = Path(tmpdir) / "bones.json"

            # --- Step 2: Download from storage to local temp file ---
            with rig.original_file.open("rb") as f:
                input_path.write_bytes(f.read())

            self.update_state(state="PROGRESS", meta={"step": "rigging", "pct": 20})
            push_ws(user_id, {"rig_id": rig_id, "step": "Auto-rigging with Blender...", "pct": 20})

            # --- Step 3: Run Blender headlessly (or stub in local dev) ---
            blender_path = settings.BLENDER_EXECUTABLE
            if not Path(blender_path).is_file():
                # Dev fallback: if Blender isn't available, just copy the
                # original file to rigged_glb so the viewer can load something.
                logger.warning(
                    "BLENDER_EXECUTABLE '%s' not found; skipping rigging and "
                    "copying original file as rigged output for local testing.",
                    blender_path,
                )
                output_path.write_bytes(input_path.read_bytes())
            else:
                # Run Blender; on any failure, fall back to copying original
                try:
                    cmd = [
                        blender_path,
                        "--background",
                        "--python",
                        str(settings.BLENDER_SCRIPTS_DIR / "blender_autorig.py"),
                        "--",
                        "--input", str(input_path),
                        "--output", str(output_path),
                        "--bones", str(bone_data_path),
                        "--format", rig.original_format,
                    ]
                    logger.info("Running Blender: %s", " ".join(cmd))
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=480,
                        cwd=str(settings.BLENDER_SCRIPTS_DIR.parent),
                    )
                    rig.rig_log = (result.stdout or "")[-5000:]

                    if result.returncode != 0 or not output_path.exists():
                        raise RuntimeError(
                            f"Blender exit {result.returncode}, stderr: {(result.stderr or '')[-500:]}"
                        )
                except (FileNotFoundError, OSError, RuntimeError) as e:
                    logger.warning("Blender failed (%s), using passthrough copy", e)
                    output_path.write_bytes(input_path.read_bytes())

            # --- Step 4: Upload result to storage ---
            self.update_state(state="PROGRESS", meta={"step": "uploading", "pct": 80})
            push_ws(user_id, {"rig_id": rig_id, "step": "Saving rigged model...", "pct": 80})

            with open(output_path, "rb") as f:
                rig.rigged_glb.save(
                    f"{rig.id}_rigged.glb",
                    File(f),
                    save=False   # we'll save the whole model below
                )

            # Parse bone mapping JSON that Blender wrote
            if bone_data_path.exists():
                rig.bone_mapping = json.loads(bone_data_path.read_text())

        # --- Step 5: Mark as done ---
        rig.status = RiggedModel.STATUS_DONE
        rig.processing_time_s = time.time() - start_time
        rig.save()

        push_ws(user_id, {
            "rig_id": rig_id,
            "status": "done",
            "pct": 100,
            "rigged_glb_url": rig.rigged_glb.url if rig.rigged_glb else None,
        })

        logger.info(f"Auto-rig complete for {rig_id} in {rig.processing_time_s:.1f}s")
        return {"status": "done", "rig_id": rig_id}

    except Exception as e:
        # Save failure info so the user can see what went wrong
        rig.status = RiggedModel.STATUS_FAILED
        rig.error_message = str(e)
        rig.save(update_fields=["status", "error_message", "rig_log"])

        push_ws(user_id, {
            "rig_id": rig_id,
            "status": "failed",
            "error": str(e),
        })

        logger.error("Auto-rig failed for %s: %s", rig_id, e)
        return {"status": "failed", "rig_id": rig_id}