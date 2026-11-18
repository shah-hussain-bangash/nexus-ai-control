export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public requestId: string,
  ) {
    super(message);
    this.name = "ApiError";
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
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET" && csrf ? { "X-CSRF-Token": csrf } : {}),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
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
