export type RecoveryRecord = {
  key: string;
  fingerprint: string;
  created: number;
};
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function recoveryScope(org: string, user: string) {
  return (
    "nexus.inference.recovery.v1:" +
    encodeURIComponent(org) +
    ":" +
    encodeURIComponent(user)
  );
}
export function readRecovery(
  storage: Store,
  scope: string,
): RecoveryRecord | null {
  try {
    const record = JSON.parse(storage.getItem(scope) || "null");
    if (
      !record ||
      typeof record.key !== "string" ||
      typeof record.fingerprint !== "string" ||
      !/^[A-Za-z0-9_-]{16,100}$/.test(record.key) ||
      !/^[a-f0-9]{64}$/.test(record.fingerprint) ||
      !Number.isFinite(record.created)
    )
      return null;
    return {
      key: record.key,
      fingerprint: record.fingerprint,
      created: record.created,
    };
  } catch {
    return null;
  }
}
export function writeRecovery(
  storage: Store,
  scope: string,
  record: RecoveryRecord,
) {
  storage.setItem(
    scope,
    JSON.stringify({
      key: record.key,
      fingerprint: record.fingerprint,
      created: record.created,
    }),
  );
}
export function clearRecovery(storage: Store, scope: string) {
  storage.removeItem(scope);
}
export async function requestFingerprint(value: unknown) {
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(value)),
  );
  return Array.from(new Uint8Array(hash), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}
