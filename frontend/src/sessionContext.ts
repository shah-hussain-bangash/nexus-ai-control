export type SessionContext = Readonly<{
  workspace_id: string;
  user_id: string;
  environment: string;
  revision: number;
  binding_id: string;
}>;
export type ContextSnapshot = { epoch: number; context: SessionContext | null };
export class ContextStore {
  private epoch = 0;
  private context: SessionContext | null = null;
  private listeners = new Set<(epoch: number) => void>();
  capture(): ContextSnapshot {
    return { epoch: this.epoch, context: this.context };
  }
  current(snapshot: ContextSnapshot) {
    return snapshot.epoch === this.epoch;
  }
  subscribe(listener: (epoch: number) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
  adopt(value: any) {
    const c = value?.runtime_context;
    if (
      !c ||
      ![c.workspace_id, c.user_id].every(
        (v) =>
          typeof v === "string" &&
          v.length > 0 &&
          v.length <= 100 &&
          !/[\u0000-\u001f\u007f]/.test(v),
      ) ||
      c.workspace_id !== value?.user?.org_id ||
      c.user_id !== value?.user?.id ||
      c.environment !== value?.environment ||
      typeof c.environment !== "string" ||
      !/^[a-z][a-z0-9-]{1,31}$/.test(c.environment) ||
      !Number.isSafeInteger(c.revision) ||
      c.revision < 1 ||
      typeof c.binding_id !== "string" ||
      !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(c.binding_id)
    )
      throw new Error(
        "Your workspace context is unavailable. Refresh and sign in again.",
      );
    const next: SessionContext = Object.freeze({
      workspace_id: c.workspace_id,
      user_id: c.user_id,
      environment: c.environment,
      revision: c.revision,
      binding_id: c.binding_id,
    });
    if (JSON.stringify(next) === JSON.stringify(this.context)) return;
    this.context = next;
    this.changed();
  }
  clear() {
    if (this.context) {
      this.context = null;
      this.changed();
    }
  }
  private changed() {
    this.epoch++;
    for (const listener of this.listeners) listener(this.epoch);
  }
  headers(snapshot: ContextSnapshot): Record<string, string> {
    const c = snapshot.context;
    return c
      ? {
          "X-Nexus-Environment": c.environment,
          "X-Nexus-Context-ID": c.binding_id,
          "X-Nexus-Context-Revision": String(c.revision),
        }
      : {};
  }
}
export const sessionContext = new ContextStore();
