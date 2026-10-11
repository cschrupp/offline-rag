import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { GoldRelevance } from "../../types";
import type { BlindScenarioExercise, ScenarioAuthority } from "../types";

const GRADE_LABEL: Record<GoldRelevance, string> = {
  0: "Irrelevant",
  1: "Supporting evidence",
  2: "Direct evidence",
};

type Props = {
  exercise: BlindScenarioExercise;
  authority: ScenarioAuthority;
  learnerByChunkId: Record<string, GoldRelevance>;
};

export function ScenarioDebrief({
  exercise,
  authority,
  learnerByChunkId,
}: Props) {
  const candidates = exercise.candidates;
  let matches = 0;
  const learnerDist = { 0: 0, 1: 0, 2: 0 };
  const authorityDist = { 0: 0, 1: 0, 2: 0 };

  for (const candidate of candidates) {
    const learner = learnerByChunkId[candidate.chunkId];
    const auth = authority.relevanceByChunkId[candidate.chunkId];
    if (learner !== undefined) learnerDist[learner] += 1;
    if (auth !== undefined) authorityDist[auth] += 1;
    if (learner !== undefined && auth !== undefined && learner === auth) {
      matches += 1;
    }
  }

  return (
    <section
      className="stack gold-lab-training-debrief"
      data-testid="training-scenario-debrief"
      aria-labelledby="train-scenario-debrief-heading"
    >
      <h2 id="train-scenario-debrief-heading">Scenario debrief</h2>
      <p className="muted">
        Deterministic, source-grounded review only. This is not a Gold score,
        grade, certification, or contribution.
      </p>
      <dl className="gold-lab-meta">
        <div>
          <dt>Case</dt>
          <dd>
            <code>{exercise.caseId}</code>
          </dd>
        </div>
        <div>
          <dt>Exercise</dt>
          <dd>
            <code>{exercise.exerciseId}</code>
          </dd>
        </div>
        <div>
          <dt>Effective query</dt>
          <dd>{exercise.scenarioStem}</dd>
        </div>
        <div>
          <dt>Matching classifications</dt>
          <dd data-testid="scenario-debrief-matches">
            {matches} / {candidates.length}
          </dd>
        </div>
        <div>
          <dt>Learner distribution</dt>
          <dd data-testid="scenario-debrief-learner-dist">
            0:{learnerDist[0]} · 1:{learnerDist[1]} · 2:{learnerDist[2]}
          </dd>
        </div>
        <div>
          <dt>Authority distribution</dt>
          <dd data-testid="scenario-debrief-authority-dist">
            0:{authorityDist[0]} · 1:{authorityDist[1]} · 2:{authorityDist[2]}
          </dd>
        </div>
      </dl>

      <ul className="gold-lab-training-candidate-list">
        {candidates.map((candidate) => {
          const learner = learnerByChunkId[candidate.chunkId];
          const auth = authority.relevanceByChunkId[candidate.chunkId];
          const matched =
            learner !== undefined && auth !== undefined && learner === auth;
          return (
            <li key={candidate.chunkId} data-chunk-id={candidate.chunkId}>
              <h3>
                <code>{candidate.chunkId}</code>
              </h3>
              <p>
                Learner: {learner} —{" "}
                {learner !== undefined ? GRADE_LABEL[learner] : "—"}
              </p>
              <p>
                Authority: {auth} —{" "}
                {auth !== undefined ? GRADE_LABEL[auth] : "—"}
              </p>
              <p>{matched ? "match" : "mismatch"}</p>
              {learner !== undefined &&
              auth !== undefined &&
              learner !== auth ? (
                <p>
                  You marked this {GRADE_LABEL[learner]} ({learner}).
                  Registration-time authority is {GRADE_LABEL[auth]} ({auth}).
                </p>
              ) : null}
              <GoldSourceContextView
                source={candidate.source}
                heading="Historical source"
                headingId={`train-scenario-src-${candidate.chunkId}`}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}
