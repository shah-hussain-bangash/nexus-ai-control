import {
  clearRecovery,
  acknowledgeRecovery,
  requestFingerprint,
  prepareRecovery,
} from "./inferenceRecovery.ts";
import { recoveryContextParts } from "./recoveryContext.ts";
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function liveIntentScope(
  kind:
    | "run"
    | "document"
    | "document-update"
    | "retrieval-check"
    | "intake"
    | "hybrid-search"
    | "member"
    | "asset-copy",
  org: string,
  user: string,
  environment: string,
) {
  const parts = recoveryContextParts(org, user, environment);
  // Provisioning is a workspace-wide operation, rather than a runtime action.
  return kind === "member"
    ? "nexus.live.member.v1:" + parts.slice(0, 2).join(":")
    : "nexus.live." + kind + ".v2:" + parts.join(":");
}
export async function sendLiveIntent<T extends { id: string; status: string }>(
  storage: Store,
  scope: string,
  body: unknown,
  send: (key: string) => Promise<T>,
  makeKey = () => crypto.randomUUID() as string,
) {
  const fingerprint = await requestFingerprint(body);
  const record = prepareRecovery(storage, scope, fingerprint, null, makeKey);
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
      clearRecovery(storage, scope, record);
    throw e;
  }
  acknowledgeRecovery(storage, scope, record, result);
  return result;
}
