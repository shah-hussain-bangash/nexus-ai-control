import { environmentReason } from "./environmentSetup.ts";
export type SupplierRoute = {
  grant_id: string;
  agent_id: string;
  agent_name: string;
  agent_generation: number;
  tool_id: string;
  tool_name: string;
  tool_version: string;
};
export type ConnectorProfile = {
  mode: string;
  destination: string;
  configured_host: string;
  contract: string;
};
export type SupplierCheck = {
  id: string;
  status: string;
  reason: string;
  supplier_id: string;
  connector_mode: string;
  verified: boolean;
  external_ref: string | null;
  trace_id: string;
  updated: number;
};
export function supplierCheckPayload(
  profile: ConnectorProfile,
  route: SupplierRoute,
  supplier: string,
  note: string,
  reviewed: boolean,
) {
  supplier = supplier.trim();
  if (
    !reviewed ||
    !["synthetic", "http"].includes(profile.mode) ||
    !(profile.mode === "synthetic"
      ? profile.destination === "mock-business-v1"
      : /^http-business-v1:[a-f0-9]{64}$/.test(profile.destination)) ||
    !route.agent_id ||
    !route.tool_id ||
    !route.grant_id ||
    route.tool_version !== "1.0" ||
    !Number.isSafeInteger(route.agent_generation) ||
    route.agent_generation < 1
  )
    throw Error(
      "Refresh and review the configured connector and granted supplier route.",
    );
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(supplier))
    throw Error(
      "Enter a supplier reference of 1–64 letters, numbers, dots, underscores, colons or hyphens.",
    );
  return {
    agent_id: route.agent_id,
    tool_id: route.tool_id,
    expected_grant_id: route.grant_id,
    expected_agent_generation: route.agent_generation,
    expected_tool_version: route.tool_version,
    expected_destination: profile.destination,
    supplier_id: supplier,
    note: environmentReason(note),
    reviewed: true,
  };
}
export function supplierCheckOutcome(value: any) {
  if (
    !value ||
    !/^[a-f0-9]{64}$/.test(value.id) ||
    !["submitted", "cancelled"].includes(value.status) ||
    (value.status === "submitted" &&
      (typeof value.check?.id !== "string" ||
        !value.check.id ||
        typeof value.check.status !== "string" ||
        !["synthetic", "http"].includes(value.check.connector_mode) ||
        !value.check.supplier_id))
  )
    throw Error(
      "The check receipt could not be confirmed. Recover or cancel the pending intent before starting again.",
    );
  return value as { id: string; status: string; check?: SupplierCheck };
}
export function supplierCheckLabel(check: SupplierCheck) {
  if (check.status === "verified" && check.verified)
    return check.connector_mode === "synthetic"
      ? "Verified synthetic lookup"
      : "Verified supplier lookup";
  return (
    (
      {
        queued: "Waiting for worker",
        executing: "Checking supplier",
        awaiting_approval: "Needs independent approval",
        outcome_unknown: "Outcome uncertain — reconcile in the ledger",
        denied: "Denied by policy",
        blocked: "Blocked before dispatch",
        failed: "Check failed",
        rejected: "Approval rejected",
        changes_requested: "Review changes requested",
        expired: "Approval expired",
        cancelled: "Cancelled",
      } as Record<string, string>
    )[check.status] || "Needs investigation in the ledger"
  );
}
