import { recoveryContextParts } from "./recoveryContext.ts";

export type RecoveryRecord = {
  key: string;
  fingerprint: string;
  created: number;
};
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function recoveryScope(org: string, user: string, environment: string) {
  return (
    "nexus.inference.recovery.v2:" +
    recoveryContextParts(org, user, environment).join(":")
  );
}

// Runtime requests were staging-only before v2. Never adopt an unscoped v1
// receipt into another environment, including document-update resource suffixes.
export function legacyRecoveryScope(scope: string): string | null {
  const match =
    /^(nexus\.(?:inference\.recovery|live\.(?:run|document|document-update|retrieval-check|intake|hybrid-search)))\.v2:([^:]+):([^:]+):staging(:.*)?$/.exec(
      scope,
    );
  return match
    ? `${match[1]}.v1:${match[2]}:${match[3]}${match[4] || ""}`
    : null;
}

function storedRecovery(storage: Store, scope: string): RecoveryRecord | null {
  const raw = storage.getItem(scope);
  try {
    const record = JSON.parse(raw || "null");
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

export function readRecovery(
  storage: Store,
  scope: string,
  strict = false,
): RecoveryRecord | null {
  try {
    const record = storedRecovery(storage, scope);
    const legacy = legacyRecoveryScope(scope);
    return record || (legacy ? storedRecovery(storage, legacy) : null);
  } catch {
    if (strict)
      throw new Error(
        "Saved request state could not be read. Refresh or recover the original outcome before submitting again.",
      );
    return null;
  }
}
export function writeRecovery(
  storage: Store,
  scope: string,
  record: RecoveryRecord,
) {
  const existing = storedRecovery(storage, scope);
  if (
    existing &&
    (existing.key !== record.key || existing.fingerprint !== record.fingerprint)
  )
    throw new Error(
      "Another request is still saved in this context. Recover its original outcome before replacing it.",
    );
  storage.setItem(
    scope,
    JSON.stringify({
      key: record.key,
      fingerprint: record.fingerprint,
      created: record.created,
    }),
  );
}
export function clearRecovery(
  storage: Store,
  scope: string,
  expected: Pick<RecoveryRecord, "key" | "fingerprint">,
) {
  const legacy = legacyRecoveryScope(scope);
  const keys = legacy ? [scope, legacy] : [scope];
  for (const key of keys) {
    const saved = storedRecovery(storage, key);
    // Only retire the receipt that was actually acknowledged. A late response
    // must not remove a different request saved under either namespace.
    if (
      saved &&
      saved.key === expected.key &&
      saved.fingerprint === expected.fingerprint
    )
      storage.removeItem(key);
  }
}

export function acknowledgeRecovery(
  storage: Store,
  scope: string,
  record: RecoveryRecord,
  response: unknown,
) {
  const value = response as { id?: unknown; status?: unknown } | null;
  if (
    typeof value?.id !== "string" ||
    !value.id ||
    typeof value.status !== "string" ||
    !value.status
  )
    throw new Error(
      "The response was incomplete. Recover the original request before submitting again.",
    );
  clearRecovery(storage, scope, record);
}

export function prepareRecovery(
  storage: Store,
  scope: string,
  fingerprint: string,
  fallback: RecoveryRecord | null = null,
  makeKey = () => crypto.randomUUID() as string,
): RecoveryRecord {
  const pending = readRecovery(storage, scope, true) || fallback;
  if (pending && pending.fingerprint !== fingerprint)
    throw new Error(
      "A previous submission is still unacknowledged. Recover it or retry the unchanged request before starting a different intent.",
    );
  const record = pending || {
    key: makeKey(),
    fingerprint,
    created: Date.now(),
  };
  writeRecovery(storage, scope, record);
  return record;
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
