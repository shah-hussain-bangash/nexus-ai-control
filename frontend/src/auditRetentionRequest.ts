export const retentionConfirmation = "PURGE EXPIRED SIGNED AUDIT PAYLOADS";
export function retentionApplyRequest(
  plan: { id: string; status: string; policy_version: number },
  policyVersion: number,
  confirmation: string,
  note: string,
) {
  if (!plan.id || !["previewed", "applied"].includes(plan.status))
    throw Error("Choose a saved retention preview.");
  if (
    !Number.isSafeInteger(policyVersion) ||
    policyVersion < 1 ||
    (plan.status !== "applied" && plan.policy_version !== policyVersion)
  )
    throw Error("The policy changed. Create a fresh preview.");
  if (confirmation !== retentionConfirmation)
    throw Error("Type the exact displayed confirmation.");
  if (
    note.trim().length < 10 ||
    note.length > 500 ||
    /[\u0000-\u001f\u007f]/.test(note)
  )
    throw Error("Use a visible 10–500 character reason.");
  return { expected_version: policyVersion, confirmation, note: note.trim() };
}
