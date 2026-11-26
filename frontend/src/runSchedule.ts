export function scheduleRun<T extends object>(
  body: T,
  value: string,
  nowMs = Date.now(),
): T & { start_at?: number } {
  if (!value) return body;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))
    throw Error("Choose a valid local start date and time.");
  const [year, month, day, hour, minute] = value.split(/\D/).map(Number);
  const date = new Date(year, month - 1, day, hour, minute);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day ||
    date.getHours() !== hour ||
    date.getMinutes() !== minute
  )
    throw Error("This local start date or time does not exist.");
  const start = date.getTime();
  if (
    !Number.isSafeInteger(start) ||
    start <= nowMs ||
    start > nowMs + 7 * 86400000
  )
    throw Error("Choose a future start within the next seven days.");
  return { ...body, start_at: start / 1000 };
}
