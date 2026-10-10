import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { getGoldProject } from "../features/goldLab/api/client";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import { GoldProjectDetail } from "../features/goldLab/shell/GoldProjectDetail";

export function GoldLabProjectPage() {
  const { projectId = "" } = useParams();

  const projectQuery = useQuery({
    queryKey: goldLabQueryKeys.project(projectId),
    queryFn: ({ signal }) => getGoldProject(projectId, signal),
    enabled: Boolean(projectId),
  });

  if (!projectId) {
    return (
      <Card>
        <h1>Gold project</h1>
        <p className="error-box" role="alert">
          Missing project identity.
        </p>
        <Button to="/gold-lab">Back to Gold Lab</Button>
      </Card>
    );
  }

  if (projectQuery.isLoading) {
    return (
      <div className="stack gold-lab-page">
        <p className="muted">Loading Gold project…</p>
      </div>
    );
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <Card>
        <h1>Gold project</h1>
        <p className="error-box" role="alert">
          {goldLabErrorMessage(projectQuery.error)}
        </p>
        <p>
          <Link to="/gold-lab">Back to Gold Lab</Link>
        </p>
      </Card>
    );
  }

  return <GoldProjectDetail project={projectQuery.data} />;
}
