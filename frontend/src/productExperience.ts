import type { FunctionDefinition } from "./functionPlans.ts";
import { validateOperation } from "./operationalModel.ts";
export const screenStates = [
  "ready",
  "empty",
  "loading",
  "permission_denied",
  "validation_error",
  "dependency_unavailable",
  "timeout_unknown",
  "stale_revision",
] as const;
export type ScreenState = (typeof screenStates)[number];
export type ReviewRole = "Operator" | "Reviewer" | "Auditor";
export type UiRecord = {
  id: string;
  feature: string;
  name: string;
  owner: string;
  values: Record<string, string>;
  version: number;
  status:
    | "draft"
    | "in_review"
    | "approved"
    | "changes_requested"
    | "rejected"
    | "outcome_unknown";
  events: { at: string; label: string; note: string }[];
};
export const phases = [
  {
    id: "foundation",
    title: "1 · Identity & platform foundation",
    modules: [
      "workspace_lifecycle",
      "identity_lifecycle",
      "secrets_network",
      "accessibility",
    ],
    deliverable:
      "Workspace, identity, access boundaries and usable global patterns.",
  },
  {
    id: "governance",
    title: "2 · Governed execution",
    modules: ["customer_connectors", "durable_agents", "traffic_controls"],
    deliverable: "Reviewed tools, durable execution and bounded admission.",
  },
  {
    id: "knowledge",
    title: "3 · Knowledge & AI quality",
    modules: [
      "document_ingestion",
      "document_permissions",
      "semantic_retrieval",
      "answer_evaluation",
      "provider_resilience",
    ],
    deliverable:
      "Reviewed sources, retrieval, model controls and measured answer quality.",
  },
  {
    id: "operations",
    title: "4 · Operational assurance",
    modules: [
      "usage_governance",
      "telemetry_alerts",
      "audit_retention",
      "recovery",
    ],
    deliverable: "Cost controls, visibility, evidence and tested recovery.",
  },
  {
    id: "release",
    title: "5 · Deployment & acceptance",
    modules: ["cloud_delivery", "security_load"],
    deliverable: "Controlled delivery and verified deployment acceptance.",
  },
] as const;
export const journeys = [
  {
    id: "onboarding",
    title: "Onboard an enterprise workspace",
    description:
      "Connect organization, identity, membership, environment and access review.",
    steps: [
      "workspace_lifecycle__organization_onboarding",
      "identity_lifecycle__oidc_and_saml_connection_design",
      "workspace_lifecycle__member_invitation_journey",
      "workspace_lifecycle__environment_creation_and_switch",
      "identity_lifecycle__access_certification_campaign",
    ],
  },
  {
    id: "execution",
    title: "Run a governed agent",
    description:
      "Review a tool connection, register an agent, checkpoint execution and inspect evidence.",
    steps: [
      "customer_connectors__rest_adapter_mapping",
      "durable_agents__agent_identity_and_capability_profile",
      "durable_agents__human_checkpoint_and_escalation",
      "durable_agents__workflow_graph_designer",
      "audit_retention__cross_service_correlation",
    ],
  },
  {
    id: "knowledge",
    title: "Turn a document into reviewed knowledge",
    description:
      "Intake, review, apply access, retrieve evidence and evaluate quality.",
    steps: [
      "document_ingestion__document_upload_queue",
      "document_ingestion__arabic_and_english_ocr_review",
      "document_permissions__document_rbac_matrix",
      "semantic_retrieval__hybrid_retrieval_weights",
      "answer_evaluation__release_evaluation_gate",
    ],
  },
  {
    id: "incident",
    title: "Investigate and recover an incident",
    description:
      "Follow alerts, investigation, controlled mitigation and evidence.",
    steps: [
      "telemetry_alerts__alert_rule_designer",
      "telemetry_alerts__incident_response_timeline",
      "telemetry_alerts__runbook_and_mitigation_steps",
      "recovery__isolated_restore_drill",
      "audit_retention__evidence_chain_investigation",
    ],
  },
  {
    id: "release",
    title: "Review a production release",
    description:
      "Inspect artifacts, scan findings, approval, rollout and rollback.",
    steps: [
      "cloud_delivery__build_artifact_registry",
      "cloud_delivery__image_vulnerability_gate",
      "cloud_delivery__deployment_approval",
      "cloud_delivery__canary_rollout_designer",
      "cloud_delivery__rollback_and_release_recovery",
    ],
  },
  {
    id: "finops",
    title: "Control AI spend and capacity",
    description:
      "Budget, admission, provider usage, reconciliation and evidence.",
    steps: [
      "usage_governance__workspace_budget_editor",
      "traffic_controls__budget_precheck",
      "usage_governance__provider_usage_ingestion",
      "usage_governance__invoice_reconciliation",
      "usage_governance__billing_evidence_export",
    ],
  },
] as const;
export const detailTabs = [
  "Overview",
  "Configuration",
  "Review",
  "Activity",
  "Access",
  "API handoff",
] as const;
export function phaseFor(module: string) {
  return phases.find((p) => (p.modules as readonly string[]).includes(module))!;
}
export function uiInputs(f: FunctionDefinition, row: UiRecord) {
  return validateOperation({ fields: f.fields } as any, {
    id: row.id,
    title: row.name,
    owner: row.owner,
    state: "draft",
    attributes: row.values,
  });
}
export function newUiRecord(f: FunctionDefinition, id: string): UiRecord {
  return {
    id,
    feature: f.id,
    name: f.title + " · example",
    owner: "Platform review team",
    values: Object.fromEntries(f.fields.map((x) => [x.id, x.default])),
    version: 1,
    status: "draft",
    events: [],
  };
}
export function previewTransition(
  row: UiRecord,
  command: string,
  role: ReviewRole,
  expected: number,
  note: string,
  state: ScreenState,
): UiRecord {
  if (row.events.length >= 50)
    throw Error(
      "This example reached 50 UI events. Export it and start a new example.",
    );
  if (row.version !== expected || state === "stale_revision")
    throw Error(
      "This preview revision changed. Refresh the record and review it again.",
    );
  if (role === "Auditor" || state === "permission_denied")
    throw Error(
      "This persona can inspect evidence but cannot change this preview record.",
    );
  if (
    ["loading", "empty", "validation_error", "dependency_unavailable"].includes(
      state,
    )
  )
    throw Error("Resolve the displayed screen state before continuing.");
  if (note.trim().length < 5 || note.length > 500)
    throw Error("Enter a review note of 5–500 characters.");
  const allowed: Record<string, string[]> = {
    submit: ["draft", "changes_requested"],
    approve: ["in_review"],
    rework: ["in_review"],
    reject: ["in_review"],
    reconcile: ["outcome_unknown"],
  };
  if (!allowed[command]?.includes(row.status))
    throw Error("This action is unavailable in the current preview state.");
  if (["approve", "rework", "reject"].includes(command) && role !== "Reviewer")
    throw Error(
      "Switch to the Reviewer preview persona for a review decision.",
    );
  if (command === "submit" && role !== "Operator")
    throw Error("Use the Operator preview persona to submit a draft.");
  if (row.status === "outcome_unknown" && command !== "reconcile")
    throw Error(
      "Inspect the existing request; do not resubmit an uncertain action.",
    );
  const next =
    state === "timeout_unknown"
      ? "outcome_unknown"
      : (
          {
            submit: "in_review",
            approve: "approved",
            rework: "changes_requested",
            reject: "rejected",
            reconcile: "in_review",
          } as const
        )[command];
  return {
    ...row,
    version: row.version + 1,
    status: next as UiRecord["status"],
    events: [
      ...row.events,
      { at: new Date().toISOString(), label: command, note: note.trim() },
    ],
  };
}
export const stateGuidance: Record<
  ScreenState,
  { title: string; body: string; action: string }
> = {
  ready: {
    title: "Ready for review",
    body: "Inspect the current example and follow the configuration, review and evidence sequence.",
    action: "Continue",
  },
  empty: {
    title: "No records match this view",
    body: "Create a synthetic example or clear the filter. No customer records are created.",
    action: "Create example",
  },
  loading: {
    title: "Loading preview records",
    body: "This is the designed loading state. Configuration and mutations remain unavailable until ready.",
    action: "Return to ready",
  },
  permission_denied: {
    title: "Access is restricted",
    body: "Explain required scope and offer an access-request journey without exposing restricted records.",
    action: "Review access journey",
  },
  validation_error: {
    title: "Correct the highlighted configuration",
    body: "Preserve inputs and identify the field-level issue before returning to review.",
    action: "Review configuration",
  },
  dependency_unavailable: {
    title: "A required service is unavailable",
    body: "Keep the draft and show the dependency status. Restoring a service must not silently execute a request.",
    action: "Return to ready",
  },
  timeout_unknown: {
    title: "Outcome needs reconciliation",
    body: "A timeout does not prove failure. Inspect the existing request before any replay; this preview only rehearses that screen.",
    action: "Inspect uncertain outcome",
  },
  stale_revision: {
    title: "A newer revision is available",
    body: "Refresh the selected record, compare the current values and repeat review before submitting.",
    action: "Refresh preview revision",
  },
};
