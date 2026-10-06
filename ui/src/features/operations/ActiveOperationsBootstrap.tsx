import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { getOperation } from "../../api/client";
import { userFacingErrorMessage } from "../../api/errors";
import { queryKeys } from "../../api/queryKeys";
import type { Operation } from "../../api/types";
import { OperationProgress } from "../../components/OperationProgress";
import {
  ACTIVE_OPERATIONS_KEY,
  forgetActiveOperation,
  isTerminalOperationStatus,
  loadActiveOperations,
  type ActiveOperationRef,
} from "./activeOperations";

type SurfacedItem = {
  ref: ActiveOperationRef;
};

/**
 * Reloads remembered operation locators and surfaces their server status.
 * localStorage is only a locator — the server remains authoritative.
 */
export function ActiveOperationsBootstrap() {
  const [items, setItems] = useState<SurfacedItem[]>(() =>
    loadActiveOperations().map((ref) => ({ ref })),
  );

  useEffect(() => {
    const sync = () => {
      setItems((current) => mergeRefs(current, loadActiveOperations()));
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === ACTIVE_OPERATIONS_KEY) sync();
    };
    window.addEventListener("storage", onStorage);
    const timer = window.setInterval(sync, 1000);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.clearInterval(timer);
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <aside
      className="operation-tray"
      aria-label="Workspace operations"
      data-testid="operation-tray"
    >
      <div className="operation-tray-inner stack">
        <h2 className="sr-only">Workspace operations</h2>
        {items.map((item) => (
          <ResumedOperationCard
            key={item.ref.operation_id}
            refItem={item.ref}
            onDismiss={() => {
              forgetActiveOperation(item.ref.operation_id);
              setItems((current) =>
                current.filter(
                  (entry) => entry.ref.operation_id !== item.ref.operation_id,
                ),
              );
            }}
            onTerminalSurfaced={() => {
              forgetActiveOperation(item.ref.operation_id);
            }}
          />
        ))}
      </div>
    </aside>
  );
}

function mergeRefs(
  current: SurfacedItem[],
  stored: ActiveOperationRef[],
): SurfacedItem[] {
  const byId = new Map(current.map((item) => [item.ref.operation_id, item]));
  for (const ref of stored) {
    if (!byId.has(ref.operation_id)) {
      byId.set(ref.operation_id, { ref });
    }
  }
  return Array.from(byId.values());
}

function ResumedOperationCard({
  refItem,
  onDismiss,
  onTerminalSurfaced,
}: {
  refItem: ActiveOperationRef;
  onDismiss: () => void;
  onTerminalSurfaced: () => void;
}) {
  const queryClient = useQueryClient();
  const handledTerminal = useRef(false);
  const onTerminalRef = useRef(onTerminalSurfaced);

  useEffect(() => {
    onTerminalRef.current = onTerminalSurfaced;
  }, [onTerminalSurfaced]);

  const query = useQuery({
    queryKey: queryKeys.operation(refItem.operation_id),
    queryFn: ({ signal }) => getOperation(refItem.operation_id, signal),
    retry: false,
    refetchInterval: (q) => {
      if (q.state.error) return false;
      const status = q.state.data?.status;
      if (status && isTerminalOperationStatus(String(status))) return false;
      return 1000;
    },
  });

  useEffect(() => {
    const operation = query.data;
    if (!operation || handledTerminal.current) return;
    if (!isTerminalOperationStatus(String(operation.status))) return;
    handledTerminal.current = true;
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspace(refItem.workspace_id),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources(refItem.workspace_id),
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
    onTerminalRef.current();
  }, [query.data, queryClient, refItem.workspace_id]);

  if (query.isError) {
    return (
      <OperationProgress
        phase="lookup_error"
        label={refItem.label ?? operationKindLabel(refItem.kind)}
        lookupError={userFacingErrorMessage(query.error)}
        onDismiss={onDismiss}
      />
    );
  }

  const operation = query.data as Operation | undefined;
  if (!operation) {
    return (
      <div className="card" aria-live="polite">
        <p className="muted">
          Reconnecting to {refItem.label ?? operationKindLabel(refItem.kind)}…
        </p>
      </div>
    );
  }

  return (
    <OperationProgress
      phase="operation"
      operation={operation}
      label={refItem.label ?? operationKindLabel(refItem.kind)}
      onDismiss={
        isTerminalOperationStatus(String(operation.status))
          ? onDismiss
          : undefined
      }
    />
  );
}

function operationKindLabel(kind: string): string {
  switch (kind) {
    case "source_add":
      return "Add sources";
    case "source_replace":
      return "Replace source";
    case "source_remove":
      return "Remove source";
    default:
      return "Workspace operation";
  }
}
