const API_BASE = import.meta.env.VITE_API_URL || "/api";
const TOKEN_KEY = "inventory_auth_token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function extractErrorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (Array.isArray(record.detail)) {
    const first = record.detail[0] as Record<string, unknown> | undefined;
    if (first && typeof first.msg === "string") {
      return first.msg.replace(/^Value error,\s*/i, "");
    }
  }
  if (typeof record.message === "string") return record.message;
  return fallback;
}

let onUnauthorizedCallback: (() => void) | null = null;

export function registerUnauthorizedHandler(cb: () => void): void {
  onUnauthorizedCallback = cb;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      // ignora resposta não JSON
    }
    const message = extractErrorMessage(
      parsed,
      `Erro na requisição (${response.status}).`
    );
    if (response.status === 401 && path !== "/auth/login") {
      setStoredToken(null);
      if (onUnauthorizedCallback) onUnauthorizedCallback();
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function downloadAuthenticatedFile(
  path: string,
  fallbackFilename: string
): Promise<void> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      // ignora
    }
    throw new ApiError(
      response.status,
      extractErrorMessage(parsed, "Não foi possível exportar o arquivo.")
    );
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || fallbackFilename;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function buildQueryString(
  params: Record<string, string | number | boolean | null | undefined>
): string {
  const usp = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val === undefined || val === null || val === "") continue;
    usp.set(key, String(val));
  }
  const str = usp.toString();
  return str ? `?${str}` : "";
}
