import axios, { AxiosInstance } from "axios";

// All Django API calls go through this single axios instance
const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
  // We use Authorization headers with tokens from localStorage, so we do NOT
  // need browser credentials/cookies on cross-origin requests. Disabling
  // credentials avoids strict CORS rules with wildcard origins.
  withCredentials: false,
});

// Attach JWT token to every request automatically
api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access") : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// If we get 401 (token expired), automatically try to refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh =
        typeof window !== "undefined" ? localStorage.getItem("refresh") : null;
      if (refresh) {
        try {
          const { data } = await axios.post(
            `${process.env.NEXT_PUBLIC_API_URL}/auth/token/refresh/`,
            { refresh },
          );
          localStorage.setItem("access", data.access);
          error.config.headers.Authorization = `Bearer ${data.access}`;
          return api.request(error.config);
        } catch {
          // Refresh failed — log user out
          localStorage.removeItem("access");
          localStorage.removeItem("refresh");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  },
);

// ── Typed API functions ───────────────────────────────────────────────────────

export interface RiggedModel {
  id: string;
  name: string;
  status: "pending" | "processing" | "done" | "failed";
  original_format: string;
  rigged_glb_url: string | null;
  bone_mapping: Record<string, string>;
  file_size_mb: number;
  created_at: string;
}

export interface RigStatus {
  rig_id: string;
  status: string;
  progress: { step: string; pct: number };
  rigged_glb_url: string | null;
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

// Upload a 3D model file → returns immediately with status "pending"
export const uploadModel = (file: File, name: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  return api.post<RiggedModel>("/rigs/", form);
};

// Poll rig processing status
export const getRigStatus = (id: string) =>
  api.get<RigStatus>(`/rigs/${id}/status/`);

// List user's rigged models
export const listRigs = () => api.get<RiggedModel[]>("/rigs/");

// Browse animation library
export const listAnimations = (params?: {
  search?: string;
  category__slug?: string;
  is_looping?: boolean;
  page?: number;
}) =>
  api.get<{ results: Animation[]; count: number }>("/animations/", { params });

// Apply animation to a rigged model (triggers Celery retarget task)
export const retargetAnimation = (animId: string, rigId: string) =>
  api.post<{ task_id: string; status: string }>(
    `/animations/${animId}/retarget/`,
    { rig_id: rigId },
  );

// Upload a custom animation file
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

// Trigger export (FBX or GLB download)
export const exportProject = (projectId: string, format: "glb" | "fbx") =>
  api.post<{ download_url: string }>(`/projects/${projectId}/export/`, {
    format,
  });

export default api;
