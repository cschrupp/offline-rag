import { useQueries, useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isApiError } from "../../../api/errors";
import { IntentHandle } from "../../../api/idempotency";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import {
  getGoldTask,
  listGoldTasks,
  submitGoldPreference,
} from "../api/client";
import {
  goldLabErrorMessage,
  isAmbiguousTransportError,
  isIdempotencyConflict,
} from "../errors/goldLabErrors";
import { ChunkDuelGame } from "../games/chunkDuel/ChunkDuelGame";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
} from "../policy/presentations";
import { goldLabQueryKeys } from "../queryKeys";
import {
  applySessionConfig,
  caseIdsInServerOrder,
  parseSessionConfig,
  type GoldWorkload,
} from "../state/sessionConfig";
import type {
  AbsoluteRelevanceTaskDetail,
  GoldMutationReceipt,
  GoldPreferenceMutationBody,
  GoldTaskListFilters,
  GoldTaskSummary,
} from "../types";
import { fingerprintGoldPreference } from "./mutationIntent";

type Props = {
  campaignId: string;
  campaignClosed: boolean;
};

type PendingMutation = {
  campaignId: string;
  key: string;
  body: GoldPreferenceMutationBody;
};

type MutationBlockReason =
  | "idempotency_conflict"
  | "gold_state_unavailable"
  | "gold_conflict";

function preferenceCapForWorkload(workload: GoldWorkload): number | null {
  if (workload === "until_stop") return null;
  if (workload === "case") return null;
  const n = Number(workload);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function ChunkDuelWorkSession({
  campaignId,
  campaignClosed,
}: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const session = parseSessionConfig(searchParams);

  const [caseId, setCaseId] = useState<string | null>(null);
  const [selectedChunkIds, setSelectedChunkIds] = useState<
    [string | null, string | null]
  >([null, null]);
  const [preferenceCount, setPreferenceCount] = useState(0);
  const [lastReceipt, setLastReceipt] = useState<GoldMutationReceipt | null>(
    null,
  );
  const [lastPreferredChunkId, setLastPreferredChunkId] = useState<
    string | null
  >(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [mutationBlocked, setMutationBlocked] =
    useState<MutationBlockReason | null>(null);
  const [pendingMutation, setPendingMutation] =
    useState<PendingMutation | null>(null);
  const intent = useRef(IntentHandle.newIntent());
  const caseBootstrapped = useRef(false);
  /** Idempotency keys already counted toward the ephemeral preference cap. */
  const countedPreferenceKeys = useRef(new Set<string>());

  const listFilters: GoldTaskListFilters = useMemo(
    () => ({
      kind: "absolute_relevance",
      active: true,
    }),
    [],
  );

  const tasksQuery = useQuery({
    queryKey: goldLabQueryKeys.tasks(campaignId, listFilters),
    queryFn: ({ signal }) => listGoldTasks(campaignId, listFilters, signal),
  });

  const caseIds = useMemo(() => {
    const tasks = tasksQuery.data?.tasks ?? [];
    const allCases = caseIdsInServerOrder(tasks);
    if (session.workload === "case") {
      const anchored = tasks.find(
        (task) =>
          task.task_id === session.taskId &&
          task.active &&
          task.task_kind === "absolute_relevance",
      );
      return anchored ? [anchored.case_id] : [];
    }
    return allCases;
  }, [tasksQuery.data?.tasks, session.workload, session.taskId]);

  useEffect(() => {
    if (!tasksQuery.data || caseBootstrapped.current) return;
    caseBootstrapped.current = true;
    const current = parseSessionConfig(searchParams);
    const tasks = tasksQuery.data.tasks;
    let initialCase: string | null;
    let anchorTask: string | null;
    if (current.workload === "case") {
      // Fail closed: no first-case fallback when the task anchor is missing/invalid.
      const anchored = tasks.find(
        (task) =>
          task.task_id === current.taskId &&
          task.active &&
          task.task_kind === "absolute_relevance",
      );
      initialCase = anchored?.case_id ?? null;
      anchorTask = anchored?.task_id ?? current.taskId;
    } else {
      initialCase = caseIdsInServerOrder(tasks)[0] ?? null;
      anchorTask =
        tasks.find(
          (task) =>
            task.case_id === initialCase &&
            task.active &&
            task.task_kind === "absolute_relevance",
        )?.task_id ?? current.taskId;
    }
    setCaseId(initialCase);
    const next = applySessionConfig(searchParams, {
      ...current,
      game: "chunk_duel",
      taskId: anchorTask,
    });
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasksQuery.data]);

  const caseCandidates: GoldTaskSummary[] = useMemo(() => {
    if (!caseId || !tasksQuery.data) return [];
    const seen = new Set<string>();
    const out: GoldTaskSummary[] = [];
    for (const task of tasksQuery.data.tasks) {
      if (
        task.case_id !== caseId ||
        !task.active ||
        task.task_kind !== "absolute_relevance" ||
        !task.candidate_chunk_id
      ) {
        continue;
      }
      if (seen.has(task.candidate_chunk_id)) continue;
      seen.add(task.candidate_chunk_id);
      out.push(task);
    }
    return out;
  }, [caseId, tasksQuery.data]);

  const selectedTaskIds = useMemo(() => {
    const [a, b] = selectedChunkIds;
    const taskA = caseCandidates.find((task) => task.candidate_chunk_id === a);
    const taskB = caseCandidates.find((task) => task.candidate_chunk_id === b);
    return [taskA?.task_id ?? null, taskB?.task_id ?? null] as const;
  }, [selectedChunkIds, caseCandidates]);

  const detailQueries = useQueries({
    queries: selectedTaskIds.map((taskId) => ({
      queryKey: goldLabQueryKeys.task(campaignId, taskId ?? ""),
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        getGoldTask(campaignId, taskId!, "absolute_relevance", signal),
      enabled: Boolean(taskId) && !campaignClosed,
    })),
  });

  const preferenceCap = preferenceCapForWorkload(session.workload);

  const mutation = useMutation({
    mutationFn: async (pending: PendingMutation) =>
      submitGoldPreference({
        campaignId: pending.campaignId,
        body: pending.body,
        idempotencyKey: pending.key,
      }),
    onSuccess: (receipt, pending) => {
      setAmbiguous(false);
      setMutationBlocked(null);
      setErrorMessage(null);
      setStatusMessage(
        receipt.replayed ? "Previous commit confirmed." : null,
      );
      setLastReceipt(receipt);
      setLastPreferredChunkId(pending.body.preferred_chunk_id);
      // Ambiguity-resolved replayed=true still completes one logical interaction.
      // Count once per frozen idempotency key; never skip replay confirmations.
      if (!countedPreferenceKeys.current.has(pending.key)) {
        countedPreferenceKeys.current.add(pending.key);
        setPreferenceCount((count) => count + 1);
      }
      setPendingMutation(null);
      intent.current.reset();
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

  function onSelectCase(nextCaseId: string) {
    if (ambiguous || mutation.isPending || lastReceipt) return;
    setCaseId(nextCaseId);
    setSelectedChunkIds([null, null]);
    const anchor =
      tasksQuery.data?.tasks.find(
        (task) =>
          task.case_id === nextCaseId &&
          task.active &&
          task.task_kind === "absolute_relevance",
      )?.task_id ?? null;
    const next = applySessionConfig(searchParams, {
      ...session,
      game: "chunk_duel",
      taskId: anchor,
    });
    setSearchParams(next, { replace: false });
  }

  function onToggleCandidate(chunkId: string) {
    if (ambiguous || mutation.isPending || lastReceipt || mutationBlocked) {
      return;
    }
    setSelectedChunkIds(([a, b]) => {
      if (a === chunkId) return [b, null];
      if (b === chunkId) return [a, null];
      if (a === null) return [chunkId, b];
      if (b === null) return [a, chunkId];
      return [a, b];
    });
  }

  function onPrefer(side: "a" | "b") {
    if (
      mutation.isPending ||
      ambiguous ||
      mutationBlocked ||
      lastReceipt ||
      !caseId
    ) {
      return;
    }
    if (preferenceCap !== null && preferenceCount >= preferenceCap) return;
    const [chunkA, chunkB] = selectedChunkIds;
    if (!chunkA || !chunkB || chunkA === chunkB) return;
    const preferred = side === "a" ? chunkA : chunkB;
    const other = side === "a" ? chunkB : chunkA;
    const body: GoldPreferenceMutationBody = {
      case_id: caseId,
      preferred_chunk_id: preferred,
      other_chunk_id: other,
      game_id: CHUNK_DUEL_GAME_ID,
      presentation_id: CHUNK_DUEL_PRESENTATION_ID,
    };
    const key = intent.current.prepare(
      fingerprintGoldPreference({ campaignId, body }),
    );
    runPending({ campaignId, key, body });
  }

  function onRetrySame() {
    if (!pendingMutation || mutationBlocked) return;
    mutation.mutate(pendingMutation);
  }

  function onStartAnother() {
    if (mutationBlocked) return;
    setLastReceipt(null);
    setLastPreferredChunkId(null);
    setSelectedChunkIds([null, null]);
    setStatusMessage(null);
    setErrorMessage(null);
    setAmbiguous(false);
    setPendingMutation(null);
    intent.current.reset();
  }

  if (tasksQuery.isLoading) {
    return <p className="muted">Preparing Chunk Duel session…</p>;
  }

  if (tasksQuery.isError) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(tasksQuery.error)}
      </p>
    );
  }

  if (campaignClosed && !ambiguous && !pendingMutation && !lastReceipt) {
    return (
      <Card>
        <h2>Campaign closed</h2>
        <p className="muted" role="status">
          This campaign is closed. New preferences cannot be started.
        </p>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Back to campaign</Link>
      </Card>
    );
  }

  const candidateOptions = caseCandidates.map((task, index) => ({
    taskId: task.task_id,
    chunkId: task.candidate_chunk_id!,
    label: `Candidate ${index + 1}`,
  }));

  const duelDetails: [
    AbsoluteRelevanceTaskDetail | null,
    AbsoluteRelevanceTaskDetail | null,
  ] = [
    (detailQueries[0]?.data as AbsoluteRelevanceTaskDetail | undefined) ?? null,
    (detailQueries[1]?.data as AbsoluteRelevanceTaskDetail | undefined) ?? null,
  ];

  const blockedMessage =
    mutationBlocked === "idempotency_conflict"
      ? "This commit key is already bound to a different earlier attempt. Reload and reconcile state before continuing."
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
      <ChunkDuelGame
        caseId={caseId}
        caseIds={caseIds}
        candidates={candidateOptions}
        selectedChunkIds={selectedChunkIds}
        duelDetails={duelDetails}
        preferenceCount={preferenceCount}
        preferenceCap={preferenceCap}
        mutationBusy={mutation.isPending}
        ambiguous={ambiguous}
        mutationBlocked={mutationBlocked !== null}
        errorMessage={blockedMessage ?? errorMessage}
        statusMessage={statusMessage}
        lastReceipt={lastReceipt}
        lastPreferredChunkId={lastPreferredChunkId}
        onSelectCase={onSelectCase}
        onToggleCandidate={onToggleCandidate}
        onPrefer={onPrefer}
        onRetrySame={onRetrySame}
        onStartAnother={onStartAnother}
      />
    </>
  );
}
