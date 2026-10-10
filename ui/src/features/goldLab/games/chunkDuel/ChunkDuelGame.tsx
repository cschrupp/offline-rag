import { Button } from "../../../../components/Button";
import type { AbsoluteRelevanceTaskDetail, GoldMutationReceipt } from "../../types";
import { GoldMutationStatus } from "../common/GoldMutationStatus";
import { GoldSourceContextView } from "../common/GoldSourceContext";

export const CHUNK_DUEL_AUXILIARY_MESSAGE =
  "Preference only — does not create Gold relevance";

type CandidateOption = {
  taskId: string;
  chunkId: string;
  label: string;
};

type Props = {
  caseId: string | null;
  caseIds: string[];
  candidates: CandidateOption[];
  selectedChunkIds: [string | null, string | null];
  duelDetails: [AbsoluteRelevanceTaskDetail | null, AbsoluteRelevanceTaskDetail | null];
  preferenceCount: number;
  preferenceCap: number | null;
  mutationBusy: boolean;
  ambiguous: boolean;
  mutationBlocked?: boolean;
  errorMessage: string | null;
  statusMessage: string | null;
  lastReceipt: GoldMutationReceipt | null;
  lastPreferredChunkId: string | null;
  onSelectCase: (caseId: string) => void;
  onToggleCandidate: (chunkId: string) => void;
  onPrefer: (side: "a" | "b") => void;
  onRetrySame: () => void;
  onStartAnother: () => void;
};

export function ChunkDuelGame({
  caseId,
  caseIds,
  candidates,
  selectedChunkIds,
  duelDetails,
  preferenceCount,
  preferenceCap,
  mutationBusy,
  ambiguous,
  mutationBlocked = false,
  errorMessage,
  statusMessage,
  lastReceipt,
  lastPreferredChunkId,
  onSelectCase,
  onToggleCandidate,
  onPrefer,
  onRetrySame,
  onStartAnother,
}: Props) {
  const locked =
    mutationBusy || ambiguous || mutationBlocked || lastReceipt !== null;
  const [chunkA, chunkB] = selectedChunkIds;
  const pairReady = Boolean(chunkA && chunkB && chunkA !== chunkB);
  const [detailA, detailB] = duelDetails;
  const capReached =
    preferenceCap !== null && preferenceCount >= preferenceCap;

  return (
    <div className="stack gold-lab-game">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h2>Chunk Duel</h2>
        <p className="gold-lab-auxiliary-banner" role="status">
          {CHUNK_DUEL_AUXILIARY_MESSAGE}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Auxiliary pairwise preference among active candidates of one case.
          This does not create Gold relevance or contribution.
        </p>
        {preferenceCap !== null ? (
          <p className="muted" style={{ margin: 0 }}>
            Session preference cap: {preferenceCount} / {preferenceCap}
          </p>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            Preferences recorded this session: {preferenceCount} (until stop)
          </p>
        )}
      </header>

      <fieldset className="gold-lab-fieldset" disabled={locked || capReached}>
        <legend>Case</legend>
        {caseIds.length === 0 ? (
          <p className="muted" role="status">
            No cases are available from the current task list.
          </p>
        ) : (
          <div className="row gold-lab-radio-row">
            {caseIds.map((id) => (
              <label key={id} className="gold-lab-radio">
                <input
                  type="radio"
                  name="gold-chunk-duel-case"
                  value={id}
                  checked={caseId === id}
                  onChange={() => onSelectCase(id)}
                  disabled={locked}
                />
                <span>{id}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      {!caseId ? (
        <p className="muted" role="status">
          Select a case to choose candidates.
        </p>
      ) : candidates.length < 2 ? (
        <p className="muted" role="status">
          No duel available for this case.
        </p>
      ) : (
        <>
          <fieldset
            className="gold-lab-fieldset"
            disabled={locked || capReached || lastReceipt !== null}
          >
            <legend>Select two candidates to compare</legend>
            <ul className="gold-lab-chunk-duel-pick-list">
              {candidates.map((candidate) => {
                const checked =
                  selectedChunkIds[0] === candidate.chunkId ||
                  selectedChunkIds[1] === candidate.chunkId;
                return (
                  <li key={candidate.chunkId}>
                    <label className="gold-lab-radio">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={
                          locked ||
                          capReached ||
                          (!checked &&
                            selectedChunkIds[0] !== null &&
                            selectedChunkIds[1] !== null)
                        }
                        onChange={() => onToggleCandidate(candidate.chunkId)}
                      />
                      <span>
                        {candidate.label}{" "}
                        <span className="muted">({candidate.chunkId})</span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </fieldset>

          {pairReady && detailA && detailB ? (
            <div className="gold-lab-chunk-duel-pair">
              <article
                className="gold-lab-chunk-duel-side"
                aria-labelledby="gold-duel-a-heading"
              >
                <h3 id="gold-duel-a-heading">Candidate A</h3>
                <p className="muted">{detailA.presentation.effective_query}</p>
                <GoldSourceContextView
                  source={detailA.presentation.candidate}
                  heading="Candidate A source"
                  headingId="gold-duel-source-a"
                />
                <Button
                  disabled={locked || capReached}
                  onClick={() => onPrefer("a")}
                >
                  Prefer candidate A
                </Button>
              </article>
              <article
                className="gold-lab-chunk-duel-side"
                aria-labelledby="gold-duel-b-heading"
              >
                <h3 id="gold-duel-b-heading">Candidate B</h3>
                <p className="muted">{detailB.presentation.effective_query}</p>
                <GoldSourceContextView
                  source={detailB.presentation.candidate}
                  heading="Candidate B source"
                  headingId="gold-duel-source-b"
                />
                <Button
                  disabled={locked || capReached}
                  onClick={() => onPrefer("b")}
                >
                  Prefer candidate B
                </Button>
              </article>
            </div>
          ) : null}
        </>
      )}

      <p className="gold-lab-auxiliary-banner" role="status">
        {CHUNK_DUEL_AUXILIARY_MESSAGE}
      </p>

      {lastReceipt ? (
        <div className="stack" role="status">
          <p className="muted">Preference recorded.</p>
          {lastPreferredChunkId ? (
            <p className="muted">Preferred candidate: {lastPreferredChunkId}</p>
          ) : null}
          <p className="gold-lab-auxiliary-banner">
            {CHUNK_DUEL_AUXILIARY_MESSAGE}
          </p>
          {!mutationBlocked && !capReached ? (
            <Button variant="secondary" onClick={onStartAnother}>
              Compare another pair
            </Button>
          ) : null}
        </div>
      ) : null}

      <GoldMutationStatus
        errorMessage={errorMessage}
        statusMessage={statusMessage}
        ambiguous={ambiguous && !mutationBlocked}
        onRetrySame={mutationBlocked ? undefined : onRetrySame}
        retryBusy={mutationBusy}
      />
    </div>
  );
}
