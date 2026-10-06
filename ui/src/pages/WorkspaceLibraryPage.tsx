import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createWorkspace, listWorkspaces } from "../api/client";
import { isApiError, userFacingErrorMessage } from "../api/errors";
import {
  IntentHandle,
  fingerprintCreateWorkspace,
} from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { TextArea, TextInput } from "../components/Field";
import { formatTimestamp } from "../features/workspaces/format";

export function WorkspaceLibraryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const intent = useRef(IntentHandle.newIntent());

  const workspacesQuery = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const trimmedTitle = title.trim();
      const trimmedDescription = description.trim();
      const key = intent.current.prepare(
        fingerprintCreateWorkspace(trimmedTitle, trimmedDescription),
      );
      return createWorkspace({
        title: trimmedTitle,
        description: trimmedDescription,
        idempotencyKey: key,
      });
    },
    onSuccess: async (workspace) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
      setTitle("");
      setDescription("");
      setFormError(null);
      intent.current.reset();
      void navigate(`/workspaces/${workspace.workspace_id}`);
    },
    onError: (error) => {
      setFormError(userFacingErrorMessage(error));
      if (isApiError(error) && error.kind !== "network") {
        intent.current.reset();
      }
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!title.trim() || title.trim().length > 256) {
      setFormError("Title must be 1–256 characters.");
      return;
    }
    if (description.length > 4096) {
      setFormError("Description must be at most 4096 characters.");
      return;
    }
    createMutation.mutate();
  }

  const workspaces = workspacesQuery.data ?? [];

  return (
    <div className="stack">
      <header>
        <h1>Workspaces</h1>
        <p className="muted">
          Manage the active workspace library for this OfflineRAG installation.
        </p>
      </header>

      <Card>
        <h2>Create workspace</h2>
        <form className="stack" onSubmit={onSubmit}>
          <TextInput
            id="workspace-title"
            label="Title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={256}
            required
            hint="1–256 characters"
          />
          <TextArea
            id="workspace-description"
            label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={4096}
            hint="Optional, up to 4096 characters"
          />
          {formError ? (
            <p className="error-box" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="row">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating…" : "Create workspace"}
            </Button>
          </div>
        </form>
      </Card>

      {workspacesQuery.isError ? (
        <p className="error-box" role="alert">
          {userFacingErrorMessage(workspacesQuery.error)}
        </p>
      ) : null}

      {workspacesQuery.isLoading ? (
        <p className="muted">Loading workspaces…</p>
      ) : null}

      {!workspacesQuery.isLoading && workspaces.length === 0 ? (
        <EmptyState
          title="No workspaces yet"
          body="Create a workspace to begin adding sources. Sample or demo workspaces are not provided."
        />
      ) : null}

      {workspaces.map((workspace) => (
        <Card key={workspace.workspace_id}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="stack" style={{ gap: "0.5rem" }}>
              <h2 style={{ margin: 0 }}>{workspace.title}</h2>
              <p className="muted" style={{ margin: 0 }}>
                {workspace.description || "No description"}
              </p>
              <div className="row">
                <Badge
                  tone={workspace.status === "empty" ? "empty" : "ready"}
                  label={
                    workspace.status === "empty"
                      ? "Empty"
                      : workspace.status === "active"
                        ? "Active"
                        : workspace.status
                  }
                />
                <span className="muted">
                  {workspace.source_count} source
                  {workspace.source_count === 1 ? "" : "s"}
                </span>
                <span className="muted">
                  Last workspace change {formatTimestamp(workspace.updated_at)}
                </span>
              </div>
            </div>
            <Button
              to={`/workspaces/${workspace.workspace_id}`}
              variant="secondary"
            >
              Open / Manage
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
