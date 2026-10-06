import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import {
  getGenerationSettings,
  probeGenerationSettings,
  saveGenerationSettings,
} from "../api/client";
import { userFacingErrorMessage } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import type { GenerationSettingsState } from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { TextInput } from "../components/Field";

type GenerationFormProps = {
  state: GenerationSettingsState;
};

function GenerationSettingsForm({ state }: GenerationFormProps) {
  const queryClient = useQueryClient();
  const view = state.pending ?? state.active;
  const locks = state.locks;
  const active = state.active;
  const pending = state.pending;

  const [enabled, setEnabled] = useState(view.enabled);
  const [baseUrl, setBaseUrl] = useState(view.base_url);
  const [model, setModel] = useState(view.model);
  const [timeoutSeconds, setTimeoutSeconds] = useState(view.timeout_seconds);
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [probeMessage, setProbeMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const probeMutation = useMutation({
    mutationFn: () =>
      probeGenerationSettings({
        enabled,
        base_url: baseUrl,
        model,
        timeout_seconds: timeoutSeconds,
        api_key: clearApiKey ? null : apiKey || null,
        api_key_action: clearApiKey ? "clear" : apiKey ? "set" : "keep",
      }),
    onSuccess: (result) => {
      setFormError(null);
      if (result.ok) {
        const count = result.available_models?.length ?? 0;
        setProbeMessage(`Connected. ${count} model(s) reported.`);
      } else {
        setProbeMessage(`Probe failed: ${result.reason ?? "unknown"}`);
      }
    },
    onError: (error) => {
      setProbeMessage(null);
      setFormError(userFacingErrorMessage(error));
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      saveGenerationSettings({
        enabled,
        base_url: baseUrl,
        model,
        timeout_seconds: timeoutSeconds,
        api_key: clearApiKey ? null : apiKey || null,
        api_key_action: clearApiKey ? "clear" : apiKey ? "set" : "keep",
      }),
    retry: false,
    onSuccess: async (result) => {
      setFormError(null);
      setSaveMessage(
        result.restart_required
          ? "Saved. Restart the application to apply pending settings."
          : "Saved.",
      );
      setApiKey("");
      setClearApiKey(false);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.generationSettings,
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.capabilities });
    },
    onError: (error) => {
      setSaveMessage(null);
      setFormError(userFacingErrorMessage(error));
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveMessage(null);
    saveMutation.mutate();
  }

  return (
    <div className="stack">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Settings</h1>
        <p className="muted" style={{ margin: 0 }}>
          Configure the local OpenAI-compatible generation server used by Seneca.
          Scientific retrieval settings are not editable here.
        </p>
      </header>

      {state.restart_required ? (
        <p className="error-box" role="status">
          Restart required. Pending generation settings are saved but not yet
          active in this running application.
        </p>
      ) : null}

      {state.strict_offline ? (
        <p className="muted">
          Strict offline mode is active. Only loopback, Docker-host, and private
          LAN endpoints can be approved.
        </p>
      ) : null}

      <Card>
        <h2>Generation server</h2>
        <form className="stack" onSubmit={onSubmit}>
          <label className="row" style={{ gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={enabled}
              disabled={Boolean(locks.enabled)}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            Generation enabled
            {locks.enabled ? (
              <span className="muted">Operator controlled</span>
            ) : null}
          </label>

          <TextInput
            id="settings-provider"
            label="Provider"
            value="OpenAI-compatible"
            readOnly
          />

          <TextInput
            id="settings-endpoint"
            label={
              locks.base_url ? "Endpoint (operator controlled)" : "Endpoint"
            }
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            disabled={Boolean(locks.base_url)}
            required
          />

          <TextInput
            id="settings-model"
            label={locks.model ? "Model (operator controlled)" : "Model"}
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={Boolean(locks.model)}
            required
          />

          <TextInput
            id="settings-timeout"
            label={
              locks.timeout_seconds
                ? "Timeout seconds (operator controlled)"
                : "Timeout seconds"
            }
            type="number"
            min={1}
            value={String(timeoutSeconds)}
            onChange={(event) =>
              setTimeoutSeconds(Number(event.target.value) || 120)
            }
            disabled={Boolean(locks.timeout_seconds)}
            required
          />

          <div className="field">
            <label htmlFor="settings-api-key">
              API key
              {locks.api_key ? " (operator controlled)" : ""}
            </label>
            <input
              id="settings-api-key"
              type="password"
              autoComplete="new-password"
              value={apiKey}
              disabled={Boolean(locks.api_key) || clearApiKey}
              placeholder={
                active.api_key_configured
                  ? "Leave blank to keep current key"
                  : "Optional"
              }
              onChange={(event) => setApiKey(event.target.value)}
            />
            <label className="row" style={{ gap: "0.5rem" }}>
              <input
                type="checkbox"
                checked={clearApiKey}
                disabled={Boolean(locks.api_key)}
                onChange={(event) => {
                  setClearApiKey(event.target.checked);
                  if (event.target.checked) setApiKey("");
                }}
              />
              Clear stored API key
            </label>
          </div>

          {probeMessage ? <p role="status">{probeMessage}</p> : null}
          {saveMessage ? <p role="status">{saveMessage}</p> : null}
          {formError ? (
            <p className="error-box" role="alert">
              {formError}
            </p>
          ) : null}

          <div className="row">
            <Button
              type="button"
              variant="secondary"
              disabled={probeMutation.isPending || saveMutation.isPending}
              onClick={() => {
                setProbeMessage(null);
                probeMutation.mutate();
              }}
            >
              Test connection
            </Button>
            <Button type="submit" disabled={saveMutation.isPending}>
              Save settings
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2>Active configuration</h2>
        <p className="muted" style={{ margin: 0 }}>
          {active.base_url} · {active.model} · timeout {active.timeout_seconds}s
          · key {active.api_key_configured ? "configured" : "not configured"}
        </p>
        {pending ? (
          <>
            <h3>Pending configuration</h3>
            <p className="muted" style={{ margin: 0 }}>
              {pending.base_url} · {pending.model} · timeout{" "}
              {pending.timeout_seconds}s · key{" "}
              {pending.api_key_configured ? "configured" : "not configured"}
            </p>
          </>
        ) : null}
      </Card>
    </div>
  );
}

export function SettingsPage() {
  const settingsQuery = useQuery({
    queryKey: queryKeys.generationSettings,
    queryFn: ({ signal }) => getGenerationSettings(signal),
  });

  if (settingsQuery.isLoading) {
    return <p className="muted">Loading settings…</p>;
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <Card>
        <h1>Settings unavailable</h1>
        <p className="error-box" role="alert">
          {userFacingErrorMessage(settingsQuery.error ?? new Error("Missing"))}
        </p>
      </Card>
    );
  }

  const formKey = [
    settingsQuery.dataUpdatedAt,
    settingsQuery.data.restart_required ? "1" : "0",
    settingsQuery.data.active.model,
    settingsQuery.data.pending?.model ?? "",
  ].join(":");

  return (
    <GenerationSettingsForm key={formKey} state={settingsQuery.data} />
  );
}
