import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { WorkspaceCitation } from "../api/types";
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

describe("Slice 16D-B2 claim citations", () => {
  it("renders answer_blocks with app-owned marker numbers and card a11y paths", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ClaimAnswer
        blocks={[
          { text: "Claim one.", citation_refs: ["c1", "c2"] },
          { text: "Claim two.", citation_refs: ["c2"] },
        ]}
        citations={citations}
        selectedEvidenceUnitId={null}
        onSelectCitation={onSelect}
      />,
    );

    expect(screen.getByText("Claim one.")).toBeInTheDocument();
    expect(screen.getByText("Claim two.")).toBeInTheDocument();
    expect(screen.queryByText(/Evidence used/i)).toBeNull();
    expect(screen.queryByText(/eu_/i)).toBeNull();

    const marker1 = screen.getByRole("button", { name: /Citation 1: Guide\.pdf/i });
    const marker2 = screen.getAllByRole("button", {
      name: /Citation 2: Guide\.pdf/i,
    })[0];

    await user.hover(marker1);
    expect(screen.getByText(/First excerpt plain/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open evidence/i })).toBeInTheDocument();

    await user.hover(marker2);
    expect(screen.getByText(/Second excerpt/i)).toBeInTheDocument();

    await user.click(marker1);
    expect(onSelect).toHaveBeenCalledWith(citations[0]);
  });

  it("maps structured abstention copy by reason", () => {
    expect(abstentionCopy("no_evidence")).toMatch(/usable evidence/i);
    expect(abstentionCopy("insufficient_support")).toMatch(/not strong enough/i);
    expect(abstentionCopy("conflicting_evidence")).toMatch(/conflicts materially/i);
    expect(abstentionCopy("model_declined")).toMatch(/did not provide an answer/i);
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
