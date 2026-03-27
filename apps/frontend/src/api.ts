import { clearTokens, getAccessToken } from "./auth";

export function getApiBase(): string {
  return (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:3000";
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("http") ? path : `${getApiBase()}${path}`;
  const headers = new Headers(init?.headers || undefined);

  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, { ...init, headers });

  if (res.status === 401) {
    clearTokens();
  }

  return res;
}
