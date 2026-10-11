import { Button } from "../../../../components/Button";
import { CHUNK_DUEL_AUXILIARY_MESSAGE } from "../../games/chunkDuel/ChunkDuelGame";
import { GoldSourceContextView } from "../../games/common/GoldSourceContext";
import type { BlindDuelItem, DuelAuthority } from "../types";

type Props = {
  item: BlindDuelItem;
  authority: DuelAuthority | undefined;
  committed: boolean;
  preferredSide: "a" | "b" | null;
  onPrefer: (side: "a" | "b") => void;
  onCommit: () => void;
  onNext: () => void;
  nextLabel?: string;
};

export function ChunkDuelCalibration({
  item,
  authority,
  committed,
  preferredSide,
  onPrefer,
  onCommit,
  onNext,
  nextLabel = "Next",
}: Props) {
  return (
    <div className="stack gold-lab-game" data-testid="calibration-chunk-duel">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Chunk Duel calibration</h2>
        <p className="gold-lab-auxiliary-banner" role="status">
          {CHUNK_DUEL_AUXILIARY_MESSAGE}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Auxiliary preference only. Absolute 0/1/2 labels are context, not
          pairwise preference truth. No correctness score is computed.
        </p>
      </header>

      <section aria-labelledby="cal-duel-query">
        <h3 id="cal-duel-query">Effective query</h3>
        <p>{item.query}</p>
      </section>

      <div className="gold-lab-chunk-duel-pair">
        <div className="gold-lab-chunk-duel-side">
          <h3>Candidate A</h3>
          <GoldSourceContextView
            source={item.chunkA.source}
            heading="Source A"
            headingId="cal-duel-a"
          />
          <Button
            variant="secondary"
            disabled={committed}
            aria-pressed={preferredSide === "a"}
            onClick={() => onPrefer("a")}
          >
            Prefer A
          </Button>
        </div>
        <div className="gold-lab-chunk-duel-side">
          <h3>Candidate B</h3>
          <GoldSourceContextView
            source={item.chunkB.source}
            heading="Source B"
            headingId="cal-duel-b"
          />
          <Button
            variant="secondary"
            disabled={committed}
            aria-pressed={preferredSide === "b"}
            onClick={() => onPrefer("b")}
          >
            Prefer B
          </Button>
        </div>
      </div>

      {!committed ? (
        <Button onClick={onCommit} disabled={preferredSide === null}>
          Commit local preference
        </Button>
      ) : null}

      {committed && preferredSide && authority ? (
        <section
          className="gold-lab-calibration-reveal"
          aria-live="polite"
          data-testid="calibration-reveal"
        >
          <h3>Context (not preference truth)</h3>
          <p>
            You preferred {preferredSide === "a" ? "A" : "B"} (
            {preferredSide === "a"
              ? item.chunkA.chunkId
              : item.chunkB.chunkId}
            ).
          </p>
          <p>
            These 0/1/2 labels are absolute relevance authority. They are not
            pairwise preference truth.
          </p>
          <p>
            A ({authority.chunkAId}): {authority.relevanceA} · B (
            {authority.chunkBId}): {authority.relevanceB}
          </p>
          <Button onClick={onNext}>{nextLabel}</Button>
        </section>
      ) : null}
    </div>
  );
}
