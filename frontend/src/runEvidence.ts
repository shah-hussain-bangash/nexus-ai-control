import type { SessionContext } from "./sessionContext";
import { canonicalEvidence } from "./supplierEvidence.ts";

export type RunEvidenceReport = {
  payload: {
    format: string;
    format_version: number;
    boundary: string;
    exported_at_utc: string;
    schema_version: number;
    scope: { workspace_id: string; account_id: string; environment: string };
    run: {
      id: string;
      status: string;
      version: number;
      scheduled_start_at_utc?: string;
    };
    connector: { mode: string };
    steps: {
      position: number;
      kind: string;
      status: string;
      action: null | { status: string; verified: boolean };
      condition?: {
        kind: string;
        source_step: number;
        matched: boolean;
        next_step: number;
      };
    }[];
  };
  integrity: {
    algorithm: string;
    canonicalization: string;
    digest: string;
    authenticated_signature: boolean;
  };
};

export async function verifyRunEvidence(
  value: RunEvidenceReport,
  context: SessionContext | null,
  id: string,
) {
  const p = value?.payload,
    i = value?.integrity;
  if (
    !context ||
    p?.format !== "nexus-durable-run-evidence" ||
    p.format_version !== 1 ||
    p.scope?.workspace_id !== context.workspace_id ||
    p.scope?.account_id !== context.user_id ||
    p.scope?.environment !== context.environment ||
    p.run?.id !== id ||
    !Number.isSafeInteger(p.run.version) ||
    p.run.version < 1 ||
    !Number.isSafeInteger(p.schema_version) ||
    p.schema_version < 1 ||
    !["synthetic", "http"].includes(p.connector?.mode) ||
    !Array.isArray(p.steps) ||
    p.steps.length < 2 ||
    p.steps.length > 12 ||
    !p.steps.every(
      (step, index) =>
        step.position === index &&
        [
          "checkpoint",
          "approval",
          "governed_action",
          "condition",
          "output",
        ].includes(step.kind) &&
        !(
          step.kind === "condition" &&
          step.status === "completed" &&
          !step.condition
        ) &&
        (step.condition === undefined ||
          (step.kind === "condition" &&
            step.condition.kind === "supplier_allowlist" &&
            typeof step.condition.matched === "boolean" &&
            Number.isSafeInteger(step.condition.source_step) &&
            step.condition.source_step >= 0 &&
            step.condition.source_step < index &&
            step.condition.next_step ===
              (step.condition.matched ? index + 1 : p.steps.length - 1))) &&
        (step.action === null ||
          (step.kind === "governed_action" &&
            typeof step.action.verified === "boolean" &&
            step.action.verified === (step.action.status === "verified"))),
    ) ||
    i?.algorithm !== "sha256" ||
    i.canonicalization !== "sorted-ascii-json-v1" ||
    i.authenticated_signature !== false ||
    !/^[a-f0-9]{64}$/.test(i.digest)
  )
    throw new Error(
      "Run evidence does not match this account, environment or format.",
    );
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalEvidence(p)),
  );
  const actual = Array.from(new Uint8Array(hash), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
  if (actual !== i.digest)
    throw new Error("Run evidence checksum failed. Refresh the report.");
  return value;
}
