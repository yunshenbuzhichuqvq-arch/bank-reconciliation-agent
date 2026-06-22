import { beforeEach, describe, expect, it } from "vitest";

import { clearToken, currentUsername, getToken, setToken } from "../src/composables/useAuth";
import { router } from "../src/router";

const localStorage = createStorage();

Object.defineProperty(window, "localStorage", { configurable: true, value: localStorage });

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

function tokenFor(sub: string): string {
  const payload = btoa(JSON.stringify({ sub })).replace(/=/g, "");
  return `header.${payload}.signature`;
}

describe("authentication state", () => {
  beforeEach(async () => {
    window.localStorage.clear();
    clearToken();
    await router.push("/login");
  });

  it("persists the token and reads the current username", () => {
    setToken(tokenFor("demo_user"));

    expect(getToken()).toContain("header.");
    expect(currentUsername()).toBe("demo_user");

    clearToken();
    expect(getToken()).toBeNull();
  });

  it("redirects unauthenticated protected navigation to login", async () => {
    await router.push("/upload");

    expect(router.currentRoute.value.path).toBe("/login");
  });
});
