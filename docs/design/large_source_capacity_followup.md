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

For a workspace SOURCE_ADD on a large existing workspace, durable/disk copies can include:

1. Upload spool/staging file
2. Vault object
3. Projection scratch files for **all** desired active sources (full-replace rewrite)
4. Candidate/stage corpora tree used by ingest
5. Published corpus/index artifacts

**Peak RAM vs aggregate work (important distinction):**

- `materialize_desired_sources()` loops sequentially: `data = load_bytes(...)` → `path.write_bytes(data)` → retain metadata only. It does **not** retain every source's `data` buffer simultaneously.
- Therefore **I/O, disk materialization, and wall-clock work** scale with aggregate workspace bytes \(A\).
- **Peak RAM in that loop** is closer to the size of the largest source currently being copied (plus interpreter/copy overhead), not \(O(N)\) simultaneous full bodies.
- Later stages (plan/vault `load_bytes`, ingestion `read_bytes`, Seneca's Docling wrapper buffers) can still place **at least one whole-file \(S\)-sized Python `bytes` buffer** in memory for the source currently being processed, in addition to an unmeasured parser working set \(D(S)\).

### 3. Does Docling require bytes and path simultaneously?

**Seneca's current interface does.** `DoclingPdfParser.parse(path, *, source_bytes, document_id)` requires both a path and `source_bytes`. Docling itself is invoked using the **path**; callers currently also supply matching `source_bytes` for identity/hash and therefore read the full file into memory first (`ingestion/pipeline.py`).

That is a **Seneca refactoring opportunity** (stream/hash + path-only parse), not evidence that Docling itself necessarily requires a second in-memory copy.

### 4. Can document identity/content hash be streamed?

Yes for the upload spool path: sha256 is already incremental during multipart write.  
Vault/`document_id_for_content` / `document_id_from_bytes` currently assume a complete `bytes` object. Streaming hash + `doc_<hex>` identity is feasible without holding the full body **if** vault put and identity APIs gain stream/path variants.

### 5. Can vault and candidate materialization avoid another complete memory copy?

Not with the current APIs. `RawSourceVault.load_bytes` and `materialize_desired_sources` always allocate full `bytes`. A path-based or chunked copy (`shutil.copyfileobj`) would remove the RAM amplification for unchanged sources during full-replace.

### 6. What happens when a workspace already has many sources and one large source is added?

SOURCE_ADD rebuilds the **entire desired active set** through Slice-15 full-replace ingest (`lifecycle` rule 2). Every prior source is re-materialized from the vault into scratch and re-fed to the ingest pipeline. **Disk I/O and end-to-end work** therefore scale with **aggregate workspace source bytes**, not only the newly uploaded file. Peak RAM remains dominated by whole-file buffers for the source currently being copied/parsed, plus unmeasured \(D(S)\), not by retaining all \(N\) bodies at once.

### 7. Expected peak RAM (code-supported bounds; unmeasured)

Let \(S\) be the source currently being processed. From the code paths above:

- At least one whole-file \(S\)-sized Python `bytes` buffer is present in several **sequential** stages (`load_bytes` / `read_bytes` / `source_bytes`).
- Docling adds an **unmeasured** parser working set \(D(S)\).
- Peak RAM for 100 / 250 / 512 MiB inputs has **not** been benchmarked in this follow-up.

| Source size \(S\) | Claim under current architecture |
|---|---|
| 25 MiB | Current supported product ceiling (unchanged) |
| 100 MiB | Whole-file buffers exist; \(D(S)\) unknown; **not** proven safe to raise limits |
| 250 MiB | Same; unsupported as a product claim without measurement + streaming refactor |
| 512 MiB | **Not supportable** as a product claim under current whole-file RAM paths |

These code-supported unknowns are sufficient to reject a blind limit bump. They are **not** laboratory peak-RAM measurements.

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
