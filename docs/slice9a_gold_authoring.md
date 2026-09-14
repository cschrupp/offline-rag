# Slice 9A — Gold authoring contracts & privacy boundary

Slice 9A opens Milestone 4 by establishing the authoring subsystem boundary:
independent config, fail-closed privacy authorization, `authorcfg_` identity,
lean silver/run models, and doctor readiness — without calling an LLM or
shipping `offline-rag gold` commands.

**Status:** implemented.

## Architecture

```text
AppSettings.authoring
        ↓
evaluate_authoring_readiness (config + privacy; no live probe)
        ↓
authorize_authoring_endpoint (allowlist AND network_policy)
        ↓
invoke_authorized_authoring_transport (9A stub; no redirects)
        ↓
GoldAuthoringRun / SilverCase (offline-rag-gold-authoring-v1)
```

Package: `src/offline_rag/gold_authoring/`

Production generation (`generation/` / `gencfg_`) and Slice 9 gold loaders
remain separate. Eval loaders reject `offline-rag-gold-authoring-v1`.

## Configuration

Top-level `authoring:` is independent of `generation.*` (no semantic
inheritance). Shared HTTP transport may appear later; contracts and hashes do not.

```yaml
authoring:
  enabled: false
  provider: openai_compatible
  adapter_contract: openai-compatible-authoring-v1
  base_url: http://127.0.0.1:11434/v1
  model: null
  api_key: null   # optional Bearer; prefer OFFLINE_RAG_AUTHORING_API_KEY
  network_policy: localhost_only   # or private_network
  approved_endpoints: []
  approved_models: []
  temperature: 0.0
  max_output_tokens: 1200
  timeout_seconds: 120
  contracts:
    question_proposal: question-proposal-v1
    relevance_prelabel: relevance-prelabel-v1
    artifact: offline-rag-gold-authoring-v1
```

Safe defaults: `enabled: false`, empty allowlists, `model: null`. Fresh
install → Authoring NOT_READY (informational). `enabled=true` ∧ NOT_READY →
doctor hard FAIL.

Env map: `OFFLINE_RAG_AUTHORING_*` → `authoring.*` (no generation key reuse).

## Contracts (hashed into `authorcfg_`)

| Contract | ID |
|---|---|
| Adapter | `openai-compatible-authoring-v1` |
| Question proposal | `question-proposal-v1` |
| Relevance prelabel | `relevance-prelabel-v1` |
| Artifact | `offline-rag-gold-authoring-v1` |

`authorcfg_` hashes: provider, adapter, model/null, temperature,
max_output_tokens, three contract IDs above.

Not hashed: enabled, network_policy, base_url, allowlists, timeout, api_key.

Example semantic payload:

```json
{
  "provider": "openai_compatible",
  "adapter_contract": "openai-compatible-authoring-v1",
  "model": null,
  "temperature": 0.0,
  "max_output_tokens": 1200,
  "question_proposal_contract": "question-proposal-v1",
  "relevance_prelabel_contract": "relevance-prelabel-v1",
  "authoring_artifact_contract": "offline-rag-gold-authoring-v1"
}
```

→ `authorcfg_<sha256>`

## Privacy

Dual gate before any transport:

1. Endpoint must be on `approved_endpoints` (normalized OpenAI-compatible `/v1`).
2. Destination must satisfy `network_policy`.

| Policy | Allowed destinations |
|---|---|
| `localhost_only` | loopback only |
| `private_network` | private / loopback / link-local; never public IPs |

Public addresses fail even if allowlisted. Fail closed. Redirects disallowed
(`authoring_follow_redirects() → False`).

## Silver vs gold

`GoldAuthoringRun` / `SilverCase` hold draft identity, human status, and
placeholders for seed / candidates / model judgments. Accepted silver ≠ gold.

`HumanReviewStatus`: `pending` | `accepted` | `edited` | `rejected`.

GoldDataset v1 loaders reject authoring schema versions.

## Readiness

```text
authoring.enabled
+ supported provider/adapter/contracts
+ endpoint configured + allowlisted
+ network_policy satisfied
+ model configured + approved
→ Authoring READY
```

Readiness is configuration + privacy authorization only — no `/models` probe
and no completions in 9A. Surface: `offline-rag doctor` Authoring section.

## Boundaries

- No LLM calls, sampling, pooling, review UI, finalize, or `offline-rag gold` CLI
- No inheritance from `generation.*` / `gencfg_` / Slice 8 prompt contracts
- No change to GoldDataset v1 semantics or `base.yaml` retrieval/generation defaults
- No promotion of Arm H / `model-query-prompt-v1` / provenance-v2

## Next

Slices **9B** / **9C** / **9D** / **9E** done. Next: Slice **9F** — 20-case authoring pilot.
