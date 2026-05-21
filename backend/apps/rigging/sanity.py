"""Pure landmark sanity checks. No Blender deps; safe to unit-test."""
from dataclasses import dataclass, field

LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow",    "right_elbow",
    "left_wrist",    "right_wrist",
    "left_hip",      "right_hip",
    "left_knee",     "right_knee",
    "left_ankle",    "right_ankle",
)

PAIRS = (
    ("left_shoulder", "right_shoulder", "shoulder"),
    ("left_elbow",    "right_elbow",    "elbow"),
    ("left_wrist",    "right_wrist",    "wrist"),
    ("left_hip",      "right_hip",      "hip"),
    ("left_knee",     "right_knee",     "knee"),
    ("left_ankle",    "right_ankle",    "ankle"),
)

# |left_X - right_X| / max(|left_X|, |right_X|, 0.01) must be < this.
# 0.60 is intentionally loose — accommodates asymmetric stylised characters.
ASYMMETRY_TOLERANCE = 0.60
AABB_INFLATE        = 0.05  # 5 % margin around the mesh AABB
MIN_TORSO_GAP       = 0.10  # groin must be at least this far below chin (Y-up)


@dataclass
class Failure:
    code: str
    detail: str = ""


@dataclass
class SanityResult:
    ok: bool
    failures: list = field(default_factory=list)


def _inflate(box, frac):
    lo, hi = box
    delta = tuple(frac * (hi[i] - lo[i]) for i in range(3))
    return (
        tuple(lo[i] - delta[i] for i in range(3)),
        tuple(hi[i] + delta[i] for i in range(3)),
    )


def _in_box(p, box):
    lo, hi = box
    return all(lo[i] <= p[i] <= hi[i] for i in range(3))


def check_landmarks(landmarks: dict, *, world_aabb) -> SanityResult:
    """Run all sanity rules. Returns SanityResult; callers decide which
    failures are blocking vs. advisory."""
    failures = []

    # Completeness — bail early so later checks can index safely
    for k in LANDMARK_KEYS:
        if k not in landmarks:
            failures.append(Failure(f"missing_{k}"))
    if failures:
        return SanityResult(ok=False, failures=failures)

    # Y-axis torso order: groin must be below chin by at least MIN_TORSO_GAP
    chin_y  = landmarks["chin"][1]
    groin_y = landmarks["groin"][1]
    if groin_y >= chin_y - MIN_TORSO_GAP:
        failures.append(Failure(
            "groin_above_chin",
            f"chin.y={chin_y:.3f} groin.y={groin_y:.3f} gap={chin_y - groin_y:.3f}",
        ))

    # Bilateral symmetry: left.x should ≈ -right.x (mirror on X).
    # Check |lx + rx| / max(|lx|, |rx|, 0.01) < ASYMMETRY_TOLERANCE.
    for lk, rk, label in PAIRS:
        lx = landmarks[lk][0]
        rx = landmarks[rk][0]
        denom = max(abs(lx), abs(rx), 0.01)
        if abs(lx + rx) / denom > ASYMMETRY_TOLERANCE:
            failures.append(Failure(
                f"asymmetry_{label}",
                f"L.x={lx:.3f} R.x={rx:.3f} ratio={abs(lx - rx) / denom:.2f}",
            ))

    # AABB bounds (inflated 5 %)
    inflated = _inflate(world_aabb, AABB_INFLATE)
    for k in LANDMARK_KEYS:
        if not _in_box(landmarks[k], inflated):
            failures.append(Failure(
                f"outside_aabb_{k}",
                f"point={landmarks[k]} box={inflated}",
            ))

    # Anatomical Y-ordering. Keep the leg/torso stack strict, but do not
    # require shoulder <= chin: stylized characters with large heads, masks,
    # or low chins can have shoulder joints visually above the chin point.
    z_chain = [
        ("ankle",    min(landmarks["left_ankle"][1],    landmarks["right_ankle"][1])),
        ("knee",     min(landmarks["left_knee"][1],     landmarks["right_knee"][1])),
        ("hip",      min(landmarks["left_hip"][1],      landmarks["right_hip"][1])),
        ("groin",    landmarks["groin"][1]),
        ("shoulder", min(landmarks["left_shoulder"][1], landmarks["right_shoulder"][1])),
    ]
    for (a, av), (b, bv) in zip(z_chain, z_chain[1:]):
        if av > bv:
            failures.append(Failure(
                f"order_{a}_above_{b}",
                f"{a}.y={av:.3f} > {b}.y={bv:.3f}",
            ))

    return SanityResult(ok=not failures, failures=failures)
