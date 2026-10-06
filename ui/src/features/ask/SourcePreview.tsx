import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { getSourceVersionContent } from "../../api/client";
import { userFacingErrorMessage } from "../../api/errors";
import { queryKeys } from "../../api/queryKeys";
import type { Source, WorkspaceCitation } from "../../api/types";
import { snapshotBadge } from "./askHistory";
import {
  buildTextLineWindow,
  isPdfContentType,
  isTextPreviewContentType,
  isUnsafePreviewContentType,
} from "./previewText";

export type PreviewTarget =
  | {
      kind: "citation";
      workspaceId: string;
      citation: WorkspaceCitation;
      workspaceRevision: number;
      querySnapshotId: string;
    }
  | {
      kind: "source";
      workspaceId: string;
      sourceId: string;
    };

type Props = {
  target: PreviewTarget | null;
  currentSnapshotId: string | null;
  currentSources: Source[];
  currentWorkspaceRevision: number;
};

export function SourcePreview({
  target,
  currentSnapshotId,
  currentSources,
  currentWorkspaceRevision,
}: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [decodedText, setDecodedText] = useState<string | null>(null);

  const liveSource =
    target?.kind === "source"
      ? (currentSources.find((source) => source.source_id === target.sourceId) ??
        null)
      : null;

  const fetchParams =
    target == null
      ? null
      : target.kind === "citation"
        ? {
            workspaceId: target.workspaceId,
            sourceId: target.citation.source_id,
            version: target.citation.source_version,
            workspaceRevision: target.workspaceRevision,
          }
        : liveSource
          ? {
              workspaceId: target.workspaceId,
              sourceId: liveSource.source_id,
              version: liveSource.version,
              workspaceRevision: currentWorkspaceRevision,
            }
          : null;

  const contentQuery = useQuery({
    queryKey: fetchParams
      ? queryKeys.sourceVersionContent(fetchParams)
      : ["source-version-content", "idle"],
    queryFn: ({ signal }) =>
      getSourceVersionContent({
        ...fetchParams!,
        signal,
      }),
    enabled: Boolean(fetchParams),
  });

  useEffect(() => {
    if (!contentQuery.data) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- revoke/replace blob URL for lazy preview
      setObjectUrl(null);
      setDecodedText(null);
      return;
    }
    const url = URL.createObjectURL(contentQuery.data.blob);
    setObjectUrl(url);

    let cancelled = false;
    const contentType = contentQuery.data.contentType;
    if (
      !isUnsafePreviewContentType(contentType) &&
      isTextPreviewContentType(contentType) &&
      !isPdfContentType(contentType)
    ) {
      void contentQuery.data.blob.text().then((text) => {
        if (!cancelled) setDecodedText(text);
      });
    } else {
      setDecodedText(null);
    }

    return () => {
      cancelled = true;
      URL.revokeObjectURL(url);
    };
  }, [contentQuery.data]);

  const lineWindow = useMemo(() => {
    if (decodedText == null || !target) return null;
    if (target.kind === "citation") {
      return buildTextLineWindow(
        decodedText,
        target.citation.line_start,
        target.citation.line_end,
      );
    }
    return buildTextLineWindow(decodedText, null, null);
  }, [decodedText, target]);

  if (!target) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        Ask a question or choose a source to inspect its evidence.
      </p>
    );
  }

  if (target.kind === "source" && !liveSource) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        Ask a question or choose a source to inspect its evidence.
      </p>
    );
  }

  const title =
    target.kind === "citation"
      ? target.citation.source_display_name
      : liveSource!.display_name;
  const version =
    target.kind === "citation"
      ? target.citation.source_version
      : liveSource!.version;
  const pageStart =
    target.kind === "citation" ? target.citation.page_start : null;
  const contentType = contentQuery.data?.contentType ?? "";
  const showUnsupported =
    Boolean(contentQuery.data) &&
    (isUnsafePreviewContentType(contentType) ||
      (!isPdfContentType(contentType) && !isTextPreviewContentType(contentType)));

  const historical =
    target.kind === "citation"
      ? snapshotBadge(target.querySnapshotId, currentSnapshotId) === "historical"
      : false;

  return (
    <div className="stack source-preview">
      <div className="stack" style={{ gap: "0.35rem" }}>
        <h3 className="evidence-source-title">{title}</h3>
        <p className="muted" style={{ margin: 0 }}>
          Version {version}
          {pageStart != null ? ` · page ${pageStart}` : ""}
        </p>
        <span
          className={
            historical
              ? "snapshot-badge snapshot-badge-historical"
              : "snapshot-badge snapshot-badge-current"
          }
        >
          {historical ? "Historical snapshot" : "Current snapshot"}
        </span>
      </div>

      {contentQuery.isLoading ? (
        <p className="muted" aria-live="polite">
          Loading source preview…
        </p>
      ) : null}
      {contentQuery.isError ? (
        <p className="error-box" role="alert">
          {userFacingErrorMessage(contentQuery.error)}
        </p>
      ) : null}

      {contentQuery.data && isPdfContentType(contentType) && objectUrl ? (
        <iframe
          title={`PDF preview for ${title}`}
          className="pdf-preview-frame"
          src={
            pageStart != null && pageStart >= 1
              ? `${objectUrl}#page=${pageStart}`
              : objectUrl
          }
        />
      ) : null}

      {contentQuery.data &&
      !isUnsafePreviewContentType(contentType) &&
      isTextPreviewContentType(contentType) &&
      !isPdfContentType(contentType) &&
      lineWindow ? (
        <div className="text-preview">
          {!lineWindow.hasExactLocation ? (
            <p className="muted">No exact line location</p>
          ) : null}
          <pre className="text-preview-pre" tabIndex={0}>
            {lineWindow.lines.map((line) => (
              <div
                key={line.lineNumber}
                className={
                  line.cited
                    ? "text-preview-line text-preview-line-cited"
                    : "text-preview-line"
                }
              >
                <span className="text-preview-gutter" aria-hidden="true">
                  {line.lineNumber}
                </span>
                <span>{line.text || " "}</span>
              </div>
            ))}
          </pre>
        </div>
      ) : null}

      {showUnsupported ? (
        <p className="muted" role="status">
          Preview is not available for this source format.
        </p>
      ) : null}
    </div>
  );
}
