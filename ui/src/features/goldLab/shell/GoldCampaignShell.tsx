import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge } from "../../../components/Badge";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { EmptyState } from "../../../components/EmptyState";
import { formatTimestamp, shortenId } from "../../workspaces/format";
import { closeGoldCampaign, listGoldTasks } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";
import {
  anchorTaskForCase,
  applySessionConfig,
  caseIdForTask,
  caseIdsInServerOrder,
  parseSessionConfig,
  pendingTasksMatchingConfig,
  sessionConfigEquals,
  type GoldGameId,
  type GoldSessionConfig,
  type GoldWorkload,
} from "../state/sessionConfig";
import type { GoldCampaign } from "../types";
import { GamePicker } from "./GamePicker";
import { WorkloadChooser } from "./WorkloadChooser";

type Props = {
  campaign: GoldCampaign;
};

export function GoldCampaignShell({ campaign }: Props) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [prepared, setPrepared] = useState(false);

  const closed = campaign.status === "closed";

  const tasksQuery = useQuery({
    queryKey: goldLabQueryKeys.tasks(campaign.campaign_id),
    queryFn: ({ signal }) => listGoldTasks(campaign.campaign_id, undefined, signal),
  });

  const tasks = useMemo(
    () => tasksQuery.data?.tasks ?? [],
    [tasksQuery.data?.tasks],
  );
  const caseIds = useMemo(() => caseIdsInServerOrder(tasks), [tasks]);
  const selectedCaseId = caseIdForTask(tasks, session.taskId);
  const matchingPending = useMemo(
    () => pendingTasksMatchingConfig(tasks, session),
    [tasks, session],
  );

  const closeMutation = useMutation({
    mutationFn: () => closeGoldCampaign(campaign.campaign_id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.campaign(campaign.campaign_id),
        }),
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.campaigns(campaign.project_id),
        }),
      ]);
      setConfirmClose(false);
      setCloseError(null);
      setPrepared(false);
    },
    onError: (error) => {
      setCloseError(goldLabErrorMessage(error));
      setConfirmClose(false);
    },
  });

  function updateSession(next: GoldSessionConfig) {
    if (sessionConfigEquals(session, next)) return;
    setPrepared(false);
    setSearchParams(applySessionConfig(searchParams, next), { replace: false });
  }

  function onGameChange(game: GoldGameId) {
    updateSession({ ...session, game });
  }

  function onWorkloadChange(workload: GoldWorkload) {
    if (workload === "case") {
      const anchor =
        session.taskId && caseIdForTask(tasks, session.taskId)
          ? session.taskId
          : caseIds[0]
            ? anchorTaskForCase(tasks, caseIds[0])
            : null;
      updateSession({ ...session, workload, taskId: anchor });
      return;
    }
    updateSession({
      ...session,
      workload,
      taskId: workload === "until_stop" ? session.taskId : session.taskId,
    });
  }

  function onCaseChange(caseId: string) {
    const anchor = anchorTaskForCase(tasks, caseId);
    updateSession({ ...session, workload: "case", taskId: anchor });
  }

  const pendingCount = tasks.filter(
    (task) => task.state === "pending" && task.active,
  ).length;
  const completedCount = tasks.filter(
    (task) => task.state === "completed",
  ).length;

  return (
    <div className="stack gold-lab-page">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <p className="muted" style={{ margin: 0 }}>
          <Link to={`/gold-lab/projects/${campaign.project_id}`}>
            Back to project
          </Link>
        </p>
        <div className="row gold-lab-card-header">
          <h1 style={{ margin: 0 }}>Campaign</h1>
          <Badge
            tone={closed ? "empty" : "ready"}
            label={closed ? "Closed" : "Open"}
          />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          <code>{campaign.campaign_id}</code>
        </p>
      </header>

      <Card>
        <h2>Campaign binding</h2>
        <dl className="gold-lab-meta">
          <div>
            <dt>Status</dt>
            <dd>{closed ? "Closed" : "Open"}</dd>
          </div>
          <div>
            <dt>Project</dt>
            <dd>
              <Link to={`/gold-lab/projects/${campaign.project_id}`}>
                {campaign.project_id}
              </Link>
            </dd>
          </div>
          <div>
            <dt>Project type</dt>
            <dd>
              {campaign.project_type === "benchmark"
                ? "Benchmark"
                : "Improvement"}
            </dd>
          </div>
          <div>
            <dt>Baseline authoring run</dt>
            <dd>
              <code>{campaign.baseline_authoring_run_id}</code>
            </dd>
          </div>
          <div>
            <dt>Corpus</dt>
            <dd>{campaign.corpus_name}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatTimestamp(campaign.created_at)}</dd>
          </div>
        </dl>
        <details className="gold-lab-provenance">
          <summary>Scientific provenance</summary>
          <dl className="gold-lab-meta">
            <div>
              <dt>Snapshot</dt>
              <dd>
                <code>{campaign.snapshot_id}</code>
              </dd>
            </div>
            <div>
              <dt>Chunk set</dt>
              <dd>
                <code>{campaign.chunk_set_id}</code>
              </dd>
            </div>
            <div>
              <dt>Corpus ID</dt>
              <dd>
                <code>{shortenId(campaign.corpus_id, 24)}</code>
              </dd>
            </div>
            <div>
              <dt>Workspace revision at creation</dt>
              <dd>{campaign.workspace_revision_at_creation}</dd>
            </div>
            <div>
              <dt>Workspace</dt>
              <dd>
                <code>{campaign.workspace_id}</code>
              </dd>
            </div>
          </dl>
        </details>
      </Card>

      {!closed ? (
        <Card>
          <h2>Close campaign</h2>
          <p className="muted">
            Closing is one-way. The campaign remains readable, but new expert
            session preparation is disabled.
          </p>
          {closeError ? (
            <p className="error-box" role="alert">
              {closeError}
            </p>
          ) : null}
          <Button
            variant="danger"
            onClick={() => {
              setCloseError(null);
              setConfirmClose(true);
            }}
            disabled={closeMutation.isPending}
          >
            Close campaign
          </Button>
        </Card>
      ) : (
        <Card>
          <h2>Campaign closed</h2>
          <p className="muted" role="status">
            This campaign is closed. New expert-session preparation is disabled.
            Reopening is not available.
          </p>
        </Card>
      )}

      <Card>
        <h2>Workload discovery</h2>
        {tasksQuery.isLoading ? (
          <p className="muted">Loading tasks…</p>
        ) : null}
        {tasksQuery.isError ? (
          <p className="error-box" role="alert">
            {goldLabErrorMessage(tasksQuery.error)}
          </p>
        ) : null}
        {tasksQuery.isSuccess && tasks.length === 0 ? (
          <EmptyState
            title="No tasks yet."
            body="The campaign task list is empty. Expert adjudication is not started from this screen."
          />
        ) : null}
        {tasksQuery.isSuccess && tasks.length > 0 ? (
          <>
            <p className="muted">
              Pending (active): {pendingCount}. Completed: {completedCount}.
              Server order is preserved.
            </p>
            <ol className="gold-lab-task-order">
              {tasks.map((task) => (
                <li key={task.task_id}>
                  <code>{task.task_id}</code>
                  {" · "}
                  {task.task_kind}
                  {" · "}
                  {task.state}
                  {task.active ? "" : " · inactive"}
                  {" · case "}
                  <code>{task.case_id}</code>
                </li>
              ))}
            </ol>
          </>
        ) : null}
      </Card>

      <Card>
        <h2>Session configuration</h2>
        {closed ? (
          <p className="muted" role="status">
            Session preparation is disabled because this campaign is closed.
          </p>
        ) : null}
        <div className="stack">
          <GamePicker
            value={session.game}
            onChange={onGameChange}
            disabled={closed}
          />
          <WorkloadChooser
            value={session.workload}
            onChange={onWorkloadChange}
            caseIds={caseIds}
            selectedCaseId={selectedCaseId}
            onCaseChange={onCaseChange}
            disabled={closed}
          />

          {!closed && tasksQuery.isSuccess && matchingPending.length === 0 ? (
            <p className="muted" role="status">
              No pending tasks match this session configuration.
            </p>
          ) : null}

          {!closed && matchingPending.length > 0 ? (
            <p className="muted" role="status">
              Eligible pending tasks for this configuration:{" "}
              {matchingPending.length}.
              {session.workload === "case" && selectedCaseId
                ? ` Case ${selectedCaseId}.`
                : null}
            </p>
          ) : null}

          {prepared ? (
            <p className="gold-lab-ready" role="status">
              Session configuration is ready. Expert task execution is not
              available in this build.
            </p>
          ) : null}

          <div className="row">
            <Button
              onClick={() => setPrepared(true)}
              disabled={
                closed ||
                tasksQuery.isLoading ||
                tasksQuery.isError ||
                (session.workload === "case" && !selectedCaseId)
              }
            >
              Prepare session
            </Button>
          </div>
        </div>
      </Card>

      <ConfirmDialog
        open={confirmClose}
        title="Close this campaign?"
        body="Closing is permanent. The campaign stays readable, but new expert-session preparation will be disabled."
        confirmLabel="Close campaign"
        danger
        busy={closeMutation.isPending}
        onConfirm={() => closeMutation.mutate()}
        onCancel={() => setConfirmClose(false)}
      />
    </div>
  );
}
