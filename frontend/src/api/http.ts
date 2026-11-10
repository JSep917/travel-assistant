import axios from "axios";

export const http = axios.create({
  baseURL: "/api",
  timeout: 180000,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    console.error(
      "API error:",
      error.config?.method,
      error.config?.url,
      error.response?.status,
      error.response?.data,
    );

    const detail = error.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => item?.msg)
        .filter(Boolean)
        .join("；");
    }

    if (error.code === "ECONNABORTED") {
      return "请求超时，请稍后重试";
    }

    const method = error.config?.method?.toUpperCase() ?? "";
    const url = error.config?.url ?? "";
    const status = error.response?.status;

    return [
      method,
      url,
      status ? `HTTP ${status}` : "",
    ]
      .filter(Boolean)
      .join(" ");
  }

  return "请求失败，请稍后重试";
}
