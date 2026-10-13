import { Button } from "../../../components/Button";

type Props = {
  campaignId: string;
  boundedWorkload: boolean;
};

export function ExpertSessionComplete({
  campaignId,
  boundedWorkload,
}: Props) {
  return (
    <section className="card" data-testid="expert-session-complete">
      <h2 style={{ marginTop: 0 }}>Session complete</h2>
      <p className="muted" role="status">
        {boundedWorkload
          ? "This work session has no remaining tasks. The campaign may still have more Gold work."
          : "No more eligible tasks remain in this work session."}
      </p>
      <Button to={`/gold-lab/campaigns/${campaignId}`}>
        Return to campaign
      </Button>
    </section>
  );
}
