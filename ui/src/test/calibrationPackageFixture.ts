import type { GoldTrainingCalibrationPackage } from "../features/goldLab/types";

const source = (chunkId: string, text: string) => ({
  chunk_id: chunkId,
  document_id: "doc_1",
  document_title: "Ops Manual",
  source_name: "ops.pdf",
  section_path: ["Start"],
  page_start: 1,
  page_end: 1,
  line_start: 1,
  line_end: 2,
  content_type: "text/plain",
  text,
});

export function trainingPackageFixture(
  overrides: Partial<GoldTrainingCalibrationPackage> = {},
): GoldTrainingCalibrationPackage {
  const base: GoldTrainingCalibrationPackage = {
    schema_version: "offline-rag-gold-lab-training-calibration-package-v1",
    campaign_id: "camp_1",
    dataset_id: "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    registration: {
      dataset_id:
        "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      project_id: "proj_1",
      campaign_id: "camp_1",
      project_type: "benchmark",
      workspace_id: "ws_1",
      snapshot_id: "snap_1",
      chunk_set_id: "chunkset_1",
      corpus_id: "corpus_1",
      corpus_name: "Ops Corpus",
      baseline_authoring_run_id: "run_1",
      baseline_sha256: "b".repeat(64),
      projection_sha256: "c".repeat(64),
      selection_policy_id: "selpol_1",
      selection_policy_fingerprint: "d".repeat(64),
      exported_case_ids: ["case_accept"],
      registered_at: "2026-03-03T00:00:00Z",
    },
    registered_dataset: {
      schema_version: "offline-rag-gold-v1",
      dataset_id:
        "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      chunk_set_id: "chunkset_1",
      corpus_id: "corpus_1",
      corpus_name: "Ops Corpus",
      cases: [
        {
          case_id: "case_accept",
          query: "What pressure?",
          category: "ops",
          tags: ["pump"],
          judgments: [{ chunk_id: "chunk_a", relevance: 2 }],
        },
      ],
    },
    adjudication: {
      projection_sha256: "c".repeat(64),
      cases: [
        {
          case_id: "case_accept",
          qc_disposition: "accept",
          proposed_query: "What pressure?",
          proposed_category: "ops",
          proposed_tags: ["pump"],
          effective_query: "What pressure?",
          effective_category: "ops",
          effective_tags: ["pump"],
          question_source: source("chunk_a", "Pump pressure must remain stable."),
          candidates: [
            {
              chunk_id: "chunk_a",
              source: source("chunk_a", "Pump pressure must remain stable."),
            },
            {
              chunk_id: "chunk_b",
              source: source("chunk_b", "Unrelated cooling note."),
            },
          ],
          relevance_judgments: [
            { chunk_id: "chunk_a", relevance: 2 },
            { chunk_id: "chunk_b", relevance: 0 },
          ],
        },
        {
          case_id: "case_reject",
          qc_disposition: "reject",
          proposed_query: "Should this be rejected?",
          proposed_category: "ops",
          proposed_tags: ["noise"],
          effective_query: null,
          effective_category: null,
          effective_tags: [],
          question_source: source("chunk_a", "Pump pressure must remain stable."),
          candidates: [
            {
              chunk_id: "chunk_a",
              source: source("chunk_a", "Pump pressure must remain stable."),
            },
          ],
          relevance_judgments: [],
        },
      ],
    },
  };
  return { ...base, ...overrides };
}
