import { useState } from "react";
import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { GoldRelevance } from "../../types";
import type { BlindRelevanceRecallExercise } from "../types";

const OPTIONS: Array<{ value: GoldRelevance; label: string }> = [
  { value: 0, label: "Irrelevant" },
  { value: 1, label: "Supporting evidence" },
  { value: 2, label: "Direct evidence" },
];

type Props = {
  exercise: BlindRelevanceRecallExercise;
  /** Authority for the current step only after that step commits. */
  stepAuthority: GoldRelevance | undefined;
  stepIndex: number;
  stepCommitted: boolean;
  onCommitStep: (relevance: GoldRelevance) => void;
  onAdvance: () => void;
};

export function RelevanceRecallDrill({
  exercise,
  stepAuthority,
  stepIndex,
  stepCommitted,
  onCommitStep,
  onAdvance,
}: Props) {
  const step = exercise.steps[stepIndex];
  const [draft, setDraft] = useState<GoldRelevance | null>(null);

  if (!step) {
    return (
      <p className="muted" role="status">
        Relevance Recall complete for this exercise.
      </p>
    );
  }

  return (
    <div
      className="stack gold-lab-training-drill"
      data-testid="training-relevance-recall"
      data-step-index={stepIndex}
    >
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Relevance Recall</h2>
        <p className="muted" style={{ margin: 0 }}>
          Candidate {stepIndex + 1} of {exercise.steps.length}. Local 0 / 1 / 2
          against registration-time adjudication.
        </p>
        <p className="muted" style={{ margin: 0 }}>
          <code>{exercise.exerciseId}</code>
        </p>
      </header>

      <section aria-labelledby="train-rr-query">
        <h3 id="train-rr-query">Question</h3>
        <p>{exercise.query}</p>
      </section>

      <GoldSourceContextView
        key={step.stepId}
        source={step.source}
        heading="Candidate source"
        headingId={`train-rr-src-${step.candidateChunkId}`}
      />

      <fieldset className="gold-lab-fieldset" disabled={stepCommitted}>
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
                name={`train-rr-${step.stepId}`}
                value={option.value}
                checked={draft === option.value}
                disabled={stepCommitted}
                onChange={() => setDraft(option.value)}
              />
              <span>
                {option.value} — {option.label}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {!stepCommitted ? (
        <Button
          onClick={() => {
            if (draft === null) return;
            onCommitStep(draft);
          }}
          disabled={draft === null}
        >
          Commit local response
        </Button>
      ) : stepAuthority !== undefined && draft !== null ? (
        <section
          className="gold-lab-training-reveal"
          aria-live="polite"
          data-testid="training-reveal"
        >
          <p>
            Your answer: {draft} — {OPTIONS.find((o) => o.value === draft)?.label}
          </p>
          <p>
            Registered answer: {stepAuthority} —{" "}
            {OPTIONS.find((o) => o.value === stepAuthority)?.label}
          </p>
          <p>
            Result: {draft === stepAuthority ? "match" : "mismatch"}
          </p>
          <Button
            onClick={() => {
              setDraft(null);
              onAdvance();
            }}
          >
            {stepIndex + 1 >= exercise.steps.length
              ? "Finish exercise"
              : "Next candidate"}
          </Button>
        </section>
      ) : null}
    </div>
  );
}
