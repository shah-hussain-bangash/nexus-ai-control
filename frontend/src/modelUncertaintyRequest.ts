export function modelUncertaintyRequest(
  version: number,
  models: { id: string; version: number; status: string }[],
  limits: Record<string, string>,
  note: string,
) {
  if (!Number.isSafeInteger(version) || version < 0)
    throw Error("Reload the current policy.");
  if (
    note.trim().length < 10 ||
    note.length > 1000 ||
    /[\u0000-\u001f\u007f]/.test(note)
  )
    throw Error("Use a visible 10–1000 character reason.");
  const inventory = new Map(models.map((model) => [model.id, model]));
  const rules = Object.entries(limits)
    .filter(([, value]) => value.trim() !== "")
    .map(([id, value]) => {
      const model = inventory.get(id);
      if (
        !model ||
        model.status === "archived" ||
        !Number.isSafeInteger(model.version) ||
        model.version < 1
      )
        throw Error(
          "Reload the model inventory and remove unavailable routes.",
        );
      if (!/^[1-9][0-9]?$|^100$/.test(value))
        throw Error(
          "Use a whole-number unknown-outcome limit from 1 to 100, or leave blank.",
        );
      return {
        model_id: id,
        expected_model_version: model.version,
        unknown_limit: Number(value),
      };
    });
  if (rules.length > 100) throw Error("Configure at most 100 model routes.");
  return { expected_version: version, rules, note: note.trim() };
}
