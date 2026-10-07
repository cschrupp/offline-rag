import { Button } from "../../components/Button";
import type { SavedTrainingPrompt } from "./trainingPrompts";

type Props = {
  question: string;
  savedPrompts: SavedTrainingPrompt[];
  presentationMode: boolean;
  askPending: boolean;
  onSavePrompt: () => void;
  onSelectPrompt: (prompt: SavedTrainingPrompt) => void;
  onDeletePrompt: (promptId: string) => void;
  onTogglePresentation: () => void;
};

export function TrainingToolbar({
  question,
  savedPrompts,
  presentationMode,
  askPending,
  onSavePrompt,
  onSelectPrompt,
  onDeletePrompt,
  onTogglePresentation,
}: Props) {
  const canSave = question.trim().length > 0 && !askPending;

  return (
    <div className="training-toolbar stack" aria-label="Training Mode tools">
      <div className="row training-toolbar-actions">
        <Button
          type="button"
          variant="secondary"
          onClick={onSavePrompt}
          disabled={!canSave}
        >
          Save question
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={onTogglePresentation}
          aria-pressed={presentationMode}
        >
          {presentationMode ? "Exit presentation" : "Presentation view"}
        </Button>
      </div>

      <div className="training-prompt-library">
        <p className="muted" style={{ margin: 0 }}>
          Saved questions (this workspace)
        </p>
        {savedPrompts.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No saved training questions yet.
          </p>
        ) : (
          <ul className="training-prompt-list">
            {savedPrompts.map((prompt) => (
              <li key={prompt.id} className="training-prompt-item">
                <button
                  type="button"
                  className="training-prompt-use"
                  disabled={askPending}
                  onClick={() => onSelectPrompt(prompt)}
                >
                  {prompt.text}
                </button>
                <button
                  type="button"
                  className="training-prompt-delete"
                  aria-label={`Delete saved question: ${prompt.text.slice(0, 48)}`}
                  disabled={askPending}
                  onClick={() => onDeletePrompt(prompt.id)}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
