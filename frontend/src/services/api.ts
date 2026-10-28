export type ApiErrorKind = "http" | "validation" | "network" | "timeout" | "offline" | "parse";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly fields: string[];
  constructor(message: string, kind: ApiErrorKind, status?: number, fields: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.fields = fields;
  }
}
type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown; timeoutMs?: number };

export function buildQuery(params: object = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}
function validationMessages(detail: unknown): { message: string; fields: string[] } {
  if (typeof detail === "string") return { message: detail, fields: [] };
  if (Array.isArray(detail)) {
    const fields = detail.map((item) => {
      if (!item || typeof item !== "object") return "Invalid input";
      const entry = item as { loc?: unknown[]; msg?: unknown };
      const loc = Array.isArray(entry.loc) ? entry.loc.filter((part) => part !== "body").join(".") : "";
      return `${loc ? `${loc}: ` : ""}${typeof entry.msg === "string" ? entry.msg : "Invalid input"}`;
    });
    return { message: fields.join("; ") || "The request is invalid.", fields };
  }
  return { message: "The server returned an unexpected error.", fields: [] };
}
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, timeoutMs = 12000, headers, signal: externalSignal, ...rest } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const abortExternal = () => controller.abort();
  externalSignal?.addEventListener("abort", abortExternal, { once: true });
  try {
    let response: Response;
    try {
      response = await fetch(path, {
        ...rest,
        headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (timedOut) throw new ApiError("The request timed out. Try again.", "timeout");
      if (!navigator.onLine) throw new ApiError("You appear to be offline. Check your connection.", "offline");
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError("Cannot reach the GreenScale API. Check that the backend is running.", "network");
    }
    const raw = await response.text();
    let payload: unknown = undefined;
    if (raw) {
      try { payload = JSON.parse(raw) as unknown; }
      catch { throw new ApiError("The server returned an unreadable response.", "parse", response.status); }
    }
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : undefined;
      const parsed = validationMessages(detail);
      throw new ApiError(parsed.message || `Request failed (${response.status}).`, response.status === 422 ? "validation" : "http", response.status, parsed.fields);
    }
    return payload as T;
  } finally {
    window.clearTimeout(timer);
    externalSignal?.removeEventListener("abort", abortExternal);
  }
}