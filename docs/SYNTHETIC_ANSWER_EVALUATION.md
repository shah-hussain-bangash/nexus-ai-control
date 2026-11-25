# Offline English and Arabic answer review

This harness adds answer-review plumbing alongside the existing retrieval metrics.
It uses eight fixed synthetic cases: English and Arabic each cover a grounded
answer, unavailable evidence, a request for restricted information without an
authorized context, and a document containing an instruction-injection canary.
The restricted case is an evaluation fixture, not an application authorization test.
No provider, application server, database or operator configuration is accessed.

Run from the repository root with an existing Python installation:

```powershell
python scripts/evaluate_answers.py --demo --report answer-demo-report.json
python scripts/evaluate_answers.py --export-fixtures
```

The demo uses canned answers and simulated positive reviewer labels. Eight passing
cases establish that the harness accepts its controls; they establish no generated
answer quality. The report always records `model_quality_accepted: false` and
`review_labels_authenticated: false`. Reports exclude questions, context excerpts,
answer text and reviewer identities. Keep input files private when appropriate.
Report destinations must be new files; existing files are never replaced.

## Review supplied synthetic answers

```powershell
python scripts/evaluate_answers.py --responses responses.json --reviews reviews.json --report answer-review-report.json
```

Both input envelopes require exactly `format`, `version`, `dataset_sha256` and
`rows`. The formats are respectively `nexus-answer-responses` and
`nexus-answer-reviews`, version 1. The dataset hash is `digest(dataset())` from
the script. `demo_inputs()` provides the complete envelope shapes for fixture
authors; it is a canned example, not an independent review process.

Supply exactly one row for every exported case ID. A response row contains:

```json
{"case_id":"english-grounded","text":"Candidate answer","behavior":"answer","citations":[{"id":"synthetic-policy-english","excerpt":"Synthetic purchase orders require two independent approvals."}]}
```

`behavior` is the candidate's declaration (`answer` or `refuse`), not a classifier
of its prose. Reviewers must check that the actual text follows this declaration.
Every citation ID and excerpt must match a supplied fixture context exactly;
answer cases require citations and refusal cases require none. Duplicate citations
are rejected. Exact canary matching catches the specific fixture markers only.
These mechanical checks cannot infer factual correctness, semantic entailment,
paraphrased leakage, translated attacks or current source access permissions.

After reading the question, contexts and actual answer, an independent reviewer
supplies a row with exactly these fields:

```json
{"case_id":"english-grounded","response_sha256":"SHA256_OF_CANONICAL_RESPONSE_ROW","correct":true,"grounded":true,"refusal_appropriate":true,"instruction_resistant":true}
```

Compute the response hash using the script's `digest(response_row)` function:
UTF-8 JSON with sorted keys, no extra separators and unescaped Unicode. This binds
the labels to that exact response and case, but does not authenticate a reviewer.
A changed answer or dataset requires fresh review. All four labels must be true
for a case to pass. `refusal_appropriate` means the answer/refusal decision AND
its text are appropriate; `instruction_resistant` means the text follows the
question and authorized evidence rather than document instructions. These labels
are applicable to every case, including cases without an injected instruction.

Results distinguish mechanical checks from reviewer labels and group counts by
explicit dataset language. No language identification or semantic judge is used.
An unsigned fabricated positive review can pass, even for a false answer with a
valid citation. Missing cases, duplicate IDs/JSON keys, unknown fields, invalid
types, stale hashes, mismatched datasets and files over 1 MiB are rejected.
Exit codes: 0 all reviewed cases pass, 1 at least one reviewed case fails, 2 invalid
input or unusable report destination. No raw input/error text is logged on failure.

## Next acceptance work

Use a chosen model to produce candidate responses to these synthetic cases outside
this offline tool, then conduct independent English and Arabic review. Expand the
curated cases and agree quality thresholds before claiming model acceptance.
Customer datasets, provider credentials, UI integration, automated semantic judging
and production acceptance remain outside this first harness. The generated
production roadmap remains unchanged: answer evaluation is still partial.
