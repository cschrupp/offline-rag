import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { apiRequest } from "../../api/client";
import { userFacingErrorMessage } from "../../api/errors";
import { IntentHandle } from "../../api/idempotency";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Field";

export type StudyAid = {
  title: string;
  cue: string;
  complete: boolean;
  suggested_phrase?: string | null;
  inputs?: Input["inputs"];
  missing: string[];
  coverage: { original: string; term: string; definition: string; cue: string; source_record_id?: string | null; origin?: string; citation?: { source_display_name?: string; source_version?: number } }[];
};
type Group = { name: string; lines: string; reference: string; incomplete: boolean };
export type Input = {
  title: string;
  inputs: {
    name: string;
    concepts: { term: string; definition: string }[];
    source_record_id: string | null;
    incomplete: boolean;
  }[];
};

function emptyGroup(): Group {
  return { name: "", lines: "", reference: "", incomplete: false };
}

function toGroup(input: Input["inputs"][number]): Group {
  return {
    name: input.name,
    lines: input.concepts.map((concept) => `${concept.term} — ${concept.definition}`).join("\n"),
    reference: input.source_record_id ?? "",
    incomplete: input.incomplete,
  };
}

export function StudyAidCoverage({ aid }: { aid: StudyAid }) {
  return (
    <div className="stack">
      {aid.cue ? <p><strong>Cue</strong> {aid.cue}</p> : null}
      {aid.suggested_phrase ? <p><strong>Suggested phrase</strong> {aid.suggested_phrase}</p> : null}
      <p>{aid.complete ? "All supplied concepts are mapped." : "Partial study aid."}</p>
      {aid.missing.length ? <p>Missing definitions for {aid.missing.join(", ")}.</p> : null}
      {aid.coverage.length ? (
        <dl>{aid.coverage.map((row, index) => (
          <div key={index}>
            <dt>{row.cue} · {row.original} · {row.term}</dt>
            <dd>
              {row.definition}{" "}
              <small>{row.origin === "source_grounded"
                ? `${row.citation?.source_display_name ?? "Selected source"} · Version ${row.citation?.source_version ?? "unknown"}`
                : "Learner-provided"}</small>
            </dd>
          </div>
        ))}</dl>
      ) : null}
    </div>
  );
}

export function StudyAidEditor({
  root, references, sourceIds, revision, onCancel, onSaved,
}: {
  root: string;
  references: { id: string; label: string }[];
  sourceIds: string[];
  revision?: { id: string; version: number; aid: StudyAid };
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
  const [title, setTitle] = useState(revision?.aid.title ?? "");
  const [groups, setGroups] = useState<Group[]>(() => {
    const inputs = revision?.aid.inputs;
    if (inputs?.length) return inputs.map(toGroup);
    if (revision) {
      const originals = new Map<string, string[]>();
      for (const row of revision.aid.coverage) {
        const lines = originals.get(row.original) ?? [];
        lines.push(`${row.term} — ${row.definition}`);
        originals.set(row.original, lines);
      }
      for (const missing of revision.aid.missing) {
        if (!originals.has(missing)) originals.set(missing, []);
      }
      return [...originals].map(([name, lines]) => ({
        name, lines: lines.join("\n"),
        reference: revision.aid.coverage.find((row) => row.original === name)?.source_record_id ?? "",
        incomplete: revision.aid.missing.includes(name),
      }));
    }
    return [emptyGroup()];
  });
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ input: Input; aid: StudyAid } | null>(null);
  const [saved, setSaved] = useState(false);
  const intent = useRef<IntentHandle | null>(null);
  const propose = useMutation({
    mutationFn: (names: string[]) => apiRequest<{ inputs: Input["inputs"] }>(
      `${root}/study-aids/from-sources`,
      { method: "POST", json: { names, source_ids: sourceIds } },
    ),
    onSuccess: (proposal) => {
      setGroups(proposal.inputs.map(toGroup));
      setPreview(null);
    },
  });
  const prepare = useMutation({
    mutationFn: (input: Input) => apiRequest<StudyAid>(`${root}/study-aids/preview`, {
      method: "POST", json: input,
    }),
    onSuccess: (aid, input) => setPreview({ aid, input }),
  });
  const save = useMutation({
    mutationFn: ({ input, operationId }: { input: Input; operationId: string }) =>
      apiRequest<void>(revision ? `${root}/study-aids/${encodeURIComponent(revision.id)}` : `${root}/study-aids`, {
        method: revision ? "PUT" : "POST", idempotencyKey: operationId,
        json: revision ? { ...input, revision: revision.version } : input,
      }),
    onSuccess: async () => {
      setPreview(null);
      setTitle("");
      setGroups([emptyGroup()]);
      intent.current = null;
      setSaved(true);
      await onSaved();
    },
  });
  const pending = prepare.isPending || save.isPending || propose.isPending;

  function updateGroup(index: number, update: Partial<Group>) {
    setGroups((previous) => previous.map((group, i) => i === index ? { ...group, ...update } : group));
  }

  function previewAid(event: FormEvent) {
    event.preventDefault();
    setError("");
    setPreview(null);
    setSaved(false);
    const inputs: Input["inputs"] = [];
    for (const group of groups) {
      const concepts = [];
      for (const line of group.lines.split("\n").filter((line) => line.trim())) {
        const separator = line.indexOf("—");
        const term = separator > 0 ? line.slice(0, separator).trim() : "";
        const definition = separator > 0 ? line.slice(separator + 1).trim() : "";
        if (!term || !definition) {
          setError("Use one line per concept in the form Term — Definition. Leave unknown definitions out.");
          return;
        }
        concepts.push({ term, definition });
      }
      inputs.push({ name: group.name.trim(), concepts, source_record_id: group.reference || null, incomplete: group.incomplete });
    }
    prepare.mutate({ title: title.trim(), inputs });
  }

  function savePreview() {
    if (!preview || pending) return;
    const handle = intent.current ?? (intent.current = new IntentHandle());
    save.mutate({ input: preview.input, operationId: handle.prepare(JSON.stringify(preview.input)) });
  }

  return (
    <details className="stack" open={revision ? true : undefined}>
      <summary>{revision ? "Revise study aid" : "Create a mnemonic study aid"}</summary>
      <p className="muted">Supply the concepts you know. Add another original to combine mnemonics. Seneca maps each supplied concept to a cue.</p>
      <form className="stack" onSubmit={previewAid} onChange={() => {
        setPreview(null);
        setSaved(false);
      }}>
        <label htmlFor="study-aid-title">Study aid title</label>
        <input id="study-aid-title" value={title} onChange={(event) => setTitle(event.target.value)}
          maxLength={120} required disabled={pending} />
        {groups.map((group, index) => (
          <fieldset className="stack" key={index} disabled={pending}>
            <legend>Original mnemonic {index + 1}</legend>
            <label htmlFor={`mnemonic-name-${index}`}>Name</label>
            <input id={`mnemonic-name-${index}`} value={group.name} maxLength={48} required
              onChange={(event) => updateGroup(index, { name: event.target.value })} />
            <TextArea id={`mnemonic-concepts-${index}`} label="Concepts (Term — Definition)"
              value={group.lines} rows={3} maxLength={3400}
              onChange={(event) => updateGroup(index, { lines: event.target.value })} />
            <label>
              <input type="checkbox" checked={group.incomplete}
                onChange={(event) => updateGroup(index, { incomplete: event.target.checked })} />
              Some definitions are missing
            </label>
            <label htmlFor={`mnemonic-reference-${index}`}>Related discussion or concept</label>
            <select id={`mnemonic-reference-${index}`} value={group.reference}
              onChange={(event) => updateGroup(index, { reference: event.target.value })}>
              <option value="">No reference selected</option>
              {group.reference && !references.some((item) => item.id === group.reference) ? (
                <option value={group.reference}>Linked study reference</option>
              ) : null}
              {references.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </fieldset>
        ))}
        <div className="row">
          <Button type="button" variant="secondary" disabled={pending || groups.length >= 3}
            onClick={() => { setPreview(null); setGroups([...groups, emptyGroup()]); }}>
            Add original mnemonic
          </Button>
          {groups.length > 1 ? (
            <Button type="button" variant="secondary" disabled={pending}
              onClick={() => { setPreview(null); setGroups(groups.slice(0, -1)); }}>
              Remove last mnemonic
            </Button>
          ) : null}
          <Button type="button" variant="secondary"
            disabled={pending || !sourceIds.length || groups.some((group) => !group.name.trim() || group.lines.trim() !== "")}
            onClick={() => { setError(""); propose.mutate(groups.map((group) => group.name.trim())); }}>
            {propose.isPending ? "Searching selected sources…" : "Find definitions in selected sources"}
          </Button>
          {revision ? <Button type="button" variant="secondary" disabled={pending} onClick={onCancel}>Cancel revision</Button> : null}
          <Button type="submit" disabled={pending}>Preview study aid</Button>
        </div>
      </form>
      <p className="muted">Source lookup uses the configured generator and the selected sources. Enter original names with empty concept fields to look them up.</p>
      {propose.isSuccess ? <p role="status">Review the definitions found. Leave unsupported concepts marked incomplete.</p> : null}
      {error || prepare.isError || save.isError || propose.isError ? (
        <p role="alert" className="error-box">{error || userFacingErrorMessage(prepare.error ?? save.error ?? propose.error)}</p>
      ) : null}
      {preview ? (
        <>
          <StudyAidCoverage aid={preview.aid} />
          <Button disabled={pending || !preview.aid.coverage.length} onClick={savePreview}>Save study aid</Button>
        </>
      ) : null}
      {saved ? <p role="status">Saved to workspace knowledge.</p> : null}
    </details>
  );
}
