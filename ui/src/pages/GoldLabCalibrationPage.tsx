import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import {
  getGoldCampaign,
  getGoldTrainingPackage,
  listGoldRegistrations,
} from "../features/goldLab/api/client";
import { CalibrationWorkspace } from "../features/goldLab/calibration/CalibrationWorkspace";
import {
  goldLabErrorMessage,
  isGoldStateUnavailable,
} from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import type { GoldRegistrationSummary } from "../features/goldLab/types";
import { formatTimestamp, shortenId } from "../features/workspaces/format";

export function GoldLabCalibrationPage() {
  const { campaignId = "" } = useParams();
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(
    null,
  );

  const campaignQuery = useQuery({
    queryKey: goldLabQueryKeys.campaign(campaignId),
    queryFn: ({ signal }) => getGoldCampaign(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  const registrationsQuery = useQuery({
    queryKey: goldLabQueryKeys.registrations(campaignId),
    queryFn: ({ signal }) => listGoldRegistrations(campaignId, signal),
    enabled: Boolean(campaignId),
  });

  const packageQuery = useQuery({
    queryKey: goldLabQueryKeys.trainingPackage(
      campaignId,
      selectedDatasetId ?? "",
    ),
    queryFn: ({ signal }) =>
      getGoldTrainingPackage(campaignId, selectedDatasetId!, signal),
    enabled: Boolean(campaignId && selectedDatasetId),
  });

  const selectedRegistration: GoldRegistrationSummary | null = useMemo(() => {
    if (!selectedDatasetId || !registrationsQuery.data) return null;
    return (
      registrationsQuery.data.registrations.find(
        (row) => row.dataset_id === selectedDatasetId,
      ) ?? null
    );
  }, [registrationsQuery.data, selectedDatasetId]);

  if (!campaignId) {
    return (
      <Card>
        <h1>Calibration</h1>
        <p className="error-box" role="alert">
          Missing campaign identity.
        </p>
        <Button to="/gold-lab">Back to Gold Lab</Button>
      </Card>
    );
  }

  if (campaignQuery.isLoading || registrationsQuery.isLoading) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted">Loading calibration…</p>
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <Card>
        <h1>Calibration</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
        <p>
          <Link to="/gold-lab">Back to Gold Lab</Link>
        </p>
      </Card>
    );
  }

  if (registrationsQuery.isError || !registrationsQuery.data) {
    const failClosed = isGoldStateUnavailable(registrationsQuery.error);
    return (
      <div className="stack gold-lab-page">
        <p className="muted" style={{ margin: 0 }}>
          <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
        </p>
        <Card>
          <h1>Calibration</h1>
          <p className="error-box" role="alert">
            {goldLabErrorMessage(registrationsQuery.error)}
          </p>
          {failClosed ? (
            <p className="muted" role="status">
              Calibration cannot safely bind evidence until Gold Lab state is
              available again.
            </p>
          ) : null}
        </Card>
      </div>
    );
  }

  const registrations = registrationsQuery.data.registrations;

  return (
    <div className="stack gold-lab-page">
      <p className="muted" style={{ margin: 0 }}>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
        {" · "}
        <Link to={`/gold-lab/campaigns/${campaignId}/contribution`}>
          Contribution
        </Link>
      </p>
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Calibration</h1>
        <p className="muted" style={{ margin: 0 }}>
          Local observational presentation evidence against an immutable
          training/calibration package. This never mutates Gold.
        </p>
      </header>

      {!selectedDatasetId ? (
        <Card>
          <h2>Select a registered dataset</h2>
          {registrations.length === 0 ? (
            <p className="muted" role="status" data-testid="calibration-no-regs">
              No registered Gold dataset is available for calibration. Export
              and register adjudicated Gold before calibration can begin.
            </p>
          ) : (
            <ul className="gold-lab-list">
              {registrations.map((row) => (
                <li key={row.dataset_id}>
                  <div className="stack" style={{ gap: "0.35rem" }}>
                    <div className="row gold-lab-card-header">
                      <code>{shortenId(row.dataset_id, 28)}</code>
                      <Button
                        variant="secondary"
                        onClick={() => setSelectedDatasetId(row.dataset_id)}
                      >
                        Use for calibration
                      </Button>
                    </div>
                    <p className="muted" style={{ margin: 0 }}>
                      Registered {formatTimestamp(row.registered_at)} ·{" "}
                      {row.exported_case_ids.length} exported cases · projection{" "}
                      <code>{row.projection_sha256.slice(0, 12)}…</code>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {selectedDatasetId && packageQuery.isLoading ? (
        <p className="muted">Loading training package…</p>
      ) : null}

      {selectedDatasetId && packageQuery.isError ? (
        <Card>
          <p className="error-box" role="alert">
            {goldLabErrorMessage(packageQuery.error)}
          </p>
          <p className="muted" role="status">
            {isGoldStateUnavailable(packageQuery.error) ||
            (packageQuery.error &&
              typeof packageQuery.error === "object" &&
              "code" in packageQuery.error &&
              (packageQuery.error as { code: string }).code ===
                "unexpected_response")
              ? "Calibration cannot start with an unavailable or incoherent package."
              : null}
          </p>
          <Button
            variant="secondary"
            onClick={() => setSelectedDatasetId(null)}
          >
            Choose another registration
          </Button>
        </Card>
      ) : null}

      {selectedDatasetId &&
      packageQuery.isSuccess &&
      packageQuery.data &&
      selectedRegistration ? (
        <CalibrationWorkspace
          key={selectedDatasetId}
          pkg={packageQuery.data}
          registration={selectedRegistration}
          onClearSelection={() => setSelectedDatasetId(null)}
        />
      ) : null}
    </div>
  );
}
