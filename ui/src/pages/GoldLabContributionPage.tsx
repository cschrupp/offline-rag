import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import {
  getGoldCampaign,
  getGoldContribution,
} from "../features/goldLab/api/client";
import { ContributionDashboard } from "../features/goldLab/contribution/ContributionDashboard";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";

export function GoldLabContributionPage() {
  const { campaignId = "" } = useParams();

  const campaignQuery = useQuery({
    queryKey: goldLabQueryKeys.campaign(campaignId),
    queryFn: ({ signal }) => getGoldCampaign(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  const contributionQuery = useQuery({
    queryKey: goldLabQueryKeys.contribution(campaignId),
    queryFn: ({ signal }) => getGoldContribution(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  if (!campaignId) {
    return (
      <Card>
        <h1>Gold Contribution</h1>
        <p className="error-box" role="alert">
          Missing campaign identity.
        </p>
        <Button to="/gold-lab">Back to Gold Lab</Button>
      </Card>
    );
  }

  if (campaignQuery.isLoading || contributionQuery.isLoading) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted">Loading contribution…</p>
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <Card>
        <h1>Gold Contribution</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
        <p>
          <Link to="/gold-lab">Back to Gold Lab</Link>
        </p>
      </Card>
    );
  }

  if (contributionQuery.isError || !contributionQuery.data) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted" style={{ margin: 0 }}>
          <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
        </p>
        <Card>
          <h1>Gold Contribution</h1>
          <p className="error-box" role="alert">
            {goldLabErrorMessage(contributionQuery.error)}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="stack gold-lab-page">
      <p className="muted" style={{ margin: 0 }}>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
        {" · "}
        <Link to={`/gold-lab/campaigns/${campaignId}/calibration`}>
          Calibration
        </Link>
      </p>
      <ContributionDashboard contribution={contributionQuery.data} />
    </div>
  );
}
