import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  getAuthoringSettings,
  getGenerationSettings,
  probeAuthoringSettings,
  probeGenerationSettings,
  saveAuthoringSettings,
  saveGenerationSettings,
} from "../api/client";
import { userFacingErrorMessage } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import type {
  AuthoringSettingsState,
  GenerationSettingsState,
} from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { TextInput } from "../components/Field";
import { authoringReadinessStatusText } from "../features/goldLab/authoringReadinessCopy";

type SettingsSection = "generation" | "authoring";

function parseSection(raw: string | null): SettingsSection {
  return raw === "authoring" ? "authoring" : "generation";
}

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
      {state.restart_required ? (
        <p className="error-box" role="status">
          Restart required. Pending generation settings are saved but not yet
          active in this running application.
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

type AuthoringFormProps = {
  state: AuthoringSettingsState;
};

function AuthoringSettingsForm({ state }: AuthoringFormProps) {
  const queryClient = useQueryClient();
  const view = state.pending ?? state.active;
  const locks = state.locks;
  const active = state.active;
  const pending = state.pending;
  const readiness = state.readiness;

  const [enabled, setEnabled] = useState(view.enabled);
  const [baseUrl, setBaseUrl] = useState(view.base_url);
  const [model, setModel] = useState(view.model ?? "");
  const [timeoutSeconds, setTimeoutSeconds] = useState(view.timeout_seconds);
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [probeMessage, setProbeMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const anySelectionLocked =
    locks.enabled ||
    locks.base_url ||
    locks.model ||
    locks.timeout_seconds ||
    locks.api_key;

  const probeMutation = useMutation({
    mutationFn: () =>
      probeAuthoringSettings({
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
      saveAuthoringSettings({
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
        queryKey: queryKeys.authoringSettings,
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
      {state.restart_required ? (
        <p className="error-box" role="status">
          Restart required. Pending Gold Lab authoring settings are saved but
          not yet active in this running application.
        </p>
      ) : null}

      <Card>
        <h2>Gold Lab authoring server</h2>
        <p className="muted">
          Gold Lab authoring creates candidate questions and evidence for review
          baselines. Machine-generated material remains review input and does
          not create Gold labels.
        </p>
        <p className="muted" role="status">
          {authoringReadinessStatusText({
            ready: readiness.ready,
            reasonCodes: readiness.reason_codes,
          })}
        </p>
        {anySelectionLocked ? (
          <p className="muted" role="status">
            One or more fields are operator controlled by environment
            configuration. Product Settings cannot override those values.
          </p>
        ) : null}
        <form className="stack" onSubmit={onSubmit}>
          <label className="row" style={{ gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={enabled}
              disabled={Boolean(locks.enabled)}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            Authoring enabled
            {locks.enabled ? (
              <span className="muted">Operator controlled</span>
            ) : null}
          </label>

          <TextInput
            id="authoring-provider"
            label="Provider"
            value="OpenAI-compatible"
            readOnly
          />

          <TextInput
            id="authoring-endpoint"
            label={
              locks.base_url ? "Endpoint (operator controlled)" : "Endpoint"
            }
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            disabled={Boolean(locks.base_url)}
            required
          />

          <TextInput
            id="authoring-model"
            label={locks.model ? "Model (operator controlled)" : "Model"}
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={Boolean(locks.model)}
            required
          />

          <TextInput
            id="authoring-timeout"
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
            <label htmlFor="authoring-api-key">
              API key
              {locks.api_key ? " (operator controlled)" : ""}
            </label>
            <input
              id="authoring-api-key"
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
            <Button
              type="submit"
              disabled={
                saveMutation.isPending ||
                (locks.enabled &&
                  locks.base_url &&
                  locks.model &&
                  locks.timeout_seconds &&
                  locks.api_key)
              }
            >
              Save settings
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2>Active configuration</h2>
        <p className="muted" style={{ margin: 0 }}>
          {active.base_url} · {active.model ?? "(no model)"} · timeout{" "}
          {active.timeout_seconds}s · policy {active.network_policy} · key{" "}
          {active.api_key_configured ? "configured" : "not configured"}
        </p>
        {pending ? (
          <>
            <h3>Pending configuration</h3>
            <p className="muted" style={{ margin: 0 }}>
              {pending.base_url} · {pending.model ?? "(no model)"} · timeout{" "}
              {pending.timeout_seconds}s · policy {pending.network_policy} · key{" "}
              {pending.api_key_configured ? "configured" : "not configured"}
            </p>
          </>
        ) : null}
      </Card>
    </div>
  );
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const section = useMemo(
    () => parseSection(searchParams.get("section")),
    [searchParams],
  );

  const generationQuery = useQuery({
    queryKey: queryKeys.generationSettings,
    queryFn: ({ signal }) => getGenerationSettings(signal),
  });
  const authoringQuery = useQuery({
    queryKey: queryKeys.authoringSettings,
    queryFn: ({ signal }) => getAuthoringSettings(signal),
    enabled: section === "authoring",
  });

  function selectSection(next: SettingsSection) {
    const params = new URLSearchParams(searchParams);
    if (next === "generation") {
      params.delete("section");
    } else {
      params.set("section", next);
    }
    setSearchParams(params, { replace: true });
  }

  const loading =
    section === "generation"
      ? generationQuery.isLoading
      : authoringQuery.isLoading;
  const errored =
    section === "generation"
      ? generationQuery.isError || !generationQuery.data
      : authoringQuery.isError || !authoringQuery.data;

  if (loading) {
    return <p className="muted">Loading settings…</p>;
  }

  if (errored) {
    const error =
      section === "generation" ? generationQuery.error : authoringQuery.error;
    return (
      <Card>
        <h1>Settings unavailable</h1>
        <p className="error-box" role="alert">
          {userFacingErrorMessage(error ?? new Error("Missing"))}
        </p>
      </Card>
    );
  }

  const generationKey = generationQuery.data
    ? [
        generationQuery.dataUpdatedAt,
        generationQuery.data.restart_required ? "1" : "0",
        generationQuery.data.active.model,
        generationQuery.data.pending?.model ?? "",
      ].join(":")
    : "generation";
  const authoringKey = authoringQuery.data
    ? [
        authoringQuery.dataUpdatedAt,
        authoringQuery.data.restart_required ? "1" : "0",
        authoringQuery.data.active.model ?? "",
        authoringQuery.data.pending?.model ?? "",
      ].join(":")
    : "authoring";

  const strictOffline =
    section === "generation"
      ? Boolean(generationQuery.data?.strict_offline)
      : Boolean(authoringQuery.data?.strict_offline);

  return (
    <div className="stack">
      <header className="stack" style={{ gap: "0.35rem" }}>
        <h1 style={{ margin: 0 }}>Settings</h1>
        <p className="muted" style={{ margin: 0 }}>
          Configure local OpenAI-compatible servers used by Seneca. Answer
          generation and Gold Lab authoring remain independent. Scientific
          retrieval settings are not editable here.
        </p>
      </header>

      <div
        className="row"
        role="group"
        aria-label="Settings section"
        style={{ gap: "0.5rem", flexWrap: "wrap" }}
      >
        <Button
          type="button"
          variant={section === "generation" ? "primary" : "secondary"}
          aria-pressed={section === "generation"}
          onClick={() => selectSection("generation")}
        >
          Answer generation
        </Button>
        <Button
          type="button"
          variant={section === "authoring" ? "primary" : "secondary"}
          aria-pressed={section === "authoring"}
          onClick={() => selectSection("authoring")}
        >
          Gold Lab authoring
        </Button>
      </div>

      {strictOffline ? (
        <p className="muted">
          Strict offline mode is active. Only loopback, Docker-host, and private
          LAN endpoints can be approved.
        </p>
      ) : null}

      {section === "generation" && generationQuery.data ? (
        <GenerationSettingsForm
          key={generationKey}
          state={generationQuery.data}
        />
      ) : null}
      {section === "authoring" && authoringQuery.data ? (
        <AuthoringSettingsForm key={authoringKey} state={authoringQuery.data} />
      ) : null}

      {section === "authoring" ? (
        <p className="muted">
          Need answer generation instead?{" "}
          <Link to="/settings">Open Answer generation</Link>
        </p>
      ) : null}
    </div>
  );
}
