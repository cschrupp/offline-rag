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

type Props = {
  sources: Source[];
  selectedSourceIds: string[];
  limits: SourceCapacityLimits | null;
  capacityLoading: boolean;
  capacityError: boolean;
  sourcesLoading: boolean;
  sourcesError: unknown;
  usedBytes: number;
  mutationsDisabled: boolean;
  selectionDisabled: boolean;
  isEmpty: boolean;
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
  sourcesLoading,
  sourcesError,
  usedBytes,
  mutationsDisabled,
  selectionDisabled,
  isEmpty,
  onToggle,
  onSelectAll,
  onAdd,
  onPreview,
  onRename,
  onReplace,
  onRemove,
}: Props) {
  const selectedCount = selectedSourceIds.length;

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
          {limits ? (
            <>
              {sources.length} / {limits.maxActiveSources}
              <br />
              {formatMiB(usedBytes)} / {formatMiB(limits.maxDesiredActiveBytes)}{" "}
              MiB
            </>
          ) : (
            <>
              {sources.length} sources
              <br />
              {capacityError
                ? "capacity unavailable"
                : capacityLoading
                  ? "loading capacity…"
                  : formatBytes(usedBytes)}
            </>
          )}
        </p>
      </div>

      <Button onClick={onAdd} disabled={mutationsDisabled}>
        + Add sources
      </Button>

      {isEmpty ? (
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

      {sourcesError ? (
        <p className="error-box" role="alert">
          {userFacingErrorMessage(sourcesError)}
        </p>
      ) : null}
      {sourcesLoading ? <p className="muted">Loading sources…</p> : null}

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

      {!isEmpty ? (
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
