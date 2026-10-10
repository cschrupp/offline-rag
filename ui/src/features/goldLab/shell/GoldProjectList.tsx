import { Link } from "react-router-dom";
import { Badge } from "../../../components/Badge";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { formatTimestamp } from "../../workspaces/format";
import type { GoldProject } from "../types";

function projectTypeLabel(type: GoldProject["project_type"]): string {
  return type === "benchmark" ? "Benchmark" : "Improvement";
}

type Props = {
  projects: GoldProject[];
  loading: boolean;
  errorMessage: string | null;
};

export function GoldProjectList({ projects, loading, errorMessage }: Props) {
  if (loading) {
    return <p className="muted">Loading Gold projects…</p>;
  }

  if (errorMessage) {
    return (
      <p className="error-box" role="alert">
        {errorMessage}
      </p>
    );
  }

  if (projects.length === 0) {
    return (
      <EmptyState
        title="No Gold projects yet"
        body="Create a Gold project to organize campaigns against eligible authoring baselines."
      />
    );
  }

  return (
    <ul className="stack gold-lab-list">
      {projects.map((project) => (
        <li key={project.project_id}>
          <Card>
            <div className="row gold-lab-card-header">
              <div className="stack" style={{ gap: "0.35rem", minWidth: 0 }}>
                <h2 style={{ margin: 0 }}>
                  <Link to={`/gold-lab/projects/${project.project_id}`}>
                    {project.title}
                  </Link>
                </h2>
                <p className="muted" style={{ margin: 0 }}>
                  {project.description || "No description"}
                </p>
              </div>
              <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                <Badge
                  tone={
                    project.project_type === "benchmark" ? "ready" : "busy"
                  }
                  label={projectTypeLabel(project.project_type)}
                />
                <Badge
                  tone={project.status === "active" ? "ready" : "empty"}
                  label={project.status === "active" ? "Active" : "Archived"}
                />
              </div>
            </div>
            <dl className="gold-lab-meta">
              <div>
                <dt>Workspace</dt>
                <dd>
                  <code>{project.workspace_id}</code>
                </dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatTimestamp(project.created_at)}</dd>
              </div>
            </dl>
          </Card>
        </li>
      ))}
    </ul>
  );
}
