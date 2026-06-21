# RigFlow ML — custom keypoint network

Goal: train our own network that looks at front + side renders of a model and
predicts where the 14 skeleton joints are, to replace/beat the Haiku vision
call in the auto-rig pipeline.

## Layout

```
ml/
├── data_gen/     # turn rigged models into training examples (images + labels)
├── train/        # PyTorch training code            (next step)
├── inference/    # load a trained model + predict    (later — feeds local_provider.py)
├── weights/      # trained .pth files     (gitignored — big, regenerable)
├── datasets/     # generated images + labels (gitignored — big, regenerable)
└── requirements.txt
```

## Step 1 — make training data (you are here)

A correctly-rigged model is a free, perfectly-labelled example: render it, and
the known bone positions tell you exactly where each joint is in the image.
Download rigged humanoids from Mixamo (FBX) and run:

```bash
# 1. render the two views + compute the true joint pixel positions
blender --background --python ml/data_gen/render_keypoints.py -- \
    --fbx "C:/path/to/mixamo_model.fbx" --out "ml/datasets/model_01"

# 2. draw the labels on top so you can CHECK they're right
python ml/data_gen/draw_overlay.py --dir "ml/datasets/model_01"
```

Open `ml/datasets/model_01/front_overlay.png`. Every dot should sit on its
joint. If it does, the example is good. Repeat for ~100 models to build a
dataset, then move on to `train/`.

`front.png` / `side.png` are the network's INPUT (no skeleton drawn).
`labels.json` is the TARGET. The `_overlay.png` images are for your eyes only.

## Step 2 — train the network

Install PyTorch once (CPU build is fine to start):

```bash
pip install torch torchvision
```

Then train on the front views in datasets/:

```bash
python train/train.py --epochs 300
```

It fine-tunes a pretrained ResNet-18 to predict the 14 front-view landmarks,
reports validation error in pixels, and saves the best weights to
`weights/keypoints.pth`.

With only ~14 examples the model OVERFITS (memorises rather than generalises) —
expected. Today's goal is a working loop and a falling loss. Real accuracy needs
hundreds of examples; keep adding Mixamo humanoids and re-running data_gen.

## Step 3 — see what it learned

```bash
python inference/predict.py --image "datasets/Remy_(1)/front.png"
```

Writes `front_pred.png` with the network's guessed joints (blue dots). Try a
training image first (should look good), then a brand-new rendered model to test
real generalisation.

- `train/dataset.py`  loads images + labels, does augmentation (L/R flip, jitter)
- `train/model.py`    the ResNet-18 + keypoint head
- `train/train.py`    the training loop
- `inference/predict.py`  load weights + predict on one image (this is what the
  future `local_provider.py` will call from the backend)

## Why our own net can beat Haiku

We only ever train on CORRECT joint positions — auto-generated from already-rigged
models, plus any hand-corrections we make in the editor. We never train on a
guess. Haiku is a general model that's never seen a rig; ours trains on nothing
but rigs, including the weird stylised ones it keeps getting wrong.
