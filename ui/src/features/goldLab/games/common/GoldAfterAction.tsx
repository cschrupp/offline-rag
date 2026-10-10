import { Button } from "../../../../components/Button";

type Props = {
  replayed: boolean;
  onNext?: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
  correctDisabled?: boolean;
  /** When false, only correction is offered (Evidence Sweep per-card). */
  showNext?: boolean;
  nextLabel?: string;
  recordedLabel?: string;
};

export function GoldAfterAction({
  replayed,
  onNext,
  onCorrect,
  nextDisabled = false,
  correctDisabled = false,
  showNext = true,
  nextLabel = "Next task",
  recordedLabel = "Judgment recorded.",
}: Props) {
  return (
    <div className="stack gold-lab-after-action">
      {replayed ? (
        <p className="muted" role="status">
          Previous commit confirmed.
        </p>
      ) : (
        <p className="muted" role="status">
          {recordedLabel}
        </p>
      )}
      <div className="row">
        {showNext && onNext ? (
          <Button onClick={onNext} disabled={nextDisabled}>
            {nextLabel}
          </Button>
        ) : null}
        <Button variant="secondary" onClick={onCorrect} disabled={correctDisabled}>
          Correct judgment
        </Button>
      </div>
    </div>
  );
}
