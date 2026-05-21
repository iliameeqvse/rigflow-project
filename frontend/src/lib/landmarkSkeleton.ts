import type { LandmarkKey } from "@/lib/api";

/**
 * Landmark pairs the editor's skeleton overlay connects. This is a placement
 * guide, not the final 73-bone DEF rig.
 */
export const SKELETON_EDGES: ReadonlyArray<readonly [LandmarkKey, LandmarkKey]> = [
  // spine
  ["groin", "chin"],
  // shoulders
  ["chin", "left_shoulder"],
  ["chin", "right_shoulder"],
  // left arm
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  // right arm
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  // pelvis
  ["groin", "left_hip"],
  ["groin", "right_hip"],
  // left leg
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  // right leg
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
];
