import { Button } from "../../../../components/Button";

type Props = {
  errorMessage: string | null;
  statusMessage: string | null;
  ambiguous: boolean;
  onRetrySame?: () => void;
  retryBusy?: boolean;
};

export function GoldMutationStatus({
  errorMessage,
  statusMessage,
  ambiguous,
  onRetrySame,
  retryBusy = false,
}: Props) {
  return (
    <div className="stack" style={{ gap: "0.5rem" }}>
      {errorMessage ? (
        <p className="error-box" role="alert">
          {errorMessage}
        </p>
      ) : null}
      {statusMessage ? (
        <p className="muted" role="status">
          {statusMessage}
        </p>
      ) : null}
      {ambiguous && onRetrySame ? (
        <Button
          variant="secondary"
          onClick={onRetrySame}
          disabled={retryBusy}
        >
          Retry same commit
        </Button>
      ) : null}
    </div>
  );
}
