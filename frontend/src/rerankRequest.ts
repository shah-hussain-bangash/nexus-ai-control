export function rerankRequest(searchId: string, query: string) {
  return { search_id: searchId, query: query.trim() };
}
