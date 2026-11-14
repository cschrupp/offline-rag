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
  if (row.currency !== "current" && row.currency !== "historical") {
    throw new EvidenceManifestError(`Invalid manifest: ${evidenceId}.currency`);
  }
  requireString(row.decision_effect, `${evidenceId}.decision_effect`);
  if (!row.currency_overrides || typeof row.currency_overrides !== "object") {
    throw new EvidenceManifestError(`Invalid manifest: ${evidenceId}.currency_overrides`);
  }
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
  if (obj.version !== 3) {
    throw new EvidenceManifestError("Invalid manifest: version");
  }
  requireString(obj.manifest_id, "manifest_id");
  if (!Array.isArray(obj.records)) {
    throw new EvidenceManifestError("Invalid manifest: records");
  }
  const catalog = obj.metric_catalog as { catalog_id?: string; definitions?: Array<{ definition_id: string; definition_revision: number; display_kind: string; precision: number }> } | undefined;
  if (!catalog?.catalog_id?.startsWith("indicatorcatalog_") || !Array.isArray(catalog.definitions)) {
    throw new EvidenceManifestError("Invalid manifest: indicator catalog");
  }
  const definitions = catalog.definitions;
  function validateBindings(node: unknown): void {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) { node.forEach(validateBindings); return; }
    const value = node as Record<string, unknown>;
    if ("availability" in value && "value" in value) {
      const ref = value.definition_ref as { definition_id?: string; definition_revision?: number } | undefined;
      const definition = definitions.find(d => d.definition_id === ref?.definition_id && d.definition_revision === ref?.definition_revision);
      if (!definition || value.display_kind !== definition.display_kind || value.precision !== definition.precision) {
        throw new EvidenceManifestError("Invalid manifest: indicator binding");
      }
    } else Object.values(value).forEach(validateBindings);
  }
  const records = obj.records.map((row, index) => validateRecord(row, index));
  records.forEach(record => validateBindings(record.presentation));
  return {
    contract: MANIFEST_CONTRACT,
    version: 3,
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
