import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { getGoldCampaign } from "../features/goldLab/api/readClient";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import { PresentationReviewWorkspace } from "../features/goldLab/presentationReview/PresentationReviewWorkspace";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";

export function GoldLabPresentationReviewPage() {
  const { campaignId = "" } = useParams();

  const campaignQuery = useQuery({
    queryKey: goldLabQueryKeys.campaign(campaignId),
    queryFn: ({ signal }) => getGoldCampaign(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  if (!campaignId) {
    return (
      <Card>
        <h1>Presentation review</h1>
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
        <p className="muted">Loading campaign…</p>
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <Card>
        <h1>Presentation review</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
        <Link to="/gold-lab">Back to Gold Lab</Link>
      </Card>
    );
  }

  return (
    <div className="stack gold-lab-page" data-testid="presentation-review-page">
      <p className="muted" style={{ margin: 0 }}>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
      </p>
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Presentation review</h1>
        <p className="muted" style={{ margin: 0 }}>
          Inspect candidate game presentations without writing Gold.
        </p>
      </header>
      <Card>
        <PresentationReviewWorkspace campaignId={campaignId} />
      </Card>
    </div>
  );
}
