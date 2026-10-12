import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { getCapabilities, getOperation } from "../../../api/client";
import { queryKeys } from "../../../api/queryKeys";
import type { Operation } from "../../../api/types";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import { TextInput } from "../../../components/Field";
import { OperationProgress } from "../../../components/OperationProgress";
import {
  forgetActiveOperation,
  isTerminalOperationStatus,
  rememberActiveOperation,
} from "../../operations/activeOperations";
import { startGoldBaselineBootstrap } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";
import type { GoldProject } from "../types";

type Props = {
  project: GoldProject;
  hasBaselines: boolean;
  onPreferBaseline?: (authoringRunId: string) => void;
};

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `boot_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

export function GoldBaselineBootstrapForm({
  project,
  hasBaselines,
  onPreferBaseline,
}: Props) {
  const queryClient = useQueryClient();
  const archived = project.status === "archived";
  const [proposalCount, setProposalCount] = useState(20);
  const [prelabelEnabled, setPrelabelEnabled] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [successSummary, setSuccessSummary] = useState<{
    authoringRunId: string;
    reviewableCaseCount: number;
  } | null>(null);
  const idempotencyKeyRef = useRef(newIdempotencyKey());
  const lastIntentRef = useRef({ proposalCount: 20, prelabelEnabled: false });

  const capabilitiesQuery = useQuery({
    queryKey: queryKeys.capabilities,
    queryFn: ({ signal }) => getCapabilities(signal),
    retry: false,
  });
  const authoringCapability = capabilitiesQuery.data?.authoring;
  const authoringReady =
    capabilitiesQuery.isSuccess &&
    authoringCapability != null &&
    typeof authoringCapability === "object" &&
    authoringCapability.ready === true;

  const operationQuery = useQuery({
    queryKey: operationId
      ? queryKeys.operation(operationId)
      : ["gold-bootstrap-idle"],
    queryFn: ({ signal }) => getOperation(operationId!, signal),
    enabled: Boolean(operationId),
    retry: false,
    refetchInterval: (q) => {
      if (q.state.error) return false;
      const status = q.state.data?.status;
      if (status && isTerminalOperationStatus(String(status))) return false;
      return 1000;
    },
  });

  useEffect(() => {
    const operation = operationQuery.data as Operation | undefined;
    if (!operation || !isTerminalOperationStatus(String(operation.status))) {
      return;
    }
    if (operation.status === "succeeded") {
      const result = operation.result ?? {};
      const authoringRunId =
        typeof result.authoring_run_id === "string"
          ? result.authoring_run_id
          : "";
      const reviewable =
        typeof result.reviewable_case_count === "number"
          ? result.reviewable_case_count
          : 0;
      if (authoringRunId) {
        setSuccessSummary({
          authoringRunId,
          reviewableCaseCount: reviewable,
        });
      }
      void queryClient.invalidateQueries({
        queryKey: goldLabQueryKeys.baselines(project.project_id),
      });
    }
    forgetActiveOperation(operation.operation_id);
  }, [operationQuery.data, project.project_id, queryClient]);

  const startMutation = useMutation({
    mutationFn: () =>
      startGoldBaselineBootstrap({
        projectId: project.project_id,
        proposalCount,
        prelabelEnabled,
        idempotencyKey: idempotencyKeyRef.current,
      }),
    onSuccess: (operation) => {
      setFormError(null);
      setSuccessSummary(null);
      setOperationId(operation.operation_id);
      rememberActiveOperation({
        operation_id: operation.operation_id,
        workspace_id: operation.workspace_id,
        kind: String(operation.kind),
        label: "Create baseline from workspace",
      });
      // Accepted — next create-another is a new intent.
      idempotencyKeyRef.current = newIdempotencyKey();
      lastIntentRef.current = { proposalCount, prelabelEnabled };
    },
    onError: (error) => {
      setFormError(goldLabErrorMessage(error));
    },
  });

  function ensureIdempotencyKeyForIntent(): void {
    const prior = lastIntentRef.current;
    const changed =
      prior.proposalCount !== proposalCount ||
      prior.prelabelEnabled !== prelabelEnabled;
    if (changed && startMutation.isError) {
      idempotencyKeyRef.current = newIdempotencyKey();
    }
    lastIntentRef.current = { proposalCount, prelabelEnabled };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (archived) {
      setFormError("Archived projects cannot create baselines.");
      return;
    }
    if (
      !Number.isInteger(proposalCount) ||
      proposalCount < 1 ||
      proposalCount > 40
    ) {
      setFormError("Proposal count must be an integer from 1 to 40.");
      return;
    }
    ensureIdempotencyKeyForIntent();
    startMutation.mutate();
  }

  function onCreateAnother() {
    setSuccessSummary(null);
    setOperationId(null);
    setFormError(null);
    idempotencyKeyRef.current = newIdempotencyKey();
  }

  if (archived) {
    return (
      <Card>
        <h2>Baseline from workspace</h2>
        <p className="muted" role="status">
          Archived projects cannot bootstrap a baseline from the workspace.
        </p>
      </Card>
    );
  }

  // Fail closed: only ready===true enables bootstrap creation.
  if (capabilitiesQuery.isPending) {
    return (
      <Card>
        <h2>Baseline from workspace</h2>
        <p className="muted" role="status">
          Checking Gold Lab authoring readiness…
        </p>
      </Card>
    );
  }

  if (capabilitiesQuery.isError) {
    return (
      <Card>
        <h2>Baseline from workspace</h2>
        <p className="error-box" role="status">
          Gold Lab authoring readiness could not be checked. Reload this page
          and try again. Baseline creation stays disabled until readiness is
          confirmed.
        </p>
        <div className="row">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              void capabilitiesQuery.refetch();
            }}
          >
            Retry readiness check
          </Button>
        </div>
      </Card>
    );
  }

  if (
    !capabilitiesQuery.isSuccess ||
    authoringCapability == null ||
    typeof authoringCapability !== "object" ||
    !("ready" in authoringCapability)
  ) {
    return (
      <Card>
        <h2>Baseline from workspace</h2>
        <p className="error-box" role="status">
          Gold Lab authoring readiness is unavailable from this installation.
          Reload the page. Baseline creation stays disabled until readiness is
          confirmed.
        </p>
        <div className="row">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              void capabilitiesQuery.refetch();
            }}
          >
            Retry readiness check
          </Button>
        </div>
      </Card>
    );
  }

  if (!authoringReady) {
    return (
      <Card>
        <h2>Baseline from workspace</h2>
        <p className="error-box" role="status">
          Gold Lab authoring is not ready. Configure the authoring server in
          Settings, apply any required restart, then return here to create a
          baseline.
        </p>
        <div className="row">
          <Button to="/settings?section=authoring" variant="primary">
            Configure Gold Lab authoring
          </Button>
        </div>
      </Card>
    );
  }

  const busy =
    startMutation.isPending ||
    (operationId != null &&
      operationQuery.data != null &&
      !isTerminalOperationStatus(String(operationQuery.data.status)));

  return (
    <Card>
      <h2>Baseline from workspace</h2>
      <p className="muted">
        Create a reviewable Gold authoring baseline from this project&apos;s
        current workspace publication. Campaign creation stays a separate,
        explicit step.
      </p>
      {successSummary ? (
        <div className="stack" data-testid="gold-bootstrap-success">
          <p role="status">
            Baseline ready. {successSummary.reviewableCaseCount} reviewable
            {successSummary.reviewableCaseCount === 1 ? " case" : " cases"}.
          </p>
          <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
            <Button
              type="button"
              onClick={() => onPreferBaseline?.(successSummary.authoringRunId)}
            >
              Create campaign from this baseline
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={onCreateAnother}
            >
              Create another baseline from workspace
            </Button>
          </div>
        </div>
      ) : (
        <form className="stack" onSubmit={onSubmit}>
          <TextInput
            id="gold-bootstrap-proposal-count"
            label="Proposal count"
            hint="Integer from 1 to 40. Default 20."
            type="number"
            min={1}
            max={40}
            step={1}
            value={String(proposalCount)}
            onChange={(event) => {
              const next = Number(event.target.value);
              setProposalCount(Number.isFinite(next) ? next : 0);
            }}
            disabled={busy}
            required
          />
          <label className="row" style={{ gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={prelabelEnabled}
              disabled={busy}
              onChange={(event) => setPrelabelEnabled(event.target.checked)}
            />
            <span>Run advisory prelabel</span>
          </label>
          {formError ? (
            <p className="error-box" role="alert">
              {formError}
            </p>
          ) : null}
          <Button type="submit" disabled={busy}>
            {hasBaselines
              ? "Create another baseline from workspace"
              : "Create baseline from workspace"}
          </Button>
        </form>
      )}
      {operationId && operationQuery.data ? (
        <OperationProgress
          phase="operation"
          operation={operationQuery.data}
          label="Create baseline from workspace"
          successMessage="Baseline ready."
        />
      ) : null}
      {operationId && operationQuery.isError ? (
        <OperationProgress
          phase="lookup_error"
          label="Create baseline from workspace"
          lookupError={goldLabErrorMessage(operationQuery.error)}
          onDismiss={() => setOperationId(null)}
        />
      ) : null}
    </Card>
  );
}
