import axios, { AxiosError, type AxiosRequestConfig } from "axios";

import { clearToken, getToken } from "../composables/useAuth";

export interface ApiResponse<T>{ code:number; message:string; data:T|null; error_code:string|null }
export interface ApiError{ status:number; message:string; detail?:unknown }
export interface TokenData{ access_token:string; token_type:string; username:string }

const http = axios.create({
  baseURL: "/api/v1",
});

http.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response.data.data,
  (error: AxiosError) => {
    if (error.response?.status === 401 && error.config?.url !== "/auth/login") {
      clearToken();
      void import("../router").then(({ router }) => router.push("/login"));
    }
    throw normalizeError(error);
  },
);

export function getDefaultHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function login(username: string, password: string): Promise<TokenData> {
  return apiPost<TokenData>("/auth/login", { username, password });
}

export function apiGet<T>(url:string, params?:Record<string,unknown>):Promise<T> {
  return http.get<T, T>(url, { params });
}

export function apiPost<T>(url:string, body?:unknown):Promise<T> {
  return http.post<T, T>(url, body);
}

export function apiUpload<T>(url:string, form:FormData):Promise<T> {
  return http.post<T, T>(url, form);
}

function normalizeError(error: AxiosError): ApiError {
  const status = error.response?.status ?? 0;
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  return {
    status,
    message: detailMessage(detail) ?? fallbackMessage(status),
    detail,
  };
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const first = detail.find((item) => item && typeof item === "object") as { msg?: unknown } | undefined;
    if (typeof first?.msg === "string") {
      return first.msg;
    }
  }
  return null;
}

function fallbackMessage(status: number): string {
  if (status >= 500) {
    return "服务暂时不可用";
  }
  if (status >= 400) {
    return "请求未通过校验";
  }
  return "网络请求失败";
}

export type RequestConfig = AxiosRequestConfig;
