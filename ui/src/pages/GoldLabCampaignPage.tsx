import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { getGoldCampaign } from "../features/goldLab/api/client";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import { GoldCampaignShell } from "../features/goldLab/shell/GoldCampaignShell";

export function GoldLabCampaignPage() {
  const { campaignId = "" } = useParams();

  const campaignQuery = useQuery({
    queryKey: goldLabQueryKeys.campaign(campaignId),
    queryFn: ({ signal }) => getGoldCampaign(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  if (!campaignId) {
    return (
      <Card>
        <h1>Gold campaign</h1>
        <p className="error-box" role="alert">
          Missing campaign identity.
        </p>
        <Button to="/gold-lab">Back to Gold Lab</Button>
      </Card>
    );
  }

  if (campaignQuery.isLoading) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted">Loading Gold campaign…</p>
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <Card>
        <h1>Gold campaign</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
        <p>
          <Link to="/gold-lab">Back to Gold Lab</Link>
        </p>
      </Card>
    );
  }

  return <GoldCampaignShell campaign={campaignQuery.data} />;
}
