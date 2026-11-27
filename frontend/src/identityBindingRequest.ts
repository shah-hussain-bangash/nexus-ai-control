export function identityBindingRequest(
  member: { id: string; role: string; revision: string },
  actor: string,
  issuer: string,
  command: "bind" | "clear",
  subject: string,
  note: string,
  reviewed: boolean,
) {
  if (member.id === actor || member.role === "owner")
    throw Error("Owner and self identity changes are protected.");
  if (!/^[a-f0-9]{64}$/.test(member.revision))
    throw Error("Reload the current member revision.");
  if (
    !reviewed ||
    note.trim().length < 10 ||
    note.length > 500 ||
    note !== note.trim() ||
    /[\u0000-\u001f\u007f]/.test(note)
  )
    throw Error(
      "Review this change and provide a visible 10–500 character reason.",
    );
  if (
    subject !== subject.trim() ||
    subject.length > 200 ||
    /[\u0000-\u001f\u007f]/.test(subject)
  )
    throw Error(
      "Use the exact trusted subject without whitespace padding or control characters.",
    );
  if (
    (command === "bind" && (!issuer || !subject)) ||
    (command === "clear" && subject)
  )
    throw Error(
      "Binding requires a configured issuer and subject. Clearing requires an empty subject.",
    );
  return {
    expected_revision: member.revision,
    expected_issuer: issuer,
    command,
    subject,
    note,
    reviewed,
  };
}
