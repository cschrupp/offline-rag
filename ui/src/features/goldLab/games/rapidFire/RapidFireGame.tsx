import type {
  AbsoluteRelevanceTaskDetail,
  GoldMutationReceipt,
  GoldRelevance,
} from "../../types";
import { RapidFirePresentation } from "./RapidFirePresentation";

type Props = {
  task: AbsoluteRelevanceTaskDetail;
  mutationBusy: boolean;
  ambiguous: boolean;
  /** Terminal reconciliation block; no new mutation or same-intent retry. */
  mutationBlocked?: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  afterAction: GoldMutationReceipt | null;
  onCommit: (relevance: GoldRelevance) => void;
  onRetrySame: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
};

/** Production Rapid Fire wrapper — owns Gold mutation after-action semantics. */
export function RapidFireGame({
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
    <RapidFirePresentation
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
