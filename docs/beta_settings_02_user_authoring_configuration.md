# BETA-SETTINGS-02 — User-editable Gold Lab Authoring configuration

This slice adds `OFFLINE_RAG_AUTHORING_SETTINGS_MODE`, with `operator` as the
backward-compatible default and `user` as the saved-settings ownership mode.

In `operator` mode, authoring environment values remain authoritative and lock
the matching Gold Lab Authoring controls. In `user` mode, the enabled state,
endpoint, model and approval lists, timeout, network policy, and API key seed
first-run configuration; saved Authoring Settings take precedence after
restart. API-key keep/set/clear behavior and strict-offline endpoint validation
remain in place. Explicit programmatic overrides stay highest priority and
lock the corresponding controls.

Authoring environment values for provider, adapter contract, temperature, and
maximum output tokens remain operator-owned because the Authoring Settings API
does not expose those fields.

The loaded authoring settings continue to feed Gold Lab readiness and the
OpenAI-compatible authoring adapter. The regression test verifies this path
with a fake completion client; it makes no network request.

## Implementation handoff

**Status:** Implementation candidate; independent review pending.

**Scope:** Configuration loading and validation, authoring field locks,
explicit-override reporting, example environment/Compose configuration, and
focused tests. No production model, network policy, or runtime lifecycle was
changed.

**Validation:** Ten focused Python tests passed, covering default/operator mode,
user-mode bootstrap and save/reload, API-key keep/set/clear, explicit override
locks, strict-offline policy, generation-mode regression, and a synthetic
Gold Lab authoring-adapter completion using the saved endpoint/model. Ruff lint,
Compose YAML parsing, and `git diff --check` passed. No live authoring endpoint
or model was used.

The broader TestClient batch stalled during application startup and was
interrupted; `TEST-STARTUP-01` remains separate. Ruff's format check still
reports pre-existing formatting drift in the touched authoring API, product
settings module, and test file. Ruff lint passes, and the new code blocks are
formatted.

A broader authoring regression run also reached 22 passes before one existing
public-host privacy test failed because this restricted environment could not
resolve its hostname (`hostname_resolution_failed`). The focused offline
privacy checks passed; network policy code was not changed.
