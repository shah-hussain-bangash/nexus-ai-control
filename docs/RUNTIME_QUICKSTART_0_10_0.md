# Working runtime walkthrough — 0.10.0

Use the actual local app started by scripts/start.cmd. The demo-preview harness shows synthetic read snapshots and blocks new runtime writes. Keep the API/worker terminal open. Use synthetic test data only until deployment data controls have been accepted.

## Complete a supervised procurement workflow

1. Sign in as owner@nexus.local in your normal browser with your privately saved owner password. Open **Agent execution → Start durable run**.
2. Select **Supervised procurement**, **Procurement Atlas**, **SUP-DEMO-104**, **USD 12,500**, and purpose **Synthetic replacement equipment**. Submit once.
3. The worker persists the input checkpoint and completes the governed supplier lookup, then waits at the independent workflow checkpoint. Leave the owner session open.
4. Open a separate incognito/browser session at the exact same printed URL. Sign in as reviewer@nexus.local with the reviewer password. Open **Agent execution**, choose the waiting run, select **Approve checkpoint**, inspect its immutable definition and enter a meaningful review note. Complete this before the displayed 30-minute expiry. The owner cannot approve their own workflow.
5. The worker submits the purchase through the policy engine. USD 12,500 requires a separate business approval. In the reviewer session open **Human approvals → Pending → Review request**. Inspect supplier, amount and purpose, enter **Reviewed synthetic supplier, amount and purchase purpose.**, and approve before expiry.
6. Return to Agent execution. The worker should verify the purchase and complete the output checkpoint. Inspect the linked action in Execution ledger and confirm its evidence. Do not submit repeatedly while waiting.

If a review has expired, it cannot be approved. Cancel the old run and create a fresh run. A blocked policy/grant or revoked agent is a real failure to investigate, not a reason to bypass authorization. Pause affects future checkpoints. Cancellation cannot undo a dispatched effect; unknown outcomes stay tracked for reconciliation. Retry never resubmits an already linked action.

## Upload and check document permissions

1. Create a small UTF-8 .txt file containing **SYNTHETIC: Purchase approval above USD 5,000 requires independent review.**
2. As owner open **Document library → Upload text document**, choose the file, set a title/language and grant **Auditor** reader access. Upload once.
3. Search **approval**, inspect the citation, open its stored source and verify version/hash/content.
4. Sign in as auditor@nexus.local in an independent session using its existing password. Confirm the granted source is readable. The auditor cannot change its ACL or delete it.
5. As owner, Manage access and remove the Auditor grant with a note. A fresh auditor retrieval must no longer return the source. An already displayed browser copy cannot be remotely erased.
6. Delete the synthetic source as owner with a note. Confirm it disappears from retrieval. Active chunks/content are removed; backup/WAL retention remains a separate deployment control.

Uploads support UTF-8 TXT/MD/CSV/JSON up to 32 KiB, not PDF/OCR or vector search. Owner/security administration and the author retain access. The API also accepts explicit same-organization active user grants.

If creation/upload times out, retain the original form and use **Recover pending run** or **Recover pending upload** before creating a different intent. Only request metadata is retained in the same tab; never clear recovery state to force a duplicate effect.
