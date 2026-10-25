# Large-source capacity architecture

Authority: `S16-K-LARGE-SOURCE-CAPACITY-DESIGN-AUTH-001`  
Canonical base: `f5c9423c471162923b3bbbfe804687db27551745`  
Branch: `design/16k-large-source-capacity`  
Disposition: **DESIGN COMPLETE / READY FOR INDEPENDENT REVIEW**  
(not accepted; implementation **NOT AUTHORIZED**)

## Provenance

Prior feasibility note (immutable):
[`docs/design/large_source_capacity_followup.md`](large_source_capacity_followup.md)
— terminal `CAPACITY_DESIGN_READY`; `SAFE_LIMIT_INCREASE_PROVEN = false`.

Motivating Human-UAT case: ~227 MiB technical handbook rejected under current
supported envelope:

- `api.max_bytes_per_document` = **25 MiB** (`26_214_400`)
- `api.max_total_upload_bytes` = **100 MiB** (`104_857_600`)

Future **qualification target** (not a product claim):
**≥512 MiB per individual technical source**.

This document freezes the implementation-ready architecture and the evidence
required before any limit raise. It does **not** authorize implementation,
benchmarks, or config changes.

---

## 1. Objective and preferred data path

Remove unnecessary whole-file Python `bytes` materialization on Seneca-owned
stages while preserving document identity, full-replace publication, managed
operations, and retrieval/embedding science.

Preferred path:

```text
HTTP multipart stream
        ↓
durable disk spool + incremental SHA-256   (already present)
        ↓
path/stream-based vault publication
        ↓
path-based desired-set reconstruction
        ↓
path-based ingestion/parser contract
        ↓
bounded-memory parse/chunk/index pipeline
        ↓
existing publication semantics
```

---

## 2. Verified current facts (canonical base)

### Already good

`app/workspace/upload_spool.py`:

- streams multipart parts to disk;
- hashes with incremental `digest.update`;
- records `byte_size` and `content_sha256`.

Do **not** replace with an in-memory upload design.

### Whole-file RAM surfaces still present

| Surface | Behavior |
|---|---|
| `lifecycle.SourceUpload.load_bytes` / ADD plan / vaulting | `Path.read_bytes()` / vault `load_bytes()` |
| `RawSourceVault.put_bytes` / `load_bytes` | whole-file `bytes`; `put_bytes` re-reads for integrity |
| `projection.materialize_desired_sources` | sequential `load_bytes` → `path.write_bytes(data)` |
| `ingest._validate_document_identities` | `item.absolute_path.read_bytes()` |
| `ingest_upload.spool_local_files` | `path.read_bytes()` → `write_bytes` |
| `ingestion/pipeline.py` | `source.absolute_path.read_bytes()` before parse |
| `DoclingPdfParser.parse(path, *, source_bytes, document_id)` | Docling reads **path**; `source_bytes` is a Seneca interface requirement |
| TXT/Markdown parsers | same `source_bytes` contract via `ingestion/base.py` |

Identity today: `document_id_from_bytes` / `content_hash_from_bytes` in
`core/ids.py` → `doc_<sha256>` from full `bytes`.

---

## 3. Architectural invariants (MUST preserve)

1. **Document identity** — equivalent source bytes → same `doc_<sha256>`;
   no filename-based identity; display name remains presentation metadata.
2. **Scientific semantics** — parsing meaning, chunking policy, dense/lexical
   indexing, fusion, reranking, query behavior, snapshot identity, accepted
   CPU/CUDA embedding architecture unchanged.
3. **Workspace semantics** — SOURCE_ADD / REPLACE / REMOVE, idempotency,
   managed-operation lifecycle, publication journal, candidate isolation,
   source-version lineage, Current/Historical behavior unchanged.
4. **Fail-closed** — no partially published source; no partially updated live
   snapshot; interrupted work remains recoverable/quarantinable.

---

## 4. Full-replace boundary (D00)

**Decision D00 — retain full-replace publication semantics.**

Bounded-memory copying/parsing is a different problem from incremental
scientific indexing. Analysis at this design stage does **not** prove
full-replace incompatible with ≥512 MiB-class sources when vault/projection/
parser stages are path-based.

Therefore:

- keep Slice-15 / 16K-C full-replace desired-set rebuild;
- optimize RAM on copy/identity/parse contracts;
- if later measurement shows aggregate reconstruction I/O or wall-clock is the
  dominant product blocker, open a **separate** incremental-indexing design
  tranche with evidence — do not conflate that redesign into L1–L3.

`Full-replace semantics changed: NO` for this architecture.

---

## 5. Frozen design decisions

### D01 — Streaming / path identity API

Introduce project-owned primitives alongside existing byte APIs:

```text
content_hash_from_path(path, *, chunk_size=DEFAULT) -> str   # hex SHA-256
document_id_from_path(path, ...) -> str                      # doc_<hex>
content_hash_from_stream(readable, ...) -> str               # optional
```

Requirements:

- bounded RAM (`O(chunk_size)`, default e.g. 1–8 MiB);
- bit-identical SHA-256 vs `content_hash_from_bytes` / `document_id_from_bytes`
  for the same file contents (golden tests: empty rejected; small; multi-chunk;
  ≥2× chunk_size);
- deterministic; pure; no I/O side effects beyond reading the path/stream.

Existing `*_from_bytes` remain for small/internal uses and as the oracle.

**Identity ownership:**

| Layer | Role |
|---|---|
| Upload spool / local spool | **Establish** identity (incremental hash while writing) |
| Vault put | **Verify** digest matches declared/spool identity; store meta.hash |
| Projection | **Reuse** meta.hash; optional cheap size/mtime check; full rehash only on mismatch suspicion |
| Ingest validation | **Reuse** spool/vault identity; do not re-`read_bytes` solely to recompute ID |
| Parser | **Consume** established `document_id` + `content_hash`; do not re-hash for ID |

Avoid redundant full-file hashing at every layer.

### D02 — Vault path API

Add:

```text
RawSourceVault.put_path(
    workspace_id,
    source_path: Path,
    *,
    display_name: str,
    content_type: str | None = None,
    object_id: str | None = None,
    expected_content_hash: str | None = None,
) -> VaultObjectMeta
```

Requirements:

- no whole-file RAM allocation (streamed copy into temp object path, then
  atomic rename into vault object slot — reuse existing atomic helpers);
- streamed integrity verification (hash while copying **or** verify against
  `expected_content_hash` from spool, then optional second streaming verify);
- metadata meaning identical to `put_bytes` (`content_hash`, `byte_size`,
  display name, content type);
- on failure: no valid meta pointing at incomplete object (delete partial
  object; do not write meta);
- server-generated object IDs; client basename never controls FS path.

**Compatibility:** keep `put_bytes` / `load_bytes` for small fixtures and
legacy callers. Large-source product flows use `put_path` and
`object_path` / `open_object` (read-only path handle) instead of `load_bytes`.

Add:

```text
RawSourceVault.object_path(workspace_id, object_id) -> Path  # after meta check
RawSourceVault.verify_object(workspace_id, object_id) -> VaultObjectMeta
```

`verify_object` streams hash vs meta without returning bytes.

### D03 — Projection materialization

Replace conceptual `load_bytes → write_bytes` with:

```text
shutil.copyfile(src_vault_object, scratch_path)   # or copyfileobj with fixed buffer
```

plus meta.hash / size checks already present.

- Correctness **must not** require reflink/hard-link.
- Optional optimization: `os.link` / `reflink` copy when same filesystem and
  policy allows; always fall back to streamed copy.
- Scratch paths remain server-generated; display name metadata unchanged.
- Peak RAM in this loop: `O(copy_buffer)` + meta objects — **independent of
  aggregate workspace bytes \(A\)**.

### D04 — Local-file spool path

`spool_local_files()` must stream:

```text
for each local file:
  stream-copy to staging with incremental SHA-256
  enforce transport limits when apply_transport_limits=True
  skip HTTP envelope limits when reconstructing from vault (16K-C)
  duplicate detection via document_id set (unchanged semantics)
```

Preserve empty/unsupported/identity-conflict fail-closed behavior.

### D05 — Ingestion identity validation

`_validate_document_identities` must not call `absolute_path.read_bytes()`.

Prefer:

- trust spool record (`document_id`, size, hash) produced at spool time;
- optional streaming verify if a debug/integrity flag is set;
- conflict detection remains set-membership on `document_id`.

Pipeline discovery should carry established identity into parse rather than
re-deriving from a full buffer.

### D06 — Parser interface

Migrate `PdfParser` / text / markdown contracts from:

```text
parse(path, *, source_bytes: bytes, document_id: str)
```

to:

```text
parse(
    path,
    *,
    document_id: str,
    content_hash: str,
)
```

- Docling continues to read **path** only.
- `ParsedDocument` / downstream `Document.content_hash` meaning unchanged
  (hex SHA-256 of canonical source bytes).
- TXT/Markdown: read from path in bounded fashion **or** stream into parser
  without retaining a second full buffer beyond what the parser itself needs;
  identity/`content_hash` still come from D01, not from re-hashing ad hoc.
- Same core identity semantics across media types — no PDF-only shortcut that
  diverges from `doc_<sha256>`.

Compatibility shim: temporary wrapper accepting `source_bytes` for tests may
exist during L3 migration, then removed before L5.

---

## 6. Memory model

Symbols:

| Symbol | Meaning |
|---|---|
| \(S\) | size of source currently processed |
| \(L\) | largest active source in the workspace |
| \(A\) | aggregate active source bytes |
| \(D(S)\) | Docling (or other parser) working set — **unmeasured** |
| \(B\) | fixed copy/hash chunk buffer (MiB-class constant) |
| \(E\) | embedding/index working set (existing dual-backend profiles; unchanged) |

### After proposed refactor (Seneca-owned stages)

| Stage | Peak RAM (architectural) |
|---|---|
| Multipart spool | \(O(B)\) (already) |
| Streaming identity | \(O(B)\) |
| Vault `put_path` / verify | \(O(B)\) |
| Projection copy | \(O(B)\) per sequential source; **not** \(O(A)\) |
| Local spool copy | \(O(B)\) |
| Ingest identity validate | \(O(1)\) metadata (no full buffer) |
| Parser | \(D(S)\) third-party; Seneca should not add an extra \(S\)-sized `bytes` |
| Chunk/embed/index | existing \(E\); not redesigned here |

**Target property:** source-copy / identity / vault stages use \(O(B)\) RAM;
workspace reconstruction RAM is independent of \(A\); parser remains
Docling-dependent \(D(S)\).

**Disk/I/O complexity** still scales with \(A\) under full-replace (every
desired source is recopied/re-fed). That is accepted under D00 until measured
otherwise.

Do **not** invent RSS numbers. Peak RSS for 100/250/512 MiB inputs is an
L5 measurement output, not a design claim.

---

## 7. Disk model

Typical simultaneous durable/scratch copies for SOURCE_ADD:

| Copy | Lifetime | Notes |
|---|---|---|
| Upload / local spool file | until vault success + cleanup | durable scratch |
| Vault object | durable | authoritative raw bytes |
| Projection scratch | until candidate ingest done | rewrite all desired sources |
| Candidate / stage corpus | until publish or fail | existing Slice-15 behavior |
| Published corpus / indexes | durable live snapshot | existing semantics |

Safe opportunities (correctness-preserving):

- **move/rename** spool → vault temp when same filesystem (optional);
- **streamed copy** otherwise;
- **optional reflink** never required;
- **early spool cleanup** after successful vault meta commit + journal
  durability (reuse existing orphan-spool quarantine for failures).

Amplification is multiplicative in workspace size under full-replace; design
does not eliminate that without D00 revision.

---

## 8. Capacity qualification plan (design only — NOT RUN)

Future campaign authority (separate): measure before any supported claim.

### Inputs

| Size | Role |
|---|---|
| 25 MiB | control (current ceiling) |
| ~100 MiB | near mid |
| ~250 MiB | near motivating UAT class |
| ~512 MiB | design target |

Prefer generated/safe PDF fixtures; include ≥1 representative real technical
handbook when locally available (e.g. ~227 MiB UAT case).

### Record per run

- process peak RSS;
- parser-stage peak RSS where observable;
- elapsed parse time; total ingest time;
- temporary disk peak; final disk growth;
- source count; page count; chunk count;
- backend/profile (`cpu_onnx_fp32_v1` / `cuda_fp16_v1` as applicable);
- terminal managed-operation result.

### Pass criterion for a supported claim

A size \(S^*\) may be claimed only if, on representative hardware:

- no Seneca-owned stage retains an \(S^*\)-sized Python `bytes` outside
  unavoidable third-party parser internals;
- operation completes fail-closed-correctly;
- peak RSS and disk stay within an explicit product envelope recorded in the
  campaign report;
- duplicate identity and full-replace publication checks pass.

This design authority **does not** run the campaign.

---

## 9. Product limit model

Do **not** ship incoherent pairs such as `512 MiB/file` with `100 MiB/request`.

Separate knobs (names illustrative; final values only after L5/L6):

| Concept | Role | Current |
|---|---|---|
| `max_bytes_per_source` | individual durable source | 25 MiB |
| `max_bytes_per_http_request` | multipart request envelope | 100 MiB |
| `max_active_source_bytes` | searchable-workload / workspace aggregate | today conflated with request total in capabilities — must be split |
| `max_active_source_count` | cardinality guard | existing file-count limits |
| `max_searchable_child_chunks` | post-parse workload (16K-C) | retain 16K-C model |
| temporary disk admission | preflight reserve | new (D07) |

Preserve 16K-C distinction: **transport capacity ≠ searchable-workload
capacity**. Reconstruction from vault must not re-apply HTTP request limits
(`apply_transport_limits=False` path already exists).

Candidate ranges for later qualification (non-binding):

- per-source target band: 256–512 MiB after L5 evidence;
- per-request ≥ per-source for single-file handbook upload;
- workspace aggregate set from disk + RSS evidence, not from per-source alone.

---

## 10. Disk-space admission (D07)

**Decision D07 — conservative disk preflight before expensive reconstruction.**

When estimated bytes needed exceed available space on the relevant filesystem:

- fail closed before vault/projection/candidate build when estimate is known;
- if size cannot be safely estimated, proceed only with explicit degraded
  policy **or** fail closed (prefer fail closed for large declared sizes).

Estimate (conservative, unmeasured multiplier \(k\) until L5):

```text
need ≈ k * (S_new + A_active) + fixed_index_slop
```

Filesystems that matter: staging, workspaces (vault), and any corpus/index
roots under `settings.paths`.

User-facing error: stable code (e.g. `storage_insufficient`) with message that
does not leak absolute paths; retryable after freeing disk.

Do not claim an exact \(k\) without measurement; design default \(k \ge 3\) as
a conservative placeholder for implementation, revised by L5.

---

## 11. Progress and UX

Reuse `ManagedOperationProgress` / existing ingest progress reporters.

Minimal stage mapping for large sources (names may alias existing steps):

| UX stage | Existing anchor |
|---|---|
| Uploading | HTTP spool (client + server) |
| Validating | identity / limits / duplicate checks |
| Storing source | vault `put_path` |
| Parsing | pipeline parse |
| Chunking | chunk phase |
| Building indexes | dense + lexical |
| Publishing | journal publish |

Do not redesign the UI. Ensure progress updates at stage boundaries so a
227–512 MiB job does not appear frozen for multi-minute silent gaps. If a
single stage (Docling) dominates wall time, emit heartbeat/`current` updates
from existing document-phase hooks where available.

---

## 12. Restart / failure recovery

| Stage | Durable | Scratch | On interrupt |
|---|---|---|---|
| Multipart spool | spool files under staging | — | orphan-spool quarantine (reuse) |
| Vault write | object only after integrity + meta | temp object | delete partial; no meta |
| Projection | — | work_dir tree | `rmtree` on failure (existing) |
| Parse / chunk / indexes | — | candidate tree | fail op; no live publish |
| Candidate publication | journal + published snapshot | candidate | existing atomic publish rules |

Retry: safe when identity/idempotency detects same `document_id` already
active (duplicate conflict) or when prior op left no published snapshot.
Managed-operation terminal states unchanged.

---

## 13. Security

Preserve:

- server-generated filesystem names;
- basename sanitization;
- no client-controlled storage paths;
- request-size admission (HTTP envelope);
- strict-offline; no remote Docling;
- no accidental unbounded parser concurrency.

Large-size support must not weaken validation or duplicate-identity checks.

---

## 14. Implementation slicing (outcome-sized)

| Slice | Outcome | Leaves repo |
|---|---|---|
| **L1** | Streaming identity + path-based vault primitives (`*_from_path`, `put_path`, verify) with golden hash tests | Coherent; product limits unchanged; old byte APIs remain |
| **L2** | Bounded-memory projection + `spool_local_files` streaming; lifecycle ADD uses `put_path` | Coherent; still ≤25 MiB product ceiling |
| **L3** | Parser/ingestion path contract migration; remove pipeline/`_validate` whole-file reads for identity | Coherent; science unchanged |
| **L4** | Instrumentation + qualification harness (RSS, disk, timings) | Harness only; no limit raise |
| **L5** | Bounded real capacity qualification (25/100/250/512) | Evidence packet; still no product claim until Human accept |
| **L6** | Product limit selection + capabilities/UI exposure | Only after L5 accept |

Each slice independently reviewable. L1–L3 are not microscopic
function-by-function chores; they are vertical slices of the data path.

---

## 15. Acceptance oracle (design)

| # | Question | Design answer |
|---|---|---|
| 1 | Can a 512 MiB source reach the parser without Seneca allocating a 512 MiB `bytes` outside unavoidable third-party parser internals? | **Yes**, under D01–D06 (Seneca stages \(O(B)\); \(D(S)\) remains Docling’s). |
| 2 | Canonical document identity unchanged? | **Yes** — same SHA-256 / `doc_<hex>` (D01). |
| 3 | Workspace reconstruction without whole-file RAM? | **Yes** — streamed/`copyfile` projection (D03). |
| 4 | Duplicate detection preserved? | **Yes** — same `document_id` set semantics at spool/plan. |
| 5 | Full-replace publication preserved? | **Yes** (D00). |
| 6 | Failure atomicity preserved? | **Yes** — meta-after-integrity; journal publish rules; spool quarantine. |
| 7 | Temporary-disk behavior modeled? | **Yes** (§7, D07). |
| 8 | Reproducible measurement before new limit claim? | **Yes** (§8); not executed here. |
| 9 | Per-file / request / workspace limits separated? | **Yes** (§9); values TBD post-L5. |
| 10 | Bounded slices without redesigning retrieval science? | **Yes** (§14). |

### Unresolved design questions

**NONE** blocking design acceptance.

Open **implementation/measurement** items (explicitly deferred, not design
blockers):

- exact copy buffer default \(B\);
- exact disk preflight multiplier \(k\) after L5;
- final numeric product limits after L5/L6;
- whether optional reflink is worth enabling on Linux workspaces.

---

## 16. Non-authorizations

This design does **not** permit:

- production implementation;
- raising 25 MiB/file or 100 MiB/request;
- editing `config/base.yaml` limits;
- running 100/250/512 MiB qualification;
- full1296; embedding campaigns; retrieval science changes;
- main promotion; release; deployment;
- any new product-support claim for large sources.

---

## 17. Summary decisions ledger

| ID | Decision |
|---|---|
| D00 | Retain full-replace publication |
| D01 | Path/stream SHA-256 identity APIs; byte APIs remain |
| D02 | `put_path` + verify; `load_bytes` compatibility only |
| D03 | Streamed projection copy; reflink optional non-required |
| D04 | Streaming `spool_local_files` |
| D05 | Reuse spool/vault identity; no validate `read_bytes` |
| D06 | Path + `(document_id, content_hash)` parser contract |
| D07 | Conservative disk preflight before heavy rebuild |
