# Optional minimum document precision

Open **Document library**, then **New retrieval check** or **Review and rerun suite**. For an expected-source retrieval case, select **Require a minimum document precision**. The enabled control starts at 100%; enter a whole percentage from 0 through 100. Leave the checkbox off to retain the existing expected-source-only pass rule. Switching a case to **Return no results** clears its precision target.

An opted-in case passes only when every expected document is found and its document precision meets or exceeds the selected target. The decision uses distinct document counts and integer arithmetic, not rounded scores. At one expected document among two returned documents, 50% passes a 50% target and fails a 51% or 100% target. One match among three returned documents passes 33% and fails 34%. The result shows the configured minimum and **Target met** or **Below target** beside the measured precision.

A 0% target still requires all expected documents to be retrieved. Empty positive results have precision 0 and fail the missing-source expectation. No-result cases retain their existing zero-match rule and cannot set a precision target. Overall suite status and per-language passed-case counts include target failures; recall, precision and rank measurements retain their original definitions.

Precision assumes the expected-source list is complete. An unlisted document may be relevant. Review unlisted sources and test expectations before enabling a strict target. This feature evaluates the configured document-retrieval suite and does not approve deployment, grade generated answers or certify language relevance.

## Storage and compatibility

The optional API field is `cases[].minimum_precision_percent`: a strict JSON integer from 0 to 100, or null/omitted. Fractions, decimal JSON values, strings, booleans and out-of-range values are rejected. An unset/null target is excluded from normalized configuration, preserving previous request fingerprints and unchanged replay/recovery behavior. A changed target is a changed intent and requires a new request key. Browser controls validate enabled targets before submission; incomplete inputs are not serialized as a disabled target.

New targeted cases save their minimum, target outcome and combined pass result when the suite runs. Historical detail recomputes the target indicator from saved expected/returned identifiers, without rerunning retrieval or rewriting stored JSON. Old untargeted cases acquire no target and keep their original pass status. Rerun configuration preserves an existing target so the reviewer can keep, change or disable it deliberately. Current account/workspace/environment, source ACL/deletion checks and evidence staleness continue to apply.

No migration, dependency, customer connection, provider call, automatic rerun or stored-document rewrite is introduced.
