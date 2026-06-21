"""
Draw the labels on top of the renders so you can SEE if they're correct.

This is your sanity check. After render_keypoints.py makes front.png / side.png
/ labels.json, run:

    python ml/data_gen/draw_overlay.py --dir ml/datasets/my_model

It writes front_overlay.png and side_overlay.png with a dot + name on every
joint. If the wrist dot sits on the wrist, your labels are good and you can
trust this model as a training example. If a dot is in the wrong place, the
bone mapping or projection is off for that model — investigate before training.

These overlay images are for YOUR EYES ONLY. Never feed them to the network —
it trains on the clean front.png / side.png.

Needs Pillow:  pip install pillow   (it's in ml/requirements.txt)
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

# front.png holds the "front" labels; side.png holds the "side" labels.
PNG_FOR_VIEW = {"front": "front.png", "side": "side.png"}
R = 4  # dot radius in pixels


def draw_one(img_path, points, out_path):
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for name, xy in points.items():
        if xy is None:
            continue
        x, y = xy
        draw.ellipse([x - R, y - R, x + R, y + R], fill=(255, 40, 40))
        draw.text((x + R + 2, y - R), name, fill=(255, 255, 0))
    img.save(out_path)
    print(f"[draw_overlay] wrote {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True, help="folder with front.png/side.png/labels.json")
    args = p.parse_args()
    d = Path(args.dir)

    labels = json.loads((d / "labels.json").read_text())
    for view, png_name in PNG_FOR_VIEW.items():
        img_path = d / png_name
        if not img_path.exists():
            print(f"[draw_overlay] skip {view}: {png_name} missing")
            continue
        out = d / png_name.replace(".png", "_overlay.png")
        draw_one(img_path, labels.get(view, {}), out)


if __name__ == "__main__":
    main()
