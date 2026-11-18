import {
  readRecovery,
  writeRecovery,
  clearRecovery,
  requestFingerprint,
} from "./inferenceRecovery.ts";
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function liveIntentScope(
  kind:
    | "run"
    | "document"
    | "document-update"
    | "retrieval-check"
    | "intake"
    | "hybrid-search"
    | "member",
  org: string,
  user: string,
) {
  return (
    "nexus.live." +
    kind +
    ".v1:" +
    encodeURIComponent(org) +
    ":" +
    encodeURIComponent(user)
  );
}
export async function sendLiveIntent<T extends { id: string; status: string }>(
  storage: Store,
  scope: string,
  body: unknown,
  send: (key: string) => Promise<T>,
  makeKey = () => crypto.randomUUID() as string,
) {
  const fingerprint = await requestFingerprint(body),
    pending = readRecovery(storage, scope);
  if (pending && pending.fingerprint !== fingerprint)
    throw Error(
      "A previous submission is still unacknowledged. Recover it or retry the unchanged request before starting a different intent.",
    );
  const record = pending || {
    key: makeKey(),
    fingerprint,
    created: Date.now(),
  };
  writeRecovery(storage, scope, record);
  let result: T;
  try {
    result = await send(record.key);
  } catch (e) {
    const status = Number((e as { status?: number }).status);
    if (
      (status >= 400 && status < 500 && status !== 409) ||
      (status === 409 &&
        [
          "STALE_VERSION",
          "SOURCE_CHANGED",
          "ACCOUNT_UNAVAILABLE",
          "OWNER_PROTECTED",
        ].includes((e as { code?: string }).code || ""))
    )
      clearRecovery(storage, scope);
    throw e;
  }
  if (!result?.id || !result.status)
    throw Error(
      "The response was incomplete. Recover or retry the unchanged intent.",
    );
  clearRecovery(storage, scope);
  return result;
}
