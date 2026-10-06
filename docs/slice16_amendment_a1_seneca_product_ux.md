# Slice 16 Design Amendment A1 — Seneca Product UX

```text
SLICE 16 DESIGN AMENDMENT A1

STATUS: ACCEPTED / LOCKED
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT REVIEW: PASSED

ACCEPTED AMENDMENT SHA:
5060e2aeb4825f265072a1f870c3c963eace3b30

BASELINE:
a18868e84f52994d6b529537c48f5da549711d20

ORIGINAL SLICE-16 AUTHORITY:
ACCEPTED / LOCKED
e2e7475076ad18d4c4ae8d939389ceeffdeff6d8

16A: COMPLETE / ACCEPTED
16B: COMPLETE / ACCEPTED
16C: COMPLETE / ACCEPTED / SEALED

16D-A: NOT AUTHORIZED / NOT STARTED
16D-B: NOT AUTHORIZED / NOT STARTED
16D-C: NOT AUTHORIZED / NOT STARTED
16E–16H: NOT AUTHORIZED

SLICE 16 OVERALL:
IN PROGRESS / NOT COMPLETE
```

## Authority relationship

Amendment A1 **supplements** S16-D01 … S16-D35. It does **not** invalidate or
rewrite the original accepted authority except where this amendment explicitly
adds or refines a future product contract.

- Original locked authority:
  [`docs/slice16_design_authority.md`](slice16_design_authority.md)
  at `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`
- Sealed 16C closeout baseline: `a18868e84f52994d6b529537c48f5da549711d20`
- Accepted 16C implementation: `936e41446eb1e3697f6b7d245659831f19cf0613`
- **Accepted Amendment A1 SHA:** `5060e2aeb4825f265072a1f870c3c963eace3b30`

Human acceptance applies **exactly** to SHA
`5060e2aeb4825f265072a1f870c3c963eace3b30`.

This amendment is now **supplemental locked** Slice-16 design authority.
Acceptance of A1 does **not** authorize implementation of 16D-A, 16D-B, or
16D-C; those phases remain **NOT AUTHORIZED** until separate explicit
implementation authorization.

Substantive decisions A1-D01 … A1-D17 are frozen by this acceptance; closeout
does not alter them.

---

## A1-D01 — Product brand: Seneca

Freeze the public product identity:

| Role | Value |
| --- | --- |
| Public product name | **Seneca** |
| Product descriptor | **Grounded knowledge workspace** |
| Canonical presentation | **Seneca — Grounded knowledge workspace** |

Technical identities remain unchanged:

| Identity | Value |
| --- | --- |
| GitHub repository | `offline-rag` |
| Python package | `offline_rag` |
| Internal architecture references | OfflineRAG |

A1 does **not** authorize a repository or package rename.

### Visual identity

Initial logo direction:

- minimalist Greek stoa / colonnade;
- calm, scholarly, structured;
- recognizable at favicon size;
- restrained geometry;
- no requirement for final artwork in A1.

Future implementation may initially use a simple project-owned placeholder
stoa mark which can later be replaced without architectural consequence.

### Brand usage

- browser title;
- favicon;
- application shell;
- future release / portfolio presentation.

Canonical browser / product title:

```text
Seneca — Grounded knowledge workspace
```

---

## A1-D02 — Product UX direction

Freeze the shift from an administration-oriented source page toward a
knowledge-workspace surface.

Primary workspace conceptual layout:

```text
┌────────────────────┬──────────────────────────────┬───────────────────────┐
│ SOURCES            │ ASK                          │ EVIDENCE              │
│                    │                              │                       │
│ capacity           │ question / answer workspace  │ citations / source    │
│ source selection   │                              │ inspection            │
│ add source         │                              │                       │
│ source list        │                              │                       │
└────────────────────┴──────────────────────────────┴───────────────────────┘
```

This is conceptual layout authority, **not** permission to copy NotebookLM.

### Source rail

Sources **SHOULD** become compact list rows rather than large CRUD cards.

Example conceptual row:

```text
☑ Week13.pdf                                  ⋮
```

Optional secondary information **MAY** include:

```text
11 MiB · Version 1
```

### Checkbox meaning

The source checkbox means: **participates in query scope**.

It does **not** mean:

- active / inactive workspace membership;
- delete;
- depublication;
- reindex;
- snapshot mutation.

### Three-dot menu meaning

`⋮` is the source-management menu.

Required actions:

- Rename source
- Replace current version
- Remove source

CRUD controls **SHOULD NOT** permanently dominate every source row.

### Workspace metadata

Title / description remain editable, but the large permanent metadata form
**SHOULD** no longer dominate the normal knowledge-workspace view.

Use a secondary edit / settings action.

### Operation completion UX

Successful durable operations **SHOULD** collapse into compact / transient
notifications or an operation tray.

They **SHOULD NOT** indefinitely occupy the top of the workspace after
completion.

Failure / interrupted states must remain adequately visible.

---

## A1-D03 — Source capacity contract

Existing backend safety defaults remain:

| Limit | Value |
| --- | --- |
| max active sources | `32` |
| max bytes per document | `26,214,400` bytes = **25 MiB** |
| max active source bytes | `104,857,600` bytes = **100 MiB** |

These are:

- real backend limits;
- deployment / product guardrails;
- **not** ordinary user preferences.

### Future internal configuration (16D-A)

16D-A **SHOULD** make these defaults explicit in the internal deployment YAML,
conceptually:

```yaml
api:
  max_files_per_ingest: 32
  max_bytes_per_document: 26214400
  max_total_upload_bytes: 104857600
```

Existing validated `AppSettings` and environment overrides remain authoritative.

A1 does **not** implement this YAML change.

### UI presentation

Replace developer-facing wording such as “Limits (backend authoritative): …”
with compact capacity information.

Example:

```text
Sources    3 / 32
Storage    12.4 / 100 MiB
```

Near upload selection:

```text
Maximum file size: 25 MiB
```

Current active byte consumption is:

```text
sum(current active source.byte_size)
```

No additional persistent scientific state is required merely to calculate usage.

---

## A1-D04 — Read-only capabilities contract

To prevent frontend / backend constant drift, 16D-A **MUST** introduce a
read-only effective-capabilities surface.

Conceptual route:

```text
GET /v1/capabilities
```

Exact naming **MAY** be finalized during 16D-A design implementation if
equivalent.

Minimum product-facing payload:

```json
{
  "source_limits": {
    "max_active_sources": 32,
    "max_bytes_per_source": 26214400,
    "max_active_source_bytes": 104857600
  }
}
```

It **MAY** also safely expose non-secret **active / effective** runtime
capability / state needed by product surfaces.

Requirements:

- values come from the **active / effective** backend runtime (`AppSettings`
  as loaded into the running ApplicationRuntime);
- **MUST** describe active/effective capability;
- **MUST NOT** report an unapplied pending generator configuration as if it
  were active;
- no secrets;
- no filesystem paths;
- no vault / corpus internals;
- no private API keys;
- browser does not hard-code effective capacity after this endpoint exists.

Backend remains authoritative.

### Capabilities versus Settings state

Keep `GET /v1/capabilities` focused on **active / effective** runtime state.

A separate Settings-specific API **MAY** carry:

- active non-secret configuration;
- pending non-secret configuration;
- `restart_required`;
- field lock / authority metadata.

Exact Settings route naming remains a 16D-A implementation decision.

Do **not** return secrets from either surface.

---

## A1-D05 — Seneca Settings surface

Seneca **MUST** provide a Settings entry, visually appropriate as a cog / gear
in the application shell.

The Settings surface is deliberately narrow. It is **not** a generic editor for
every OfflineRAG YAML / scientific parameter.

### Initial editable runtime / product settings (16D-A)

16D-A **SHOULD** support:

- generation enabled state where semantically valid;
- OpenAI-compatible generation endpoint;
- generation model;
- optional API key;
- timeout where useful;
- connection / model probe;
- active and (where applicable) pending non-secret runtime information;
- restart-required indication.

Primary intended providers include:

- Ollama;
- other OpenAI-compatible local servers;
- OpenAI-compatible private-network servers within accepted endpoint classes.

### Generator configuration / approval authority (normative)

A1 freezes who may approve a newly entered endpoint / model so Settings can
configure a local/LAN generator without weakening allow-list security.

#### Product-managed standalone mode

For the intended standalone Seneca deployment, the local user is also the
product operator.

When a generator endpoint / model is **not** locked by a higher-authority
operator override, Seneca **MAY** persist both:

- the selected endpoint / model; and
- the corresponding **product-managed approval** necessary to use them.

This is **not** permission for arbitrary Internet access.

Under strict-offline operation, product-managed endpoint approval **MUST** be
bounded to accepted local / private endpoint classes.

At minimum distinguish:

- loopback;
- Docker host bridge;
- explicit private-LAN endpoint.

Public Internet endpoints **MUST NOT** become approved merely because a user
typed one into Settings while strict-offline is active.

Exact private-network validation mechanics may be finalized in 16D-A, but the
fail-closed policy is normative.

In standalone product-managed mode, configuring a user’s own Ollama (or other
approved OpenAI-compatible local / private) server through Settings **MUST** be
able to succeed without requiring a separate environment-variable edit merely
to approve the address just entered — provided the candidate passes network
policy and validation.

#### Operator-managed / locked mode

Environment / operator configuration remains higher authority.

If endpoint / model / approval policy is supplied or locked by that authority:

- Settings **MUST NOT** override it;
- Settings **MUST NOT** create a product-managed approval that bypasses it;
- affected controls **SHOULD** be shown as read-only / locked;
- UI **SHOULD** explain that the effective value is operator-controlled.

#### Model approval

Apply the same authority distinction to models.

In standalone product-managed mode:

- a model returned by the explicitly approved / tested local or private
  endpoint **MAY** become product-approved when the user explicitly saves /
  selects it.

In operator-managed mode:

- UI **MUST NOT** bypass an operator-controlled approved-model list.

Do **not** silently approve arbitrary model identifiers without endpoint /
model validation.

### Not ordinary user-editable

Do **not** expose normal controls for:

- source capacity limits;
- embedding model;
- chunking strategy;
- chunk sizes;
- dense retrieval parameters;
- lexical configuration;
- fusion settings;
- reranker thresholds / configuration;
- context assembly scientific policy;
- retrieval-recovery scientific policy;
- versioned prompt contracts;
- benchmark / evaluation controls.

Those remain governed scientific / runtime configuration unless separately
designed.

---

## A1-D06 — Settings security contract

Existing generation security **MUST NOT** be weakened.

Current accepted behavior includes:

- approved endpoint allow-list;
- approved model allow-list;
- rejection of unapproved endpoint / model where configured.

A1 clarifies that, in **product-managed standalone mode**, Seneca itself may
write the product-managed approvals needed for a validated local / private
selection (see A1-D05). That remains an allow-list mechanism — not removal of
allow-lists.

A Settings UI **MUST NOT** simply permit arbitrary Internet endpoints under a
strict-offline profile.

Support for a LAN server must preserve explicit authorization via:

- product-managed approval after validation (standalone, unlocked fields); or
- pre-existing operator / environment approval (locked / operator-managed).

Public Internet destinations remain forbidden under strict-offline operation.

Do **not** silently reinterpret strict-offline as arbitrary network access.

Operator / environment locks always win and cannot be bypassed from the UI.

---

## A1-D07 — Settings persistence / restart semantics

Do **not** require live hot-swapping of the active runtime in 16D-A.

Preferred initial lifecycle:

```text
Settings UI
    ↓
validate candidate values (prospective policy)
    ↓
Test connection / model  (does not activate or persist)
    ↓
explicit Save
    ↓
persist product settings + product-managed approvals under /data
    ↓
restart required
    ↓
next application start loads the effective configuration
```

This avoids mutating live generator / runtime clients while requests may be
active.

### Configuration precedence

```text
base YAML defaults
       ↓
persistent Seneca product settings / product-managed approvals
       ↓
environment / operator overrides and locks
```

Highest authority wins.

If a setting is locked by an operator / environment override, the UI **SHOULD**
make that state clear rather than pretending the user can change it.

### ACTIVE versus PENDING configuration

Because A1 uses restart-to-apply semantics, freeze:

```text
ACTIVE
  Configuration actually loaded into the running ApplicationRuntime.
  Example:
    endpoint: http://host.docker.internal:11434/v1
    model: qwen3:8b

PENDING
  Persisted product settings that differ from the active runtime and require
  restart.
  Example:
    endpoint: http://192.168.1.40:11434/v1
    model: qwen3:14b

  Restart required
```

`GET /v1/capabilities` **MUST** describe **ACTIVE / effective** runtime
capability and **MUST NOT** report an unapplied pending generator as if it were
active.

A Settings read surface **MAY** expose non-secret pending values.

It **MUST** indicate:

- whether restart is required;
- active value;
- pending value where safe;
- whether a field is operator locked.

API keys remain write-only / masked and **MUST NOT** be returned as plaintext.

After successful restart, pending settings that became effective are reflected
as ACTIVE.

If an environment / operator override shadows a persisted product value, the UI
must show the effective operator-controlled value and must not claim that the
shadowed value is active.

### Secrets

API keys:

- **MUST NOT** be returned by read APIs;
- **MUST NOT** appear in logs / traces;
- **MUST NOT** be serialized into public evidence;
- should be write-only or masked;
- persistence mechanism must use the safest practical local-product treatment
  available within this single-user architecture.

A1 does not require a full enterprise secrets manager.

---

## A1-D08 — Connection test

Settings **SHOULD** provide **Test connection**.

This probe **MUST NOT** activate the candidate configuration.

A connection probe **MUST NOT** require the candidate to already be present in
the currently **active** allow-list; otherwise a new valid endpoint can never
be tested.

Instead the backend **MUST** validate the candidate against the **prospective**
Settings policy:

1. syntax;
2. endpoint class / network policy;
3. operator locks;
4. reachability;
5. OpenAI-compatible `/models` behavior where supported;
6. selected model availability.

A successful probe:

- does **NOT** activate the candidate;
- does **NOT** modify the running generator;
- does **NOT** itself persist approval unless the later explicit Save action
  does so.

Save remains an explicit user action.

The existing OpenAI-compatible probe behavior **SHOULD** be reused rather than
duplicated in the browser.

Browser **MUST NOT** directly probe Ollama / model servers.

Probe goes through the Seneca backend.

---

## A1-D09 — Per-query source selection

This is a **core** 16D Ask requirement.

The current accepted workspace query DTO accepts only:

```json
{
  "question": "..."
}
```

A1 adds a backward-compatible selected-source scope.

Conceptual request:

```json
{
  "question": "What does the selected material say about ventilation?",
  "source_ids": [
    "src_...",
    "src_..."
  ]
}
```

### Semantics

| `source_ids` | Meaning |
| --- | --- |
| omitted | query all current active sources |
| non-empty | query exactly that source subset |
| empty | invalid / no-source query |

For empty `source_ids`:

- UI **SHOULD** disable Ask before request;
- server **SHOULD** reject rather than reinterpret as “all sources”.

Unknown source: fail closed.

Inactive / superseded source identity: fail closed.

A source selection is **not** a workspace mutation.

It **MUST NOT**:

- increment workspace revision;
- alter workspace source membership;
- create a new scientific snapshot;
- rebuild indexes;
- alter source lineage.

---

## A1-D10 — Query-scope binding

Workspace query still binds first to:

```text
workspace.current_snapshot_id
```

The selected `source_id` set is then resolved against the source identities
valid for that bound workspace snapshot.

Conceptual binding:

```text
workspace
   ↓
current_snapshot_id N
   ↓
selected source_ids
   ↓
source versions valid in N
   ↓
document_ids
   ↓
retrieval scope
```

Do **not** trust client-supplied `document_id`.

Client sends logical `source_id`.

Server resolves scientific identities.

This preserves the stable user-facing source abstraction.

---

## A1-D11 — Filter before retrieval ranking

Selected-source filtering **MUST** occur before candidate ranking.

### Forbidden

```text
retrieve globally
→ take top-k
→ remove unchecked-source hits afterward
```

because selected documents may have already been displaced.

### Required conceptual pipeline

```text
                     selected document_ids
                            │
             ┌──────────────┴──────────────┐
             ↓                             ↓
      dense retrieval               lexical retrieval
      scoped to docs                scoped to docs
             └──────────────┬──────────────┘
                            ↓
                          fusion
                            ↓
                         rerank
                            ↓
                    context assembly
                            ↓
                       generation
```

An excluded source **MUST NOT** influence:

- dense candidates;
- lexical candidates;
- fusion;
- reranker inputs;
- context / evidence units;
- citations;
- generated answer.

This requires acceptance tests with unique markers.

---

## A1-D12 — Query trace provenance

Query traces **MUST** record effective source scope.

At minimum preserve enough identity to answer:

> Which workspace sources were permitted to participate in this answer?

Recommended:

- selected logical `source_ids`;
- resolved `document_ids` or equivalent scientific identities;
- workspace revision / snapshot binding.

Omitted / all-source queries should still have an unambiguous trace
representation.

This is provenance, not conversational memory.

---

## A1-D13 — Source-selection UI state

Checkbox selection is presentation / query state.

For the initial implementation it **MAY** be:

- workspace-local browser state;
- session / local presentation persistence.

It **MUST NOT** become scientific workspace membership.

It **MUST NOT** be sent as hidden conversational history.

Recommended UX:

- all active sources selected initially;
- Select all;
- easy deselection;
- clear selected count;
- Ask disabled at zero selected sources.

If a selected source disappears due to a real workspace mutation, the UI
**MUST** reconcile against refreshed active-source state.

---

## A1-D14 — Revised 16D phase decomposition

Amend the implementation sequence to:

```text
16A [ACCEPTED]
 ↓
16B [ACCEPTED]
 ↓
16C [ACCEPTED / SEALED]
 ↓
16D-A [NOT AUTHORIZED]
 ↓
16D-B [NOT AUTHORIZED]
 ↓
16D-C [NOT AUTHORIZED]
 ↓
16E
 ↓
16F
 ↓
16G
 ↓
16H
```

Top-level Slice 16 remains one coherent design.

### 16D-A — Seneca Product Foundation & Query-Scope Substrate

Future scope:

- Seneca brand application;
- provisional stoa favicon / logo;
- canonical title / tagline;
- compact source rail;
- source `⋮` CRUD menu;
- de-emphasized metadata management;
- compact operation completion UX;
- source count + active MiB capacity presentation;
- explicit internal YAML capacity defaults;
- read-only capabilities endpoint;
- Settings cog / page;
- generation runtime configuration API / persistence;
- product-managed local/LAN approval vs operator-locked mode;
- endpoint / model probe against prospective policy;
- ACTIVE / PENDING configuration and restart-required semantics;
- source-scoped query DTO;
- server-side source → document binding;
- dense + lexical pre-ranking scope enforcement;
- scoped-query provenance / tracing.

16D-A **MUST NOT** implement the full Ask / Evidence experience merely because
the query substrate exists.

Its main purpose is to make that substrate provably correct.

### 16D-B — Ask & Evidence Workspace

Future scope:

- Sources | Ask | Evidence desktop layout;
- responsive drawers;
- source-selection checkboxes;
- single-turn Ask;
- answer rendering;
- citation chips;
- evidence panel;
- source preview;
- Current / Historical snapshot visibility;
- abstention as successful safety outcome;
- session-local visual history.

Inherited existing prohibitions:

- no conversational memory;
- no hidden chat history as query context;
- no fabricated PDF highlights.

### 16D-C — Training Mode

Future scope:

- instructor-oriented Training Mode;
- saved prompts;
- hide / reveal answer;
- hide / reveal evidence;
- presentation-friendly typography;
- optional fullscreen / presentation layout.

Training Mode remains **required** Slice-16 scope.

It is subdivided for implementation governance, not deferred or removed.

---

## A1-D15 — 16H capacity validation

Add to future 16H integration / acceptance scope:

Empirically validate practical source / corpus capacity on a declared local
reference machine.

Evaluate representative envelopes, potentially:

- 32 sources;
- 64 sources;
- 128 sources;
- increasing active-source byte totals.

Exact benchmark matrix may be determined later.

Goal:

- validate whether release defaults remain sensible;
- do **not** promise NotebookLM-equivalent cloud capacity;
- do **not** change limits merely by intuition.

Any future increase in defaults should be evidence-backed.

---

## A1-D16 — UX language

Seneca should avoid developer / internal language in normal product surfaces.

Prefer:

- Sources
- Storage
- Add sources
- Rename source
- Replace current version
- Remove source
- Settings
- Ask
- Evidence

Avoid prominently showing:

- backend authoritative
- corpus
- Qdrant
- snapshot internals
- vault object
- RAG implementation terminology

Technical / provenance views **MAY** expose appropriate identifiers where they
help advanced inspection.

---

## A1-D17 — NotebookLM benchmarking position

NotebookLM is a UX reference, **not** a product clone.

Useful patterns adopted conceptually:

- compact source rail;
- source-selection checkboxes;
- secondary CRUD behind overflow menu;
- central knowledge-working surface;
- evidence / source inspection alongside answers.

Do **not** copy:

- Google visual identity;
- proprietary assets;
- exact layout measurements;
- copyrighted UI artwork.

Seneca retains its own brand / design system.

---

## Explicit non-authorization

```text
A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT REVIEW: PASSED
16D-A: NOT AUTHORIZED / NOT STARTED
16D-B: NOT AUTHORIZED / NOT STARTED
16D-C: NOT AUTHORIZED / NOT STARTED
16E–16H: NOT AUTHORIZED
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
SLICE 16 OVERALL: IN PROGRESS / NOT COMPLETE
```

Acceptance of this amendment locks supplemental design authority only. It does
**not**:

- authorize 16D-A / 16D-B / 16D-C implementation;
- mutate `ui/`, `src/`, `tests/`, `config/`, packaging, or Docker;
- rewrite sealed 16A / 16B / 16C implementation evidence;
- merge to main;
- authorize Slice 17 / Slice 18 / 9G / M7 closeout.
