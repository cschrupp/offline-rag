import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { downloadArtifact } from "../../lib/downloadFile";
import {
  conversationHasPendingTurn,
  serializeConversationJson,
  serializeConversationMarkdown,
  type ConversationExportInput,
} from "./conversationExport";
import type { ConversationHistoryEntry, IncompleteUserTurn } from "./conversationState";

type Props = {
  workspace: ConversationExportInput["workspace"];
  history: ConversationHistoryEntry[];
  incompleteTurns: IncompleteUserTurn[];
  exportedFromView: ConversationExportInput["exportedFromView"];
  askPending: boolean;
};

export function ExportConversationMenu({
  workspace,
  history,
  incompleteTurns,
  exportedFromView,
  askPending,
}: Props) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const pending = askPending || conversationHasPendingTurn(incompleteTurns);
  const hasThread =
    history.length > 0 ||
    incompleteTurns.some((turn) => turn.status === "failed");

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (
        menuRef.current?.contains(target) ||
        buttonRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    }
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function exportInput(): ConversationExportInput {
    return {
      workspace,
      history,
      incompleteTurns,
      exportedFromView,
    };
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  return (
    <div className="export-conversation-menu">
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-secondary"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={pending || !hasThread}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={onTriggerKeyDown}
      >
        Export conversation
      </button>
      {open ? (
        <div
          ref={menuRef}
          id={menuId}
          className="export-conversation-dropdown"
          role="menu"
          aria-label="Export conversation formats"
        >
          <button
            type="button"
            role="menuitem"
            className="export-conversation-item"
            onClick={() => {
              downloadArtifact(serializeConversationMarkdown(exportInput()));
              setOpen(false);
              buttonRef.current?.focus();
            }}
          >
            Export as Markdown
          </button>
          <button
            type="button"
            role="menuitem"
            className="export-conversation-item"
            onClick={() => {
              downloadArtifact(serializeConversationJson(exportInput()));
              setOpen(false);
              buttonRef.current?.focus();
            }}
          >
            Export as JSON
          </button>
        </div>
      ) : null}
    </div>
  );
}
