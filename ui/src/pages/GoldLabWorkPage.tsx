import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { getGoldCampaign } from "../features/goldLab/api/client";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import {
  candidatePresentationForGame,
  isAllowProduction,
  isExpertWorkGame,
  isI2ExpertGame,
  isI3ExpertGame,
} from "../features/goldLab/policy/presentations";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import { parseSessionConfig } from "../features/goldLab/state/sessionConfig";
import { ChunkDuelWorkSession } from "../features/goldLab/work/ChunkDuelWorkSession";
import { EvidenceSweepWorkSession } from "../features/goldLab/work/EvidenceSweepWorkSession";
import { GoldWorkSession } from "../features/goldLab/work/GoldWorkSession";

export function GoldLabWorkPage() {
  const { campaignId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);

  const campaignQuery = useQuery({
    queryKey: goldLabQueryKeys.campaign(campaignId),
    queryFn: ({ signal }) => getGoldCampaign(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  if (!campaignId) {
    return (
      <Card>
        <h1>Expert work</h1>
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
        <h1>Expert work</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
        <Link to="/gold-lab">Back to Gold Lab</Link>
      </Card>
    );
  }

  const campaign = campaignQuery.data;

  if (!isExpertWorkGame(session.game)) {
    return (
      <Card>
        <h1>Expert work</h1>
        <p className="error-box" role="alert">
          Unsupported game selection.
        </p>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
      </Card>
    );
  }

  const candidate = candidatePresentationForGame(session.game);
  if (!isAllowProduction(candidate.gameId, candidate.presentationId)) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted">
          <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
        </p>
        <Card>
          <h1>Expert work</h1>
          <p className="muted" role="status">
            This presentation is not approved for production Gold Mode. Gold
            judgments cannot be submitted with it.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="stack gold-lab-page">
      <p className="muted" style={{ margin: 0 }}>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
      </p>
      {isI2ExpertGame(session.game) ? (
        <GoldWorkSession
          campaignId={campaignId}
          game={session.game}
          campaignClosed={campaign.status === "closed"}
        />
      ) : null}
      {isI3ExpertGame(session.game) && session.game === "evidence_sweep" ? (
        <EvidenceSweepWorkSession
          campaignId={campaignId}
          campaignClosed={campaign.status === "closed"}
        />
      ) : null}
      {isI3ExpertGame(session.game) && session.game === "chunk_duel" ? (
        <ChunkDuelWorkSession
          campaignId={campaignId}
          campaignClosed={campaign.status === "closed"}
        />
      ) : null}
    </div>
  );
}
