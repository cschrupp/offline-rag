import { Link } from "react-router-dom";
import { Card } from "../components/Card";

export function NotFoundPage() {
  return (
    <Card>
      <h1>Page not found</h1>
      <p className="muted">
        This Seneca page is not available. Check the address or return to
        Overview.
      </p>
      <p>
        <Link to="/">Return to Overview</Link>
        {" · "}
        <Link to="/workspaces">Open Workspaces</Link>
      </p>
    </Card>
  );
}
