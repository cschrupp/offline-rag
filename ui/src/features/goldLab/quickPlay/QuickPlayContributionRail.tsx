import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { Award, CheckCircle2, ClipboardCheck, FileText } from "lucide-react";
import { getGoldContribution } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";

type Props = {
  workspaceTitle: string | null;
  campaignId: string | undefined;
};

export function QuickPlayContributionRail({ workspaceTitle, campaignId }: Props) {
  const headingId = useId();
  const contributionQuery = useQuery({
    queryKey: goldLabQueryKeys.contribution(campaignId ?? ""),
    queryFn: ({ signal }) => getGoldContribution(campaignId!, signal),
    enabled: Boolean(campaignId),
  });
  const contribution =
    contributionQuery.data?.campaign_id === campaignId
      ? contributionQuery.data
      : undefined;

  return (
    <section
      className="quick-play-contribution"
      aria-labelledby={headingId}
    >
      <header className="quick-play-contribution-heading">
        <Award aria-hidden="true" size={19} />
        <div>
          <h2 id={headingId}>Contribution</h2>
          {workspaceTitle ? <p>{workspaceTitle}</p> : null}
        </div>
      </header>
      {!campaignId ? (
        <p className="muted" role="status">
          No current deck contribution yet.
        </p>
      ) : contributionQuery.isLoading ? (
        <p className="muted" role="status">
          Loading campaign contribution…
        </p>
      ) : contributionQuery.isError ? (
        <div className="stack quick-play-contribution-error">
          <p className="error-box" role="alert">
            {goldLabErrorMessage(contributionQuery.error)}
          </p>
          <button
            type="button"
            className="link-button"
            onClick={() => void contributionQuery.refetch()}
          >
            Retry contribution
          </button>
        </div>
      ) : contribution ? (
        <>
          <p className="quick-play-contribution-score">
            {contribution.total_score.toLocaleString()}
            <span>points</span>
          </p>
          <dl className="quick-play-contribution-metrics">
            <div>
              <dt>
                <ClipboardCheck aria-hidden="true" size={15} /> Questions
                reviewed
              </dt>
              <dd>{contribution.questions_reviewed.toLocaleString()}</dd>
            </div>
            <div>
              <dt>
                <CheckCircle2 aria-hidden="true" size={15} /> Cases completed
              </dt>
              <dd>{contribution.cases_completed.toLocaleString()}</dd>
            </div>
            <div>
              <dt>
                <FileText aria-hidden="true" size={15} /> Evidence judgments
                completed
              </dt>
              <dd>
                {contribution.completed_active_absolute_tasks.toLocaleString()}
              </dd>
            </div>
          </dl>
          <p className="quick-play-contribution-note">
            Current campaign contribution
          </p>
        </>
      ) : null}
    </section>
  );
}
