import { useMemo, useRef, useState } from "react";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import {
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_PRESENTATION_ID,
} from "../policy/presentations";
import type {
  GoldRegistrationSummary,
  GoldRelevance,
  GoldTrainingCalibrationPackage,
} from "../types";
import {
  compileAbsoluteItems,
  compileDuelItems,
  compileQuestionItems,
} from "./compileCalibrationItems";
import {
  buildCalibrationEvidence,
  downloadCalibrationEvidence,
} from "./evidence";
import { ChunkDuelCalibration } from "./games/ChunkDuelCalibration";
import { EvidenceSweepCalibration } from "./games/EvidenceSweepCalibration";
import { QuestionCheckCalibration } from "./games/QuestionCheckCalibration";
import { RapidFireCalibration } from "./games/RapidFireCalibration";
import type {
  AbsoluteLocalRecord,
  CalibrationGameKind,
  DuelLocalRecord,
  LocalQuestionResponse,
  QuestionLocalRecord,
} from "./types";

const BATCH_SIZE = 5;

const GAME_OPTIONS: Array<{
  kind: CalibrationGameKind;
  label: string;
  presentationId: string;
}> = [
  {
    kind: "rapid_fire",
    label: "Rapid Fire",
    presentationId: RAPID_FIRE_PRESENTATION_ID,
  },
  {
    kind: "question_check",
    label: "Question Check",
    presentationId: QUESTION_CHECK_PRESENTATION_ID,
  },
  {
    kind: "evidence_sweep",
    label: "Evidence Sweep",
    presentationId: EVIDENCE_SWEEP_PRESENTATION_ID,
  },
  {
    kind: "chunk_duel",
    label: "Chunk Duel",
    presentationId: CHUNK_DUEL_PRESENTATION_ID,
  },
];

type Props = {
  pkg: GoldTrainingCalibrationPackage;
  registration: GoldRegistrationSummary;
  onClearSelection: () => void;
};

function nowIso(): string {
  return new Date().toISOString();
}

export function CalibrationWorkspace({
  pkg,
  registration,
  onClearSelection,
}: Props) {
  const [game, setGame] = useState<CalibrationGameKind | null>(null);
  const [index, setIndex] = useState(0);
  const [batchOffset, setBatchOffset] = useState(0);
  const [draft, setDraft] = useState<GoldRelevance | null>(null);
  const [sweepDrafts, setSweepDrafts] = useState<
    Record<string, GoldRelevance | null>
  >({});
  const [sweepCommitted, setSweepCommitted] = useState<Record<string, boolean>>(
    {},
  );
  const [duelSide, setDuelSide] = useState<"a" | "b" | null>(null);
  const [committed, setCommitted] = useState(false);
  const [revisionCount, setRevisionCount] = useState(0);
  const [shownAt, setShownAt] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [absoluteRecords, setAbsoluteRecords] = useState<AbsoluteLocalRecord[]>(
    [],
  );
  const [questionRecords, setQuestionRecords] = useState<QuestionLocalRecord[]>(
    [],
  );
  const [duelRecords, setDuelRecords] = useState<DuelLocalRecord[]>([]);
  const [exported, setExported] = useState(false);
  const lastDraftRef = useRef<GoldRelevance | null>(null);

  const absoluteBundle = useMemo(() => compileAbsoluteItems(pkg), [pkg]);
  const questionBundle = useMemo(() => compileQuestionItems(pkg), [pkg]);
  const duelBundle = useMemo(() => compileDuelItems(pkg), [pkg]);

  function resetItemClock() {
    setShownAt(nowIso());
    setRevisionCount(0);
    setDraft(null);
    setDuelSide(null);
    setCommitted(false);
    lastDraftRef.current = null;
  }

  function startGame(next: CalibrationGameKind) {
    setGame(next);
    setIndex(0);
    setBatchOffset(0);
    setAbsoluteRecords([]);
    setQuestionRecords([]);
    setDuelRecords([]);
    setSweepDrafts({});
    setSweepCommitted({});
    setExported(false);
    setStartedAt(nowIso());
    resetItemClock();
  }

  function recordTiming() {
    const shown = shownAt ?? nowIso();
    const committedAt = nowIso();
    return {
      shownAt: shown,
      committedAt,
      durationMs: Math.max(0, Date.parse(committedAt) - Date.parse(shown)),
      revisionCount,
    };
  }

  function onAbsoluteDraft(value: GoldRelevance) {
    if (committed) return;
    if (lastDraftRef.current !== null && lastDraftRef.current !== value) {
      setRevisionCount((count) => count + 1);
    }
    lastDraftRef.current = value;
    setDraft(value);
  }

  function commitAbsolute(itemId: string) {
    if (draft === null || committed) return;
    const authority = absoluteBundle.authorityByItemId.get(itemId);
    const item = absoluteBundle.items.find((entry) => entry.itemId === itemId);
    if (!authority || !item) return;
    const timing = recordTiming();
    setAbsoluteRecords((prev) => [
      ...prev,
      {
        itemId,
        caseId: item.caseId,
        candidateChunkId: item.candidateChunkId,
        localRelevance: draft,
        authorityRelevance: authority.relevance,
        matched: draft === authority.relevance,
        timing,
      },
    ]);
    setCommitted(true);
  }

  function commitSweep(itemId: string) {
    if (sweepCommitted[itemId]) return;
    const draftValue = sweepDrafts[itemId];
    if (draftValue === null || draftValue === undefined) return;
    const authority = absoluteBundle.authorityByItemId.get(itemId);
    const item = absoluteBundle.items.find((entry) => entry.itemId === itemId);
    if (!authority || !item) return;
    const timing = recordTiming();
    setAbsoluteRecords((prev) => [
      ...prev,
      {
        itemId,
        caseId: item.caseId,
        candidateChunkId: item.candidateChunkId,
        localRelevance: draftValue,
        authorityRelevance: authority.relevance,
        matched: draftValue === authority.relevance,
        timing,
      },
    ]);
    setSweepCommitted((prev) => ({ ...prev, [itemId]: true }));
  }

  function commitQuestion(response: LocalQuestionResponse) {
    if (committed || !game) return;
    const item = questionBundle.items[index];
    if (!item) return;
    const authority = questionBundle.authorityByItemId.get(item.itemId);
    if (!authority) return;
    const timing = recordTiming();
    setQuestionRecords((prev) => [
      ...prev,
      {
        itemId: item.itemId,
        caseId: item.caseId,
        local: response,
        authorityDisposition: authority.disposition,
        dispositionMatched: response.decision === authority.disposition,
        timing,
      },
    ]);
    setCommitted(true);
  }

  function preferDuel(side: "a" | "b") {
    if (committed) return;
    if (duelSide !== null && duelSide !== side) {
      setRevisionCount((count) => count + 1);
    }
    setDuelSide(side);
  }

  function commitDuel() {
    if (committed || duelSide === null) return;
    const item = duelBundle.items[index];
    if (!item) return;
    const authority = duelBundle.authorityByItemId.get(item.itemId);
    if (!authority) return;
    const timing = recordTiming();
    const preferredChunkId =
      duelSide === "a" ? item.chunkA.chunkId : item.chunkB.chunkId;
    const otherChunkId =
      duelSide === "a" ? item.chunkB.chunkId : item.chunkA.chunkId;
    setDuelRecords((prev) => [
      ...prev,
      {
        itemId: item.itemId,
        caseId: item.caseId,
        preferredSide: duelSide,
        preferredChunkId,
        otherChunkId,
        authorityRelevanceA: authority.relevanceA,
        authorityRelevanceB: authority.relevanceB,
        timing,
      },
    ]);
    setCommitted(true);
  }

  function advanceLinear(total: number) {
    if (index + 1 >= total) {
      setIndex(total);
      return;
    }
    setIndex((value) => value + 1);
    resetItemClock();
  }

  function exportEvidence() {
    if (!game || !startedAt) return;
    const endedAt = nowIso();
    const totalItems =
      game === "rapid_fire" || game === "evidence_sweep"
        ? absoluteBundle.items.length
        : game === "question_check"
          ? questionBundle.items.length
          : duelBundle.items.length;
    const artifact = buildCalibrationEvidence({
      pkg,
      game,
      startedAt,
      endedAt,
      totalItems,
      absoluteRecords:
        game === "rapid_fire" || game === "evidence_sweep"
          ? absoluteRecords
          : undefined,
      questionRecords: game === "question_check" ? questionRecords : undefined,
      duelRecords: game === "chunk_duel" ? duelRecords : undefined,
    });
    downloadCalibrationEvidence(artifact);
    setExported(true);
  }

  const sweepBatch = useMemo(() => {
    if (game !== "evidence_sweep") return [];
    return absoluteBundle.items.slice(batchOffset, batchOffset + BATCH_SIZE);
  }, [absoluteBundle.items, batchOffset, game]);

  const sweepBatchComplete =
    game === "evidence_sweep" &&
    sweepBatch.length > 0 &&
    sweepBatch.every((item) => sweepCommitted[item.itemId]);

  return (
    <div className="stack gold-lab-calibration" data-testid="calibration-workspace">
      <Card>
        <h2>Selected registration</h2>
        <dl className="gold-lab-meta">
          <div>
            <dt>Dataset</dt>
            <dd>
              <code>{registration.dataset_id}</code>
            </dd>
          </div>
          <div>
            <dt>Projection</dt>
            <dd>
              <code>{registration.projection_sha256.slice(0, 16)}…</code>
            </dd>
          </div>
          <div>
            <dt>Baseline</dt>
            <dd>
              <code>{registration.baseline_sha256.slice(0, 16)}…</code>
            </dd>
          </div>
          <div>
            <dt>Exported cases</dt>
            <dd>{registration.exported_case_ids.length}</dd>
          </div>
          <div>
            <dt>Registered at</dt>
            <dd>{registration.registered_at}</dd>
          </div>
        </dl>
        <Button variant="secondary" onClick={onClearSelection}>
          Change registration
        </Button>
      </Card>

      {!game ? (
        <Card>
          <h2>Calibration presentation</h2>
          <p className="muted">
            Unapproved candidate presentations may be exercised here against
            immutable registration-time truth. Calibration cannot mutate Gold or
            change production eligibility.
          </p>
          <div className="stack">
            {GAME_OPTIONS.map((option) => (
              <Button
                key={option.kind}
                variant="secondary"
                onClick={() => startGame(option.kind)}
              >
                Calibrate {option.label}
              </Button>
            ))}
          </div>
        </Card>
      ) : null}

      {game === "rapid_fire" ? (
        absoluteBundle.items.length === 0 ? (
          <Card>
            <p className="muted" role="status">
              No accepted/edited absolute candidates are available in this
              package.
            </p>
          </Card>
        ) : index < absoluteBundle.items.length ? (
          <RapidFireCalibration
            key={absoluteBundle.items[index]!.itemId}
            item={absoluteBundle.items[index]!}
            authority={absoluteBundle.authorityByItemId.get(
              absoluteBundle.items[index]!.itemId,
            )}
            committed={committed}
            draft={draft}
            revealRelevance={committed ? draft : null}
            onDraftChange={onAbsoluteDraft}
            onCommit={() =>
              commitAbsolute(absoluteBundle.items[index]!.itemId)
            }
            onNext={() => advanceLinear(absoluteBundle.items.length)}
            nextLabel={
              index + 1 >= absoluteBundle.items.length
                ? "Finish items"
                : "Next"
            }
          />
        ) : (
          <SessionComplete
            answered={absoluteRecords.length}
            total={absoluteBundle.items.length}
            exported={exported}
            onExport={exportEvidence}
          />
        )
      ) : null}

      {game === "evidence_sweep" ? (
        absoluteBundle.items.length === 0 ? (
          <Card>
            <p className="muted" role="status">
              No accepted/edited absolute candidates are available in this
              package.
            </p>
          </Card>
        ) : batchOffset >= absoluteBundle.items.length ? (
          <SessionComplete
            answered={absoluteRecords.length}
            total={absoluteBundle.items.length}
            exported={exported}
            onExport={exportEvidence}
          />
        ) : (
          <EvidenceSweepCalibration
            cards={sweepBatch.map((item) => ({
              item,
              authority: absoluteBundle.authorityByItemId.get(item.itemId)!,
              draft: sweepDrafts[item.itemId] ?? null,
              committed: Boolean(sweepCommitted[item.itemId]),
            }))}
            onDraftChange={(itemId, value) => {
              setSweepDrafts((prev) => {
                const prior = prev[itemId];
                if (prior !== null && prior !== undefined && prior !== value) {
                  setRevisionCount((count) => count + 1);
                }
                return { ...prev, [itemId]: value };
              });
            }}
            onCommit={commitSweep}
            onNextBatch={() => {
              const next = batchOffset + BATCH_SIZE;
              if (next >= absoluteBundle.items.length) {
                setBatchOffset(absoluteBundle.items.length);
                return;
              }
              setBatchOffset(next);
              setShownAt(nowIso());
            }}
            batchComplete={sweepBatchComplete}
            nextBatchDisabled={false}
            finishLabel={
              batchOffset + BATCH_SIZE >= absoluteBundle.items.length
                ? "Finish session"
                : "Next batch"
            }
          />
        )
      ) : null}

      {game === "question_check" ? (
        questionBundle.items.length === 0 ? (
          <Card>
            <p className="muted" role="status">
              No finalized adjudication cases are available in this package.
            </p>
          </Card>
        ) : index < questionBundle.items.length ? (
          <QuestionCheckCalibration
            key={questionBundle.items[index]!.itemId}
            item={questionBundle.items[index]!}
            authority={questionBundle.authorityByItemId.get(
              questionBundle.items[index]!.itemId,
            )}
            committed={committed}
            onCommit={commitQuestion}
            onNext={() => advanceLinear(questionBundle.items.length)}
            nextLabel={
              index + 1 >= questionBundle.items.length
                ? "Finish items"
                : "Next"
            }
          />
        ) : (
          <SessionComplete
            answered={questionRecords.length}
            total={questionBundle.items.length}
            exported={exported}
            onExport={exportEvidence}
          />
        )
      ) : null}

      {game === "chunk_duel" ? (
        duelBundle.items.length === 0 ? (
          <Card>
            <p className="muted" role="status">
              No duel-eligible accepted/edited cases with two candidates are
              available.
            </p>
          </Card>
        ) : index < duelBundle.items.length ? (
          <ChunkDuelCalibration
            item={duelBundle.items[index]!}
            authority={duelBundle.authorityByItemId.get(
              duelBundle.items[index]!.itemId,
            )}
            committed={committed}
            preferredSide={duelSide}
            onPrefer={preferDuel}
            onCommit={commitDuel}
            onNext={() => advanceLinear(duelBundle.items.length)}
            nextLabel={
              index + 1 >= duelBundle.items.length ? "Finish items" : "Next"
            }
          />
        ) : (
          <SessionComplete
            answered={duelRecords.length}
            total={duelBundle.items.length}
            exported={exported}
            onExport={exportEvidence}
          />
        )
      ) : null}

      {game &&
      !(
        (game === "rapid_fire" && index >= absoluteBundle.items.length) ||
        (game === "question_check" && index >= questionBundle.items.length) ||
        (game === "chunk_duel" && index >= duelBundle.items.length) ||
        (game === "evidence_sweep" &&
          batchOffset >= absoluteBundle.items.length)
      ) &&
      (absoluteRecords.length > 0 ||
        questionRecords.length > 0 ||
        duelRecords.length > 0) ? (
        <Card>
          <h2>Export evidence early</h2>
          <p className="muted">
            Partial runs are marked abandoned. Download is local JSON only.
          </p>
          <Button variant="secondary" onClick={exportEvidence}>
            Download calibration evidence
          </Button>
          {exported ? <GovernanceNotice /> : null}
        </Card>
      ) : null}
    </div>
  );
}

function SessionComplete({
  answered,
  total,
  exported,
  onExport,
}: {
  answered: number;
  total: number;
  exported: boolean;
  onExport: () => void;
}) {
  const abandoned = answered < total;
  return (
    <Card data-testid="calibration-session-complete">
      <h2>Calibration session</h2>
      <p>
        Answered {answered} / {total}.{" "}
        {abandoned ? "Abandoned / incomplete." : "Completed."}
      </p>
      <Button onClick={onExport}>Download calibration evidence</Button>
      {exported ? <GovernanceNotice /> : null}
    </Card>
  );
}

function GovernanceNotice() {
  return (
    <p className="gold-lab-calibration-governance" role="status">
      Calibration evidence is review input only. ALLOW_PRODUCTION /
      REPAIR_REQUIRED / DISALLOW is a Human governance disposition. Production
      eligibility changes only through a separately authorized repository update
      to the versioned approved-presentations policy.
    </p>
  );
}
