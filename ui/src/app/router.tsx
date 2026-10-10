import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { EngineeringArchitecturePage } from "../pages/EngineeringArchitecturePage";
import { EngineeringEvaluationPage } from "../pages/EngineeringEvaluationPage";
import { GoldLabCampaignPage } from "../pages/GoldLabCampaignPage";
import { GoldLabPage } from "../pages/GoldLabPage";
import { GoldLabProjectPage } from "../pages/GoldLabProjectPage";
import { GoldLabWorkPage } from "../pages/GoldLabWorkPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { SettingsPage } from "../pages/SettingsPage";
import { WorkspaceLibraryPage } from "../pages/WorkspaceLibraryPage";
import { WorkspacePage } from "../pages/WorkspacePage";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
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
