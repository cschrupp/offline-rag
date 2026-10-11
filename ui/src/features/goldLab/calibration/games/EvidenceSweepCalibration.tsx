import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { GoldRelevance } from "../../types";
import type { AbsoluteAuthority, BlindAbsoluteItem } from "../types";

const OPTIONS: Array<{ value: GoldRelevance; label: string }> = [
  { value: 0, label: "Irrelevant" },
  { value: 1, label: "Supporting evidence" },
  { value: 2, label: "Direct evidence" },
];

export type SweepCardState = {
  item: BlindAbsoluteItem;
  /** Present only after this card's local commit (structural blindness). */
  authority: AbsoluteAuthority | undefined;
  draft: GoldRelevance | null;
  committed: boolean;
};

type Props = {
  cards: SweepCardState[];
  onDraftChange: (itemId: string, value: GoldRelevance) => void;
  onCommit: (itemId: string) => void;
  onNextBatch: () => void;
  batchComplete: boolean;
  nextBatchDisabled: boolean;
  finishLabel?: string;
};

export function EvidenceSweepCalibration({
  cards,
  onDraftChange,
  onCommit,
  onNextBatch,
  batchComplete,
  nextBatchDisabled,
  finishLabel = "Next batch",
}: Props) {
  return (
    <div className="stack gold-lab-game" data-testid="calibration-evidence-sweep">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Evidence Sweep calibration</h2>
        <p className="muted" style={{ margin: 0 }}>
          Up to five candidates. Each local commit is independent. No Gold
          mutation.
        </p>
      </header>

      <ol className="gold-lab-evidence-sweep-list">
        {cards.map((card, index) => (
          <li
            key={card.item.itemId}
            className="gold-lab-evidence-sweep-card"
            data-item-id={card.item.itemId}
          >
            <h3>Candidate {index + 1}</h3>
            <section aria-labelledby={`cal-es-q-${card.item.itemId}`}>
              <h4 id={`cal-es-q-${card.item.itemId}`}>Effective query</h4>
              <p>{card.item.query}</p>
            </section>
            <GoldSourceContextView
              source={card.item.source}
              heading="Candidate source"
              headingId={`cal-es-src-${card.item.itemId}`}
            />
            <fieldset
              className="gold-lab-fieldset"
              disabled={card.committed}
            >
              <legend>Your local relevance</legend>
              <div
                className="row gold-lab-radio-row"
                role="radiogroup"
                aria-label={`Local relevance for candidate ${index + 1}`}
              >
                {OPTIONS.map((option) => (
                  <label key={option.value} className="gold-lab-radio">
                    <input
                      type="radio"
                      name={`cal-es-${card.item.itemId}`}
                      value={option.value}
                      checked={card.draft === option.value}
                      disabled={card.committed}
                      onChange={() =>
                        onDraftChange(card.item.itemId, option.value)
                      }
                    />
                    <span>
                      {option.value} — {option.label}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            {!card.committed ? (
              <Button
                onClick={() => onCommit(card.item.itemId)}
                disabled={card.draft === null}
              >
                Commit local response
              </Button>
            ) : card.authority ? (
              <section
                className="gold-lab-calibration-reveal"
                aria-live="polite"
                data-testid={`calibration-reveal-${card.item.itemId}`}
              >
                <p>Your response: {card.draft}</p>
                <p>
                  Registration-time relevance: {card.authority.relevance}
                  {card.draft === card.authority.relevance
                    ? " — match"
                    : " — mismatch"}
                </p>
              </section>
            ) : null}
          </li>
        ))}
      </ol>

      {batchComplete ? (
        <Button onClick={onNextBatch} disabled={nextBatchDisabled}>
          {finishLabel}
        </Button>
      ) : null}
    </div>
  );
}
