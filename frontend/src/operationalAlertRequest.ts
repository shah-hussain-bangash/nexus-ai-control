export const alertMetrics = [
  [
    "oldest_queued_action_age_seconds",
    "Oldest queued action (seconds)",
    604800,
  ],
  ["unknown_action_count", "Unknown action outcomes (count)", 1000000],
  ["unknown_inference_count", "Unknown inference outcomes (count)", 1000000],
  [
    "overdue_pending_inference_count",
    "Inference pending at least 5 minutes (count)",
    1000000,
  ],
  [
    "expired_ingestion_lease_count",
    "Expired ingestion leases (count)",
    1000000,
  ],
  [
    "expired_index_build_lease_count",
    "Expired index build leases (count)",
    1000000,
  ],
  [
    "expired_agent_run_lease_count",
    "Expired agent run leases (count)",
    1000000,
  ],
] as const;
export type AlertRule = {
  metric: string;
  enabled: boolean;
  severity: "warning" | "critical";
  threshold: number;
};
export function alertPolicyRequest(
  version: number,
  rules: AlertRule[],
  note: string,
) {
  if (!Number.isSafeInteger(version) || version < 0)
    throw Error("Reload the current policy.");
  if (note.trim().length < 10 || note.length > 1000 || note.includes("\0"))
    throw Error("Use a change note of 10–1000 characters.");
  if (new Set(rules.map((r) => r.metric)).size !== rules.length)
    throw Error("Use one rule per signal.");
  return {
    expected_version: version,
    note: note.trim(),
    rules: rules.map((rule) => {
      const definition = alertMetrics.find(
        ([metric]) => metric === rule.metric,
      );
      if (
        !definition ||
        typeof rule.enabled !== "boolean" ||
        !["warning", "critical"].includes(rule.severity) ||
        !Number.isSafeInteger(rule.threshold) ||
        rule.threshold < 1 ||
        rule.threshold > definition[2]
      )
        throw Error(
          "Choose a positive whole-number threshold within the displayed limit.",
        );
      return {
        metric: rule.metric,
        enabled: rule.enabled,
        severity: rule.severity,
        threshold: rule.threshold,
      };
    }),
  };
}
