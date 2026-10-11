import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import {
  getGoldCampaign,
  getGoldTrainingPackage,
  listGoldRegistrations,
} from "../features/goldLab/api/client";
import {
  goldLabErrorMessage,
  isGoldStateUnavailable,
} from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import { compileTrainingPackage } from "../features/goldLab/training/compiler";
import { ScenarioWorkspace } from "../features/goldLab/training/scenario/ScenarioWorkspace";
import type { ScenarioAuthority } from "../features/goldLab/training/types";
import { formatTimestamp, shortenId } from "../features/workspaces/format";

export function GoldLabTrainingScenarioPage() {
  const { campaignId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const datasetFromQuery = searchParams.get("dataset");
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(
    datasetFromQuery,
  );
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const [scenarioKey, setScenarioKey] = useState(0);

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

  const compiled = useMemo(
    () =>
      packageQuery.data ? compileTrainingPackage(packageQuery.data) : null,
    [packageQuery.data],
  );

  const exercise = compiled?.scenarios[scenarioIndex] ?? null;

  function selectDataset(datasetId: string) {
    setSelectedDatasetId(datasetId);
    setScenarioIndex(0);
    setScenarioKey((value) => value + 1);
    setSearchParams({ dataset: datasetId }, { replace: true });
  }

  if (!campaignId) {
    return (
      <Card>
        <h1>Training scenario</h1>
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
        <p className="muted">Loading scenario…</p>
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return (
      <Card>
        <h1>Training scenario</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(campaignQuery.error)}
        </p>
      </Card>
    );
  }

  if (registrationsQuery.isError || !registrationsQuery.data) {
    return (
      <div className="stack gold-lab-page">
        <Card>
          <h1>Training scenario</h1>
          <p className="error-box" role="alert">
            {goldLabErrorMessage(registrationsQuery.error)}
          </p>
          {isGoldStateUnavailable(registrationsQuery.error) ? (
            <p className="muted" role="status">
              Scenario cannot bind an immutable package until Gold Lab state is
              available.
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
        <Link to={`/gold-lab/campaigns/${campaignId}/training`}>
          Back to Training
        </Link>
      </p>

      {!selectedDatasetId ? (
        <Card>
          <h1>Scenario / debrief</h1>
          <h2>Select a registered dataset</h2>
          {registrations.length === 0 ? (
            <p className="muted" role="status">
              No registered Gold dataset is available for Training. Export and
              register adjudicated Gold before Training can begin.
            </p>
          ) : (
            <ul className="gold-lab-list">
              {registrations.map((row) => (
                <li key={row.dataset_id}>
                  <div className="row gold-lab-card-header">
                    <code>{shortenId(row.dataset_id, 28)}</code>
                    <Button
                      variant="secondary"
                      onClick={() => selectDataset(row.dataset_id)}
                    >
                      Use for scenario
                    </Button>
                  </div>
                  <p className="muted">
                    Registered {formatTimestamp(row.registered_at)}
                  </p>
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
          <Button
            variant="secondary"
            onClick={() => {
              setSelectedDatasetId(null);
              setSearchParams({}, { replace: true });
            }}
          >
            Choose another registration
          </Button>
        </Card>
      ) : null}

      {compiled && exercise ? (
        <>
          <p className="muted">
            Scenario {scenarioIndex + 1} of {compiled.scenarios.length}
          </p>
          <ScenarioWorkspace
            key={`${exercise.exerciseId}-${scenarioKey}`}
            exercise={exercise}
            resolveAuthorityAfterCommit={() =>
              compiled.authorityByExerciseId.get(exercise.exerciseId) as
                | ScenarioAuthority
                | undefined
            }
            onRestart={() => setScenarioKey((value) => value + 1)}
          />
          {scenarioIndex + 1 < compiled.scenarios.length ? (
            <Button
              variant="secondary"
              onClick={() => {
                setScenarioIndex((value) => value + 1);
                setScenarioKey((value) => value + 1);
              }}
            >
              Next scenario case
            </Button>
          ) : null}
        </>
      ) : null}

      {compiled && compiled.scenarios.length === 0 && packageQuery.isSuccess ? (
        <Card>
          <p className="muted" role="status">
            No scenario exercises could be compiled from this registered
            package.
          </p>
        </Card>
      ) : null}
    </div>
  );
}
