import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "../../../components/Badge";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { EmptyState } from "../../../components/EmptyState";
import { formatTimestamp } from "../../workspaces/format";
import {
  archiveGoldProject,
  listGoldBaselines,
  listGoldCampaigns,
} from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";
import type { GoldProject } from "../types";
import { GoldCampaignCreateForm } from "./GoldCampaignCreateForm";

type Props = {
  project: GoldProject;
};

export function GoldProjectDetail({ project }: Props) {
  const queryClient = useQueryClient();
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const baselinesQuery = useQuery({
    queryKey: goldLabQueryKeys.baselines(project.project_id),
    queryFn: ({ signal }) => listGoldBaselines(project.project_id, signal),
  });

  const campaignsQuery = useQuery({
    queryKey: goldLabQueryKeys.campaigns(project.project_id),
    queryFn: ({ signal }) => listGoldCampaigns(project.project_id, signal),
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveGoldProject(project.project_id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.project(project.project_id),
        }),
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.projects,
        }),
      ]);
      setConfirmArchive(false);
      setArchiveError(null);
    },
    onError: (error) => {
      setArchiveError(goldLabErrorMessage(error));
      setConfirmArchive(false);
    },
  });

  const archived = project.status === "archived";
  const baselines = baselinesQuery.data?.baselines ?? [];
  const campaigns = campaignsQuery.data?.campaigns ?? [];
  const canCreateCampaign =
    !archived && baselinesQuery.isSuccess && baselines.length > 0;

  let createDisabledReason: string | undefined;
  if (archived) {
    createDisabledReason =
      "This project is archived. New campaigns cannot be created.";
  } else if (baselinesQuery.isSuccess && baselines.length === 0) {
    createDisabledReason =
      "No eligible pristine authoring baselines are available for this project.";
  } else if (baselinesQuery.isError) {
    createDisabledReason =
      "Baselines could not be loaded. Campaign creation is disabled until baselines are available.";
  } else if (baselinesQuery.isLoading) {
    createDisabledReason = "Loading eligible baselines…";
  }

  return (
    <div className="stack gold-lab-page">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <p className="muted" style={{ margin: 0 }}>
          <Link to="/gold-lab">Back to Gold Lab</Link>
        </p>
        <div className="row gold-lab-card-header">
          <h1 style={{ margin: 0 }}>{project.title}</h1>
          <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
            <Badge
              tone={project.project_type === "benchmark" ? "ready" : "busy"}
              label={
                project.project_type === "benchmark"
                  ? "Benchmark"
                  : "Improvement"
              }
            />
            <Badge
              tone={archived ? "empty" : "ready"}
              label={archived ? "Archived" : "Active"}
            />
          </div>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          {project.description || "No description"}
        </p>
      </header>

      <Card>
        <h2>Project details</h2>
        <dl className="gold-lab-meta">
          <div>
            <dt>Workspace</dt>
            <dd>
              <code>{project.workspace_id}</code>
            </dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>
              {project.project_type === "benchmark"
                ? "Benchmark"
                : "Improvement"}
            </dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{archived ? "Archived" : "Active"}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatTimestamp(project.created_at)}</dd>
          </div>
          <div>
            <dt>Project ID</dt>
            <dd>
              <code>{project.project_id}</code>
            </dd>
          </div>
        </dl>
      </Card>

      {!archived ? (
        <Card>
          <h2>Archive project</h2>
          <p className="muted">
            Archiving is one-way. Existing campaigns remain readable; new
            campaign creation is disabled.
          </p>
          {archiveError ? (
            <p className="error-box" role="alert">
              {archiveError}
            </p>
          ) : null}
          <Button
            variant="danger"
            onClick={() => {
              setArchiveError(null);
              setConfirmArchive(true);
            }}
            disabled={archiveMutation.isPending}
          >
            Archive project
          </Button>
        </Card>
      ) : null}

      <Card>
        <h2>Eligible baselines</h2>
        {baselinesQuery.isLoading ? (
          <p className="muted">Loading baselines…</p>
        ) : null}
        {baselinesQuery.isError ? (
          <p className="error-box" role="alert">
            {goldLabErrorMessage(baselinesQuery.error)}
          </p>
        ) : null}
        {baselinesQuery.isSuccess && baselines.length === 0 ? (
          <EmptyState
            title="No eligible pristine authoring baselines are available for this project."
            body="Campaign creation stays disabled until the server reports an eligible baseline. Seneca does not synthesize baselines in the browser."
          />
        ) : null}
        {baselines.length > 0 ? (
          <ul className="stack gold-lab-list">
            {baselines.map((baseline) => (
              <li key={baseline.authoring_run_id}>
                <article className="gold-lab-baseline">
                  <h3>{baseline.corpus_name}</h3>
                  <dl className="gold-lab-meta">
                    <div>
                      <dt>Authoring run</dt>
                      <dd>
                        <code>{baseline.authoring_run_id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatTimestamp(baseline.created_at)}</dd>
                    </div>
                    <div>
                      <dt>Chunk set</dt>
                      <dd>
                        <code>{baseline.chunk_set_id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Cases</dt>
                      <dd>
                        {baseline.case_count} total /{" "}
                        {baseline.reviewable_case_count} reviewable
                      </dd>
                    </div>
                  </dl>
                </article>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      <Card>
        <h2>Campaigns</h2>
        {campaignsQuery.isLoading ? (
          <p className="muted">Loading campaigns…</p>
        ) : null}
        {campaignsQuery.isError ? (
          <p className="error-box" role="alert">
            {goldLabErrorMessage(campaignsQuery.error)}
          </p>
        ) : null}
        {campaignsQuery.isSuccess && campaigns.length === 0 ? (
          <EmptyState
            title="No campaigns yet."
            body="Create a campaign from an eligible baseline when this project is active."
          />
        ) : null}
        {campaigns.length > 0 ? (
          <ul className="stack gold-lab-list">
            {campaigns.map((campaign) => (
              <li key={campaign.campaign_id}>
                <div className="row gold-lab-card-header">
                  <div className="stack" style={{ gap: "0.25rem" }}>
                    <Link to={`/gold-lab/campaigns/${campaign.campaign_id}`}>
                      <code>{campaign.campaign_id}</code>
                    </Link>
                    <span className="muted">
                      {campaign.corpus_name} ·{" "}
                      {formatTimestamp(campaign.created_at)}
                    </span>
                  </div>
                  <Badge
                    tone={campaign.status === "open" ? "ready" : "empty"}
                    label={campaign.status === "open" ? "Open" : "Closed"}
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      <GoldCampaignCreateForm
        projectId={project.project_id}
        baselines={baselines}
        disabled={!canCreateCampaign}
        disabledReason={createDisabledReason}
      />

      <ConfirmDialog
        open={confirmArchive}
        title="Archive this Gold project?"
        body="Archiving is permanent. Campaigns remain readable, but you will not be able to create new campaigns for this project."
        confirmLabel="Archive project"
        danger
        busy={archiveMutation.isPending}
        onConfirm={() => archiveMutation.mutate()}
        onCancel={() => setConfirmArchive(false)}
      />
    </div>
  );
}
