export function indexedReviewRequest(options: {
  searchId: string;
  expectation: "retrieve" | "no_results";
  expected: string[];
  language: "" | "English" | "Arabic" | "Bilingual";
  precision: number | null;
  note: string;
}) {
  return {
    search_id: options.searchId,
    expectation: options.expectation,
    expected_document_ids:
      options.expectation === "retrieve" ? [...options.expected].sort() : [],
    ...(options.language ? { query_language: options.language } : {}),
    ...(options.expectation === "retrieve" && options.precision !== null
      ? { minimum_precision_percent: options.precision }
      : {}),
    note: options.note.trim(),
  };
}
