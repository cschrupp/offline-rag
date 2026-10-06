import { useEffect, useId, useRef, useState } from "react";
import type { Source } from "../api/types";

type SourceActionsMenuProps = {
  source: Source;
  disabled?: boolean;
  onRename: () => void;
  onReplace: () => void;
  onRemove: () => void;
};

export function SourceActionsMenu({
  source,
  disabled = false,
  onRename,
  onReplace,
  onRemove,
}: SourceActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

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
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
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

  return (
    <div className="source-actions">
      <button
        ref={buttonRef}
        type="button"
        className="source-actions-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Actions for ${source.display_name}`}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        ⋮
      </button>
      {open ? (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          className="source-actions-menu"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onRename();
              buttonRef.current?.focus();
            }}
          >
            Rename source
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onReplace();
              buttonRef.current?.focus();
            }}
          >
            Replace current version
          </button>
          <button
            type="button"
            role="menuitem"
            className="danger"
            onClick={() => {
              setOpen(false);
              onRemove();
              buttonRef.current?.focus();
            }}
          >
            Remove source
          </button>
        </div>
      ) : null}
    </div>
  );
}
