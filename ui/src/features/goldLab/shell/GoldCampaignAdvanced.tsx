import { Link } from "react-router-dom";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { formatTimestamp, shortenId } from "../../workspaces/format";
import type { GoldCampaign, GoldTaskSummary } from "../types";
import { GamePicker } from "./GamePicker";
import { WorkloadChooser } from "./WorkloadChooser";
import type { GoldGameId, GoldWorkload } from "../state/sessionConfig";

type Props = {
  campaign: GoldCampaign;
  closed: boolean;
  tasks: GoldTaskSummary[];
  tasksLoading: boolean;
  tasksError: string | null;
  sessionGame: GoldGameId;
  sessionWorkload: GoldWorkload;
  caseIds: string[];
  selectedCaseId: string | null;
  matchingPendingCount: number;
  prepareError: string | null;
  closeError: string | null;
  closeBusy: boolean;
  onGameChange: (game: GoldGameId) => void;
  onWorkloadChange: (workload: GoldWorkload) => void;
  onCaseChange: (caseId: string) => void;
  onPrepareSession: () => void;
  prepareDisabled: boolean;
  onRequestClose: () => void;
};

const PRODUCTION_GAMES = new Set<GoldGameId>([
  "question_check",
  "rapid_fire",
]);

export function GoldCampaignAdvanced({
  campaign,
  closed,
  tasks,
  tasksLoading,
  tasksError,
  sessionGame,
  sessionWorkload,
  caseIds,
  selectedCaseId,
  matchingPendingCount,
  prepareError,
  closeError,
  closeBusy,
  onGameChange,
  onWorkloadChange,
  onCaseChange,
  onPrepareSession,
  prepareDisabled,
  onRequestClose,
}: Props) {
  const pendingCount = tasks.filter(
    (task) => task.state === "pending" && task.active,
  ).length;
  const completedCount = tasks.filter(
    (task) => task.state === "completed",
  ).length;
  const productionSelected = PRODUCTION_GAMES.has(sessionGame);

  return (
    <details className="card" data-testid="campaign-advanced">
      <summary>Advanced</summary>
      <div className="stack" style={{ marginTop: "0.75rem" }}>
        <p className="muted" style={{ margin: 0 }}>
          Tools for presentation review, provenance, diagnostics, and campaign
          management.
        </p>

        <section>
          <h3>Presentation review</h3>
          <p className="muted">
            Inspect candidate game presentations without writing Gold.
          </p>
          <Button
            to={`/gold-lab/campaigns/${campaign.campaign_id}/presentation-review`}
            variant="secondary"
          >
            Open presentation review
          </Button>
        </section>

        <section>
          <h3>Calibration & training</h3>
          <div className="row" style={{ flexWrap: "wrap" }}>
            <Link to={`/gold-lab/campaigns/${campaign.campaign_id}/calibration`}>
              Calibration
            </Link>
            <Link to={`/gold-lab/campaigns/${campaign.campaign_id}/training`}>
              Training
            </Link>
            <Link
              to={`/gold-lab/campaigns/${campaign.campaign_id}/contribution`}
            >
              Contribution
            </Link>
          </div>
        </section>

        <section>
          <h3>Scientific provenance</h3>
          <dl className="gold-lab-meta">
            <div>
              <dt>Campaign ID</dt>
              <dd>
                <code>{campaign.campaign_id}</code>
              </dd>
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
              <dt>Corpus</dt>
              <dd>{campaign.corpus_name}</dd>
            </div>
            <div>
              <dt>Baseline authoring run</dt>
              <dd>
                <code>{campaign.baseline_authoring_run_id}</code>
              </dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatTimestamp(campaign.created_at)}</dd>
            </div>
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
        </section>

        <section>
          <h3>Custom session configuration</h3>
          {closed ? (
            <p className="muted" role="status">
              Session preparation is disabled because this campaign is closed.
            </p>
          ) : null}
          <div className="stack">
            <GamePicker
              value={sessionGame}
              onChange={onGameChange}
              disabled={closed}
            />
            {!productionSelected ? (
              <p className="muted" role="status">
                Evidence Sweep and Chunk Duel are optional and not available for
                production Gold work yet. Prepare session stays blocked for them.
              </p>
            ) : null}
            <WorkloadChooser
              value={sessionWorkload}
              onChange={onWorkloadChange}
              caseIds={caseIds}
              selectedCaseId={selectedCaseId}
              onCaseChange={onCaseChange}
              disabled={closed}
            />
            {!closed && matchingPendingCount === 0 && productionSelected ? (
              <p className="muted" role="status">
                No pending tasks match this session configuration.
              </p>
            ) : null}
            {!closed && matchingPendingCount > 0 && productionSelected ? (
              <p className="muted" role="status">
                Eligible pending tasks for this configuration:{" "}
                {matchingPendingCount}.
              </p>
            ) : null}
            {prepareError ? (
              <p className="error-box" role="alert">
                {prepareError}
              </p>
            ) : null}
            <Button
              onClick={onPrepareSession}
              disabled={prepareDisabled || !productionSelected}
            >
              Prepare session
            </Button>
          </div>
        </section>

        <section>
          <h3>Workload discovery</h3>
          {tasksLoading ? <p className="muted">Loading tasks…</p> : null}
          {tasksError ? (
            <p className="error-box" role="alert">
              {tasksError}
            </p>
          ) : null}
          {!tasksLoading && !tasksError && tasks.length === 0 ? (
            <EmptyState
              title="No tasks yet."
              body="The campaign task list is empty."
            />
          ) : null}
          {tasks.length > 0 ? (
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
        </section>

        <section>
          <h3>Campaign management</h3>
          {closed ? (
            <p className="muted" role="status">
              This campaign is closed. New expert-session preparation is disabled.
              Reopening is not available.
            </p>
          ) : (
            <>
              <p className="muted">
                Closing is one-way. The campaign remains readable, but new expert
                session preparation is disabled. This is not End session.
              </p>
              {closeError ? (
                <p className="error-box" role="alert">
                  {closeError}
                </p>
              ) : null}
              <Button
                variant="danger"
                onClick={onRequestClose}
                disabled={closeBusy}
              >
                Close campaign
              </Button>
            </>
          )}
        </section>
      </div>
    </details>
  );
}
