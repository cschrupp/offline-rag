import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { WorkspaceCitation, WorkspaceQueryResponse } from "../api/types";
import { ClaimAnswer } from "../features/ask/ClaimAnswer";
import { abstentionCopy } from "../features/ask/abstentionCopy";
import { loadAskHistory } from "../features/ask/askHistory";

const citations: WorkspaceCitation[] = [
  {
    evidence_unit_id: "eu_b",
    document_id: "doc_1",
    source_chunk_id: "chunk_b",
    kind: "parent",
    section_path: ["Safety"],
    page_start: 3,
    page_end: 3,
    line_start: null,
    line_end: null,
    clipped: false,
    source_id: "src_1",
    source_version: 1,
    source_display_name: "Guide.pdf",
    citation_ref: "c1",
    excerpt: "First excerpt plain",
    excerpt_clipped: false,
  },
  {
    evidence_unit_id: "eu_a",
    document_id: "doc_1",
    source_chunk_id: "chunk_a",
    kind: "parent",
    section_path: [],
    page_start: null,
    page_end: null,
    line_start: null,
    line_end: null,
    clipped: false,
    source_id: "src_1",
    source_version: 1,
    source_display_name: "Guide.pdf",
    citation_ref: "c2",
    excerpt: "Second excerpt",
    excerpt_clipped: true,
  },
];

function baseCitation(
  overrides: Partial<WorkspaceCitation> & Pick<WorkspaceCitation, "citation_ref" | "evidence_unit_id">,
): WorkspaceCitation {
  return {
    document_id: "doc_1",
    source_chunk_id: "chunk_1",
    kind: "parent",
    section_path: ["Safety"],
    page_start: 1,
    page_end: 1,
    line_start: null,
    line_end: null,
    clipped: false,
    source_id: "src_1",
    source_version: 1,
    source_display_name: "Guide.pdf",
    excerpt: "excerpt",
    excerpt_clipped: false,
    ...overrides,
  };
}

function answeredResponse(
  overrides: Partial<WorkspaceQueryResponse> = {},
): WorkspaceQueryResponse {
  const c1 = baseCitation({ citation_ref: "c1", evidence_unit_id: "eu_1" });
  const c2 = baseCitation({ citation_ref: "c2", evidence_unit_id: "eu_2" });
  const blocks = [
    { text: "Claim A", citation_refs: ["c1", "c2"] },
    { text: "Claim B", citation_refs: ["c2"] },
  ];
  return {
    workspace_id: "ws_x",
    workspace_revision: 1,
    snapshot_id: "snap",
    product_mode_id: "grounded_v1",
    trace_id: "tr",
    status: "answered",
    answer: "Claim A\n\nClaim B",
    answer_blocks: blocks,
    citations: [c1, c2],
    abstention_reason: null,
    ...overrides,
  };
}

function historyPayload(response: WorkspaceQueryResponse) {
  return [
    {
      entryId: "e1",
      askedAt: "2026-01-01T00:00:00Z",
      question: "q",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["Guide.pdf"],
      response,
    },
  ];
}

describe("Slice 16D-B2 claim citations", () => {
  it("renders answer_blocks with app-owned marker numbers", () => {
    render(
      <ClaimAnswer
        blocks={[
          { text: "Claim one.", citation_refs: ["c1", "c2"] },
          { text: "Claim two.", citation_refs: ["c2"] },
        ]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={vi.fn()}
      />,
    );

    expect(screen.getByText("Claim one.")).toBeInTheDocument();
    expect(screen.getByText("Claim two.")).toBeInTheDocument();
    expect(screen.queryByText(/Evidence used/i)).toBeNull();
    expect(screen.queryByText(/eu_/i)).toBeNull();
  });

  it("A/D: hover and keyboard focus expose the evidence card", () => {
    render(
      <ClaimAnswer
        blocks={[{ text: "Claim one.", citation_refs: ["c1"] }]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={vi.fn()}
      />,
    );
    const marker = screen.getByRole("button", {
      name: /Citation 1: Guide\.pdf/i,
    });

    fireEvent.mouseEnter(marker);
    expect(screen.getByText(/First excerpt plain/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Open evidence/i }),
    ).toBeInTheDocument();

    const root = marker.closest(".claim-answer");
    expect(root).not.toBeNull();
    fireEvent.mouseLeave(root as Element, { relatedTarget: document.body });
    expect(screen.queryByRole("button", { name: /Open evidence/i })).toBeNull();

    fireEvent.focus(marker);
    expect(screen.getByText(/First excerpt plain/i)).toBeInTheDocument();
  });

  it("B/C: pointer can move onto Open evidence and activate it", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ClaimAnswer
        blocks={[{ text: "Claim one.", citation_refs: ["c1"] }]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={onSelect}
      />,
    );
    const marker = screen.getByRole("button", {
      name: /Citation 1: Guide\.pdf/i,
    });

    fireEvent.mouseEnter(marker);
    const open = screen.getByRole("button", { name: /Open evidence/i });
    // Transition pointer into the card control without unmounting.
    fireEvent.mouseLeave(marker, { relatedTarget: open });
    fireEvent.mouseEnter(open.parentElement as Element);
    expect(screen.getByRole("button", { name: /Open evidence/i })).toBeInTheDocument();
    await user.click(open);
    expect(onSelect).toHaveBeenCalledWith(citations[0]);
  });

  it("E: keyboard can reach and activate Open evidence", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ClaimAnswer
        blocks={[{ text: "Claim one.", citation_refs: ["c1"] }]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={onSelect}
      />,
    );
    const marker = screen.getByRole("button", {
      name: /Citation 1: Guide\.pdf/i,
    });
    marker.focus();
    fireEvent.focus(marker);
    expect(screen.getByRole("button", { name: /Open evidence/i })).toBeInTheDocument();

    await user.tab();
    expect(screen.getByRole("button", { name: /Open evidence/i })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(citations[0]);
  });

  it("F/G: marker Enter/Space and click select exact citation", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ClaimAnswer
        blocks={[{ text: "Claim one.", citation_refs: ["c1"] }]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={onSelect}
      />,
    );
    const marker = screen.getByRole("button", {
      name: /Citation 1: Guide\.pdf/i,
    });

    marker.focus();
    fireEvent.focus(marker);
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(citations[0]);

    onSelect.mockClear();
    marker.focus();
    fireEvent.focus(marker);
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenLastCalledWith(citations[0]);

    onSelect.mockClear();
    await user.click(marker);
    expect(onSelect).toHaveBeenCalledWith(citations[0]);
  });

  it("maps structured abstention copy by reason", () => {
    expect(abstentionCopy("no_evidence")).toMatch(/usable evidence/i);
    expect(abstentionCopy("insufficient_support")).toMatch(/not strong enough/i);
    expect(abstentionCopy("conflicting_evidence")).toMatch(/conflicts materially/i);
    expect(abstentionCopy("model_declined")).toMatch(/did not provide an answer/i);
  });

  it("retains valid shared-citation history (block1 c1,c2; block2 c2)", () => {
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_ok",
      JSON.stringify(historyPayload(answeredResponse())),
    );
    const loaded = loadAskHistory("ws_ok");
    expect(loaded).toHaveLength(1);
    expect(loaded[0].response.answer_blocks[1].citation_refs).toEqual(["c2"]);
  });

  it("rejects dangling block citation_ref c999", () => {
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_dang",
      JSON.stringify(
        historyPayload(
          answeredResponse({
            answer: "Claim A",
            answer_blocks: [{ text: "Claim A", citation_refs: ["c999"] }],
            citations: [
              baseCitation({ citation_ref: "c1", evidence_unit_id: "eu_1" }),
            ],
          }),
        ),
      ),
    );
    expect(loadAskHistory("ws_dang")).toEqual([]);
  });

  it("rejects duplicate citation_ref identities", () => {
    const dup = baseCitation({ citation_ref: "c1", evidence_unit_id: "eu_1" });
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_dup",
      JSON.stringify(
        historyPayload(
          answeredResponse({
            answer: "Claim A",
            answer_blocks: [{ text: "Claim A", citation_refs: ["c1"] }],
            citations: [dup, { ...dup, evidence_unit_id: "eu_other" }],
          }),
        ),
      ),
    );
    expect(loadAskHistory("ws_dup")).toEqual([]);
  });

  it("rejects block with no resolvable citation", () => {
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_empty_refs",
      JSON.stringify(
        historyPayload(
          answeredResponse({
            answer: "Claim A",
            answer_blocks: [{ text: "Claim A", citation_refs: [] }],
            citations: [
              baseCitation({ citation_ref: "c1", evidence_unit_id: "eu_1" }),
            ],
          }),
        ),
      ),
    );
    expect(loadAskHistory("ws_empty_refs")).toEqual([]);
  });

  it("rejects answered answer string not equal to block projection", () => {
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_proj",
      JSON.stringify(
        historyPayload(
          answeredResponse({
            answer: "NOT THE BLOCKS",
          }),
        ),
      ),
    );
    expect(loadAskHistory("ws_proj")).toEqual([]);
  });

  it("rejects invalid standalone abstention reason and ambiguous_request", () => {
    for (const reason of ["ambiguous_request", "made_up_reason", "no_evidence"]) {
      sessionStorage.setItem(
        "seneca.ask-history.v2:ws_abs",
        JSON.stringify(
          historyPayload({
            workspace_id: "ws_x",
            workspace_revision: 1,
            snapshot_id: "snap",
            product_mode_id: "grounded_v1",
            trace_id: "tr",
            status: "model_abstain",
            answer: null,
            answer_blocks: [],
            citations: [],
            abstention_reason: reason,
          }),
        ),
      );
      // no_evidence is invalid under model_abstain; ambiguous/arbitrary rejected.
      expect(loadAskHistory("ws_abs")).toEqual([]);
    }

    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_ie",
      JSON.stringify(
        historyPayload({
          workspace_id: "ws_x",
          workspace_revision: 1,
          snapshot_id: "snap",
          product_mode_id: "grounded_v1",
          trace_id: "tr",
          status: "insufficient_evidence",
          answer: null,
          answer_blocks: [],
          citations: [],
          abstention_reason: "model_declined",
        }),
      ),
    );
    expect(loadAskHistory("ws_ie")).toEqual([]);
  });

  it("fails closed on legacy/malformed history without crashing", () => {
    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_x",
      JSON.stringify([
        {
          entryId: "legacy",
          askedAt: "2026-01-01T00:00:00Z",
          question: "old",
          selectedSourceIds: ["src_1"],
          selectedSourceNames: ["A.pdf"],
          response: {
            workspace_id: "ws_x",
            workspace_revision: 1,
            snapshot_id: "snap",
            product_mode_id: "grounded_v1",
            trace_id: "tr",
            status: "answered",
            answer: "plain",
            citations: [],
          },
        },
      ]),
    );
    expect(loadAskHistory("ws_x")).toEqual([]);
  });
});
