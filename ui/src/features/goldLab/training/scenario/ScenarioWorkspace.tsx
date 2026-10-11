import { useState } from "react";
import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { GoldRelevance } from "../../types";
import type { BlindScenarioExercise, ScenarioAuthority } from "../types";
import { ScenarioDebrief } from "./ScenarioDebrief";

const OPTIONS: Array<{ value: GoldRelevance; label: string }> = [
  { value: 0, label: "Irrelevant" },
  { value: 1, label: "Supporting evidence" },
  { value: 2, label: "Direct evidence" },
];

const GRADE_LABEL: Record<GoldRelevance, string> = {
  0: "Irrelevant",
  1: "Supporting evidence",
  2: "Direct evidence",
};

type Props = {
  exercise: BlindScenarioExercise;
  /**
   * Called only after local scenario commit to obtain registration-time
   * authority. Must not be invoked while the scenario remains editable.
   */
  resolveAuthorityAfterCommit: () => ScenarioAuthority | undefined;
  onRestart: () => void;
};

export function ScenarioWorkspace({
  exercise,
  resolveAuthorityAfterCommit,
  onRestart,
}: Props) {
  const [drafts, setDrafts] = useState<Record<string, GoldRelevance | null>>(
    () =>
      Object.fromEntries(
        exercise.candidates.map((c) => [c.chunkId, null]),
      ) as Record<string, GoldRelevance | null>,
  );
  const [committed, setCommitted] = useState(false);
  const [authority, setAuthority] = useState<ScenarioAuthority | undefined>(
    undefined,
  );

  const allClassified = exercise.candidates.every(
    (c) => drafts[c.chunkId] !== null && drafts[c.chunkId] !== undefined,
  );

  function commit() {
    if (!allClassified || committed) return;
    const resolved = resolveAuthorityAfterCommit();
    setAuthority(resolved);
    setCommitted(true);
  }

  const learnerByChunkId = Object.fromEntries(
    Object.entries(drafts).filter(
      (entry): entry is [string, GoldRelevance] =>
        entry[1] === 0 || entry[1] === 1 || entry[1] === 2,
    ),
  );

  return (
    <div
      className="stack gold-lab-training-scenario"
      data-testid="training-scenario"
    >
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Scenario — relevance map</h1>
        <p className="muted" style={{ margin: 0 }}>
          Classify every candidate for this case. Authority stays hidden until
          you commit the scenario.
        </p>
        <p className="muted" style={{ margin: 0 }}>
          <code>{exercise.exerciseId}</code>
        </p>
      </header>

      <section aria-labelledby="train-scenario-stem">
        <h2 id="train-scenario-stem">Scenario</h2>
        <p data-testid="scenario-stem">{exercise.scenarioStem}</p>
        {exercise.category ? (
          <p className="muted">Category: {exercise.category}</p>
        ) : null}
        {exercise.tags.length > 0 ? (
          <p className="muted">Tags: {exercise.tags.join(", ")}</p>
        ) : null}
      </section>

      <ol className="gold-lab-training-candidate-list">
        {exercise.candidates.map((candidate, index) => (
          <li key={candidate.chunkId} data-chunk-id={candidate.chunkId}>
            <h3>Candidate {index + 1}</h3>
            <GoldSourceContextView
              source={candidate.source}
              heading="Historical source"
              headingId={`train-sc-src-${candidate.chunkId}`}
            />
            <fieldset className="gold-lab-fieldset" disabled={committed}>
              <legend>Classification</legend>
              <div
                className="row gold-lab-radio-row"
                role="radiogroup"
                aria-label={`Classification for ${candidate.chunkId}`}
              >
                {OPTIONS.map((option) => (
                  <label key={option.value} className="gold-lab-radio">
                    <input
                      type="radio"
                      name={`train-sc-${candidate.chunkId}`}
                      value={option.value}
                      checked={drafts[candidate.chunkId] === option.value}
                      disabled={committed}
                      onChange={() =>
                        setDrafts((prev) => ({
                          ...prev,
                          [candidate.chunkId]: option.value,
                        }))
                      }
                    />
                    <span>
                      {option.value} — {option.label}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            {committed && authority ? (
              <section
                className="gold-lab-training-reveal"
                aria-live="polite"
                data-testid={`scenario-reveal-${candidate.chunkId}`}
              >
                <p>
                  Authority: {authority.relevanceByChunkId[candidate.chunkId]} —{" "}
                  {
                    GRADE_LABEL[
                      authority.relevanceByChunkId[candidate.chunkId]!
                    ]
                  }
                </p>
              </section>
            ) : null}
          </li>
        ))}
      </ol>

      {!committed ? (
        <Button onClick={commit} disabled={!allClassified}>
          Commit scenario
        </Button>
      ) : authority ? (
        <>
          <ScenarioDebrief
            exercise={exercise}
            authority={authority}
            learnerByChunkId={learnerByChunkId}
          />
          <Button variant="secondary" onClick={onRestart}>
            Restart scenario exercise
          </Button>
        </>
      ) : (
        <p className="error-box" role="alert">
          Training cannot safely reveal this scenario because registration-time
          authority is unavailable.
        </p>
      )}
    </div>
  );
}
