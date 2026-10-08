import { Button } from "./Button";
import { ModalDialog } from "./ModalDialog";

type Props = {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  /** Disables confirm only — Cancel remains available. */
  confirmDisabled?: boolean;
  /** Compact status shown above actions (e.g. stale source-state notice). */
  notice?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  confirmDisabled = false,
  notice = null,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <ModalDialog
      open={open}
      role="alertdialog"
      title={title}
      description={body}
      busy={busy}
      onClose={onCancel}
    >
      {notice ? (
        <p className="muted" role="status">
          {notice}
        </p>
      ) : null}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          onClick={onConfirm}
          disabled={busy || confirmDisabled}
        >
          {confirmLabel}
        </Button>
      </div>
    </ModalDialog>
  );
}
