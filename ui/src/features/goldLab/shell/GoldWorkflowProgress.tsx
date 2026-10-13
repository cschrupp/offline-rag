import type { ExpertCampaignState } from "./deriveExpertCampaignState";

type Props = {
  state: ExpertCampaignState;
};

export function GoldWorkflowProgress({ state }: Props) {
  return (
    <section
      className="card"
      data-testid="gold-workflow-progress"
      aria-labelledby="gold-workflow-heading"
    >
      <h2 id="gold-workflow-heading" style={{ marginTop: 0 }}>
        Gold workflow
      </h2>
      <ol className="gold-lab-workflow-ladder">
        <li>
          <strong>Review questions</strong>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            {state.qcReviewed} reviewed · {state.qcPending} remaining
          </p>
        </li>
        <li>
          <strong>Judge evidence</strong>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            {state.relevanceCompleted} judged · {state.relevancePending} ready
          </p>
        </li>
        <li>
          <strong>Canonical Gold work complete</strong>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            {state.primaryComplete
              ? "No primary Question Check or Rapid Fire work remains."
              : "Primary expert adjudication is still in progress."}
          </p>
        </li>
      </ol>
    </section>
  );
}
