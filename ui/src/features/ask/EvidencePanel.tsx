import type { Source, WorkspaceCitation } from "../../api/types";
import { SourcePreview, type PreviewTarget } from "./SourcePreview";
import {
  snapshotBadge,
  type ConversationHistoryEntry,
} from "./conversationState";

type Props = {
  previewTarget: PreviewTarget | null;
  activeEntry: ConversationHistoryEntry | null;
  selectedCitation: WorkspaceCitation | null;
  currentSnapshotId: string | null;
  currentSources: Source[];
  currentWorkspaceRevision: number;
  /** Training Mode: omit source excerpts / evidence-bearing provenance. */
  evidenceHidden?: boolean;
};

export function EvidencePanel({
  previewTarget,
  activeEntry,
  selectedCitation,
  currentSnapshotId,
  currentSources,
  currentWorkspaceRevision,
  evidenceHidden = false,
}: Props) {
  const isSourcePreview = previewTarget?.kind === "source";
  const isCitationPreview = previewTarget?.kind === "citation";
  const liveSource =
    isSourcePreview && previewTarget
      ? (currentSources.find(
          (source) => source.source_id === previewTarget.sourceId,
        ) ?? null)
      : null;

  const queryBadge =
    activeEntry != null
      ? snapshotBadge(activeEntry.response.snapshot_id, currentSnapshotId)
      : null;

  // Query provenance belongs to citation / answer evidence only — never under
  // an unrelated current-source inspection.
  const showQueryProvenance =
    !evidenceHidden &&
    (isCitationPreview || previewTarget == null) &&
    activeEntry != null;
  const showCitationDetails =
    !evidenceHidden && isCitationPreview && selectedCitation != null;
  const showSourceProvenance =
    !evidenceHidden && isSourcePreview && liveSource != null;
  const showProvenance =
    showQueryProvenance || showCitationDetails || showSourceProvenance;

  return (
    <section className="evidence-panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" style={{ margin: 0, flexShrink: 0 }}>
        Evidence
      </h2>
      <div className="evidence-scroll">
        {evidenceHidden ? (
          <div className="training-evidence-hidden" role="status">
            <p style={{ margin: 0 }}>Evidence hidden</p>
            <p className="muted" style={{ margin: 0 }}>
              Reveal evidence from Training Mode controls, or activate a
              revealed citation to inspect the exact source.
            </p>
          </div>
        ) : (
          <SourcePreview
            target={previewTarget}
            currentSnapshotId={currentSnapshotId}
            currentSources={currentSources}
            currentWorkspaceRevision={currentWorkspaceRevision}
          />
        )}
        {showProvenance ? (
          <details className="provenance-disclosure">
            <summary>Provenance</summary>
            <dl className="provenance-list">
              {showSourceProvenance && liveSource ? (
                <>
                  <div>
                    <dt>Snapshot status</dt>
                    <dd>Current snapshot</dd>
                  </div>
                  <div>
                    <dt>Source version</dt>
                    <dd>{liveSource.version}</dd>
                  </div>
                  <div>
                    <dt>Workspace revision</dt>
                    <dd>{currentWorkspaceRevision}</dd>
                  </div>
                </>
              ) : null}
              {showQueryProvenance && activeEntry ? (
                <>
                  <div>
                    <dt>Snapshot status</dt>
                    <dd>
                      {queryBadge === "current"
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
                    <dt>Conversation trace ID</dt>
                    <dd>{activeEntry.response.conversation_trace_id}</dd>
                  </div>
                  {activeEntry.response.query_trace_id != null ? (
                    <div>
                      <dt>Query trace ID</dt>
                      <dd>{activeEntry.response.query_trace_id}</dd>
                    </div>
                  ) : (
                    <div>
                      <dt>Query trace ID</dt>
                      <dd>None (no scientific query for this turn)</dd>
                    </div>
                  )}
                </>
              ) : null}
              {showCitationDetails && selectedCitation ? (
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
                        selectedCitation.page_end !==
                          selectedCitation.page_start
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
                        selectedCitation.line_end !==
                          selectedCitation.line_start
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
      </div>
    </section>
  );
}
