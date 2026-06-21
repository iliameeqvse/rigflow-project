"""
The network: a pretrained ResNet-18 with its classifier swapped for a small head
that outputs 2 numbers (x, y) per landmark.

Why pretrained: ResNet-18 has already learned generic image features (edges,
shapes, body parts) from millions of photos. We reuse that and only teach it
WHERE our specific joints are. This is "transfer learning" and it's the only
reason training works with a small dataset.

Output is passed through sigmoid so every coordinate stays in 0..1, matching the
normalised targets in dataset.py.
"""
import torch.nn as nn
import torchvision
from torchvision.models import resnet18

from dataset import NUM_LANDMARKS


def build_model(pretrained=True):
    try:
        weights = torchvision.models.ResNet18_Weights.DEFAULT if pretrained else None
        net = resnet18(weights=weights)
    except Exception:
        net = resnet18(pretrained=pretrained)   # older torchvision fallback

    in_features = net.fc.in_features
    net.fc = nn.Sequential(
        nn.Linear(in_features, 256),
        nn.ReLU(inplace=True),
        nn.Dropout(0.3),                         # guards against overfitting
        nn.Linear(256, NUM_LANDMARKS * 2),
        nn.Sigmoid(),                            # keep outputs in 0..1
    )
    return net
