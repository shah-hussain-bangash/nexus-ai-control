import test from "node:test";
import assert from "node:assert/strict";
import {
  alertPolicyRequest,
  alertMetrics,
} from "../src/operationalAlertRequest.ts";
import { liveIntentScope } from "../src/liveIntent.ts";
const note = "Reviewed manual alert rules.";
test("fixed alert rules preserve version and copy reviewed inputs", () => {
  const rules = [
    {
      metric: "unknown_action_count",
      enabled: true,
      threshold: 1,
      severity: "critical" as const,
    },
  ];
  const request = alertPolicyRequest(2, rules, note);
  rules[0].threshold = 99;
  assert.equal(request.rules[0].threshold, 1);
  assert.equal(request.expected_version, 2);
  assert.equal(alertMetrics.length, 7);
  assert.deepEqual(alertPolicyRequest(0, [], note).rules, []);
});
test("reject unknown, duplicate, fractional and out-of-range alert thresholds", () => {
  for (const threshold of [0, 1.5, NaN, 1000001])
    assert.throws(() =>
      alertPolicyRequest(
        0,
        [
          {
            metric: "unknown_action_count",
            enabled: true,
            threshold,
            severity: "warning",
          },
        ],
        note,
      ),
    );
  assert.throws(() =>
    alertPolicyRequest(
      0,
      [
        {
          metric: "oldest_queued_action_age_seconds",
          enabled: true,
          threshold: 604801,
          severity: "warning",
        },
      ],
      note,
    ),
  );
  assert.throws(() =>
    alertPolicyRequest(
      0,
      [{ metric: "sql", enabled: true, threshold: 1, severity: "warning" }],
      note,
    ),
  );
  const rule = {
    metric: "unknown_action_count",
    enabled: true,
    threshold: 1,
    severity: "warning" as const,
  };
  assert.throws(() => alertPolicyRequest(0, [rule, rule], note));
  assert.throws(() => alertPolicyRequest(0, [], "   "));
});
test("policy and sample recovery keys are separate across users and environments", () => {
  const scope = liveIntentScope("ops-alert-policy", "org", "user", "staging");
  assert.notEqual(
    scope,
    liveIntentScope("ops-alert-sample", "org", "user", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("ops-alert-policy", "org", "other", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("ops-alert-policy", "org", "user", "development"),
  );
});
