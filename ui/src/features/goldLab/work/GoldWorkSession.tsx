import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isApiError } from "../../../api/errors";
import { IntentHandle } from "../../../api/idempotency";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import {
  getGoldTask,
  listGoldTasks,
  submitGoldQuestionCheck,
  submitGoldRelevance,
} from "../api/client";
import {
  goldLabErrorMessage,
  isAmbiguousTransportError,
  isIdempotencyConflict,
} from "../errors/goldLabErrors";
import {
  QuestionCheckGame,
  type QuestionCheckCommitDraft,
} from "../games/questionCheck/QuestionCheckGame";
import { RapidFireGame } from "../games/rapidFire/RapidFireGame";
import {
  candidatePresentationForGame,
  type I2ExpertGame,
} from "../policy/presentations";
import { goldLabQueryKeys } from "../queryKeys";
import {
  applySessionConfig,
  parseSessionConfig,
  taskKindForGame,
} from "../state/sessionConfig";
import type {
  AbsoluteRelevanceTaskDetail,
  GoldMutationReceipt,
  GoldRelevance,
  GoldTaskListFilters,
  QuestionCheckMutationBody,
  QuestionCheckTaskDetail,
} from "../types";
import {
  fingerprintGoldQuestionCheck,
  fingerprintGoldRelevance,
} from "./mutationIntent";
import {
  buildSessionWindow,
  nextTaskInWindow,
  resolveTaskInWindow,
  type SessionWindow,
} from "./sessionWindow";

type Props = {
  campaignId: string;
  game: I2ExpertGame;
  campaignClosed: boolean;
};

type PendingMutation =
  | {
      kind: "relevance";
      relevance: GoldRelevance;
      key: string;
      body: {
        relevance: GoldRelevance;
        game_id: string;
        presentation_id: string;
      };
    }
  | {
      kind: "question_check";
      key: string;
      body: QuestionCheckMutationBody;
    };

export function GoldWorkSession({
  campaignId,
  game,
  campaignClosed,
}: Props) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);
  const presentation = candidatePresentationForGame(game);
  const expectedKind = taskKindForGame(game);

  const [windowState, setWindowState] = useState<SessionWindow | null>(null);
  const [afterAction, setAfterAction] = useState<GoldMutationReceipt | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [pendingMutation, setPendingMutation] =
    useState<PendingMutation | null>(null);
  const intent = useRef(IntentHandle.newIntent());
  const windowBootstrapped = useRef(false);

  const listFilters: GoldTaskListFilters = useMemo(
    () => ({
      kind: expectedKind,
      state: "pending",
      active: true,
    }),
    [expectedKind],
  );

  const tasksQuery = useQuery({
    queryKey: goldLabQueryKeys.tasks(campaignId, listFilters),
    queryFn: ({ signal }) => listGoldTasks(campaignId, listFilters, signal),
  });

  useEffect(() => {
    if (!tasksQuery.data || windowBootstrapped.current) return;
    windowBootstrapped.current = true;
    const current = parseSessionConfig(searchParams);
    const built = buildSessionWindow(tasksQuery.data.tasks, {
      ...current,
      game,
    });
    setWindowState(built);
    const resolved = resolveTaskInWindow(
      built,
      tasksQuery.data.tasks,
      current.taskId,
      game,
    );
    const next = applySessionConfig(searchParams, {
      ...current,
      game,
      taskId: resolved,
    });
    setSearchParams(next, { replace: true });
    // Bootstrap only once when the authoritative pending list arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasksQuery.data, game]);

  const activeTaskId =
    windowState && tasksQuery.data
      ? resolveTaskInWindow(
          windowState,
          tasksQuery.data.tasks,
          session.taskId,
          game,
        )
      : null;

  const taskQuery = useQuery({
    queryKey: goldLabQueryKeys.task(campaignId, activeTaskId ?? ""),
    queryFn: ({ signal }) =>
      getGoldTask(campaignId, activeTaskId!, expectedKind, signal),
    enabled: Boolean(activeTaskId) && !campaignClosed,
  });

  const mutation = useMutation({
    mutationFn: async (pending: PendingMutation) => {
      if (pending.kind === "relevance") {
        return submitGoldRelevance({
          campaignId,
          taskId: activeTaskId!,
          relevance: pending.relevance,
          gameId: pending.body.game_id,
          presentationId: pending.body.presentation_id,
          idempotencyKey: pending.key,
        });
      }
      return submitGoldQuestionCheck({
        campaignId,
        taskId: activeTaskId!,
        body: pending.body,
        idempotencyKey: pending.key,
      });
    },
    onSuccess: async (receipt) => {
      setAmbiguous(false);
      setErrorMessage(null);
      setStatusMessage(
        receipt.replayed ? "Previous commit confirmed." : null,
      );
      setAfterAction(receipt);
      setPendingMutation(null);
      intent.current.reset();
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.task(campaignId, activeTaskId ?? ""),
        }),
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.tasks(campaignId, listFilters),
        }),
      ]);
    },
    onError: (error) => {
      setErrorMessage(goldLabErrorMessage(error));
      if (isAmbiguousTransportError(error)) {
        setAmbiguous(true);
        return;
      }
      if (isIdempotencyConflict(error)) {
        setAmbiguous(false);
        return;
      }
      if (isApiError(error) && error.code === "gold_busy") {
        setAmbiguous(true);
        return;
      }
      if (isApiError(error) && error.code === "request_invalid") {
        setAmbiguous(false);
        intent.current.reset();
        setPendingMutation(null);
        return;
      }
      setAmbiguous(false);
    },
  });

  function runPending(pending: PendingMutation) {
    if (campaignClosed && !ambiguous) {
      setErrorMessage(
        "This Gold Lab resource changed since you last loaded it. Refresh, then try again.",
      );
      return;
    }
    setPendingMutation(pending);
    setErrorMessage(null);
    setStatusMessage(null);
    mutation.mutate(pending);
  }

  function onRelevance(relevance: GoldRelevance) {
    if (mutation.isPending || afterAction || ambiguous) return;
    const body = {
      relevance,
      game_id: presentation.gameId,
      presentation_id: presentation.presentationId,
    };
    const key = intent.current.prepare(
      fingerprintGoldRelevance({
        campaignId,
        taskId: activeTaskId!,
        relevance,
        gameId: presentation.gameId,
        presentationId: presentation.presentationId,
      }),
    );
    runPending({ kind: "relevance", relevance, key, body });
  }

  function onQuestionCheck(partial: QuestionCheckCommitDraft) {
    if (mutation.isPending || afterAction || ambiguous) return;
    const body = {
      ...partial,
      game_id: presentation.gameId,
      presentation_id: presentation.presentationId,
    } as QuestionCheckMutationBody;
    const key = intent.current.prepare(
      fingerprintGoldQuestionCheck({
        campaignId,
        taskId: activeTaskId!,
        body,
      }),
    );
    runPending({ kind: "question_check", key, body });
  }

  function onRetrySame() {
    if (!pendingMutation) return;
    mutation.mutate(pendingMutation);
  }

  function onCorrect() {
    setAfterAction(null);
    setStatusMessage(null);
    setErrorMessage(null);
    setAmbiguous(false);
    setPendingMutation(null);
    intent.current.reset();
  }

  async function onNext() {
    if (!windowState || !activeTaskId) return;
    const refreshed = await queryClient.fetchQuery({
      queryKey: goldLabQueryKeys.tasks(campaignId, listFilters),
      queryFn: ({ signal }) => listGoldTasks(campaignId, listFilters, signal),
    });
    const nextId = nextTaskInWindow(
      windowState,
      refreshed.tasks,
      activeTaskId,
      game,
    );
    setAfterAction(null);
    setStatusMessage(null);
    setErrorMessage(null);
    setAmbiguous(false);
    setPendingMutation(null);
    intent.current.reset();
    const next = applySessionConfig(searchParams, {
      ...session,
      game,
      taskId: nextId,
    });
    setSearchParams(next, { replace: false });
  }

  if (tasksQuery.isLoading || (tasksQuery.isSuccess && !windowState)) {
    return <p className="muted">Preparing expert work session…</p>;
  }

  if (tasksQuery.isError) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(tasksQuery.error)}
      </p>
    );
  }

  if (!activeTaskId) {
    return (
      <Card>
        <h2>No eligible tasks</h2>
        <p className="muted" role="status">
          No pending tasks match this session configuration.
        </p>
        <Button to={`/gold-lab/campaigns/${campaignId}`} variant="secondary">
          Back to campaign
        </Button>
      </Card>
    );
  }

  if (campaignClosed && !ambiguous && !pendingMutation) {
    return (
      <Card>
        <h2>Campaign closed</h2>
        <p className="muted" role="status">
          This campaign is closed. New expert judgments cannot be started.
        </p>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
      </Card>
    );
  }

  if (taskQuery.isLoading) {
    return <p className="muted">Loading task…</p>;
  }

  if (taskQuery.isError || !taskQuery.data) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(taskQuery.error)}
      </p>
    );
  }

  const nextDisabled =
    !windowState ||
    nextTaskInWindow(
      windowState,
      tasksQuery.data?.tasks ?? [],
      activeTaskId,
      game,
    ) === null;

  if (game === "rapid_fire") {
    return (
      <RapidFireGame
        task={taskQuery.data as AbsoluteRelevanceTaskDetail}
        mutationBusy={mutation.isPending}
        ambiguous={ambiguous}
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        afterAction={afterAction}
        onCommit={onRelevance}
        onRetrySame={onRetrySame}
        onNext={() => void onNext()}
        onCorrect={onCorrect}
        nextDisabled={nextDisabled}
      />
    );
  }

  return (
    <QuestionCheckGame
      task={taskQuery.data as QuestionCheckTaskDetail}
      mutationBusy={mutation.isPending}
      ambiguous={ambiguous}
      errorMessage={errorMessage}
      statusMessage={statusMessage}
      afterAction={afterAction}
      onCommit={onQuestionCheck}
      onRetrySame={onRetrySame}
      onNext={() => void onNext()}
      onCorrect={onCorrect}
      nextDisabled={nextDisabled}
    />
  );
}
