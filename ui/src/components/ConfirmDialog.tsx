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
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          onClick={onConfirm}
          disabled={busy}
        >
          {confirmLabel}
        </Button>
      </div>
    </ModalDialog>
  );
}
