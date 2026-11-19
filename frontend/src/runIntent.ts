export type SubmittedAction = { id: string; status: string; decision?: string };

// Keep unacknowledged action keys across a context-driven view reset. A different
// actor/workspace/environment gets a distinct map; returning to the original
// scope must not accidentally turn an uncertain action into a new intent.
export class IntentKeyRegistry {
  private scopes = new Map<string, Map<string, string>>();
  forContext(scope: string) {
    let keys = this.scopes.get(scope);
    if (!keys) {
      keys = new Map();
      this.scopes.set(scope, keys);
    }
    return keys;
  }
}

// An unacknowledged retry must keep its key. A later, acknowledged new intent
// gets a new key even if its form values match a previous successful request.
export async function submitIntent<T extends SubmittedAction>(
  pendingKeys: Map<string, string>,
  fingerprint: string,
  send: (key: string) => Promise<T>,
  makeKey = () => crypto.randomUUID() as string,
): Promise<T> {
  let key = pendingKeys.get(fingerprint);
  if (!key) {
    key = makeKey();
    pendingKeys.set(fingerprint, key);
  }
  const result = await send(key);
  if (!result?.id || !result?.status)
    throw new Error(
      "The submission response was incomplete. Retry the unchanged request to recover its outcome.",
    );
  pendingKeys.delete(fingerprint);
  return result;
}

export function submissionMessage(action: SubmittedAction): string {
  const reference = "ACT-" + action.id.slice(0, 8).toUpperCase();
  if (action.status === "awaiting_approval")
    return `${reference}: Awaiting approval. Sign in as the independent reviewer and open Approvals before expiry.`;
  if (action.status === "denied")
    return `${reference}: Denied by policy. No execution was queued. Open Executions for the reason.`;
  if (action.status === "queued")
    return `${reference}: Queued for the worker. Open Executions to follow its outcome.`;
  if (action.status === "verified")
    return `${reference}: Verified. Open Executions for the evidence.`;
  return `${reference}: ${action.status.replaceAll("_", " ")}. Open Executions for details.`;
}
