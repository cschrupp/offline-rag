import {
  useId,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import type { AnswerBlock, WorkspaceCitation } from "../../api/types";

type Props = {
  blocks: AnswerBlock[];
  citations: WorkspaceCitation[];
  selectedEvidenceUnitId: string | null;
  onSelectCitation: (citation: WorkspaceCitation) => void;
  /** When false, render claim prose without citation markers/cards. */
  citationsVisible?: boolean;
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

function isInside(
  root: HTMLElement | null,
  target: EventTarget | null,
): boolean {
  return (
    root != null && target instanceof Node && root.contains(target)
  );
}

export function ClaimAnswer({
  blocks,
  citations,
  selectedEvidenceUnitId,
  onSelectCitation,
  citationsVisible = true,
}: Props) {
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const cardId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);

  const activeCitation =
    citationsVisible && activeRef != null
      ? citationByRef(citations, activeRef)
      : undefined;

  function openCitation(citation: WorkspaceCitation) {
    setActiveRef(null);
    onSelectCitation(citation);
  }

  function clearIfFocusLeftRegion() {
    // relatedTarget is often null in jsdom / during focus moves; settle first,
    // then clear only if focus is outside the marker+card region.
    queueMicrotask(() => {
      const root = rootRef.current;
      if (!root) return;
      if (isInside(root, document.activeElement)) return;
      setActiveRef(null);
    });
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

  function onRootMouseLeave(event: MouseEvent<HTMLDivElement>) {
    if (isInside(rootRef.current, event.relatedTarget)) return;
    setActiveRef(null);
  }

  function onMarkerBlur(_event: FocusEvent<HTMLButtonElement>) {
    clearIfFocusLeftRegion();
  }

  function onCardBlur(_event: FocusEvent<HTMLDivElement>) {
    clearIfFocusLeftRegion();
  }

  return (
    <div
      ref={rootRef}
      className="claim-answer stack"
      onMouseLeave={onRootMouseLeave}
    >
      {blocks.map((block, blockIndex) => (
        <p key={blockIndex} className="claim-block">
          <span className="claim-block-text">{block.text}</span>
          {citationsVisible
            ? block.citation_refs.map((ref) => {
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
                    onFocus={() => setActiveRef(ref)}
                    onBlur={onMarkerBlur}
                    onClick={(event: MouseEvent<HTMLButtonElement>) => {
                      event.preventDefault();
                      openCitation(citation);
                    }}
                    onKeyDown={(event) => onMarkerKeyDown(event, citation)}
                  >
                    <sup>{n}</sup>
                  </button>
                );
              })
            : null}
        </p>
      ))}

      {activeCitation ? (
        <div
          id={`${cardId}-card`}
          className="claim-evidence-card"
          role="note"
          onMouseEnter={() => setActiveRef(activeCitation.citation_ref)}
          onBlur={onCardBlur}
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
            onClick={() => openCitation(activeCitation)}
          >
            Open evidence →
          </button>
        </div>
      ) : null}
    </div>
  );
}
