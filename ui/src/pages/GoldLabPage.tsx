import { useQuery } from "@tanstack/react-query";
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
        <h1>Gold Lab</h1>
        <p className="muted">
          Organize Gold projects and campaigns. Expert adjudication games are
          configured from a campaign shell.
        </p>
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
