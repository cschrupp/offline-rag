import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../../components/Button";
import { getGoldTask, listGoldTasks } from "../api/readClient";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import {
  QuestionCheckPresentation,
  type QuestionCheckCommitDraft,
} from "../games/questionCheck/QuestionCheckPresentation";
import { goldLabQueryKeys } from "../queryKeys";
import type { QuestionCheckTaskDetail } from "../types";
import { createPreviewInteraction } from "./PreviewInteraction";
import { isPreviewableTaskDetail } from "./previewEligibility";
import {
  PREVIEW_CORRECT_LABEL,
  PREVIEW_LOCAL_STATUS,
  PREVIEW_NEXT_LABEL,
  type PreviewResponse,
} from "./previewTypes";

type Props = {
  campaignId: string;
};

export function QuestionCheckPreviewSession({ campaignId }: Props) {
  const [previewResponse, setPreviewResponse] =
    useState<PreviewResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

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
      "question_check",
    ],
    queryFn: ({ signal }) =>
      listGoldTasks(
        campaignId,
        { kind: "question_check", state: "pending", active: true },
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
      getGoldTask(campaignId, activeTaskId!, "question_check", signal),
    enabled: Boolean(activeTaskId),
  });

  async function onCommit(draft: QuestionCheckCommitDraft) {
    if (!activeTaskId) return;
    await interaction.submitQuestionCheck(activeTaskId, draft);
  }

  function onNext() {
    if (!activeTaskId) return;
    const idx = pending.findIndex((t) => t.task_id === activeTaskId);
    const next = pending[idx + 1] ?? pending[0] ?? null;
    interaction.clear();
    setSelectedTaskId(next?.task_id ?? null);
  }

  function onCorrect() {
    interaction.clear();
  }

  if (tasksQuery.isLoading) {
    return <p className="muted">Loading Question Check tasks…</p>;
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
      <p className="muted" role="status" data-testid="qc-preview-empty">
        No pending active Question Check tasks are available for preview in this
        campaign.
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

  const task = detailQuery.data as QuestionCheckTaskDetail;
  if (!isPreviewableTaskDetail(task)) {
    return (
      <p className="error-box" role="alert" data-testid="qc-preview-stale">
        Question Check preview is not available for this task because it is no
        longer pending and active. Refresh the campaign task list and try again.
      </p>
    );
  }

  const locked = previewResponse !== null;

  return (
    <div className="stack" data-testid="qc-preview-session">
      <p className="muted" role="status">
        Previewing real pending Question Check task{" "}
        <code>{task.task_id}</code> ({pending.length} available).
      </p>
      <QuestionCheckPresentation
        key={task.task_id}
        task={task}
        locked={locked}
        errorMessage={null}
        statusMessage={null}
        showAfterAction={previewResponse?.kind === "question_check"}
        afterActionReplayed={false}
        afterActionRecordedLabel={PREVIEW_LOCAL_STATUS}
        afterActionCorrectLabel={PREVIEW_CORRECT_LABEL}
        afterActionNextLabel={PREVIEW_NEXT_LABEL}
        onCommit={(draft) => {
          void onCommit(draft);
        }}
        onNext={onNext}
        onCorrect={onCorrect}
        nextDisabled={pending.length < 2 && previewResponse !== null}
      />
      {previewResponse?.kind === "question_check" ? (
        <p className="muted" role="status" data-testid="preview-response-summary">
          Local preview decision: {previewResponse.decision}
          {previewResponse.decision === "edit" && previewResponse.effective_query
            ? ` · ${previewResponse.effective_query}`
            : ""}
        </p>
      ) : null}
      {pending.length > 1 ? (
        <div className="row">
          <Button
            variant="secondary"
            onClick={() => {
              interaction.clear();
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
