import type { WorkspaceCitation } from "../../api/types";
import { SourcePreview, type PreviewTarget } from "./SourcePreview";
import { snapshotBadge, type AskHistoryEntry } from "./askHistory";

type Props = {
  previewTarget: PreviewTarget | null;
  activeEntry: AskHistoryEntry | null;
  selectedCitation: WorkspaceCitation | null;
  currentSnapshotId: string | null;
};

export function EvidencePanel({
  previewTarget,
  activeEntry,
  selectedCitation,
  currentSnapshotId,
}: Props) {
  const badge =
    activeEntry != null
      ? snapshotBadge(activeEntry.response.snapshot_id, currentSnapshotId)
      : null;

  return (
    <section className="evidence-panel stack" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">Evidence</h2>
      <SourcePreview target={previewTarget} />
      {selectedCitation || activeEntry ? (
        <details className="provenance-disclosure">
          <summary>Provenance</summary>
          <dl className="provenance-list">
            {activeEntry ? (
              <>
                <div>
                  <dt>Snapshot status</dt>
                  <dd>
                    {badge === "current"
                      ? "Current snapshot"
                      : "Historical snapshot"}
                  </dd>
                </div>
                <div>
                  <dt>Snapshot ID</dt>
                  <dd>{activeEntry.response.snapshot_id}</dd>
                </div>
                <div>
                  <dt>Workspace revision</dt>
                  <dd>{activeEntry.response.workspace_revision}</dd>
                </div>
                <div>
                  <dt>Trace ID</dt>
                  <dd>{activeEntry.response.trace_id}</dd>
                </div>
              </>
            ) : null}
            {selectedCitation ? (
              <>
                <div>
                  <dt>Source version</dt>
                  <dd>{selectedCitation.source_version}</dd>
                </div>
                <div>
                  <dt>Evidence unit ID</dt>
                  <dd>{selectedCitation.evidence_unit_id}</dd>
                </div>
                {selectedCitation.section_path?.length ? (
                  <div>
                    <dt>Section path</dt>
                    <dd>{selectedCitation.section_path.join(" / ")}</dd>
                  </div>
                ) : null}
                {selectedCitation.page_start != null ? (
                  <div>
                    <dt>Page range</dt>
                    <dd>
                      {selectedCitation.page_start}
                      {selectedCitation.page_end != null &&
                      selectedCitation.page_end !== selectedCitation.page_start
                        ? `–${selectedCitation.page_end}`
                        : ""}
                    </dd>
                  </div>
                ) : null}
                {selectedCitation.line_start != null ? (
                  <div>
                    <dt>Line range</dt>
                    <dd>
                      {selectedCitation.line_start}
                      {selectedCitation.line_end != null &&
                      selectedCitation.line_end !== selectedCitation.line_start
                        ? `–${selectedCitation.line_end}`
                        : ""}
                    </dd>
                  </div>
                ) : null}
                {selectedCitation.clipped ? (
                  <div>
                    <dt>Clipped</dt>
                    <dd>Yes</dd>
                  </div>
                ) : null}
              </>
            ) : null}
          </dl>
        </details>
      ) : null}
    </section>
  );
}
