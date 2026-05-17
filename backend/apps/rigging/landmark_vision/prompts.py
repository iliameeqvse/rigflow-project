"""Vision prompt template for landmark detection."""

VISION_PROMPT_TEMPLATE = (
    "You are an expert character technical director labeling a 3D character mesh\n"
    "for auto-rigging. Four orthographic 512×512 renders are attached: front, back,\n"
    "left, right (in that order).\n"
    "\n"
    "## Orientation markers (READ THIS FIRST)\n"
    "Two small bright cubes are composited into the FRONT and BACK renders as\n"
    "anatomical ground truth — they disambiguate the character's left and right\n"
    "regardless of which way the character is facing:\n"
    "  * RED  cube → placed beside the character's LEFT  (left-arm side).\n"
    "  * BLUE cube → placed beside the character's RIGHT (right-arm side).\n"
    "\n"
    "The 'front' label refers to the camera, not the character. The character may\n"
    "be facing toward or away from the front camera. Do NOT assume left = viewer's\n"
    "left. Use the colored cubes as the single source of truth.\n"
    "\n"
    "Rule applied to EVERY paired landmark in the front and back renders:\n"
    '  Every "left_*"  coordinate must lie on the SAME side of the image as the\n'
    "  RED  cube.\n"
    '  Every "right_*" coordinate must lie on the SAME side of the image as the\n'
    "  BLUE cube.\n"
    "This holds even when the front render shows the character's back.\n"
    "\n"
    "Side views (left, right) have no markers — infer sides there from the\n"
    "front/back labels you already committed to.\n"
    "\n"
    "## Task\n"
    "Identify the pixel coordinates of these 14 anatomical landmarks IN EACH VIEW:\n"
    "  chin, groin,\n"
    "  left_shoulder, right_shoulder,\n"
    "  left_elbow,    right_elbow,\n"
    "  left_wrist,    right_wrist,\n"
    "  left_hip,      right_hip,\n"
    "  left_knee,     right_knee,\n"
    "  left_ankle,    right_ankle.\n"
    "\n"
    "Pixel origin is top-left; x grows right, y grows down.\n"
    "If a landmark is occluded or not visible in a given view, set it to null for\n"
    "that view only. At least the front view must contain non-null values for all\n"
    "landmarks anatomically visible from the front.\n"
    "\n"
    "Do NOT return the marker cubes themselves as landmarks — they are scene\n"
    "helpers, not body parts.\n"
    "\n"
    "## Mesh-object classification\n"
    "Classify each distinct mesh object listed below as exactly one of:\n"
    "  body, hat, accessory_held_left, accessory_held_right, clothing, other.\n"
    "The marker cubes are NOT user mesh objects and will not appear in the list.\n"
    "\n"
    "## Response format\n"
    "Respond ONLY with valid JSON matching this schema — no prose, no markdown fence:\n"
    "{\n"
    '  "landmarks": {\n'
    '    "front": {"chin": [x, y], "groin": [x, y], "left_shoulder": [x, y], "right_shoulder": [x, y],\n'
    '              "left_elbow": [x, y], "right_elbow": [x, y], "left_wrist": [x, y], "right_wrist": [x, y],\n'
    '              "left_hip": [x, y], "right_hip": [x, y], "left_knee": [x, y], "right_knee": [x, y],\n'
    '              "left_ankle": [x, y], "right_ankle": [x, y]},\n'
    '    "back":  { ...same 14 keys, null where occluded... },\n'
    '    "left":  { ...same 14 keys, null where occluded... },\n'
    '    "right": { ...same 14 keys, null where occluded... }\n'
    "  },\n"
    '  "mesh_objects": {\n'
    '    "<object_name>": "body" | "hat" | "accessory_held_left" | "accessory_held_right" | "clothing" | "other"\n'
    "  },\n"
    '  "notes": "<optional one-line observation>"\n'
    "}\n"
    "\n"
    "Mesh objects in this scene: {mesh_object_names}"
)
