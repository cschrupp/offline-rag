import type { GoldGameId } from "../state/sessionConfig";
import { GOLD_GAMES } from "../state/sessionConfig";

const GAME_LABELS: Record<GoldGameId, string> = {
  rapid_fire: "Rapid Fire",
  evidence_sweep: "Evidence Sweep",
  question_check: "Question Check",
  chunk_duel: "Chunk Duel",
};

type Props = {
  value: GoldGameId;
  onChange: (game: GoldGameId) => void;
  disabled?: boolean;
};

export function GamePicker({ value, onChange, disabled = false }: Props) {
  return (
    <fieldset className="gold-lab-fieldset" disabled={disabled}>
      <legend>Game</legend>
      <p className="muted">
        Selection only. Expert task execution is not available in this build.
      </p>
      <div className="row gold-lab-radio-row">
        {GOLD_GAMES.map((game) => (
          <label key={game} className="gold-lab-radio">
            <input
              type="radio"
              name="gold-lab-game"
              value={game}
              checked={value === game}
              onChange={() => onChange(game)}
            />
            <span>{GAME_LABELS[game]}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
