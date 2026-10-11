import { Button } from "../../../../components/Button";
import type {
  AbsoluteRelevanceTaskDetail,
  GoldMutationReceipt,
  GoldRelevance,
} from "../../types";
import { GoldAfterAction } from "../common/GoldAfterAction";
import { GoldMutationStatus } from "../common/GoldMutationStatus";
import { GoldSourceContextView } from "../common/GoldSourceContext";

const RELEVANCE_OPTIONS: Array<{
  value: GoldRelevance;
  label: string;
}> = [
  { value: 0, label: "Irrelevant" },
  { value: 1, label: "Supporting evidence" },
  { value: 2, label: "Direct evidence" },
];

export type EvidenceSweepCardState = {
  task: AbsoluteRelevanceTaskDetail;
  afterAction: GoldMutationReceipt | null;
};

type Props = {
  cards: EvidenceSweepCardState[];
  mutationBusy: boolean;
  ambiguous: boolean;
  mutationBlocked?: boolean;
  busyTaskId: string | null;
  errorMessage: string | null;
  statusMessage: string | null;
  batchComplete: boolean;
  nextBatchDisabled: boolean;
  onCommit: (taskId: string, relevance: GoldRelevance) => void;
  onCorrect: (taskId: string) => void;
  onRetrySame: () => void;
  onNextBatch: () => void;
};

export function EvidenceSweepGame({
  cards,
  mutationBusy,
  ambiguous,
  mutationBlocked = false,
  busyTaskId,
  errorMessage,
  statusMessage,
  batchComplete,
  nextBatchDisabled,
  onCommit,
  onCorrect,
  onRetrySame,
  onNextBatch,
}: Props) {
  const sessionLocked = mutationBusy || ambiguous || mutationBlocked;

  return (
    <div className="stack gold-lab-game">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Evidence Sweep</h2>
        <p className="muted" style={{ margin: 0 }}>
          Absolute relevance 0 / 1 / 2 for each candidate. Each card commits
          independently. Scientific order follows the sealed server task list.
        </p>
      </header>

      <ol className="gold-lab-evidence-sweep-list">
        {cards.map((card, index) => {
          const { task, afterAction } = card;
          const presentation = task.presentation;
          const cardLocked =
            sessionLocked ||
            afterAction !== null ||
            (busyTaskId !== null && busyTaskId !== task.task_id);
          const relevanceLabel = task.current_result
            ? RELEVANCE_OPTIONS.find(
                (option) => option.value === task.current_result?.relevance,
              )?.label
            : null;

          return (
            <li
              key={task.task_id}
              className="gold-lab-evidence-sweep-card"
              data-task-id={task.task_id}
            >
              <h3>
                Candidate {index + 1}
                <span className="muted">{` (${task.task_id})`}</span>
              </h3>

              <section
                aria-labelledby={`gold-es-query-${task.task_id}`}
              >
                <h4 id={`gold-es-query-${task.task_id}`}>Effective query</h4>
                <p>{presentation.effective_query}</p>
                {presentation.effective_category ? (
                  <p className="muted">
                    Category: {presentation.effective_category}
                  </p>
                ) : null}
                {presentation.effective_tags.length > 0 ? (
                  <p className="muted">
                    Tags: {presentation.effective_tags.join(", ")}
                  </p>
                ) : null}
              </section>

              <GoldSourceContextView
                source={presentation.candidate}
                heading="Candidate source"
                headingId={`gold-es-source-${task.task_id}`}
              />

              {task.current_result ? (
                <p className="muted" role="status">
                  Current recorded relevance: {task.current_result.relevance} —{" "}
                  {relevanceLabel}
                </p>
              ) : null}

              <fieldset
                className="gold-lab-fieldset"
                disabled={cardLocked}
                aria-label={`Relevance judgment for candidate ${index + 1}`}
              >
                <legend>Relevance judgment</legend>
                <div className="row gold-lab-radio-row">
                  {RELEVANCE_OPTIONS.map((option) => (
                    <Button
                      key={option.value}
                      variant="secondary"
                      disabled={cardLocked}
                      onClick={() => onCommit(task.task_id, option.value)}
                    >
                      {option.value} — {option.label}
                    </Button>
                  ))}
                </div>
              </fieldset>

              {afterAction && !mutationBlocked ? (
                <GoldAfterAction
                  replayed={afterAction.replayed}
                  showNext={false}
                  onCorrect={() => onCorrect(task.task_id)}
                  correctDisabled={mutationBusy}
                />
              ) : null}
            </li>
          );
        })}
      </ol>

      <GoldMutationStatus
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        ambiguous={ambiguous && !mutationBlocked}
        onRetrySame={mutationBlocked ? undefined : onRetrySame}
        retryBusy={mutationBusy}
      />

      {batchComplete && !mutationBlocked ? (
        <div className="row gold-lab-after-action">
          <Button onClick={onNextBatch} disabled={nextBatchDisabled}>
            Next batch
          </Button>
        </div>
      ) : null}
    </div>
  );
}
