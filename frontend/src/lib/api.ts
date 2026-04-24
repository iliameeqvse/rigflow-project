import axios, { AxiosInstance } from "axios";

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
  error_message?: string;
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

// ── API calls ─────────────────────────────────────────────────────────────────

export const uploadModel = (file: File, name: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  return api.post<RiggedModel>("/rigs/", form);
};

export const getRigStatus = (id: string) =>
  api.get<RigStatus>(`/rigs/${id}/status/`);

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

export default api;