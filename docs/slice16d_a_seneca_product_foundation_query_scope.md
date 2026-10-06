# Slice 16D-A — Seneca Product Foundation & Query-Scope Substrate

STATUS: IMPLEMENTATION CANDIDATE
HUMAN ACCEPTANCE: PENDING

Authorized baseline: `185d3e3d2bd472ffaddf72cfddc49c7e38a3a146`
Prior candidate (review disposition REWORK REQUIRED): `5864e06c57368dcc432ea8867ecd681f99841434`
A1 authority: `5060e2aeb4825f265072a1f870c3c963eace3b30`
Branch: `implementation/16d-a-seneca-product-foundation-query-scope`

## Brand

- Public product identity: **Seneca — Grounded knowledge workspace**
- `ui/index.html` title updated
- Local geometric stoa/colonnade SVG favicon (replaceable placeholder)
- AppShell brand mark + descriptor + Settings cog navigation
- Overview product copy updated to Seneca
- Technical identities retained: repository `offline-rag`, package `offline_rag`, API title `OfflineRAG API`

## Capabilities

- `GET /v1/capabilities` (ACTIVE runtime only)
- Product name/descriptor, source capacity limits, generation ACTIVE block
- No API key, approvals lists, paths, or pending values
- No network probe

## Capacity defaults

- `config/base.yaml` explicit:
  - `api.max_files_per_ingest: 32`
  - `api.max_bytes_per_document: 26214400`
  - `api.max_total_upload_bytes: 104857600`
- Env overrides remain supported
- Frontend hard-coded `SOURCE_LIMITS` authority removed; capacity from capabilities

## Product settings persistence

- Path: `paths.product_settings` → `data/settings` / `<DATA_DIR>/settings`
- File: `seneca-generation.json` (`seneca-generation-settings-v1`)
- Generation-only allowlisted schema
- Atomic write + owner-only permissions where practical
- Overlay derives `approved_endpoints` / `approved_models` from selected endpoint/model

## Precedence / locks

- Precedence: defaults → YAML → Seneca product generation overlay → environment → explicit overrides
- `OFFLINE_RAG_DATA_DIR` rebases product settings path **before** overlay read
- Operator env locks: base_url, model, timeout, api_key (+ approval-list envs lock matching fields)
- Env-selected endpoint/model is not auto-approved by stale product approvals

## Strict-offline endpoint policy

- Central helper: `src/offline_rag/app/endpoint_policy.py`
- Accepts loopback, RFC1918, private/link-local IPv6, `host.docker.internal`
- Rejects public Internet / arbitrary DNS under `strict_offline`
- Rejects unsupported scheme, missing host, embedded credentials
- Used by Settings validate / probe / save
- **Rework:** also enforced at product-settings load and at the active
  `OpenAICompatibleGenerator._assert_authorized` / startup
  `validate_generation_static_config` boundary (defense in depth)

## Settings API

- `GET /v1/settings/generation` — ACTIVE + PENDING + locks + restart_required; never returns API key
- `POST /v1/settings/generation/probe` — prospective probe; no persist; no runtime mutation; closed reason codes
- `PUT /v1/settings/generation` — persist only; no live hot-swap; re-probe when enabling
- API key actions: `keep` | `set` | `clear`
- Errors: `SETTINGS_INVALID` (422), `SETTINGS_LOCKED` (409), `SETTINGS_PROBE_FAILED`
- **Rework:** operator-locked selection cannot acquire product-managed approval via
  Test/Save; probe uses active approval authority when locks apply
- **Rework:** pending `api_key_configured` reflects effective future key under
  YAML / product-managed null / env-lock precedence (omit preserves YAML;
  explicit product null clears YAML)
- **Rework 3:** probe `api_key_action=keep` honors explicit product `api_key: null`
  and does not resurrect ACTIVE/YAML secrets for prospective Test Connection
- **Rework 2:** endpoint and model approval authority are independent; product
  may own only model or only endpoint; locked selection is omitted from the
  durable product file (no duplicated operator approval)

## ACTIVE / PENDING

- ACTIVE = current ApplicationRuntime generation settings
- PENDING = effective future after restart (locked fields keep operator ACTIVE values)
- Product-omitted selection fields keep ACTIVE values in PENDING
- Capabilities reports ACTIVE only
- Fresh `load_settings` after restart applies product overlay under env authority

## Compact workspace UX

- Compact header with capacity summary (`N / max sources · MiB / max MiB`)
- Source rows with accessible `⋮` overflow menu (Rename / Replace / Remove)
- Workspace metadata behind secondary Edit dialog
- Add sources behind modal; preserves 16C idempotency + durable ops
- No source-selection checkboxes (16D-B)
- Compact terminal Ready tray; no permanent success card domination
- **Rework:** FAILED / INTERRUPTED keep dismissible `OperationProgress` with
  message/code / retry guidance (local terminal surface; not bootstrap-dependent)
- **Rework:** `SourceActionsMenu` implements ArrowUp/Down, Home/End, Escape +
  focus restoration under `role="menu"`

## Source-scope query substrate

- `POST /v1/workspaces/{id}/query` accepts optional `source_ids`
- Omitted → all ACTIVE sources; `[]` rejected; unknown/inactive fail closed
- Logical source_ids → document_ids server-side; client document_ids not accepted
- No workspace mutation / If-Match / idempotency for scope
- Propagation through canonical stack:
  workspace query → query runtime → orchestrator → context → reranker → hybrid → dense + lexical
- Dense: native Qdrant `document_id` MatchAny filter before `limit=top_k`
- Lexical: real scoped BM25 (scoped N / avgdl / df / postings) before ranking
- **Rework 2:** fail-closed document-scope invariants after dense/lexical
  candidate materialization, before hybrid fusion, on hybrid output, and on
  hybrid-rerank input/output (`assert_document_scope` — never drop escaped hits)
- Downstream scope invariants + citation document-set enforcement
- Trace `ProductTraceSourceScope` on request summary; generic `/v1/query` remains `source_scope=null`
- Old traces without `source_scope` remain readable
- Duplicate-content / shared document_id attribution remains fail-closed when ambiguous within selected scope
- **Rework:** `source_ids` validated as safe identity tokens at the HTTP boundary
  (malformed → bounded 422; never SafeErrorDetails 500)
- **Rework:** canonical end-to-end isolation proof with
  `ALPHA_SCOPE_MARKER` / `BETA_SCOPE_MARKER` through dense→lexical→hybrid→
  reranker→context→generator→citations→trace

## Independent review rework

Disposition: **REWORK REQUIRED** against candidate
`0a5bb534440737bcf0b02b3630c4b175fd00c159` (rework 1 → `ae63c0f…`).

Rework 1 addressed F1–F7. Rework 2 addresses F8–F9 on the same branch.
Rework 3 addresses F10 (probe keep after explicit product API-key clear).
No merge, no self-accept, no 16D-B/C.

### Rework 2

- F8: dense / lexical / hybrid / hybrid-rerank fail-closed scope invariants +
  fault-injection tests (escaped `doc_beta` never reaches fusion/scoring/return)
- F9: field-specific endpoint/model lock semantics; partial-ownership product
  overlay; mixed-authority pending; partial-lock save/probe matrix

### Rework 3

- F10: `POST /v1/settings/generation/probe` with `api_key_action=keep` uses the
  product-managed key exactly when the product file owns `api_key` (including
  explicit null); omitted product key continues to inherit ACTIVE/YAML

## Tests run

Backend (selected):

- `tests/unit/app/test_slice16d_a_settings_capabilities.py` — passed (F1/F2/F6/F9/F10)
- `tests/unit/app/test_slice16d_a_query_scope.py` — passed (F3/F4/F8 + E2E)
- `tests/unit/app/test_slice15e_product_query_traces.py` — passed
- `tests/unit/app/test_slice16b_query_binding.py` — passed
- `tests/unit/app/test_slice16b_workspace_api.py` — passed (in earlier batch)
- `tests/unit/app/test_slice16b_rework_hardening.py` — passed
- `tests/unit/app/test_slice16b_integrity_rework.py` — passed
- `tests/unit/app/test_slice16b_publication_journal.py` — passed
- `tests/unit/app/test_slice15b_runtime_health.py` — passed
- `tests/unit/app/test_slice15g_container_packaging.py` — passed
- `tests/unit/test_dense_indexing.py` — passed
- `tests/unit/test_lexical_indexing.py` — passed
- `tests/unit/test_hybrid_retrieval.py` — passed
- `tests/unit/test_hybrid_rerank.py` — passed

Frontend (unchanged in rework 2; prior rework 1 evidence retained):

- `npm run lint` — passed
- `npm run typecheck` — passed
- `npm test` — 30 passed (incl. F5 FAILED/INTERRUPTED + F7 menu keyboard)
- `npm run build` — passed

## Known limitations

- No Ask/Evidence UI (16D-B)
- No Training Mode (16D-C)
- No live generator hot-swap (restart required)
- Favicon is a placeholder mark
- Manual browser smoke not claimed in this evidence package unless separately recorded

## Explicit non-scope

16D-B Ask/Evidence UX, 16D-C Training Mode, 16E–16H, Slice 17/18, 9G, M7 closeout, merge, and self-acceptance are **not** included.
