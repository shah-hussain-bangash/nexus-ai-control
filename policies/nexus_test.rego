package nexus_test
import rego.v1
import data.nexus.decision

test_read_allowed if {
    result := decision with input as {"action": "supplier:read"}
    result.decision == "allow"
}
test_unknown_denied if {
    result := decision with input as {"action": "delete:all"}
    result.decision == "deny"
}
test_threshold_allowed if {
    result := decision with input as {"action":"purchase:create","amount_cents":500000,"threshold_cents":500000,"maximum_cents":2500000}
    result.decision == "allow"
}
test_above_threshold_reviewed if {
    result := decision with input as {"action":"purchase:create","amount_cents":500001,"threshold_cents":500000,"maximum_cents":2500000}
    result.decision == "require_approval"
}
test_above_maximum_denied if {
    result := decision with input as {"action":"purchase:create","amount_cents":2500001,"threshold_cents":500000,"maximum_cents":2500000}
    result.decision == "deny"
}
