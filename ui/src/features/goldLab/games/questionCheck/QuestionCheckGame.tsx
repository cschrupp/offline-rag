import type { GoldMutationReceipt, QuestionCheckTaskDetail } from "../../types";
import {
  QuestionCheckPresentation,
  type QuestionCheckCommitDraft,
} from "./QuestionCheckPresentation";

export type { QuestionCheckCommitDraft };

type Props = {
  task: QuestionCheckTaskDetail;
  mutationBusy: boolean;
  ambiguous: boolean;
  /** Terminal reconciliation block; no new mutation or same-intent retry. */
  mutationBlocked?: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  afterAction: GoldMutationReceipt | null;
  onCommit: (body: QuestionCheckCommitDraft) => void;
  onRetrySame: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
};

/** Production Question Check wrapper — owns Gold mutation after-action semantics. */
export function QuestionCheckGame({
  task,
  mutationBusy,
  ambiguous,
  mutationBlocked = false,
  errorMessage,
  statusMessage,
  afterAction,
  onCommit,
  onRetrySame,
  onNext,
  onCorrect,
  nextDisabled = false,
}: Props) {
  const locked =
    mutationBusy ||
    ambiguous ||
    mutationBlocked ||
    afterAction !== null;

  return (
    <QuestionCheckPresentation
      task={task}
      locked={locked}
      errorMessage={errorMessage}
      statusMessage={statusMessage}
      ambiguous={ambiguous && !mutationBlocked}
      showRetry={ambiguous && !mutationBlocked}
      showAfterAction={Boolean(afterAction) && !mutationBlocked}
      afterActionReplayed={afterAction?.replayed ?? false}
      onCommit={onCommit}
      onRetrySame={onRetrySame}
      onNext={onNext}
      onCorrect={onCorrect}
      nextDisabled={nextDisabled}
      correctDisabled={mutationBusy}
      retryBusy={mutationBusy}
    />
  );
}
