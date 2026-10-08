import { Button } from "../../components/Button";

type Props = {
  presentationMode: boolean;
  onTogglePresentation: () => void;
};

/** Training Mode chrome: presentation control only (A4-D03). */
export function TrainingToolbar({
  presentationMode,
  onTogglePresentation,
}: Props) {
  return (
    <div className="training-toolbar stack" aria-label="Training Mode tools">
      <div className="row training-toolbar-actions">
        <Button
          type="button"
          variant="secondary"
          onClick={onTogglePresentation}
          aria-pressed={presentationMode}
        >
          {presentationMode ? "Exit presentation" : "Presentation view"}
        </Button>
      </div>
    </div>
  );
}
