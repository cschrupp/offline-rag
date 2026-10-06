import { Link } from "react-router-dom";
import { Card } from "../components/Card";

export function NotFoundPage() {
  return (
    <Card>
      <h1>Page not found</h1>
      <p className="muted">
        This OfflineRAG screen is not available. Ask, Evidence, and Training Mode
        are not part of this release surface.
      </p>
      <p>
        <Link to="/">Return to Overview</Link>
        {" · "}
        <Link to="/workspaces">Open Workspaces</Link>
      </p>
    </Card>
  );
}
