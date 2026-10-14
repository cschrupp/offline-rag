import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { EngineeringArchitecturePage } from "../pages/EngineeringArchitecturePage";
import { EngineeringEvaluationPage } from "../pages/EngineeringEvaluationPage";
import { GoldLabCalibrationPage } from "../pages/GoldLabCalibrationPage";
import { GoldLabCampaignPage } from "../pages/GoldLabCampaignPage";
import { GoldLabContributionPage } from "../pages/GoldLabContributionPage";
import { GoldLabPage } from "../pages/GoldLabPage";
import { GoldLabPresentationReviewPage } from "../pages/GoldLabPresentationReviewPage";
import { GoldLabProjectPage } from "../pages/GoldLabProjectPage";
import { GoldLabTrainingPage } from "../pages/GoldLabTrainingPage";
import { GoldLabTrainingScenarioPage } from "../pages/GoldLabTrainingScenarioPage";
import { GoldLabWorkPage } from "../pages/GoldLabWorkPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { RootEntryGate } from "../pages/RootEntryGate";
import { SettingsPage } from "../pages/SettingsPage";
import { WelcomePage } from "../pages/WelcomePage";
import { WorkspaceLibraryPage } from "../pages/WorkspaceLibraryPage";
import { WorkspacePage } from "../pages/WorkspacePage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/welcome" element={<WelcomePage />} />
      <Route element={<AppShell />}>
        <Route index element={<RootEntryGate />} />
        <Route path="workspaces" element={<WorkspaceLibraryPage />} />
        <Route path="workspaces/:workspaceId" element={<WorkspacePage />} />
        <Route path="gold-lab" element={<GoldLabPage />} />
        <Route
          path="gold-lab/projects/:projectId"
          element={<GoldLabProjectPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId"
          element={<GoldLabCampaignPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/work"
          element={<GoldLabWorkPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/presentation-review"
          element={<GoldLabPresentationReviewPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/contribution"
          element={<GoldLabContributionPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/calibration"
          element={<GoldLabCalibrationPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/training"
          element={<GoldLabTrainingPage />}
        />
        <Route
          path="gold-lab/campaigns/:campaignId/training/scenario"
          element={<GoldLabTrainingScenarioPage />}
        />
        <Route
          path="engineering"
          element={<Navigate to="/engineering/evaluation" replace />}
        />
        <Route
          path="engineering/evaluation"
          element={<EngineeringEvaluationPage />}
        />
        <Route
          path="engineering/architecture"
          element={<EngineeringArchitecturePage />}
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
