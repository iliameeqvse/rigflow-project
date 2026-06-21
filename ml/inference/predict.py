"""
Run a trained model on one image and draw the predicted joints.

    python inference/predict.py --image ml/datasets/Remy_(1)/front.png

Writes <image>_pred.png next to the input, with the network's guessed joints
dotted on. This is how you SEE what the network learned. Try it first on an
image it trained on (dots should land well), then on a brand-new model you
render with data_gen — that shows whether it actually generalises.
"""
import argparse
import sys
from pathlib import Path

import torch
from torchvision import transforms
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ML_ROOT = HERE.parent
sys.path.insert(0, str(ML_ROOT / "train"))      # reuse dataset/model definitions
from dataset import (LANDMARKS, IMG_SIZE, IMAGENET_MEAN,   # noqa: E402
                     IMAGENET_STD, NUM_LANDMARKS)
from model import build_model                             # noqa: E402

R = 4


def load_model(weights_path, device):
    ckpt = torch.load(weights_path, map_location=device)
    model = build_model(pretrained=False).to(device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def predict(model, img_path, device):
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    net_in = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    x = transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)(
        transforms.functional.to_tensor(net_in)
    ).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(x).cpu().reshape(NUM_LANDMARKS, 2)
    # normalised 0..1 -> original pixel space
    return {name: (out[i, 0].item() * w, out[i, 1].item() * h)
            for i, name in enumerate(LANDMARKS)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--weights", default=str(ML_ROOT / "weights" / "keypoints.pth"))
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(args.weights, device)
    preds = predict(model, args.image, device)

    img = Image.open(args.image).convert("RGB")
    draw = ImageDraw.Draw(img)
    for name, (x, y) in preds.items():
        draw.ellipse([x - R, y - R, x + R, y + R], fill=(40, 200, 255))
        draw.text((x + R + 2, y - R), name, fill=(255, 255, 0))
    out_path = str(Path(args.image).with_name(Path(args.image).stem + "_pred.png"))
    img.save(out_path)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
