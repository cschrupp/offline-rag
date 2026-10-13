import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
import {
  createPreviewInteraction,
  type PreviewResponseMap,
} from "./PreviewInteraction";
import { isPreviewableTaskDetail } from "./previewEligibility";
import {
  PREVIEW_CORRECT_LABEL,
  PREVIEW_LOCAL_STATUS,
  PREVIEW_NEXT_LABEL,
} from "./previewTypes";

type Props = {
  campaignId: string;
};

export function QuestionCheckPreviewSession({ campaignId }: Props) {
  const [responses, setResponses] = useState<PreviewResponseMap>({});
  const [cursor, setCursor] = useState(0);
  const [runIds, setRunIds] = useState<string[] | null>(null);
  const [complete, setComplete] = useState(false);

  const interaction = useMemo(
    () =>
      createPreviewInteraction({
        getMap: () => responses,
        setMap: setResponses,
      }),
    [responses],
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

  useEffect(() => {
    if (!tasksQuery.isSuccess || runIds !== null) return;
    if (pending.length === 0) return;
    setRunIds(pending.map((t) => t.task_id));
  }, [tasksQuery.isSuccess, pending, runIds]);

  const snapshotIds = runIds ?? [];
  const activeTaskId =
    !complete && snapshotIds.length > 0
      ? (snapshotIds[Math.min(cursor, snapshotIds.length - 1)] ?? null)
      : null;

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
    if (cursor >= snapshotIds.length - 1) {
      setComplete(true);
      return;
    }
    setCursor((c) => c + 1);
  }

  function onPrevious() {
    if (cursor <= 0) return;
    setComplete(false);
    setCursor((c) => c - 1);
  }

  function onCorrect() {
    if (!activeTaskId) return;
    interaction.clearTask(activeTaskId);
  }

  function restartPreview() {
    interaction.clearAll();
    setComplete(false);
    setCursor(0);
    setRunIds(pending.map((t) => t.task_id));
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
  if (tasksQuery.isSuccess && pending.length === 0 && snapshotIds.length === 0) {
    return (
      <p className="muted" role="status" data-testid="qc-preview-empty">
        No pending active Question Check tasks are available for preview in this
        campaign.
      </p>
    );
  }

  if (complete) {
    return (
      <div className="stack" data-testid="qc-preview-complete">
        <h3>End of available preview tasks</h3>
        <p className="muted" role="status">
          You reviewed {snapshotIds.length} of {snapshotIds.length} presentations
          in this preview session.
        </p>
        <div className="row">
          <Button to={`/gold-lab/campaigns/${campaignId}`} variant="secondary">
            Return to campaign
          </Button>
          <Button onClick={restartPreview}>Restart preview</Button>
        </div>
      </div>
    );
  }

  if (runIds === null) {
    return <p className="muted">Preparing preview session…</p>;
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

  const previewResponse = interaction.getResponse(task.task_id);
  const locked = previewResponse !== null;
  const atFirst = cursor === 0;

  return (
    <div className="stack" data-testid="qc-preview-session">
      <p className="muted" role="status">
        Previewing Question Check {cursor + 1} of {snapshotIds.length}{" "}
        <code>{task.task_id}</code>.
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
        nextDisabled={false}
      />
      {previewResponse?.kind === "question_check" ? (
        <p className="muted" role="status" data-testid="preview-response-summary">
          Local preview decision: {previewResponse.decision}
          {previewResponse.decision === "edit" && previewResponse.effective_query
            ? ` · ${previewResponse.effective_query}`
            : ""}
        </p>
      ) : null}
      <div className="row">
        <Button
          variant="secondary"
          onClick={onPrevious}
          disabled={atFirst}
          aria-disabled={atFirst}
        >
          Previous preview task
        </Button>
        <Link to={`/gold-lab/campaigns/${campaignId}`}>Return to campaign</Link>
      </div>
    </div>
  );
}
