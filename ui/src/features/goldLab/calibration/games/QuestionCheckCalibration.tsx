import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "../../../../components/Button";
import { TextArea, TextInput } from "../../../../components/Field";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type {
  BlindQuestionItem,
  LocalQuestionResponse,
  QuestionAuthority,
} from "../types";

type Props = {
  item: BlindQuestionItem;
  authority: QuestionAuthority | undefined;
  committed: boolean;
  onCommit: (response: LocalQuestionResponse) => void;
  onNext: () => void;
  nextLabel?: string;
};

function tagsFromLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function QuestionCheckCalibration({
  item,
  authority,
  committed,
  onCommit,
  onNext,
  nextLabel = "Next",
}: Props) {
  // Parent remounts with key={item.itemId} so draft state never leaks across items.
  const [editing, setEditing] = useState(false);
  const [query, setQuery] = useState(item.proposedQuery);
  const [category, setCategory] = useState(item.proposedCategory ?? "");
  const [tagsText, setTagsText] = useState(item.proposedTags.join("\n"));
  const [formError, setFormError] = useState<string | null>(null);
  const [local, setLocal] = useState<LocalQuestionResponse | null>(null);

  function commit(response: LocalQuestionResponse) {
    setLocal(response);
    onCommit(response);
  }

  function onEditSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setFormError("Edited query must be non-empty.");
      return;
    }
    setFormError(null);
    commit({
      decision: "edit",
      effective_query: trimmed,
      effective_category: category.trim() ? category.trim() : null,
      effective_tags: tagsFromLines(tagsText),
    });
  }

  return (
    <div className="stack gold-lab-game" data-testid="calibration-question-check">
      <header>
        <h2>Question Check calibration</h2>
        <p className="muted">
          Local accept / edit / reject against registration-time QC disposition.
          No Gold mutation.
        </p>
      </header>

      <section aria-labelledby="cal-qc-proposed">
        <h3 id="cal-qc-proposed">Proposed question</h3>
        <p>{item.proposedQuery}</p>
        {item.proposedCategory ? (
          <p className="muted">Category: {item.proposedCategory}</p>
        ) : null}
        {item.proposedTags.length > 0 ? (
          <p className="muted">Tags: {item.proposedTags.join(", ")}</p>
        ) : null}
      </section>

      {item.questionSource ? (
        <GoldSourceContextView
          source={item.questionSource}
          heading="Question source"
        />
      ) : null}

      {!committed && !editing ? (
        <div className="row">
          <Button onClick={() => commit({ decision: "accept" })}>Accept</Button>
          <Button variant="secondary" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button
            variant="danger"
            onClick={() => commit({ decision: "reject" })}
          >
            Reject
          </Button>
        </div>
      ) : null}

      {!committed && editing ? (
        <form className="stack" onSubmit={onEditSubmit}>
          <TextInput
            id="cal-qc-edit-query"
            label="Effective query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <TextInput
            id="cal-qc-edit-category"
            label="Effective category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          />
          <TextArea
            id="cal-qc-edit-tags"
            label="Effective tags (one per line)"
            value={tagsText}
            onChange={(event) => setTagsText(event.target.value)}
          />
          {formError ? (
            <p className="error-box" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="row">
            <Button type="submit">Commit edit</Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditing(false)}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {committed && local && authority ? (
        <section
          className="gold-lab-calibration-reveal"
          aria-live="polite"
          data-testid="calibration-reveal"
        >
          <h3>Reveal</h3>
          <p>Your disposition: {local.decision}</p>
          <p>
            Registration-time disposition: {authority.disposition}
            {local.decision === authority.disposition
              ? " — disposition match"
              : " — disposition mismatch"}
          </p>
          {authority.disposition === "edit" ? (
            <div className="muted">
              <p>Registered effective query: {authority.effectiveQuery}</p>
              <p>
                Registered effective category:{" "}
                {authority.effectiveCategory ?? "—"}
              </p>
              <p>
                Registered effective tags:{" "}
                {authority.effectiveTags.length > 0
                  ? authority.effectiveTags.join(", ")
                  : "—"}
              </p>
            </div>
          ) : null}
          <Button onClick={onNext}>{nextLabel}</Button>
        </section>
      ) : null}
    </div>
  );
}
