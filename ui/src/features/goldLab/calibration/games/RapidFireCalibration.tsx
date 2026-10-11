import { useEffect, useState } from "react";
import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { GoldRelevance } from "../../types";
import type { AbsoluteAuthority, BlindAbsoluteItem } from "../types";

const OPTIONS: Array<{ value: GoldRelevance; label: string; shortcut: string }> =
  [
    { value: 0, label: "Irrelevant", shortcut: "0" },
    { value: 1, label: "Supporting evidence", shortcut: "1" },
    { value: 2, label: "Direct evidence", shortcut: "2" },
  ];

type Props = {
  item: BlindAbsoluteItem;
  authority: AbsoluteAuthority | undefined;
  committed: boolean;
  draft: GoldRelevance | null;
  revealRelevance: GoldRelevance | null;
  onDraftChange: (value: GoldRelevance) => void;
  onCommit: () => void;
  onNext: () => void;
  nextLabel?: string;
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

export function RapidFireCalibration({
  item,
  authority,
  committed,
  draft,
  revealRelevance,
  onDraftChange,
  onCommit,
  onNext,
  nextLabel = "Next",
}: Props) {
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (committed) return;
      if (isEditableTarget(event.target)) return;
      if (event.key === "0" || event.key === "1" || event.key === "2") {
        event.preventDefault();
        onDraftChange(Number(event.key) as GoldRelevance);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [committed, onDraftChange]);

  return (
    <div className="stack gold-lab-game" data-testid="calibration-rapid-fire">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Rapid Fire calibration</h2>
        <p className="muted" style={{ margin: 0 }}>
          Local 0 / 1 / 2 against registration-time absolute relevance. No Gold
          mutation.
        </p>
      </header>

      <section aria-labelledby="cal-rf-query">
        <h3 id="cal-rf-query">Effective query</h3>
        <p>{item.query}</p>
        {item.category ? (
          <p className="muted">Category: {item.category}</p>
        ) : null}
        {item.tags.length > 0 ? (
          <p className="muted">Tags: {item.tags.join(", ")}</p>
        ) : null}
      </section>

      <GoldSourceContextView source={item.source} heading="Candidate source" />

      <fieldset className="gold-lab-fieldset" disabled={committed}>
        <legend>Your local relevance</legend>
        <div
          className="row gold-lab-radio-row"
          role="radiogroup"
          aria-label="Local relevance judgment"
        >
          {OPTIONS.map((option) => (
            <label key={option.value} className="gold-lab-radio">
              <input
                type="radio"
                name={`cal-rf-${item.itemId}`}
                value={option.value}
                checked={draft === option.value}
                disabled={committed}
                onChange={() => onDraftChange(option.value)}
              />
              <span>
                {option.shortcut} — {option.label}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {!committed ? (
        <Button
          onClick={() => {
            if (draft === null) {
              setStatus("Select a local relevance before committing.");
              return;
            }
            setStatus(null);
            onCommit();
          }}
          disabled={draft === null}
        >
          Commit local response
        </Button>
      ) : null}

      {status ? (
        <p className="error-box" role="alert">
          {status}
        </p>
      ) : null}

      {committed && revealRelevance !== null && authority ? (
        <section
          className="gold-lab-calibration-reveal"
          aria-live="polite"
          data-testid="calibration-reveal"
        >
          <h3>Reveal</h3>
          <p>Your response: {revealRelevance}</p>
          <p>
            Registration-time relevance: {authority.relevance}
            {revealRelevance === authority.relevance
              ? " — match"
              : " — mismatch"}
          </p>
          <Button onClick={onNext}>{nextLabel}</Button>
        </section>
      ) : null}
    </div>
  );
}
