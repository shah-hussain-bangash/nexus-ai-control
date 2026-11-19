import { sessionContext } from "./sessionContext.ts";
export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string;
  constructor(
    message: string,
    status: number,
    code: string,
    requestId: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}
export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  const snapshot = sessionContext.capture();
  const contextual =
    (path.startsWith("/v1/") || path.split("?")[0] === "/auth/logout") &&
    path.split("?")[0] !== "/v1/me";
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(contextual ? sessionContext.headers(snapshot) : {}),
      ...(method !== "GET" && csrf ? { "X-CSRF-Token": csrf } : {}),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!sessionContext.current(snapshot))
    throw new ApiError(
      "This response belongs to an earlier workspace context.",
      409,
      "STALE_CONTEXT_RESPONSE",
      "",
    );
  if (
    !response.ok &&
    [
      "AUTH_REQUIRED",
      "SESSION_CONTEXT_UNAVAILABLE",
      "STALE_SESSION_CONTEXT",
      "ENVIRONMENT_ACCESS_DENIED",
      "ENVIRONMENT_CONTEXT_CHANGED",
      "CSRF_FAILED",
    ].includes(data.error?.code)
  ) {
    csrf = "";
    sessionContext.clear();
  }
  if (!response.ok)
    throw new ApiError(
      data.error?.message ||
        (Array.isArray(data.detail)
          ? "Check the form fields and try again."
          : "The request could not be completed."),
      response.status,
      data.error?.code || "REQUEST_FAILED",
      response.headers.get("X-Request-ID") || "",
    );
  return data;
}
