import type { FormEvent, KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import type { WorkspaceCitation } from "../../api/types";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Field";
import { ClaimAnswer } from "./ClaimAnswer";
import { abstentionCopy } from "./abstentionCopy";
import { snapshotBadge, type AskHistoryEntry } from "./askHistory";

type Props = {
  question: string;
  onQuestionChange: (value: string) => void;
  onAsk: () => void;
  askDisabled: boolean;
  askPending: boolean;
  selectedCount: number;
  totalCount: number;
  askError: string | null;
  conflictHint: string | null;
  activeEntry: AskHistoryEntry | null;
  history: AskHistoryEntry[];
  selectedEvidenceUnitId: string | null;
  onSelectCitation: (citation: WorkspaceCitation) => void;
  onSelectHistory: (entry: AskHistoryEntry) => void;
  currentSnapshotId: string | null;
  settingsHint?: boolean;
};

function statusLabel(status: string): string {
  switch (status) {
    case "answered":
      return "Answered";
    case "insufficient_evidence":
      return "Not enough evidence";
    case "model_abstain":
      return "Abstained";
    default:
      return status;
  }
}

export function AskPanel({
  question,
  onQuestionChange,
  onAsk,
  askDisabled,
  askPending,
  selectedCount,
  totalCount,
  askError,
  conflictHint,
  activeEntry,
  history,
  selectedEvidenceUnitId,
  onSelectCitation,
  onSelectHistory,
  currentSnapshotId,
  settingsHint,
}: Props) {
  function onSubmit(event: FormEvent) {
    event.preventDefault();
    onAsk();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (!askDisabled && !askPending) onAsk();
    }
  }

  const badge =
    activeEntry != null
      ? snapshotBadge(activeEntry.response.snapshot_id, currentSnapshotId)
      : null;

  return (
    <section className="ask-panel stack" aria-labelledby="ask-heading">
      <h2 id="ask-heading">Ask your sources</h2>
      <form className="stack" onSubmit={onSubmit}>
        <TextArea
          id="ask-question"
          label="Question"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={4}
          disabled={askPending}
        />
        <p className="muted" style={{ margin: 0 }} aria-live="polite">
          Using {selectedCount} of {totalCount} sources
        </p>
        <p className="muted" style={{ margin: 0, fontSize: "0.875rem" }}>
          Each question is answered independently.
        </p>
        <div className="row">
          <Button type="submit" disabled={askDisabled || askPending}>
            Ask
          </Button>
        </div>
      </form>

      {askPending ? (
        <p className="muted" aria-live="polite" role="status">
          Searching your selected sources…
        </p>
      ) : null}

      {conflictHint ? (
        <p className="error-box" role="alert">
          {conflictHint}
        </p>
      ) : null}

      {askError ? (
        <p className="error-box" role="alert">
          {askError}
          {settingsHint ? (
            <>
              {" "}
              <Link to="/settings">Open Settings</Link>
            </>
          ) : null}
        </p>
      ) : null}

      {activeEntry ? (
        <article className="answer-card stack" aria-labelledby="answer-heading">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 id="answer-heading" style={{ margin: 0 }}>
              Answer
            </h3>
            <span
              className={
                badge === "current"
                  ? "snapshot-badge snapshot-badge-current"
                  : "snapshot-badge snapshot-badge-historical"
              }
            >
              {badge === "current" ? "Current snapshot" : "Historical snapshot"}
            </span>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Asked from {activeEntry.selectedSourceIds.length} source
            {activeEntry.selectedSourceIds.length === 1 ? "" : "s"}
            {activeEntry.selectedSourceNames.length
              ? `: ${activeEntry.selectedSourceNames.join(", ")}`
              : ""}
          </p>
          {activeEntry.response.status === "answered" ? (
            <div className="answer-body">
              <ClaimAnswer
                blocks={activeEntry.response.answer_blocks}
                citations={activeEntry.response.citations}
                selectedEvidenceUnitId={selectedEvidenceUnitId}
                onSelectCitation={onSelectCitation}
              />
            </div>
          ) : null}
          {activeEntry.response.status === "insufficient_evidence" ||
          activeEntry.response.status === "model_abstain" ? (
            <p className="abstention-callout" role="status">
              {abstentionCopy(activeEntry.response.abstention_reason)}
            </p>
          ) : null}
        </article>
      ) : null}

      {history.length > 0 ? (
        <div className="stack ask-history">
          <h3>Recent questions</h3>
          <ul className="ask-history-list">
            {history.map((entry) => {
              const entryBadge = snapshotBadge(
                entry.response.snapshot_id,
                currentSnapshotId,
              );
              const active = activeEntry?.entryId === entry.entryId;
              return (
                <li key={entry.entryId}>
                  <button
                    type="button"
                    className={
                      active
                        ? "ask-history-item ask-history-item-active"
                        : "ask-history-item"
                    }
                    aria-pressed={active}
                    onClick={() => onSelectHistory(entry)}
                  >
                    <span className="ask-history-question">{entry.question}</span>
                    <span className="muted">
                      {statusLabel(String(entry.response.status))} ·{" "}
                      {entryBadge === "current"
                        ? "Current snapshot"
                        : "Historical snapshot"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
