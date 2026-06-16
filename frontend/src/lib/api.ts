import axios, { AxiosError, AxiosInstance, isAxiosError } from "axios";

const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
  withCredentials: false,
});

// ── Token helpers ─────────────────────────────────────────────────────────────

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access");
}

export function getUser(): StoredUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveAuth(access: string, refresh: string, user: StoredUser) {
  localStorage.setItem("access", access);
  localStorage.setItem("refresh", refresh);
  localStorage.setItem("user", JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
  localStorage.removeItem("user");
}

export function isLoggedIn(): boolean {
  return !!getAccessToken();
}

// ── Attach JWT to every request ───────────────────────────────────────────────

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Auto-refresh on 401 ───────────────────────────────────────────────────────

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response?.status === 401 &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;
      const refresh =
        typeof window !== "undefined"
          ? localStorage.getItem("refresh")
          : null;
      if (refresh) {
        try {
          const { data } = await axios.post(
            `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/auth/token/refresh/`,
            { refresh },
          );
          localStorage.setItem("access", data.access);
          originalRequest.headers.Authorization = `Bearer ${data.access}`;
          return api.request(originalRequest);
        } catch {
          clearAuth();
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        }
      } else {
        clearAuth();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  },
);

// ── Types ─────────────────────────────────────────────────────────────────────

export interface StoredUser {
  id: number;
  email: string;
  username: string;
  plan?: string;
  avatar?: string | null;
}

export type DetectionMethod = "geometry" | "llm_vision" | "user_landmarks" | "failed" | "";

export interface RiggedModel {
  id: string;
  name: string;
  status: "pending" | "processing" | "done" | "failed";
  original_format: string;
  rigged_glb_url: string | null;
  bone_mapping: Record<string, string>;
  file_size_mb: number;
  detected_pose?: "t_pose" | "a_pose" | "arms_down" | "unclear";
  pose_angle_deg?: number | null;
  pose_confidence?: number;
  detection_method?: DetectionMethod;
  used_existing_rig?: boolean;
  created_at: string;
}

export interface RigStatus {
  rig_id: string;
  status: string;
  progress: { step: string; pct: number };
  rigged_glb_url: string | null;
  error_message?: string;
  detection_method?: DetectionMethod;
}

export interface Animation {
  id: string;
  name: string;
  slug: string;
  category: { name: string; slug: string; icon: string };
  gltf_file: string;
  preview_gif: string | null;
  duration_frames: number;
  frame_rate: number;
  is_looping: boolean;
  tags: string[];
  like_count: number;
  download_count: number;
}

export interface ModelRotation {
  x: number;
  y: number;
  z: number;
}

export interface ModelRotationQuaternion {
  x: number;
  y: number;
  z: number;
  w: number;
}

export const LANDMARK_KEYS = [
  "chin", "groin",
  "left_shoulder", "right_shoulder",
  "left_elbow", "right_elbow",
  "left_wrist", "right_wrist",
  "left_hip", "right_hip",
  "left_knee", "right_knee",
  "left_ankle", "right_ankle",
  "left_heel", "right_heel",
] as const;

export type LandmarkKey = typeof LANDMARK_KEYS[number];

export type LandmarkPoint = [number, number, number]; // three.js editor space

export type LandmarkSet = Record<LandmarkKey, LandmarkPoint>;

// ── API calls ─────────────────────────────────────────────────────────────────

export const uploadModel = (
  file: File,
  name: string,
  rotation: ModelRotation = { x: 0, y: 0, z: 0 },
  rotationQuaternion?: ModelRotationQuaternion,
) => {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  form.append("rotation_x", String(rotation.x));
  form.append("rotation_y", String(rotation.y));
  form.append("rotation_z", String(rotation.z));
  if (rotationQuaternion) {
    form.append("rotation_qx", String(rotationQuaternion.x));
    form.append("rotation_qy", String(rotationQuaternion.y));
    form.append("rotation_qz", String(rotationQuaternion.z));
    form.append("rotation_qw", String(rotationQuaternion.w));
  }
  return api.post<RiggedModel>("/rigs/", form);
};

export const getRigStatus = (id: string) =>
  api.get<RigStatus>(`/rigs/${id}/status/`);

export const getLandmarks = (id: string) =>
  api.get<{ landmarks: LandmarkSet }>(`/rigs/${id}/landmarks/`);

export const listRigs = () => api.get<RiggedModel[]>("/rigs/");

export const listAnimations = (params?: {
  search?: string;
  category__slug?: string;
  is_looping?: boolean;
}) => api.get<Animation[]>("/animations/", { params });

export const retargetAnimation = (animId: string, rigId: string) =>
  api.post<{ task_id: string; status: string }>(
    `/animations/${animId}/retarget/`,
    { rig_id: rigId },
  );

export const uploadAnimation = (
  file: File,
  name: string,
  categorySlug: string,
) => {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  form.append("category_slug", categorySlug);
  return api.post<Animation>("/animations/", form);
};

export const exportProject = (projectId: string, format: "glb" | "fbx") =>
  api.post<{ download_url: string }>(`/projects/${projectId}/export/`, {
    format,
  });

// ── Error helpers ─────────────────────────────────────────────────────────────

// DRF returns either { detail: "..." } (auth/throttle) or { field: ["..."] }
// (serializer validation). This widens to whatever shape the server sent.
export type ApiErrorPayload =
  | { detail?: string; error?: string }
  | Record<string, string | string[]>;

export type ApiError = AxiosError<ApiErrorPayload>;

/**
 * Extract a human-readable message from an axios/unknown error.
 * Optional `prefixFieldKey: false` skips the "fieldname: " prefix on
 * field-validation errors (used by login where field names leak).
 */
export function extractApiError(
  err: unknown,
  fallback: string,
  options: { prefixFieldKey?: boolean } = {},
): string {
  const { prefixFieldKey = true } = options;
  if (!isAxiosError<ApiErrorPayload>(err)) {
    return err instanceof Error ? err.message : fallback;
  }
  const data = err.response?.data;
  if (!data) return err.message || fallback;
  if (typeof data === "string") return data;

  const detail = (data as { detail?: string }).detail;
  if (detail) return detail;
  const errorField = (data as { error?: string }).error;
  if (errorField) return errorField;

  const firstKey = Object.keys(data)[0];
  if (!firstKey) return fallback;
  const val = (data as Record<string, string | string[]>)[firstKey];
  const text = Array.isArray(val) ? val[0] : String(val);
  if (!prefixFieldKey || firstKey === "non_field_errors") return text;
  return `${firstKey}: ${text}`;
}

export default api;
