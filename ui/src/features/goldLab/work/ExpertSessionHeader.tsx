import { Button } from "../../../components/Button";

type Props = {
  title: string;
  endDisabled: boolean;
  endDisabledReason?: string | null;
  onEndSession: () => void;
};

export function ExpertSessionHeader({
  title,
  endDisabled,
  endDisabledReason,
  onEndSession,
}: Props) {
  return (
    <header
      className="row gold-lab-card-header"
      data-testid="expert-session-header"
      style={{ alignItems: "center", gap: "1rem", justifyContent: "flex-end" }}
    >
      <p className="muted" style={{ margin: 0, flex: 1 }} data-session-title={title}>
        {endDisabled && endDisabledReason
          ? endDisabledReason
          : `${title} session`}
      </p>
      <Button
        variant="secondary"
        onClick={onEndSession}
        disabled={endDisabled}
        data-testid="end-session"
        aria-label={`End ${title} session`}
      >
        End session
      </Button>
    </header>
  );
}
