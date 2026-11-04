import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import {
  GoldLabGuideLayout,
  GoldLabGuideRoute,
} from "../features/goldLab/guide/GoldLabGuide";
import { useGoldLabGuide, type GoldLabGuideKey } from "../features/goldLab/guide/GoldLabGuideContext";

afterEach(() => cleanup());

function GuideRouteProbe() {
  const { setGuideKey } = useGoldLabGuide();
  return (
    <div>
      <button onClick={() => setGuideKey("question_check_active")}>
        Open Question Check
      </button>
      <Link to="/gold-lab/campaigns/c2">Open another campaign</Link>
    </div>
  );
}

describe("BETA-GAME-02 contextual guide", () => {
  it("renders the Question Check guidance in an accessible complementary rail", () => {
    render(
      <GoldLabGuideLayout guideKey="question_check_active">
        <p>Task content</p>
      </GoldLabGuideLayout>,
    );

    const rail = screen.getByRole("complementary", { name: "How to play" });
    expect(
      within(rail).getByText(
        "Decide whether this proposed question is clear and supported by its displayed source.",
      ),
    ).toBeInTheDocument();
    expect(
      within(rail).getByText("You are evaluating the question, not answering it."),
    ).toBeInTheDocument();
    expect(screen.getByText("Task content")).toBeInTheDocument();
  });

  it("explains the distinct Rapid Fire 0/1/2 scale without giving an answer key", () => {
    render(
      <GoldLabGuideLayout guideKey="rapid_fire_active">
        <p>Candidate passage</p>
      </GoldLabGuideLayout>,
    );

    const rail = screen.getByRole("complementary", { name: "How to play" });
    expect(within(rail).getByText(/0 — Irrelevant/)).toBeInTheDocument();
    expect(within(rail).getByText(/1 — Supporting evidence/)).toBeInTheDocument();
    expect(within(rail).getByText(/2 — Direct evidence/)).toBeInTheDocument();
    expect(within(rail).getByText(/background context may support/)).toBeInTheDocument();
    expect(within(rail).queryByText(/correct answer/i)).not.toBeInTheDocument();
  });

  it("uses a native mobile disclosure and keeps route-state guidance current", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/gold-lab/campaigns/c1/work"]}>
        <Routes>
          <Route element={<GoldLabGuideRoute />}>
            <Route
              path="gold-lab/campaigns/:campaignId/work"
              element={<GuideRouteProbe />}
            />
            <Route
              path="gold-lab/campaigns/:campaignId"
              element={<GuideRouteProbe />}
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getAllByText("Seneca is loading the next eligible task for this game."),
    ).toHaveLength(2);
    const disclosure = screen.getByText("How to play / What do I do here?");
    await user.click(disclosure);
    expect(disclosure.closest("details")).toHaveAttribute("open");

    await user.click(screen.getByRole("button", { name: "Open Question Check" }));
    expect(
      screen.getAllByText(
        "Decide whether this proposed question is clear and supported by its displayed source.",
      ),
    ).toHaveLength(2);
    await user.click(screen.getByRole("link", { name: "Open another campaign" }));
    expect(
      screen.getAllByText(
        "A campaign groups expert review work against a fixed baseline.",
      ),
    ).toHaveLength(2);
  });

  it.each([
    ["/gold-lab", "Create a small activity deck from this workspace’s published sources."],
    ["/gold-lab/advanced", "Advanced Gold Lab manages projects, baselines, and campaigns."],
    ["/gold-lab/projects/p1", "A project organizes Gold campaigns for one workspace."],
    ["/gold-lab/campaigns/c1", "A campaign groups expert review work against a fixed baseline."],
    ["/gold-lab/campaigns/c1/presentation-review", "Inspect how a candidate presentation displays a task and its source."],
    ["/gold-lab/campaigns/c1/contribution", "Review contribution summaries for this campaign."],
    ["/gold-lab/campaigns/c1/calibration", "Inspect a registered dataset using local calibration evidence."],
    ["/gold-lab/campaigns/c1/training", "Practice with an immutable registered training dataset."],
    ["/gold-lab/campaigns/c1/training/scenario", "Work through a practice scenario from a registered dataset."],
    ["/gold-lab/campaigns/c1/work", "Seneca is loading the next eligible task for this game."],
  ])("selects route-specific help for %s", (path, goal) => {
    const { unmount } = render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<GoldLabGuideRoute />}>
            <Route path="*" element={<p>Route page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getAllByText(goal)).toHaveLength(2);
    unmount();
  });

  it("provides explanatory content for every Gold Lab route and task state", () => {
    const keys: GoldLabGuideKey[] = [
      "quick_play_ready",
      "quick_play_loading",
      "quick_play_generating",
      "quick_play_error",
      "quick_play_empty",
      "quick_play_playable",
      "quick_play_complete",
      "question_check_active",
      "question_check_saving",
      "question_check_saved",
      "rapid_fire_active",
      "rapid_fire_saving",
      "rapid_fire_saved",
      "session_preparing",
      "session_error",
      "session_complete",
      "session_closed",
      "advanced_home",
      "project",
      "campaign",
      "presentation_review",
      "contribution",
      "calibration",
      "training",
      "training_scenario",
      "unavailable_game",
    ];

    for (const guideKey of keys) {
      const { unmount } = render(
        <GoldLabGuideLayout guideKey={guideKey}>
          <p>Page content</p>
        </GoldLabGuideLayout>,
      );
      expect(
        screen.getByRole("complementary", { name: "How to play" }),
      ).toBeInTheDocument();
      unmount();
    }
  });
});
