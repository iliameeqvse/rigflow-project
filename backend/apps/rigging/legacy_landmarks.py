"""Default 16-key landmarks for rigs that pre-date the auto-detection
feature. Computed from a unit-height humanoid silhouette so the editor
has draggable starting points instead of all-zero coordinates.
"""

DEFAULT_LANDMARKS_UNIT_HEIGHT = {
    # three.js editor space, model normalized to 2.0 units tall
    "chin":           [ 0.00, 1.84,  0.00],
    "groin":          [ 0.00, 1.00,  0.00],
    "left_shoulder":  [ 0.20, 1.64,  0.00],
    "right_shoulder": [-0.20, 1.64,  0.00],
    "left_elbow":     [ 0.50, 1.64,  0.05],
    "right_elbow":    [-0.50, 1.64,  0.05],
    "left_wrist":     [ 0.80, 1.64,  0.00],
    "right_wrist":    [-0.80, 1.64,  0.00],
    "left_hip":       [ 0.10, 1.00,  0.00],
    "right_hip":      [-0.10, 1.00,  0.00],
    "left_knee":      [ 0.10, 0.50,  0.00],
    "right_knee":     [-0.10, 0.50,  0.00],
    "left_ankle":     [ 0.10, 0.00,  0.00],
    "right_ankle":    [-0.10, 0.00,  0.00],
    # Heel: behind the ankle (-Z is backward in editor space) at floor level.
    "left_heel":      [ 0.10, 0.00, -0.10],
    "right_heel":     [-0.10, 0.00, -0.10],
}


def default_landmarks_for_rig(rig):
    """Return the same defaults regardless of rig — three.js space is
    normalized to a fixed display height. The editor will autoFit and
    rescale the user's drags back into mesh-space on submit."""
    return dict(DEFAULT_LANDMARKS_UNIT_HEIGHT)
