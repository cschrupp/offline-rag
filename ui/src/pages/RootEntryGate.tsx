import { Navigate } from "react-router-dom";
import { WELCOME_SESSION_KEY } from "../product/identity";
import { OverviewPage } from "./OverviewPage";

function welcomeAlreadyShown(): boolean {
  try {
    return sessionStorage.getItem(WELCOME_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

/** First-open gate for `/` only. Deep links never enter this component. */
export function RootEntryGate() {
  if (!welcomeAlreadyShown()) {
    return <Navigate to="/welcome" replace />;
  }
  return <OverviewPage />;
}
