import { Button } from "../../components/Button";

type Props = {
  presentationMode: boolean;
  onTogglePresentation: () => void;
  memoryReviewOpen: boolean;
  onToggleMemoryReview: () => void;
};

/** Training Mode controls for presentation and workspace review. */
export function TrainingToolbar({
  presentationMode,
  onTogglePresentation,
  memoryReviewOpen,
  onToggleMemoryReview,
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
        {!presentationMode ? (
          <Button type="button" variant="secondary" onClick={onToggleMemoryReview}
            aria-expanded={memoryReviewOpen}>
            {memoryReviewOpen ? "Close memory review" : "Review workspace memory"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
