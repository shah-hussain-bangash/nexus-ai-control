export function indexJobRequest(
  name: string,
  sources: { id: string; version: number }[],
) {
  return {
    name: name.trim(),
    sources: sources.map(({ id, version }) => ({ id, version })),
  };
}
