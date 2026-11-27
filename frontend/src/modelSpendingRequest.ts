import { usdToMicros } from "./billingStatementRequest.ts";
export function modelSpendingRequest(
  version: number,
  required: boolean,
  models: { id: string; version: number }[],
  limits: Record<string, string>,
  note: string,
) {
  const caps = models
    .filter((model) => (limits[model.id] ?? "").trim() !== "")
    .map((model) => ({
      model_id: model.id,
      expected_model_version: model.version,
      monthly_limit_micro_usd: usdToMicros(limits[model.id]),
    }));
  return {
    expected_version: version,
    require_model_caps: required,
    caps,
    note: note.trim(),
  };
}
export function formatMicroUsd(value: string | number) {
  const amount = BigInt(value),
    negative = amount < 0n,
    absolute = negative ? -amount : amount;
  return `${negative ? "-" : ""}$${(absolute / 1000000n).toLocaleString("en-US")}.${(absolute % 1000000n).toString().padStart(6, "0")}`;
}
export function microUsdInput(value: number) {
  const amount = BigInt(value);
  return `${amount / 1000000n}.${(amount % 1000000n).toString().padStart(6, "0")}`;
}
