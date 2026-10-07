import { useEffect, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import type { WorkspaceCitation } from "../../api/types";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Field";
import { ClaimAnswer } from "./ClaimAnswer";
import { assistantPresentationText } from "./assistantPresentation";
import {
  buildConversationTimeline,
  snapshotBadge,
  sourceScopeLabel,
  type ConversationHistoryEntry,
  type IncompleteUserTurn,
} from "./conversationState";

type Props = {
  question: string;
  onQuestionChange: (value: string) => void;
  onAsk: () => void;
  onNewConversation: () => void;
  askDisabled: boolean;
  askPending: boolean;
  selectedCount: number;
  totalCount: number;
  askError: string | null;
  conflictHint: string | null;
  activeEntry: ConversationHistoryEntry | null;
  history: ConversationHistoryEntry[];
  incompleteTurns: IncompleteUserTurn[];
  selectedEvidenceUnitId: string | null;
  onSelectCitation: (
    citation: WorkspaceCitation,
    entry: ConversationHistoryEntry,
  ) => void;
  onSelectHistory: (entry: ConversationHistoryEntry) => void;
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
    case "clarification_required":
      return "Clarification needed";
    default:
      return status;
  }
}

export function AskPanel({
  question,
  onQuestionChange,
  onAsk,
  onNewConversation,
  askDisabled,
  askPending,
  selectedCount,
  totalCount,
  askError,
  conflictHint,
  activeEntry,
  history,
  incompleteTurns,
  selectedEvidenceUnitId,
  onSelectCitation,
  onSelectHistory,
  currentSnapshotId,
  settingsHint,
}: Props) {
  useEffect(() => {
    if (askPending) return;
    const el = document.getElementById("ask-question");
    if (el instanceof HTMLTextAreaElement) {
      el.focus();
    }
  }, [askPending, history.length, incompleteTurns.length]);

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

  const timeline = buildConversationTimeline(history, incompleteTurns);
  const hasThread = timeline.length > 0;

  return (
    <section className="ask-panel conversation-panel" aria-labelledby="ask-heading">
      <div className="row conversation-panel-header">
        <h2 id="ask-heading" style={{ margin: 0 }}>
          Conversation
        </h2>
        <Button
          type="button"
          variant="secondary"
          onClick={onNewConversation}
          disabled={askPending || !hasThread}
        >
          + New conversation
        </Button>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Using {selectedCount} of {totalCount} sources. Follow-ups use conversation
        context for wording only — answers still come from selected sources.
      </p>

      <div className="conversation-thread stack" aria-live="polite">
        {!hasThread ? (
          <p className="muted" style={{ margin: 0 }}>
            Ask a question about your selected sources.
          </p>
        ) : null}

        {timeline.map((item) => {
          if (item.kind === "incomplete") {
            const turn = item.turn;
            return (
              <article
                key={turn.pairId}
                className="conversation-turn stack"
                aria-busy={turn.status === "pending"}
              >
                <div className="conversation-user-turn">
                  <p className="conversation-role">You</p>
                  <p className="conversation-user-text">{turn.question}</p>
                </div>
                <div className="conversation-assistant-turn">
                  <p className="conversation-role">Seneca</p>
                  {turn.status === "pending" ? (
                    <p className="muted" role="status">
                      Searching your selected sources…
                    </p>
                  ) : (
                    <p className="error-box" role="alert">
                      {turn.errorMessage ??
                        "This turn did not complete. Your question is still shown above."}
                    </p>
                  )}
                </div>
              </article>
            );
          }

          const entry = item.entry;
          const badge = snapshotBadge(
            entry.response.snapshot_id,
            currentSnapshotId,
          );
          const active = activeEntry?.entryId === entry.entryId;
          const assistantText = assistantPresentationText(entry.response);
          return (
            <article
              key={entry.entryId}
              className={
                active
                  ? "conversation-turn stack conversation-turn-active"
                  : "conversation-turn stack"
              }
            >
              <div className="conversation-user-turn">
                <p className="conversation-role">You</p>
                <p className="conversation-user-text">{entry.question}</p>
              </div>
              <div className="conversation-assistant-turn stack">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <p className="conversation-role" style={{ margin: 0 }}>
                    Seneca
                  </p>
                  <button
                    type="button"
                    className={
                      badge === "current"
                        ? "snapshot-badge snapshot-badge-current"
                        : "snapshot-badge snapshot-badge-historical"
                    }
                    onClick={() => onSelectHistory(entry)}
                    aria-pressed={active}
                  >
                    {badge === "current"
                      ? "Current snapshot"
                      : "Historical snapshot"}
                  </button>
                </div>
                <p className="muted" style={{ margin: 0, fontSize: "0.875rem" }}>
                  {statusLabel(String(entry.response.status))} ·{" "}
                  {sourceScopeLabel(entry)}
                </p>
                {entry.response.status === "answered" ? (
                  <div className="answer-body">
                    <ClaimAnswer
                      blocks={entry.response.answer_blocks}
                      citations={entry.response.citations}
                      selectedEvidenceUnitId={
                        active ? selectedEvidenceUnitId : null
                      }
                      onSelectCitation={(citation) => {
                        onSelectCitation(citation, entry);
                      }}
                    />
                  </div>
                ) : (
                  <p className="abstention-callout" role="status">
                    {assistantText}
                  </p>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <form className="stack conversation-composer" onSubmit={onSubmit}>
        <TextArea
          id="ask-question"
          label="Ask a follow-up"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          disabled={askPending}
        />
        <div className="row">
          <Button type="submit" disabled={askDisabled || askPending}>
            Send
          </Button>
        </div>
      </form>

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
    </section>
  );
}
