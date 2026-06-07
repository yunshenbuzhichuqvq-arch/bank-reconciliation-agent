import axios, { AxiosError, type AxiosRequestConfig } from "axios";

export interface ApiResponse<T>{ code:number; message:string; data:T|null; error_code:string|null }
export interface ApiError{ status:number; message:string; detail?:unknown }

const DEFAULT_HEADERS = { "X-User-ID": "demo_user" };

const http = axios.create({
  baseURL: "/api/v1",
  headers: DEFAULT_HEADERS,
});

http.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  config.headers["X-User-ID"] = DEFAULT_HEADERS["X-User-ID"];
  return config;
});

http.interceptors.response.use(
  (response) => response.data.data,
  (error: AxiosError) => {
    throw normalizeError(error);
  },
);

export function getDefaultHeaders(): Record<string, string> {
  return { ...DEFAULT_HEADERS };
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
