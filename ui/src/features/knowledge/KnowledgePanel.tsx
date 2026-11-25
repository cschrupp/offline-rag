import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiRequest } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { userFacingErrorMessage } from "../../api/errors";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Field";

type Revision = { revision: number; text: string; origin: string; corrected_at: string };
type Citation = {
  source_id: string;
  source_version: number;
  document_id: string;
  source_chunk_id: string;
  evidence_unit_id: string;
};
type Record = {
  id: string;
  category: "episode" | "semantic" | "learning" | "derived";
  origin: string;
  topic: string;
  text: string;
  revision: number;
  created_at: string;
  parent_id: string | null;
  relation: string | null;
  history: Revision[];
  provenance: { parent_revision?: number; snapshot_id?: string; workspace_revision?: number; citations?: Citation[] };
};
type Recall = {
  enabled: boolean;
  records: Record[];
  summaries: {
    topic: string;
    category: "derived";
    origin: "generated";
    items: { record_id: string; text: string; origin: string }[];
  }[];
};
type Change =
  | { kind: "settings"; enabled: boolean }
  | { kind: "note"; id: string; text: string }
  | { kind: "change"; id: string; revision: number; text: string | null };
type Editor = { kind: "note" | "correct" | "forget"; record: Record };

const categoryLabel = {
  episode: "Discussion",
  semantic: "Concept",
  learning: "Learning note",
  derived: "Study excerpt",
};
const originLabel: { [origin: string]: string } = {
  user_provided: "Learner",
  source_grounded: "From a cited discussion",
  generated: "Generated",
};

export function KnowledgePanel({
  workspaceId,
  snapshotId,
}: {
  workspaceId: string;
  snapshotId: string | null;
}) {
  const root = `/v1/workspaces/${encodeURIComponent(workspaceId)}/knowledge`;
  const client = useQueryClient();
  const queryKey = queryKeys.workspaceKnowledge(workspaceId);
  const [searchDraft, setSearchDraft] = useState("");
  const [topic, setTopic] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [draft, setDraft] = useState("");
  const recall = useQuery({
    queryKey: [...queryKey, topic],
    queryFn: ({ signal }) => apiRequest<Recall>(`${root}?topic=${encodeURIComponent(topic)}`, { signal }),
    retry: false,
  });
  const change = useMutation({
    mutationFn: (input: Change) => {
      switch (input.kind) {
        case "settings":
          return apiRequest<void>(`${root}/settings`, {
            method: "PUT", json: { enabled: input.enabled },
          });
        case "note":
          return apiRequest<void>(`${root}/notes`, {
            method: "POST", json: { parent_id: input.id, text: input.text },
          });
        case "change":
          return apiRequest<void>(`${root}/records/${encodeURIComponent(input.id)}`, {
            method: "PATCH", json: { revision: input.revision, text: input.text },
          });
      }
    },
    onSuccess: async () => {
      setEditor(null);
      setDraft("");
      await client.invalidateQueries({ queryKey });
    },
  });
  function openEditor(kind: Editor["kind"], record: Record) {
    change.reset();
    setEditor({ kind, record });
    setDraft(kind === "correct" ? record.text : "");
  }
  function submitEdit(event: FormEvent) {
    event.preventDefault();
    if (!editor || change.isPending) return;
    const { kind, record } = editor;
    if (kind !== "forget" && !draft.trim()) return;
    if (kind === "note") {
      change.mutate({ kind, id: record.id, text: draft });
    } else {
      change.mutate({
        kind: "change", id: record.id, revision: record.revision,
        text: kind === "forget" ? null : draft,
      });
    }
  }

  return (
    <section className="stack workspace-knowledge" aria-label="Workspace knowledge">
      <h2>Knowledge</h2>
      {recall.isPending ? <p role="status">Loading workspace knowledge…</p> : null}
      {recall.isError ? (
        <>
          <p className="error-box" role="alert">Workspace knowledge could not be loaded.</p>
          <Button variant="secondary" onClick={() => void recall.refetch()}>Try again</Button>
        </>
      ) : null}
      {change.isError ? (
        <p className="error-box" role="alert">{userFacingErrorMessage(change.error)}</p>
      ) : null}
      {recall.data ? (
        <>
          <p className="muted">
            {recall.data.enabled
              ? "Seneca saves cited discussions in this workspace. Use the Evidence tab to check current sources."
              : "Enable memory to save future cited discussions locally in this workspace."}
          </p>
          <Button variant="secondary" disabled={change.isPending}
            onClick={() => change.mutate({ kind: "settings", enabled: !recall.data.enabled })}>
            {recall.data.enabled ? "Pause memory" : "Enable memory"}
          </Button>
          <form className="stack" onSubmit={(event) => {
            event.preventDefault();
            setTopic(searchDraft.trim());
          }}>
            <label htmlFor="workspace-knowledge-search">Find a topic</label>
            <input id="workspace-knowledge-search" value={searchDraft} maxLength={256}
              onChange={(event) => setSearchDraft(event.target.value)} />
            <Button variant="secondary" type="submit">Find</Button>
          </form>
          {recall.data.records.length === 0 ? <p>No matching knowledge yet.</p> : null}
          {recall.data.summaries.map((summary) => (
            <details key={summary.topic}>
              <summary>Topic summary · {summary.topic}</summary>
              <p className="muted">Excerpts from related discussions</p>
              <ul>{summary.items.map((item) => (
                <li key={item.record_id}>
                  <a href={`#memory-${item.record_id}`}>{item.text}</a>{" "}
                  <small>{originLabel[item.origin] ?? item.origin}</small>
                </li>
              ))}</ul>
            </details>
          ))}
          {recall.data.records.map((record) => (
            <details id={`memory-${record.id}`} key={record.id}>
              <summary>{categoryLabel[record.category]} · {record.topic}</summary>
              <p className="muted">{originLabel[record.origin] ?? record.origin} · Revision {record.revision}</p>
              <p className="workspace-knowledge-text">{record.text}</p>
              {record.parent_id ? (
                <p>{record.relation === "note_on" ? "Note on" : record.relation === "excerpt_of" ? "Excerpt from" : "Discussed in"}{" "}
                  {recall.data.records.some((candidate) => candidate.id === record.parent_id) ? (
                    <a href={`#memory-${record.parent_id}`}>related item</a>
                  ) : <code>{record.parent_id}</code>}
                  {record.provenance.parent_revision ? ` · Revision ${record.provenance.parent_revision}` : ""}
                </p>
              ) : null}
              {record.provenance.snapshot_id ? (
                <details>
                  <summary>{record.revision > 1 ? "Original source provenance" : "Source provenance"}</summary>
                  <p>Workspace revision {record.provenance.workspace_revision}</p>
                  <p>{record.provenance.snapshot_id === snapshotId ? "Current publication" : "Historical publication"}</p>
                  <p><code>{record.provenance.snapshot_id}</code></p>
                  <ul>{record.provenance.citations?.map((citation, index) => (
                    <li key={index}>{citation.source_id} · Version {citation.source_version} · {citation.evidence_unit_id}</li>
                  ))}</ul>
                </details>
              ) : null}
              {record.history.length > 0 ? (
                <details>
                  <summary>Revision history</summary>
                  {record.history.map((old) => (
                    <p className="workspace-knowledge-text" key={old.revision}>
                      Revision {old.revision} · {originLabel[old.origin] ?? old.origin}<br />{old.text}
                    </p>
                  ))}
                </details>
              ) : null}
              <div className="row">
                {recall.data.enabled && record.category !== "learning" ? <Button variant="secondary" disabled={change.isPending} onClick={() => openEditor("note", record)}>Add note</Button> : null}
                <Button variant="secondary" disabled={change.isPending} onClick={() => openEditor("correct", record)}>Correct</Button>
                <Button variant="secondary" disabled={change.isPending} onClick={() => openEditor("forget", record)}>Forget</Button>
              </div>
              {editor?.record.id === record.id ? (
                <form className="stack" onSubmit={submitEdit}>
                  {editor.kind === "forget" ? (
                    <p>Remove this item, its revision history and any notes or concepts attached to it?</p>
                  ) : (
                    <TextArea id="workspace-knowledge-editor" label={editor.kind === "note" ? "Learning note" : "Correction"}
                      value={draft} maxLength={6000} onChange={(event) => setDraft(event.target.value)} />
                  )}
                  <div className="row">
                    <Button type="submit" disabled={change.isPending || (editor.kind !== "forget" && !draft.trim())}>
                      {editor.kind === "forget" ? "Confirm forget" : "Save"}
                    </Button>
                    <Button type="button" variant="secondary" disabled={change.isPending} onClick={() => setEditor(null)}>Cancel</Button>
                  </div>
                </form>
              ) : null}
            </details>
          ))}
        </>
      ) : null}
    </section>
  );
}
