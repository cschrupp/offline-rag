import { Button } from "../../../../components/Button";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type {
  BlindQuestionCheckExercise,
  LocalQcDisposition,
  QuestionCheckAuthority,
} from "../types";

type Props = {
  exercise: BlindQuestionCheckExercise;
  /** Present only after local commit. */
  authority: QuestionCheckAuthority | undefined;
  committed: boolean;
  localDisposition: LocalQcDisposition | null;
  onCommit: (disposition: LocalQcDisposition) => void;
  onNext: () => void;
};

export function QuestionCheckDrill({
  exercise,
  authority,
  committed,
  localDisposition,
  onCommit,
  onNext,
}: Props) {
  return (
    <div
      className="stack gold-lab-training-drill"
      data-testid="training-question-check"
    >
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Question Check</h2>
        <p className="muted" style={{ margin: 0 }}>
          Recall the registration-time QC disposition. Choosing Edit does not
          require authoring a replacement query.
        </p>
        <p className="muted" style={{ margin: 0 }}>
          <code>{exercise.exerciseId}</code>
        </p>
      </header>

      <section aria-labelledby="train-qc-proposed">
        <h3 id="train-qc-proposed">Proposed question</h3>
        <p>{exercise.proposedQuery}</p>
        {exercise.proposedCategory ? (
          <p className="muted">Category: {exercise.proposedCategory}</p>
        ) : null}
        {exercise.proposedTags.length > 0 ? (
          <p className="muted">Tags: {exercise.proposedTags.join(", ")}</p>
        ) : null}
      </section>

      <GoldSourceContextView
        source={exercise.questionSource}
        heading="Question source"
      />

      {!committed ? (
        <div className="row" style={{ flexWrap: "wrap" }}>
          <Button onClick={() => onCommit("accept")}>Accept</Button>
          <Button variant="secondary" onClick={() => onCommit("edit")}>
            Edit
          </Button>
          <Button variant="danger" onClick={() => onCommit("reject")}>
            Reject
          </Button>
        </div>
      ) : authority && localDisposition ? (
        <section
          className="gold-lab-training-reveal"
          aria-live="polite"
          data-testid="training-reveal"
        >
          <p>Your disposition: {localDisposition}</p>
          <p>
            Registration-time disposition: {authority.disposition}
            {localDisposition === authority.disposition
              ? " — match"
              : " — mismatch"}
          </p>
          {authority.disposition === "edit" ? (
            <div className="muted">
              <p>Registered effective query: {authority.effectiveQuery}</p>
              <p>
                Registered effective category:{" "}
                {authority.effectiveCategory ?? "—"}
              </p>
              <p>
                Registered effective tags:{" "}
                {authority.effectiveTags.length > 0
                  ? authority.effectiveTags.join(", ")
                  : "—"}
              </p>
            </div>
          ) : null}
          <Button onClick={onNext}>Next exercise</Button>
        </section>
      ) : null}
    </div>
  );
}
