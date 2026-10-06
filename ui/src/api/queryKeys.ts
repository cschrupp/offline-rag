export const queryKeys = {
  healthReady: ["health", "ready"] as const,
  workspaces: ["workspaces"] as const,
  workspace: (workspaceId: string) => ["workspace", workspaceId] as const,
  workspaceSources: (workspaceId: string) =>
    ["workspace", workspaceId, "sources"] as const,
  operation: (operationId: string) => ["operation", operationId] as const,
};
