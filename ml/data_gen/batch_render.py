"""
Run render_keypoints.py + draw_overlay.py over a WHOLE FOLDER of FBX files.

Download a pile of Mixamo characters (T-pose, FBX) into one folder, then:

    python ml/data_gen/batch_render.py --fbx-dir "C:/Users/dzodz/OneDrive/Desktop/ml_datatraining"

For every "Foo.fbx" it creates ml/datasets/Foo/ with front.png, side.png,
labels.json and the two _overlay.png check images.

After it finishes, flip through the *_overlay.png images. Keep the ones where
the dots sit on the joints; delete the folder for any model that came out wrong
(bad mesh, weird bone names) so junk doesn't poison training.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ML_ROOT = HERE.parent
DEFAULT_BLENDER = r"C:\Program Files\blender-5.0.1-windows-x64\blender.exe"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fbx-dir", required=True, help="folder full of .fbx files")
    p.add_argument("--out-root", default=str(ML_ROOT / "datasets"),
                   help="where per-model folders are written")
    p.add_argument("--blender", default=DEFAULT_BLENDER)
    args = p.parse_args()

    fbx_dir = Path(args.fbx_dir)
    fbx_files = sorted(fbx_dir.glob("*.fbx"))
    if not fbx_files:
        print(f"No .fbx files found in {fbx_dir}")
        sys.exit(1)

    print(f"Found {len(fbx_files)} FBX files.")
    print("Each model takes ~10-20s (Blender startup + render). Be patient — "
          "this is NOT frozen.\n")
    ok, failed = [], []
    for i, fbx in enumerate(fbx_files, 1):
        # Folder name = file name without extension, spaces -> underscores.
        name = fbx.stem.replace(" ", "_")
        out_dir = Path(args.out_root) / name
        out_dir.mkdir(parents=True, exist_ok=True)
        # Blender's output goes to a log file (not an in-memory pipe) so it
        # can't stall and you can read it if something goes wrong.
        log_path = out_dir / "_blender.log"
        print(f"[{i}/{len(fbx_files)}] {fbx.name} -> datasets/{name} ... ",
              end="", flush=True)

        try:
            with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
                render = subprocess.run(
                    [args.blender, "--background", "--python",
                     str(HERE / "render_keypoints.py"), "--",
                     "--fbx", str(fbx), "--out", str(out_dir)],
                    stdout=lf, stderr=subprocess.STDOUT, text=True,
                    timeout=240,   # a single model can't hang the whole batch
                )
        except subprocess.TimeoutExpired:
            print("TIMEOUT (>240s) — skipped")
            failed.append(fbx.name)
            continue

        if render.returncode != 0 or not (out_dir / "labels.json").exists():
            print("FAILED")
            tail = log_path.read_text(encoding="utf-8", errors="replace").strip()
            tail = "\n".join(l for l in tail.splitlines()
                             if "User property type 'Short'" not in l)[-800:]
            print("    " + tail.replace("\n", "\n    "))
            failed.append(fbx.name)
            continue

        # Warn (don't fail) if any bones were missing for this model.
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        for line in log_text.splitlines():
            if "bones not found" in line:
                print(f"\n    NOTE: {line.split('WARNING:')[-1].strip()}", end="")

        subprocess.run([sys.executable, str(HERE / "draw_overlay.py"),
                        "--dir", str(out_dir)], capture_output=True, text=True)
        print("ok")
        ok.append(name)

    print(f"\nDone. {len(ok)} ok, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))
    print(f"\nNow eyeball the overlays in {args.out_root}\\*\\front_overlay.png")
    print("Delete any folder whose dots are wrong before you train.")


if __name__ == "__main__":
    main()
