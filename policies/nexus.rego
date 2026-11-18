package nexus
import rego.v1

default decision := {"decision": "deny", "reason": "UNKNOWN_ACTION"}

decision := {"decision": "allow", "reason": "SCOPED_READ"} if {
    input.action == "supplier:read"
}
decision := {"decision": "allow", "reason": "WITHIN_GRANTED_LIMIT"} if {
    input.action == "purchase:create"
    input.amount_cents <= input.threshold_cents
    input.amount_cents <= input.maximum_cents
}
decision := {"decision": "require_approval", "reason": "AMOUNT_REQUIRES_APPROVAL"} if {
    input.action == "purchase:create"
    input.amount_cents > input.threshold_cents
    input.amount_cents <= input.maximum_cents
}
decision := {"decision": "deny", "reason": "AMOUNT_EXCEEDS_MAXIMUM"} if {
    input.action == "purchase:create"
    input.amount_cents > input.maximum_cents
}
