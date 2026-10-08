import {
  ENGINEERING_EVIDENCE_MANIFEST_PATH,
  MANIFEST_CONTRACT,
  type EngineeringEvidenceManifest,
  type EvidenceRecord,
} from "./evidenceTypes";

export class EvidenceManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvidenceManifestError";
  }
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new EvidenceManifestError(`Invalid manifest: ${label}`);
  }
  return value;
}

function validateRecord(raw: unknown, index: number): EvidenceRecord {
  if (!raw || typeof raw !== "object") {
    throw new EvidenceManifestError(`Invalid manifest: records[${index}]`);
  }
  const row = raw as Record<string, unknown>;
  const evidenceId = requireString(row.evidence_id, `records[${index}].evidence_id`);
  if (!Array.isArray(row.caveats) || !Array.isArray(row.source_refs)) {
    throw new EvidenceManifestError(`Invalid manifest: ${evidenceId} arrays`);
  }
  if (!row.provenance || typeof row.provenance !== "object") {
    throw new EvidenceManifestError(`Invalid manifest: ${evidenceId} provenance`);
  }
  if (!row.presentation || typeof row.presentation !== "object") {
    throw new EvidenceManifestError(`Invalid manifest: ${evidenceId} presentation`);
  }
  return row as EvidenceRecord;
}

export function validateEngineeringEvidenceManifest(
  raw: unknown,
): EngineeringEvidenceManifest {
  if (!raw || typeof raw !== "object") {
    throw new EvidenceManifestError("Invalid manifest: root");
  }
  const obj = raw as Record<string, unknown>;
  if (obj.contract !== MANIFEST_CONTRACT) {
    throw new EvidenceManifestError("Invalid manifest: contract");
  }
  if (obj.version !== 1) {
    throw new EvidenceManifestError("Invalid manifest: version");
  }
  requireString(obj.manifest_id, "manifest_id");
  if (!Array.isArray(obj.records)) {
    throw new EvidenceManifestError("Invalid manifest: records");
  }
  const records = obj.records.map((row, index) => validateRecord(row, index));
  return {
    contract: MANIFEST_CONTRACT,
    version: 1,
    manifest_id: String(obj.manifest_id),
    records,
  };
}

export async function fetchEngineeringEvidenceManifest(
  signal?: AbortSignal,
): Promise<EngineeringEvidenceManifest> {
  const response = await fetch(ENGINEERING_EVIDENCE_MANIFEST_PATH, {
    method: "GET",
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new EvidenceManifestError(
      `Engineering evidence is unavailable (${response.status}).`,
    );
  }
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw new EvidenceManifestError("Invalid manifest: JSON parse failed");
  }
  return validateEngineeringEvidenceManifest(raw);
}

export function recordById(
  manifest: EngineeringEvidenceManifest,
  evidenceId: string,
): EvidenceRecord | undefined {
  return manifest.records.find((row) => row.evidence_id === evidenceId);
}
