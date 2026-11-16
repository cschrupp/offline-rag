import {
  type EngineeringEvidenceManifest,
  type EvidenceRecord,
  type Metric,
} from "./evidenceTypes";

export class PortfolioProjectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PortfolioProjectionError";
  }
}

function requireRecord(
  manifest: EngineeringEvidenceManifest,
  evidenceId: string,
): EvidenceRecord {
  const record = manifest.records.find((item) => item.evidence_id === evidenceId);
  if (!record) {
    throw new PortfolioProjectionError(
      `Required Engineering evidence is missing: ${evidenceId}`,
    );
  }
  return record;
}

function requireObject(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new PortfolioProjectionError(`Required evidence binding is invalid: ${label}`);
  }
  return value as Record<string, unknown>;
}

function requireFact(record: EvidenceRecord, factId: string): Record<string, unknown> {
  const presentation = requireObject(record.presentation, `${record.evidence_id}.presentation`);
  const facts = presentation.facts;
  if (!Array.isArray(facts)) {
    throw new PortfolioProjectionError(
      `Required Engineering fact list is missing: ${record.evidence_id}`,
    );
  }
  const fact = facts.find(
    (item) =>
      item &&
      typeof item === "object" &&
      (item as Record<string, unknown>).fact_id === factId,
  );
  if (!fact) {
    throw new PortfolioProjectionError(
      `Required Engineering fact is missing: ${record.evidence_id}/${factId}`,
    );
  }
  return fact as Record<string, unknown>;
}

function requireFactMetric(
  record: EvidenceRecord,
  factId: string,
  metricId: string,
): Metric {
  const fact = requireFact(record, factId);
  const metrics = fact.metrics;
  if (!Array.isArray(metrics)) {
    throw new PortfolioProjectionError(
      `Required metric list is missing: ${record.evidence_id}/${factId}`,
    );
  }
  const metricRow = metrics.find(
    (item) =>
      item &&
      typeof item === "object" &&
      (item as Record<string, unknown>).metric_id === metricId,
  );
  if (!metricRow) {
    throw new PortfolioProjectionError(
      `Required metric is missing: ${record.evidence_id}/${factId}/${metricId}`,
    );
  }
  const metric = (metricRow as Record<string, unknown>).metric;
  if (!metric || typeof metric !== "object" || !("availability" in metric)) {
    throw new PortfolioProjectionError(
      `Required metric binding is invalid: ${record.evidence_id}/${factId}/${metricId}`,
    );
  }
  const bound = metric as Metric;
  if (!bound.display_kind || typeof bound.precision !== "number") {
    throw new PortfolioProjectionError(
      `Required metric definition is missing: ${record.evidence_id}/${factId}/${metricId}`,
    );
  }
  if (bound.availability !== "measured" || typeof bound.value !== "number") {
    throw new PortfolioProjectionError(
      `Required measured value is unavailable: ${record.evidence_id}/${factId}/${metricId}`,
    );
  }
  return bound;
}

function requirePrompt(record: EvidenceRecord, promptId: string): Record<string, unknown> {
  const prompts = record.presentation.prompts;
  if (!Array.isArray(prompts)) {
    throw new PortfolioProjectionError(
      `Required prompt list is missing: ${record.evidence_id}`,
    );
  }
  const prompt = prompts.find(
    (item) =>
      item &&
      typeof item === "object" &&
      (item as Record<string, unknown>).prompt_id === promptId,
  );
  if (!prompt) {
    throw new PortfolioProjectionError(
      `Required prompt is missing: ${record.evidence_id}/${promptId}`,
    );
  }
  return prompt as Record<string, unknown>;
}

function requireNestedMetric(
  root: Record<string, unknown>,
  groupId: string,
  metricId: string,
  label: string,
): Metric {
  const group = groupId
    ? requireObject(root[groupId], `${label}.${groupId}`)
    : root;
  const rawMetric = group[metricId];
  if (!rawMetric || typeof rawMetric !== "object" || !("availability" in rawMetric)) {
    throw new PortfolioProjectionError(`Required metric is missing: ${label}/${metricId}`);
  }
  const metric = rawMetric as Metric;
  if (!metric.display_kind || typeof metric.precision !== "number") {
    throw new PortfolioProjectionError(`Required metric definition is missing: ${label}/${metricId}`);
  }
  if (metric.availability !== "measured" || typeof metric.value !== "number") {
    throw new PortfolioProjectionError(`Required measured value is unavailable: ${label}/${metricId}`);
  }
  return metric;
}

function requireVariant(record: EvidenceRecord, variantId: string): Record<string, unknown> {
  const variants = record.presentation.variants;
  if (!Array.isArray(variants)) {
    throw new PortfolioProjectionError(
      `Required variant list is missing: ${record.evidence_id}`,
    );
  }
  const variant = variants.find(
    (item) =>
      item &&
      typeof item === "object" &&
      (item as Record<string, unknown>).variant_id === variantId,
  );
  if (!variant) {
    throw new PortfolioProjectionError(
      `Required variant is missing: ${record.evidence_id}/${variantId}`,
    );
  }
  return variant as Record<string, unknown>;
}

function requireArm(
  record: EvidenceRecord,
  populationId: string,
  armId: string,
): Record<string, unknown> {
  const populations = requireObject(record.presentation.populations, `${record.evidence_id}.populations`);
  const population = requireObject(populations[populationId], `${record.evidence_id}.${populationId}`);
  if (!Array.isArray(population.arms)) {
    throw new PortfolioProjectionError(`Required arm list is missing: ${record.evidence_id}/${populationId}`);
  }
  const arm = population.arms.find(
    (item) =>
      item &&
      typeof item === "object" &&
      (item as Record<string, unknown>).arm_id === armId,
  );
  if (!arm) {
    throw new PortfolioProjectionError(
      `Required retrieval arm is missing: ${record.evidence_id}/${populationId}/${armId}`,
    );
  }
  return arm as Record<string, unknown>;
}

export function projectEngineeringSummary(manifest: EngineeringEvidenceManifest) {
  const retrieval = requireRecord(manifest, "performance.slice14c");
  const hybrid = requireVariant(retrieval, "hybrid");
  const reranked = requireVariant(retrieval, "hybrid_rerank");
  const pilot = requireRecord(manifest, "retrieval.slice9hp");
  const pilotC = requireArm(pilot, "full-22", "C");
  const pilotD = requireArm(pilot, "full-22", "D");
  const pilotFullPopulation = requireObject(
    requireObject(pilot.presentation.populations, "retrieval.slice9hp.populations")["full-22"],
    "retrieval.slice9hp.full-22",
  );
  const pilotHumanPopulation = requireObject(
    requireObject(pilot.presentation.populations, "retrieval.slice9hp.populations")["human-16"],
    "retrieval.slice9hp.human-16",
  );

  const generation = requireRecord(manifest, "generation.slice10e");
  const prompt = requirePrompt(generation, "prompt-grounded-v1");
  const promptMetrics = requireObject(prompt.metrics, "prompt-grounded-v1.metrics");
  const generationProvenance = requireObject(generation.provenance.fields, "generation.slice10e.provenance");
  if (
    generationProvenance.same_model_self_judge !== true ||
    generationProvenance.same_endpoint_as_generator !== true
  ) {
    throw new PortfolioProjectionError(
      "Required same-model evaluation limitation is missing.",
    );
  }
  const generationCounts = requireRecord(manifest, "generation.grounding-and-external-boundary");
  const citationMembership = requireFact(generationCounts, "membership");

  const capacity = requireRecord(manifest, "capacity.large-source-envelope");
  const release = requireRecord(manifest, "release.verification");
  const runtime = requireRecord(manifest, "runtime.compute-portability");
  const currentProfiles = requireFact(runtime, "current-18c-profiles");
  const retrievalRationale = requireFact(
    requireRecord(manifest, "product.current-configuration"),
    "retrieval-rationale",
  );
  const decisions = requireRecord(manifest, "conversation.decision-history");
  const learnedRouter = requireFact(decisions, "01b");
  const shippedActions = requireFact(decisions, "01c");
  const recovery = requireRecord(manifest, "recovery.slice12c");
  const security = requireRecord(manifest, "security.slice13b");
  const levelC = requireRecord(manifest, "performance.slice14-level-c");
  const levelCMetrics = requireObject(levelC.presentation.metrics, "performance.slice14-level-c.metrics");
  const levelCEndToEnd = requireNestedMetric(
    levelCMetrics,
    "",
    "end_to_end_p50",
    "level-c",
  );
  const securityPrimary = requireObject(security.presentation.primary, "security.slice13b.primary");
  if (
    typeof learnedRouter.claim !== "string" ||
    typeof shippedActions.claim !== "string" ||
    typeof securityPrimary.interpretation !== "string" ||
    typeof recovery.presentation.efficacy_evidence !== "string" ||
    typeof recovery.presentation.product_recovery !== "string"
  ) {
    throw new PortfolioProjectionError("Required product-decision evidence is incomplete.");
  }
  const fullOrderNote = String(pilotFullPopulation.ndcg_order_note ?? "");
  const humanOrderNote = String(pilotHumanPopulation.ndcg_order_note ?? "");
  if (!fullOrderNote.includes("D > C") || !humanOrderNote.includes("C > D")) {
    throw new PortfolioProjectionError(
      "Required dense-pilot sensitivity evidence is missing.",
    );
  }

  return {
    evidence: {
      retrievalId: retrieval.evidence_id,
      pilotId: pilot.evidence_id,
      generationId: generation.evidence_id,
      generationCountsId: generationCounts.evidence_id,
      citationId: generationCounts.evidence_id,
      capacityId: capacity.evidence_id,
      releaseId: release.evidence_id,
      runtimeId: runtime.evidence_id,
      configId: "product.current-configuration",
      decisionsId: decisions.evidence_id,
      recoveryId: recovery.evidence_id,
      securityId: security.evidence_id,
    },
    retrieval: {
      hybridQuality: requireNestedMetric(hybrid, "quality", "ndcg_at_10", "hybrid"),
      hybridLatency: requireNestedMetric(hybrid, "latency", "retrieval_p50", "hybrid"),
      rerankedQuality: requireNestedMetric(reranked, "quality", "ndcg_at_10", "hybrid_rerank"),
      rerankedLatency: requireNestedMetric(reranked, "latency", "retrieval_p50", "hybrid_rerank"),
      densePilotC: requireNestedMetric(pilotC, "metrics", "ndcg_at_10", "pilot/C"),
      densePilotD: requireNestedMetric(pilotD, "metrics", "ndcg_at_10", "pilot/D"),
      densePilotOrderingChanged: true,
      rationaleAvailable: Boolean(retrievalRationale.claim),
    },
    generation: {
      answered: requireFactMetric(generation, "development-counts", "answered"),
      population: requireFactMetric(generation, "development-counts", "population"),
      failures: requireFactMetric(generation, "development-counts", "generation-failures"),
      grade2Hits: requireFactMetric(generation, "development-counts", "grade2-hit-count"),
      grade2Eligible: requireFactMetric(generation, "development-counts", "grade2-eligible-count"),
      answerRate: requireNestedMetric(promptMetrics, "", "answer_rate", "generation/prompt-grounded-v1"),
      failureRate: requireNestedMetric(promptMetrics, "", "generation_failed_rate", "generation/prompt-grounded-v1"),
      grade2Rate: requireNestedMetric(promptMetrics, "", "grade2_citation_hit_rate", "generation/prompt-grounded-v1"),
      invalidCitationRate: requireNestedMetric(promptMetrics, "", "citation_invalid_rate", "generation/prompt-grounded-v1"),
      noInvalidCitations: requireNestedMetric(promptMetrics, "", "citation_invalid_rate", "generation/prompt-grounded-v1").value === 0,
      selfJudgeIsSameModelAndEndpoint: true,
      citationMembershipClaim: String(citationMembership.claim ?? ""),
    },
    capacity: {
      pdfLimit: requireFactMetric(capacity, "product-limit", "pdf-limit"),
      threshold: requireFactMetric(capacity, "product-limit", "large-pdf-path-threshold"),
    },
    images: {
      current: requireFactMetric(release, "current-cpu-image", "image-bytes"),
      original: requireFactMetric(release, "historical-image-optimization", "baseline-image-bytes"),
      optimized: requireFactMetric(release, "historical-image-optimization", "optimized-image-bytes"),
      reduction: requireFactMetric(release, "historical-image-optimization", "image-reduction"),
    },
    runtime: {
      currentProfilesClaim: String(currentProfiles.claim ?? ""),
      currentImageFactId: "current-cpu-image",
    },
    decisions: {
      recoveryStatus: String(recovery.presentation.product_recovery ?? ""),
      recoveryEfficacy: String(recovery.presentation.efficacy_evidence ?? ""),
    },
    levelC: {
      endToEndP50: levelCEndToEnd,
      generationP50: requireNestedMetric(levelCMetrics, "", "generation_p50", "level-c"),
      populationLabel: String(levelCEndToEnd.population?.label ?? levelC.claim_scope),
    },
  };
}
