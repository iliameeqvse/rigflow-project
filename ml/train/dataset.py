"""
Dataset: reads the folders made by data_gen/ and serves (image, keypoints) to
PyTorch for training.

Each datasets/<model>/ has:
    front.png      the input image (no skeleton drawn)
    labels.json    {"front": {landmark: [px, py] | null, ...}, "side": {...}}

We train on the FRONT view only for v1 — it's the most informative and carries
all 14 landmarks. (Side view collapses the arms in a T-pose, so it's a weaker
signal; we add it later.)

Coordinates are stored normalised to 0..1 (pixel / image_size) so the network's
output is resolution-independent. A `mask` marks which landmarks are present
(some are null), so missing ones don't contribute to the loss.
"""
import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from torchvision import transforms
from PIL import Image

# Fixed landmark order — the network's outputs map to THIS order. Never reorder
# without retraining.
LANDMARKS = [
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]
NUM_LANDMARKS = len(LANDMARKS)

# Index pairs that swap when the image is mirrored left<->right.
_NAME_TO_IDX = {n: i for i, n in enumerate(LANDMARKS)}
FLIP_PAIRS = [
    (_NAME_TO_IDX[f"left_{p}"], _NAME_TO_IDX[f"right_{p}"])
    for p in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
]

IMG_SIZE = 256                      # ResNet input size
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_target(label_dict, img_w, img_h):
    """Turn a labels.json 'front' dict into (coords[N,2], mask[N]) normalised 0..1."""
    coords = torch.zeros(NUM_LANDMARKS, 2)
    mask = torch.zeros(NUM_LANDMARKS)
    for i, name in enumerate(LANDMARKS):
        xy = label_dict.get(name)
        if xy is None:
            continue
        coords[i, 0] = xy[0] / img_w
        coords[i, 1] = xy[1] / img_h
        mask[i] = 1.0
    return coords, mask


class KeypointDataset(Dataset):
    def __init__(self, root="datasets", augment=True):
        self.samples = []
        for d in sorted(Path(root).iterdir()):
            lp, ip = d / "labels.json", d / "front.png"
            if lp.exists() and ip.exists():
                self.samples.append((ip, json.loads(lp.read_text())["front"]))
        if not self.samples:
            raise RuntimeError(f"no training examples found under {root}/")
        self.augment = augment
        self.jitter = transforms.ColorJitter(0.3, 0.3, 0.3, 0.05)
        self.normalize = transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label_dict = self.samples[idx]
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        coords, mask = build_target(label_dict, w, h)
        img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)

        if self.augment:
            # Horizontal flip: mirror image, x -> 1-x, and swap L/R landmarks.
            if torch.rand(1).item() < 0.5:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
                coords[:, 0] = 1.0 - coords[:, 0]
                for a, b in FLIP_PAIRS:
                    coords[[a, b]] = coords[[b, a]]
                    mask[[a, b]] = mask[[b, a]]
                # flipped-but-missing landmarks keep coord 0; zero them via mask
                coords[mask == 0] = 0.0
            img = self.jitter(img)

        x = self.normalize(transforms.functional.to_tensor(img))
        # flatten coords to [2N] and expand mask to match (x,y share a mask bit)
        target = coords.reshape(-1)                       # [2N]
        mask2 = mask.repeat_interleave(2)                 # [2N]
        return x, target, mask2
