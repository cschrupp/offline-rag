import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import type {
  GoldRegistrationSummary,
  GoldRelevance,
  GoldTrainingCalibrationPackage,
} from "../types";
import { compileTrainingPackage } from "./compiler";
import { EvidenceSelectionDrill } from "./drills/EvidenceSelectionDrill";
import { QuestionCheckDrill } from "./drills/QuestionCheckDrill";
import { RelevanceRecallDrill } from "./drills/RelevanceRecallDrill";
import type {
  EvidenceSelectAuthority,
  LocalQcDisposition,
  QuestionCheckAuthority,
  RelevanceRecallAuthority,
} from "./types";

type Props = {
  campaignId: string;
  pkg: GoldTrainingCalibrationPackage;
  registration: GoldRegistrationSummary;
  onClearSelection: () => void;
};

export function TrainingWorkspace({
  campaignId,
  pkg,
  registration,
  onClearSelection,
}: Props) {
  const compiled = useMemo(() => compileTrainingPackage(pkg), [pkg]);
  const [drillIndex, setDrillIndex] = useState(0);
  const [committed, setCommitted] = useState(false);
  const [qcDisposition, setQcDisposition] = useState<LocalQcDisposition | null>(
    null,
  );
  const [recallStep, setRecallStep] = useState(0);
  const [recallStepCommitted, setRecallStepCommitted] = useState(false);
  const [recallDraftAuthority, setRecallDraftAuthority] = useState<
    GoldRelevance | undefined
  >(undefined);
  const [sessionMatches, setSessionMatches] = useState(0);
  const [sessionAnswers, setSessionAnswers] = useState(0);

  const current = compiled.drills[drillIndex] ?? null;
  const finished = compiled.drills.length > 0 && drillIndex >= compiled.drills.length;

  function resetDrillLocal() {
    setCommitted(false);
    setQcDisposition(null);
    setRecallStep(0);
    setRecallStepCommitted(false);
    setRecallDraftAuthority(undefined);
  }

  function advanceDrill() {
    setDrillIndex((value) => value + 1);
    resetDrillLocal();
  }

  return (
    <div className="stack gold-lab-training" data-testid="training-workspace">
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
            <dt>Compiled drills</dt>
            <dd>{compiled.drills.length}</dd>
          </div>
          <div>
            <dt>Compiled scenarios</dt>
            <dd>{compiled.scenarios.length}</dd>
          </div>
        </dl>
        <div className="row" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
          <Button variant="secondary" onClick={onClearSelection}>
            Change registration
          </Button>
          <Link
            to={`/gold-lab/campaigns/${campaignId}/training/scenario?dataset=${encodeURIComponent(registration.dataset_id)}`}
          >
            Open scenario / debrief
          </Link>
        </div>
      </Card>

      {compiled.issues.length > 0 ? (
        <Card>
          <h2>Compiler notes</h2>
          <ul>
            {compiled.issues.map((row) => (
              <li key={`${row.caseId}-${row.templateId}-${row.reason}`}>
                Training cannot safely compile {row.templateId} for{" "}
                <code>{row.caseId}</code>: {row.reason}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {compiled.drills.length === 0 ? (
        <Card>
          <p className="muted" role="status">
            No learner drills could be compiled from this registered package.
          </p>
        </Card>
      ) : null}

      {!finished && current ? (
        <>
          <p className="muted" data-testid="training-progress">
            Exercise {drillIndex + 1} of {compiled.drills.length}
            {sessionAnswers > 0
              ? ` · ${sessionAnswers} responses committed`
              : ""}
          </p>

          {current.kind === "evidence_select" ? (
            <EvidenceSelectionDrill
              key={current.exerciseId}
              exercise={current}
              authority={
                committed
                  ? (compiled.authorityByExerciseId.get(
                      current.exerciseId,
                    ) as EvidenceSelectAuthority | undefined)
                  : undefined
              }
              committed={committed}
              onCommit={(chunks) => {
                setCommitted(true);
                setSessionAnswers((n) => n + 1);
                const auth = compiled.authorityByExerciseId.get(
                  current.exerciseId,
                ) as EvidenceSelectAuthority | undefined;
                if (auth) {
                  const selected = new Set(chunks);
                  const positives = new Set(auth.positiveChunkIds);
                  const exact =
                    selected.size === positives.size &&
                    [...selected].every((id) => positives.has(id));
                  if (exact) setSessionMatches((n) => n + 1);
                }
              }}
              onNext={advanceDrill}
            />
          ) : null}

          {current.kind === "relevance_recall" ? (
            <RelevanceRecallDrill
              key={`${current.exerciseId}-${recallStep}`}
              exercise={current}
              stepAuthority={
                recallStepCommitted ? recallDraftAuthority : undefined
              }
              stepIndex={recallStep}
              stepCommitted={recallStepCommitted}
              onCommitStep={(relevance) => {
                const auth = compiled.authorityByExerciseId.get(
                  current.exerciseId,
                ) as RelevanceRecallAuthority | undefined;
                const step = current.steps[recallStep];
                const expected = step
                  ? auth?.relevanceByChunkId[step.candidateChunkId]
                  : undefined;
                setRecallDraftAuthority(expected);
                setRecallStepCommitted(true);
                setSessionAnswers((n) => n + 1);
                if (expected !== undefined && expected === relevance) {
                  setSessionMatches((n) => n + 1);
                }
              }}
              onAdvance={() => {
                if (recallStep + 1 >= current.steps.length) {
                  advanceDrill();
                  return;
                }
                setRecallStep((value) => value + 1);
                setRecallStepCommitted(false);
                setRecallDraftAuthority(undefined);
              }}
            />
          ) : null}

          {current.kind === "question_check" ? (
            <QuestionCheckDrill
              key={current.exerciseId}
              exercise={current}
              authority={
                committed
                  ? (compiled.authorityByExerciseId.get(
                      current.exerciseId,
                    ) as QuestionCheckAuthority | undefined)
                  : undefined
              }
              committed={committed}
              localDisposition={qcDisposition}
              onCommit={(disposition) => {
                setQcDisposition(disposition);
                setCommitted(true);
                setSessionAnswers((n) => n + 1);
                const auth = compiled.authorityByExerciseId.get(
                  current.exerciseId,
                ) as QuestionCheckAuthority | undefined;
                if (auth && auth.disposition === disposition) {
                  setSessionMatches((n) => n + 1);
                }
              }}
              onNext={advanceDrill}
            />
          ) : null}
        </>
      ) : null}

      {finished ? (
        <Card data-testid="training-session-complete">
          <h2>Local session summary</h2>
          <p>
            {sessionMatches} matches across {sessionAnswers} committed
            responses. This is local observational progress only — not a Gold
            score, grade, certification, mastery, or contribution.
          </p>
          <Link
            to={`/gold-lab/campaigns/${campaignId}/training/scenario?dataset=${encodeURIComponent(registration.dataset_id)}`}
          >
            Continue to scenario / debrief
          </Link>
        </Card>
      ) : null}
    </div>
  );
}
