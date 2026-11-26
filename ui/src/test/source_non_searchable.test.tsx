import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { validateSourceListResponse } from "../api/sourceListValidation";
import { SourceRail } from "../features/ask/SourceRail";
import { source } from "./mockApi";

it("retains a published OCR-only source and explains why it is not searchable", () => {
  const highrise = {
    ...source({ source_id: "src_highrise", display_name: "Highrise.pdf" }),
    non_searchable_reason: "ocr_required",
  };
  const { sources } = validateSourceListResponse(
    { workspace_id: "ws_rich", revision: 20, sources: [highrise] },
    "ws_rich",
  );
  render(
    <SourceRail
      sources={sources}
      selectedSourceIds={["src_highrise"]}
      limits={null}
      capacityLoading={false}
      capacityError={false}
      sourcePhase="ready"
      sourcesError={null}
      recordedSourceCount={1}
      usedBytes={1024}
      addDisabled={false}
      existingSourceActionsDisabled={false}
      selectionDisabled={false}
      onRetrySources={vi.fn()}
      onToggle={vi.fn()}
      onSelectAll={vi.fn()}
      onAdd={vi.fn()}
      onPreview={vi.fn()}
      onRename={vi.fn()}
      onReplace={vi.fn()}
      onRemove={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "Highrise.pdf" })).toBeVisible();
  expect(screen.getByText("Not searchable · No extractable text (OCR required)")).toBeVisible();
});
