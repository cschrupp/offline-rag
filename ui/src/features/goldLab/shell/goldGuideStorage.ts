export const GOLD_GUIDE_DISMISSED_KEY = "seneca-gold-guide-dismissed-v1";

export function isGoldGuideDismissed(): boolean {
  try {
    return sessionStorage.getItem(GOLD_GUIDE_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setGoldGuideDismissed(dismissed: boolean): void {
  try {
    if (dismissed) {
      sessionStorage.setItem(GOLD_GUIDE_DISMISSED_KEY, "1");
    } else {
      sessionStorage.removeItem(GOLD_GUIDE_DISMISSED_KEY);
    }
  } catch {
    // sessionStorage may be unavailable; Guide still works in-memory
  }
}
