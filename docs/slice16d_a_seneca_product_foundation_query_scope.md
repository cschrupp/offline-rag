# Slice 16D-A — Seneca Product Foundation & Query-Scope Substrate

STATUS: IMPLEMENTATION EVIDENCE CANDIDATE  
HUMAN ACCEPTANCE: PENDING

Authorized baseline: `185d3e3d2bd472ffaddf72cfddc49c7e38a3a146`  
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

## Settings API

- `GET /v1/settings/generation` — ACTIVE + PENDING + locks + restart_required; never returns API key
- `POST /v1/settings/generation/probe` — prospective probe; no persist; no runtime mutation; closed reason codes
- `PUT /v1/settings/generation` — persist only; no live hot-swap; re-probe when enabling
- API key actions: `keep` | `set` | `clear`
- Errors: `SETTINGS_INVALID` (422), `SETTINGS_LOCKED` (409), `SETTINGS_PROBE_FAILED`

## ACTIVE / PENDING

- ACTIVE = current ApplicationRuntime generation settings
- PENDING = effective future after restart (locked fields keep operator ACTIVE values)
- Capabilities reports ACTIVE only
- Fresh `load_settings` after restart applies product overlay under env authority

## Compact workspace UX

- Compact header with capacity summary (`N / max sources · MiB / max MiB`)
- Source rows with accessible `⋮` overflow menu (Rename / Replace / Remove)
- Workspace metadata behind secondary Edit dialog
- Add sources behind modal; preserves 16C idempotency + durable ops
- No source-selection checkboxes (16D-B)
- Compact terminal Ready tray; no permanent success card domination

## Source-scope query substrate

- `POST /v1/workspaces/{id}/query` accepts optional `source_ids`
- Omitted → all ACTIVE sources; `[]` rejected; unknown/inactive fail closed
- Logical source_ids → document_ids server-side; client document_ids not accepted
- No workspace mutation / If-Match / idempotency for scope
- Propagation through canonical stack:
  workspace query → query runtime → orchestrator → context → reranker → hybrid → dense + lexical
- Dense: native Qdrant `document_id` MatchAny filter before `limit=top_k`
- Lexical: real scoped BM25 (scoped N / avgdl / df / postings) before ranking
- Downstream scope invariants + citation document-set enforcement
- Trace `ProductTraceSourceScope` on request summary; generic `/v1/query` remains `source_scope=null`
- Old traces without `source_scope` remain readable
- Duplicate-content / shared document_id attribution remains fail-closed when ambiguous within selected scope

## Tests run

Backend (selected):

- `tests/unit/app/test_slice16d_a_settings_capabilities.py` — passed
- `tests/unit/app/test_slice16d_a_query_scope.py` — passed
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

Frontend:

- `npm run lint` — passed
- `npm run typecheck` — passed
- `npm test` — 27 passed
- `npm run build` — passed

## Known limitations

- No Ask/Evidence UI (16D-B)
- No Training Mode (16D-C)
- No live generator hot-swap (restart required)
- Favicon is a placeholder mark
- Manual browser smoke not claimed in this evidence package unless separately recorded

## Explicit non-scope

16D-B Ask/Evidence UX, 16D-C Training Mode, 16E–16H, Slice 17/18, 9G, M7 closeout, merge, and self-acceptance are **not** included.
