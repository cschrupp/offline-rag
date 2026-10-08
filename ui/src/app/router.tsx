import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { EngineeringArchitecturePage } from "../pages/EngineeringArchitecturePage";
import { EngineeringEvaluationPage } from "../pages/EngineeringEvaluationPage";
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
