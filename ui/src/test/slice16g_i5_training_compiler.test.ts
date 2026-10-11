import { describe, expect, it } from "vitest";
import {
  compileTrainingPackage,
  exerciseId,
} from "../features/goldLab/training/compiler";
import { trainingPackageFixture } from "./calibrationPackageFixture";

const DATASET_ID =
  "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

describe("16G-I5 training compiler", () => {
  it("compiles accepted/edited drills and QC-only for reject", () => {
    const result = compileTrainingPackage(trainingPackageFixture());
    const kindsByCase = new Map<string, string[]>();
    for (const drill of result.drills) {
      const list = kindsByCase.get(drill.caseId) ?? [];
      list.push(drill.kind);
      kindsByCase.set(drill.caseId, list);
    }
    expect(kindsByCase.get("case_accept")).toEqual([
      "question_check",
      "evidence_select",
      "relevance_recall",
    ]);
    expect(kindsByCase.get("case_reject")).toEqual(["question_check"]);
    expect(result.scenarios.map((s) => s.caseId)).toEqual(["case_accept"]);
    expect(
      result.scenarios.some((s) => s.caseId === "case_reject"),
    ).toBe(false);
  });

  it("preserves package candidate order and deterministic exercise ids", () => {
    const result = compileTrainingPackage(trainingPackageFixture());
    const recall = result.drills.find((d) => d.kind === "relevance_recall");
    expect(recall?.kind).toBe("relevance_recall");
    if (recall?.kind !== "relevance_recall") throw new Error("missing recall");
    expect(recall.steps.map((s) => s.candidateChunkId)).toEqual([
      "chunk_a",
      "chunk_b",
    ]);
    expect(recall.exerciseId).toBe(
      exerciseId(DATASET_ID, "case_accept", "relevance_recall"),
    );
    const again = compileTrainingPackage(trainingPackageFixture());
    expect(again.drills.map((d) => d.exerciseId)).toEqual(
      result.drills.map((d) => d.exerciseId),
    );
    expect(again.scenarios.map((s) => s.exerciseId)).toEqual(
      result.scenarios.map((s) => s.exerciseId),
    );
  });

  it("uses registered positives for Evidence Selection and adjudication zeros as distractors", () => {
    const result = compileTrainingPackage(trainingPackageFixture());
    const evidence = result.drills.find((d) => d.kind === "evidence_select");
    expect(evidence).toBeTruthy();
    const auth = result.authorityByExerciseId.get(evidence!.exerciseId);
    expect(auth?.exerciseId).toBe(evidence!.exerciseId);
    if (!auth || !("positiveChunkIds" in auth)) {
      throw new Error("missing evidence authority");
    }
    expect(auth.positiveChunkIds).toEqual(["chunk_a"]);
    expect(auth.relevanceByChunkId).toEqual({ chunk_a: 2, chunk_b: 0 });
  });

  it("scenario stem equals effective query", () => {
    const result = compileTrainingPackage(trainingPackageFixture());
    expect(result.scenarios[0]?.scenarioStem).toBe("What pressure?");
  });

  it("fail-closes Evidence Selection on dataset/adjudication mismatch", () => {
    const pkg = trainingPackageFixture({
      registered_dataset: {
        ...trainingPackageFixture().registered_dataset,
        cases: [
          {
            case_id: "case_accept",
            query: "Different query?",
            category: "ops",
            tags: ["pump"],
            judgments: [{ chunk_id: "chunk_a", relevance: 2 }],
          },
        ],
      },
    });
    const result = compileTrainingPackage(pkg);
    expect(
      result.drills.some(
        (d) => d.kind === "evidence_select" && d.caseId === "case_accept",
      ),
    ).toBe(false);
    expect(
      result.issues.some(
        (row) =>
          row.templateId === "evidence_select" && row.reason.includes("query"),
      ),
    ).toBe(true);
  });

  it("fail-closes Question Check when question_source is missing", () => {
    const base = trainingPackageFixture();
    const pkg = trainingPackageFixture({
      adjudication: {
        projection_sha256: base.adjudication.projection_sha256,
        cases: base.adjudication.cases.map((row) =>
          row.case_id === "case_reject"
            ? { ...row, question_source: null }
            : row,
        ),
      },
    });
    const result = compileTrainingPackage(pkg);
    expect(
      result.drills.some(
        (d) => d.kind === "question_check" && d.caseId === "case_reject",
      ),
    ).toBe(false);
    expect(
      result.issues.some((row) =>
        row.reason.includes("historical source context is unavailable"),
      ),
    ).toBe(true);
  });

  it("edited effective fields drive learner exercises", () => {
    const pkg = trainingPackageFixture({
      registration: {
        ...trainingPackageFixture().registration,
        exported_case_ids: ["case_edit"],
      },
      registered_dataset: {
        ...trainingPackageFixture().registered_dataset,
        cases: [
          {
            case_id: "case_edit",
            query: "Edited offline RAG question?",
            category: "edited",
            tags: ["edited-tag"],
            judgments: [{ chunk_id: "chunk_a", relevance: 1 }],
          },
        ],
      },
      adjudication: {
        projection_sha256: "c".repeat(64),
        cases: [
          {
            case_id: "case_edit",
            qc_disposition: "edit",
            proposed_query: "Original?",
            proposed_category: "ops",
            proposed_tags: ["pump"],
            effective_query: "Edited offline RAG question?",
            effective_category: "edited",
            effective_tags: ["edited-tag"],
            question_source: trainingPackageFixture().adjudication.cases[0]!
              .question_source,
            candidates: trainingPackageFixture().adjudication.cases[0]!
              .candidates,
            relevance_judgments: [
              { chunk_id: "chunk_a", relevance: 1 },
              { chunk_id: "chunk_b", relevance: 0 },
            ],
          },
        ],
      },
    });
    const result = compileTrainingPackage(pkg);
    const evidence = result.drills.find((d) => d.kind === "evidence_select");
    expect(evidence?.kind === "evidence_select" && evidence.query).toBe(
      "Edited offline RAG question?",
    );
    expect(result.scenarios[0]?.scenarioStem).toBe(
      "Edited offline RAG question?",
    );
  });
});
