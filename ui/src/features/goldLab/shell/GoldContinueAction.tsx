import { Button } from "../../../components/Button";
import type { ExpertCampaignState } from "./deriveExpertCampaignState";

type Props = {
  state: ExpertCampaignState;
  closed: boolean;
  busy: boolean;
  onContinue: () => void;
};

export function GoldContinueAction({
  state,
  closed,
  busy,
  onContinue,
}: Props) {
  if (closed) {
    return (
      <section className="card" data-testid="gold-continue-resting">
        <h2 style={{ marginTop: 0 }}>Continue Gold work</h2>
        <p className="muted" role="status">
          This campaign is closed. New expert sessions cannot be prepared.
        </p>
      </section>
    );
  }

  if (state.primaryComplete) {
    return (
      <section className="card" data-testid="gold-continue-resting">
        <h2 style={{ marginTop: 0 }}>Continue Gold work</h2>
        <p className="muted" role="status">
          Canonical Gold work is complete for now. No active Question Check or
          Rapid Fire tasks remain.
        </p>
      </section>
    );
  }

  const label =
    state.nextPrimaryGame === "question_check"
      ? "Continue Gold work — Review questions"
      : "Continue Gold work — Judge evidence";

  return (
    <section className="card" data-testid="gold-continue-action">
      <h2 style={{ marginTop: 0 }}>Continue Gold work</h2>
      <p className="muted">
        {state.nextPrimaryGame === "question_check"
          ? `${state.qcPending} questions remaining.`
          : `${state.relevancePending} evidence judgments ready.`}
      </p>
      <Button onClick={onContinue} disabled={busy}>
        {label}
      </Button>
    </section>
  );
}
