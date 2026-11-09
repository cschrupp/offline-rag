# REL-03-P0 Live OpenRouter Qualification

**Final disposition:** `REL03_P0_LIVE_SMOKE_PASS`

## Identity

- Candidate SHA: `ac55095fb9ded47123fa56d52b42502f5fd3a43e`
- Branch: `feature/rel-03-p0-external-inference-demo-profile`
- Workspace: Recipes (`ws_bc83cab6b52b4223935ca3bb102ed6fa`)
- Capture directory identity: `rel03-p0-final-capture-iobjo37y` (preserved local capture)
- Started: `2026-11-09T03:04:16.373056Z`
- Clean worktree preflight: `true`
- Profile / endpoint / model: `portfolio_openrouter` / `https://openrouter.ai/api/v1` / `~deepseek/deepseek-flash-latest`
- Evidence reduction used only preserved local artifacts; **no additional external inference calls** were made.

## Readiness

- Seneca readiness probe recognized the exact configured alias `~deepseek/deepseek-flash-latest`: **PASS** (HTTP 200).
- Readiness: `GET` `https://openrouter.ai/api/v1/models`; captured full URL path `/api/v1/models`; configured base path `/api/v1`; normalized path `/models`; model `None`; HTTP 200; auth present `true`; auth value persisted `false`; response_format `false`; chat_template_kwargs `false`.

## Smoke A — Grounded Recipes answer

- Exact question: Which type of beans does the Brazilian Bean Stew (Feijoada) recipe use?
- Exact answer: The Brazilian Bean Stew (Feijoada) recipe uses canned black beans (2 cans, 19.7 oz. each, drained and rinsed).
- HTTP 200; status `answered`; origin `sources`.
- Citations: 1; cited source: brazilian-bean-stew-feijoada-gloria-goodtaste.pdf (`src_707b45eec222462ba5a1e26127881ef6`).
- Query trace: `trace_da082075e8e74b8a83118fd09ad8c8d2`; trace confirms generator invoked: `true`.
- Smoke A: `POST` `https://openrouter.ai/api/v1/chat/completions`; captured full URL path `/api/v1/chat/completions`; configured base path `/api/v1`; normalized path `/chat/completions`; model `~deepseek/deepseek-flash-latest`; HTTP 200; auth present `true`; auth value persisted `false`; response_format `true`; chat_template_kwargs `false`.

## Smoke B — Conversation transformation

- Operation: `summarize_answer`
- Exact transformed answer: It uses two 19.7-oz. cans of black beans, drained and rinsed.
- HTTP 200; status `answered`; `answer_origin=conversation`.
- Citations: 0; query trace: absent; conversation trace: `trace_5d88d895f8ee47c893749c916c24bd6a`.
- Resolver invoked: `false`; outcome: `bypassed`.
- Provenance: “From this conversation — not re-checked against your sources”
- Smoke B: `POST` `https://openrouter.ai/api/v1/chat/completions`; captured full URL path `/api/v1/chat/completions`; configured base path `/api/v1`; normalized path `/chat/completions`; model `~deepseek/deepseek-flash-latest`; HTTP 200; auth present `true`; auth value persisted `false`; response_format `false`; chat_template_kwargs `false`.

## Smoke C — Gold authoring

- Project / operation / authoring run: `goldproj_c7e7b3a88a2447218051370eafa7c563` / `wop_40e8aad1f08644aa9a1540d0e808b161` / `authorrun_1c470a3dd62f45e1b001776461a9362b`.
- Exact proposed query: How many pounds of peeled and deveined large shrimp are required for the Greek Style Shrimp Sauté?
- Category / tags: `Recipe` / `Shrimp, Greek, Sauté, Ingredients`.
- Proposal count succeeded: 1; reviewable case count: 1.
- Validation: strict parser and existing quality gate accepted; reviewable case produced.
- Persisted artifact identity: `authorrun_1c470a3dd62f45e1b001776461a9362b`; repository-relative artifact: `data/corpora/wsc_bc83cab6b52b4223935ca3bb102ed6fa/gold_authoring/runs/authorrun_1c470a3dd62f45e1b001776461a9362b.json`.
- Smoke C: `POST` `https://openrouter.ai/api/v1/chat/completions`; captured full URL path `/api/v1/chat/completions`; configured base path `/api/v1`; normalized path `/chat/completions`; model `~deepseek/deepseek-flash-latest`; HTTP 200; auth present `true`; auth value persisted `false`; response_format `true`; chat_template_kwargs `false`.

## Transport path normalization

The captured full URL path was `/api/v1/chat/completions`; the configured base path was `/api/v1`; the base-relative Chat Completions path is `/chat/completions`. This is path normalization of the captured URL, not a runtime endpoint mismatch.

## Secret audit

A fresh audit covered 25 persisted qualification files: the 15 files in the preserved capture, 9 application artifacts modified by this run, and this final evidence document. The unchanged `.env` was used only as the local key source and was not included as an artifact.

- Actual API-key occurrences: **0**.
- Persisted Authorization/Bearer value patterns: **0**.
- Auth-presence booleans are recorded; header values and request headers are not.
- `.env` unchanged during the live run: `true`.

## Default-profile regression

- Profile: `standalone_ollama`; `strict_offline=true`.
- OpenRouter was rejected by the endpoint network policy and ordinary authoring policy.
- This was configuration-only; no model call was made.

## Qualification history

- Attempt 1: runtime A/B/C succeeded; response and transport preservation was insufficient.
- Attempt 2: runtime A/B/C succeeded; path serialization failed before evidence was preserved.
- Attempt 3: runtime A/B/C succeeded and stage records were preserved. Its initial reducer returned STOP because it expected an untracked file path rather than Git's directory-level report and did not normalize the captured URL path relative to the configured base.
- Evidence-only salvage verified the preserved response, trace, Gold artifact, and raw sanitized transport records. The reducer defects were corrected; **no new external inference was performed**.

There were no transient retries. This is a bounded live smoke, not broad performance or scientific qualification. No production code/configuration changed, and no promotion was performed.

REL03_P0_LIVE_SMOKE_PASS
