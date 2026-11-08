# REL-03-P0 — External Inference Demo Profile

**Status:** IMPLEMENTATION COMPLETE / INDEPENDENT REVIEW PENDING

**Parent:** REL-03 — Hosted Portfolio Demo Profile (Milestone 7)  
**Profile:** `portfolio_openrouter`  
**Scope:** Backend/configuration seam only; no promotion or hosted deployment.

## Objective and boundary

Add one hidden, operator-only OpenRouter profile for portfolio/job-search demos.
The default product remains local-first and strict-offline. The external profile
redirects only three existing inference responsibilities:

1. grounded answer generation;
2. explicit BETA-CONV-01C conversation actions, including recent-conversation
   summaries;
3. Gold Lab authoring calls already governed by `settings.authoring`.

Retrieval and scientific authority remain in Seneca. The model neither retrieves
documents nor creates citation identities, validates citations, judges Gold
truth, or performs human adjudication.

## Profile and environment contract

Use the existing `deployment.profile` setting. The only new external-inference
profile is `portfolio_openrouter`; do not add arbitrary provider or endpoint
selection.

The three operator-facing environment values are:

```ini
OFFLINE_RAG_DEPLOYMENT_PROFILE=portfolio_openrouter
OFFLINE_RAG_EXTERNAL_INFERENCE_MODEL=~deepseek/deepseek-flash-latest
OFFLINE_RAG_EXTERNAL_INFERENCE_API_KEY=<operator secret>
```

The endpoint is application-owned and fixed to
`https://openrouter.ai/api/v1`. There is no external base-URL setting. The model
is operator-selected and required; the API key is secret and required. The
requested model alias was present as an `id` in OpenRouter's public model catalog
when this contract was prepared ([catalog](https://openrouter.ai/api/v1/models),
[model profile](https://openrouter.ai/~deepseek/deepseek-flash-latest)). This is
catalog evidence only, not a live inference qualification.

Fail closed:

- If the profile is not `portfolio_openrouter`, presence of either external
  inference input is a configuration error. They never enable cloud inference
  implicitly.
- If `portfolio_openrouter` is selected, missing or empty model/key is a
  configuration error.
- There is no fallback to Ollama, persisted product settings, or another
  provider.

## Configuration precedence and effective profile

The deployment-profile overlay is applied last:

```text
built-in defaults
  < YAML
  < persisted product settings
  < ordinary environment overrides
  < explicit programmatic overrides
  < portfolio_openrouter profile overlay
```

This overlay owns the inference boundary even when Generation or Gold Authoring
Settings are in `user` mode. Saved settings remain on disk, but cannot redirect
runtime inference while this profile is active. Both Settings APIs report
profile-owned fields as operator-controlled. No UI control is added.

Effective generation and authoring settings are:

```text
enabled            = true
provider           = openai_compatible
endpoint           = https://openrouter.ai/api/v1
model              = OFFLINE_RAG_EXTERNAL_INFERENCE_MODEL
api_key            = OFFLINE_RAG_EXTERNAL_INFERENCE_API_KEY
approved_endpoints = [https://openrouter.ai/api/v1]
approved_models    = [OFFLINE_RAG_EXTERNAL_INFERENCE_MODEL]
```

Authoring retains the accepted adapter contract. Its public endpoint exception
is exact and conjunctive: profile is `portfolio_openrouter`; normalized URL is
`https://openrouter.ai/api/v1`; endpoint and model are in their exact approved
lists; and the key is non-empty. All other public authoring URLs remain rejected.
Do not introduce a general public/internet authoring network policy.

Under the profile, `project.strict_offline=false` only to permit the fixed
inference destination. The default profile remains `strict_offline=true` with
existing behavior unchanged. Deployment continues to set
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; no runtime model downloads are
enabled.

## Inference paths

### Grounded answers

The user question still passes through local dense and lexical retrieval, local
fusion, local reranking, local context assembly, and the existing grounded
generation prompt. Only the generation request uses OpenRouter. Seneca continues
to construct and validate citations locally. Keep the existing generation
endpoint/model approval guards enabled with the exact narrow allowlists above.

### Explicit conversation actions

Summarize, Simplify, Translate, and Summarize recent conversation continue
through the single existing `generator_client` and conversation-action executor.
They use the existing bounded transcript, prompt, truncation protection and
synthetic-user-turn semantics. These calls do not retrieve, emit citations, or
create a query trace; conversation-origin provenance remains unchanged. Do not
add special provider-specific conversation code or a second executor.

### Gold Lab authoring

Existing Gold authoring calls governed by `settings.authoring` use the same
OpenAI-compatible generator transport and profile model. Preserve structured
`response_format` and all existing output/scientific validation. If the provider
rejects a required structured-output contract, fail and report the
incompatibility; do not downgrade parsing, add JSON salvage, or weaken Gold
validation. Retrieval arms, Gold judgments/truth, and human adjudication remain
local.

## Local-only systems

The profile does not externalize ingestion, Docling, tokenization, chunking,
dense embeddings, lexical indexing, Qdrant Local, dense/BM25 retrieval, RRF,
cross-encoder reranking, context assembly, citation creation/validation,
workspace publication/persistence, Gold judgments/ledger, retrieval evaluation,
or scientific metrics.

Independent inference systems are not redirected: retrieval recovery rewriting
and `evaluation.generation_semantic_judge` retain their own existing settings
and enablement. This profile is not a blanket cloud switch. Do not add external
embeddings, reranking, search/tools, or web search.

## Transport, probe, and secrets

Use the existing OpenAI-compatible adapters and Bearer-token authentication.
Grounded and authoring requests use the existing `/chat/completions` endpoint,
preserving request fields including `response_format` when supplied. The local
runtime-only `chat_template_kwargs: {enable_thinking: false}` is omitted only
for `portfolio_openrouter`; local-profile request shaping remains unchanged.

Keep the existing non-generative `GET /models` probe and exact approved-model
readiness. If the requested alias is not recognized compatibly by that probe,
stop and report the observed response; do not weaken the generic readiness
contract.

The key must never appear in Git, examples, logs, repr output, traces, exports,
API responses, frontend state, error details, configuration hashes, or evidence.
Tests use an obvious sentinel secret and assert it is absent from serialized and
loggable projections. Product settings files must not persist this environment-
owned key. No key value is recorded in evidence.

## Deterministic verification before live calls

Focused tests must establish:

- no REL-03 environment: unchanged strict-offline defaults, generation endpoint,
  and authoring privacy behavior;
- profile overlay wins over YAML, persisted settings, ordinary environment,
  and explicit runtime generation/authoring settings;
- required model/key validation and external-input-without-profile rejection;
- operator-owned fields from both Settings APIs;
- exact endpoint/model allowlists and rejection of OpenAI, arbitrary example,
  and OpenRouter-like public URLs;
- mocked grounded generation to
  `https://openrouter.ai/api/v1/chat/completions`, configured model and Bearer
  auth, no local-only `chat_template_kwargs`, retained structured response
  format, and secret-safe errors;
- explicit conversation action uses the same generator boundary and preserves
  conversation provenance, empty citations, and absent query trace;
- an actual Gold authoring adapter/application flow uses the profile endpoint,
  retains structured output, and preserves existing scientific validation;
- secret redaction in repr, logs/serialization, API views and hash projections.

All external HTTP in deterministic tests is mocked. No test may use a real key.

## Optional bounded live smoke

Only after deterministic tests pass, and only when the operator has supplied a
real key, one smoke each may exercise: a public/synthetic grounded question, a
conversation summary of that answer, and the smallest existing Gold authoring
operation. Verify local retrieval/reranking/citations for the grounded path and
existing 01C provenance for the conversation path. Do not use proprietary Well
Logging data.

Stop immediately if the key is exposed, the model alias is rejected, required
structured authoring is unsupported, another public URL is authorized, default
strict-offline changes, or external inference touches retrieval, embeddings, or
reranking. Do not invent compatibility fallbacks. No live request is made when
no operator key is present.

## Explicit exclusions and dependency order

This P0 does not authorize UI changes, Cloud Run or Secret Manager setup,
Dockerfile/deployment claims, Terraform, public hosting, Slice 17, REL-01
implementation, Slice 18, BETA-CONV-02, or Slice 9G. No promotion is authorized.

Dependency order:

```text
REL-03-P0 external-inference seam
    ↓
Slice 17 profile-isolation regression CI
    ↓
REL-01 CPU release image
    ↓
Slice 18 Cloud Run + Secret Manager + hosted demo
```
