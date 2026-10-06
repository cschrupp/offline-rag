import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { deleteWorkspace, patchWorkspace } from "../../api/client";
import { isApiError, userFacingErrorMessage } from "../../api/errors";
import {
  IntentHandle,
  fingerprintDeleteWorkspace,
  fingerprintPatchWorkspace,
} from "../../api/idempotency";
import { queryKeys } from "../../api/queryKeys";
import type { Workspace } from "../../api/types";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { TextArea, TextInput } from "../../components/Field";

type Props = {
  workspace: Workspace;
  onRemoved: () => void;
  onSaved?: (workspace: Workspace) => void;
};

type FormSnapshot = {
  revision: number;
  title: string;
  description: string;
};

export function WorkspaceMetadataForm({
  workspace,
  onRemoved,
  onSaved,
}: Props) {
  const queryClient = useQueryClient();
  const patchIntent = useRef(IntentHandle.newIntent());
  const removeIntent = useRef(IntentHandle.newIntent());
  const [snapshot, setSnapshot] = useState<FormSnapshot>({
    revision: workspace.revision,
    title: workspace.title,
    description: workspace.description,
  });
  if (workspace.revision !== snapshot.revision) {
    setSnapshot({
      revision: workspace.revision,
      title: workspace.title,
      description: workspace.description,
    });
  }

  const [metaError, setMetaError] = useState<string | null>(null);
  const [removeOpen, setRemoveOpen] = useState(false);

  const patchMutation = useMutation({
    mutationFn: () => {
      const title = snapshot.title.trim();
      const description = snapshot.description.trim();
      const key = patchIntent.current.prepare(
        fingerprintPatchWorkspace({
          workspaceId: workspace.workspace_id,
          revision: workspace.revision,
          title,
          description,
        }),
      );
      return patchWorkspace({
        workspaceId: workspace.workspace_id,
        title,
        description,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(
        queryKeys.workspace(workspace.workspace_id),
        updated,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
      setMetaError(null);
      patchIntent.current.reset();
      onSaved?.(updated);
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "workspace_conflict") {
        setMetaError(userFacingErrorMessage(error));
        void queryClient.invalidateQueries({
          queryKey: queryKeys.workspace(workspace.workspace_id),
        });
        void queryClient.invalidateQueries({
          queryKey: queryKeys.workspaceSources(workspace.workspace_id),
        });
        patchIntent.current.reset();
        return;
      }
      setMetaError(userFacingErrorMessage(error));
      if (isApiError(error) && error.kind !== "network") {
        patchIntent.current.reset();
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      const key = removeIntent.current.prepare(
        fingerprintDeleteWorkspace({
          workspaceId: workspace.workspace_id,
          revision: workspace.revision,
        }),
      );
      return deleteWorkspace({
        workspaceId: workspace.workspace_id,
        revision: workspace.revision,
        idempotencyKey: key,
      });
    },
    onSuccess: async () => {
      setRemoveOpen(false);
      removeIntent.current.reset();
      queryClient.removeQueries({
        queryKey: queryKeys.workspace(workspace.workspace_id),
      });
      queryClient.removeQueries({
        queryKey: queryKeys.workspaceSources(workspace.workspace_id),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
      onRemoved();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "workspace_conflict") {
        setMetaError(userFacingErrorMessage(error));
        void queryClient.invalidateQueries({
          queryKey: queryKeys.workspace(workspace.workspace_id),
        });
        removeIntent.current.reset();
        setRemoveOpen(false);
        return;
      }
      setMetaError(userFacingErrorMessage(error));
      if (isApiError(error) && error.kind !== "network") {
        removeIntent.current.reset();
      }
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setMetaError(null);
    patchMutation.mutate();
  }

  return (
    <div className="stack">
      <form className="stack" onSubmit={onSubmit}>
        <TextInput
          id="edit-title"
          label="Title"
          value={snapshot.title}
          onChange={(event) =>
            setSnapshot((current) => ({ ...current, title: event.target.value }))
          }
          maxLength={256}
          required
        />
        <TextArea
          id="edit-description"
          label="Description"
          value={snapshot.description}
          onChange={(event) =>
            setSnapshot((current) => ({
              ...current,
              description: event.target.value,
            }))
          }
          maxLength={4096}
        />
        {metaError ? (
          <p className="error-box" role="alert">
            {metaError}
          </p>
        ) : null}
        <div className="row">
          <Button type="submit" disabled={patchMutation.isPending}>
            Save changes
          </Button>
          <Button
            variant="danger"
            onClick={() => setRemoveOpen(true)}
            disabled={deleteMutation.isPending}
          >
            Remove workspace
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={removeOpen}
        title="Remove workspace"
        body="This removes the workspace from the active library. Historical/source artifacts may remain stored locally. This is not secure permanent deletion."
        confirmLabel="Remove workspace"
        danger
        busy={deleteMutation.isPending}
        onCancel={() => setRemoveOpen(false)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </div>
  );
}
