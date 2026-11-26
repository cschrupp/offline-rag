import { AnswerMarkdown } from "../../components/AnswerMarkdown";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { apiRequest } from "../../api/client";
import { userFacingErrorMessage } from "../../api/errors";
import { IntentHandle } from "../../api/idempotency";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../components/Button";

type Source = {
  source_id: string;
  source_display_name?: string;
  source_version: number;
  evidence_unit_id: string;
};
type Card = {
  id: string;
  topic: string;
  flashcard_question: string;
  exercise: string;
  citation: Source;
  snapshot_id: string;
  requires_revalidation: boolean;
};
type Outcome = {
  outcome: "revealed" | "matched" | "missed" | "assisted";
  statement?: string;
};
type Review = {
  enabled: boolean;
  cards: Card[];
  aids: {
    id: string;
    title: string;
    text: string;
    origin: string;
    revision: number;
    requires_revalidation: boolean;
    references: { record_id: string; revision: number; provenance: {
      snapshot_id?: string;
      citations?: Source[];
    } }[];
  }[];
  history: { topic: string; label?: string; items: { record_id: string; text: string; historical: boolean; origin: string }[] }[];
  topics: {
    topic: string;
    exposure: number;
    practice: number;
    current_matches: number;
    historical_matches: number;
    needs_revalidation: number;
    recommendation: string;
  }[];
};

const outcomeCopy = {
  revealed: "Source answer revealed. Practice recorded.",
  matched: "Exact match. Recall demonstrated on this exercise.",
  missed: "The answer did not match the missing word. Try again or reveal the source answer.",
  assisted: "Exact match after a reveal. Practice recorded.",
};

function PracticeCard({
  card, root, enabled, selectedSourceIds, onRecorded,
}: {
  card: Card;
  root: string;
  enabled: boolean;
  selectedSourceIds: string[];
  onRecorded: () => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const intent = useRef<IntentHandle | null>(null);
  const canPractice = enabled && !card.requires_revalidation &&
    selectedSourceIds.includes(card.citation.source_id);
  const attempt = useMutation({
    mutationFn: (mode: "check" | "reveal") => {
      const body = {
        mode, source_ids: selectedSourceIds, answer: mode === "check" ? answer.trim() : "",
      };
      const handle = intent.current ?? (intent.current = new IntentHandle());
      return apiRequest<Outcome>(`${root}/cards/${encodeURIComponent(card.id)}/attempts`, {
        method: "POST", idempotencyKey: handle.prepare(JSON.stringify(body)), json: body,
      });
    },
    onSuccess: async () => {
      intent.current = null;
      await onRecorded();
    },
  });
  return (
    <details className="stack">
      <summary>{card.topic}</summary>
      <AnswerMarkdown text={card.flashcard_question} />
      {card.requires_revalidation ? (
        <p><strong>Needs revalidation.</strong> Generate a new card from the current publication.</p>
      ) : !selectedSourceIds.includes(card.citation.source_id) ? (
        <p>Select the linked source to practice.</p>
      ) : null}
      <AnswerMarkdown text={card.exercise} />
      <form className="stack" onSubmit={(event) => {
        event.preventDefault();
        if (canPractice && answer.trim() && !attempt.isPending) attempt.mutate("check");
      }}>
        <label htmlFor={`training-answer-${card.id}`}>Missing word</label>
        <input id={`training-answer-${card.id}`} value={answer} maxLength={160}
          onChange={(event) => setAnswer(event.target.value)} disabled={!canPractice || attempt.isPending} />
        <div className="row">
          <Button type="submit" disabled={!canPractice || !answer.trim() || attempt.isPending}>Check recall</Button>
          <Button type="button" variant="secondary" disabled={!canPractice || attempt.isPending}
            onClick={() => attempt.mutate("reveal")}>Reveal source answer</Button>
        </div>
      </form>
      {attempt.isError ? <p className="error-box" role="alert">{userFacingErrorMessage(attempt.error)}</p> : null}
      {canPractice && attempt.data ? (
        <div role="status">
          <p>{outcomeCopy[attempt.data.outcome]}</p>
          {attempt.data.statement ? <AnswerMarkdown text={attempt.data.statement} /> : null}
        </div>
      ) : null}
      <details>
        <summary>Source provenance</summary>
        <p>{card.citation.source_display_name || card.citation.source_id} · Version {card.citation.source_version}</p>
        <p>Publication <code>{card.snapshot_id}</code></p>
        <p>Evidence <code>{card.citation.evidence_unit_id}</code></p>
      </details>
    </details>
  );
}

export function MemoryReviewPanel({
  workspaceId, snapshotId, sourceIds,
}: {
  workspaceId: string;
  snapshotId: string | null;
  sourceIds: string[];
}) {
  const root = `/v1/workspaces/${encodeURIComponent(workspaceId)}/knowledge/training`;
  const client = useQueryClient();
  const prefix = queryKeys.workspaceKnowledge(workspaceId);
  const trainingKey = [...prefix, "training"];
  const [search, setSearch] = useState("");
  const [topic, setTopic] = useState("");
  const [cardTopic, setCardTopic] = useState("");
  const intent = useRef<IntentHandle | null>(null);
  const query = useQuery({
    queryKey: [...trainingKey, snapshotId, topic],
    queryFn: ({ signal }) => apiRequest<Review>(`${root}?topic=${encodeURIComponent(topic)}`, { signal }),
    retry: false,
  });
  const create = useMutation({
    mutationFn: (text: string) => {
      const body = { topic: text, source_ids: sourceIds };
      const handle = intent.current ?? (intent.current = new IntentHandle());
      return apiRequest<void>(`${root}/cards`, {
        method: "POST", idempotencyKey: handle.prepare(JSON.stringify(body)), json: body,
      });
    },
    onSuccess: async () => {
      intent.current = null;
      setSearch(cardTopic.trim());
      setTopic(cardTopic.trim());
      await client.invalidateQueries({ queryKey: prefix });
    },
  });

  function searchTopics(event: FormEvent) {
    event.preventDefault();
    setTopic(search.trim());
  }

  return (
    <section className="stack workspace-knowledge training-memory-review" aria-label="Training memory review">
      <h2>Memory review</h2>
      {query.isPending ? <p role="status">Loading memory review…</p> : null}
      {query.isError ? <p className="error-box" role="alert">{userFacingErrorMessage(query.error)}</p> : null}
      {query.data ? (
        <>
          {!query.data.enabled ? <p>Memory is paused or disabled. Enable it in Knowledge to create materials and record practice.</p> : null}
          <form className="row" onSubmit={searchTopics}>
            <label htmlFor="training-memory-topic">Review topic</label>
            <input id="training-memory-topic" maxLength={256} value={search} onChange={(event) => setSearch(event.target.value)} />
            <Button variant="secondary" type="submit">Find review material</Button>
          </form>
          {query.data.enabled ? (
            <form className="stack" onSubmit={(event) => {
              event.preventDefault();
              if (cardTopic.trim() && sourceIds.length && !create.isPending) create.mutate(cardTopic.trim());
            }}>
              <label htmlFor="training-card-topic">New card topic</label>
              <input id="training-card-topic" maxLength={160} value={cardTopic}
                onChange={(event) => setCardTopic(event.target.value)} disabled={create.isPending} />
              <div><Button type="submit" disabled={!cardTopic.trim() || !sourceIds.length || create.isPending}>
                {create.isPending ? "Reading selected sources…" : "Create flashcard and recall exercise"}
              </Button></div>
              <p className="muted">Create a card from the current selection using the configured generator.</p>
              {create.isError ? <p className="error-box" role="alert">{userFacingErrorMessage(create.error)}</p> : null}
            </form>
          ) : null}

          <h3>Review recommendations</h3>
          <p className="muted">These counts describe recent saved activity. A match records an exact answer before a retained reveal on that exercise.</p>
          {query.data.topics.length ? (
            <ul>{query.data.topics.map((item, index) => (
              <li key={index}>
                <strong>{item.topic}</strong> · Exposure {item.exposure} · Practice {item.practice}
                {" · "}Current recall matches {item.current_matches}
                {item.historical_matches ? ` · Historical matches ${item.historical_matches}` : ""}
                <p>{item.recommendation}</p>
              </li>
            ))}</ul>
          ) : <p>No saved activity matches this topic.</p>}

          <h3>Flashcards and recall exercises</h3>
          {query.data.cards.length ? query.data.cards.map((card) => (
            <PracticeCard card={card} root={root} enabled={query.data.enabled} selectedSourceIds={sourceIds}
              key={`${card.id}:${snapshotId ?? ""}`}
              onRecorded={async () => { await client.invalidateQueries({ queryKey: prefix }); }} />
          )) : <p>No saved cards match this topic.</p>}

          <h3>Saved mnemonics and study aids</h3>
          {query.data.aids.length ? query.data.aids.map((aid) => (
            <details key={aid.id}>
              <summary>{aid.title} · Revision {aid.revision}</summary>
              {aid.requires_revalidation ? <p><strong>Needs revalidation.</strong> This aid uses a prior publication.</p> : null}
              <p className="workspace-knowledge-text">{aid.text}</p>
              {aid.references.map((item) => (
                <div key={item.record_id}>
                  <p>Related record revision {item.revision} · {item.provenance.snapshot_id ?? "Learner reference"}</p>
                  <ul>{item.provenance.citations?.map((citation, index) => (
                    <li key={index}>{citation.source_display_name || citation.source_id} · Version {citation.source_version}</li>
                  ))}</ul>
                </div>
              ))}
            </details>
          )) : <p>No saved aids match this topic.</p>}
          <h3>Topic history</h3>
          {query.data.history.length ? query.data.history.map((entry) => (
            <details key={entry.topic}>
              <summary>{entry.label ?? entry.topic}</summary>
              <ul>{entry.items.map((item) => <li key={item.record_id}>{item.text} {item.historical ? "(Prior publication)" : ""} {item.origin === "user_provided" ? "(Learner correction)" : ""}</li>)}</ul>
            </details>
          )) : <p>No grouped discussions match this topic.</p>}
        </>
      ) : null}
    </section>
  );
}
