/**
 * Fail-closed gate for Presentation Review detail authenticity (16N-A).
 * List filters alone are insufficient: detail may race to completed/inactive.
 */

export type PreviewEligibilityDetail = {
  active: boolean;
  state: string;
};

export function isPreviewableTaskDetail(
  detail: PreviewEligibilityDetail,
): boolean {
  return detail.active === true && detail.state === "pending";
}
