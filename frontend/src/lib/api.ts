import axios, { AxiosInstance } from "axios";
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
  setAuthTokens,
} from "@/lib/auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: false,
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !String(originalRequest.url ?? "").includes("/auth/token/refresh/")
    ) {
      originalRequest._retry = true;
      const refresh = getRefreshToken();

      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
            refresh,
          });
          setAuthTokens(data.access, refresh);
          originalRequest.headers.Authorization = `Bearer ${data.access}`;
          return api.request(originalRequest);
        } catch {
          clearAuthTokens();
          window.location.href = "/login";
        }
      }
    }

    return Promise.reject(error);
  },
);

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

export const uploadModel = (file: File, name: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  return api.post<RiggedModel>("/rigs/", form);
};

export const getRigStatus = (id: string) => api.get<RigStatus>(`/rigs/${id}/status/`);

export const listRigs = () => api.get<RiggedModel[]>("/rigs/");

export const listAnimations = (params?: {
  search?: string;
  category__slug?: string;
  is_looping?: boolean;
  page?: number;
}) => api.get<{ results: Animation[]; count: number }>("/animations/", { params });

export const retargetAnimation = (animId: string, rigId: string) =>
  api.post<{ task_id: string; status: string }>(`/animations/${animId}/retarget/`, {
    rig_id: rigId,
  });

export const uploadAnimation = (file: File, name: string, categorySlug: string) => {
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