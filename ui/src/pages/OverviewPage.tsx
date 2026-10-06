import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getHealthReady, listWorkspaces } from "../api/client";
import { userFacingErrorMessage } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { formatTimestamp } from "../features/workspaces/format";

export function OverviewPage() {
  const healthQuery = useQuery({
    queryKey: queryKeys.healthReady,
    queryFn: ({ signal }) => getHealthReady(signal),
  });
  const workspacesQuery = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });

  const workspaces = workspacesQuery.data ?? [];
  const workspaceCount = workspaces.length;
  const activeSourceCount = workspaces.reduce(
    (sum, workspace) => sum + workspace.source_count,
    0,
  );
  const ready = healthQuery.data?.status === "ready";

  return (
    <div className="stack">
      <header>
        <h1>OfflineRAG</h1>
        <p className="muted">
          Local operational knowledge workspaces for this OfflineRAG
          installation.
        </p>
      </header>

      <Card>
        <h2>System status</h2>
        <div className="row">
          {healthQuery.isLoading ? (
            <Badge tone="busy" label="Checking readiness" />
          ) : ready ? (
            <Badge tone="ready" label="Ready" />
          ) : (
            <Badge tone="error" label="Not ready" />
          )}
          <span className="muted">
            {ready
              ? "GET /health/ready reports ready."
              : healthQuery.isError
                ? userFacingErrorMessage(healthQuery.error)
                : "Waiting for readiness."}
          </span>
        </div>
      </Card>

      <div className="row" style={{ alignItems: "stretch" }}>
        <Card className="stack" style={{ flex: "1 1 14rem" }}>
          <h2>Workspaces</h2>
          <p style={{ fontSize: "2rem", margin: 0, fontWeight: 700 }}>
            {workspacesQuery.isLoading ? "—" : workspaceCount}
          </p>
          <p className="muted">Active library entries from this installation.</p>
        </Card>
        <Card className="stack" style={{ flex: "1 1 14rem" }}>
          <h2>Active sources</h2>
          <p style={{ fontSize: "2rem", margin: 0, fontWeight: 700 }}>
            {workspacesQuery.isLoading ? "—" : activeSourceCount}
          </p>
          <p className="muted">
            Sum of current active sources across listed workspaces.
          </p>
        </Card>
        <Card className="stack" style={{ flex: "1 1 14rem" }}>
          <h2>Local storage</h2>
          <Badge tone="ready" label="Local / offline product" />
          <p className="muted">
            Source data is managed by this OfflineRAG installation. No cloud
            source upload is provided by this product.
          </p>
        </Card>
      </div>

      <Card>
        <h2>Manage sources</h2>
        <p className="muted">
          Create and maintain workspaces and their active sources. Asking
          questions and reviewing evidence belong to a later phase and are not
          available here.
        </p>
        <div className="row">
          <Link to="/workspaces">
            <Button>Open workspaces</Button>
          </Link>
        </div>
      </Card>

      <section className="stack" aria-labelledby="available-workspaces">
        <h2 id="available-workspaces">Available workspaces</h2>
        {workspacesQuery.isError ? (
          <p className="error-box" role="alert">
            {userFacingErrorMessage(workspacesQuery.error)}
          </p>
        ) : null}
        {workspacesQuery.isLoading ? (
          <p className="muted">Loading workspaces…</p>
        ) : null}
        {!workspacesQuery.isLoading && workspaces.length === 0 ? (
          <Card>
            <p className="muted">
              No workspaces yet. Create one from the workspace library.
            </p>
            <Link to="/workspaces">
              <Button>Create a workspace</Button>
            </Link>
          </Card>
        ) : null}
        {workspaces.map((workspace) => (
          <Card key={workspace.workspace_id}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <h3 style={{ marginBottom: "0.35rem" }}>{workspace.title}</h3>
                <p className="muted" style={{ marginBottom: "0.35rem" }}>
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
              <Link to={`/workspaces/${workspace.workspace_id}`}>
                <Button variant="secondary">Open</Button>
              </Link>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
