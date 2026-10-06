# Slice 16D-A — Seneca Product Foundation & Query-Scope Substrate

```text
STATUS: COMPLETE / ACCEPTED
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT REVIEW: PASSED
MANUAL UI SMOKE: PASSED

ACCEPTED IMPLEMENTATION SHA:
4f8962f2893ab433e6ea269ad54e46f67771ca70

AUTHORIZED BASELINE:
185d3e3d2bd472ffaddf72cfddc49c7e38a3a146

A1 AUTHORITY:
5060e2aeb4825f265072a1f870c3c963eace3b30

Branch: implementation/16d-a-seneca-product-foundation-query-scope

F1–F12: CLOSED
```

Human acceptance applies **exactly** to SHA
`4f8962f2893ab433e6ea269ad54e46f67771ca70`.

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

- PENDING settings require process restart to become ACTIVE
- Capabilities expose ACTIVE generation only
- Restart-required messaging in Settings when PENDING differs from ACTIVE

## Compact workspace UX

- Compact source rail; source `⋮` actions menu; de-emphasized metadata via Edit modal
- Operation completion UX for FAILED / INTERRUPTED restore paths
- **Rework 4 (F11):** reusable `ModalDialog` visible Close (×) control; Edit
  workspace Save changes closes on success and restores focus to Edit
- **Rework 5 (F12):** Edit workspace Remove confirmation is inline in
  `WorkspaceMetadataForm` (no nested `ConfirmDialog` / second modal)

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

## Acceptance

Independent review: **PASSED** (F1–F12 **CLOSED**).

Manual UI smoke: **PASSED**

- Edit workspace opens/closes visibly
- Save changes closes successfully
- Remove workspace inline confirmation
- Cancel returns to edit surface
- Escape closes the one Edit dialog
- no nested modal

Smoke paths exercised:

- Edit → Remove workspace → Cancel
- Edit → Remove workspace → Escape
- Edit → Save changes

## Independent review rework (historical)

Disposition during review: **REWORK REQUIRED** against earlier candidates
(historical narrative only; accepted SHA below supersedes).

Rework 1 addressed F1–F7. Rework 2 addresses F8–F9 on the same branch.
Rework 3 addresses F10 (probe keep after explicit product API-key clear).
Rework 4 addresses F11 (Edit workspace / ModalDialog close UX from manual test).
Rework 5 addresses F12 (nested Remove confirmation inside Edit modal).

Accepted implementation SHA: `4f8962f2893ab433e6ea269ad54e46f67771ca70`.

### Rework 2

- F8: dense / lexical / hybrid / hybrid-rerank fail-closed scope invariants +
  fault-injection tests (escaped `doc_beta` never reaches fusion/scoring/return)
- F9: field-specific endpoint/model lock semantics; partial-ownership product
  overlay; mixed-authority pending; partial-lock save/probe matrix

### Rework 3

- F10: `POST /v1/settings/generation/probe` with `api_key_action=keep` uses the
  product-managed key exactly when the product file owns `api_key` (including
  explicit null); omitted product key continues to inherit ACTIVE/YAML

### Rework 4

- F11: `ModalDialog` always exposes a visible Close button (`aria-label="Close"`,
  disabled while `busy`); successful Edit workspace Save changes closes the
  dialog; failed save keeps it open

### Rework 5

- F12: Workspace removal confirmation is inline inside the single Edit
  workspace `ModalDialog` (Cancel restores edit controls; confirm runs existing
  delete mutation; Escape closes Edit only; no nested alertdialog / second
  focus trap). Source-removal `ConfirmDialog` paths unchanged.

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

Frontend (rework 5 / F12; retained for accepted candidate):

- `npm run lint` — passed
- `npm run typecheck` — passed
- `npm test` — 38 passed (incl. F5/F7/F11 + F12 inline remove)
- `npm run build` — passed
- `git diff --check` — passed

## Known limitations

- No Ask/Evidence UI (16D-B)
- No Training Mode (16D-C)
- No live generator hot-swap (restart required)
- Favicon is a placeholder mark

## Explicit non-scope

16D-B Ask/Evidence UX, 16D-C Training Mode, 16E–16H, Slice 17/18, 9G, M7 closeout,
and merge are **not** included. 16D-B / 16D-C remain **NOT AUTHORIZED**.
