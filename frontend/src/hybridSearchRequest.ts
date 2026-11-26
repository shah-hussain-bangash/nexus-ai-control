export function hybridSearchRequest(options: {
  neural: boolean;
  query: string;
  sources: { id: string; version: number }[];
  dimensions: number;
  weight: number;
  threshold: number;
  top: number;
  onePerDocument: boolean;
}) {
  const {
    neural,
    query,
    sources,
    dimensions,
    weight,
    threshold,
    top,
    onePerDocument,
  } = options;
  return {
    query,
    sources: sources.map(({ id, version }) => ({ id, version })),
    ...(neural
      ? { retrieval_mode: "local_neural" }
      : { dimensions, semantic_weight: weight }),
    min_score: threshold,
    top_k: top,
    ...(onePerDocument ? { one_per_document: true } : {}),
  };
}
