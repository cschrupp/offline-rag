import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { getOperation } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import {
  forgetActiveOperation,
  isTerminalOperationStatus,
  loadActiveOperations,
  type ActiveOperationRef,
} from "./activeOperations";

/**
 * On startup, reconnect to remembered nonterminal operations.
 * localStorage is only a locator — the server remains authoritative.
 */
export function ActiveOperationsBootstrap() {
  const queryClient = useQueryClient();
  const [refs, setRefs] = useState<ActiveOperationRef[]>(() =>
    loadActiveOperations(),
  );

  return (
    <>
      {refs.map((ref) => (
        <OperationRehydrator
          key={ref.operation_id}
          operationId={ref.operation_id}
          workspaceId={ref.workspace_id}
          onTerminal={() => {
            forgetActiveOperation(ref.operation_id);
            void queryClient.invalidateQueries({
              queryKey: queryKeys.workspace(ref.workspace_id),
            });
            void queryClient.invalidateQueries({
              queryKey: queryKeys.workspaceSources(ref.workspace_id),
            });
            void queryClient.invalidateQueries({
              queryKey: queryKeys.workspaces,
            });
            setRefs(loadActiveOperations());
          }}
        />
      ))}
    </>
  );
}

function OperationRehydrator({
  operationId,
  workspaceId,
  onTerminal,
}: {
  operationId: string;
  workspaceId: string;
  onTerminal: () => void;
}) {
  const settledRef = useRef(false);
  const onTerminalRef = useRef(onTerminal);

  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  const { data } = useQuery({
    queryKey: queryKeys.operation(operationId),
    queryFn: ({ signal }) => getOperation(operationId, signal),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isTerminalOperationStatus(String(status))) {
        return false;
      }
      return 1000;
    },
  });

  useEffect(() => {
    if (!data || settledRef.current) return;
    if (!isTerminalOperationStatus(String(data.status))) return;
    settledRef.current = true;
    onTerminalRef.current();
  }, [data, workspaceId]);

  return null;
}
