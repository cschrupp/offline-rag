import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getOperation, listWorkspaces } from "../api/client";
import { OperationProgress } from "../components/OperationProgress";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { queryKeys } from "../api/queryKeys";
import {
  getQuickPlayState,
  prepareQuickPlay,
  type QuickPlayState,
} from "../features/goldLab/api/quickPlay";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import {
  forgetActiveOperation,
  isTerminalOperationStatus,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import { userFacingErrorMessage } from "../api/errors";

const QUICK_PLAY_WORKSPACE_KEY = "offline-rag.quick-play.workspace.v1";

function newIdempotencyKey(): string {
  return `quick-play-${crypto.randomUUID()}`;
}

function gamePath(
  campaignId: string,
  game: string,
  workspaceId: string,
): string {
  const params = new URLSearchParams({
    game,
    return_to: "quick_play",
    quick_play_workspace: workspaceId,
  });
  return `/gold-lab/campaigns/${encodeURIComponent(campaignId)}/work?${params.toString()}`;
}

function actionLabel(status: QuickPlayState["status"]): string {
  switch (status) {
    case "needs_generation":
      return "Generate deck";
    case "baseline_available":
      return "Use existing deck";
    case "campaign_ready":
      return "Continue to deck";
    case "generation_failed":
      return "Retry generation";
    case "complete":
      return "Replenish deck";
    default:
      return "Prepare deck";
  }
}

export function GoldLabQuickPlayPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const autoContinueProject = useRef<string | null>(null);
  const workspaceId = searchParams.get("workspace") ?? "";

  const workspacesQuery = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });
  const workspaces = (workspacesQuery.data ?? []).filter(
    (workspace) => workspace.status !== "tombstoned",
  );
  const selectedWorkspace = workspaces.find(
    (workspace) => workspace.workspace_id === workspaceId,
  );

  useEffect(() => {
    if (workspaceId || !workspacesQuery.data?.length) return;
    const rememberedWorkspaceId = localStorage.getItem(QUICK_PLAY_WORKSPACE_KEY);
    if (
      rememberedWorkspaceId &&
      workspacesQuery.data.some(
        (workspace) => workspace.workspace_id === rememberedWorkspaceId,
      )
    ) {
      setSearchParams({ workspace: rememberedWorkspaceId }, { replace: true });
    }
  }, [setSearchParams, workspaceId, workspacesQuery.data]);

  const stateQuery = useQuery({
    queryKey: goldLabQueryKeys.quickPlay(workspaceId),
    queryFn: ({ signal }) => getQuickPlayState(workspaceId, signal),
    enabled: Boolean(workspaceId),
    refetchInterval: (query) =>
      query.state.data?.status === "generating" ? 1500 : 5000,
  });
  const state = stateQuery.data;
  const operationId = state?.operation?.operation_id;
  const operationQuery = useQuery({
    queryKey: queryKeys.operation(operationId ?? ""),
    queryFn: ({ signal }) => getOperation(operationId!, signal),
    enabled: Boolean(operationId && state?.status === "generating"),
    refetchInterval: (query) =>
      query.state.data && !isTerminalOperationStatus(query.state.data.status)
        ? 1500
        : false,
  });

  const prepareMutation = useMutation({
    mutationFn: (action: "start" | "replenish") =>
      prepareQuickPlay({
        workspaceId,
        action,
        idempotencyKey: newIdempotencyKey(),
      }),
    onSuccess: (result) => {
      autoContinueProject.current = null;
      queryClient.setQueryData(
        goldLabQueryKeys.quickPlay(workspaceId),
        result,
      );
      if (result.status === "generating") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
      }
    },
    onError: () => {
      autoContinueProject.current = null;
    },
  });
  const prepareDeck = prepareMutation.mutate;

  useEffect(() => {
    if (state?.status !== "generating" || !state.operation) return;
    rememberActiveOperation({
      operation_id: state.operation.operation_id,
      workspace_id: state.workspace_id,
      kind: "gold_lab_baseline_bootstrap",
      label: "Generating Quick Play deck",
    });
  }, [state?.operation, state?.status, state?.workspace_id]);

  useEffect(() => {
    const operation = operationQuery.data;
    if (operation && isTerminalOperationStatus(operation.status)) {
      forgetActiveOperation(operation.operation_id);
      void queryClient.invalidateQueries({
        queryKey: goldLabQueryKeys.quickPlay(workspaceId),
      });
    }
  }, [operationQuery.data, queryClient, workspaceId]);

  useEffect(() => {
    if (state?.status !== "campaign_ready" || !state.project_id) return;
    if (autoContinueProject.current === state.project_id) return;
    autoContinueProject.current = state.project_id;
    prepareDeck("start");
  }, [prepareDeck, state?.status, state?.project_id]);

  function selectWorkspace(nextWorkspaceId: string) {
    autoContinueProject.current = null;
    if (nextWorkspaceId) {
      localStorage.setItem(QUICK_PLAY_WORKSPACE_KEY, nextWorkspaceId);
      setSearchParams({ workspace: nextWorkspaceId }, { replace: true });
    } else {
      localStorage.removeItem(QUICK_PLAY_WORKSPACE_KEY);
      setSearchParams({}, { replace: true });
    }
  }

  function prepareCurrentDeck() {
    if (!state) return;
    prepareMutation.mutate(state.status === "complete" ? "replenish" : "start");
  }

  const operation = operationQuery.data;
  const availableGames = state?.available_games ?? [];
  const campaignId = state?.campaign_id;
  const nextGame = availableGames.find(
    (game) => game.game_id === state?.next_game,
  );

  return (
    <div className="stack gold-lab-page quick-play-page">
      <header className="row gold-lab-card-header">
        <div>
          <h1>Quick Play</h1>
          <p className="muted">
            Review proposed questions and judge their evidence. Your
            contributions are saved as you play.
          </p>
        </div>
        <Button variant="secondary" to="/gold-lab/advanced">
          Advanced Gold Lab
        </Button>
      </header>

      <Card className="stack">
        <label htmlFor="quick-play-workspace">
          <strong>Workspace</strong>
        </label>
        {workspacesQuery.isLoading ? <p>Loading workspaces…</p> : null}
        {workspacesQuery.isError ? (
          <p className="error-box" role="alert">
            {userFacingErrorMessage(workspacesQuery.error)}
          </p>
        ) : null}
        {!workspacesQuery.isLoading && workspaces.length === 0 ? (
          <p className="muted">Create a workspace and add sources to begin.</p>
        ) : null}
        {workspaces.length > 0 ? (
          <select
            id="quick-play-workspace"
            value={workspaceId}
            onChange={(event) => selectWorkspace(event.target.value)}
          >
            <option value="">Choose a workspace</option>
            {workspaces.map((workspace) => (
              <option key={workspace.workspace_id} value={workspace.workspace_id}>
                {workspace.title}
                {workspace.current_snapshot_id ? "" : " · No published sources"}
              </option>
            ))}
          </select>
        ) : null}
        {selectedWorkspace ? (
          <p className="muted">
            {selectedWorkspace.source_count.toLocaleString()} active{" "}
            {selectedWorkspace.source_count === 1 ? "source" : "sources"}
          </p>
        ) : null}
      </Card>

      {!workspaceId ? (
        <Card>
          <p>Select a workspace to check for an activity deck.</p>
        </Card>
      ) : null}
      {stateQuery.isLoading && workspaceId ? <Card>Checking your deck…</Card> : null}
      {stateQuery.isError ? (
        <Card>
          <p className="error-box" role="alert">
            {userFacingErrorMessage(stateQuery.error)}
          </p>
          <Button variant="secondary" onClick={() => void stateQuery.refetch()}>
            Check again
          </Button>
        </Card>
      ) : null}
      {state?.status === "not_ready" ? (
        <Card>
          <h2>Publish workspace sources first</h2>
          <p>This workspace has no published source snapshot to play from.</p>
          <Button variant="secondary" to={`/workspaces/${workspaceId}`}>
            Open workspace
          </Button>
        </Card>
      ) : null}
      {state?.status === "blocked" ? (
        <Card>
          <h2>Deck unavailable</h2>
          <p>
            This deck cannot accept more judgments. Your existing work is
            preserved; contact an administrator to review the campaign.
          </p>
        </Card>
      ) : null}
      {state?.status === "empty_population" ? (
        <Card>
          <h2>No suitable source text yet</h2>
          <p>
            Quick Play needs published source chunks with readable text. Add
            or update workspace sources, publish the workspace, then try again.
          </p>
          <Button variant="secondary" to={`/workspaces/${workspaceId}`}>
            Open workspace
          </Button>
        </Card>
      ) : null}
      {state?.status === "generating" ? (
        <section className="stack" aria-live="polite">
          <h2>Generating your activity deck</h2>
          {operation ? (
            <OperationProgress
              phase="operation"
              operation={operation}
              label="Generating activity deck"
              successMessage="Your activity deck is ready."
            />
          ) : (
            <Card>Recovering generation progress…</Card>
          )}
        </section>
      ) : null}
      {state?.status === "generation_failed" ? (
        <Card className="stack">
          <h2>Deck generation did not finish</h2>
          {operation ? (
            <OperationProgress
              phase="operation"
              operation={operation}
              label="Activity deck generation"
            />
          ) : (
            <p role="alert">
              {state.operation?.failure_summary ??
                "Generation stopped. Your existing workspace and contributions are unchanged."}
            </p>
          )}
          <Button
            onClick={prepareCurrentDeck}
            disabled={prepareMutation.isPending}
          >
            Retry generation
          </Button>
        </Card>
      ) : null}
      {state &&
      ["needs_generation", "baseline_available", "campaign_ready"].includes(
        state.status,
      ) ? (
        <Card className="stack">
          <h2>
            {state.status === "needs_generation"
              ? "Create an activity deck"
              : state.status === "baseline_available"
                ? "A reusable deck is available"
                : "Opening your deck"}
          </h2>
          <p>
            Quick Play selects improvement-oriented cases from this published
            workspace. It is for expert review, not a representative benchmark.
          </p>
          {state.status !== "campaign_ready" ? (
            <Button
              onClick={prepareCurrentDeck}
              disabled={
                prepareMutation.isPending ||
                !selectedWorkspace?.current_snapshot_id
              }
            >
              {prepareMutation.isPending ? "Preparing…" : actionLabel(state.status)}
            </Button>
          ) : prepareMutation.isError ? (
            <Button
              onClick={prepareCurrentDeck}
              disabled={prepareMutation.isPending}
            >
              Retry deck setup
            </Button>
          ) : (
            <p aria-live="polite">Preparing the playable deck…</p>
          )}
          {prepareMutation.isError ? (
            <p className="error-box" role="alert">
              {userFacingErrorMessage(prepareMutation.error)}
              {" "}
              Retry to reconcile the saved deck state.
            </p>
          ) : null}
        </Card>
      ) : null}
      {state?.status === "playable" && campaignId ? (
        <Card className="stack">
          <h2>Your deck is ready</h2>
          <p>
            {state.question_check_pending ?? 0} questions to review ·{" "}
            {state.rapid_fire_pending ?? 0} evidence judgments available
          </p>
          <div className="row">
            {nextGame ? (
              <Button
                to={gamePath(campaignId, nextGame.game_id, workspaceId)}
              >
                Resume Play · {nextGame.label}
              </Button>
            ) : null}
          </div>
          {availableGames.length > 1 ? (
            <div className="stack">
              <h3>Play another available game</h3>
              <div className="row">
                {availableGames
                  .filter((game) => game.game_id !== nextGame?.game_id)
                  .map((game) => (
                    <Button
                      key={game.game_id}
                      variant="secondary"
                      to={gamePath(campaignId, game.game_id, workspaceId)}
                    >
                      {game.label} · {game.pending_count}
                    </Button>
                  ))}
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}
      {state?.status === "complete" ? (
        <Card className="stack">
          <h2>This deck is complete</h2>
          <p>
            Existing judgments remain saved. Replenishing creates another
            activity set without replacing your completed work.
          </p>
          <Button
            onClick={prepareCurrentDeck}
            disabled={prepareMutation.isPending}
          >
            {prepareMutation.isPending ? "Preparing…" : "Replenish deck"}
          </Button>
        </Card>
      ) : null}

      <footer>
        <Link to="/gold-lab/advanced">Open Advanced Gold Lab</Link>
      </footer>
    </div>
  );
}
