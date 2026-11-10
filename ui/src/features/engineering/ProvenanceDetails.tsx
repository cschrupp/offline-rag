import type { EvidenceRecord } from "./evidenceTypes";

function formatField(value: unknown): string {
  if (value === null || value === undefined) {
    return "Unavailable in committed accepted evidence";
  }
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "Unavailable in committed accepted evidence";
  }
}

type Props = {
  record: EvidenceRecord;
  manifestId?: string;
};

export function ProvenanceDetails({ record, manifestId }: Props) {
  const fields = record.provenance.fields ?? {};
  const entries = Object.entries(fields).filter(([, value]) => value !== undefined);

  return (
    <details className="engineering-provenance">
      <summary>View provenance</summary>
      <div className="stack" style={{ gap: "0.75rem", marginTop: "0.75rem" }}>
        {manifestId ? (
          <p style={{ margin: 0 }}>
            <strong>Manifest ID.</strong> <code>{manifestId}</code>
          </p>
        ) : null}
        <dl className="engineering-provenance-dl">
          <div><dt>Evidence authority</dt><dd>{record.evidence_authority}</dd></div>
          <div><dt>Currency</dt><dd>{record.currency}</dd></div>
          <div><dt>Product/config promotion</dt><dd>{record.promotion_status}</dd></div>
          <div><dt>Decision effect</dt><dd>{record.decision_effect}</dd></div>
        </dl>
        {Object.keys(record.currency_overrides).length > 0 ? (
          <dl className="engineering-provenance-dl">
            {Object.entries(record.currency_overrides).map(([key, currency]) => (
              <div key={key}><dt>{key} currency</dt><dd>{currency}</dd></div>
            ))}
          </dl>
        ) : null}
        <p style={{ margin: 0 }}>
          <strong>Claim scope.</strong> {record.claim_scope}
        </p>
        {entries.length > 0 ? (
          <dl className="engineering-provenance-dl">
            {entries.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  <code>{formatField(value)}</code>
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            No typed provenance fields in this record.
          </p>
        )}
        <div>
          <h4 style={{ margin: "0 0 0.35rem" }}>Source references</h4>
          <ul className="engineering-source-list">
            {record.source_refs.map((ref) => (
              <li key={ref.source_ref_id}>
                <div>
                  <code>{ref.path}</code>
                </div>
                <div className="muted">
                  {ref.source_ref_id} · {ref.role} · {ref.source_kind}
                </div>
                {ref.source_locator ? (
                  <div className="muted">Locator: {ref.source_locator}</div>
                ) : null}
                <div className="muted">
                  SHA-256: <code>{ref.actual_sha256}</code>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <details>
          <summary>Exact presentation values</summary>
          <pre className="engineering-exact-presentation">
            {JSON.stringify(record.presentation, null, 2)}
          </pre>
        </details>
      </div>
    </details>
  );
}
