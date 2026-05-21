"""Compositing for the landmark debug photo (debug/audit aid).

Draws a 2×2 grid of the four ortho renders, marking where the AI placed each
landmark (hollow orange circle) versus where the rig actually used it (filled
green dot). Strictly best-effort: any failure is logged and returns False so
the rig still completes.
"""
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_VIEWS = ("front", "back", "left", "right")
# (column, row) of each view in the 2×2 grid.
_GRID = {"front": (0, 0), "back": (1, 0), "left": (0, 1), "right": (1, 1)}

_AI_COLOR = (255, 140, 0)        # orange — AI pick
_FINAL_COLOR = (40, 200, 60)     # green  — final used
_TEXT_COLOR = (255, 255, 255)
_CONNECT_COLOR = (160, 160, 160)


def build_landmark_debug_photo(ortho_dir, ai_picks, final_pixels, out_path):
    """Composite a 2×2 annotated debug photo.

    ortho_dir     directory containing front.png/back.png/left.png/right.png
    ai_picks      {view: {key: [px, py] | None}} — AI's returned pixels
    final_pixels  {view: {key: [px, py] | None}} — rig's final pixels
    out_path      destination PNG path

    Returns True on success, False on any missing input or draw error.
    """
    try:
        ortho_dir = Path(ortho_dir)
        tiles = {}
        for view in _VIEWS:
            png = ortho_dir / f"{view}.png"
            if not png.is_file():
                log.warning("Debug photo: missing ortho render %s", png)
                return False
            tiles[view] = Image.open(png).convert("RGB")

        w, h = tiles["front"].size
        canvas = Image.new("RGB", (w * 2, h * 2), (20, 20, 20))
        font = ImageFont.load_default()

        for view in _VIEWS:
            tile = tiles[view]
            draw = ImageDraw.Draw(tile)
            view_ai = (ai_picks or {}).get(view) or {}
            view_final = (final_pixels or {}).get(view) or {}
            for key in sorted(set(view_ai) | set(view_final)):
                ap = view_ai.get(key)
                fp = view_final.get(key)
                if ap and fp:
                    draw.line([tuple(ap), tuple(fp)],
                              fill=_CONNECT_COLOR, width=1)
                if ap:
                    _circle(draw, ap, 6, _AI_COLOR, 2)
                if fp:
                    _dot(draw, fp, 4, _FINAL_COLOR)
                anchor = fp or ap
                if anchor:
                    draw.text((anchor[0] + 7, anchor[1] - 5), key,
                              fill=_TEXT_COLOR, font=font)
            draw.text((6, 6), view.upper(), fill=_TEXT_COLOR, font=font)
            col, row = _GRID[view]
            canvas.paste(tile, (col * w, row * h))

        ImageDraw.Draw(canvas).text(
            (6, h * 2 - 16),
            "orange = AI pick    green = final used",
            fill=_TEXT_COLOR, font=font,
        )

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "PNG")
        return True
    except Exception as e:
        log.warning("Debug photo build failed: %s", e)
        return False


def _circle(draw, center, r, outline, width):
    x, y = center
    draw.ellipse([x - r, y - r, x + r, y + r], outline=outline, width=width)


def _dot(draw, center, r, fill):
    x, y = center
    draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)
