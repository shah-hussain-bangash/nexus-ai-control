from uuid import uuid4

from nexus.banking_policy import evaluate_evidence_read


def test_banking_evidence_policy_requires_matching_case_and_clearance():
    case = str(uuid4())
    inputs = dict(action="read_financial_evidence", actor_role="analyst", case_id=case,
                  evidence_case_id=case, compliance_status="cleared")
    assert evaluate_evidence_read(**inputs)["decision"] == "allow"
    for change in (
        {"action": "write_financial_evidence"},
        {"actor_role": "originator"},
        {"evidence_case_id": str(uuid4())},
        {"compliance_status": "pending"},
    ):
        assert evaluate_evidence_read(**(inputs | change))["decision"] == "deny"
