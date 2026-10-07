import { useEffect, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import type { WorkspaceCitation } from "../../api/types";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Field";
import { ClaimAnswer } from "./ClaimAnswer";
import { abstentionCopy } from "./abstentionCopy";
import {
  snapshotBadge,
  type ConversationHistoryEntry,
} from "./conversationState";

type PendingUserTurn = {
  pairId: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
};

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
  pendingUser: PendingUserTurn | null;
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
  pendingUser,
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
  }, [askPending, history.length]);

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

  // Chronological display: oldest first.
  const chronological = [...history].reverse();

  return (
    <section className="ask-panel conversation-panel stack" aria-labelledby="ask-heading">
      <div className="row conversation-panel-header">
        <h2 id="ask-heading" style={{ margin: 0 }}>
          Conversation
        </h2>
        <Button
          type="button"
          variant="secondary"
          onClick={onNewConversation}
          disabled={askPending || (history.length === 0 && !pendingUser)}
        >
          + New conversation
        </Button>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Using {selectedCount} of {totalCount} sources. Follow-ups use conversation
        context for wording only — answers still come from selected sources.
      </p>

      <div className="conversation-thread stack" aria-live="polite">
        {chronological.length === 0 && !pendingUser ? (
          <p className="muted" style={{ margin: 0 }}>
            Ask a question about your selected sources.
          </p>
        ) : null}

        {chronological.map((entry) => {
          const badge = snapshotBadge(
            entry.response.snapshot_id,
            currentSnapshotId,
          );
          const active = activeEntry?.entryId === entry.entryId;
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
                  {statusLabel(String(entry.response.status))} · Asked from{" "}
                  {entry.selectedSourceIds.length} source
                  {entry.selectedSourceIds.length === 1 ? "" : "s"}
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
                ) : null}
                {entry.response.status === "insufficient_evidence" ||
                entry.response.status === "model_abstain" ||
                entry.response.status === "clarification_required" ? (
                  <p className="abstention-callout" role="status">
                    {abstentionCopy(entry.response.abstention_reason)}
                  </p>
                ) : null}
              </div>
            </article>
          );
        })}

        {pendingUser ? (
          <article className="conversation-turn stack" aria-busy="true">
            <div className="conversation-user-turn">
              <p className="conversation-role">You</p>
              <p className="conversation-user-text">{pendingUser.question}</p>
            </div>
            <div className="conversation-assistant-turn">
              <p className="conversation-role">Seneca</p>
              <p className="muted" role="status">
                Searching your selected sources…
              </p>
            </div>
          </article>
        ) : null}
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
