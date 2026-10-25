# Large-source capacity follow-up (P4 human-UAT)

Authority context: P4 HUMAN UAT FOLLOW-UP (post IR-002).  
This note is design/feasibility only. It does **not** authorize raising product limits.

Current product ceilings (config / capabilities):

- `api.max_bytes_per_document` = **25 MiB** (`26_214_400`)
- `api.max_total_upload_bytes` = **100 MiB** (`104_857_600`)

Observed UAT: a ~227 MiB technical PDF is correctly rejected by the UI before upload. That is a capacity limit, not a transport/UI defect.

## Terminal disposition

**CAPACITY_DESIGN_READY**

`SAFE_LIMIT_INCREASE_PROVEN` is **not** claimed. Downstream ingestion still materializes full source bytes in RAM in multiple places; raising 25 MiB → 512 MiB under the current architecture would over-claim support.

## Answers

### 1. Where are full document bytes materialized in RAM?

| Location | Behavior |
|---|---|
| `app/workspace/upload_spool.py` | Multipart parts are **streamed to disk** while hashing incrementally (`digest.update`). Good. |
| `app/workspace/lifecycle.py` `SourceUpload.load_bytes` / `_plan_add` / `_vault_source_version` | Loads **entire** spool/vault object via `Path.read_bytes()` / vault `load_bytes`. |
| `app/workspace/vault.py` `put_bytes` / `load_bytes` | Writes/reads **full** object bytes; `put_bytes` also re-reads for digest check. |
| `app/workspace/projection.py` `materialize_desired_sources` | For **each** desired active source: `load_bytes` → `path.write_bytes(data)` (full copy into scratch). |
| `app/ingest.py` `_validate_document_identities` | `item.absolute_path.read_bytes()` per uploaded file. |
| `app/ingest_upload.py` path-based spool helper | `path.read_bytes()` then `write_bytes` (legacy/local path). |
| `ingestion/pipeline.py` | `source.absolute_path.read_bytes()` then passes `source_bytes` into Docling parse. |

### 2. How many simultaneous copies of a PDF can exist?

For a workspace SOURCE_ADD on a large existing workspace, peak concurrent logical copies can include:

1. Durable vault object (disk)
2. Spool/staging file (disk; upload path)
3. In-memory `bytes` from `load_bytes` during plan/vault
4. In-memory `bytes` again during `materialize_desired_sources` for **every** active source (full-replace)
5. Scratch file rewrite of those bytes (disk)
6. In-memory `source_bytes` again in `run_ingestion` / Docling path

So for one large add into a workspace with \(N\) active sources, the architecture may hold **O(N)** full source bodies in memory across the materialization loop (sequentially per source, but still whole-file), plus an additional whole-file buffer in the parser stage for the source currently being parsed.

### 3. Does Docling require bytes and path simultaneously?

Yes. `DoclingPdfParser.parse(path, *, source_bytes, document_id)` documents that Docling **reads the path**, while callers must also supply matching `source_bytes` for identity/hash. Callers currently satisfy this by reading the full file into memory first (`ingestion/pipeline.py`).

### 4. Can document identity/content hash be streamed?

Yes for the upload spool path: sha256 is already incremental during multipart write.  
Vault/`document_id_for_content` / `document_id_from_bytes` currently assume a complete `bytes` object. Streaming hash + `doc_<hex>` identity is feasible without holding the full body **if** vault put and identity APIs gain stream/path variants.

### 5. Can vault and candidate materialization avoid another complete memory copy?

Not with the current APIs. `RawSourceVault.load_bytes` and `materialize_desired_sources` always allocate full `bytes`. A path-based or chunked copy (`shutil.copyfileobj`) would remove the RAM amplification for unchanged sources during full-replace.

### 6. What happens when a workspace already has many sources and one large source is added?

SOURCE_ADD rebuilds the **entire desired active set** through Slice-15 full-replace ingest (`lifecycle` rule 2). Every prior source is re-materialized from the vault into scratch and re-fed to the ingest pipeline. Cost and peak memory therefore scale with **aggregate workspace source bytes**, not only the newly uploaded file.

### 7. Expected peak RAM (order-of-magnitude, current architecture)

Assumptions: one large new source of size \(S\); workspace aggregate active bytes \(A\); sequential materialization; Docling may add its own working set \(D(S)\) (not measured here).

| Source size \(S\) | Conservative peak (ingestion process) |
|---|---|
| 25 MiB | ~1–3×\(S\) plus \(D(S)\) plus smaller per-source buffers while scanning \(A\) |
| 100 MiB | similar multiple; often **>300 MiB** process growth before Docling |
| 250 MiB | often **>0.75–1.5 GiB** class risk once Docling + scratch + vault buffers overlap |
| 512 MiB | **not supportable** as a product claim under current whole-file RAM paths |

These are engineering bounds from code shape, not lab measurements. They are sufficient to reject a blind limit bump.

### 8. Disk amplification during staging/candidate/publication

Typical durable copies for one add:

- upload spool file
- vault object
- projection scratch files for **all** desired sources
- candidate/stage corpora tree used by full-replace ingest
- published corpus/index artifacts (existing Slice-15 behavior)

Amplification is therefore **multiplicative in workspace size**, not only in \(S\).

### 9. What product limit is safe for the current architecture?

Keep the present ceilings:

- **25 MiB / file**
- **100 MiB / request**

until streaming identity + path-based materialization/parser integration lands. A modest increase (for example 40–50 MiB) is still **not** proven without measurement of Docling \(D(S)\) on representative handbooks.

### 10. Refactor required for a 512 MiB supported ceiling

Preferred end-state:

```
HTTP multipart streaming
  → durable disk spool (already present)
  → streaming identity/hash (partially present on spool)
  → vault put from path / file object (no full RAM buffer)
  → path-based desired-set materialization (copyfile, not load_bytes)
  → path-based parser API (Docling path only; hash from stream)
  → bounded-memory ingestion + coherent aggregate limits
```

Also revise aggregate limits coherently (must not leave `per-file=512 MiB` with `per-request=100 MiB`).

Future product target (not authorized now): **≥512 MiB per source** for technical handbooks, with a matching request/workspace aggregate policy.

## Decision

Do **not** raise constants in this corrective.  
Record terminal: **CAPACITY_DESIGN_READY**.
