import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addSources,
  conversationTurn,
  getCapabilities,
  getOperation,
  getWorkspace,
  listSources,
  removeSource,
  renameSource,
  replaceSource,
} from "../api/client";
import { isApiError, userFacingErrorMessage } from "../api/errors";
import {
  IntentHandle,
  fingerprintAddSources,
  fingerprintRemoveSource,
  fingerprintRenameSource,
  fingerprintReplaceSource,
} from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type { Operation, Source, WorkspaceCitation } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { TextInput } from "../components/Field";
import { ModalDialog } from "../components/ModalDialog";
import { OperationProgress } from "../components/OperationProgress";
import { ResponsiveDrawer } from "../components/ResponsiveDrawer";
import { AskPanel } from "../features/ask/AskPanel";
import {
  loadDesktopRailState,
  saveDesktopRailState,
} from "../features/ask/desktopRailState";
import { EvidencePanel } from "../features/ask/EvidencePanel";
import { SourceRail } from "../features/ask/SourceRail";
import type { PreviewTarget } from "../features/ask/SourcePreview";
import {
  appendConversationPair,
  buildResolverPriorTurns,
  chronologicalPairs,
  clearConversation,
  loadConversation,
  newPairId,
  toHistoryEntry,
  type ConversationHistoryEntry,
  type ConversationPair,
  type IncompleteUserTurn,
} from "../features/ask/conversationState";
import {
  reconcileSourceSelection,
  selectAllSources,
  setSourceSelected,
  sourceIdsForQuery,
  type SourceSelectionMode,
} from "../features/ask/sourceSelection";
import { useNarrowLayout } from "../features/ask/useNarrowLayout";

type AskSubmit = {
  pairId: string;
  /** Immutable submission-time order key (ISO). */
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  mode: SourceSelectionMode;
  /** undefined = omit source_ids (all-active); [] would mean empty scope */
  sourceIds: string[] | undefined;
  priorTurns: ReturnType<typeof buildResolverPriorTurns>;
};
import {
  forgetActiveOperation,
  isTerminalOperationStatus,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import { WorkspaceMetadataForm } from "../features/workspaces/WorkspaceMetadataForm";
import {
  activeSourceBytes,
  formatBytes,
  formatMiB,
  formatTimestamp,
  type SourceCapacityLimits,
} from "../features/workspaces/format";

type PendingPhase = "idle" | "uploading" | "operation" | "terminal_error";

/** Frozen Add Sources submission — never rebuilt from live workspace on retry. */
export type AddSourcesIntent = {
  workspaceId: string;
  expectedRevision: number;
  files: File[];
  fingerprint: string;
  idempotencyKey: string;
};

function limitsFromCapabilities(
  caps: {
    source_limits: {
      max_active_sources: number;
      max_bytes_per_source: number;
      max_active_source_bytes: number;
    };
  } | undefined,
): SourceCapacityLimits | null {
  if (!caps) return null;
  return {
    maxActiveSources: caps.source_limits.max_active_sources,
    maxBytesPerFile: caps.source_limits.max_bytes_per_source,
    maxDesiredActiveBytes: caps.source_limits.max_active_source_bytes,
  };
}

export function WorkspacePage() {
  const { workspaceId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handledTerminalOps = useRef(new Set<string>());
  const addIntent = useRef(IntentHandle.newIntent());
  const renameIntent = useRef(IntentHandle.newIntent());
  const replaceIntent = useRef(IntentHandle.newIntent());
  const removeIntent = useRef(IntentHandle.newIntent());

  const workspaceQuery = useQuery({
    queryKey: queryKeys.workspace(workspaceId),
    queryFn: ({ signal }) => getWorkspace(workspaceId, signal),
    enabled: Boolean(workspaceId),
  });

  const sourcesQuery = useQuery({
    queryKey: queryKeys.workspaceSources(workspaceId),
    queryFn: ({ signal }) => listSources(workspaceId, signal),
    enabled: Boolean(workspaceId),
  });

  const capabilitiesQuery = useQuery({
    queryKey: queryKeys.capabilities,
    queryFn: ({ signal }) => getCapabilities(signal),
  });

  const workspace = workspaceQuery.data;
  const sources = sourcesQuery.data?.sources ?? [];
  const limits = limitsFromCapabilities(capabilitiesQuery.data);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [addError, setAddError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addSourcesIntent, setAddSourcesIntent] =
    useState<AddSourcesIntent | null>(null);
  const [addAmbiguous, setAddAmbiguous] = useState(false);
  /** After cancel: block Add until workspace/source refetch settles. */
  const [addCancelReconciling, setAddCancelReconciling] = useState(false);
  const [addFileInputKey, setAddFileInputKey] = useState(0);
  const addUploadAbortRef = useRef<AbortController | null>(null);
  const [editWorkspaceOpen, setEditWorkspaceOpen] = useState(false);

  const [renameTarget, setRenameTarget] = useState<Source | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  const [replaceTarget, setReplaceTarget] = useState<Source | null>(null);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replaceError, setReplaceError] = useState<string | null>(null);

  const [removeTarget, setRemoveTarget] = useState<Source | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const [pendingPhase, setPendingPhase] = useState<PendingPhase>("idle");
  const [activeOperationId, setActiveOperationId] = useState<string | null>(
    null,
  );
  const [operationLabel, setOperationLabel] = useState<string | undefined>();

  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectionMode, setSelectionMode] =
    useState<SourceSelectionMode>("all");
  const [selectionSyncKey, setSelectionSyncKey] = useState("");
  const [question, setQuestion] = useState("");
  const [askError, setAskError] = useState<string | null>(null);
  const [conflictHint, setConflictHint] = useState<string | null>(null);
  const [settingsHint, setSettingsHint] = useState(false);
  const [pairs, setPairs] = useState<ConversationPair[]>(() =>
    workspaceId ? loadConversation(workspaceId) : [],
  );
  const [historyWorkspaceId, setHistoryWorkspaceId] = useState(workspaceId);
  const [activeEntryId, setActiveEntryId] = useState<string | null>(() =>
    workspaceId ? (loadConversation(workspaceId)[0]?.pairId ?? null) : null,
  );
  const [incompleteTurns, setIncompleteTurns] = useState<IncompleteUserTurn[]>(
    [],
  );
  const [selectedCitation, setSelectedCitation] =
    useState<WorkspaceCitation | null>(null);
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(
    null,
  );
  const [sourcesDrawerOpen, setSourcesDrawerOpen] = useState(false);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [sourcesRailExpanded, setSourcesRailExpanded] = useState(
    () => loadDesktopRailState().sourcesExpanded,
  );
  const [evidenceRailExpanded, setEvidenceRailExpanded] = useState(
    () => loadDesktopRailState().evidenceExpanded,
  );
  const isNarrowLayout = useNarrowLayout();

  function setSourcesRailExpandedPersisted(expanded: boolean) {
    setSourcesRailExpanded(expanded);
    saveDesktopRailState({
      sourcesExpanded: expanded,
      evidenceExpanded: evidenceRailExpanded,
    });
  }

  function setEvidenceRailExpandedPersisted(expanded: boolean) {
    setEvidenceRailExpanded(expanded);
    saveDesktopRailState({
      sourcesExpanded: sourcesRailExpanded,
      evidenceExpanded: expanded,
    });
  }

  if (historyWorkspaceId !== workspaceId) {
    const loaded = workspaceId ? loadConversation(workspaceId) : [];
    setHistoryWorkspaceId(workspaceId);
    setPairs(loaded);
    setActiveEntryId(loaded[0]?.pairId ?? null);
    setSelectedCitation(loaded[0]?.response.citations[0] ?? null);
    setPreviewTarget(null);
    setIncompleteTurns([]);
    setQuestion("");
    setAskError(null);
    setConflictHint(null);
    setSelectionSyncKey("");
    setSelectionMode("all");
    setSourcesDrawerOpen(false);
    setEvidenceDrawerOpen(false);
  }

  if (!isNarrowLayout && (sourcesDrawerOpen || evidenceDrawerOpen)) {
    setSourcesDrawerOpen(false);
    setEvidenceDrawerOpen(false);
  }

  const activeSources = sourcesQuery.data?.sources ?? [];
  const selectionKey = `${workspaceId}:${activeSources
    .map((source) => source.source_id)
    .join(",")}`;
  if (sourcesQuery.data && selectionSyncKey !== selectionKey) {
    const next = reconcileSourceSelection(workspaceId, activeSources);
    setSelectionSyncKey(selectionKey);
    setSelectedSourceIds(next.selectedSourceIds);
    setSelectionMode(next.mode);
  }

  if (
    previewTarget?.kind === "source" &&
    sourcesQuery.data &&
    !activeSources.some((source) => source.source_id === previewTarget.sourceId)
  ) {
    setPreviewTarget(null);
  }

  function settleTerminalOperation(operation: Operation) {
    if (handledTerminalOps.current.has(operation.operation_id)) return;
    handledTerminalOps.current.add(operation.operation_id);
    const status = String(operation.status).toLowerCase();
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspace(workspaceId),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources(workspaceId),
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
    if (status === "succeeded") {
      forgetActiveOperation(operation.operation_id);
      setPendingPhase("idle");
      return;
    }
    if (status === "failed" || status === "interrupted") {
      // Keep error-capable terminal surface until dismissed; do not collapse.
      setPendingPhase("terminal_error");
      return;
    }
    setPendingPhase("idle");
  }

  const operationQuery = useQuery({
    queryKey: activeOperationId
      ? queryKeys.operation(activeOperationId)
      : ["operation", "none"],
    queryFn: async ({ signal }) => {
      const op = await getOperation(activeOperationId!, signal);
      if (isTerminalOperationStatus(String(op.status))) {
        queueMicrotask(() => settleTerminalOperation(op));
      }
      return op;
    },
    enabled: Boolean(activeOperationId),
    refetchInterval: (query) => {
      const op = query.state.data;
      if (op && isTerminalOperationStatus(String(op.status))) {
        queueMicrotask(() => settleTerminalOperation(op));
        return false;
      }
      return 100;
    },
  });

  function beginOperation(operation: Operation, label: string) {
    rememberActiveOperation({
      operation_id: operation.operation_id,
      workspace_id: operation.workspace_id,
      kind: String(operation.kind),
      label,
    });
    setOperationLabel(label);
    setActiveOperationId(operation.operation_id);
    setPendingPhase("operation");
    queryClient.setQueryData(
      queryKeys.operation(operation.operation_id),
      operation,
    );
    if (isTerminalOperationStatus(String(operation.status))) {
      queueMicrotask(() => settleTerminalOperation(operation));
    }
  }

  function handleConflict(error: unknown): boolean {
    if (isApiError(error) && error.code === "workspace_conflict") {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workspace(workspaceId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workspaceSources(workspaceId),
      });
      return true;
    }
    return false;
  }

  function clearAddUploadTransport() {
    addUploadAbortRef.current = null;
  }

  function abandonAddSourcesIntent() {
    addUploadAbortRef.current?.abort();
    clearAddUploadTransport();
    setAddSourcesIntent(null);
    setAddAmbiguous(false);
    addIntent.current.reset();
  }

  function cancelAddUpload() {
    const controller = addUploadAbortRef.current;
    if (controller && !controller.signal.aborted) {
      controller.abort();
    }
  }

  function closeAddSourcesModal() {
    if (pendingPhase === "uploading" || addMutation.isPending) {
      cancelAddUpload();
    }
    setAddSourcesIntent(null);
    setAddAmbiguous(false);
    setAddCancelReconciling(false);
    addIntent.current.reset();
    clearAddUploadTransport();
    setSelectedFiles([]);
    setAddFileInputKey((key) => key + 1);
    setAddError(null);
    setAddOpen(false);
    setPendingPhase((phase) => (phase === "uploading" ? "idle" : phase));
  }

  const addMutation = useMutation({
    mutationFn: async (intent: AddSourcesIntent) => {
      const controller = new AbortController();
      addUploadAbortRef.current = controller;
      setPendingPhase("uploading");
      setAddAmbiguous(false);
      try {
        return await addSources({
          workspaceId: intent.workspaceId,
          files: intent.files,
          revision: intent.expectedRevision,
          idempotencyKey: intent.idempotencyKey,
          signal: controller.signal,
        });
      } finally {
        if (addUploadAbortRef.current === controller) {
          clearAddUploadTransport();
        }
      }
    },
    onSuccess: (operation) => {
      beginOperation(operation, "Add sources");
      setSelectedFiles([]);
      setAddOpen(false);
      setAddSourcesIntent(null);
      setAddAmbiguous(false);
      setAddError(null);
      addIntent.current.reset();
    },
    onError: (error) => {
      setPendingPhase("idle");
      setAddError(userFacingErrorMessage(error));

      if (isApiError(error) && error.code === "request_aborted") {
        // Cancel is not a safe-retry surface. Abort cannot prove the server
        // lost the race, so do not leave the same files preselected under a
        // freshly reset idempotency key (would enable one-click duplicate).
        setAddAmbiguous(false);
        setAddSourcesIntent(null);
        addIntent.current.reset();
        setSelectedFiles([]);
        setAddFileInputKey((key) => key + 1);
        setAddCancelReconciling(true);
        void Promise.all([
          queryClient.invalidateQueries({
            queryKey: queryKeys.workspace(workspaceId),
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.workspaceSources(workspaceId),
          }),
        ]).finally(() => {
          setAddCancelReconciling(false);
        });
        return;
      }

      void queryClient.invalidateQueries({
        queryKey: queryKeys.workspace(workspaceId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workspaceSources(workspaceId),
      });

      if (isApiError(error) && error.code === "upload_transport_interrupted") {
        // Keep frozen intent for explicit "Retry safely".
        setAddAmbiguous(true);
        return;
      }

      if (
        handleConflict(error) ||
        (isApiError(error) && error.kind !== "network")
      ) {
        setAddAmbiguous(false);
        setAddSourcesIntent(null);
        addIntent.current.reset();
      }
    },
  });

  function submitAddSourcesIntent(intent: AddSourcesIntent) {
    setAddSourcesIntent(intent);
    setAddError(null);
    setOperationLabel("Add sources");
    addMutation.mutate(intent);
  }

  function retryAddSourcesSafely() {
    if (!addSourcesIntent || addMutation.isPending) return;
    setAddError(null);
    setOperationLabel("Add sources");
    addMutation.mutate(addSourcesIntent);
  }

  const renameMutation = useMutation({
    mutationFn: () => {
      if (!workspace || !renameTarget) throw new Error("Missing rename target");
      const displayName = renameValue.trim();
      const key = renameIntent.current.prepare(
        fingerprintRenameSource({
          workspaceId,
          sourceId: renameTarget.source_id,
          revision: workspace.revision,
          displayName,
        }),
      );
      return renameSource({
        workspaceId,
        sourceId: renameTarget.source_id,
        displayName,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: async () => {
      setRenameTarget(null);
      setRenameError(null);
      renameIntent.current.reset();
      await queryClient.invalidateQueries({
        queryKey: queryKeys.workspace(workspaceId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.workspaceSources(workspaceId),
      });
    },
    onError: (error) => {
      setRenameError(userFacingErrorMessage(error));
      if (handleConflict(error) || (isApiError(error) && error.kind !== "network")) {
        renameIntent.current.reset();
      }
    },
  });

  const replaceMutation = useMutation({
    mutationFn: async () => {
      if (!workspace || !replaceTarget || !replaceFile) {
        throw new Error("Missing replace target");
      }
      const key = replaceIntent.current.prepare(
        fingerprintReplaceSource({
          workspaceId,
          sourceId: replaceTarget.source_id,
          revision: workspace.revision,
          file: replaceFile,
        }),
      );
      return replaceSource({
        workspaceId,
        sourceId: replaceTarget.source_id,
        file: replaceFile,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: (operation) => {
      beginOperation(operation, "Replace source");
      setReplaceTarget(null);
      setReplaceFile(null);
      replaceIntent.current.reset();
    },
    onError: (error) => {
      setPendingPhase("idle");
      setReplaceError(userFacingErrorMessage(error));
      if (handleConflict(error) || (isApiError(error) && error.kind !== "network")) {
        replaceIntent.current.reset();
      }
    },
  });

  const removeMutation = useMutation({
    mutationFn: async () => {
      if (!workspace || !removeTarget) throw new Error("Missing remove target");
      setRemoveError(null);
      const key = removeIntent.current.prepare(
        fingerprintRemoveSource({
          workspaceId,
          sourceId: removeTarget.source_id,
          revision: workspace.revision,
        }),
      );
      return removeSource({
        workspaceId,
        sourceId: removeTarget.source_id,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: (operation) => {
      beginOperation(operation, "Remove source");
      setRemoveTarget(null);
      removeIntent.current.reset();
    },
    onError: (error) => {
      setRemoveError(userFacingErrorMessage(error));
      if (handleConflict(error) || (isApiError(error) && error.kind !== "network")) {
        removeIntent.current.reset();
      }
    },
  });

  const askMutation = useMutation({
    mutationFn: (submit: AskSubmit) =>
      conversationTurn({
        workspaceId,
        question: submit.question,
        sourceIds: submit.sourceIds,
        priorTurns: submit.priorTurns,
      }),
    retry: false,
    onSuccess: (response, submit) => {
      setAskError(null);
      setConflictHint(null);
      setSettingsHint(false);
      setIncompleteTurns((prev) =>
        prev.filter((turn) => turn.pairId !== submit.pairId),
      );
      const pair: ConversationPair = {
        pairId: submit.pairId,
        askedAt: submit.askedAt,
        question: submit.question,
        selectedSourceIds: submit.selectedSourceIds,
        selectedSourceNames: submit.selectedSourceNames,
        selectionMode: submit.mode,
        response,
      };
      const next = appendConversationPair(workspaceId, pair);
      setPairs(next);
      setActiveEntryId(pair.pairId);
      const first = response.citations[0] ?? null;
      setSelectedCitation(first);
      if (first) {
        setPreviewTarget({
          kind: "citation",
          workspaceId,
          citation: first,
          workspaceRevision: response.workspace_revision,
          querySnapshotId: response.snapshot_id,
        });
      } else {
        setPreviewTarget(null);
      }
    },
    onError: (error, submit) => {
      const message = userFacingErrorMessage(error);
      // A2-D10: submitted user turn remains immutable display content.
      setIncompleteTurns((prev) =>
        prev.map((turn) =>
          turn.pairId === submit.pairId
            ? { ...turn, status: "failed", errorMessage: message }
            : turn,
        ),
      );
      if (isApiError(error) && error.code === "workspace_conflict") {
        setConflictHint(
          "The workspace changed while this question was running. Sources were refreshed; review the selection and ask again.",
        );
        setAskError(null);
        void queryClient.invalidateQueries({
          queryKey: queryKeys.workspace(workspaceId),
        });
        void queryClient.invalidateQueries({
          queryKey: queryKeys.workspaceSources(workspaceId),
        });
        return;
      }
      setConflictHint(null);
      setAskError(message);
      setSettingsHint(
        isApiError(error) &&
          (error.code.includes("generation") ||
            error.code.includes("settings") ||
            error.code === "service_unavailable"),
      );
    },
  });

  function submitAsk() {
    const trimmed = question.trim();
    if (
      isEmpty ||
      selectedSourceIds.length === 0 ||
      trimmed.length === 0 ||
      askMutation.isPending
    ) {
      return;
    }
    const submittedIds = selectedSourceIds.slice();
    const submittedNames = sources
      .filter((source) => submittedIds.includes(source.source_id))
      .map((source) => source.display_name);
    const submittedMode = selectionMode;
    const pairId = newPairId();
    const askedAt = new Date().toISOString();
    // Only completed pairs enter resolver context — never failed/incomplete.
    const priorTurns = buildResolverPriorTurns(chronologicalPairs(pairs));
    const submit: AskSubmit = {
      pairId,
      askedAt,
      question: trimmed,
      selectedSourceIds: submittedIds,
      selectedSourceNames: submittedNames,
      mode: submittedMode,
      sourceIds: sourceIdsForQuery(sources, submittedIds, submittedMode),
      priorTurns,
    };
    setAskError(null);
    setConflictHint(null);
    setQuestion("");
    setIncompleteTurns((prev) => [
      ...prev,
      {
        pairId,
        askedAt,
        question: trimmed,
        selectedSourceIds: submittedIds,
        selectedSourceNames: submittedNames,
        selectionMode: submittedMode,
        status: "pending",
      },
    ]);
    askMutation.mutate(submit);
  }

  function startNewConversation() {
    if (askMutation.isPending) return;
    clearConversation(workspaceId);
    setPairs([]);
    setActiveEntryId(null);
    setSelectedCitation(null);
    setPreviewTarget(null);
    setIncompleteTurns([]);
    setAskError(null);
    setConflictHint(null);
    setQuestion("");
  }

  function closeSourcesDrawerThen(action: () => void) {
    setSourcesDrawerOpen(false);
    queueMicrotask(action);
  }

  function validateSelectedFiles(files: File[]): string | null {
    if (files.length === 0) return "Select at least one file.";
    if (!limits) {
      // Backend remains authoritative when capabilities are unavailable.
      return null;
    }
    if (sources.length + files.length > limits.maxActiveSources) {
      return `At most ${limits.maxActiveSources} active sources are allowed.`;
    }
    for (const file of files) {
      if (file.size > limits.maxBytesPerFile) {
        return `${file.name} exceeds the ${formatMiB(limits.maxBytesPerFile)} MiB per-file limit.`;
      }
    }
    const existingBytes = activeSourceBytes(sources);
    const incomingBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (existingBytes + incomingBytes > limits.maxDesiredActiveBytes) {
      return `Selected files would exceed the ${formatMiB(limits.maxDesiredActiveBytes)} MiB active-source budget.`;
    }
    return null;
  }

  function onAddSubmit(event: FormEvent) {
    event.preventDefault();
    if (
      !workspace ||
      addMutation.isPending ||
      pendingPhase === "uploading" ||
      addCancelReconciling
    ) {
      return;
    }
    if (addAmbiguous && addSourcesIntent) {
      // Unresolved ambiguous intent must be retried or explicitly abandoned.
      return;
    }
    const validation = validateSelectedFiles(selectedFiles);
    if (validation) {
      setAddError(validation);
      return;
    }
    const fingerprint = fingerprintAddSources({
      workspaceId,
      revision: workspace.revision,
      files: selectedFiles,
    });
    const idempotencyKey = addIntent.current.prepare(fingerprint);
    const intent: AddSourcesIntent = {
      workspaceId,
      expectedRevision: workspace.revision,
      files: selectedFiles,
      fingerprint,
      idempotencyKey,
    };
    submitAddSourcesIntent(intent);
  }

  if (workspaceQuery.isLoading) {
    return <p className="muted">Loading workspace…</p>;
  }

  if (workspaceQuery.isError || !workspace) {
    return (
      <Card>
        <h1>Workspace unavailable</h1>
        <p className="error-box" role="alert">
          {userFacingErrorMessage(workspaceQuery.error ?? new Error("Missing"))}
        </p>
        <Link to="/workspaces">Back to workspaces</Link>
      </Card>
    );
  }

  const isEmpty = workspace.status === "empty" || sources.length === 0;
  const usedBytes = activeSourceBytes(sources);
  const finalSourceWarning =
    removeTarget && sources.length === 1
      ? "Removing the final source will leave this workspace empty and retire its current searchable knowledge. Historical artifacts may remain locally."
      : "Removing this source rebuilds the workspace's current searchable knowledge from the remaining active sources. Historical artifacts may remain locally.";

  const busyForMutations =
    pendingPhase === "uploading" ||
    pendingPhase === "operation" ||
    askMutation.isPending;

  const history: ConversationHistoryEntry[] = pairs.map(toHistoryEntry);
  const activeEntry =
    history.find((entry) => entry.entryId === activeEntryId) ??
    history[0] ??
    null;

  const askDisabled =
    isEmpty ||
    selectedSourceIds.length === 0 ||
    question.trim().length === 0 ||
    askMutation.isPending;

  function openCitation(
    citation: WorkspaceCitation,
    entry: ConversationHistoryEntry,
  ) {
    setSelectedCitation(citation);
    setPreviewTarget({
      kind: "citation",
      workspaceId,
      citation,
      workspaceRevision: entry.response.workspace_revision,
      querySnapshotId: entry.response.snapshot_id,
    });
    if (isNarrowLayout) {
      setSourcesDrawerOpen(false);
      setEvidenceDrawerOpen(true);
    } else if (!evidenceRailExpanded) {
      // A3-D07: evidence inspection overrides collapsed Evidence rail.
      setEvidenceRailExpandedPersisted(true);
    }
  }

  function openSourcePreview(source: Source) {
    setSelectedCitation(null);
    setPreviewTarget({
      kind: "source",
      workspaceId,
      sourceId: source.source_id,
    });
    if (isNarrowLayout) {
      closeSourcesDrawerThen(() => setEvidenceDrawerOpen(true));
    } else if (!evidenceRailExpanded) {
      setEvidenceRailExpandedPersisted(true);
    }
  }

  const sourceRail = (
    <SourceRail
      sources={sources}
      selectedSourceIds={selectedSourceIds}
      limits={limits}
      capacityLoading={capabilitiesQuery.isLoading}
      capacityError={capabilitiesQuery.isError}
      sourcesLoading={sourcesQuery.isLoading}
      sourcesError={sourcesQuery.isError ? sourcesQuery.error : null}
      usedBytes={usedBytes}
      mutationsDisabled={busyForMutations}
      selectionDisabled={askMutation.isPending}
      isEmpty={isEmpty}
      onToggle={(sourceId, selected) => {
        const next = setSourceSelected(workspaceId, sources, sourceId, selected);
        setSelectedSourceIds(next.selectedSourceIds);
        setSelectionMode(next.mode);
      }}
      onSelectAll={() => {
        const next = selectAllSources(workspaceId, sources);
        setSelectedSourceIds(next.selectedSourceIds);
        setSelectionMode(next.mode);
      }}
      onAdd={() =>
        closeSourcesDrawerThen(() => {
          setAddOpen(true);
          setAddError(null);
          setSelectedFiles([]);
          addIntent.current = IntentHandle.newIntent();
        })
      }
      onPreview={openSourcePreview}
      onRename={(source) =>
        closeSourcesDrawerThen(() => {
          setRenameTarget(source);
          setRenameValue(source.display_name);
          setRenameError(null);
          renameIntent.current = IntentHandle.newIntent();
        })
      }
      onReplace={(source) =>
        closeSourcesDrawerThen(() => {
          setReplaceTarget(source);
          setReplaceFile(null);
          setReplaceError(null);
          replaceIntent.current = IntentHandle.newIntent();
        })
      }
      onRemove={(source) =>
        closeSourcesDrawerThen(() => {
          setRemoveTarget(source);
          setRemoveError(null);
          removeIntent.current = IntentHandle.newIntent();
        })
      }
    />
  );

  const evidencePanel = (
    <EvidencePanel
      previewTarget={previewTarget}
      activeEntry={activeEntry}
      selectedCitation={selectedCitation}
      currentSnapshotId={workspace.current_snapshot_id}
      currentSources={sources}
      currentWorkspaceRevision={workspace.revision}
    />
  );

  const showRunningTray =
    pendingPhase === "uploading" ||
    pendingPhase === "operation" ||
    (operationQuery.data &&
      !isTerminalOperationStatus(String(operationQuery.data.status)));

  const showFailedTerminal =
    pendingPhase === "terminal_error" &&
    operationQuery.data &&
    (String(operationQuery.data.status).toLowerCase() === "failed" ||
      String(operationQuery.data.status).toLowerCase() === "interrupted");

  const showCompactSuccess =
    operationQuery.data &&
    String(operationQuery.data.status).toLowerCase() === "succeeded" &&
    pendingPhase === "idle";

  return (
    <div className="stack workspace-page">
      <nav aria-label="Breadcrumb" className="muted">
        <Link to="/workspaces">Workspaces</Link>
        {" / "}
        <span>{workspace.title}</span>
      </nav>

      <header className="workspace-header">
        <div className="workspace-header-main">
          <div className="row" style={{ gap: "0.75rem" }}>
            <h1 style={{ margin: 0 }}>{workspace.title}</h1>
            <Badge
              tone={isEmpty ? "empty" : "ready"}
              label={isEmpty ? "Empty" : "Active"}
            />
          </div>
          <p className="muted capacity-summary" style={{ margin: 0 }}>
            {limits ? (
              <>
                {sources.length} / {limits.maxActiveSources} sources ·{" "}
                {formatMiB(usedBytes)} / {formatMiB(limits.maxDesiredActiveBytes)}{" "}
                MiB
              </>
            ) : (
              <>
                {sources.length} sources · {formatBytes(usedBytes)}
                {capabilitiesQuery.isError
                  ? " · capacity unavailable"
                  : " · loading capacity…"}
              </>
            )}
          </p>
        </div>
        <div className="row workspace-header-actions">
          <Button
            variant="secondary"
            onClick={() => setEditWorkspaceOpen(true)}
            disabled={busyForMutations}
          >
            Edit
          </Button>
        </div>
      </header>

      {showRunningTray ? (
        <div className="operation-tray" aria-live="polite">
          {pendingPhase === "uploading" ? (
            <OperationProgress phase="uploading" label={operationLabel} />
          ) : null}
          {pendingPhase === "operation" ||
          (operationQuery.data &&
            !isTerminalOperationStatus(String(operationQuery.data.status))) ? (
            <OperationProgress
              phase="operation"
              operation={operationQuery.data}
              label={operationLabel}
            />
          ) : null}
        </div>
      ) : null}

      {showFailedTerminal && operationQuery.data ? (
        <div className="operation-tray" aria-live="assertive">
          <OperationProgress
            phase="operation"
            operation={operationQuery.data}
            label={operationLabel}
            onDismiss={() => {
              forgetActiveOperation(operationQuery.data!.operation_id);
              setActiveOperationId(null);
              setPendingPhase("idle");
            }}
          />
        </div>
      ) : null}

      {showCompactSuccess && operationQuery.data ? (
        <p className="operation-compact muted" role="status">
          Ready
          {operationLabel ? ` · ${operationLabel}` : ""}
        </p>
      ) : null}

      <div className="knowledge-mobile-bar row">
        <Button
          variant="secondary"
          type="button"
          onClick={() => {
            setEvidenceDrawerOpen(false);
            setSourcesDrawerOpen(true);
          }}
        >
          Sources
        </Button>
        <Button
          variant="secondary"
          type="button"
          onClick={() => {
            setSourcesDrawerOpen(false);
            setEvidenceDrawerOpen(true);
          }}
        >
          Evidence
        </Button>
      </div>

      <div
        className={[
          "knowledge-layout",
          sourcesRailExpanded ? "" : "sources-collapsed",
          evidenceRailExpanded ? "" : "evidence-collapsed",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <aside
          id="workspace-sources-rail"
          className="knowledge-sources knowledge-desktop-only"
        >
          {sourcesRailExpanded ? (
            <div className="rail-shell">
              <div className="rail-toolbar">
                <button
                  type="button"
                  className="rail-toggle"
                  aria-expanded={true}
                  aria-controls="workspace-sources-rail"
                  aria-label="Collapse Sources"
                  onClick={() => setSourcesRailExpandedPersisted(false)}
                >
                  «
                </button>
              </div>
              {sourceRail}
            </div>
          ) : (
            <div className="rail-shell rail-shell-collapsed">
              <button
                type="button"
                className="rail-toggle rail-toggle-collapsed"
                aria-expanded={false}
                aria-controls="workspace-sources-rail"
                aria-label="Expand Sources"
                onClick={() => setSourcesRailExpandedPersisted(true)}
              >
                Sources
              </button>
            </div>
          )}
        </aside>
        <div className="knowledge-ask">
          <div className="rail-shell">
            <AskPanel
              question={question}
              onQuestionChange={setQuestion}
              onAsk={() => {
                if (askDisabled) return;
                submitAsk();
              }}
              onNewConversation={startNewConversation}
              askDisabled={askDisabled}
              askPending={askMutation.isPending}
              selectedCount={selectedSourceIds.length}
              totalCount={sources.length}
              askError={askError}
              conflictHint={conflictHint}
              activeEntry={activeEntry}
              history={history}
              incompleteTurns={incompleteTurns}
              selectedEvidenceUnitId={
                selectedCitation?.evidence_unit_id ?? null
              }
              onSelectCitation={(citation, entry) => {
                setActiveEntryId(entry.entryId);
                openCitation(citation, entry);
              }}
              onSelectHistory={(entry) => {
                setActiveEntryId(entry.entryId);
                const first = entry.response.citations[0] ?? null;
                setSelectedCitation(first);
                if (first) {
                  setPreviewTarget({
                    kind: "citation",
                    workspaceId,
                    citation: first,
                    workspaceRevision: entry.response.workspace_revision,
                    querySnapshotId: entry.response.snapshot_id,
                  });
                  if (!isNarrowLayout && !evidenceRailExpanded) {
                    setEvidenceRailExpandedPersisted(true);
                  }
                } else {
                  setPreviewTarget(null);
                }
              }}
              currentSnapshotId={workspace.current_snapshot_id}
              settingsHint={settingsHint}
            />
          </div>
        </div>
        <aside
          id="workspace-evidence-rail"
          className="knowledge-evidence knowledge-desktop-only"
        >
          {evidenceRailExpanded ? (
            <div className="rail-shell">
              <div className="rail-toolbar">
                <button
                  type="button"
                  className="rail-toggle"
                  aria-expanded={true}
                  aria-controls="workspace-evidence-rail"
                  aria-label="Collapse Evidence"
                  onClick={() => setEvidenceRailExpandedPersisted(false)}
                >
                  »
                </button>
              </div>
              {evidencePanel}
            </div>
          ) : (
            <div className="rail-shell rail-shell-collapsed">
              <button
                type="button"
                className="rail-toggle rail-toggle-collapsed"
                aria-expanded={false}
                aria-controls="workspace-evidence-rail"
                aria-label="Expand Evidence"
                onClick={() => setEvidenceRailExpandedPersisted(true)}
              >
                Evidence
              </button>
            </div>
          )}
        </aside>
      </div>

      {isNarrowLayout ? (
        <ResponsiveDrawer
          open={sourcesDrawerOpen}
          title="Sources"
          side="start"
          onClose={() => setSourcesDrawerOpen(false)}
        >
          {sourceRail}
        </ResponsiveDrawer>
      ) : null}

      {isNarrowLayout ? (
        <ResponsiveDrawer
          open={evidenceDrawerOpen}
          title="Evidence"
          side="end"
          onClose={() => setEvidenceDrawerOpen(false)}
        >
          {evidencePanel}
        </ResponsiveDrawer>
      ) : null}

      <ModalDialog
        open={editWorkspaceOpen}
        title="Edit workspace"
        description="Update title and description, or remove this workspace."
        onClose={() => setEditWorkspaceOpen(false)}
      >
        <WorkspaceMetadataForm
          key={workspace.workspace_id}
          workspace={workspace}
          onSaved={() => setEditWorkspaceOpen(false)}
          onRemoved={() => {
            setEditWorkspaceOpen(false);
            void navigate("/workspaces");
          }}
        />
      </ModalDialog>

      <ModalDialog
        open={addOpen}
        title="Add sources"
        description="Select files to add to this knowledge workspace."
        busy={false}
        onClose={closeAddSourcesModal}
      >
        <form className="stack" onSubmit={onAddSubmit}>
          <div className="field">
            <label htmlFor="add-files">Source files</label>
            <input
              key={addFileInputKey}
              id="add-files"
              type="file"
              multiple
              disabled={
                pendingPhase === "uploading" ||
                addMutation.isPending ||
                addCancelReconciling
              }
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (addAmbiguous && addSourcesIntent) {
                  // Explicit abandonment — new selection must not reuse old key.
                  abandonAddSourcesIntent();
                }
                setSelectedFiles(files);
                setAddError(null);
              }}
            />
            <p className="muted">
              {limits
                ? `Maximum file size: ${formatMiB(limits.maxBytesPerFile)} MiB`
                : "Maximum file size: determined by the server"}
            </p>
          </div>
          {(addSourcesIntent?.files ?? selectedFiles).length > 0 ? (
            <>
              <p className="muted" style={{ margin: 0 }}>
                {(() => {
                  const files = addSourcesIntent?.files ?? selectedFiles;
                  const label = files.length === 1 ? "file" : "files";
                  return `Selected: ${files.length} ${label} · ${formatBytes(
                    files.reduce((sum, file) => sum + file.size, 0),
                  )}`;
                })()}
              </p>
              <ul>
                {(addSourcesIntent?.files ?? selectedFiles).map((file) => (
                  <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                    {file.name} · {formatBytes(file.size)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {pendingPhase === "uploading" || addMutation.isPending ? (
            <p className="muted" aria-live="polite">
              Uploading...
            </p>
          ) : null}
          {addCancelReconciling ? (
            <p className="muted" aria-live="polite">
              Checking workspace state after cancel…
            </p>
          ) : null}
          {addError ? (
            <p className="error-box" role="alert">
              {addError}
            </p>
          ) : null}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            {pendingPhase === "uploading" || addMutation.isPending ? (
              <Button
                variant="secondary"
                type="button"
                onClick={cancelAddUpload}
              >
                Cancel upload
              </Button>
            ) : (
              <Button
                variant="secondary"
                type="button"
                onClick={closeAddSourcesModal}
              >
                Cancel
              </Button>
            )}
            {pendingPhase === "uploading" || addMutation.isPending ? null : addAmbiguous &&
              addSourcesIntent ? (
              <Button
                type="button"
                onClick={retryAddSourcesSafely}
                disabled={busyForMutations || addCancelReconciling}
              >
                Retry safely
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={
                  busyForMutations ||
                  addCancelReconciling ||
                  selectedFiles.length === 0
                }
              >
                Add sources
              </Button>
            )}
          </div>
        </form>
      </ModalDialog>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title="Remove source"
        body={finalSourceWarning}
        confirmLabel="Remove source"
        danger
        busy={removeMutation.isPending}
        onCancel={() => setRemoveTarget(null)}
        onConfirm={() => removeMutation.mutate()}
      />

      <ModalDialog
        open={Boolean(renameTarget)}
        title="Rename display label"
        description="This updates the display name only. It does not reindex or change the source version."
        busy={renameMutation.isPending}
        onClose={() => setRenameTarget(null)}
      >
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            renameMutation.mutate();
          }}
        >
          <TextInput
            id="rename-display-name"
            label="Display name"
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            maxLength={512}
            required
          />
          {renameError ? (
            <p className="error-box" role="alert">
              {renameError}
            </p>
          ) : null}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button
              variant="secondary"
              onClick={() => setRenameTarget(null)}
              disabled={renameMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={renameMutation.isPending}>
              Save label
            </Button>
          </div>
        </form>
      </ModalDialog>

      <ModalDialog
        open={Boolean(replaceTarget)}
        title="Replace current version"
        description={
          replaceTarget
            ? `Replace the current version of ${replaceTarget.display_name}. The logical source identity remains stable; this does not create a second copy.`
            : undefined
        }
        busy={replaceMutation.isPending}
        onClose={() => setReplaceTarget(null)}
      >
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (!replaceFile) {
              setReplaceError("Choose exactly one file.");
              return;
            }
            if (limits && replaceFile.size > limits.maxBytesPerFile) {
              setReplaceError(
                `File exceeds the ${formatMiB(limits.maxBytesPerFile)} MiB per-file limit.`,
              );
              return;
            }
            setReplaceError(null);
            setOperationLabel("Replace source");
            setPendingPhase("uploading");
            replaceMutation.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="replace-file">Replacement file</label>
            <input
              id="replace-file"
              type="file"
              onChange={(event) => {
                setReplaceFile(event.target.files?.[0] ?? null);
                setReplaceError(null);
              }}
            />
            {limits ? (
              <p className="muted">
                Maximum file size: {formatMiB(limits.maxBytesPerFile)} MiB
              </p>
            ) : null}
          </div>
          {replaceError ? (
            <p className="error-box" role="alert">
              {replaceError}
            </p>
          ) : null}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button
              variant="secondary"
              onClick={() => setReplaceTarget(null)}
              disabled={replaceMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={replaceMutation.isPending}>
              Replace current version
            </Button>
          </div>
        </form>
      </ModalDialog>

      {removeError ? (
        <p className="error-box" role="alert">
          {removeError}
        </p>
      ) : null}

      <p className="muted" style={{ margin: 0, fontSize: "0.875rem" }}>
        Revision {workspace.revision} · Last workspace change{" "}
        {formatTimestamp(workspace.updated_at)}
      </p>
    </div>
  );
}
