export function procurementRun(
  agentId: string,
  supplierTool: string,
  purchaseTool: string,
  mode: string,
  supplier: string,
  amount: string,
  purpose: string,
) {
  if (!agentId || !supplierTool)
    throw Error("Choose an active agent and registered supplier tool.");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(supplier))
    throw Error("Enter a valid supplier reference of up to 64 characters.");
  const steps: any[] = [
    { kind: "checkpoint", label: "Validate run inputs" },
    {
      kind: "governed_action",
      label: "Supplier directory lookup",
      tool_id: supplierTool,
      request: {
        action: "supplier:read",
        resource: "suppliers",
        arguments: { supplier_id: supplier },
      },
    },
  ];
  if (mode === "procurement") {
    if (
      !purchaseTool ||
      !/^\d{1,8}\.\d{2}$/.test(amount) ||
      Number(amount) <= 0 ||
      purpose.trim().length < 3 ||
      purpose.length > 300
    )
      throw Error(
        "Enter a positive amount with two decimals and a purchase purpose.",
      );
    steps.push(
      { kind: "approval", label: "Independent workflow review" },
      {
        kind: "governed_action",
        label: "Governed purchase request",
        tool_id: purchaseTool,
        request: {
          action: "purchase:create",
          resource: "purchase_requests",
          arguments: {
            supplier_id: supplier,
            amount,
            currency: "USD",
            purpose: purpose.trim(),
          },
        },
      },
    );
  }
  steps.push({ kind: "output", label: "Collect verified outcome" });
  return {
    name:
      mode === "procurement"
        ? "Supervised procurement run"
        : "Verified supplier lookup",
    agent_id: agentId,
    steps,
  };
}
export function intakeMetadata(file: { name: string; size: number }) {
  if (
    !/^[^/\\]+\.(txt|md|csv|json)$/i.test(file.name) ||
    file.name.length > 120
  )
    throw Error("Choose a TXT, MD, CSV or JSON file with a plain filename.");
  if (file.size < 1 || file.size > 32768)
    throw Error("Document intake supports 1 byte to 32 KiB of UTF-8 text.");
  return { filename: file.name, bytes: file.size };
}
export function runControls(run: { status: string; can_retry?: boolean }) {
  const s = run.status;
  return [
    ...(["queued", "processing", "waiting_action", "waiting_review"].includes(s)
      ? ["pause"]
      : []),
    ...(s === "paused" ? ["resume"] : []),
    ...([
      "queued",
      "processing",
      "waiting_action",
      "waiting_review",
      "paused",
      "cancelling",
      "outcome_unknown",
    ].includes(s)
      ? ["cancel"]
      : []),
    ...(run.can_retry ? ["retry"] : []),
  ];
}

export function queuedFileMetadata(file: { name: string; size: number }) {
  if (
    !/^[^/\\]+\.(pdf|docx|png|jpe?g)$/i.test(file.name) ||
    file.name.length > 120
  )
    throw Error("Choose a plain PDF, DOCX, PNG or JPEG filename.");
  if (file.size < 1 || file.size > 1048576)
    throw Error("File intake supports 1 byte to 1 MiB.");
  return { filename: file.name, bytes: file.size };
}
