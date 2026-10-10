import { useEffect } from "react";
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
  shortcut: string;
}> = [
  { value: 0, label: "Irrelevant", shortcut: "0" },
  { value: 1, label: "Supporting evidence", shortcut: "1" },
  { value: 2, label: "Direct evidence", shortcut: "2" },
];

type Props = {
  task: AbsoluteRelevanceTaskDetail;
  mutationBusy: boolean;
  ambiguous: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  afterAction: GoldMutationReceipt | null;
  onCommit: (relevance: GoldRelevance) => void;
  onRetrySame: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
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

export function RapidFireGame({
  task,
  mutationBusy,
  ambiguous,
  errorMessage,
  statusMessage,
  afterAction,
  onCommit,
  onRetrySame,
  onNext,
  onCorrect,
  nextDisabled = false,
}: Props) {
  const presentation = task.presentation;
  const locked = mutationBusy || ambiguous || afterAction !== null;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (locked) return;
      if (isEditableTarget(event.target)) return;
      if (event.key === "0" || event.key === "1" || event.key === "2") {
        event.preventDefault();
        onCommit(Number(event.key) as GoldRelevance);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [locked, onCommit]);

  return (
    <div className="stack gold-lab-game">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Rapid Fire</h2>
        <p className="muted" style={{ margin: 0 }}>
          Keyboard shortcuts: 0 Irrelevant · 1 Supporting evidence · 2 Direct
          evidence
        </p>
      </header>

      <section aria-labelledby="gold-rf-query-heading">
        <h3 id="gold-rf-query-heading">Effective query</h3>
        <p>{presentation.effective_query}</p>
        {presentation.effective_category ? (
          <p className="muted">Category: {presentation.effective_category}</p>
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
      />

      {task.current_result ? (
        <p className="muted" role="status">
          Current recorded relevance: {task.current_result.relevance} —{" "}
          {
            RELEVANCE_OPTIONS.find(
              (option) => option.value === task.current_result?.relevance,
            )?.label
          }
        </p>
      ) : null}

      <fieldset className="gold-lab-fieldset" disabled={locked}>
        <legend>Relevance judgment</legend>
        <div className="row gold-lab-radio-row">
          {RELEVANCE_OPTIONS.map((option) => (
            <Button
              key={option.value}
              variant="secondary"
              disabled={locked}
              onClick={() => onCommit(option.value)}
              aria-keyshortcuts={option.shortcut}
            >
              {option.shortcut} — {option.label}
            </Button>
          ))}
        </div>
      </fieldset>

      <GoldMutationStatus
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        ambiguous={ambiguous}
        onRetrySame={onRetrySame}
        retryBusy={mutationBusy}
      />

      {afterAction ? (
        <GoldAfterAction
          replayed={afterAction.replayed}
          onNext={onNext}
          onCorrect={onCorrect}
          nextDisabled={nextDisabled}
          correctDisabled={mutationBusy}
        />
      ) : null}
    </div>
  );
}
