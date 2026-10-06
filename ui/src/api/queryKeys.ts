export const queryKeys = {
  healthReady: ["health", "ready"] as const,
  capabilities: ["capabilities"] as const,
  generationSettings: ["settings", "generation"] as const,
  workspaces: ["workspaces"] as const,
  workspace: (workspaceId: string) => ["workspace", workspaceId] as const,
  workspaceSources: (workspaceId: string) =>
    ["workspace", workspaceId, "sources"] as const,
  operation: (operationId: string) => ["operation", operationId] as const,
  sourceVersionContent: (params: {
    workspaceId: string;
    sourceId: string;
    version: number;
    workspaceRevision: number;
  }) =>
    [
      "source-version-content",
      params.workspaceId,
      params.sourceId,
      params.version,
      params.workspaceRevision,
    ] as const,
};
