import type { GoldContribution } from "../types";

type Props = {
  contribution: GoldContribution;
};

function formatCoverage(fraction: number | null): string | null {
  if (fraction === null) return null;
  return `${Math.round(fraction * 1000) / 10}%`;
}

export function ContributionDashboard({ contribution }: Props) {
  const coveragePct = formatCoverage(contribution.coverage_fraction);

  return (
    <div className="stack gold-lab-contribution">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Gold Contribution</h1>
        <p className="muted" style={{ margin: 0 }}>
          Personal scientific work progress for this campaign. Scores come from
          the server contribution contract only.
        </p>
      </header>

      <section
        className="gold-lab-contribution-score"
        aria-labelledby="gold-contribution-score-heading"
      >
        <h2 id="gold-contribution-score-heading">Total score</h2>
        <p
          className="gold-lab-contribution-total"
          data-testid="contribution-total-score"
        >
          {contribution.total_score}
        </p>
      </section>

      <dl className="gold-lab-meta gold-lab-contribution-metrics">
        <div>
          <dt>Expert judgments</dt>
          <dd data-testid="contribution-expert-judgments">
            {contribution.expert_judgments}
          </dd>
        </div>
        <div>
          <dt>Questions reviewed</dt>
          <dd data-testid="contribution-questions-reviewed">
            {contribution.questions_reviewed}
          </dd>
        </div>
        <div>
          <dt>Cases completed</dt>
          <dd data-testid="contribution-cases-completed">
            {contribution.cases_completed}
          </dd>
        </div>
        <div>
          <dt>Gold finalized</dt>
          <dd data-testid="contribution-gold-finalized">
            {contribution.gold_finalized}
          </dd>
        </div>
        <div>
          <dt>Hard Calls resolved</dt>
          <dd data-testid="contribution-hard-calls-resolved">
            {contribution.hard_calls_resolved}
          </dd>
        </div>
      </dl>

      <section aria-labelledby="gold-contribution-coverage-heading">
        <h2 id="gold-contribution-coverage-heading">Evidence coverage</h2>
        <p data-testid="contribution-coverage-counts">
          {contribution.completed_active_absolute_tasks} /{" "}
          {contribution.total_active_absolute_tasks}
          {coveragePct !== null ? (
            <>
              {" "}
              <span data-testid="contribution-coverage-pct">({coveragePct})</span>
            </>
          ) : null}
        </p>
      </section>

      <section aria-labelledby="gold-contribution-question-heading">
        <h2 id="gold-contribution-question-heading">Question progress</h2>
        <p data-testid="contribution-question-progress">
          {contribution.questions_reviewed} / {contribution.total_question_tasks}
        </p>
      </section>
    </div>
  );
}
