import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listGoldProjects } from "../features/goldLab/api/client";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import { goldLabQueryKeys } from "../features/goldLab/queryKeys";
import { GoldProjectCreateForm } from "../features/goldLab/shell/GoldProjectCreateForm";
import { GoldProjectList } from "../features/goldLab/shell/GoldProjectList";

export function GoldLabPage() {
  const projectsQuery = useQuery({
    queryKey: goldLabQueryKeys.projects,
    queryFn: ({ signal }) => listGoldProjects(signal),
  });

  return (
    <div className="stack gold-lab-page">
      <header>
          <h1>Advanced Gold Lab</h1>
        <p className="muted">
            Manage Gold projects, baselines, and campaigns. Quick Play is the
            streamlined workspace for expert judgments.
        </p>
          <Link to="/gold-lab">Return to Quick Play</Link>
      </header>

      <GoldProjectCreateForm />

      <section className="stack" aria-labelledby="gold-lab-projects-heading">
        <h2 id="gold-lab-projects-heading">Projects</h2>
        <GoldProjectList
          projects={projectsQuery.data?.projects ?? []}
          loading={projectsQuery.isLoading}
          errorMessage={
            projectsQuery.isError
              ? goldLabErrorMessage(projectsQuery.error)
              : null
          }
        />
      </section>
    </div>
  );
}
