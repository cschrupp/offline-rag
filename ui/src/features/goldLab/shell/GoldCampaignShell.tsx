import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Badge } from "../../../components/Badge";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { closeGoldCampaign, listGoldTasks } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import {
  candidatePresentationForGame,
  isAllowProduction,
} from "../policy/presentations";
import { goldLabQueryKeys } from "../queryKeys";
import {
  anchorTaskForCase,
  applySessionConfig,
  caseIdForTask,
  caseIdsInServerOrder,
  eligiblePendingForGame,
  parseSessionConfig,
  pendingTasksMatchingConfig,
  sessionConfigEquals,
  type GoldGameId,
  type GoldSessionConfig,
  type GoldWorkload,
} from "../state/sessionConfig";
import type { GoldCampaign } from "../types";
import { GoldCampaignAdvanced } from "./GoldCampaignAdvanced";
import { GoldContinueAction } from "./GoldContinueAction";
import { GoldGuide } from "./GoldGuide";
import { GoldWorkCard } from "./GoldWorkCard";
import { GoldWorkflowProgress } from "./GoldWorkflowProgress";
import {
  continueAnchorTaskId,
  deriveExpertCampaignState,
} from "./deriveExpertCampaignState";

type Props = {
  campaign: GoldCampaign;
};

export function GoldCampaignShell({ campaign }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);

  const closed = campaign.status === "closed";

  const tasksQuery = useQuery({
    queryKey: goldLabQueryKeys.tasks(campaign.campaign_id),
    queryFn: ({ signal }) => listGoldTasks(campaign.campaign_id, undefined, signal),
  });

  const tasks = useMemo(
    () => tasksQuery.data?.tasks ?? [],
    [tasksQuery.data?.tasks],
  );
  const expertState = useMemo(
    () => deriveExpertCampaignState(tasks),
    [tasks],
  );
  const gameEligiblePending = useMemo(
    () => eligiblePendingForGame(tasks, session.game),
    [tasks, session.game],
  );
  const caseIds = useMemo(
    () => caseIdsInServerOrder(gameEligiblePending),
    [gameEligiblePending],
  );
  const selectedCaseId = caseIdForTask(gameEligiblePending, session.taskId);
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
    },
    onError: (error) => {
      setCloseError(goldLabErrorMessage(error));
      setConfirmClose(false);
    },
  });

  function updateSession(next: GoldSessionConfig) {
    if (sessionConfigEquals(session, next)) return;
    setPrepareError(null);
    setSearchParams(applySessionConfig(searchParams, next), { replace: false });
  }

  function onGameChange(game: GoldGameId) {
    updateSession({ ...session, game, taskId: null });
  }

  function onWorkloadChange(workload: GoldWorkload) {
    if (workload === "case") {
      const currentCase = caseIdForTask(gameEligiblePending, session.taskId);
      const anchor = currentCase
        ? session.taskId
        : caseIds[0]
          ? anchorTaskForCase(gameEligiblePending, caseIds[0])
          : null;
      updateSession({ ...session, workload, taskId: anchor });
      return;
    }
    updateSession({
      ...session,
      workload,
      taskId: null,
    });
  }

  function onCaseChange(caseId: string) {
    const anchor = anchorTaskForCase(gameEligiblePending, caseId);
    updateSession({ ...session, workload: "case", taskId: anchor });
  }

  function navigateToWork(game: GoldGameId, taskId: string | null) {
    const candidate = candidatePresentationForGame(game);
    if (!isAllowProduction(candidate.gameId, candidate.presentationId)) {
      setPrepareError(
        "This presentation is not approved for production Gold Mode.",
      );
      return;
    }
    const next: GoldSessionConfig = {
      game,
      workload: "until_stop",
      taskId,
    };
    const params = applySessionConfig(new URLSearchParams(), next);
    void navigate(
      `/gold-lab/campaigns/${campaign.campaign_id}/work?${params.toString()}`,
    );
  }

  function onContinueGoldWork() {
    setPrepareError(null);
    const game = expertState.nextPrimaryGame;
    if (!game) return;
    navigateToWork(game, continueAnchorTaskId(expertState));
  }

  function onPrepareSession() {
    setPrepareError(null);
    if (session.game !== "question_check" && session.game !== "rapid_fire") {
      setPrepareError(
        "Evidence Sweep and Chunk Duel are not available for production Gold work yet.",
      );
      return;
    }
    const candidate = candidatePresentationForGame(session.game);
    if (!isAllowProduction(candidate.gameId, candidate.presentationId)) {
      setPrepareError(
        "This presentation is not approved for production Gold Mode.",
      );
      return;
    }
    let next: GoldSessionConfig = { ...session };
    if (next.workload === "case") {
      const belongs = gameEligiblePending.some(
        (task) => task.task_id === next.taskId,
      );
      if (!belongs) {
        const firstCase = caseIds[0];
        const anchor = firstCase
          ? anchorTaskForCase(gameEligiblePending, firstCase)
          : null;
        if (!anchor) {
          setPrepareError(
            "No pending tasks match this session configuration.",
          );
          return;
        }
        next = { ...next, taskId: anchor };
      }
    } else {
      const membership = pendingTasksMatchingConfig(tasks, next);
      if (membership.length === 0) {
        setPrepareError(
          "No pending tasks match this session configuration.",
        );
        return;
      }
      if (
        !next.taskId ||
        !membership.some((task) => task.task_id === next.taskId)
      ) {
        next = { ...next, taskId: membership[0]?.task_id ?? null };
      }
    }
    const params = applySessionConfig(new URLSearchParams(), next);
    void navigate(
      `/gold-lab/campaigns/${campaign.campaign_id}/work?${params.toString()}`,
    );
  }

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
          {campaign.corpus_name}
          {" · "}
          {campaign.project_type === "benchmark" ? "Benchmark" : "Improvement"}
        </p>
      </header>

      {tasksQuery.isError ? (
        <section
          className="card"
          data-testid="gold-task-status-error"
          aria-labelledby="gold-task-status-error-heading"
        >
          <h2 id="gold-task-status-error-heading" style={{ marginTop: 0 }}>
            Gold work status unavailable
          </h2>
          <p className="error-box" role="alert">
            Seneca could not load the campaign task state.
            {tasksQuery.error
              ? ` ${goldLabErrorMessage(tasksQuery.error)}`
              : ""}
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              void tasksQuery.refetch();
            }}
          >
            Retry
          </Button>
        </section>
      ) : null}

      {!tasksQuery.isSuccess && !tasksQuery.isError ? (
        <section
          className="card"
          data-testid="gold-task-status-loading"
          role="status"
        >
          <h2 style={{ marginTop: 0 }}>Gold work status</h2>
          <p className="muted" style={{ margin: 0 }}>
            Loading campaign task state…
          </p>
        </section>
      ) : null}

      {tasksQuery.isSuccess ? (
        <>
          {!closed ? <GoldGuide state={expertState} /> : null}

          <GoldWorkflowProgress state={expertState} />

          <GoldContinueAction
            state={expertState}
            closed={closed}
            busy={false}
            onContinue={onContinueGoldWork}
          />

          <section
            className="gold-lab-work-cards"
            aria-label="Gold work activities"
            data-testid="gold-work-cards"
          >
            <GoldWorkCard
              kind="question_check"
              title="Question Check"
              purpose="Review generated questions before evidence judgment."
              status={
                expertState.qcPending > 0
                  ? `${expertState.qcPending} questions remaining`
                  : "Complete"
              }
              actionLabel={
                expertState.qcPending > 0
                  ? expertState.qcReviewed > 0
                    ? "Continue Question Check"
                    : "Start Question Check"
                  : undefined
              }
              onAction={
                expertState.qcPending > 0 && !closed
                  ? () =>
                      navigateToWork(
                        "question_check",
                        expertState.firstQcTaskId,
                      )
                  : undefined
              }
              disabled={closed}
            />
            <GoldWorkCard
              kind="rapid_fire"
              title="Rapid Fire"
              purpose="Judge how strongly a source supports the accepted question."
              status={
                expertState.relevancePending > 0
                  ? `${expertState.relevancePending} evidence judgments ready`
                  : expertState.qcPending > 0
                    ? "Available as accepted questions become ready"
                    : "Complete"
              }
              actionLabel={
                expertState.relevancePending > 0
                  ? expertState.relevanceCompleted > 0
                    ? "Continue Rapid Fire"
                    : "Start Rapid Fire"
                  : undefined
              }
              onAction={
                expertState.relevancePending > 0 && !closed
                  ? () =>
                      navigateToWork("rapid_fire", expertState.firstRfTaskId)
                  : undefined
              }
              disabled={closed}
            />
            <GoldWorkCard
              kind="evidence_sweep"
              title="Evidence Sweep"
              purpose="Optional spatial evidence review."
              status="Optional · Not available yet"
              locked
              lockedReason="Optional. Not available for production Gold work yet."
            />
            <GoldWorkCard
              kind="chunk_duel"
              title="Chunk Duel"
              purpose="Optional preference comparison. Does not create canonical absolute Gold."
              status="Optional · Not available yet"
              locked
              lockedReason="Optional. Not available for production Gold work yet."
            />
          </section>
        </>
      ) : null}

      {prepareError ? (
        <p className="error-box" role="alert">
          {prepareError}
        </p>
      ) : null}

      <GoldCampaignAdvanced
        campaign={campaign}
        closed={closed}
        tasks={tasks}
        tasksLoading={tasksQuery.isLoading}
        tasksError={
          tasksQuery.isError ? goldLabErrorMessage(tasksQuery.error) : null
        }
        sessionGame={session.game}
        sessionWorkload={session.workload}
        caseIds={caseIds}
        selectedCaseId={selectedCaseId}
        matchingPendingCount={matchingPending.length}
        prepareError={null}
        closeError={closeError}
        closeBusy={closeMutation.isPending}
        onGameChange={onGameChange}
        onWorkloadChange={onWorkloadChange}
        onCaseChange={onCaseChange}
        onPrepareSession={onPrepareSession}
        prepareDisabled={
          closed ||
          tasksQuery.isLoading ||
          tasksQuery.isError ||
          matchingPending.length === 0 ||
          (session.workload === "case" && !selectedCaseId)
        }
        onRequestClose={() => {
          setCloseError(null);
          setConfirmClose(true);
        }}
      />

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
