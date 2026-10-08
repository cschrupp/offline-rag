import { useEffect, useId, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { ModalDialog } from "../../components/ModalDialog";
import { downloadArtifact } from "../../lib/downloadFile";
import { useNarrowLayout } from "../ask/useNarrowLayout";
import {
  exportQuestionBankJson,
  exportQuestionBankMarkdown,
  filterQuestionBankSearch,
  parseQuestionBankFile,
  planQuestionBankMerge,
  type QuestionBankImportPlan,
} from "./questionBankIo";
import {
  saveTrainingPrompt,
  type SavedTrainingPrompt,
} from "./trainingPrompts";

type Props = {
  workspaceId: string;
  workspaceTitle: string;
  savedPrompts: SavedTrainingPrompt[];
  askPending: boolean;
  drawersOpen?: boolean;
  onPromptsChange: (prompts: SavedTrainingPrompt[]) => void;
  onSelectPrompt: (prompt: SavedTrainingPrompt) => void;
  onDeletePrompt: (promptId: string) => void;
};

export function QuestionBankPanel({
  workspaceId,
  workspaceTitle,
  savedPrompts,
  askPending,
  drawersOpen = false,
  onPromptsChange,
  onSelectPrompt,
  onDeletePrompt,
}: Props) {
  const isNarrow = useNarrowLayout();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [importPlan, setImportPlan] = useState<{
    fileName: string;
    plan: QuestionBankImportPlan;
  } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const searchId = useId();
  const panelId = useId();

  const visible = filterQuestionBankSearch(savedPrompts, search);
  // A4-D02: never stack the bank over Sources/Evidence drawers.
  const surfaceOpen = open && !drawersOpen;

  useEffect(() => {
    if (!surfaceOpen || isNarrow) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (
        panelRef.current?.contains(target) ||
        triggerRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [surfaceOpen, isNarrow]);

  function closeBank() {
    setOpen(false);
    setSearch("");
    setImportError(null);
    queueMicrotask(() => triggerRef.current?.focus());
  }

  function openBank() {
    if (drawersOpen) return;
    setImportError(null);
    setOpen(true);
  }

  async function onFileChosen(file: File | null) {
    if (!file) return;
    setImportError(null);
    try {
      const raw = await file.text();
      const parsed = parseQuestionBankFile(file.name, raw, file.size);
      if (parsed.ok === false) {
        setImportError(parsed.error);
        return;
      }
      const plan = planQuestionBankMerge(savedPrompts, parsed.questions);
      plan.title = parsed.title;
      setImportPlan({ fileName: file.name, plan });
      setOpen(false);
    } catch {
      setImportError("Could not read the question bank file.");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function commitImport() {
    if (!importPlan || importPlan.plan.importableTexts.length === 0) return;
    let next = savedPrompts;
    for (const text of importPlan.plan.importableTexts) {
      next = saveTrainingPrompt(workspaceId, text);
    }
    onPromptsChange(next);
    setImportPlan(null);
  }

  const bankBody = (
    <div className="question-bank-body stack">
      <div className="row question-bank-header-row">
        <p className="question-bank-title" style={{ margin: 0 }}>
          Question bank
        </p>
        <span className="muted" aria-live="polite">
          {savedPrompts.length}
        </span>
      </div>
      <div className="field">
        <label htmlFor={searchId}>Search questions</label>
        <input
          id={searchId}
          type="search"
          placeholder="Search questions..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      {visible.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          {savedPrompts.length === 0
            ? "No saved training questions yet."
            : "No questions match this search."}
        </p>
      ) : (
        <ul className="question-bank-list">
          {visible.map((prompt) => (
            <li key={prompt.id} className="question-bank-item">
              <button
                type="button"
                className="question-bank-use"
                disabled={askPending}
                onClick={() => {
                  onSelectPrompt(prompt);
                  closeBank();
                }}
              >
                {prompt.text}
              </button>
              <button
                type="button"
                className="question-bank-delete"
                aria-label={`Delete saved question: ${prompt.text.slice(0, 80)}`}
                disabled={askPending}
                onClick={() => onDeletePrompt(prompt.id)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="row question-bank-io">
        <Button
          type="button"
          variant="secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={askPending}
        >
          Import
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            downloadArtifact(
              exportQuestionBankJson(savedPrompts, workspaceTitle),
            )
          }
          disabled={askPending || savedPrompts.length === 0}
        >
          Export JSON
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            downloadArtifact(
              exportQuestionBankMarkdown(savedPrompts, workspaceTitle),
            )
          }
          disabled={askPending || savedPrompts.length === 0}
        >
          Export Markdown
        </Button>
      </div>
      {importError ? (
        <p className="error-box" role="alert">
          {importError}
        </p>
      ) : null}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.md,.markdown,application/json,text/markdown,text/plain"
        hidden
        onChange={(event) => {
          void onFileChosen(event.target.files?.[0] ?? null);
        }}
      />
    </div>
  );

  return (
    <div className="question-bank-anchor">
      <button
        ref={triggerRef}
        type="button"
        className="btn btn-secondary"
        aria-expanded={surfaceOpen}
        aria-controls={surfaceOpen ? panelId : undefined}
        onClick={() => {
          if (surfaceOpen) closeBank();
          else openBank();
        }}
        disabled={askPending || drawersOpen}
      >
        {`Question bank (${savedPrompts.length})`}
      </button>

      {surfaceOpen && !isNarrow ? (
        <div
          id={panelId}
          ref={panelRef}
          className="question-bank-popover"
          role="dialog"
          aria-label="Question bank"
        >
          {bankBody}
        </div>
      ) : null}

      <ModalDialog
        open={surfaceOpen && isNarrow}
        title="Question bank"
        onClose={closeBank}
      >
        {bankBody}
      </ModalDialog>

      <ModalDialog
        open={importPlan != null}
        title="Import question bank"
        onClose={() => setImportPlan(null)}
      >
        {importPlan ? (
          <div className="stack">
            <p style={{ margin: 0 }}>
              File: {importPlan.fileName}
            </p>
            <ul className="muted" style={{ margin: 0 }}>
              <li>{importPlan.plan.entries.length} questions found</li>
              <li>{importPlan.plan.newCount} new</li>
              <li>{importPlan.plan.duplicateCount} duplicates</li>
              <li>{importPlan.plan.invalidCount} invalid</li>
              {importPlan.plan.capacitySkippedCount > 0 ? (
                <li>
                  {importPlan.plan.capacitySkippedCount} capacity-skipped
                </li>
              ) : null}
            </ul>
            <div className="row">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setImportPlan(null)}
              >
                Cancel
              </Button>
              {importPlan.plan.newCount > 0 ? (
                <Button type="button" onClick={commitImport}>
                  {`Import ${importPlan.plan.newCount} questions`}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
      </ModalDialog>
    </div>
  );
}
