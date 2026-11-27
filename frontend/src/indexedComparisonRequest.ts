export function indexedComparisonRequest(
  baselineId: string,
  candidateId: string,
) {
  if (!baselineId || !candidateId || baselineId === candidateId)
    throw Error("Choose two different saved reviews.");
  return { baseline_id: baselineId, candidate_id: candidateId };
}
