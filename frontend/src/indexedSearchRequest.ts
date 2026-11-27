export function indexedSearchRequest(
  primary: string,
  additional: string[],
  query: string,
) {
  if (!primary) throw Error("Choose a primary snapshot.");
  const ids = [...new Set([primary, ...additional])].sort();
  if (ids.length > 8) throw Error("Choose at most eight snapshots in total.");
  return {
    ...(ids.length === 1 ? { index_id: primary } : { index_ids: ids }),
    query,
    top_k: 5,
    min_score: 0.15,
    one_per_document: true,
  };
}
