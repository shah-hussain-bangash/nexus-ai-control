export type BillingLine = {
  line_ref: string;
  call_id: string;
  billed_usd: string;
  input_tokens: string;
  output_tokens: string;
  provider_request_id: string;
};
export function usdToMicros(value: string) {
  const text = value.trim();
  if (!/^\d{1,7}(\.\d{1,6})?$/.test(text))
    throw Error(
      "Enter a nonnegative USD amount with at most six decimal places.",
    );
  const [whole, fraction = ""] = text.split(".");
  const micros = Number(whole) * 1000000 + Number(fraction.padEnd(6, "0"));
  if (micros > 1000000000000)
    throw Error("A comparison line supports at most 1,000,000 USD.");
  return micros;
}
function optionalTokens(value: string) {
  if (!value.trim()) return undefined;
  if (!/^\d{1,9}$/.test(value.trim()) || Number(value) > 100000000)
    throw Error("Token counts must be whole numbers from 0 to 100,000,000.");
  return Number(value);
}
export function billingStatementRequest(
  reference: string,
  period: string,
  note: string,
  lines: BillingLine[],
) {
  return {
    statement_ref: reference.trim(),
    period,
    currency: "USD",
    note: note.trim(),
    lines: lines.map((line) => ({
      line_ref: line.line_ref.trim(),
      call_id: line.call_id.trim(),
      billed_micro_usd: usdToMicros(line.billed_usd),
      ...(line.input_tokens.trim()
        ? { input_tokens: optionalTokens(line.input_tokens) }
        : {}),
      ...(line.output_tokens.trim()
        ? { output_tokens: optionalTokens(line.output_tokens) }
        : {}),
      ...(line.provider_request_id.trim()
        ? { provider_request_id: line.provider_request_id.trim() }
        : {}),
    })),
  };
}
