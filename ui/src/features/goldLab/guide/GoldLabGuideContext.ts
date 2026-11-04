import {
  createContext,
  useContext,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

export type GoldLabGuideKey =
  | "quick_play_ready"
  | "quick_play_loading"
  | "quick_play_generating"
  | "quick_play_error"
  | "quick_play_empty"
  | "quick_play_playable"
  | "quick_play_complete"
  | "question_check_active"
  | "question_check_saving"
  | "question_check_saved"
  | "rapid_fire_active"
  | "rapid_fire_saving"
  | "rapid_fire_saved"
  | "session_preparing"
  | "session_error"
  | "session_complete"
  | "session_closed"
  | "advanced_home"
  | "project"
  | "campaign"
  | "presentation_review"
  | "contribution"
  | "calibration"
  | "training"
  | "training_scenario"
  | "unavailable_game";

type GuideContextValue = {
  guideKey: GoldLabGuideKey;
  setGuideKey: Dispatch<SetStateAction<GoldLabGuideKey>>;
  quickPlayContribution: ReactNode;
  setQuickPlayContribution: Dispatch<SetStateAction<ReactNode>>;
};

const NOOP_GUIDE_CONTEXT: GuideContextValue = {
  guideKey: "advanced_home",
  setGuideKey: () => undefined,
  quickPlayContribution: null,
  setQuickPlayContribution: () => undefined,
};

export const GoldLabGuideContext = createContext<GuideContextValue | null>(null);

export function useGoldLabGuide(): GuideContextValue {
  return useContext(GoldLabGuideContext) ?? NOOP_GUIDE_CONTEXT;
}
