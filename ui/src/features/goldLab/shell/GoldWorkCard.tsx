import { Button } from "../../../components/Button";

export type GoldWorkCardKind =
  | "question_check"
  | "rapid_fire"
  | "evidence_sweep"
  | "chunk_duel";

type Props = {
  kind: GoldWorkCardKind;
  title: string;
  purpose: string;
  status: string;
  actionLabel?: string;
  onAction?: () => void;
  locked?: boolean;
  lockedReason?: string;
  disabled?: boolean;
};

export function GoldWorkCard({
  kind,
  title,
  purpose,
  status,
  actionLabel,
  onAction,
  locked = false,
  lockedReason,
  disabled = false,
}: Props) {
  return (
    <article
      className="card gold-lab-work-card"
      data-testid={`gold-work-card-${kind}`}
      aria-labelledby={`gold-work-card-${kind}-title`}
    >
      <h3 id={`gold-work-card-${kind}-title`} style={{ marginTop: 0 }}>
        {title}
      </h3>
      <p className="muted" style={{ margin: "0 0 0.5rem" }}>
        {purpose}
      </p>
      <p role="status" style={{ margin: "0 0 0.75rem" }}>
        {status}
      </p>
      {locked ? (
        <p className="muted" role="status" data-testid={`gold-work-card-${kind}-locked`}>
          {lockedReason ?? "Not available yet"}
        </p>
      ) : actionLabel && onAction ? (
        <Button onClick={onAction} disabled={disabled}>
          {actionLabel}
        </Button>
      ) : null}
    </article>
  );
}
