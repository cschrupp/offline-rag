import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../../components/Button";
import { Card } from "../../../components/Card";
import { Field, TextInput } from "../../../components/Field";
import { createGoldCampaign } from "../api/client";
import { goldLabErrorMessage } from "../errors/goldLabErrors";
import { goldLabQueryKeys } from "../queryKeys";
import type { GoldBaselineSummary } from "../types";

type Props = {
  projectId: string;
  baselines: GoldBaselineSummary[];
  disabled: boolean;
  disabledReason?: string;
};

export function GoldCampaignCreateForm({
  projectId,
  baselines,
  disabled,
  disabledReason,
}: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [baselineId, setBaselineId] = useState("");
  const [selectionPolicyId, setSelectionPolicyId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createGoldCampaign(projectId, {
        baseline_authoring_run_id: baselineId,
        selection_policy_id: selectionPolicyId.trim(),
        selection_policy_parameters: {},
        hard_calls: [],
      }),
    onSuccess: async (campaign) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.campaigns(projectId),
        }),
        queryClient.invalidateQueries({
          queryKey: goldLabQueryKeys.project(projectId),
        }),
      ]);
      setFormError(null);
      void navigate(`/gold-lab/campaigns/${campaign.campaign_id}`);
    },
    onError: (error) => {
      setFormError(goldLabErrorMessage(error));
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (disabled) {
      setFormError(disabledReason ?? "Campaign creation is not available.");
      return;
    }
    if (!baselineId) {
      setFormError("Select an eligible baseline.");
      return;
    }
    if (!selectionPolicyId.trim()) {
      setFormError("Enter an explicit selection policy ID.");
      return;
    }
    createMutation.mutate();
  }

  return (
    <Card>
      <h2>Create campaign</h2>
      {disabled ? (
        <p className="muted" role="status">
          {disabledReason ?? "Campaign creation is disabled."}
        </p>
      ) : null}
      <form className="stack" onSubmit={onSubmit}>
        <Field
          id="gold-campaign-baseline"
          label="Eligible baseline"
          hint="Baselines are server-authoritative. Arbitrary paths are not accepted."
        >
          <select
            id="gold-campaign-baseline"
            value={baselineId}
            onChange={(event) => setBaselineId(event.target.value)}
            disabled={disabled || baselines.length === 0}
            required={!disabled}
          >
            <option value="">Select a baseline</option>
            {baselines.map((baseline) => (
              <option
                key={baseline.authoring_run_id}
                value={baseline.authoring_run_id}
              >
                {baseline.corpus_name} — {baseline.authoring_run_id}
              </option>
            ))}
          </select>
        </Field>

        <TextInput
          id="gold-campaign-policy"
          label="Selection policy ID"
          value={selectionPolicyId}
          onChange={(event) => setSelectionPolicyId(event.target.value)}
          disabled={disabled}
          required={!disabled}
          hint="Identifies this campaign’s selection methodology. Seneca does not invent a default policy catalog in this build."
        />

        <p className="muted">
          Selection parameters and hard calls are not authored in this build.
          The create request sends empty parameters and an empty hard-call list.
        </p>

        {formError ? (
          <p className="error-box" role="alert">
            {formError}
          </p>
        ) : null}

        <div className="row">
          <Button
            type="submit"
            disabled={disabled || createMutation.isPending || baselines.length === 0}
          >
            {createMutation.isPending ? "Creating…" : "Create campaign"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
