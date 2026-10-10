import { Button } from "../../../../components/Button";

type Props = {
  replayed: boolean;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
  correctDisabled?: boolean;
};

export function GoldAfterAction({
  replayed,
  onNext,
  onCorrect,
  nextDisabled = false,
  correctDisabled = false,
}: Props) {
  return (
    <div className="stack gold-lab-after-action">
      {replayed ? (
        <p className="muted" role="status">
          Previous commit confirmed.
        </p>
      ) : (
        <p className="muted" role="status">
          Judgment recorded.
        </p>
      )}
      <div className="row">
        <Button onClick={onNext} disabled={nextDisabled}>
          Next task
        </Button>
        <Button variant="secondary" onClick={onCorrect} disabled={correctDisabled}>
          Correct judgment
        </Button>
      </div>
    </div>
  );
}
