import { useState } from "react";
import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type {
  BlindEvidenceSelectExercise,
  EvidenceSelectAuthority,
} from "../types";

const GRADE_LABEL: Record<0 | 1 | 2, string> = {
  0: "Irrelevant",
  1: "Supporting evidence",
  2: "Direct evidence",
};

type Props = {
  exercise: BlindEvidenceSelectExercise;
  /** Present only after local case commit. */
  authority: EvidenceSelectAuthority | undefined;
  committed: boolean;
  onCommit: (selectedChunkIds: string[]) => void;
  onNext: () => void;
};

export function EvidenceSelectionDrill({
  exercise,
  authority,
  committed,
  onCommit,
  onNext,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  function toggle(chunkId: string) {
    if (committed) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  }

  const positives = new Set(authority?.positiveChunkIds ?? []);

  return (
    <div className="stack gold-lab-training-drill" data-testid="training-evidence-select">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Evidence Selection</h2>
        <p className="muted" style={{ margin: 0 }}>
          Select all candidate chunks that belong in the registered Gold
          evidence set. Labels stay hidden until you commit.
        </p>
        <p className="muted" style={{ margin: 0 }}>
          <code>{exercise.exerciseId}</code>
        </p>
      </header>

      <section aria-labelledby="train-es-query">
        <h3 id="train-es-query">Question</h3>
        <p>{exercise.query}</p>
        {exercise.category ? (
          <p className="muted">Category: {exercise.category}</p>
        ) : null}
        {exercise.tags.length > 0 ? (
          <p className="muted">Tags: {exercise.tags.join(", ")}</p>
        ) : null}
      </section>

      <fieldset className="gold-lab-fieldset" disabled={committed}>
        <legend>Candidates</legend>
        <ul className="gold-lab-training-candidate-list">
          {exercise.candidates.map((candidate) => {
            const grade = authority?.relevanceByChunkId[candidate.chunkId];
            return (
              <li key={candidate.chunkId} data-chunk-id={candidate.chunkId}>
                <label className="gold-lab-training-check">
                  <input
                    type="checkbox"
                    checked={selected.has(candidate.chunkId)}
                    disabled={committed}
                    onChange={() => toggle(candidate.chunkId)}
                  />
                  <span>Include {candidate.chunkId}</span>
                </label>
                <GoldSourceContextView
                  source={candidate.source}
                  heading="Historical source"
                  headingId={`train-es-src-${candidate.chunkId}`}
                />
                {committed && authority && grade !== undefined ? (
                  <section
                    className="gold-lab-training-reveal"
                    aria-live="polite"
                    data-testid={`training-reveal-${candidate.chunkId}`}
                  >
                    <p>
                      {grade} — {GRADE_LABEL[grade]}
                      {positives.has(candidate.chunkId)
                        ? " · authoritative evidence"
                        : " · irrelevant distractor"}
                    </p>
                    {selected.has(candidate.chunkId) &&
                    positives.has(candidate.chunkId) ? (
                      <p>Selected and authoritative evidence</p>
                    ) : null}
                    {!selected.has(candidate.chunkId) &&
                    positives.has(candidate.chunkId) ? (
                      <p>Missed authoritative evidence</p>
                    ) : null}
                    {selected.has(candidate.chunkId) &&
                    !positives.has(candidate.chunkId) ? (
                      <p>Selected irrelevant candidate</p>
                    ) : null}
                  </section>
                ) : null}
              </li>
            );
          })}
        </ul>
      </fieldset>

      {!committed ? (
        <Button onClick={() => onCommit([...selected])}>
          Commit local response
        </Button>
      ) : (
        <Button onClick={onNext}>Next exercise</Button>
      )}
    </div>
  );
}
