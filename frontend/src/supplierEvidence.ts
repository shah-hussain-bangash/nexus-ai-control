import type { SessionContext } from "./sessionContext";

// This format permits integer numbers only and matches Python's ensure_ascii JSON.
export function canonicalEvidence(value: unknown): string {
  if (value === null || typeof value === "boolean")
    return JSON.stringify(value);
  if (typeof value === "string")
    return JSON.stringify(value).replace(
      /[^\x00-\x7f]/g,
      (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
    );
  if (typeof value === "number" && Number.isSafeInteger(value))
    return String(value);
  if (Array.isArray(value))
    return "[" + value.map(canonicalEvidence).join(",") + "]";
  if (typeof value === "object" && value) {
    const entries = Object.entries(value).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    );
    if (entries.some(([key]) => /[^\x00-\x7f]/.test(key)))
      throw new Error("Unsupported evidence key.");
    return (
      "{" +
      entries
        .map(
          ([key, item]) => JSON.stringify(key) + ":" + canonicalEvidence(item),
        )
        .join(",") +
      "}"
    );
  }
  throw new Error("Unsupported evidence value.");
}
export type EvidenceReport = {
  payload: {
    format: string;
    format_version: number;
    exported_at_utc: string;
    boundary: string;
    scope: { workspace_id: string; account_id: string; environment: string };
    check: {
      id: string;
      status: string;
      supplier_id: string;
      verified: boolean;
    };
    connector: { mode: string };
    operation: { action: string; resource: string };
    audit_events: unknown[];
  };
  integrity: {
    algorithm: string;
    canonicalization: string;
    digest: string;
    authenticated_signature: boolean;
  };
};
export async function verifyEvidence(
  value: EvidenceReport,
  context: SessionContext | null,
  id: string,
) {
  const p = value?.payload,
    i = value?.integrity;
  if (
    !context ||
    p?.format !== "nexus-supplier-check-evidence" ||
    p.format_version !== 1 ||
    p.scope?.workspace_id !== context.workspace_id ||
    p.scope?.account_id !== context.user_id ||
    p.scope?.environment !== context.environment ||
    p.check?.id !== id ||
    p.operation?.action !== "supplier:read" ||
    p.operation?.resource !== "suppliers" ||
    !["synthetic", "http"].includes(p.connector?.mode) ||
    !Array.isArray(p.audit_events) ||
    i?.algorithm !== "sha256" ||
    i.canonicalization !== "sorted-ascii-json-v1" ||
    i.authenticated_signature !== false ||
    !/^[a-f0-9]{64}$/.test(i.digest)
  )
    throw new Error(
      "Evidence does not match this account, environment or report format.",
    );
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalEvidence(p)),
  );
  const actual = Array.from(new Uint8Array(hash), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
  if (actual !== i.digest)
    throw new Error("Evidence checksum failed. Refresh the report.");
  return value;
}
