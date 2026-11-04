import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Check, ClipboardCheck, Pencil, X } from "lucide-react";
import { Button } from "../../../../components/Button";
import { TextArea, TextInput } from "../../../../components/Field";
import type { QuestionCheckTaskDetail } from "../../types";
import { GoldAfterAction } from "../common/GoldAfterAction";
import { GoldMutationStatus } from "../common/GoldMutationStatus";
import { GoldSourceContextView } from "../common/GoldSourceContext";

export type QuestionCheckCommitDraft =
  | { decision: "accept" }
  | { decision: "reject" }
  | {
      decision: "edit";
      effective_query: string;
      effective_category: string | null;
      effective_tags: string[];
    };

export type QuestionCheckPresentationProps = {
  task: QuestionCheckTaskDetail;
  locked: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  ambiguous?: boolean;
  showRetry?: boolean;
  showAfterAction: boolean;
  afterActionReplayed?: boolean;
  onCommit: (body: QuestionCheckCommitDraft) => void;
  onRetrySame?: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
  correctDisabled?: boolean;
  retryBusy?: boolean;
  /** Injected after-action copy; production keeps GoldAfterAction defaults. */
  afterActionRecordedLabel?: string;
  afterActionCorrectLabel?: string;
  afterActionNextLabel?: string;
  /** Notifies parent when an unsubmitted edit form is open. */
  onEditingChange?: (editing: boolean) => void;
};

function tagsFromLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Shared Question Check presentation (production + Presentation Review).
 * Mutation authority is owned by the parent via onCommit / after-action props.
 */
export function QuestionCheckPresentation({
  task,
  locked,
  errorMessage,
  statusMessage,
  ambiguous = false,
  showRetry = false,
  showAfterAction,
  afterActionReplayed = false,
  onCommit,
  onRetrySame,
  onNext,
  onCorrect,
  nextDisabled = false,
  correctDisabled = false,
  retryBusy = false,
  afterActionRecordedLabel,
  afterActionCorrectLabel,
  afterActionNextLabel,
  onEditingChange,
}: QuestionCheckPresentationProps) {
  const presentation = task.presentation;
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    onEditingChange?.(editing && !showAfterAction);
  }, [editing, showAfterAction, onEditingChange]);
  const [query, setQuery] = useState(presentation.proposed_query);
  const [category, setCategory] = useState(
    presentation.proposed_category ?? "",
  );
  const [tagsText, setTagsText] = useState(
    presentation.proposed_tags.join("\n"),
  );
  const [formError, setFormError] = useState<string | null>(null);

  function seedEdit() {
    setQuery(presentation.proposed_query);
    setCategory(presentation.proposed_category ?? "");
    setTagsText(presentation.proposed_tags.join("\n"));
    setFormError(null);
    setEditing(true);
  }

  function onEditSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setFormError("Edited query must be non-empty.");
      return;
    }
    const tags = tagsFromLines(tagsText);
    const categoryValue = category.trim() ? category.trim() : null;
    if (
      trimmed === presentation.proposed_query &&
      categoryValue === (presentation.proposed_category ?? null) &&
      JSON.stringify(tags) === JSON.stringify(presentation.proposed_tags)
    ) {
      setFormError(
        "Edit must change the proposed question content, or use Accept.",
      );
      return;
    }
    setFormError(null);
    onCommit({
      decision: "edit",
      effective_query: trimmed,
      effective_category: categoryValue,
      effective_tags: tags,
    });
  }

  return (
    <div className="stack gold-lab-game" data-testid="question-check-presentation">
      <header className="gold-game-heading question-check-heading">
        <span className="gold-game-heading-icon" aria-hidden="true">
          <ClipboardCheck size={22} />
        </span>
        <div>
          <p className="quick-play-eyebrow">QUESTION REVIEW</p>
          <h2>Question Check</h2>
        </div>
      </header>

      <section
        className="question-check-question"
        aria-labelledby="gold-qc-proposal-heading"
      >
        <h3 id="gold-qc-proposal-heading">Proposed question</h3>
        <p className="question-check-question-text">{presentation.proposed_query}</p>
        <div className="question-check-tags">
          <span>{presentation.proposed_category ?? "Uncategorized"}</span>
          {presentation.proposed_tags.map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      </section>

      {presentation.source ? (
        <GoldSourceContextView source={presentation.source} />
      ) : (
        <p className="muted" role="status">
          No source seed is available for this question.
        </p>
      )}

      {task.current_result ? (
        <p className="muted" role="status">
          Current recorded decision: {task.current_result.decision}
          {task.current_result.effective_query
            ? ` · ${task.current_result.effective_query}`
            : ""}
        </p>
      ) : null}

      <div className="row question-check-actions">
        <Button
          disabled={locked}
          onClick={() => onCommit({ decision: "accept" })}
        >
          <Check size={17} aria-hidden="true" />
          Accept
        </Button>
        <Button
          variant="secondary"
          disabled={locked}
          onClick={() => seedEdit()}
        >
          <Pencil size={16} aria-hidden="true" />
          Edit
        </Button>
        <Button
          variant="danger"
          disabled={locked}
          onClick={() => onCommit({ decision: "reject" })}
        >
          <X size={17} aria-hidden="true" />
          Reject
        </Button>
      </div>

      {editing && !showAfterAction ? (
        <form className="stack" onSubmit={onEditSubmit}>
          <h3>Edit proposed question</h3>
          <TextInput
            id="gold-qc-edit-query"
            label="Effective query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            disabled={locked}
          />
          <TextInput
            id="gold-qc-edit-category"
            label="Effective category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            hint="Leave blank to submit null."
            disabled={locked}
          />
          <TextArea
            id="gold-qc-edit-tags"
            label="Effective tags"
            value={tagsText}
            onChange={(event) => setTagsText(event.target.value)}
            hint="One tag per line."
            disabled={locked}
          />
          {formError ? (
            <p className="error-box" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="row">
            <Button type="submit" disabled={locked}>
              Submit edit
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={locked}
              onClick={() => setEditing(false)}
            >
              Cancel edit
            </Button>
          </div>
        </form>
      ) : null}

      <GoldMutationStatus
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        ambiguous={ambiguous && showRetry}
        onRetrySame={showRetry ? onRetrySame : undefined}
        retryBusy={retryBusy}
      />

      {showAfterAction ? (
        <GoldAfterAction
          replayed={afterActionReplayed}
          onNext={onNext}
          onCorrect={() => {
            setEditing(false);
            onCorrect();
          }}
          nextDisabled={nextDisabled}
          correctDisabled={correctDisabled}
          recordedLabel={afterActionRecordedLabel}
          correctLabel={afterActionCorrectLabel}
          nextLabel={afterActionNextLabel}
        />
      ) : null}
    </div>
  );
}
