export const ENGINEERING_EVIDENCE_MANIFEST_PATH =
  "/evidence/engineering-evidence-v1.json";

export const MANIFEST_CONTRACT = "seneca-engineering-evidence-manifest-v1";

export type MetricAvailability =
  | "measured"
  | "unavailable"
  | "unevaluable"
  | "not_applicable";

export type Metric = {
  availability: MetricAvailability;
  value: number | null;
  unit?: string;
  value_qualifier?: "exact" | "approximate" | null;
};

export type SourceRef = {
  source_ref_id: string;
  path: string;
  role: string;
  source_kind: string;
  expected_sha256: string;
  actual_sha256: string;
  source_locator?: string;
};

export type EvidenceRecord = {
  evidence_id: string;
  evidence_family: string;
  title: string;
  summary: string;
  evidence_authority: string;
  promotion_status: string;
  claim_scope: string;
  caveats: string[];
  source_refs: SourceRef[];
  provenance: {
    evidence_family: string;
    fields: Record<string, unknown>;
  };
  presentation: Record<string, unknown>;
};

export type EngineeringEvidenceManifest = {
  contract: string;
  version: number;
  manifest_id: string;
  records: EvidenceRecord[];
};

export function isMetric(value: unknown): value is Metric {
  if (!value || typeof value !== "object") return false;
  const m = value as Metric;
  return (
    typeof m.availability === "string" &&
    (m.value === null || typeof m.value === "number")
  );
}
