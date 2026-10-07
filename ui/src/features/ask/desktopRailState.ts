/** Session-local desktop rail preference (A3-D06). UI state only. */

export type DesktopRailState = {
  sourcesExpanded: boolean;
  evidenceExpanded: boolean;
};

const KEY = "seneca.workspace-rails.v1";

const DEFAULT_STATE: DesktopRailState = {
  sourcesExpanded: true,
  evidenceExpanded: true,
};

export function loadDesktopRailState(): DesktopRailState {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_STATE };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return { ...DEFAULT_STATE };
    const row = parsed as Record<string, unknown>;
    return {
      sourcesExpanded: row.sourcesExpanded !== false,
      evidenceExpanded: row.evidenceExpanded !== false,
    };
  } catch {
    return { ...DEFAULT_STATE };
  }
}

export function saveDesktopRailState(state: DesktopRailState): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // sessionStorage may be unavailable; in-memory state still applies.
  }
}
