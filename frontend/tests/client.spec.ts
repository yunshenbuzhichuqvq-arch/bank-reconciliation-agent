import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost, getDefaultHeaders } from "../src/api/client";

const handlers = vi.hoisted((): {
  request?: (config: Record<string, unknown>) => Record<string, unknown>;
  response?: (response: Record<string, unknown>) => unknown;
  responseError?: (error: unknown) => unknown;
} => ({}));

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
          response: { status: 400, data: { detail: "bad request detail" } },
        });
      }),
    })),
  },
}));

describe("api client", () => {
  afterEach(() => {
    vi.clearAllMocks();
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

  it("sends X-User-ID demo header", async () => {
    const response = await apiGet<{ requestConfig: { headers: Record<string, string> } }>("/tasks");

    expect(response.requestConfig.headers["X-User-ID"]).toBe("demo_user");
    expect(getDefaultHeaders()["X-User-ID"]).toBe("demo_user");
  });
});
