import { useQueries, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isApiError } from "../../../api/errors";
import { IntentHandle } from "../../../api/idempotency";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import {
  getGoldTask,
  listGoldTasks,
  submitGoldRelevance,
} from "../api/client";
import {
  goldLabErrorMessage,
  isAmbiguousTransportError,
  isIdempotencyConflict,
} from "../errors/goldLabErrors";
import { EvidenceSweepGame } from "../games/evidenceSweep/EvidenceSweepGame";
import {
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
} from "../policy/presentations";
import { goldLabQueryKeys } from "../queryKeys";
import {
  applySessionConfig,
  parseSessionConfig,
} from "../state/sessionConfig";
import type {
  AbsoluteRelevanceTaskDetail,
  GoldMutationReceipt,
  GoldRelevance,
  GoldTaskListFilters,
} from "../types";
import { fingerprintGoldRelevance } from "./mutationIntent";
import {
  buildSessionWindow,
  nextBatchTaskIds,
  orderedWindowTaskIds,
  type SessionWindow,
} from "./sessionWindow";

type Props = {
  campaignId: string;
  campaignClosed: boolean;
};

type PendingMutation = {
  campaignId: string;
  taskId: string;
  key: string;
  relevance: GoldRelevance;
  body: {
    relevance: GoldRelevance;
    game_id: string;
    presentation_id: string;
  };
};

type MutationBlockReason =
  | "idempotency_conflict"
  | "gold_state_unavailable"
  | "gold_conflict";

export function EvidenceSweepWorkSession({
  campaignId,
  campaignClosed,
}: Props) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);

  const [windowState, setWindowState] = useState<SessionWindow | null>(null);
  const [batchTaskIds, setBatchTaskIds] = useState<string[]>([]);
  const [consumedBatchIds, setConsumedBatchIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [afterByTask, setAfterByTask] = useState<
    Record<string, GoldMutationReceipt>
  >({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [mutationBlocked, setMutationBlocked] =
    useState<MutationBlockReason | null>(null);
  const [pendingMutation, setPendingMutation] =
    useState<PendingMutation | null>(null);
  const intent = useRef(IntentHandle.newIntent());
  const windowBootstrapped = useRef(false);

  const listFilters: GoldTaskListFilters = useMemo(
    () => ({
      kind: "absolute_relevance",
      state: "pending",
      active: true,
    }),
    [],
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
      game: "evidence_sweep",
    });
    setWindowState(built);
    const ordered = orderedWindowTaskIds(
      built,
      tasksQuery.data.tasks,
      "evidence_sweep",
    );
    const batch = nextBatchTaskIds(ordered, new Set());
    setBatchTaskIds(batch);
    const anchor = batch[0] ?? current.taskId;
    const next = applySessionConfig(searchParams, {
      ...current,
      game: "evidence_sweep",
      taskId: anchor,
    });
    setSearchParams(next, { replace: true });
    // Bootstrap only once when the authoritative pending list arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasksQuery.data]);

  const detailQueries = useQueries({
    queries: batchTaskIds.map((taskId) => ({
      queryKey: goldLabQueryKeys.task(campaignId, taskId),
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        getGoldTask(campaignId, taskId, "absolute_relevance", signal),
      enabled: Boolean(taskId) && !campaignClosed,
    })),
  });

  const mutation = useMutation({
    mutationFn: async (pending: PendingMutation) =>
      submitGoldRelevance({
        campaignId: pending.campaignId,
        taskId: pending.taskId,
        relevance: pending.relevance,
        gameId: pending.body.game_id,
        presentationId: pending.body.presentation_id,
        idempotencyKey: pending.key,
      }),
    onSuccess: async (receipt, pending) => {
      setAmbiguous(false);
      setMutationBlocked(null);
      setErrorMessage(null);
      setStatusMessage(
        receipt.replayed ? "Previous commit confirmed." : null,
      );
      setAfterByTask((prev) => ({ ...prev, [pending.taskId]: receipt }));
      setPendingMutation(null);
      intent.current.reset();
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.task(pending.campaignId, pending.taskId),
        }),
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.tasks(pending.campaignId, listFilters),
        }),
      ]);
    },
    onError: (error) => {
      setErrorMessage(goldLabErrorMessage(error));
      if (isAmbiguousTransportError(error)) {
        setAmbiguous(true);
        setMutationBlocked(null);
        return;
      }
      if (isApiError(error) && error.code === "gold_busy") {
        setAmbiguous(true);
        setMutationBlocked(null);
        return;
      }
      if (isIdempotencyConflict(error)) {
        setAmbiguous(false);
        setMutationBlocked("idempotency_conflict");
        setPendingMutation(null);
        return;
      }
      if (isApiError(error) && error.code === "gold_state_unavailable") {
        setAmbiguous(false);
        setMutationBlocked("gold_state_unavailable");
        setPendingMutation(null);
        return;
      }
      if (isApiError(error) && error.code === "gold_conflict") {
        setAmbiguous(false);
        setMutationBlocked("gold_conflict");
        setPendingMutation(null);
        return;
      }
      if (isApiError(error) && error.code === "request_invalid") {
        setAmbiguous(false);
        setMutationBlocked(null);
        intent.current.reset();
        setPendingMutation(null);
        return;
      }
      setAmbiguous(false);
    },
  });

  function runPending(pending: PendingMutation) {
    if (mutationBlocked) return;
    if (campaignClosed && !ambiguous) {
      setMutationBlocked("gold_conflict");
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

  function onCommit(taskId: string, relevance: GoldRelevance) {
    if (
      mutation.isPending ||
      ambiguous ||
      mutationBlocked ||
      afterByTask[taskId]
    ) {
      return;
    }
    if (!batchTaskIds.includes(taskId)) return;
    const body = {
      relevance,
      game_id: EVIDENCE_SWEEP_GAME_ID,
      presentation_id: EVIDENCE_SWEEP_PRESENTATION_ID,
    };
    const key = intent.current.prepare(
      fingerprintGoldRelevance({
        campaignId,
        taskId,
        relevance,
        gameId: EVIDENCE_SWEEP_GAME_ID,
        presentationId: EVIDENCE_SWEEP_PRESENTATION_ID,
      }),
    );
    runPending({
      campaignId,
      taskId,
      relevance,
      key,
      body,
    });
  }

  function onRetrySame() {
    if (!pendingMutation || mutationBlocked) return;
    mutation.mutate(pendingMutation);
  }

  function onCorrect(taskId: string) {
    if (mutationBlocked) return;
    setAfterByTask((prev) => {
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
    setStatusMessage(null);
    setErrorMessage(null);
    setAmbiguous(false);
    setPendingMutation(null);
    intent.current.reset();
  }

  async function onNextBatch() {
    if (!windowState || mutationBlocked) return;
    const allResolved = batchTaskIds.every((id) => Boolean(afterByTask[id]));
    if (!allResolved) return;

    const refreshed = await queryClient.fetchQuery({
      queryKey: goldLabQueryKeys.tasks(campaignId, listFilters),
      queryFn: ({ signal }) => listGoldTasks(campaignId, listFilters, signal),
    });

    const nextConsumed = new Set(consumedBatchIds);
    for (const id of batchTaskIds) nextConsumed.add(id);
    setConsumedBatchIds(nextConsumed);

    const ordered = orderedWindowTaskIds(
      windowState,
      refreshed.tasks,
      "evidence_sweep",
    );
    const nextBatch = nextBatchTaskIds(ordered, nextConsumed);
    setBatchTaskIds(nextBatch);
    setAfterByTask({});
    setStatusMessage(null);
    setErrorMessage(null);
    setAmbiguous(false);
    setPendingMutation(null);
    intent.current.reset();

    const next = applySessionConfig(searchParams, {
      ...session,
      game: "evidence_sweep",
      taskId: nextBatch[0] ?? null,
    });
    setSearchParams(next, { replace: false });
  }

  if (tasksQuery.isLoading || (tasksQuery.isSuccess && !windowState)) {
    return <p className="muted">Preparing Evidence Sweep session…</p>;
  }

  if (tasksQuery.isError) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(tasksQuery.error)}
      </p>
    );
  }

  if (batchTaskIds.length === 0) {
    return (
      <Card>
        <h2>No eligible tasks</h2>
        <p className="muted" role="status">
          No pending tasks match this Evidence Sweep session configuration.
        </p>
        <Button to={`/gold-lab/campaigns/${campaignId}`} variant="secondary">
          Back to campaign
        </Button>
      </Card>
    );
  }

  if (campaignClosed && !ambiguous && !pendingMutation) {
    const hasAfter = Object.keys(afterByTask).length > 0;
    if (!hasAfter) {
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
  }

  const detailsLoading = detailQueries.some((query) => query.isLoading);
  const detailsError = detailQueries.find((query) => query.isError);

  if (detailsLoading) {
    return <p className="muted">Loading batch…</p>;
  }

  if (detailsError) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(detailsError.error)}
      </p>
    );
  }

  const cards = batchTaskIds.map((taskId, index) => {
    const detail = detailQueries[index]?.data as
      | AbsoluteRelevanceTaskDetail
      | undefined;
    if (!detail) {
      throw new Error(`Missing task detail for latched batch member ${taskId}`);
    }
    return {
      task: detail,
      afterAction: afterByTask[taskId] ?? null,
    };
  });

  const batchComplete = batchTaskIds.every((id) => Boolean(afterByTask[id]));
  const nextBatchDisabled =
    !windowState ||
    nextBatchTaskIds(
      orderedWindowTaskIds(
        windowState,
        tasksQuery.data?.tasks ?? [],
        "evidence_sweep",
      ),
      new Set([...consumedBatchIds, ...batchTaskIds]),
    ).length === 0;

  const blockedMessage =
    mutationBlocked === "idempotency_conflict"
      ? "This commit key is already bound to a different earlier attempt. Reload and reconcile state before correcting."
      : mutationBlocked === "gold_state_unavailable"
        ? "Gold Lab state is temporarily unavailable. Reload the page. Do not continue with this action until state can be trusted."
        : mutationBlocked === "gold_conflict"
          ? "This Gold Lab resource changed since you last loaded it. Reload to reconcile lifecycle state before continuing."
          : null;

  return (
    <>
      {mutationBlocked ? (
        <div className="row" role="status">
          <Button
            variant="secondary"
            onClick={() => window.location.reload()}
          >
            Reload to reconcile
          </Button>
        </div>
      ) : null}
      <EvidenceSweepGame
        cards={cards}
        mutationBusy={mutation.isPending}
        ambiguous={ambiguous}
        mutationBlocked={mutationBlocked !== null}
        busyTaskId={pendingMutation?.taskId ?? null}
        errorMessage={blockedMessage ?? errorMessage}
        statusMessage={statusMessage}
        batchComplete={batchComplete}
        nextBatchDisabled={nextBatchDisabled || mutationBlocked !== null}
        onCommit={onCommit}
        onCorrect={onCorrect}
        onRetrySame={onRetrySame}
        onNextBatch={() => void onNextBatch()}
      />
    </>
  );
}
