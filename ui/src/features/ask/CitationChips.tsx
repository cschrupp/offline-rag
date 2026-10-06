import type { WorkspaceCitation } from "../../api/types";

type Props = {
  citations: WorkspaceCitation[];
  selectedEvidenceUnitId: string | null;
  onSelect: (citation: WorkspaceCitation) => void;
};

function chipLabel(citation: WorkspaceCitation, index: number): string {
  const page =
    citation.page_start != null ? ` · p. ${citation.page_start}` : "";
  return `${index + 1} · ${citation.source_display_name}${page}`;
}

export function CitationChips({
  citations,
  selectedEvidenceUnitId,
  onSelect,
}: Props) {
  if (citations.length === 0) return null;
  return (
    <div className="citation-chips">
      <p className="muted" style={{ margin: 0 }}>
        Evidence used
      </p>
      <ul className="row citation-chip-row" aria-label="Evidence used">
        {citations.map((citation, index) => {
          const selected =
            citation.evidence_unit_id === selectedEvidenceUnitId;
          return (
            <li key={citation.evidence_unit_id}>
              <button
                type="button"
                className={
                  selected
                    ? "citation-chip citation-chip-active"
                    : "citation-chip"
                }
                aria-pressed={selected}
                onClick={() => onSelect(citation)}
              >
                {chipLabel(citation, index)}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
