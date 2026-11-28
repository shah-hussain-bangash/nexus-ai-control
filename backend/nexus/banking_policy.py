"""Case-bound reference policy for the synthetic credit evidence connector."""

from uuid import UUID


POLICY_VERSION = "nexus-credit-evidence-v1"


def evaluate_evidence_read(*, action, actor_role, case_id, evidence_case_id, compliance_status):
    """This policy authorizes one structured read and cannot authorize a write."""
    if action != "read_financial_evidence":
        return {"decision": "deny", "reason": "UNKNOWN_ACTION", "policy_version": POLICY_VERSION}
    try:
        same_case = UUID(case_id) == UUID(evidence_case_id)
    except (AttributeError, TypeError, ValueError):
        same_case = False
    if actor_role != "analyst" or not same_case:
        return {"decision": "deny", "reason": "MISSING_CASE_SCOPE", "policy_version": POLICY_VERSION}
    if compliance_status != "cleared":
        return {"decision": "deny", "reason": "COMPLIANCE_CLEARANCE_REQUIRED", "policy_version": POLICY_VERSION}
    return {"decision": "allow", "reason": "SCOPED_CREDIT_EVIDENCE_READ", "policy_version": POLICY_VERSION}
