import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import type { AnswerBlock, WorkspaceCitation } from "../../api/types";

type Props = {
  blocks: AnswerBlock[];
  citations: WorkspaceCitation[];
  selectedEvidenceUnitId: string | null;
  onSelectCitation: (citation: WorkspaceCitation) => void;
};

function citationByRef(
  citations: WorkspaceCitation[],
  ref: string,
): WorkspaceCitation | undefined {
  return citations.find((c) => c.citation_ref === ref);
}

function displayIndex(
  citations: WorkspaceCitation[],
  ref: string,
): number | null {
  const index = citations.findIndex((c) => c.citation_ref === ref);
  return index >= 0 ? index + 1 : null;
}

export function ClaimAnswer({
  blocks,
  citations,
  selectedEvidenceUnitId,
  onSelectCitation,
}: Props) {
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const cardId = useId();
  const cardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onPointerDown(event: Event) {
      if (!cardRef.current) return;
      if (event.target instanceof Node && cardRef.current.contains(event.target)) {
        return;
      }
      // Keep card while focus remains on a marker; blur handlers clear it.
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const activeCitation =
    activeRef != null ? citationByRef(citations, activeRef) : undefined;

  function openCitation(citation: WorkspaceCitation) {
    setActiveRef(null);
    onSelectCitation(citation);
  }

  function onMarkerKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    citation: WorkspaceCitation,
  ) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openCitation(citation);
    }
  }

  return (
    <div className="claim-answer stack">
      {blocks.map((block, blockIndex) => (
        <p key={blockIndex} className="claim-block">
          <span className="claim-block-text">{block.text}</span>
          {block.citation_refs.map((ref) => {
            const citation = citationByRef(citations, ref);
            const n = displayIndex(citations, ref);
            if (!citation || n == null) return null;
            const selected =
              citation.evidence_unit_id === selectedEvidenceUnitId;
            return (
              <button
                key={`${blockIndex}-${ref}`}
                type="button"
                className={
                  selected
                    ? "claim-marker claim-marker-active"
                    : "claim-marker"
                }
                aria-label={`Citation ${n}: ${citation.source_display_name}`}
                aria-describedby={
                  activeRef === ref ? `${cardId}-card` : undefined
                }
                onMouseEnter={() => setActiveRef(ref)}
                onMouseLeave={() =>
                  setActiveRef((current) => (current === ref ? null : current))
                }
                onFocus={() => setActiveRef(ref)}
                onBlur={() =>
                  setActiveRef((current) => (current === ref ? null : current))
                }
                onClick={(event: MouseEvent<HTMLButtonElement>) => {
                  event.preventDefault();
                  openCitation(citation);
                }}
                onKeyDown={(event) => onMarkerKeyDown(event, citation)}
              >
                <sup>{n}</sup>
              </button>
            );
          })}
        </p>
      ))}

      {activeCitation ? (
        <div
          ref={cardRef}
          id={`${cardId}-card`}
          className="claim-evidence-card"
          role="note"
        >
          <p className="claim-evidence-card-title">
            {activeCitation.source_display_name}
            {activeCitation.page_start != null
              ? ` · p. ${activeCitation.page_start}`
              : ""}
          </p>
          {activeCitation.section_path.length > 0 ? (
            <p className="muted claim-evidence-card-section">
              {activeCitation.section_path.join(" / ")}
            </p>
          ) : null}
          <p className="claim-evidence-card-excerpt">
            {activeCitation.excerpt}
            {activeCitation.excerpt_clipped ? "…" : ""}
          </p>
          <button
            type="button"
            className="claim-evidence-open"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => openCitation(activeCitation)}
          >
            Open evidence →
          </button>
        </div>
      ) : null}
    </div>
  );
}
