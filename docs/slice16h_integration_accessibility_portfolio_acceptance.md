# 16H — Integration / Accessibility / Portfolio Acceptance

**Status:** 16H COMPLETE / ACCEPTED
**Envelope:** `16H-ACCEPTANCE-ENVELOPE-AUTH-001`
**Independent review:** 16H-IR-003 — ACCEPT
**Human acceptance:** 16H-HA-001 — ACCEPTED
**Exact Human-accepted technical subject:** `01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`
**Prior candidate (IR-001 NOT ACCEPTED):** `71185d327b76db8cc804d3afb2c4845414043ed6`
**Slice 16 overall:** IN PROGRESS / NOT COMPLETE (16H acceptance does not auto-close Slice 16)

## 1. Authority / exact baseline

| Item | Value |
|------|--------|
| Repository | `cschrupp/offline-rag` |
| Canonical branch | `main` |
| Starting baseline SHA | `f1b6e27bfbc9b156552073304210da0c5d9af32e` |
| Working branch | `acceptance/16h-integration-accessibility-portfolio` |
| Design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Amendment A1 | `5060e2aeb4825f265072a1f870c3c963eace3b30` LOCKED |
| Amendment A2 | `dce3456e519cb6c96570e20f5af800d00cafb5a7` LOCKED / SEALED |
| Amendment A3 | `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73` LOCKED / SEALED |
| Amendment A4 | materialization `d12f6322ef13915002b49dcc8f1211052a66dcc5` LOCKED / SEALED |
| 16A–16F | COMPLETE / ACCEPTED |
| 16G | IMPLEMENTATION COMPLETE / ACCEPTED (I6 subject `cc7ff520…`, IR-002 ACCEPT) |
| 9G / Slice 17 / Slice 18 / M7 closeout | NOT AUTHORIZED |
| `ALLOW_PRODUCTION` | UNCHANGED / EMPTY |

## 2. Candidate SHA and footprint

Candidate SHA is recorded at commit time in the handoff (this file lands in the candidate commit).

Primary artifacts:

- `docs/slice16h_integration_accessibility_portfolio_acceptance.md` (this document)
- `ui/src/test/slice16h_integration_acceptance.test.tsx`
- `scripts/validate_seneca_static_bundle.py`
- `scripts/run_slice16h_capacity_validation.py`
- `scripts/run_slice16h_container_smoke.py`
- `tests/unit/app/test_slice16h_static_bundle.py`
- `tests/unit/app/test_slice16h_supersession.py`
- `docs/evidence/slice16h_*.json`

Production-code corrections in this envelope: **NONE**.

Packaging-only build support (not product semantics): `deploy/Dockerfile`
accepts an optional BuildKit `build_ca` secret for TLS-intercepted dependency
fetches. The secret is mount-only and is never copied into the image. The UI
builder exposes it through `NODE_EXTRA_CA_CERTS` only for the `npm ci` RUN; the
Python build combines it with the system CA bundle in a temporary
`/tmp/offlinerag-build-ca-bundle.pem` used only for the pip-install RUN and
removes that file before the layer commits. No custom CA is installed into the
final runtime system trust store.

## 3. Cross-surface integration (Family A)

**Disposition: PASS** (automated harness + rendered navigation)

Harness `ui/src/test/slice16h_integration_acceptance.test.tsx` proves:

- Overview → Workspaces → Engineering → Settings → Gold Lab navigation coherence
- Ask fails closed with empty source selection (no query POST)
- Question Bank JSON round-trip remains local-only (no backend mutation)
- Gold Lab Expert Work fails closed for unapproved presentations (`ALLOW_PRODUCTION` empty)
- Engineering loads static evidence and never hits `/eval/`
- Managed-operation reconnect / failure / interrupted UX
- Keyboard Tab reaches primary navigation without pointer

Rendered-browser (Vite `127.0.0.1:5173` + API `127.0.0.1:8080`) exercised live workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d` (B1 Upload Smoke): Sources / Ask / Evidence / Training Mode /
Add sources affordances present; Engineering Evaluation → Architecture nav present; Settings and
Gold Lab surfaces load with labeled controls.

A4 preserved: conversation export ≠ source ingestion (harness + accepted A4 regression suite).

## 4. WCAG 2.2 AA internal audit matrix (Family B)

**Disposition: PASS** as an **internal project audit** against applicable WCAG 2.2 AA on required
Slice-16 surfaces. **Not** an external accessibility certification.

Verification methods:

- **DOM/TL:** Vitest + Testing Library (16H harness + accepted I6 / 16D suites)
- **Rendered:** Cursor IDE Chromium CDP against live Vite UI (`docs/evidence/slice16h_rendered_browser_evidence.json`)
- **CSS:** focus-visible / reduced-motion / skip-link retained in `ui/src/styles/global.css`

| Success criterion (AA focus) | Applicability | Surface(s) | Method | Evidence | Result | Notes |
|-----------------------------|---------------|------------|--------|----------|--------|-------|
| 2.1.1 Keyboard | Yes | Global shell, workspace, Gold Lab, Engineering, Settings | TL + browser | 16H-C harness; I6 keyboard preflight; Menu/Escape on mobile | PASS | |
| 2.1.2 No Keyboard Trap | Yes | Dialogs/drawers/menu | TL + browser | Escape closes mobile Menu; accepted dialog suites | PASS | |
| 2.4.7 Focus Visible | Yes | Interactive controls | CSS + TL | `:focus-visible` retained | PASS | Visual ring not certified by JSDOM alone |
| 2.4.3 Focus Order | Yes | Primary nav / workspace | TL tab loops | Harness reaches Primary links | PASS | |
| 1.3.1 Info & Relationships | Yes | Headings/landmarks/labels | a11y tree | `navigation Primary`, regions Sources/Conversation/Evidence; form labels on Settings/Gold Lab/Workspaces | PASS | |
| 4.1.2 Name, Role, Value | Yes | Controls | a11y tree | Named Menu, Add sources, Ask, Send, Training Mode, etc. | PASS | |
| 4.1.3 Status Messages | Yes | Operations | TL | Operation tray Running/Failed/Interrupted | PASS | |
| 1.4.1 Use of Color | Yes | Status | UI copy | Status text accompanies state | PASS | |
| 1.4.3 Contrast (text) | Yes | Shell/content | Computed styles | Body 15.19:1; H1 15.56:1; nav 16.69:1 | PASS | Sampled pairs; not exhaustive palette audit |
| 1.4.11 Non-text Contrast | Yes | Critical controls | CDP computed styles | Add sources focus outline white on `#175CD3` ≈ 5.99:1 (≥ 3:1) | PASS | Representative critical control; not every glyph |
| 2.5.8 Target Size (AA) | Yes | Critical controls | CDP bounding boxes @1440 | Add sources 226×44; Send 73×44; Training Mode 144×44 (all ≥ 24×24) | PASS | Critical controls measured |
| 1.4.10 Reflow | Yes | Critical surfaces | CDP viewports | 320 CSS px workspace: no page-level overflowX | PASS | |
| 1.4.4 Resize Text | Yes | Workspace | `font-size: 200%` / CSS zoom @1440 | No page-level overflowX; header/ask/add remain | PASS | Extreme 320+CSS-zoom noted separately; not 1.4.10 failure |
| 1.4.12 Text Spacing | Yes | Workspace | Injected WCAG spacing overrides | No overflowX; Ask/Add sources/header remain visible | PASS | See `wcag_f002_rework` in browser evidence JSON |
| 3.3.1 Error Identification | Yes | Forms / ops | TL + accepted suites | Failed ops / policy gates expose text | PASS | |
| 2.4.11 Focus Not Obscured (AA) | Yes | Source menu | CDP `elementFromPoint` | Focused “Rename source” in `role=menu` in viewport and not obscured | PASS | Critical keyboard/menu flow |
| 2.3.3 Animation from Interactions | Yes | Global CSS | CSS | `prefers-reduced-motion: reduce` present | PASS | |
| 1.1.1 Non-text Content | Yes | Icons/favicon | Bundle + labels | Favicon local; controls named | PASS | Decorative icons rely on adjacent names |

## 5. Keyboard-only acceptance (Family C)

**Disposition: PASS**

- 16H harness: Tab reaches Primary navigation without pointer
- I6 Gold Lab keyboard preflight remains authoritative for Gold Lab deep flows (referenced, not duplicated)
- Rendered: mobile Menu expands Primary links; Escape collapses Menu
- Workspace: Ask textbox, Sources checkboxes, Add sources, Training Mode, Evidence are keyboard-reachable controls in the accessibility tree

## 6. Responsive / zoom acceptance (Family D)

**Disposition: PASS** (responsive); **PASS** (200% text/zoom on representative desktop workspace)

Runtime: Chromium CDP via Cursor IDE browser; Vite UI + live API.

| Viewport | Surface | Page overflowX | Notes |
|----------|---------|----------------|-------|
| 1440×900 | Overview / workspace | No | Header + full Primary nav |
| 1024×768 | Workspace | No | Ask + Add sources present |
| 768×1024 | Workspace | No | Sources/Evidence mobile affordances |
| 390×844 | Workspace | No | Header + Menu; Primary in Menu |
| 320 CSS px | Workspace | No | Reflow target; no page-level horizontal overflow |
| 1440 + 200% text | Workspace | No | `font-size: 200%` |
| 1440 + CSS zoom 200% | Workspace | No | Controls remain |

Residual: CSS zoom 200% at 320 px showed `scrollWidth > clientWidth`; treated as extreme combination, not failure of the required reflow target alone.

Question Bank height containment remains covered by accepted A4/16D suites (not re-opened).

## 7. Source supersession integration (Family E)

**Disposition: PASS**

New proof: `tests/unit/app/test_slice16h_supersession.py`

- Add version N with `OLD_VERSION_UNIQUE_MARKER`
- Replace → N+1 with `NEW_VERSION_UNIQUE_MARKER`
- `source_id` stable; version/document_id advance; snapshot advances
- Current source content and active vault blob: OLD absent, NEW present
- Published pointer tracks N+1 snapshot

Query-path dense/lexical/rerank/citation marker isolation remains covered by accepted
16B supersession suite (`test_f6_supersession_old_marker_absent` and related), re-run in the
16H regression matrix. Historical Gold snapshot binding is not weakened.

## 8. Operation recovery UX (Family F)

**Disposition: PASS**

16H harness:

- F1 reconnect: durable locator → operation tray rediscovery (Running)
- F3 failure: Failed visible; not Succeeded
- F4 interrupted: Interrupted + retry guidance

Accepted 16B managed-operation / publication-journal suites remain binding for crash/fail-closed
semantics (no auto-publish of unfinished candidates).

## 9. Strict-offline / static assets (Family G)

**Disposition: PASS**

- Vite production build produced `ui/dist`
- `scripts/validate_seneca_static_bundle.py` → `docs/evidence/slice16h_static_bundle.json` (`ok: true`)
- HTML/CSS refs local; fonts bundled (56 woff*); no blocked presentation CDNs
- Configurable generator URL strings in JS are ignored per envelope

## 10. Container delivery (Family H)

**Disposition: PASS** (current-SHA image build + runtime/static smoke)

IR-001/IR-002 F001 packaging trust:

- Optional build-host CA is supplied only as BuildKit secret `id=build_ca` (never `COPY`'d).
- `.dockerignore` excludes `deploy/certs/*.crt`, `deploy/certs/*.pem`, `deploy/wheelhouse/`.
- Dependency RUNs may temporarily use the secret for npm/pip TLS; final runtime trust store
  remains the standard image CA bundle (custom CA ABSENT).
- Smoke (`slice16h-container-smoke-v3`): `/health` live (not model-ready), SPA/static,
  same-origin `/v1` JSON surface, `/data` RW + `/models` RO, `--network none` static probe,
  runtime trust-store marker absence.

Evidence: `docs/evidence/slice16h_container_smoke.json`.

## 11. Portfolio evidence consistency (Family I)

**Disposition: PASS**

- Manifest contract hash-pinned; families present: retrieval, generation, recovery, security, performance
- Engineering UI loads `/evidence/engineering-evidence-v1.json` only; no browser `/eval/` execution
- Rendered Engineering page shows recovery Disabled / efficacy Insufficient; LangGraph deferred;
  quality vs latency separated; security campaign fail-closed narrative preserved
- No scientific results updated; no evaluation rerun
- **F004:** `uv run pytest tests/unit/test_slice16e_engineering_evidence.py -q` → **21 passed**
  (rebuilds manifest, byte identity, `actual_sha256 == expected_sha256`)

## 12. No-fake-data audit (Family J)

**Disposition: PASS**

Harness scans production `ui/src/**` (excluding `test/`) for imports of `ui/src/test/**`, `mockApi`,
`installFetchMock`, and canned-answer markers. `ALLOW_PRODUCTION` remains `[]`.
Accepted hash-pinned Engineering evidence is legitimate static evidence, not fake runtime data.

## 13. Final Slice-16 integration harness (Family K)

**File:** `ui/src/test/slice16h_integration_acceptance.test.tsx`
**Count / result:** recorded in §17 (expected 13 tests).

## 14. Capacity reference machine (Family L)

From `docs/evidence/slice16h_capacity_observations.json`:

| Field | Value |
|-------|--------|
| OS / kernel | Linux 6.18.33.2-microsoft-standard-WSL2 |
| CPU | x86_64 (16 logical) |
| Physical RAM | 33507909632 bytes (~31.2 GiB) |
| GPU | not_declared_for_this_run |
| Storage | WSL2_virtual_disk_or_host_fs |
| Python | 3.14.5 |
| Node | v22.23.3 |
| Docker | Docker version 29.1.3 |
| Embedding / rerank / generation | FakeEmbedder / FakeReranker / FakeGenerator (observation harness) |
| Exact git SHA at run | `f1b6e27bfbc9b156552073304210da0c5d9af32e` |

## 15. Capacity matrix and measurements

Accepted defaults unchanged: 32 files / 25 MiB / 100 MiB.

| Envelope | Result | Highlights |
|----------|--------|------------|
| 32 sources × 64 KiB (~2 MiB) | SUCCEEDED | query HTTP 200 / `query_ok=true` (grounded_answer_v2 FakeGenerator) |
| 32 sources × 3 MiB (~96 MiB near-cap) | SUCCEEDED | `reported_active_bytes=100663296`; ingest ~355.6 s; query ~222.1 s; query HTTP 200 / `model_abstain`; RSS peak ~982 MiB |
| Over-100 MiB admission (8×14 MiB) | REFUSED `upload_too_large` @ 422 | Guardrail holds |
| 64 sources | NOT TESTABLE WITHOUT CONTRACT/CONFIG CHANGE (`max_files_per_ingest=32`) | 422 `too_many_files` |
| 128 sources | NOT TESTABLE WITHOUT CONTRACT/CONFIG CHANGE | 422 `too_many_files` |

**Capacity conclusion:** `CURRENT DEFAULTS SUPPORTED BY OBSERVATION`

F003 closed: legal near-cap workload proven; query probe required to succeed under current
answer contract (performance values remain observational).

## 16. Residual risks / deferrals

1. Build-host optional `deploy/certs/*.crt` is local-only (gitignored); CI/other hosts without
   TLS interception need no certs.
2. Extreme 320 px + 200% CSS zoom horizontal overflow observation (not a 1.4.10 reflow failure).
3. 64/128 active-source envelopes not measurable without authorized limit/config change.
4. Legacy F6/F12 supersession tests still emit grounded_answer v1 FakeGenerator JSON (existing debt);
   16H supersession proves the pipeline under v2.
5. 9G / Slice 17 / Slice 18 / M7 closeout remain unauthorized.

## 17. Exact test commands / results

| Command | Result |
|---------|--------|
| `npm test -- src/test/slice16h_integration_acceptance.test.tsx` | **13 passed** (prior + rework regression) |
| Slice-16 UI regression cluster (prior IR candidate) | **141 passed** |
| `npm run typecheck` / `npm run build` | PASS (rework validation) |
| `uv run pytest tests/unit/app/test_slice16h_*.py tests/unit/app/test_slice15g_container_packaging.py` | PASS |
| `uv run pytest tests/unit/test_slice16e_engineering_evidence.py -q` | **21 passed** (F004) |
| `uv run python scripts/validate_seneca_static_bundle.py` | PASS |
| `uv run python scripts/run_slice16h_capacity_validation.py` | PASS; near-cap + query_ok; conclusion CURRENT DEFAULTS SUPPORTED BY OBSERVATION |
| `uv run python scripts/run_slice16h_container_smoke.py` | PASS after current-SHA `deploy/Dockerfile` build (F001) |
| `uv run ruff check` (touched Python) | PASS |
| `git diff --check` (16H paths) | PASS |

IR-001 findings F001–F004 closed in this rework commit.

Not claimed: FULL REPOSITORY GREEN.

## 18. Production fixes

NONE.

## 19. Explicit downstream boundaries

- Scientific semantics: UNCHANGED
- New public backend contracts: NONE
- New dependencies: NONE
- `ALLOW_PRODUCTION`: UNCHANGED / EMPTY
- 9G: DEFERRED / NOT AUTHORIZED
- Slice 17 / 18: NOT AUTHORIZED
- M7 closeout: NOT AUTHORIZED
- Slice 16: IN PROGRESS / NOT COMPLETE
- Do not update `PORTFOLIO_DEMO.md` under this envelope

## 20. Human acceptance / canonicalization record

| Item | Value |
|------|--------|
| Human acceptance | 16H-HA-001 — ACCEPTED |
| Independent review | 16H-IR-003 — ACCEPT |
| Exact Human-accepted technical subject | `01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10` |
| Acceptance envelope | `16H-ACCEPTANCE-ENVELOPE-AUTH-001` |
| 16H | COMPLETE / ACCEPTED |
| Slice 16 | IN PROGRESS / NOT COMPLETE |
| 9G / Slice 17 / Slice 18 / M7 closeout | NOT AUTHORIZED |
| `ALLOW_PRODUCTION` | UNCHANGED / EMPTY |

Technical subject `01a4a984…` remains the accepted implementation even if a
docs-only acceptance-record successor is created for live-projection sync.
