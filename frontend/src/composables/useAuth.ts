const TOKEN_STORAGE_KEY = "auth_token";

function storage(): Storage | null {
  return typeof window === "undefined" ? null : (window.localStorage ?? null);
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_STORAGE_KEY) ?? null;
}

export function setToken(token: string): void {
  storage()?.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  storage()?.removeItem(TOKEN_STORAGE_KEY);
}

export function currentUsername(): string | null {
  const token = getToken();
  if (!token) {
    return null;
  }

  try {
    const payload = token.split(".")[1];
    if (!payload) {
      return null;
    }
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const sub = (JSON.parse(window.atob(padded)) as { sub?: unknown }).sub;
    return typeof sub === "string" ? sub : null;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}
