import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "../../../../components/Button";
import { TextArea, TextInput } from "../../../../components/Field";
import type {
  GoldMutationReceipt,
  QuestionCheckTaskDetail,
} from "../../types";
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

type Props = {
  task: QuestionCheckTaskDetail;
  mutationBusy: boolean;
  ambiguous: boolean;
  /** Terminal reconciliation block; no new mutation or same-intent retry. */
  mutationBlocked?: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  afterAction: GoldMutationReceipt | null;
  onCommit: (body: QuestionCheckCommitDraft) => void;
  onRetrySame: () => void;
  onNext: () => void;
  onCorrect: () => void;
  nextDisabled?: boolean;
};

function tagsFromLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function QuestionCheckGame({
  task,
  mutationBusy,
  ambiguous,
  mutationBlocked = false,
  errorMessage,
  statusMessage,
  afterAction,
  onCommit,
  onRetrySame,
  onNext,
  onCorrect,
  nextDisabled = false,
}: Props) {
  const presentation = task.presentation;
  const [editing, setEditing] = useState(false);
  const [query, setQuery] = useState(presentation.proposed_query);
  const [category, setCategory] = useState(
    presentation.proposed_category ?? "",
  );
  const [tagsText, setTagsText] = useState(
    presentation.proposed_tags.join("\n"),
  );
  const [formError, setFormError] = useState<string | null>(null);

  // Parent remounts with key={task.task_id} so edit/draft state never
  // leaks across Q1→Q2 (I2-R4). Do not sync via effect.

  const locked =
    mutationBusy ||
    ambiguous ||
    mutationBlocked ||
    afterAction !== null;

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
    <div className="stack gold-lab-game">
      <header>
        <h2>Question Check</h2>
      </header>

      <section aria-labelledby="gold-qc-proposal-heading">
        <h3 id="gold-qc-proposal-heading">Proposed question</h3>
        <p>{presentation.proposed_query}</p>
        {presentation.proposed_category ? (
          <p className="muted">Category: {presentation.proposed_category}</p>
        ) : (
          <p className="muted">Category: none</p>
        )}
        {presentation.proposed_tags.length > 0 ? (
          <p className="muted">
            Tags: {presentation.proposed_tags.join(", ")}
          </p>
        ) : (
          <p className="muted">Tags: none</p>
        )}
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

      <div className="row" style={{ flexWrap: "wrap" }}>
        <Button
          disabled={locked}
          onClick={() => onCommit({ decision: "accept" })}
        >
          Accept
        </Button>
        <Button
          variant="secondary"
          disabled={locked}
          onClick={() => seedEdit()}
        >
          Edit
        </Button>
        <Button
          variant="danger"
          disabled={locked}
          onClick={() => onCommit({ decision: "reject" })}
        >
          Reject
        </Button>
      </div>

      {editing && !afterAction ? (
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
        ambiguous={ambiguous && !mutationBlocked}
        onRetrySame={mutationBlocked ? undefined : onRetrySame}
        retryBusy={mutationBusy}
      />

      {afterAction && !mutationBlocked ? (
        <GoldAfterAction
          replayed={afterAction.replayed}
          onNext={onNext}
          onCorrect={() => {
            setEditing(false);
            onCorrect();
          }}
          nextDisabled={nextDisabled}
          correctDisabled={mutationBusy}
        />
      ) : null}
    </div>
  );
}
