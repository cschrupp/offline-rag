import type { Source } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { SourceActionsMenu } from "../../components/SourceActionsMenu";
import { userFacingErrorMessage } from "../../api/errors";
import {
  formatBytes,
  formatMiB,
  type SourceCapacityLimits,
} from "../workspaces/format";
import type { SourceListPhase } from "../workspaces/sourceLoadingState";

type Props = {
  sources: Source[];
  selectedSourceIds: string[];
  limits: SourceCapacityLimits | null;
  capacityLoading: boolean;
  capacityError: boolean;
  sourcePhase: SourceListPhase;
  sourcesError: unknown;
  recordedSourceCount: number;
  usedBytes: number;
  mutationsDisabled: boolean;
  selectionDisabled: boolean;
  onRetrySources: () => void;
  onToggle: (sourceId: string, selected: boolean) => void;
  onSelectAll: () => void;
  onAdd: () => void;
  onPreview: (source: Source) => void;
  onRename: (source: Source) => void;
  onReplace: (source: Source) => void;
  onRemove: (source: Source) => void;
};

export function SourceRail({
  sources,
  selectedSourceIds,
  limits,
  capacityLoading,
  capacityError,
  sourcePhase,
  sourcesError,
  recordedSourceCount,
  usedBytes,
  mutationsDisabled,
  selectionDisabled,
  onRetrySources,
  onToggle,
  onSelectAll,
  onAdd,
  onPreview,
  onRename,
  onReplace,
  onRemove,
}: Props) {
  const selectedCount = selectedSourceIds.length;
  const showRows = sourcePhase === "ready";
  const showSelectionControls = sourcePhase === "ready";

  return (
    <section className="source-rail" aria-labelledby="source-list-heading">
      <div
        className="row"
        style={{ justifyContent: "space-between", flexShrink: 0 }}
      >
        <h2 id="source-list-heading" style={{ margin: 0 }}>
          Sources
        </h2>
        <p className="muted capacity-summary" style={{ margin: 0 }}>
          {sourcePhase === "ready" && limits ? (
            <>
              {sources.length} / {limits.maxActiveSources}
              <br />
              {formatMiB(usedBytes)} / {formatMiB(limits.maxDesiredActiveBytes)}{" "}
              MiB
            </>
          ) : sourcePhase === "ready" ? (
            <>
              {sources.length} sources
              <br />
              {capacityError
                ? "capacity unavailable"
                : capacityLoading
                  ? "loading capacity…"
                  : formatBytes(usedBytes)}
            </>
          ) : sourcePhase === "empty" && limits ? (
            <>
              0 / {limits.maxActiveSources}
              <br />
              0.0 / {formatMiB(limits.maxDesiredActiveBytes)} MiB
            </>
          ) : (
            <>
              {recordedSourceCount} recorded
              <br />
              {sourcePhase === "loading"
                ? "loading details…"
                : sourcePhase === "error"
                  ? "details unavailable"
                  : sourcePhase === "inconsistent"
                    ? "state mismatch"
                    : capacityError
                      ? "capacity unavailable"
                      : "—"}
            </>
          )}
        </p>
      </div>

      <Button onClick={onAdd} disabled={mutationsDisabled}>
        + Add sources
      </Button>

      {sourcePhase === "empty" ? (
        <EmptyState
          title="This workspace is empty"
          body="This workspace is ready for sources but currently contains no active knowledge."
          action={
            <Button onClick={onAdd} disabled={mutationsDisabled}>
              + Add sources
            </Button>
          }
        />
      ) : null}

      {sourcePhase === "loading" ? (
        <p className="muted" role="status">
          Loading source details…
        </p>
      ) : null}

      {sourcePhase === "error" ? (
        <div className="stack" style={{ gap: "0.75rem" }}>
          <p className="error-box" role="alert">
            Source details could not be loaded.
            {sourcesError ? (
              <>
                <br />
                <span className="muted">{userFacingErrorMessage(sourcesError)}</span>
              </>
            ) : null}
          </p>
          <Button type="button" variant="secondary" onClick={onRetrySources}>
            Retry
          </Button>
        </div>
      ) : null}

      {sourcePhase === "inconsistent" ? (
        <p className="error-box" role="alert">
          Inconsistent workspace/source state: this workspace is Active and
          records {recordedSourceCount} source
          {recordedSourceCount === 1 ? "" : "s"}, but the source list returned
          none. Source details are unavailable until this is resolved.
        </p>
      ) : null}

      {showRows ? (
        <ul className="source-list">
          {sources.map((source) => {
            const checked = selectedSourceIds.includes(source.source_id);
            const checkboxId = `source-select-${source.source_id}`;
            return (
              <li key={source.source_id} className="source-row source-row-ask">
                <div className="source-row-select">
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={checked}
                    disabled={selectionDisabled}
                    onChange={(event) =>
                      onToggle(source.source_id, event.target.checked)
                    }
                  />
                  <div className="source-row-main">
                    <button
                      type="button"
                      className="source-name-button"
                      onClick={() => onPreview(source)}
                    >
                      {source.display_name}
                    </button>
                    <label className="sr-only" htmlFor={checkboxId}>
                      Include {source.display_name} in next Ask
                    </label>
                    <span className="muted source-meta">
                      {formatBytes(source.byte_size)} · Version {source.version}
                    </span>
                  </div>
                </div>
                <SourceActionsMenu
                  source={source}
                  disabled={mutationsDisabled}
                  onRename={() => onRename(source)}
                  onReplace={() => onReplace(source)}
                  onRemove={() => onRemove(source)}
                />
              </li>
            );
          })}
        </ul>
      ) : null}

      {showSelectionControls ? (
        <div className="stack" style={{ gap: "0.35rem" }}>
          <p className="muted" style={{ margin: 0 }} aria-live="polite">
            {selectedCount} selected
          </p>
          <Button
            variant="secondary"
            type="button"
            onClick={onSelectAll}
            disabled={selectionDisabled || sources.length === 0}
          >
            Select all
          </Button>
        </div>
      ) : null}
    </section>
  );
}
