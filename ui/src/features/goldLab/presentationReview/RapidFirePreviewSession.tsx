import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../../components/Button";
import { getGoldTask, listGoldTasks } from "../api/readClient";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { RapidFirePresentation } from "../games/rapidFire/RapidFirePresentation";
import { goldLabQueryKeys } from "../queryKeys";
import type { AbsoluteRelevanceTaskDetail, GoldRelevance } from "../types";
import { createPreviewInteraction } from "./PreviewInteraction";
import {
  PREVIEW_LOCAL_STATUS,
  type PreviewResponse,
} from "./previewTypes";

type Props = {
  campaignId: string;
};

export function RapidFirePreviewSession({ campaignId }: Props) {
  const [previewResponse, setPreviewResponse] =
    useState<PreviewResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const interaction = useMemo(
    () =>
      createPreviewInteraction({
        getResponse: () => previewResponse,
        setResponse: setPreviewResponse,
      }),
    [previewResponse],
  );

  const tasksQuery = useQuery({
    queryKey: [
      ...goldLabQueryKeys.tasks(campaignId),
      "presentation-review",
      "absolute_relevance",
    ],
    queryFn: ({ signal }) =>
      listGoldTasks(
        campaignId,
        { kind: "absolute_relevance", state: "pending", active: true },
        signal,
      ),
  });

  const pending = tasksQuery.data?.tasks ?? [];
  const activeTaskId =
    selectedTaskId && pending.some((t) => t.task_id === selectedTaskId)
      ? selectedTaskId
      : (pending[0]?.task_id ?? null);

  const detailQuery = useQuery({
    queryKey: goldLabQueryKeys.task(campaignId, activeTaskId ?? ""),
    queryFn: ({ signal }) =>
      getGoldTask(campaignId, activeTaskId!, "absolute_relevance", signal),
    enabled: Boolean(activeTaskId),
  });

  async function onCommit(relevance: GoldRelevance) {
    if (!activeTaskId) return;
    await interaction.submitRelevance(activeTaskId, relevance);
    setStatusMessage(PREVIEW_LOCAL_STATUS);
  }

  function onNext() {
    if (!activeTaskId) return;
    const idx = pending.findIndex((t) => t.task_id === activeTaskId);
    const next = pending[idx + 1] ?? pending[0] ?? null;
    interaction.clear();
    setStatusMessage(null);
    setSelectedTaskId(next?.task_id ?? null);
  }

  function onCorrect() {
    interaction.clear();
    setStatusMessage(null);
  }

  if (tasksQuery.isLoading) {
    return <p className="muted">Loading Rapid Fire tasks…</p>;
  }
  if (tasksQuery.isError) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(tasksQuery.error)}
      </p>
    );
  }
  if (pending.length === 0) {
    return (
      <p className="muted" role="status" data-testid="rf-preview-unavailable">
        Rapid Fire preview is not available yet. Approve the Question Check
        presentation, record one real Question Check Accept or Edit in normal
        Gold work, then return here to inspect Rapid Fire.
      </p>
    );
  }

  if (detailQuery.isLoading) {
    return <p className="muted">Loading task detail…</p>;
  }
  if (detailQuery.isError || !detailQuery.data) {
    return (
      <p className="error-box" role="alert">
        {goldLabErrorMessage(detailQuery.error)}
      </p>
    );
  }

  const task = detailQuery.data as AbsoluteRelevanceTaskDetail;
  if (!task.active) {
    return (
      <p className="error-box" role="alert" data-testid="rf-preview-inactive">
        Rapid Fire preview refused an inactive absolute-relevance task. Preview
        never activates inactive scientific work.
      </p>
    );
  }

  const locked = previewResponse !== null;

  return (
    <div className="stack" data-testid="rf-preview-session">
      <p className="muted" role="status">
        Previewing real pending active Rapid Fire task{" "}
        <code>{task.task_id}</code> ({pending.length} available).
      </p>
      <RapidFirePresentation
        key={task.task_id}
        task={task}
        locked={locked}
        errorMessage={null}
        statusMessage={statusMessage}
        showAfterAction={previewResponse?.kind === "rapid_fire"}
        afterActionReplayed={false}
        onCommit={(relevance) => {
          void onCommit(relevance);
        }}
        onNext={onNext}
        onCorrect={onCorrect}
        nextDisabled={pending.length < 2 && previewResponse !== null}
      />
      {previewResponse?.kind === "rapid_fire" ? (
        <p className="muted" role="status" data-testid="preview-response-summary">
          Local preview relevance: {previewResponse.relevance}
        </p>
      ) : null}
      {pending.length > 1 ? (
        <div className="row">
          <Button
            variant="secondary"
            onClick={() => {
              interaction.clear();
              setStatusMessage(null);
              const idx = pending.findIndex((t) => t.task_id === activeTaskId);
              const prev =
                pending[idx - 1] ?? pending[pending.length - 1] ?? null;
              setSelectedTaskId(prev?.task_id ?? null);
            }}
          >
            Previous preview task
          </Button>
        </div>
      ) : null}
    </div>
  );
}
