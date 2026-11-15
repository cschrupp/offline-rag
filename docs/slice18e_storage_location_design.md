# Slice 18E — Storage Location and Data Root Selection

**Design status:** scope Human accepted; design authorized; implementation not
authorized.  This document proposes the bounded design for independent review.

**Canonical design base:** `8591aacc1810ba7265014c55a4d9327f7f755a02`.

## Objective

Let a supported workstation user inspect Seneca's active durable data root,
choose a safe root for the next start, and understand whether Seneca must be
restarted.  The feature changes only the root used by the existing durable
path roles.  It does not move, copy, merge, or remove data.

The user-facing surface is **Settings → Storage**.  It must distinguish the
active root from a pending root, show restart-required state, and explain
whether configuration is editable or controlled by an operator/deployment.
The models root may be shown for context but remains read-only.

## Current repository seams

| Concern | Existing contract | Design consequence |
| --- | --- | --- |
| Configuration source | `OFFLINE_RAG_CONFIG` selects YAML. `load_settings()` loads YAML, rebases durable paths when `OFFLINE_RAG_DATA_DIR` is present, then applies product settings and environment authority. | Keep `OFFLINE_RAG_DATA_DIR` as the only data-root setting. Do not add a parallel root registry or settings file. |
| Durable path rebasing | `src/offline_rag/config/loader.py::_apply_data_dir()` rebases raw data, manifests, parsed data, corpora, chunks, chunk manifests, embeddings, index manifests, lexical indexes/manifests, Qdrant, traces, staging, locks, workspaces, Gold Lab, product settings, logs, and evaluation results beneath the supplied root. | One root selection applies to every existing durable role. No role can be hot-switched independently. |
| Startup ownership | The API builds one `ApplicationRuntime` from loaded settings. `ApplicationRuntime.start()` owns runtime initialization and directory creation; the process does not reload settings when an environment file changes. | Saving a root only persists next-start configuration. The active runtime and all open workspace state remain bound to the original root until restart. |
| Workstation installation | `install.sh --data-dir PATH` records `OFFLINE_RAG_DATA_DIR` in `~/.config/seneca/workstation.env` (under `XDG_CONFIG_HOME` when set), outside the data root. The generated systemd user service reads that file at process start. | For a recognized workstation install, persist the pending root in that existing environment file. Do not store it under the root being changed. |
| Workstation file writing | `scripts/workstation/configure.py` has a same-directory temporary-file writer that flushes and `fsync`s before `os.replace()`. Its installer writer creates a mode-0600 environment file and rejects conflicting installation bindings; it is not a product settings editor. | Add only a bounded `OFFLINE_RAG_DATA_DIR` update path in a later implementation. Preserve all unrelated environment entries and secret values; do not generalize this into arbitrary environment editing. |
| Existing Settings APIs | Generation and Compute expose `GET`/`PUT /v1/settings/...` with active/pending/locks/restart-required concepts. Their product settings are stored under `settings.paths.product_settings`, which itself is under the data root. | Add a separate Storage contract. Do not put the selected root in product settings, because changing the root would strand that preference. |
| Existing Settings UI | `ui/src/pages/SettingsPage.tsx` currently has Answer generation, Gold Lab authoring, and Compute sections. | Add a context-specific Storage section with explicit active/pending text, lock reason, restart notice, and no implication that data moved. |
| Container deployment | Docker sets `OFFLINE_RAG_DATA_DIR=/data`; Compose mounts the host-selected directory or volume at `/data`. A running container cannot change its host bind mount or volume mapping. | Container/operator deployments report `/data` (or the effective configured mount path) as deployment-controlled and expose no editable relocation control. Explain that relocation is a deployment reconfiguration. |
| Models | `OFFLINE_RAG_MODELS_DIR` is a distinct loader input and workstation environment value. | Display it read-only if useful. Do not alter it or imply that data-root changes relocate models. |

The source audit confirms that durable state is process-bound at startup and
that workstation persistence already lives outside `/data`. Existing
installation metadata also records the installation-time `data_root`; it is
not the loader authority. The later implementation must confirm its consumers
and prevent a stale metadata value from being presented as the active root.
`workstation.env` plus the process's effective startup configuration remain
the authority for this feature.

## Proposed behavior

### Ownership and supported surfaces

Storage is editable only when the running process can positively identify a
supported managed workstation installation and safely validate its existing
`workstation.env` persistence target. The effective process root must agree
with the bounded persisted root entry. The environment file is then the sole
product-write target for this setting.

If an explicit operator environment/configuration override shadows the
workstation value, the installation metadata or service binding is
unavailable, the environment file is malformed, or its current root does not
match the process's effective root, Storage is locked and reports a safe
reason. Presence of an environment variable alone is not proof of product
ownership. Do not add a generic ownership-mode variable or arbitrary-env UI.

Container deployments are always informational/locked because a container
cannot change its host mount. Direct development or other unmanaged installs
are also locked unless they satisfy the same positively verified workstation
ownership contract. No API may claim a requested host path is active in a
container.

### Settings API shape

Add a dedicated router with:

```text
GET /v1/settings/storage
PUT /v1/settings/storage
```

The GET projection should follow established Settings conventions and expose
at least:

```json
{
  "active": {"data_root": "/absolute/current/root"},
  "pending": null,
  "default_data_root": "/absolute/workstation/default",
  "models_root": "/absolute/read-only/models/root",
  "restart_required": false,
  "ownership": {
    "editable": true,
    "owner": "workstation",
    "reason": null,
    "deployment_controlled": false
  }
}
```

`pending` is either null or `{ "data_root": "..." }`. The exact enum/schema
names may follow current API conventions, but the response must keep active,
pending, ownership, deployment control, and restart state separate. In locked
or unrooted custom configurations, report the effective root only when it can
be derived without pretending independently configured path roles share one
root; otherwise return an explicit unavailable/locked state. Do not expose
environment-file contents, credentials, or unrestricted filesystem details.

PUT accepts only the candidate data-root field. It rejects unknown fields,
requires workstation ownership, validates the candidate, and atomically
updates only `OFFLINE_RAG_DATA_DIR` in the existing workstation environment
file. It returns the unchanged active root, the new pending root, and
`restart_required=true`. It never switches the runtime or migrates data. A
save equal to the active root is an idempotent no-op that clears any differing
pending value using the same bounded writer and reports no restart required.

Saving must not invoke `systemctl` or restart the server. The UI explains that
the new location applies after the user restarts Seneca. Existing `seneca
restart`/systemd-user lifecycle remains the restart mechanism.

### Data-root selection semantics

The API validates and saves a location choice; it does not perform data
movement:

```text
choose empty/new root → next start initializes a fresh Seneca data set there
choose compatible existing Seneca root → next start reopens that data set
old root → remains untouched
```

The UI must say plainly: **Changing the storage location does not move your
existing data.** There is no implicit migration, merge, deletion, garbage
collection, or cleanup. An explicit “Move current data” flow is deferred and
requires separate authorization.

### Fail-closed candidate validation

Validation occurs before persistence. The detailed implementation must:

1. Require a non-empty absolute Linux path. Do not silently expand a relative
   path, Windows path, or unsafe spelling into an accepted target.
2. Reject filesystem roots, regular files, unsupported filesystem objects,
   malformed paths, and an unavailable/malformed workstation environment.
3. For an existing directory, perform a bounded create/write/flush/fsync,
   same-directory rename, directory-fsync, and cleanup probe. For a new target,
   require an existing writable parent and probe create/rename/fsync there
   without initializing the new Seneca root during Save.
4. Compare resolved path identities to reject equality/ancestor/descendant
   overlap with application/release/package roots, the models root, and the
   workstation configuration/persistence root. The candidate must not contain
   or be contained by the environment file or its installation directory.
5. Treat the current root as a no-op when selected exactly. Reject a candidate
   nested inside or above the current root, because both create ambiguous
   recursive ownership. The former active root is otherwise left untouched.
6. Classify an existing target as empty/new, compatible existing Seneca data,
   or non-empty/unrecognized. Accept only the first two. Compatibility must be
   established from the repository's current durable directory roles and
   workspace/catalog structures using read-only inspection; directory names
   alone are not sufficient evidence. Do not invent a marker format or mutate
   a candidate to make it appear compatible.
7. Return bounded user-facing validation reasons. Do not leak exception text,
   environment values, or arbitrary absolute paths in logs/traces.

Canonical resolution is for overlap and identity checks, not silent repair.
If symlinks or a filesystem class make the actual target ambiguous, fail
closed. Qualification on one filesystem does not establish support for
network shares, Windows-native paths, or all `/mnt/<drive>` mounts.

The save operation probes filesystem capabilities and persists configuration;
the next application startup creates the durable role directories using the
existing runtime initialization. No scientific/model/security/performance
campaign is implied by these checks.

## WSL and container presentation

The backend accepts Linux/WSL absolute paths only. `/home/...` and `/mnt/d/...`
are examples of syntax, not qualification claims for a particular mounted
filesystem. Do not use a browser folder picker: a browser cannot supply a
trusted backend host path. Any `/mnt/<drive>` compatibility statement requires
specific qualification before public documentation.

For Docker/container profiles, the UI should present a locked summary such as:

```text
Data location: /data
Deployment controlled
To relocate Seneca data, change the host bind mount or volume and restart
the deployment.
```

## Proposed implementation boundary

The implementation should add one Storage API/UI path and a narrowly scoped
workstation environment update helper, reusing the existing config loader,
`WorkstationLayout`, environment parser, and atomic-write conventions. It must
not add another data-root architecture, route through product settings under
the current root, or modify the active `ApplicationRuntime.settings` object.

No changes are proposed to workspace storage layout, Qdrant, retrieval,
embedding, reranking, Gold, generation, model provisioning, container mounts,
or the installer `--data-dir` contract. Existing installs created with
`--data-dir` remain compatible.

## Qualification plan for a separately authorized implementation

Provider-free deterministic tests and bounded local qualification should cover:

- current active-root projection and workstation default root;
- pending-root projection, idempotent save, and restart-required state;
- save persistence surviving API process restart and then becoming active;
- atomic bounded update of only `OFFLINE_RAG_DATA_DIR`;
- preservation of unrelated environment entries, comments where supported,
  permissions, and secret values without logging them;
- empty/new-root selection and compatible existing-root selection;
- non-empty unrecognized, missing-parent, file, root, overlap, symlink/ambiguous,
  and failed write/rename/fsync rejection;
- operator environment override, malformed/unavailable environment file,
  unmanaged install, and Docker locked/informational state;
- Settings Storage UI active/pending/restart/locked disclosures;
- unchanged installer `--data-dir` behavior;
- restart applying the selected root while the previous root remains byte-for-
  byte untouched.

Tests must establish that no runtime path changes before restart and that
requests continue to use the original active root until the process starts
again. Do not run a new scientific, model, security, or performance campaign
for this feature.

## Renumbered Slice 18 sequence

```text
18A — Engineering Evidence Reconciliation
     COMPLETE / HUMAN ACCEPTED / PROMOTED
18B Revision 2 — Workstation Distribution
     COMPLETE / HUMAN ACCEPTED / PROMOTED
18C — Universal Workstation Distribution & Release Optimization
     COMPLETE / HUMAN ACCEPTED / PROMOTED
18D — Product Metrics Audit and Explainability
     COMPLETE / HUMAN ACCEPTED / PROMOTED at 8591aacc1810ba7265014c55a4d9327f7f755a02
18E — Storage Location and Data Root Selection
     SCOPE HUMAN ACCEPTED / DESIGN AUTHORIZED /
     IMPLEMENTATION NOT AUTHORIZED
18F — Canonical Documentation and Portfolio Narrative
     PLANNED / NOT AUTHORIZED
18G — Public Release and Demo Assembly
     PLANNED / NOT AUTHORIZED
Milestone 7 closeout
     NOT AUTHORIZED
```

18E is design-only at this handoff. Implementation requires separate Human
authorization after review of this design. 18F, 18G, and Milestone 7 closeout
remain outside this authorization.
