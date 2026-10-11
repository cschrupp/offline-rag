import type {
  GoldTrainingCalibrationPackage,
  TrainingPackageAdjudicationCase,
  TrainingPackageRegisteredCase,
} from "../types";
import type {
  BlindEvidenceSelectExercise,
  BlindQuestionCheckExercise,
  BlindRelevanceRecallExercise,
  BlindScenarioExercise,
  CompileIssue,
  EvidenceSelectAuthority,
  QuestionCheckAuthority,
  RelevanceRecallAuthority,
  ScenarioAuthority,
  TrainingAuthority,
  TrainingCompileResult,
  TrainingTemplateId,
} from "./types";

function tagsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((value, index) => value === right[index]);
}

export function exerciseId(
  datasetId: string,
  caseId: string,
  templateId: TrainingTemplateId,
): string {
  return `goldex_${datasetId}_${caseId}_${templateId}_v1`;
}

function adjudicationMap(
  adj: TrainingPackageAdjudicationCase,
): Map<string, 0 | 1 | 2> | null {
  if (!adj.candidates.length) return null;
  const ids = adj.candidates.map((c) => c.chunk_id);
  if (new Set(ids).size !== ids.length) return null;
  const map = new Map<string, 0 | 1 | 2>();
  for (const judgment of adj.relevance_judgments) {
    if (map.has(judgment.chunk_id)) return null;
    map.set(judgment.chunk_id, judgment.relevance);
  }
  if (map.size !== ids.length) return null;
  for (const id of ids) {
    if (!map.has(id)) return null;
  }
  return map;
}

function issue(
  caseId: string,
  templateId: TrainingTemplateId,
  reason: string,
): CompileIssue {
  return { caseId, templateId, reason };
}

function compileEvidenceSelect(
  pkg: GoldTrainingCalibrationPackage,
  adj: TrainingPackageAdjudicationCase,
  registered: TrainingPackageRegisteredCase | undefined,
  issues: CompileIssue[],
): {
  blind: BlindEvidenceSelectExercise;
  authority: EvidenceSelectAuthority;
} | null {
  const templateId: TrainingTemplateId = "evidence_select";
  if (!adj.effective_query) {
    issues.push(issue(adj.case_id, templateId, "missing effective_query"));
    return null;
  }
  const map = adjudicationMap(adj);
  if (!map) {
    issues.push(
      issue(adj.case_id, templateId, "incoherent adjudication relevance map"),
    );
    return null;
  }
  if (!registered) {
    issues.push(
      issue(adj.case_id, templateId, "missing registered dataset case"),
    );
    return null;
  }
  if (registered.query !== adj.effective_query) {
    issues.push(issue(adj.case_id, templateId, "query mismatch"));
    return null;
  }
  if (registered.category !== adj.effective_category) {
    issues.push(issue(adj.case_id, templateId, "category mismatch"));
    return null;
  }
  if (!tagsEqual(registered.tags, adj.effective_tags)) {
    issues.push(issue(adj.case_id, templateId, "tags mismatch"));
    return null;
  }
  const projectedPositives = new Map<string, 1 | 2>();
  for (const [chunkId, grade] of map) {
    if (grade >= 1) projectedPositives.set(chunkId, grade as 1 | 2);
  }
  const registeredPositives = new Map(
    registered.judgments.map((j) => [j.chunk_id, j.relevance] as const),
  );
  if (projectedPositives.size !== registeredPositives.size) {
    issues.push(issue(adj.case_id, templateId, "positive set size mismatch"));
    return null;
  }
  for (const [chunkId, grade] of projectedPositives) {
    if (registeredPositives.get(chunkId) !== grade) {
      issues.push(issue(adj.case_id, templateId, "positive set mismatch"));
      return null;
    }
  }

  const id = exerciseId(pkg.dataset_id, adj.case_id, templateId);
  return {
    blind: {
      kind: "evidence_select",
      exerciseId: id,
      caseId: adj.case_id,
      query: adj.effective_query,
      category: adj.effective_category,
      tags: [...adj.effective_tags],
      candidates: adj.candidates.map((c) => ({
        chunkId: c.chunk_id,
        source: c.source,
      })),
    },
    authority: {
      exerciseId: id,
      caseId: adj.case_id,
      positiveChunkIds: [...projectedPositives.keys()],
      relevanceByChunkId: Object.fromEntries(map) as Record<string, 0 | 1 | 2>,
    },
  };
}

function compileRelevanceRecall(
  pkg: GoldTrainingCalibrationPackage,
  adj: TrainingPackageAdjudicationCase,
  issues: CompileIssue[],
): {
  blind: BlindRelevanceRecallExercise;
  authority: RelevanceRecallAuthority;
} | null {
  const templateId: TrainingTemplateId = "relevance_recall";
  if (!adj.effective_query) {
    issues.push(issue(adj.case_id, templateId, "missing effective_query"));
    return null;
  }
  const map = adjudicationMap(adj);
  if (!map) {
    issues.push(
      issue(adj.case_id, templateId, "incoherent adjudication relevance map"),
    );
    return null;
  }
  const id = exerciseId(pkg.dataset_id, adj.case_id, templateId);
  return {
    blind: {
      kind: "relevance_recall",
      exerciseId: id,
      caseId: adj.case_id,
      query: adj.effective_query,
      category: adj.effective_category,
      tags: [...adj.effective_tags],
      steps: adj.candidates.map((c) => ({
        stepId: `${id}::${c.chunk_id}`,
        candidateChunkId: c.chunk_id,
        source: c.source,
      })),
    },
    authority: {
      exerciseId: id,
      caseId: adj.case_id,
      relevanceByChunkId: Object.fromEntries(map) as Record<string, 0 | 1 | 2>,
    },
  };
}

function compileQuestionCheck(
  pkg: GoldTrainingCalibrationPackage,
  adj: TrainingPackageAdjudicationCase,
  issues: CompileIssue[],
): {
  blind: BlindQuestionCheckExercise;
  authority: QuestionCheckAuthority;
} | null {
  const templateId: TrainingTemplateId = "question_check";
  if (adj.question_source === null) {
    issues.push(
      issue(
        adj.case_id,
        templateId,
        "authoritative historical source context is unavailable",
      ),
    );
    return null;
  }
  const id = exerciseId(pkg.dataset_id, adj.case_id, templateId);
  return {
    blind: {
      kind: "question_check",
      exerciseId: id,
      caseId: adj.case_id,
      proposedQuery: adj.proposed_query,
      proposedCategory: adj.proposed_category,
      proposedTags: [...adj.proposed_tags],
      questionSource: adj.question_source,
    },
    authority: {
      exerciseId: id,
      caseId: adj.case_id,
      disposition: adj.qc_disposition,
      effectiveQuery: adj.effective_query,
      effectiveCategory: adj.effective_category,
      effectiveTags: [...adj.effective_tags],
    },
  };
}

function compileScenario(
  pkg: GoldTrainingCalibrationPackage,
  adj: TrainingPackageAdjudicationCase,
  issues: CompileIssue[],
): {
  blind: BlindScenarioExercise;
  authority: ScenarioAuthority;
} | null {
  const templateId: TrainingTemplateId = "scenario_relevance_map";
  if (!adj.effective_query) {
    issues.push(issue(adj.case_id, templateId, "missing effective_query"));
    return null;
  }
  const map = adjudicationMap(adj);
  if (!map) {
    issues.push(
      issue(adj.case_id, templateId, "incoherent adjudication relevance map"),
    );
    return null;
  }
  for (const candidate of adj.candidates) {
    if (!candidate.source || typeof candidate.source.text !== "string") {
      issues.push(issue(adj.case_id, templateId, "missing candidate source"));
      return null;
    }
  }
  const id = exerciseId(pkg.dataset_id, adj.case_id, templateId);
  return {
    blind: {
      kind: "scenario_relevance_map",
      exerciseId: id,
      caseId: adj.case_id,
      scenarioStem: adj.effective_query,
      category: adj.effective_category,
      tags: [...adj.effective_tags],
      candidates: adj.candidates.map((c) => ({
        chunkId: c.chunk_id,
        source: c.source,
      })),
    },
    authority: {
      exerciseId: id,
      caseId: adj.case_id,
      relevanceByChunkId: Object.fromEntries(map) as Record<string, 0 | 1 | 2>,
    },
  };
}

/** Deterministic package → learner exercises. Package order preserved. */
export function compileTrainingPackage(
  pkg: GoldTrainingCalibrationPackage,
): TrainingCompileResult {
  const registeredById = new Map(
    pkg.registered_dataset.cases.map((row) => [row.case_id, row]),
  );
  const drills: TrainingCompileResult["drills"] = [];
  const scenarios: BlindScenarioExercise[] = [];
  const authorityByExerciseId = new Map<string, TrainingAuthority>();
  const issues: CompileIssue[] = [];

  for (const adj of pkg.adjudication.cases) {
    const qc = compileQuestionCheck(pkg, adj, issues);
    if (qc) {
      drills.push(qc.blind);
      authorityByExerciseId.set(qc.blind.exerciseId, qc.authority);
    }

    if (adj.qc_disposition === "reject") {
      continue;
    }

    const evidence = compileEvidenceSelect(
      pkg,
      adj,
      registeredById.get(adj.case_id),
      issues,
    );
    if (evidence) {
      drills.push(evidence.blind);
      authorityByExerciseId.set(evidence.blind.exerciseId, evidence.authority);
    }

    const recall = compileRelevanceRecall(pkg, adj, issues);
    if (recall) {
      drills.push(recall.blind);
      authorityByExerciseId.set(recall.blind.exerciseId, recall.authority);
    }

    const scenario = compileScenario(pkg, adj, issues);
    if (scenario) {
      scenarios.push(scenario.blind);
      authorityByExerciseId.set(
        scenario.blind.exerciseId,
        scenario.authority,
      );
    }
  }

  // Deterministic drill order: case package order × template order
  // (question_check, evidence_select, relevance_recall) already interleaved
  // by case iteration above. Re-sort by case index then template rank for
  // stable identity across recompiles if push order changes.
  const caseOrder = new Map(
    pkg.adjudication.cases.map((row, index) => [row.case_id, index]),
  );
  const templateRank: Record<string, number> = {
    question_check: 0,
    evidence_select: 1,
    relevance_recall: 2,
  };
  drills.sort((a, b) => {
    const caseDelta =
      (caseOrder.get(a.caseId) ?? 0) - (caseOrder.get(b.caseId) ?? 0);
    if (caseDelta !== 0) return caseDelta;
    return (templateRank[a.kind] ?? 99) - (templateRank[b.kind] ?? 99);
  });
  scenarios.sort(
    (a, b) => (caseOrder.get(a.caseId) ?? 0) - (caseOrder.get(b.caseId) ?? 0),
  );

  return {
    datasetId: pkg.dataset_id,
    projectionSha256: pkg.registration.projection_sha256,
    drills,
    scenarios,
    authorityByExerciseId,
    issues,
  };
}
