# NEXUS AI Control 0.3.3 - clear submissions and recovery-safe retry keys

14 November 2026. This patch addresses the repeated synthetic approval-test confusion seen after 0.3.2.

## Fixes

1. **Successful submissions no longer reuse an old intent key.** Previously the UI kept a body-to-key map indefinitely, including after success. Submitting identical values again could retrieve an earlier verified or expired record while displaying a generic submission toast. The UI now retires a key only after a response identifies the accepted action and its status. A later deliberate new submission gets a fresh key, even with identical form values.
2. **Uncertain retries retain their key.** Network failures and incomplete responses preserve the existing key for the unchanged body in the loaded UI. Retrying after a lost response can recover the original action instead of creating another effect. This in-memory recovery map does not survive a page reload. Inspect Executions before recreating an intent after an uncertain outcome; do not change payloads or generate a fresh key merely to bypass uncertainty.
3. **Business tool selection is explicit.** The form opens with “Choose a business tool” and submission stays disabled until a selection is made. It no longer silently defaults to Supplier directory.
4. **Purchase fields are tool-specific.** Amount and purpose appear only for Purchase requests. Supplier directory displays a read-only explanation and sends no purchase parameters. Policy enforcement stays on the backend.
5. **Confirmation reflects the actual returned record.** The toast includes its ACT reference and whether it awaits approval, is queued, is denied or is already verified. Pending review navigates to Approvals; other outcomes navigate to Executions. The All filter is restored so a prior filter does not hide the result.
6. **Lockfile metadata restored.** The prior release-number replacement also altered transitive dependency version strings in the lockfile. This patch restores them from the 0.3.1 baseline and updates only root package version metadata; clean npm installation passed.

No approval window, role, identity, policy, database schema or dispatch authorization was relaxed. Expired approvals stay expired; owner self-approval stays prohibited. Existing user accounts and data are preserved.

## Verification

- `npm ci`: passed with the restored lockfile.
- `npm test`: five cases passed. Covers new keys for new acknowledged intents, response loss after a simulated commit without duplicate effect, independent uncertain payload keys, incomplete acknowledgement recovery, and actual-status feedback.
- `npm run build`: TypeScript and Vite passed; compiled frontend included.
- 0.3.2 Python regression remains historical evidence: 88 passed, 15 skipped, zero failures/errors. Backend logic is unchanged in 0.3.3 except release metadata; the full backend suite was not rerun for this UI patch.
- This patch was not installed or browser-tested on the user's Windows machine. No successful new reviewer approval is claimed by this release.

## Upgrade and finish the synthetic test

1. Stop the existing launcher with Ctrl+C. Back up `backend/.env` and both configured databases while stopped.
2. Copy the new release files into the existing project, preserving `.env`, runtime data and `.venv`. These are excluded from the ZIP. Schema remains 2.
3. From `C:\nexus-ai-control`, run `.\scripts\start.cmd` and open its printed URL. Refresh the browser to load the new frontend. Check footer version **0.3.3**.
4. Keep the reviewer signed in in a normal Chrome window. Use Incognito for the owner, since tabs in the same browser context share a session.
5. As owner, click Run governed action. Explicitly choose Procurement Atlas and **Purchase requests**, supplier SUP-DEMO-104, amount **12500**, and a synthetic purchase purpose. Submit once.
6. Confirm the toast and new record say **Awaiting approval/Pending**. Above-maximum values may be denied; lower values may be allowed directly under the active policy.
7. In the reviewer window, refresh Approvals and open the new Pending record. Add a review note and approve within the displayed expiry. Refresh Executions to inspect the worker's verified result or explicit exception state.

The remaining enterprise phases in `RELEASE_0_3_2.md` still apply. This is a synthetic integration prototype, not a completed customer production deployment.
