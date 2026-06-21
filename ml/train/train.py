"""
Train the keypoint network.

    python train/train.py --epochs 300

It splits your datasets/ folders into train/val, fine-tunes the pretrained
ResNet on the train set, reports validation error in PIXELS (easy to interpret:
"on average the predicted joint is N pixels from the true joint"), and saves the
best weights to weights/keypoints.pth.

With only ~14 examples expect the model to OVERFIT — train error will fall much
lower than val error. That's normal and not a bug. The cure is more data, not
more epochs. The goal today is to confirm the whole loop runs and the loss goes
down.
"""
import argparse
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Subset

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))           # so `import dataset/model` works anywhere
from dataset import KeypointDataset, IMG_SIZE   # noqa: E402
from model import build_model                   # noqa: E402

ML_ROOT = HERE.parent


def masked_mse(pred, target, mask):
    """MSE over present landmarks only (mask zeroes out missing ones)."""
    se = (pred - target) ** 2 * mask
    return se.sum() / mask.sum().clamp(min=1.0)


def mean_pixel_error(pred, target, mask, img_size=IMG_SIZE):
    """Average distance (in pixels) between predicted and true present landmarks."""
    pred = pred.reshape(-1, 2)
    target = target.reshape(-1, 2)
    m = mask.reshape(-1, 2)[:, 0].bool()          # one bit per landmark
    if m.sum() == 0:
        return float("nan")
    d = ((pred - target) * img_size) ** 2
    dist = d.sum(dim=1).sqrt()[m]
    return dist.mean().item()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(ML_ROOT / "datasets"))
    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--val-frac", type=float, default=0.2)
    p.add_argument("--out", default=str(ML_ROOT / "weights" / "keypoints.pth"))
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}")

    full = KeypointDataset(args.data, augment=True)
    n = len(full)
    n_val = max(1, int(n * args.val_frac))
    # Deterministic split (no Math.random equivalent needed; fixed generator).
    g = torch.Generator().manual_seed(42)
    perm = torch.randperm(n, generator=g).tolist()
    val_idx, train_idx = perm[:n_val], perm[n_val:]
    train_set = Subset(full, train_idx)
    # Val uses the same dataset but we disable augmentation by wrapping a clean copy.
    val_full = KeypointDataset(args.data, augment=False)
    val_set = Subset(val_full, val_idx)
    print(f"{n} examples -> {len(train_set)} train, {len(val_set)} val")

    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size)

    model = build_model(pretrained=True).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_val_px = float("inf")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        tr_loss = 0.0
        for x, target, mask in train_loader:
            x, target, mask = x.to(device), target.to(device), mask.to(device)
            opt.zero_grad()
            pred = model(x)
            loss = masked_mse(pred, target, mask)
            loss.backward()
            opt.step()
            tr_loss += loss.item() * x.size(0)
        tr_loss /= len(train_set)

        model.eval()
        val_px = 0.0
        with torch.no_grad():
            for x, target, mask in val_loader:
                x, target, mask = x.to(device), target.to(device), mask.to(device)
                pred = model(x)
                val_px += mean_pixel_error(pred, target, mask) * x.size(0)
        val_px /= len(val_set)

        if val_px < best_val_px:
            best_val_px = val_px
            torch.save({
                "state_dict": model.state_dict(),
                "img_size": IMG_SIZE,
            }, args.out)

        if epoch % 10 == 0 or epoch == 1:
            print(f"epoch {epoch:4d} | train loss {tr_loss:.5f} "
                  f"| val err {val_px:6.1f}px | best {best_val_px:6.1f}px")

    print(f"\nDone. Best val error: {best_val_px:.1f}px. Saved -> {args.out}")
    print("Reminder: with this few images the model overfits. Add more data for "
          "real accuracy. Try it on an image with inference/predict.py.")


if __name__ == "__main__":
    main()
