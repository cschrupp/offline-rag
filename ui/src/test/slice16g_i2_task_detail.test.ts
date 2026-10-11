import { describe, expect, it } from "vitest";
import {
  validateGoldMutationReceipt,
  validateGoldTaskDetail,
} from "../features/goldLab/api/validation";

const source = {
  chunk_id: "chunk_1",
  document_id: "doc_1",
  document_title: "SOP",
  source_name: "sop.pdf",
  section_path: ["Intro"],
  page_start: 1,
  page_end: 1,
  line_start: null,
  line_end: null,
  content_type: "text/plain",
  text: "Candidate evidence text.",
};

describe("16G-I2 task detail and receipt validation", () => {
  it("binds identity and rejects blindness leaks", () => {
    const detail = {
      task_id: "t1",
      task_kind: "absolute_relevance",
      campaign_id: "camp_1",
      case_id: "case_a",
      active: true,
      state: "pending",
      candidate_chunk_id: "chunk_1",
      effective_query: "How?",
      presentation: {
        kind: "absolute_relevance",
        effective_query: "How?",
        effective_category: null,
        effective_tags: [],
        candidate: source,
      },
      current_result: null,
    };
    expect(
      validateGoldTaskDetail(detail, {
        campaignId: "camp_1",
        taskId: "t1",
        expectedKind: "absolute_relevance",
      }).task_id,
    ).toBe("t1");

    expect(() =>
      validateGoldTaskDetail(
        { ...detail, rank: 3, score: 0.9 },
        { campaignId: "camp_1", taskId: "t1" },
      ),
    ).toThrow(/forbidden scientific enrichment/i);

    expect(() =>
      validateGoldTaskDetail(
        {
          ...detail,
          presentation: {
            ...detail.presentation,
            candidate: { ...source, model_confidence: 0.99 },
          },
        },
        { campaignId: "camp_1", taskId: "t1" },
      ),
    ).toThrow(/forbidden scientific enrichment/i);

    expect(() =>
      validateGoldTaskDetail(
        { ...detail, task_id: "other" },
        { campaignId: "camp_1", taskId: "t1" },
      ),
    ).toThrow(/requested task/i);
  });

  it("fails closed when pending tasks carry prior results", () => {
    expect(() =>
      validateGoldTaskDetail(
        {
          task_id: "t1",
          task_kind: "question_check",
          campaign_id: "camp_1",
          case_id: "case_a",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
          effective_query: null,
          presentation: {
            kind: "question_check",
            proposed_query: "Q?",
            proposed_category: null,
            proposed_tags: [],
            source: null,
          },
          current_result: {
            kind: "question_check",
            decision: "accept",
            effective_query: "Q?",
            effective_category: null,
            effective_tags: [],
          },
        },
        { campaignId: "camp_1", taskId: "t1", expectedKind: "question_check" },
      ),
    ).toThrow(/unexpectedly contained current_result/i);
  });

  it("binds mutation receipts to campaign/task/record_type", () => {
    const receipt = {
      campaign_id: "camp_1",
      record_id: "rec_1",
      judgment_id: "jud_1",
      task_id: "t1",
      record_type: "absolute_relevance",
      sequence: 1,
      created_at: "2026-03-01T00:00:00Z",
      replayed: false,
    };
    expect(
      validateGoldMutationReceipt(receipt, {
        campaignId: "camp_1",
        taskId: "t1",
        expectedRecordType: "absolute_relevance",
      }).replayed,
    ).toBe(false);
    expect(() =>
      validateGoldMutationReceipt(
        { ...receipt, record_type: "question_check" },
        {
          campaignId: "camp_1",
          taskId: "t1",
          expectedRecordType: "absolute_relevance",
        },
      ),
    ).toThrow(/record_type/i);
  });
});
