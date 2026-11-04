import { Button } from "../../../components/Button";

type Props = {
  boundedWorkload: boolean;
  returnHref: string;
  returnLabel: string;
};

export function ExpertSessionComplete({
  boundedWorkload,
  returnHref,
  returnLabel,
}: Props) {
  return (
    <section className="card" data-testid="expert-session-complete">
      <h2 style={{ marginTop: 0 }}>Session complete</h2>
      <p className="muted" role="status">
        {boundedWorkload
          ? "This work session has no remaining tasks. The campaign may still have more Gold work."
          : "No more eligible tasks remain in this work session."}
      </p>
      <Button to={returnHref}>{returnLabel}</Button>
    </section>
  );
}
