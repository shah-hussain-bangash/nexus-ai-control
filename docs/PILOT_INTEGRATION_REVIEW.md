# Combined local-pilot review candidate

This isolated integration candidate combines the source below against main
`c89707b7812c9d92ee3de93d2c2863921b1955bd`. It is a review build, not a release,
production acceptance, authorization to merge the original PRs, or deployment.
The running Cursor checkout, accounts, credentials and database are not changed.

## Included source

| PR | Capability | Pinned head |
| --- | --- | --- |
| [#65](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/65) | Add offline recovery evidence checker and missing-proof regressions | `9274bf5ef98487262fdd4306834bfa995139ac72` |
| [#66](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/66) | Add reusable disposable Docker recovery and restart drill | `d75026eaf747340ec5f277c528d9d1074173157b` |
| [#67](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/67) | Add offline English and Arabic synthetic answer review | `07a31c0e0ed4067c13789c47a3ec21dbc64a7ea2` |
| [#72](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/72) | Match the capability dashboard to the preserved Cursor version | `e84b9e45b70f8df1ca97a97ad7c1dc0c27552df9` |
| [#73](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/73) | Phase 1: build a scoped Business v1 reference gateway | `b1c1b05200f8b62cc48daf8451684b4d23b25fcb` |
| [#74](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/74) | Add reviewable durable workflow evidence snapshots | `03d4e2e349b2ef2a82acd88469fcb0640848078c` |
| [#75](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/75) | Add a scoped attention filter for durable workflows | `998ac8fd5767c82c350d468345faab6235747a84` |
| [#76](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/76) | Add bounded one-time scheduled starts for durable workflows | `50315f8e2c97b2f4ba9e6c99a0fd369480432f38` |
| [#77](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/77) | Add bounded supplier allowlist routing to durable workflows | `00c24751206a2164ae996b9941dfb3ab21f87d7f` |
| [#78](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/78) | Support workflow reports in offline evidence verification | `d69f02c96f733125c65c7e907ff72778d56c6329` |
| [#79](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/79) | Add optional one-result-per-document retrieval | `f805bf8e1c218e1181f7c5cf33453221f49acaad` |
| [#80](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/80) | Add read-only review of identical indexed-text documents | `5a72caba636ccfa9970852135ee1a9c21a068419` |
| [#81](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/81) | Add one-result-per-document option to keyword search | `40d6fa7d157afe6bb322051218a13d9a2814339c` |
| [#82](https://github.com/shah-hussain-bangash/nexus-ai-control/pull/82) | Add saved retrieval quality checks for document diversity | `f8816d277dcffc5e64e1dbf75291570429366321` |

## Resolved overlaps

- Preserved both existing pilot/answer commands and the disposable Docker recovery commands.
- Kept workflow evidence, request coordination, scheduling, supplier routing and document-copy imports together in Document library/workflows.
- Retained hybrid diversity, lexical diversity, identical-text review and mode-bound saved quality checks without changing legacy search defaults.
- Combined connector, workflow, retrieval, permission and evidence roadmap descriptions in the source definitions, then regenerated both roadmap artifacts. Partial states remain partial.
- Retained every feature documentation link and the reviewed dashboard capability source from PR #72.
- Conflict resolution uses explicit UTF-8 text handling; source strings and bilingual text are preserved.

The workflow stack (#74–#78) and evaluation stack (#81–#82) are combined in dependency order. Older open recovery/answer PRs (#65–#67) also contain source changes absent from main and are included. No original PR was closed, merged, rebased or otherwise rewritten.

## Verification and limits

Local verification runs the changed-feature backend suites on disposable databases,
all frontend unit checks, the frontend build, generated-roadmap consistency, and
conflict-marker/diff checks. `test_pilot_feature_integration.py` exercises copy
review, document-diverse keyword search and persisted quality checks through the
normal API, then revokes source access and checks all three boundaries again.

GitHub CI must verify the **combined** revision, including full backend,
PostgreSQL recovery/regression, Windows launcher, frontend, policy and disposable
Docker recovery checks. Individual PR passes do not establish combined acceptance.
Docker recovery is confined to disposable fixtures and owned resources. No live
customer connector, model provider, application database or infrastructure is
part of the integration tests. Existing bundle-size and optional dependency
warnings remain separate from test failures.

The next review decision is whether to accept the combined source. Merging,
updating the active Cursor checkout and restarting the pilot require a separate
explicit decision. Enterprise integrations, neural retrieval, identity/security,
operations, real backup scope and deployment acceptance remain future phases.
