import {
  useCallback,
  useId,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { Outlet, useLocation } from "react-router-dom";
import {
  GoldLabGuideContext,
  type GoldLabGuideKey,
} from "./GoldLabGuideContext";

type GuideContent = {
  goal: string;
  steps: string[];
  tip?: string;
};

const GUIDE_CONTENT: Record<GoldLabGuideKey, GuideContent> = {
  quick_play_ready: {
    goal: "Create a small activity deck from this workspace’s published sources.",
    steps: [
      "Choose the workspace whose documents you want to review.",
      "Generate a deck, or resume one that is already available.",
      "Choose an available game and start reviewing.",
    ],
    tip: "Your contributions are expert judgments, not quiz scores.",
  },
  quick_play_loading: {
    goal: "Seneca is checking this workspace’s published sources and saved deck.",
    steps: [
      "Wait for the deck state to load.",
      "Refresh and return here if you need to reconnect.",
      "Choose an available action after the current state appears.",
    ],
  },
  quick_play_generating: {
    goal: "Seneca is proposing questions and gathering candidate passages.",
    steps: [
      "Let the operation continue; its progress is saved.",
      "You can refresh and return to this operation.",
      "When the deck is ready, choose a game.",
    ],
    tip: "No judgments are finalized until you review them.",
  },
  quick_play_error: {
    goal: "Review the reported problem before starting another generation.",
    steps: [
      "Read the specific error or source-readiness message.",
      "Use Retry only after the underlying issue is resolved.",
      "Check the deck state again if an operation may still be reconciling.",
    ],
    tip: "A failed generation does not replace the published workspace or saved judgments.",
  },
  quick_play_empty: {
    goal: "Make sure this workspace has published, readable source text.",
    steps: [
      "Open the workspace and add or update supported sources.",
      "Publish the workspace changes.",
      "Return here and check the deck again.",
    ],
  },
  quick_play_playable: {
    goal: "Choose an available activity and review its questions or evidence.",
    steps: [
      "Resume the suggested game, or choose another available game.",
      "Read the task and its displayed source material.",
      "Save your judgment before moving to another task.",
    ],
    tip: "Only eligible work for this published snapshot is shown.",
  },
  quick_play_complete: {
    goal: "This deck has no more eligible tasks.",
    steps: [
      "Resume another available game if one has pending work.",
      "Replenish when you want Seneca to prepare another activity set.",
      "Previously saved judgments remain recorded.",
    ],
  },
  question_check_active: {
    goal: "Decide whether this proposed question is clear and supported by its displayed source.",
    steps: [
      "Read the question and source excerpt.",
      "Accept if suitable, Edit to improve it, or Reject if unusable.",
      "Save your choice, then continue to the next question.",
    ],
    tip: "You are evaluating the question, not answering it.",
  },
  question_check_saving: {
    goal: "Seneca is saving your Question Check judgment.",
    steps: [
      "Wait for the save to finish before continuing.",
      "If the result is uncertain, follow the reconciliation message on screen.",
      "Continue or correct only after Seneca confirms the saved state.",
    ],
    tip: "A pending save is not shown as a completed judgment.",
  },
  question_check_saved: {
    goal: "Your judgment was recorded.",
    steps: [
      "Continue to the next question, or correct this judgment.",
      "End the session when you are ready to return.",
    ],
    tip: "The confirmation reflects a saved judgment, not a correctness grade.",
  },
  rapid_fire_active: {
    goal: "Judge how strongly this passage supports the question.",
    steps: [
      "Choose 0 — Irrelevant when it does not support the question.",
      "Choose 1 — Supporting evidence when it helps but does not directly establish the answer.",
      "Choose 2 — Direct evidence when the passage directly supports the question.",
    ],
    tip: "For example, background context may support a question; a passage stating the requested fact is direct evidence. Judge this passage alone.",
  },
  rapid_fire_saving: {
    goal: "Seneca is saving your relevance judgment.",
    steps: [
      "Wait for the save to finish before continuing.",
      "If the result is uncertain, follow the reconciliation message on screen.",
      "Continue or correct only after Seneca confirms the saved state.",
    ],
    tip: "A pending save is not shown as a completed judgment.",
  },
  rapid_fire_saved: {
    goal: "Your relevance judgment was recorded.",
    steps: [
      "Continue to the next passage, or correct this judgment.",
      "End the session when you are ready to return.",
    ],
    tip: "The confirmation reflects a saved judgment, not a correctness grade.",
  },
  session_preparing: {
    goal: "Seneca is loading the next eligible task for this game.",
    steps: [
      "Wait for the task or status message to appear.",
      "If an error appears, read it before retrying.",
      "Use End session when no task is being saved.",
    ],
  },
  session_error: {
    goal: "Resolve or reconcile the reported state before continuing.",
    steps: [
      "Read the error and any recovery instruction.",
      "If a submission is unresolved, use the provided retry or reload action.",
      "Continue only after Seneca confirms the saved state.",
    ],
    tip: "An uncertain submission is not shown as successful.",
  },
  session_complete: {
    goal: "There are no more eligible tasks in this work session.",
    steps: [
      "Return to Quick Play or the campaign to choose another activity.",
      "Saved judgments remain recorded.",
    ],
    tip: "Completion reports progress, not correctness.",
  },
  session_closed: {
    goal: "This campaign is closed, so new judgments cannot be started.",
    steps: [
      "Return to Quick Play or the campaign overview.",
      "Review existing campaign information there.",
    ],
  },
  advanced_home: {
    goal: "Advanced Gold Lab manages projects, baselines, and campaigns.",
    steps: [
      "Create or open a project for a workspace.",
      "Review eligible authoring baselines before creating a campaign.",
      "Use Quick Play for a streamlined expert-review workflow.",
    ],
  },
  project: {
    goal: "A project organizes Gold campaigns for one workspace.",
    steps: [
      "Review its status and eligible pristine authoring baselines.",
      "Create a campaign only when an eligible baseline is available.",
      "Archive only when you intend to stop creating campaigns here.",
    ],
    tip: "Archiving is a project lifecycle action; existing campaigns remain readable.",
  },
  campaign: {
    goal: "A campaign groups expert review work against a fixed baseline.",
    steps: [
      "Review task availability and the selected game or workload.",
      "Start Question Check or Rapid Fire when eligible work is available.",
      "Use campaign management actions only when you intend to change its lifecycle.",
    ],
    tip: "Gold judgments are expert labels; the interface does not grade them.",
  },
  presentation_review: {
    goal: "Inspect how a candidate presentation displays a task and its source.",
    steps: [
      "Review the presentation and its task context.",
      "Use the preview controls to inspect the experience.",
      "Return to the campaign when you are done.",
    ],
    tip: "Presentation review is a preview and does not write Gold judgments.",
  },
  contribution: {
    goal: "Review contribution summaries for this campaign.",
    steps: [
      "Use the displayed totals to understand recorded activity.",
      "Open Calibration only when you intend to inspect a registered dataset.",
      "Return to the campaign to continue eligible review work.",
    ],
    tip: "Summary counts describe activity; they are not correctness scores.",
  },
  calibration: {
    goal: "Inspect a registered dataset using local calibration evidence.",
    steps: [
      "Choose a registered dataset when one is available.",
      "Review the shown material and calibration output.",
      "Return to the campaign when finished.",
    ],
    tip: "Calibration is observational and does not mutate Gold judgments.",
  },
  training: {
    goal: "Practice with an immutable registered training dataset.",
    steps: [
      "Choose a registered dataset.",
      "Read each exercise and use its practice controls.",
      "Review the debrief when available.",
    ],
    tip: "Training does not write Gold judgments or durable learner progress.",
  },
  training_scenario: {
    goal: "Work through a practice scenario from a registered dataset.",
    steps: [
      "Read the exercise instructions and displayed evidence.",
      "Use the practice controls to explore the scenario.",
      "Review the debrief before returning to Training.",
    ],
    tip: "This practice view does not reveal hidden Gold labels or create production judgments.",
  },
  unavailable_game: {
    goal: "This presentation is not enabled for production Gold work.",
    steps: [
      "Return to the campaign or Quick Play.",
      "Choose Question Check or Rapid Fire when eligible work is available.",
    ],
    tip: "This help panel does not grant access to additional games.",
  },
};

function guideKeyForPath(pathname: string): GoldLabGuideKey {
  const routePath = pathname.replace(/\/+$/, "") || "/";
  if (routePath === "/gold-lab") return "quick_play_ready";
  if (routePath === "/gold-lab/advanced") return "advanced_home";
  if (routePath.includes("/training/scenario")) return "training_scenario";
  if (routePath.endsWith("/presentation-review")) return "presentation_review";
  if (routePath.endsWith("/contribution")) return "contribution";
  if (routePath.endsWith("/calibration")) return "calibration";
  if (routePath.endsWith("/training")) return "training";
  if (routePath.endsWith("/work")) return "session_preparing";
  if (routePath.includes("/campaigns/")) return "campaign";
  if (routePath.includes("/projects/")) return "project";
  return "advanced_home";
}

function GuideText({ content }: { content: GuideContent }) {
  return (
    <div className="gold-lab-guide-content">
      <h3>Your goal</h3>
      <p>{content.goal}</p>
      <h3>What to do</h3>
      <ol>
        {content.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {content.tip ? (
        <p className="gold-lab-guide-tip">
          <strong>Tip:</strong> {content.tip}
        </p>
      ) : null}
    </div>
  );
}

export function GoldLabGuideLayout({
  guideKey,
  children,
}: {
  guideKey: GoldLabGuideKey;
  children: ReactNode;
}) {
  const id = useId();
  const content = GUIDE_CONTENT[guideKey];

  return (
    <div className="gold-lab-guide-layout">
      <details className="gold-lab-guide-mobile">
        <summary>How to play / What do I do here?</summary>
        <section aria-label="Gold Lab instructions">
          <GuideText content={content} />
        </section>
      </details>
      <div className="gold-lab-guide-main">{children}</div>
      <aside
        className="gold-lab-guide-desktop"
        aria-labelledby={`${id}-heading`}
      >
        <h2 id={`${id}-heading`}>How to play</h2>
        <GuideText content={content} />
      </aside>
    </div>
  );
}

export function GoldLabGuideRoute() {
  const location = useLocation();
  const [override, setOverride] = useState<{
    locationKey: string;
    guideKey: GoldLabGuideKey;
  } | null>(null);
  const guideKey =
    override?.locationKey === location.key
      ? override.guideKey
      : guideKeyForPath(location.pathname);
  const setGuideKey = useCallback<
    Dispatch<SetStateAction<GoldLabGuideKey>>
  >(
    (nextKey) => {
      setOverride((current) => {
        const currentKey =
          current?.locationKey === location.key
            ? current.guideKey
            : guideKeyForPath(location.pathname);
        return {
          locationKey: location.key,
          guideKey:
            typeof nextKey === "function" ? nextKey(currentKey) : nextKey,
        };
      });
    },
    [location.key, location.pathname],
  );
  const value = useMemo(
    () => ({ guideKey, setGuideKey }),
    [guideKey, setGuideKey],
  );

  return (
    <GoldLabGuideContext.Provider value={value}>
      <GoldLabGuideLayout guideKey={guideKey}>
        <Outlet />
      </GoldLabGuideLayout>
    </GoldLabGuideContext.Provider>
  );
}
