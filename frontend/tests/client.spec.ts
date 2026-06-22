import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost, getDefaultHeaders } from "../src/api/client";

const routerPush = vi.hoisted(() => vi.fn());
const localStorage = createStorage();

Object.defineProperty(window, "localStorage", { configurable: true, value: localStorage });

vi.mock("../src/router", () => ({ router: { push: routerPush } }));

function createStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

const handlers = vi.hoisted((): {
  request?: (config: Record<string, unknown>) => Record<string, unknown>;
  response?: (response: Record<string, unknown>) => unknown;
  responseError?: (error: unknown) => unknown;
  responseStatus: number;
} => ({ responseStatus: 400 }));

vi.mock("axios", () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: {
          use: vi.fn((handler) => {
            handlers.request = handler;
          }),
        },
        response: {
          use: vi.fn((handler, errorHandler) => {
            handlers.response = handler;
            handlers.responseError = errorHandler;
          }),
        },
      },
      get: vi.fn(async (url: string, config?: Record<string, unknown>) => {
        const requestConfig = handlers.request?.({ url, ...(config ?? {}) });
        return handlers.response?.({
          data: { code: 200, message: "success", data: { ok: true, requestConfig }, error_code: null },
        });
      }),
      post: vi.fn(async () => {
        throw await handlers.responseError?.({
          response: { status: handlers.responseStatus, data: { detail: "bad request detail" } },
          config: { url: "/protected" },
        });
      }),
    })),
  },
}));

describe("api client", () => {
  afterEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    handlers.responseStatus = 400;
  });

  it("unwraps ApiResponse data", async () => {
    await expect(apiGet<{ ok: boolean }>("/health")).resolves.toMatchObject({ ok: true });
  });

  it("normalizes 4xx responses into ApiError", async () => {
    await expect(apiPost("/fail", {})).rejects.toMatchObject({
      status: 400,
      message: "bad request detail",
      detail: "bad request detail",
    });
  });

  it("sends the stored token as a Bearer header", async () => {
    window.localStorage.setItem("auth_token", "signed-token");
    const response = await apiGet<{ requestConfig: { headers: Record<string, string> } }>("/tasks");

    expect(response.requestConfig.headers.Authorization).toBe("Bearer signed-token");
    expect(getDefaultHeaders().Authorization).toBe("Bearer signed-token");
  });

  it("clears authentication and redirects after a non-login 401", async () => {
    window.localStorage.setItem("auth_token", "expired-token");
    handlers.responseStatus = 401;

    await expect(apiPost("/protected", {})).rejects.toMatchObject({ status: 401 });

    expect(window.localStorage.getItem("auth_token")).toBeNull();
    await vi.waitFor(() => expect(routerPush).toHaveBeenCalledWith("/login"));
  });
});
