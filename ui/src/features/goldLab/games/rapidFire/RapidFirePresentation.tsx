import { useEffect } from "react";
import { Zap, CircleMinus, BookOpen, Crosshair } from "lucide-react";
import { Button } from "../../../../components/Button";
import type {
  AbsoluteRelevanceTaskDetail,
  GoldRelevance,
} from "../../types";
import { GoldAfterAction } from "../common/GoldAfterAction";
import { GoldMutationStatus } from "../common/GoldMutationStatus";
import { GoldSourceContextView } from "../common/GoldSourceContext";

const RELEVANCE_OPTIONS: Array<{
  value: GoldRelevance;
  label: string;
  shortcut: string;
  description: string;
  icon: typeof CircleMinus;
}> = [
  {
    value: 0,
    label: "Irrelevant",
    shortcut: "0",
    description: "The passage does not help answer the question.",
    icon: CircleMinus,
  },
  {
    value: 1,
    label: "Supporting evidence",
    shortcut: "1",
    description: "The passage adds useful context but does not establish the answer.",
    icon: BookOpen,
  },
  {
    value: 2,
    label: "Direct evidence",
    shortcut: "2",
    description: "The passage directly states or demonstrates the requested fact.",
    icon: Crosshair,
  },
];

export type RapidFirePresentationProps = {
  task: AbsoluteRelevanceTaskDetail;
  locked: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  ambiguous?: boolean;
  showRetry?: boolean;
  showAfterAction: boolean;
  afterActionReplayed?: boolean;
  onCommit: (relevance: GoldRelevance) => void;
  onRetrySame?: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
  correctDisabled?: boolean;
  retryBusy?: boolean;
  /** Injected after-action copy; production keeps GoldAfterAction defaults. */
  afterActionRecordedLabel?: string;
  afterActionCorrectLabel?: string;
  afterActionNextLabel?: string;
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

/**
 * Shared Rapid Fire presentation (production + Presentation Review).
 * Mutation authority is owned by the parent via onCommit / after-action props.
 */
export function RapidFirePresentation({
  task,
  locked,
  errorMessage,
  statusMessage,
  ambiguous = false,
  showRetry = false,
  showAfterAction,
  afterActionReplayed = false,
  onCommit,
  onRetrySame,
  onNext,
  onCorrect,
  nextDisabled = false,
  correctDisabled = false,
  retryBusy = false,
  afterActionRecordedLabel,
  afterActionCorrectLabel,
  afterActionNextLabel,
}: RapidFirePresentationProps) {
  const presentation = task.presentation;

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
    <div className="stack gold-lab-game" data-testid="rapid-fire-presentation">
      <header className="gold-game-heading rapid-fire-heading">
        <span className="gold-game-heading-icon" aria-hidden="true">
          <Zap size={22} />
        </span>
        <div>
          <p className="quick-play-eyebrow">EVIDENCE JUDGMENT</p>
          <h2>Rapid Fire</h2>
          <p className="muted">Use 0, 1, or 2 on your keyboard when focus is outside an editable field.</p>
        </div>
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
        <div className="gold-lab-radio-row rapid-fire-options">
          {RELEVANCE_OPTIONS.map((option) => (
            <Button
              key={option.value}
              className={`rapid-fire-option rapid-fire-option-${option.value}`}
              variant={task.current_result?.relevance === option.value ? "primary" : "secondary"}
              disabled={locked}
              onClick={() => onCommit(option.value)}
              aria-keyshortcuts={option.shortcut}
              aria-label={`${option.shortcut} — ${option.label}`}
              aria-describedby={`rapid-fire-option-${option.value}-description`}
            >
              <span className="rapid-fire-option-number">{option.shortcut}</span>
              <span className="rapid-fire-option-icon" aria-hidden="true"><option.icon size={19} /></span>
              <span className="rapid-fire-option-copy">
                <strong>{option.label}</strong>
                <span id={`rapid-fire-option-${option.value}-description`}>
                  {option.description}
                </span>
              </span>
            </Button>
          ))}
        </div>
      </fieldset>

      <GoldMutationStatus
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        ambiguous={ambiguous && showRetry}
        onRetrySame={showRetry ? onRetrySame : undefined}
        retryBusy={retryBusy}
      />

      {showAfterAction ? (
        <GoldAfterAction
          replayed={afterActionReplayed}
          onNext={onNext}
          onCorrect={onCorrect}
          nextDisabled={nextDisabled}
          correctDisabled={correctDisabled}
          recordedLabel={afterActionRecordedLabel}
          correctLabel={afterActionCorrectLabel}
          nextLabel={afterActionNextLabel}
        />
      ) : null}
    </div>
  );
}
