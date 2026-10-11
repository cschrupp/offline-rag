import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listWorkspaces } from "../../../api/client";
import { queryKeys } from "../../../api/queryKeys";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { Field, TextArea, TextInput } from "../../../components/Field";
import { createGoldProject } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";
import type { GoldProjectType } from "../types";

export function GoldProjectCreateForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [workspaceId, setWorkspaceId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [projectType, setProjectType] =
    useState<GoldProjectType>("benchmark");
  const [formError, setFormError] = useState<string | null>(null);

  const workspacesQuery = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });

  const usableWorkspaces = (workspacesQuery.data ?? []).filter(
    (workspace) => workspace.status !== "tombstoned",
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createGoldProject({
        workspace_id: workspaceId,
        title: title.trim(),
        description,
        project_type: projectType,
      }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({
        queryKey: goldLabQueryKeys.projects,
      });
      setFormError(null);
      void navigate(`/gold-lab/projects/${project.project_id}`);
    },
    onError: (error) => {
      setFormError(goldLabErrorMessage(error));
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!workspaceId) {
      setFormError("Select an existing workspace.");
      return;
    }
    if (!title.trim()) {
      setFormError("Title is required.");
      return;
    }
    createMutation.mutate();
  }

  if (workspacesQuery.isLoading) {
    return (
      <Card>
        <h2>Create Gold project</h2>
        <p className="muted">Loading workspaces…</p>
      </Card>
    );
  }

  if (workspacesQuery.isError) {
    return (
      <Card>
        <h2>Create Gold project</h2>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(workspacesQuery.error)}
        </p>
      </Card>
    );
  }

  if (usableWorkspaces.length === 0) {
    return (
      <EmptyState
        title="No usable workspaces"
        body="Gold projects require an existing non-tombstoned workspace. Create a workspace first, then return here."
        action={<Button to="/workspaces">Open Workspaces</Button>}
      />
    );
  }

  return (
    <Card>
      <h2>Create Gold project</h2>
      <form className="stack" onSubmit={onSubmit}>
        <Field
          id="gold-project-workspace"
          label="Workspace"
          hint="Choose an existing workspace. Gold Lab does not invent workspaces."
        >
          <select
            id="gold-project-workspace"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.target.value)}
            required
          >
            <option value="">Select a workspace</option>
            {usableWorkspaces.map((workspace) => (
              <option
                key={workspace.workspace_id}
                value={workspace.workspace_id}
              >
                {workspace.title} ({workspace.workspace_id})
              </option>
            ))}
          </select>
        </Field>

        <TextInput
          id="gold-project-title"
          label="Title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          required
        />

        <TextArea
          id="gold-project-description"
          label="Description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />

        <fieldset className="gold-lab-fieldset">
          <legend>Project type</legend>
          <p className="muted">
            Benchmark is representative evaluation-oriented Gold work.
            Improvement is diagnostic / improvement-oriented Gold work. A
            Benchmark project does not automatically satisfy publication
            readiness.
          </p>
          <div className="row gold-lab-radio-row">
            <label className="gold-lab-radio">
              <input
                type="radio"
                name="gold-project-type"
                value="benchmark"
                checked={projectType === "benchmark"}
                onChange={() => setProjectType("benchmark")}
              />
              <span>
                <strong>Benchmark</strong>
                <span className="muted">
                  {" "}
                  — Representative evaluation-oriented Gold work
                </span>
              </span>
            </label>
            <label className="gold-lab-radio">
              <input
                type="radio"
                name="gold-project-type"
                value="improvement"
                checked={projectType === "improvement"}
                onChange={() => setProjectType("improvement")}
              />
              <span>
                <strong>Improvement</strong>
                <span className="muted">
                  {" "}
                  — Diagnostic / improvement-oriented Gold work
                </span>
              </span>
            </label>
          </div>
        </fieldset>

        {formError ? (
          <p className="error-box" role="alert">
            {formError}
          </p>
        ) : null}

        <div className="row">
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Creating…" : "Create project"}
          </Button>
          <Link className="muted" to="/workspaces">
            Manage workspaces
          </Link>
        </div>
      </form>
    </Card>
  );
}
