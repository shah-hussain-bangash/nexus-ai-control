export function collectionSelection(
  group: {
    searchable: boolean;
    index_ids: string[];
    model: string;
    model_digest: string;
  },
  model: string,
  digest: string,
) {
  if (
    !group.searchable ||
    group.model !== model ||
    group.model_digest !== digest ||
    !Array.isArray(group.index_ids) ||
    group.index_ids.length < 1 ||
    group.index_ids.length > 8 ||
    new Set(group.index_ids).size !== group.index_ids.length ||
    group.index_ids.some(
      (id) => typeof id !== "string" || !id || id.length > 64,
    )
  )
    throw Error(
      "Select a completed, current collection that matches the configured embedding model.",
    );
  return [...group.index_ids];
}
