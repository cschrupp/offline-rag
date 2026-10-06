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
import type { Operation, Source } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { TextInput } from "../components/Field";
import { ModalDialog } from "../components/ModalDialog";
import { OperationProgress } from "../components/OperationProgress";
import {
  forgetActiveOperation,
  isTerminalOperationStatus,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import { WorkspaceMetadataForm } from "../features/workspaces/WorkspaceMetadataForm";
import {
  SOURCE_LIMITS,
  formatBytes,
  formatTimestamp,
  shortenId,
} from "../features/workspaces/format";

type PendingPhase = "idle" | "uploading" | "operation";

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

  const workspace = workspaceQuery.data;
  const sources = sourcesQuery.data?.sources ?? [];

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [addError, setAddError] = useState<string | null>(null);

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

  function settleTerminalOperation(operation: Operation) {
    if (handledTerminalOps.current.has(operation.operation_id)) return;
    handledTerminalOps.current.add(operation.operation_id);
    forgetActiveOperation(operation.operation_id);
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspace(workspaceId),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources(workspaceId),
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
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

  const addMutation = useMutation({
    mutationFn: async () => {
      if (!workspace) throw new Error("Workspace not loaded");
      const key = addIntent.current.prepare(
        fingerprintAddSources({
          workspaceId,
          revision: workspace.revision,
          files: selectedFiles,
        }),
      );
      return addSources({
        workspaceId,
        files: selectedFiles,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: (operation) => {
      beginOperation(operation, "Add sources");
      setSelectedFiles([]);
      addIntent.current.reset();
    },
    onError: (error) => {
      setPendingPhase("idle");
      setAddError(userFacingErrorMessage(error));
      if (handleConflict(error) || (isApiError(error) && error.kind !== "network")) {
        addIntent.current.reset();
      }
    },
  });

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

  function validateSelectedFiles(files: File[]): string | null {
    if (files.length === 0) return "Select at least one file.";
    if (sources.length + files.length > SOURCE_LIMITS.maxActiveSources) {
      return `At most ${SOURCE_LIMITS.maxActiveSources} active sources are allowed.`;
    }
    for (const file of files) {
      if (file.size > SOURCE_LIMITS.maxBytesPerFile) {
        return `${file.name} exceeds the 25 MiB per-file limit.`;
      }
    }
    const existingBytes = sources.reduce((sum, source) => sum + source.byte_size, 0);
    const incomingBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (existingBytes + incomingBytes > SOURCE_LIMITS.maxDesiredActiveBytes) {
      return "Selected files would exceed the 100 MiB active-source budget.";
    }
    return null;
  }

  function onAddSubmit(event: FormEvent) {
    event.preventDefault();
    const validation = validateSelectedFiles(selectedFiles);
    if (validation) {
      setAddError(validation);
      return;
    }
    setAddError(null);
    setOperationLabel("Add sources");
    setPendingPhase("uploading");
    addMutation.mutate();
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
  const finalSourceWarning =
    removeTarget && sources.length === 1
      ? "Removing the final source will leave this workspace empty and retire its current searchable knowledge. Historical artifacts may remain locally."
      : "Removing this source rebuilds the workspace's current searchable knowledge from the remaining active sources. Historical artifacts may remain locally.";

  return (
    <div className="stack">
      <nav aria-label="Breadcrumb" className="muted">
        <Link to="/workspaces">Workspaces</Link>
        {" / "}
        <span>{workspace.title}</span>
      </nav>

      <header className="stack" style={{ gap: "0.75rem" }}>
        <div className="row">
          <h1 style={{ margin: 0 }}>{workspace.title}</h1>
          <Badge
            tone={isEmpty ? "empty" : "ready"}
            label={isEmpty ? "Empty" : "Active"}
          />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          {workspace.description || "No description"}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Revision {workspace.revision} · {workspace.source_count} source
          {workspace.source_count === 1 ? "" : "s"} · Last workspace change{" "}
          {formatTimestamp(workspace.updated_at)}
        </p>
      </header>

      {pendingPhase === "uploading" ? (
        <OperationProgress phase="uploading" label={operationLabel} />
      ) : null}
      {pendingPhase === "operation" || operationQuery.data ? (
        <OperationProgress
          phase="operation"
          operation={operationQuery.data}
          label={operationLabel}
        />
      ) : null}

      <WorkspaceMetadataForm
        key={workspace.workspace_id}
        workspace={workspace}
        onRemoved={() => {
          void navigate("/workspaces");
        }}
      />

      {isEmpty ? (
        <EmptyState
          title="This workspace is empty"
          body="This workspace is ready for sources but currently contains no active knowledge."
          action={
            <span className="muted">Use Add sources below to get started.</span>
          }
        />
      ) : null}

      <Card>
        <h2>Add sources</h2>
        <form className="stack" onSubmit={onAddSubmit}>
          <div className="field">
            <label htmlFor="add-files">Source files</label>
            <input
              id="add-files"
              type="file"
              multiple
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                setSelectedFiles(files);
                setAddError(null);
              }}
            />
            <p className="muted">
              Limits (backend authoritative): max 32 active sources, 25 MiB per
              file, 100 MiB desired active total.
            </p>
          </div>
          {selectedFiles.length > 0 ? (
            <ul>
              {selectedFiles.map((file) => (
                <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                  {file.name} · {formatBytes(file.size)}
                </li>
              ))}
            </ul>
          ) : null}
          {addError ? (
            <p className="error-box" role="alert">
              {addError}
            </p>
          ) : null}
          <Button
            type="submit"
            disabled={addMutation.isPending || pendingPhase !== "idle"}
          >
            Add sources
          </Button>
        </form>
      </Card>

      <section className="stack" aria-labelledby="source-list-heading">
        <h2 id="source-list-heading">Active sources</h2>
        {sourcesQuery.isError ? (
          <p className="error-box" role="alert">
            {userFacingErrorMessage(sourcesQuery.error)}
          </p>
        ) : null}
        {sourcesQuery.isLoading ? (
          <p className="muted">Loading sources…</p>
        ) : null}
        {sources.map((source) => (
          <Card key={source.source_id}>
            <div className="stack" style={{ gap: "0.75rem" }}>
              <div>
                <h3 style={{ marginBottom: "0.35rem" }}>
                  {source.display_name}
                </h3>
                <div className="row">
                  <span className="muted">
                    {source.content_type || "unknown type"}
                  </span>
                  <span className="muted">{formatBytes(source.byte_size)}</span>
                  <Badge tone="ready" label={`Version ${source.version}`} />
                  <span className="muted">
                    Added {formatTimestamp(source.created_at)}
                  </span>
                </div>
                <details>
                  <summary>Technical details</summary>
                  <p className="muted">
                    Document identity: {shortenId(source.document_id, 16)}
                  </p>
                </details>
              </div>
              <div className="row">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setRenameTarget(source);
                    setRenameValue(source.display_name);
                    setRenameError(null);
                    renameIntent.current = IntentHandle.newIntent();
                  }}
                >
                  Rename
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setReplaceTarget(source);
                    setReplaceFile(null);
                    setReplaceError(null);
                    replaceIntent.current = IntentHandle.newIntent();
                  }}
                >
                  Replace current version
                </Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    setRemoveTarget(source);
                    setRemoveError(null);
                    removeIntent.current = IntentHandle.newIntent();
                  }}
                >
                  Remove source
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </section>

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
            if (replaceFile.size > SOURCE_LIMITS.maxBytesPerFile) {
              setReplaceError("File exceeds the 25 MiB per-file limit.");
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
    </div>
  );
}
